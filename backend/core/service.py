import hashlib
import json
import secrets
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from agents import doval, saarthi
from agents.runner import AgentFailure
from core import data
from core.errors import Problem
from core.models import Conversation, Knowledge, Message, now
from core.schemas import ConversationOut, KnowledgeOut, MessageOut, UserOut

TRANSCRIPT_LIMIT = 64000
KNOWLEDGE_LIMIT = 12000


def out(schema, row):
    return schema.model_validate(row).model_dump(mode="json")


def public_user(user):
    return {**out(UserOut, user), "onboarding_required": user.onboarded_at is None}


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def login(factory, settings, phone):
    token = secrets.token_urlsafe(32)
    with factory.begin() as db:
        user = data.login_user(db, phone)
        user.session_token_hash = digest(token)
        user.session_expires_at = now() + timedelta(days=settings.session_days)
        result = public_user(user)
    return token, result


def authenticate(factory, token):
    if not token or len(token) > 200:
        raise Problem(401, "unauthenticated", "Please sign in.")
    with factory() as db:
        user = data.session_user(db, digest(token))
        if not user:
            raise Problem(401, "unauthenticated", "Your session has expired. Please sign in.")
        return user


def logout(factory, user_id, token):
    with factory.begin() as db:
        user = data.lock_user(db, user_id)
        if user.session_token_hash == digest(token):
            user.session_token_hash = None
            user.session_expires_at = None


def profile(factory, user_id, values):
    with factory.begin() as db:
        user = data.lock_user(db, user_id)
        for key, value in values.items():
            setattr(user, key, value)
        user.onboarded_at = user.onboarded_at or now()
        db.flush()
        return public_user(user)


def owned(db, user_id, conversation_id):
    conv = data.conversation(db, user_id, conversation_id)
    if not conv:
        raise Problem(404, "not_found", "Conversation not found.")
    return conv


def context(db, user):
    records = data.knowledge(db, user.id)
    active = [r for r in records if r.status == "active"]
    details = [
        {"id": str(r.id), "type": r.type, "content": r.content, "status": r.status}
        for r in active
        if r.type != "summary"
    ]
    summary = data.latest_summary(db, user.id)
    payload = {
        "profile": {"name": user.name, "gender": user.gender, "age": user.age},
        "knowledge": details,
        "latest_summary": summary.content if summary else None,
    }
    bound_knowledge(payload)
    return payload


def bound_knowledge(payload):
    if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > KNOWLEDGE_LIMIT:
        raise Problem(
            409,
            "knowledge_limit",
            "Knowledge is too large for this prototype. Shorten or remove records and retry.",
        )


def claim(conv, settings):
    if conv.claim_expires_at and conv.claim_expires_at > now():
        raise Problem(
            409,
            "operation_in_progress",
            "An operation is still running. Retry shortly.",
            retry_after_seconds=3,
        )
    conv.claim_token = uuid4()
    conv.claim_expires_at = now() + timedelta(seconds=settings.agent_timeout_seconds + 15)
    return conv.claim_token


def clear_claim(conv):
    conv.claim_token = None
    conv.claim_expires_at = None


def generation_result(db, conv, message_id):
    assistant = data.assistant_reply(db, conv.id, message_id)
    if not assistant:
        return None
    if message_id is None:
        return {"conversation": out(ConversationOut, conv), "message": out(MessageOut, assistant)}
    return {
        "user_message": out(MessageOut, data.message_by_id(db, message_id)),
        "assistant_message": out(MessageOut, assistant),
    }


