"""Authenticated lifecycle/signaling; provider keys never cross the browser boundary."""

import asyncio
from contextlib import suppress
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from core import service
from core.errors import Problem
from core.routes import onboarded
from voice import store
from voice.session import VoiceSession

router = APIRouter(prefix="/voice", tags=["voice"])


class Start(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    conversation_id: UUID
    resume: bool = False


class Offer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sdp: str = Field(min_length=1, max_length=64000)
    type: str = Field(pattern="^offer$")


def sessions(request):
    return request.app.state.voice_sessions


def get(request, user, identifier):
    session = sessions(request).get(identifier)
    if not session or session.user_id != user.id:
        raise Problem(404, "not_found", "Voice session not found on this worker. Reconnect.")
    if session.closed:
        raise Problem(409, "voice_closed", "Voice session closed. Reconnect.")
    return session


@router.post("/sessions", status_code=201)
async def start(body: Start, request: Request, user=Depends(onboarded)):
    settings = request.app.state.settings
    if not settings.voice_enabled:
        raise Problem(503, "voice_disabled", "Voice is not enabled on this server.")
    if not all(
        (
            settings.deepgram_api_key,
            settings.cartesia_api_key,
            settings.openrouter_api_key,
            settings.cartesia_voice_id,
        )
    ):
        raise Problem(
            503, "voice_not_configured", "Configure the voice provider keys and Cartesia voice ID."
        )
    existing = sessions(request).get(body.id)
    if existing:
        if existing.user_id != user.id or existing.conversation_id != body.conversation_id:
            raise Problem(409, "id_conflict", "Voice session ID already used.")
        if not existing.closed:
            return {"id": str(body.id)}
        raise Problem(409, "voice_closed", "Use a new voice session ID.")
    try:
        from voice.pipeline import build  # noqa: F401
    except ImportError:
        raise Problem(
            503, "voice_dependencies", "Install the backend voice extra with Python 3.12."
        ) from None
    # Prune closed records, keeping a bounded registry for this process.
    for key, entry in list(sessions(request).items()):
        if entry.closed:
            sessions(request).pop(key, None)
    if len(sessions(request)) >= 10:
        raise Problem(503, "voice_capacity", "Voice server is busy. Retry shortly.")
    store.acquire(request.app.state.db, user.id, body.conversation_id, body.id)
    session = VoiceSession(
        request.app.state.db,
        settings,
        user.id,
        body.conversation_id,
        service.digest(request.cookies["saarthi_session"]),
        body.id,
    )
    session.resume = body.resume
    sessions(request)[body.id] = session
    # Includes permission/signaling time, so abandoned starts cannot retain ownership.
    session.watch_task = asyncio.create_task(session.watch())
    return {"id": str(body.id)}


@router.post("/sessions/{identifier}/offer")
async def offer(identifier: UUID, body: Offer, request: Request, user=Depends(onboarded)):
    session = get(request, user, identifier)
    from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection

    from voice.pipeline import build

    if session.connection:
        raise Problem(409, "offer_exists", "Start a new connection after reconnecting.")
    connection = SmallWebRTCConnection(ice_servers=[], connection_timeout_secs=15)
    session.connection = connection
    try:
        store.renew(
            session.factory, user.id, session.conversation_id, session.token, session.auth_hash
        )
        await connection.initialize(body.sdp, body.type)
        if session.closed:
            await connection.disconnect()
            raise Problem(409, "voice_closed", "Voice was closed while connecting.")
        if session.watch_task:
            session.watch_task.cancel()
        await build(session, connection)
        return connection.get_answer()
    except Exception:
        await session.close()
        raise Problem(
            502, "voice_connect_failed", "Voice connection failed. Reconnect to retry."
        ) from None


@router.delete("/sessions/{identifier}", status_code=204)
async def stop(identifier: UUID, request: Request, user=Depends(onboarded)):
    session = sessions(request).get(identifier)
    if session and session.user_id == user.id:
        await session.close()
        sessions(request).pop(identifier, None)
    # A different worker can revoke a lease even without the process-local media handle.
    with suppress(Problem):
        with request.app.state.db() as db:
            from sqlalchemy import select

            from core.models import Conversation

            conv = db.scalar(
                select(Conversation).where(
                    Conversation.voice_token == identifier, Conversation.user_id == user.id
                )
            )
            conversation_id = conv.id if conv else None
        if conversation_id:
            store.release(request.app.state.db, user.id, conversation_id, identifier)
