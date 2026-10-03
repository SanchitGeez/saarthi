from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    language: Mapped[str] = mapped_column(String(12), default="auto")
    memory_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    memories: Mapped[list[Memory]] = relationship(back_populates="user", cascade="all, delete-orphan", passive_deletes=True)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(100), default="A new conversation")
    private: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True
    )
    user: Mapped[User] = relationship(back_populates="conversations")


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    source_conversation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(24), default="context")
    content: Mapped[str] = mapped_column(Text)
    source_excerpt: Mapped[str] = mapped_column(Text)
    proposed_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    user: Mapped[User] = relationship(back_populates="memories")


class AuthCode(Base):
    __tablename__ = "auth_codes"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatTurn(Base):
    """One durable user message and its reply. Retries reuse the same primary key."""

    __tablename__ = "chat_turns"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="processing", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scripture_refs: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class VoiceSession(Base):
    __tablename__ = "voice_sessions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    room_name: Mapped[str] = mapped_column(String(100), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="connecting")
    worker_claimed: Mapped[bool] = mapped_column(Boolean, default=False)
    greeting_claimed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VoiceMessage(Base):
    __tablename__ = "voice_messages"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("voice_sessions.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    interrupted: Mapped[bool] = mapped_column(Boolean, default=False)
    memory_saved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