async def generate(factory, settings, user_id, conversation_id, message=None):
    message_id = message.id if message else None
    with factory.begin() as db:
        user = data.lock_user(db, user_id)
        conv = data.conversation(db, user_id, conversation_id)
        if not conv:
            if message:
                raise Problem(404, "not_found", "Conversation not found.")
            if data.conversation_id_taken(db, conversation_id):
                raise Problem(404, "not_found", "Conversation not found.")
            active = data.active_conversation(db, user_id)
            if active:
                raise Problem(
                    409,
                    "active_conversation_exists",
                    "Resume the active conversation.",
                    conversation_id=str(active.id),
                )
            conv = Conversation(id=conversation_id, user_id=user_id)
            db.add(conv)
            db.flush()
        existing = data.message_by_id(db, message_id) if message_id else None
        if existing and (existing.conversation_id != conv.id or existing.role != "user"):
            raise Problem(409, "id_conflict", "This message ID has already been used.")
        if existing and existing.content != message.content:
            raise Problem(409, "id_conflict", "Retry this message with its original content.")
        saved = generation_result(db, conv, message_id)
        if saved:
            return saved
        if conv.status != "active":
            raise Problem(409, "conversation_ended", "This conversation has ended.")
        if message and not generation_result(db, conv, None):
            raise Problem(409, "greeting_required", "Retry the opening greeting first.")
        if conv.generation_status != "idle" and conv.generation_message_id != message_id:
            raise Problem(
                409, "message_pending", "Retry the pending message before sending another."
            )
        token = claim(conv, settings)
        payload = context(db, user)
        transcript = data.messages(db, conv.id)
        if message and not existing:
            if (
                sum(len(m.content.encode("utf-8")) for m in transcript)
                + len(message.content.encode("utf-8"))
                + 8000 * 4
                > TRANSCRIPT_LIMIT
            ):
                raise Problem(
                    409,
                    "transcript_limit",
                    "This chat is full. End it and start a new conversation.",
                )
            existing = Message(
                id=message.id, conversation_id=conv.id, role="user", content=message.content
            )
            db.add(existing)
            db.flush()
            transcript.append(existing)
            if len(transcript) == 2:
                conv.title = message.content[:80]
        payload.update(
            opening=message is None,
            transcript=[{"role": m.role, "content": m.content} for m in transcript],
        )
        conv.generation_status = "processing"
        conv.generation_message_id = message_id
        conv.updated_at = now()
    try:
        reply = await saarthi.reply(settings, payload)
        if not isinstance(reply, str) or not reply.strip() or len(reply) > 8000:
            raise AgentFailure()
    except Exception as exc:
        with factory.begin() as db:
            data.lock_user(db, user_id)
            conv = owned(db, user_id, conversation_id)
            if conv.claim_token == token:
                conv.generation_status = "failed"
                clear_claim(conv)
        raise Problem(
            504 if isinstance(exc, AgentFailure) and exc.timeout else 502,
            "generation_failed",
            "Reply failed. Retry the same message.",
            conversation_id=str(conversation_id),
        ) from None
    with factory.begin() as db:
        data.lock_user(db, user_id)
        conv = owned(db, user_id, conversation_id)
        if conv.claim_token != token:
            raise Problem(
                409,
                "operation_superseded",
                "This attempt expired. Refresh to see the current state.",
            )
        db.add(
            Message(
                conversation_id=conv.id,
                role="assistant",
                content=reply.strip(),
                reply_to_id=message_id,
            )
        )
        conv.generation_status = "idle"
        clear_claim(conv)
        conv.updated_at = now()
        db.flush()
        return generation_result(db, conv, message_id)


def get_conversation(factory, user_id, conversation_id):
    with factory() as db:
        conv = owned(db, user_id, conversation_id)
        return {
            "conversation": out(ConversationOut, conv),
            "messages": [out(MessageOut, m) for m in data.messages(db, conv.id)],
        }


def list_conversations(factory, user_id, limit, before):
    with factory() as db:
        cursor = None
        if before:
            try:
                stamp, identifier = before.split("|")
                timestamp = datetime.fromisoformat(stamp)
                if timestamp.tzinfo is None:
                    raise ValueError()
                cursor = timestamp, UUID(identifier)
            except ValueError:
                raise Problem(422, "invalid_cursor", "Invalid history cursor.") from None
        rows = data.conversation_page(db, user_id, limit, cursor)
        active = data.active_conversation(db, user_id)
        last = rows[limit - 1] if len(rows) > limit else None
        return {
            "items": [out(ConversationOut, c) for c in rows[:limit]],
            "active_conversation_id": str(active.id) if active else None,
            "next_cursor": f"{last.updated_at.isoformat()}|{last.id}" if last else None,
        }


def snapshot_knowledge(db, user_id):
    records = data.knowledge(db, user_id)
    payload = [
        {
            "id": str(r.id),
            "type": r.type,
            "content": r.content,
            "status": r.status,
            "manual_revision": r.manual_revision,
        }
        for r in records
        if r.type != "summary"
    ]
    bound_knowledge(payload)
    return payload


def normal(value):
    return " ".join(value.casefold().split())


