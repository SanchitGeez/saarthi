from __future__ import annotations

import secrets
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from google.adk.sessions import DatabaseSessionService
from sqlalchemy import delete, desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import embed
from app.turns import router as turns_router
from app.auth import (
    create_access_token,
    current_user,
    hash_code,
    normalize_email,
    send_code,
    smtp_is_configured,
)
from app.config import settings
from app.db import engine, get_db
from app.models import AuthCode, Base, Conversation, Memory, User
from app.schemas import (
    CodeRequest,
    CodeVerify,
    ConversationCreate,
    MemoryPatch,
    PreferencesPatch,
    SpeechRequest,
)
from app.voice import speak, transcribe

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await connection.run_sync(Base.metadata.create_all)
    session_service = DatabaseSessionService(db_url=settings.database_url)
    app.state.session_service = session_service
    try:
        yield
    finally:
        await session_service.close()
        await engine.dispose()


app = FastAPI(title="Saarthi API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


app.include_router(turns_router)

@app.get("/api/health")
async def health(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"ok": True, "service": "saarthi-api"}


@app.post("/api/auth/request-code")
async def request_code(payload: CodeRequest, db: AsyncSession = Depends(get_db)):
    email = normalize_email(str(payload.email))
    now = datetime.now(UTC)
    await db.execute(delete(AuthCode).where(AuthCode.expires_at < now - timedelta(days=1)))
    recent = await db.scalar(
        select(AuthCode)
        .where(AuthCode.email == email, AuthCode.consumed_at.is_(None), AuthCode.created_at > now - timedelta(seconds=45))
        .order_by(desc(AuthCode.created_at))
        .limit(1)
    )
    if recent:
        wait = max(1, 45 - int((now - recent.created_at).total_seconds()))
        raise HTTPException(status_code=429, detail=f"Please wait {wait} seconds before requesting another code.",
                            headers={"Retry-After": str(wait)})
    if not settings.is_development and not smtp_is_configured():
        raise HTTPException(status_code=503, detail="Email sign-in is not configured yet.")

    code = f"{secrets.randbelow(1_000_000):06d}"
    record = AuthCode(
        email=email,
        code_hash=hash_code(email, code),
        expires_at=now + timedelta(minutes=10),
    )
    db.add(record)
    await db.commit()
    if smtp_is_configured():
        try:
            await send_code(email, code)
        except Exception as exc:
            await db.delete(record)
            await db.commit()
            raise HTTPException(status_code=502, detail="We couldn't send that email. Please try again.") from exc
    response = {"ok": True, "message": "Your sign-in code is ready."}
    if settings.is_development and not smtp_is_configured():
        response["dev_code"] = code
    return response


@app.post("/api/auth/verify-code")
async def verify_code(payload: CodeVerify, db: AsyncSession = Depends(get_db)):
    email = normalize_email(str(payload.email))
    now = datetime.now(UTC)
    record = await db.scalar(
        select(AuthCode)
        .where(
            AuthCode.email == email,
            AuthCode.consumed_at.is_(None),
            AuthCode.expires_at > now,
            AuthCode.attempts < 5,
        )
        .order_by(desc(AuthCode.created_at))
        .with_for_update()
        .limit(1)
    )
    if record is None:
        raise HTTPException(status_code=400, detail="That code has expired. Request a new one.")
    if not secrets.compare_digest(record.code_hash, hash_code(email, payload.code)):
        record.attempts += 1
        await db.commit()
        raise HTTPException(status_code=400, detail="That code doesn't match. Please try again.")
    record.consumed_at = now
    user = await db.scalar(select(User).where(User.email == email).with_for_update())
    if user is None:
        user = User(email=email)
        db.add(user)
        await db.flush()
    await db.commit()
    return {
        "access_token": create_access_token(str(user.id)),
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "memory_enabled": user.memory_enabled,
            "language": user.language,
        },
    }


@app.get("/api/auth/me")
async def me(user: User = Depends(current_user)):
    return {
        "id": str(user.id),
        "email": user.email,
        "memory_enabled": user.memory_enabled,
        "language": user.language,
    }


