"""Durable chat delivery, idempotent retries, and legacy ADK history import."""
import asyncio
from datetime import UTC, datetime, timedelta
import logging
import re
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import TurnContext, commit_memories, reset_turn_context, run_turn, set_turn_context
from app.auth import current_user
from app.config import settings
from app.db import get_db
from app.models import ChatTurn, Conversation, User, VoiceSession
from app.conversation_history import merge_voice_history
from app.schemas import TurnRequest
from app.scripture import verse_payload

router = APIRouter(prefix="/api/conversations")
logger = logging.getLogger(__name__)
LEASE = timedelta(seconds=120)


async def owned(conversation_id, user, db, lock=False):
    query = select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user.id)
    if lock:
        query = query.with_for_update()
    item = await db.scalar(query)
    if item is None:
        raise HTTPException(404, "That conversation is no longer here.")
    return item


async def load_turns(conversation, user, db, request):
    rows = list(await db.scalars(select(ChatTurn).where(
        ChatTurn.conversation_id == conversation.id,
    ).order_by(ChatTurn.created_at, ChatTurn.id)))
    if not rows:
        # Preserve existing conversations without making ADK events the delivery log.
        session = await request.app.state.session_service.get_session(
            app_name=settings.app_name, user_id=str(user.id), session_id=str(conversation.id))
        current = None
        if session:
            for event in session.events:
                if not event.content or not event.content.parts:
                    continue
                value = "".join(p.text or "" for p in event.content.parts if not p.thought).strip()
                if not value:
                    continue
                if event.author == "user":
                    current = ChatTurn(
                        id=uuid5(NAMESPACE_URL, f"saarthi:{conversation.id}:{event.id}"),
                        conversation_id=conversation.id, text=value, status="failed",
                        error="This earlier message did not receive a reply. You can retry it.",
                        error_code=502, scripture_refs=[],
                        created_at=datetime.fromtimestamp(event.timestamp, UTC),
                        updated_at=datetime.fromtimestamp(event.timestamp, UTC),
                    )
                    rows.append(current)
                elif event.author in {"mitra", "saarthi"} and event.is_final_response() and current:
                    current.answer = value
                    current.status = "completed"
                    current.error = None
                    current.error_code = None
                    current = None
            for row in rows:
                db.add(row)
            await db.flush()
    now = datetime.now(UTC)
    for row in rows:
        if row.status == "processing" and now - row.updated_at > LEASE:
            row.status = "failed"
            row.error = "The reply was interrupted. Retry this message when you're ready."
            row.error_code = 504
    return rows


def messages_payload(rows):
    messages = []
    for row in rows:
        if row.status == "discarded":
            continue
        messages.append({
            "id": str(row.id), "turn_id": str(row.id), "role": "user", "text": row.text,
            "status": row.status, "error": row.error, "error_code": row.error_code,
            "created_at": row.created_at,
        })
        if row.status == "completed" and row.answer:
            messages.append({
                "id": f"{row.id}-reply", "turn_id": str(row.id), "role": "assistant",
                "text": row.answer, "status": "completed", "created_at": row.updated_at,
                "verses": [verse_payload(r) for r in row.scripture_refs if verse_payload(r)],
            })
    return messages


def reply_payload(turn, conversation):
    return {**messages_payload([turn])[-1], "conversation_title": conversation.title}