def apply_changes(db, user_id, conv, changes):
    snapshot = {r["id"]: r for r in conv.extraction_input["previous_knowledge"]}
    ids = [str(r.id) for r in changes.updates] + [str(i) for i in changes.deactivate_ids]
    if len(ids) != len(set(ids)) or any(i not in snapshot for i in ids):
        raise ValueError("Unknown or conflicting knowledge operations")
    records = data.knowledge(db, user_id, include_deleted=True)
    current = {str(r.id): r for r in records}
    # Validate the whole set before applying anything, including ownership on tombstones.
    if any(i not in current for i in ids):
        raise ValueError("Invalid knowledge reference")
    protected_content = set()
    suppress_additions = False
    for key, previous in snapshot.items():
        row = current.get(key)
        if row is None or row.deleted_at or row.manual_revision != previous["manual_revision"]:
            protected_content.add(normal(previous["content"]))
            suppress_additions = True
    for row in records:
        if row.deleted_at and row.deleted_at >= conv.created_at:
            protected_content.add(normal(row.content))
            suppress_additions = True
        if row.source_conversation_id is None and row.created_at >= conv.ended_at:
            suppress_additions = True
    for update in changes.updates:
        row = current[str(update.id)]
        if row.deleted_at or row.manual_revision != snapshot[str(update.id)]["manual_revision"]:
            continue
        row.type, row.content, row.status = update.type, update.content, update.status
        row.source_conversation_id, row.updated_at = conv.id, now()
    for identifier in changes.deactivate_ids:
        row = current[str(identifier)]
        if row.deleted_at or row.manual_revision != snapshot[str(identifier)]["manual_revision"]:
            continue
        row.status, row.source_conversation_id, row.updated_at = "inactive", conv.id, now()
    existing_content = {normal(r.content) for r in records if not r.deleted_at}
    for addition in changes.additions:
        content = normal(addition.content)
        # Conservative conflict policy also blocks paraphrased re-additions after manual changes.
        if suppress_additions or content in protected_content or content in existing_content:
            continue
        db.add(
            Knowledge(
                user_id=user_id,
                type=addition.type,
                content=addition.content,
                source_conversation_id=conv.id,
            )
        )
        existing_content.add(content)
    db.add(
        Knowledge(
            user_id=user_id,
            type="summary",
            content="\n".join("- " + line for line in changes.summary),
            source_conversation_id=conv.id,
        )
    )
    db.flush()
    bound_knowledge(
        [
            {
                "type": r.type,
                "content": r.content,
                "id": str(r.id),
                "status": r.status,
                "manual_revision": r.manual_revision,
            }
            for r in data.knowledge(db, user_id)
            if r.type != "summary"
        ]
    )
    context(db, data.lock_user(db, user_id))


async def end_conversation(factory, settings, user_id, conversation_id):
    with factory.begin() as db:
        data.lock_user(db, user_id)
        conv = owned(db, user_id, conversation_id)
        if conv.knowledge_status == "completed":
            return {"conversation": out(ConversationOut, conv)}
        token = claim(conv, settings)
        if conv.status == "active":
            # Snapshot before committing End; an over-limit request leaves the chat active.
            previous = snapshot_knowledge(db, user_id)
            conv.extraction_input = {
                "transcript": [
                    {"role": m.role, "content": m.content} for m in data.messages(db, conv.id)
                ],
                "previous_knowledge": previous,
            }
            conv.status, conv.ended_at, conv.updated_at = "ended", now(), now()
            conv.generation_status = "idle"
        conv.knowledge_status = "processing"
        payload = conv.extraction_input
    try:
        changes = doval.ChangeSet.model_validate(await doval.extract(settings, payload))
        with factory.begin() as db:
            data.lock_user(db, user_id)
            conv = owned(db, user_id, conversation_id)
            if conv.claim_token != token:
                raise Problem(
                    409,
                    "operation_superseded",
                    "This extraction attempt expired. Refresh and retry.",
                )
            apply_changes(db, user_id, conv, changes)
            conv.knowledge_status = "completed"
            clear_claim(conv)
            db.flush()
            result = {"conversation": out(ConversationOut, conv)}
        return result
    except Exception as exc:
        if isinstance(exc, Problem) and exc.code == "operation_superseded":
            raise
        with factory.begin() as db:
            data.lock_user(db, user_id)
            conv = owned(db, user_id, conversation_id)
            if conv.claim_token == token:
                conv.knowledge_status = "failed"
                clear_claim(conv)
        raise Problem(
            504 if isinstance(exc, AgentFailure) and exc.timeout else 502,
            "knowledge_extraction_failed",
            "Conversation ended, but knowledge was not updated. Retry extraction.",
            conversation_id=str(conversation_id),
            knowledge_status="failed",
        ) from None


def list_knowledge(factory, user_id, limit=100, after=None):
    with factory() as db:
        rows = data.knowledge_page(db, user_id, limit, after)
        return {
            "items": [out(KnowledgeOut, r) for r in rows[:limit]],
            "next_cursor": str(rows[limit - 1].id) if len(rows) > limit else None,
        }


def edit_knowledge(factory, user_id, values, record_id=None, delete=False):
    with factory.begin() as db:
        data.lock_user(db, user_id)
        row = data.knowledge_record(db, user_id, record_id) if record_id else None
        if record_id and not row:
            raise Problem(404, "not_found", "Knowledge record not found.")
        if (
            row
            and row.source_conversation_id
            and (
                (row.type == "summary" and values.get("type", "summary") != "summary")
                or (row.type != "summary" and values.get("type") == "summary")
            )
        ):
            raise Problem(
                409, "summary_type_fixed", "An extracted record cannot change to or from summary."
            )
        if not row:
            row = Knowledge(user_id=user_id, **values)
            db.add(row)
        else:
            for key, value in values.items():
                setattr(row, key, value)
            row.manual_revision += 1
            row.updated_at = now()
        if delete:
            row.deleted_at = now()
        db.flush()
        snapshot_knowledge(db, user_id)
        context(db, data.lock_user(db, user_id))
        return out(KnowledgeOut, row)