@app.patch("/api/me/preferences")
async def update_preferences(
    payload: PreferencesPatch,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.memory_enabled is not None:
        user.memory_enabled = payload.memory_enabled
    if payload.language is not None:
        user.language = payload.language
    await db.commit()
    return {"memory_enabled": user.memory_enabled, "language": user.language}


@app.delete("/api/auth/me", status_code=204)
async def delete_account(
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    conversations = await db.scalars(select(Conversation).where(Conversation.user_id == user.id))
    for conversation in conversations:
        try:
            session = await request.app.state.session_service.get_session(
                app_name=settings.app_name,
                user_id=str(user.id),
                session_id=str(conversation.id),
            )
            if session is not None:
                await request.app.state.session_service.delete_session(
                    app_name=settings.app_name,
                    user_id=str(user.id),
                    session_id=str(conversation.id),
                )
        except Exception as exc:
            raise HTTPException(status_code=503, detail="We couldn't safely remove every conversation. Try again.") from exc
    codes = await db.scalars(select(AuthCode).where(AuthCode.email == user.email))
    for code in codes:
        await db.delete(code)
    await db.delete(user)
    await db.commit()
    return Response(status_code=204)


@app.get("/api/conversations")
async def list_conversations(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    result = await db.scalars(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
    )
    return [
        {
            "id": str(item.id),
            "title": item.title,
            "private": item.private,
            "updated_at": item.updated_at,
        }
        for item in result
    ]


@app.post("/api/conversations")
async def create_conversation(
    payload: ConversationCreate,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    conversation = Conversation(user_id=user.id, private=payload.private)
    db.add(conversation)
    await db.flush()
    await db.commit()
    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "private": conversation.private,
        "updated_at": conversation.updated_at,
    }


async def owned_conversation(
    conversation_id: UUID,
    user: User,
    db: AsyncSession,
) -> Conversation:
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="That conversation is no longer here.")
    return conversation


@app.delete("/api/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: UUID,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    conversation = await owned_conversation(conversation_id, user, db)
    try:
        await request.app.state.session_service.delete_session(
            app_name=settings.app_name,
            user_id=str(user.id),
            session_id=str(conversation.id),
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="We couldn't safely remove that conversation. Try again.") from exc
    await db.delete(conversation)
    await db.commit()
    return Response(status_code=204)


@app.get("/api/memories")
async def list_memories(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    result = await db.scalars(
        select(Memory)
        .where(Memory.user_id == user.id, Memory.status != "rejected")
        .order_by(Memory.created_at.desc())
    )
    return [
        {
            "id": str(item.id),
            "kind": item.kind,
            "content": item.content,
            "proposed_content": item.proposed_content,
            "source_excerpt": item.source_excerpt,
            "status": item.status,
        }
        for item in result
    ]


@app.patch("/api/memories/{memory_id}")
async def update_memory(
    memory_id: UUID,
    payload: MemoryPatch,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await db.scalar(select(Memory).where(Memory.id == memory_id, Memory.user_id == user.id))
    if item is None:
        raise HTTPException(status_code=404, detail="That saved note is no longer here.")
    if payload.action == "reject":
        await db.delete(item)
        await db.commit()
        return {"ok": True}
    if payload.content is not None and not payload.content.strip():
        raise HTTPException(status_code=422, detail="A saved detail cannot be blank.")
    if payload.content is not None:
        if item.status == "pending_update":
            item.proposed_content = payload.content.strip()
        else:
            item.content = payload.content.strip()
            item.embedding = await embed(item.content)
            item.embedding_model = settings.openai_embedding_model if item.embedding else None
    if payload.action == "confirm":
        if item.status == "pending_update" and item.proposed_content:
            item.content = item.proposed_content
            item.embedding = await embed(item.content)
            item.embedding_model = settings.openai_embedding_model if item.embedding else None
            item.proposed_content = None
        item.status = "confirmed"
    await db.commit()
    return {"ok": True, "status": item.status, "content": item.content}


@app.delete("/api/memories/{memory_id}", status_code=204)
async def delete_memory(
    memory_id: UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await db.scalar(select(Memory).where(Memory.id == memory_id, Memory.user_id == user.id))
    if item is None:
        raise HTTPException(status_code=404, detail="That saved note is no longer here.")
    await db.delete(item)
    await db.commit()
    return Response(status_code=204)


@app.get("/api/voice/status")
async def voice_status(user: User = Depends(current_user)):
    return {"available": bool(settings.eleven_labs_api_key)}


@app.post("/api/voice/transcribe")
async def transcribe_voice(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
):
    try:
        return {"text": await transcribe(file)}
    finally:
        await file.close()


@app.post("/api/voice/speak", response_class=Response, responses={
    200: {"description": "Spoken reply, held in memory only", "content": {
        "audio/mpeg": {"schema": {"type": "string", "format": "binary"}},
    }},
})
async def speak_reply(payload: SpeechRequest, user: User = Depends(current_user)):
    audio = await speak(payload.text)
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})
