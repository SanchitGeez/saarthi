from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    phone: Mapped[str] = mapped_column(String(13), unique=True)
    name: Mapped[str | None] = mapped_column(String(100))
    gender: Mapped[str | None] = mapped_column(String(100))
    age: Mapped[int | None]
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    session_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    session_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        CheckConstraint("age IS NULL OR age BETWEEN 1 AND 120"),
        CheckConstraint("phone ~ '^\\+91[6-9][0-9]{9}$'"),
        CheckConstraint(
            "onboarded_at IS NULL OR (name IS NOT NULL AND gender IS NOT NULL AND age IS NOT NULL)"
        ),
    )


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(80), default="New conversation")
    status: Mapped[str] = mapped_column(String(16), default="active")
    knowledge_status: Mapped[str] = mapped_column(String(16), default="not_started")
    generation_status: Mapped[str] = mapped_column(String(16), default="idle")
    generation_message_id: Mapped[UUID | None]
    claim_token: Mapped[UUID | None]
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extraction_input: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("status IN ('active', 'ended')"),
        CheckConstraint("knowledge_status IN ('not_started', 'processing', 'completed', 'failed')"),
        CheckConstraint("generation_status IN ('idle', 'processing', 'failed')"),
        CheckConstraint("(status = 'ended') = (ended_at IS NOT NULL)"),
        Index(
            "one_active_conversation",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("conversation_history", "user_id", "updated_at", "id"),
    )


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    reply_to_id: Mapped[UUID | None] = mapped_column(ForeignKey("messages.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')"),
        CheckConstraint("length(content) BETWEEN 1 AND 8000"),
        Index("message_order", "conversation_id", "created_at", "id"),
        Index(
            "one_greeting",
            "conversation_id",
            unique=True,
            postgresql_where=text("role = 'assistant' AND reply_to_id IS NULL"),
        ),
    )


class Knowledge(Base):
    __tablename__ = "user_knowledge"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    type: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="active")
    content: Mapped[str] = mapped_column(Text)
    source_conversation_id: Mapped[UUID | None] = mapped_column(ForeignKey("conversations.id"))
    manual_revision: Mapped[int] = mapped_column(Integer, default=0)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        CheckConstraint("type IN ('factual', 'behavioural', 'contextual', 'summary')"),
        CheckConstraint("status IN ('active', 'inactive')"),
        CheckConstraint("length(content) BETWEEN 1 AND 2000"),
        Index("knowledge_owner", "user_id"),
        Index(
            "one_conversation_summary",
            "source_conversation_id",
            unique=True,
            postgresql_where=text("type = 'summary' AND source_conversation_id IS NOT NULL"),
        ),
    )
