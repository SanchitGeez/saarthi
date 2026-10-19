# Saarthi v2 implementation decisions

The implementation request supersedes the working specification's earlier
“define, not build” status. Confirmed requirements and the spec's concrete
proposals are implemented with the following decisions for the open items.

## Boundaries and storage

One FastAPI process/application and PostgreSQL database. `core/routes.py` handles
HTTP; `core/service.py` owns business transactions and context; `core/data.py`
contains owner-scoped reads; `core/models.py` defines constraints. Agents accept
plain payloads, never import persistence or HTTP, and have no tools. SQLAlchemy
and Alembic provide persistence and versioned migrations. Exactly four application
tables (plus Alembic's migration-version table).

All UUIDs and UTC timestamps are generated server-side except conversation/user
message retry IDs. PostgreSQL enforces one active conversation per user, one
opening greeting per conversation, one assistant reply per user message, and one
summary per source conversation. Messages order by creation time and UUID;
serialized sends and independently assigned timestamps establish normal turn order.
No bulk transcript writes or concurrent sends are supported.

## Retry and crash recovery

Create accepts `{id}`; send accepts `{id, content}`. Retry with the same IDs returns
the saved greeting/reply without another invocation. A changed message body or ID
collision is 409. A failed generation retains its user message and blocks another
send until that message is retried (End can still close it). Greeting failure
leaves an active empty conversation; retry Create with its existing ID.

Each generation/extraction claims the conversation with a random token and a
persisted lease of `AGENT_TIMEOUT_SECONDS + 15` seconds. The provider timeout is
60 seconds by default. Requests during a live claim return 409
`operation_in_progress`; another send while a different message is pending returns
`message_pending`. After a crashed worker's lease expires, the same operation can
be retried. A replaced claim token prevents a late worker from saving its output.
No background recovery worker: the user explicitly retries. Transient
`processing` state after a crash is visible with `claim_expires_at`.

Short transactions lock the user row to serialize mutations for that account.
No database session, transaction or row lock stays open during an agent call.
End freezes transcript and prior non-summary knowledge in `extraction_input`, marks
ended/processing, commits, then invokes Doval. Successful changes and completion
commit atomically. Failure persists ended/failed; repeating End retries the same
frozen input. Completed End is a no-op. A new conversation can start while an older
ended chat is processing or failed. Retries affect subsequent invocations only.

## Knowledge application and manual conflicts

Doval returns required `additions`, `updates`, `deactivate_ids` and 1–5 `summary`
bullets. Additions exclude summary. Updates require ID/type/content/status. Each
array is limited to 30 operations, details to 2,000 characters, and summary bullets
to 300 characters. Extra fields, unknown/foreign/summary IDs, duplicate or
conflicting ID operations and invalid schemas reject the entire change set.
Identical additions are deduplicated by normalized case/whitespace. Agent-driven
forgetting sets inactive; no tool mutates the database.

Manual edits increment `manual_revision`. Deletes retain an internal tombstone
(`deleted_at`); they disappear from the API and future agent context. Frozen
extraction snapshots include revisions. Updates/deactivations are skipped when a
record has since been edited or deleted. To prevent a paraphrased re-addition,
**all additions from that extraction are conservatively skipped** if any snapshot
record was manually changed/deleted, a new manual record was added after End, or a
record was deleted during this conversation. Other unaffected updates and the
summary still apply. This may skip unrelated useful additions; that is deliberate
in favor of manual precedence. A later conversation, started after deletion, can
learn a detail again from new user statements. Tombstones are internal conflict
metadata, not a promise of irreversible data erasure.

Source references identify the conversation that last substantively updated a
record, not a full evidence history. One summary is created per ended conversation;
only the latest active sourced summary enters chat, ordered by conversation End
time, including after late retries or manual summary edits. All other active
factual/behavioural/contextual records enter chat. Inactive records remain visible
and are supplied to Doval for possible correction. Extracted records cannot change
to/from summary through manual edits. Manually added summaries have no source and
are inspection-only. Old summaries remain stored and editable.

## Context, provider and guardrails

Each invocation creates an isolated in-memory ADK session, runs once with the full
explicit JSON payload, then discards the session. PostgreSQL is canonical. New user
text occurs exactly once in that transcript. No ADK database session/history,
retrieval, agent delegation, streaming or external tools.

The lockfile pins ADK/LiteLLM. A mocked completion through the real ADK Runner and
LiteLLM adapter verifies native `response_format=json_schema`, `strict=true`, no
tools/functions and no carried-over assistant history. The opt-in live test checks
both agents through OpenRouter; it is not replaced with a tool-based output fallback.
Actual OpenRouter acceptance and quality remain unverified until credentials are supplied.

Transcript content is limited to **64,000 UTF-8 bytes**; accepting a new message
reserves 32,000 bytes for the maximum 8,000-character reply. Input messages allow
4,000 characters. Active chat context and the complete non-summary extraction
knowledge snapshot each have a **12,000 UTF-8 byte JSON** budget. The backend
rejects over-limit writes/changes atomically with a recoverable error instead of
silently truncating user evidence. End the chat for transcript capacity; shorten or
remove knowledge for knowledge capacity. These conservative bounds fit the chosen
model, including multilingual text; reassess if configuring a smaller-context model.

Prompts specify an honest AI identity, emotional understanding then candid
challenge, short replies and one useful question, automatic English/Hindi/Hinglish,
contextual greetings, Gita concepts after a few substantive turns without rigid
counting, uncertain citations, no invented authority, no diagnoses, and urgent
human support when safety is at risk. Doval distinguishes user statements from
assistant suggestions and tentative behavioural interpretations, and avoids
retaining unnecessary sensitive identifiers/details. These are prompt safeguards,
not an assertion of clinically evaluated behavior.

## HTTP/client contracts

Resource objects use the spec's proposed endpoints and shapes. Errors use
`{"error":{"code":"...","message":"..."}}`; validation exposes field names,
never raw values or exception details. Failed End returns
`knowledge_extraction_failed` with conversation ID and persisted `failed` status.
Missing/foreign resources are 404, unauthenticated is 401, incomplete onboarding
403, conflicts 409, validation 422, provider failure/timeout 502/504.

Conversation history supports `limit=1..100` (default 30) and a
`before=<ISO timestamp>|<UUID>` cursor. Active conversation is independently found.
Knowledge inspection supports `limit=1..200` (default 100), `after=<UUID>` and
`next_cursor`; tombstones are excluded. All resources are scoped to authenticated
identity. Profile/auth are available before onboarding; conversation/knowledge
routes require it. Knowledge controls exist only in the development/test app;
production configuration refuses the entire mock-auth application.

The same-origin static client uses ordinary controls and safe `textContent`, never
model HTML. It covers phone/OTP/onboarding, auto-create/resume on entry, read-only
ended history, explicit New conversation after End, pending-message retry,
extraction warnings/retry, sign out and paged knowledge CRUD. No frontend framework
or build step. Existing `mobile/` files are untouched.
