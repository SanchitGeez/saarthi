"""Owned, bounded LiveKit calls. No model credentials ever reach the client."""
import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid5, NAMESPACE_URL

from fastapi import APIRouter, Depends, HTTPException
from livekit import api
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import TurnContext, commit_memories
from app.auth import current_user
from app.config import settings
from app.db import get_db, SessionLocal
from app.models import ChatTurn, Conversation, User, VoiceMessage, VoiceSession

router = APIRouter(prefix='/api/voice/sessions')
logger = logging.getLogger(__name__)
ACTIVE = ('connecting', 'active')
CONNECT_TIMEOUT = timedelta(seconds=60)


def expired(call, now):
    return call.expires_at <= now or (call.status == 'connecting' and now - call.created_at > CONNECT_TIMEOUT)


class StartCall(BaseModel):
    client_id: UUID
    conversation_id: UUID


from app.providers import missing_credentials


def voice_available():
    return bool(settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret
                and not missing_credentials())


def participant_identity(call):
    return f'user-{call.user_id}'


def join_token(call):
    # Dispatch only when this unique room is first created. A reconnect to an
    # existing room cannot start another greeting/worker.
    return (api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(participant_identity(call)).with_name('You')
        .with_ttl(timedelta(minutes=2))
        .with_grants(api.VideoGrants(room_join=True, room=call.room_name,
            can_publish=True, can_subscribe=True, can_publish_data=True,
            can_publish_sources=['microphone'], can_update_own_metadata=False))
        .with_room_config(api.RoomConfiguration(
            empty_timeout=30, max_participants=2,
            agents=[api.RoomAgentDispatch(agent_name=settings.livekit_agent_name,
                metadata=json.dumps({'session_id': str(call.id)}))]))
        .to_jwt())


async def remove_room(room_name):
    if not settings.livekit_url:
        return
    async with api.LiveKitAPI(settings.livekit_url, settings.livekit_api_key, settings.livekit_api_secret) as lk:
        try:
            async with asyncio.timeout(8):
                await lk.room.delete_room(api.DeleteRoomRequest(room=room_name))
        except api.TwirpError as exc:
            if exc.code != 'not_found':
                raise


@router.get('/status')
async def status(user: User = Depends(current_user)):
    return {'available': voice_available(), 'max_seconds': settings.voice_max_seconds}


