from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import Conversation, Knowledge, Message, User


def lock_user(db: Session, user_id):
    return db.scalar(select(User).where(User.id == user_id).with_for_update())


def conversation(db, user_id, conversation_id):
    return db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id
        )
    )


def active_conversation(db, user_id):
    return db.scalar(
        select(Conversation).where(Conversation.user_id == user_id, Conversation.status == "active")
    )


def messages(db, conversation_id):
    return list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at, Message.id)
        )
    )


def knowledge(db, user_id, include_deleted=False):
    query = select(Knowledge).where(Knowledge.user_id == user_id)
    if not include_deleted:
        query = query.where(Knowledge.deleted_at.is_(None))
    return list(db.scalars(query.order_by(Knowledge.created_at, Knowledge.id)))


def knowledge_record(db, user_id, record_id):
    return db.scalar(
        select(Knowledge).where(
            Knowledge.id == record_id, Knowledge.user_id == user_id, Knowledge.deleted_at.is_(None)
        )
    )


def login_user(db, phone):
    from sqlalchemy.dialects.postgresql import insert

    db.execute(insert(User).values(phone=phone).on_conflict_do_nothing(index_elements=["phone"]))
    return db.scalar(select(User).where(User.phone == phone).with_for_update())


def session_user(db, token_hash):
    from core.models import now

    return db.scalar(
        select(User).where(User.session_token_hash == token_hash, User.session_expires_at > now())
    )


def conversation_id_taken(db, conversation_id):
    return db.scalar(select(Conversation.id).where(Conversation.id == conversation_id)) is not None


def message_by_id(db, message_id):
    # Global lookup is only for retry-ID collision detection, never authorization.
    return db.get(Message, message_id)


def assistant_reply(db, conversation_id, message_id):
    return db.scalar(
        select(Message).where(
            Message.conversation_id == conversation_id,
            Message.role == "assistant",
            Message.reply_to_id == message_id,
        )
    )


def latest_summary(db, user_id):
    return db.scalar(
        select(Knowledge)
        .join(Conversation, Knowledge.source_conversation_id == Conversation.id)
        .where(
            Knowledge.user_id == user_id,
            Conversation.user_id == user_id,
            Knowledge.type == "summary",
            Knowledge.status == "active",
            Knowledge.deleted_at.is_(None),
        )
        .order_by(Conversation.ended_at.desc(), Conversation.id.desc())
        .limit(1)
    )


def conversation_page(db, user_id, limit, cursor):
    from sqlalchemy import tuple_

    query = select(Conversation).where(Conversation.user_id == user_id)
    if cursor:
        query = query.where(tuple_(Conversation.updated_at, Conversation.id) < tuple_(*cursor))
    return list(
        db.scalars(
            query.order_by(Conversation.updated_at.desc(), Conversation.id.desc()).limit(limit + 1)
        )
    )


def knowledge_page(db, user_id, limit, after):
    query = select(Knowledge).where(Knowledge.user_id == user_id, Knowledge.deleted_at.is_(None))
    if after:
        query = query.where(Knowledge.id > after)
    return list(db.scalars(query.order_by(Knowledge.id).limit(limit + 1)))
