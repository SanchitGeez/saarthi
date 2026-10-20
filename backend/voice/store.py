"""Short transactions; no audio or provisional assistant text is persisted."""

from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

from core import data, service
from core.errors import Problem
from core.models import Message, now

LEASE_SECONDS = 30


def acquire(factory, user_id, conversation_id, token):
    with factory.begin() as db:
        data.lock_user(db, user_id)
        conv = service.owned(db, user_id, conversation_id)
        if conv.status != "active":
            raise Problem(409, "conversation_ended", "This conversation has ended.")
        if conv.generation_status != "idle":
            raise Problem(409, "message_pending", "Finish the pending text reply first.")
        service.claim(conv, SimpleNamespace(agent_timeout_seconds=15))
        service.clear_claim(conv)
        conv.voice_token = token
        conv.voice_expires_at = now() + timedelta(seconds=LEASE_SECONDS)


def owner(db, user_id, conversation_id, token):
    user = data.lock_user(db, user_id)
    conv = service.owned(db, user_id, conversation_id)
    if (
        conv.voice_token != token
        or not conv.voice_expires_at
        or conv.voice_expires_at <= now()
        or conv.status != "active"
    ):
        raise Problem(409, "voice_superseded", "Voice session expired. Reconnect to continue.")
    return user, conv


def renew(factory, user_id, conversation_id, token, auth_hash):
    with factory.begin() as db:
        user, conv = owner(db, user_id, conversation_id, token)
        if user.session_token_hash != auth_hash or user.session_expires_at <= now():
            raise Problem(401, "unauthenticated", "Sign in again.")
        conv.voice_expires_at = now() + timedelta(seconds=LEASE_SECONDS)


def release(factory, user_id, conversation_id, token):
    with factory.begin() as db:
        data.lock_user(db, user_id)
        conv = service.owned(db, user_id, conversation_id)
        if conv.voice_token == token:
            conv.voice_token = conv.voice_expires_at = None


def prepare(factory, user_id, conversation_id, token, text, message_id):
    with factory.begin() as db:
        user, conv = owner(db, user_id, conversation_id, token)
        payload = service.context(db, user)
        rows = data.messages(db, conv.id)
        if not 1 <= len(text) <= 4000:
            raise Problem(422, "voice_input_limit", "Please use a shorter voice turn.")
        if (
            sum(len(m.content.encode()) for m in rows) + len(text.encode()) + 32000
            > service.TRANSCRIPT_LIMIT
        ):
            raise Problem(409, "transcript_limit", "This chat is full. Leave voice and end it.")
        previous = data.message_by_id(db, message_id)
        if previous is None:
            previous = Message(id=message_id, conversation_id=conv.id, role="user", content=text)
            db.add(previous)
            db.flush()
            rows.append(previous)
            if len(rows) == 2:
                conv.title = text[:80]
        elif previous.conversation_id != conv.id or previous.content != text:
            raise Problem(409, "id_conflict", "Voice turn ID conflict.")
        conv.updated_at = now()
        payload.update(
            opening=False,
            transcript=[
                {
                    "role": m.role,
                    "content": m.content,
                    **({"interrupted": True} if m.delivery_status == "interrupted" else {}),
                }
                for m in rows
            ],
        )
        return payload


def commit(
    factory, user_id, conversation_id, token, message_id, text, interrupted, *, notice_id=None
):
    with factory.begin() as db:
        _, conv = owner(db, user_id, conversation_id, token)
        previous = (
            db.get(Message, notice_id)
            if notice_id
            else data.assistant_reply(db, conv.id, message_id)
        )
        if text.strip():
            if previous is None:
                db.add(
                    Message(
                        id=notice_id or uuid4(),
                        kind="voice_notice" if notice_id else "reply",
                        conversation_id=conv.id,
                        role="assistant",
                        reply_to_id=message_id,
                        content=text.strip(),
                        delivery_status="interrupted" if interrupted else "complete",
                    )
                )
            elif previous.delivery_status == "interrupted" and text.strip().startswith(
                previous.content
            ):
                previous.content = text.strip()
                previous.delivery_status = "interrupted" if interrupted else "complete"
        conv.updated_at = now()