@router.post('')
async def start_call(payload: StartCall, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if not voice_available():
        raise HTTPException(503, 'Live calls are not configured yet. You can still type to Parth.')
    # Serializes starts across tabs/devices and deletion/preferences on this user.
    await db.scalar(select(User).where(User.id == user.id).with_for_update())
    conversation = await db.scalar(select(Conversation).where(
        Conversation.id == payload.conversation_id, Conversation.user_id == user.id,
    ).with_for_update())
    if conversation is None:
        raise HTTPException(404, 'That conversation is no longer here.')
    now = datetime.now(UTC)
    call = await db.get(VoiceSession, payload.client_id)
    if call:
        if call.user_id != user.id or call.conversation_id != conversation.id:
            raise HTTPException(404, 'That call is no longer here.')
        if call.status not in ACTIVE or expired(call, now):
            raise HTTPException(409, 'That call has ended. Start a new call.')
    else:
        existing = await db.scalars(select(VoiceSession).where(
            VoiceSession.user_id == user.id, VoiceSession.status.in_((*ACTIVE, "closing")),
        ).with_for_update())
        for other in existing:
            if other.status in ACTIVE and not expired(other, now):
                raise HTTPException(409, 'End your current call before starting another.')
            # Cleanup must succeed before opening another billable room.
            try:
                await remove_room(other.room_name)
            except Exception as exc:
                raise HTTPException(503, 'The previous call is still closing. Please retry.') from exc
            other.status, other.ended_at = 'ended', now
        processing = await db.scalar(select(ChatTurn.id).where(
            ChatTurn.conversation_id == conversation.id, ChatTurn.status == 'processing',
            ChatTurn.updated_at > now - timedelta(seconds=120),
        ).limit(1))
        if processing:
            raise HTTPException(409, 'Wait for the typed reply before starting a call.')
        call = VoiceSession(id=payload.client_id, user_id=user.id, conversation_id=conversation.id,
            room_name=f'saarthi-{payload.client_id.hex}', status='connecting',
            expires_at=now + timedelta(seconds=settings.voice_max_seconds))
        db.add(call)
    token = join_token(call)
    await db.commit()
    return {'session_id': str(call.id), 'conversation_id': str(call.conversation_id),
            'server_url': settings.livekit_url, 'participant_token': token,
            'expires_at': call.expires_at}


@router.delete('/{session_id}', status_code=204)
async def end_call(session_id: UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await db.scalar(select(User).where(User.id == user.id).with_for_update())
    call = await db.scalar(select(VoiceSession).where(
        VoiceSession.id == session_id, VoiceSession.user_id == user.id,
    ).with_for_update())
    if call is None:
        raise HTTPException(404, 'That call is no longer here.')
    call.status, call.ended_at = 'closing', datetime.now(UTC)
    await db.commit()  # deny further tools/writes even if media teardown is delayed
    try:
        await remove_room(call.room_name)
    except Exception as exc:
        logger.warning('Room cleanup failed (%s)', type(exc).__name__)
        raise HTTPException(503, 'The microphone is closed on this device. Retry to finish closing the call.') from exc
    call.status = 'ended'
    await db.commit()


async def close_user_calls(db, user_id, conversation_id=None):
    calls = await db.scalars(select(VoiceSession).where(
        VoiceSession.user_id == user_id,
        *([VoiceSession.conversation_id == conversation_id] if conversation_id else []),
    ))
    for call in calls:
        # Include ended rows: a previous media cleanup may have failed.
        await remove_room(call.room_name)
        call.status, call.ended_at = 'ended', datetime.now(UTC)


def message_id(session_id, event_id):
    return uuid5(NAMESPACE_URL, f'saarthi-voice:{session_id}:{event_id}')


async def record_message(session_id, event_id, role, value, timestamp, interrupted=False):
    value = value.strip()
    if not value or role not in {'user', 'assistant'}:
        return None
    async with SessionLocal() as db:
        # User lock is shared by voice writes/memory/deletion; a deleted chat
        # cannot be resurrected by a late event or tool.
        call = await db.get(VoiceSession, session_id)
        if not call:
            return None
        user = await db.scalar(select(User).where(User.id == call.user_id).with_for_update())
        call = await db.get(VoiceSession, session_id, populate_existing=True)
        if not user or not call or call.status not in ACTIVE or call.expires_at <= datetime.now(UTC):
            return None
        conversation = await db.get(Conversation, call.conversation_id)
        if not conversation:
            return None
        item_id = message_id(session_id, event_id)
        if await db.get(VoiceMessage, item_id):
            return item_id
        db.add(VoiceMessage(id=item_id, session_id=session_id, conversation_id=call.conversation_id,
            event_id=event_id, role=role, text=value[:10000], interrupted=interrupted,
            created_at=datetime.fromtimestamp(timestamp, UTC)))
        conversation.updated_at = datetime.now(UTC)
        if role == 'user' and conversation.title == 'A new conversation':
            conversation.title = ' '.join(value.split())[:56]
        await db.commit()
        return item_id


async def remember_from_voice(session_id, source_id, content, kind, evidence, memory_id=None):
    from app.guidance import queue_memory
    async with SessionLocal() as db:
        call = await db.get(VoiceSession, session_id)
        if not call:
            return {'saved': False, 'reason': 'Call ended.'}
        user = await db.scalar(select(User).where(User.id == call.user_id).with_for_update())
        call = await db.get(VoiceSession, session_id, populate_existing=True)
        if not user or not call or call.status not in ACTIVE or call.expires_at <= datetime.now(UTC):
            return {'saved': False, 'reason': 'Call ended.'}
        conversation = await db.get(Conversation, call.conversation_id)
        source = await db.get(VoiceMessage, source_id)
        latest = await db.scalar(select(VoiceMessage.id).where(
            VoiceMessage.session_id == session_id, VoiceMessage.role == 'user',
        ).order_by(VoiceMessage.created_at.desc(), VoiceMessage.id.desc()).limit(1))
        if (not conversation or not source or source.session_id != session_id or
                source.role != 'user' or source.id != latest or source.memory_saved):
            return {'saved': False, 'reason': 'Use the current user turn, once.'}
        context = TurnContext(user.id, conversation.id, source.text,
            user.memory_enabled and not conversation.private)
        result = queue_memory(context, content, kind, evidence)
        if not result['saved']:
            return result
        if memory_id:
            context.memory_changes[0]['memory_id'] = str(memory_id)
        saved = await commit_memories(db, context)
        source.memory_saved = bool(saved)
        await db.commit()
        return {'saved': bool(saved), 'reason': 'Saved.' if saved else 'Already remembered or unavailable.'}