@router.get("/{conversation_id}/messages")
async def get_messages(conversation_id: UUID, request: Request,
                       user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    conversation = await owned(conversation_id, user, db, lock=True)
    rows = await load_turns(conversation, user, db, request)
    await db.commit()
    return await merge_voice_history(db, conversation_id, messages_payload(rows))


@router.post("/{conversation_id}/turns")
async def send_turn(conversation_id: UUID, payload: TurnRequest, request: Request,
                    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    user_text = payload.text.strip()
    if not user_text:
        raise HTTPException(422, "Write a little about what's on your mind.")
    await db.scalar(select(User).where(User.id == user.id).with_for_update())
    conversation = await owned(conversation_id, user, db, lock=True)
    if await db.scalar(select(VoiceSession.id).where(
        VoiceSession.conversation_id == conversation_id, VoiceSession.status.in_(("connecting", "active")),
        VoiceSession.expires_at > datetime.now(UTC),
        or_(VoiceSession.status == "active", VoiceSession.created_at > datetime.now(UTC) - timedelta(seconds=60)),
    ).limit(1)):
        raise HTTPException(409, "End your call before sending a typed message.")
    rows = await load_turns(conversation, user, db, request)
    turn_id = payload.client_id or uuid4()
    existing = await db.get(ChatTurn, turn_id)
    if existing and existing.conversation_id != conversation.id:
        raise HTTPException(404, "That message is no longer here.")
    if existing and existing.text != user_text:
        raise HTTPException(409, "A retry must use the original message.")
    if existing and existing.status == "completed":
        await db.commit()
        return reply_payload(existing, conversation)
    if any(row.status == "processing" for row in rows):
        await db.commit()
        raise HTTPException(409, "Saarthi is still replying. Your message is saved; check again in a moment.")
    if sum(row.status == "completed" for row in rows) >= 50:
        raise HTTPException(409, "Start a new conversation so Saarthi can stay focused.")
    turn = existing or ChatTurn(id=turn_id, conversation_id=conversation.id, text=user_text)
    if existing is None:
        db.add(turn)
    turn.status, turn.error, turn.error_code = "processing", None, None
    turn.updated_at = datetime.now(UTC)
    conversation.updated_at = datetime.now(UTC)
    if conversation.title == "A new conversation":
        first_sentence = re.split(r"(?<=[.!?।])\s+", user_text.strip())[0]
        title = " ".join(first_sentence.split())
        conversation.title = title if len(title) <= 56 else title[:56].rsplit(" ", 1)[0] + "…"
    await db.commit()  # delivery survives a process restart or disconnected phone
    context = TurnContext(user.id, conversation.id, user_text, user.memory_enabled and not conversation.private)
    token = set_turn_context(context)
    failure_code, failure = None, None
    try:
        from app.providers import missing_credentials
        if missing_credentials(voice=False):
            raise RuntimeError("Chat is not configured.")
        successful = [row for row in rows if row.status == "completed"]
        history = await merge_voice_history(db, conversation.id, messages_payload(successful))
        async with asyncio.timeout(90):
            try:
                answer = await run_turn(user.id, conversation.id, user_text, successful, user.language, messages=history)
            except Exception as provider_error:
                code = getattr(provider_error, "code", getattr(provider_error, "status_code", None))
                fallback = settings.gemini_fallback_model
                if settings.llm_provider != "gemini" or code not in {429, 503} or not fallback or fallback == settings.gemini_model:
                    raise
                # One bounded fallback for model overload or rate limits; no retry loop.
                # Discard tool changes from the abandoned invocation.
                context.memory_changes.clear()
                context.scripture_refs.clear()
                logger.info("Primary Gemini model unavailable; trying configured fallback once")
                answer = await run_turn(user.id, conversation.id, user_text, successful, user.language, fallback, messages=history)
        if not answer:
            raise RuntimeError("Empty assistant response.")
        # Only tool-verified markers may survive into a saved reply.
        used = re.findall(r"\[\[gita:([\d.]+)\]\]", answer)
        refs = [r for r in context.scripture_refs if r in used][:1]
        answer = re.sub(r"\[\[gita:([\d.]+)\]\]",
                        lambda m: m.group(0) if m.group(1) in refs else "", answer).strip()
        await commit_memories(db, context)
        turn.answer, turn.scripture_refs, turn.status = answer, refs, "completed"
        turn.updated_at = datetime.now(UTC)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        code = getattr(exc, "code", getattr(exc, "status_code", None))
        failure_code = 504 if isinstance(exc, TimeoutError) else code if code in {429, 503} else 502
        failure = {
            429: "Saarthi has reached its chat limit. Please retry later.",
            503: "Saarthi is temporarily unavailable. Please retry in a moment.",
            504: "The reply took too long. Your message is saved; you can retry it.",
        }.get(failure_code, "The reply couldn't be completed. Your message is saved; please retry.")
        logger.warning("Agent turn failed (%s, upstream_status=%s)", type(exc).__name__, code)
        turn = await db.get(ChatTurn, turn_id, populate_existing=True)
        turn.status, turn.error, turn.error_code = "failed", failure, failure_code
        turn.updated_at = datetime.now(UTC)
        await db.commit()
    finally:
        reset_turn_context(token)
    if failure:
        raise HTTPException(failure_code, failure, headers={"Retry-After": "30"} if failure_code == 429 else None)
    return reply_payload(turn, conversation)


@router.delete("/{conversation_id}/turns/{turn_id}", status_code=204)
async def discard_failed_turn(conversation_id: UUID, turn_id: UUID,
                             user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await owned(conversation_id, user, db, lock=True)
    turn = await db.scalar(select(ChatTurn).where(ChatTurn.id == turn_id, ChatTurn.conversation_id == conversation_id))
    if turn is None:
        raise HTTPException(404, "That message is no longer here.")
    if turn.status != "failed":
        raise HTTPException(409, "Only an unfinished message can be removed here.")
    # A content-free tombstone prevents a removed legacy ADK message from being
    # imported again when this was the conversation's only turn.
    turn.status, turn.text, turn.answer = "discarded", "", None
    turn.error, turn.error_code, turn.scripture_refs = None, None, []
    await db.commit()
