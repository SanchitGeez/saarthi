# Saarthi v2 — working specification

Status: discovery in progress. Updated: 2026-10-17.

This document separates confirmed requirements from proposals. Open proposals are
not implementation instructions. The current request is to define the app, not
build it yet. New decisions supersede archived designs.

## Confirmed scope

- Text chatbot with a minimal backend and a plain black-and-white testing UI.
- Two backend modules: `core` and `agents`. These are code boundaries; separate
  services have not been requested.
- `core` owns authentication, users, onboarding, conversations and persistence.
- `agents` owns Google ADK integration, prompts, chat generation and knowledge
  extraction. The conversational agent is named `saarthi`; the extraction agent
  is named `doval`. These are two independent invocations, not a delegation tree.
- Mobile number + mocked OTP login. For this prototype, any entered OTP is
  accepted. This does not establish ownership of the phone number.
- Onboarding requires name, gender and age. Gender supports a self-described value
  or prefer not to say. India-only phone numbers, stored in normalized `+91` form.
- UI: message input, recent-conversation sidebar, sign out and End conversation.
  Reopening the app resumes the active conversation. On a new conversation,
  Saarthi proactively greets the user and asks a contextual question when relevant.
  Automatically start on entry after onboarding/login when there is no active
  chat. After End, show New conversation rather than immediately starting another.
  This supersedes the original first-user-message creation flow.
- Each chat request includes the system prompt, that user's active factual,
  behavioural and contextual knowledge, the latest active conversation summary,
  and the current conversation transcript.
- Ending a conversation invokes a separate extraction agent with the complete
  transcript and previous user knowledge. It returns structured JSON; validated
  changes are persisted to user knowledge.
- Voice is deferred. No animation or visual styling beyond a usable monochrome UI.
- Keep implementation minimal under Ponytail: no speculative infrastructure.

## Product direction to refine

Saarthi should be emotionally perceptive, knowledgeable about the Bhagavad Gita,
and able to help users reflect on a problem and its root causes. Guidance should
combine useful questions with practical perspectives. Occasional follow-up hooks
should make the conversation interesting.

Confirmed: Saarthi presents itself as a wise, spiritually grounded AI guide.
"Psychiatrist", "godly" and "enlightened" describe its tone, not qualifications
or an identity it claims. It must not claim to be a clinician or divine authority.
Follow-up hooks are useful questions, without pressure to keep chatting.

Confirmed: use model knowledge for Gita-inspired guidance; no scripture corpus,
retrieval tool or verified-source claim in this iteration. Exact quotations and
verse references can be wrong. Prompt Saarthi to acknowledge uncertainty, avoid
inventing citations and distinguish its interpretation from scripture quotations.
Support English, Hindi and Hinglish, automatically following the user's language.
No language selector initially. Return complete replies rather than streaming.
Confirmed conversation style: understand the situation first, then candidly
challenge assumptions. Keep replies short by default and usually ask one useful
question at a time; expand when the user requests an explanation.

Confirmed Gita presence: scripture should not be forced into every reply, but
Gita-inspired reflection must become apparent after a few substantive exchanges.
Do not remain a generic supportive chatbot indefinitely. Connect the user's
actual situation to a relevant idea, such as attachment to outcomes, acting with
care, equanimity or duty. A conceptual reference or clearly labelled paraphrase
is enough; an exact Sanskrit quotation or verse number is not required.
Initial prompt target: introduce a relevant Gita connection around the second
to fourth substantive user turn, sooner if directly asked. This is a proposed
prompt guideline, not a rigid turn counter or a requirement to interrupt urgent
support with scripture. Do not repeatedly force the same lesson.
Detailed guardrail wording remains to be finalized.

## Confirmed architecture

Keep the existing Python/FastAPI backend as one application and one database.
Use PostgreSQL with four application tables. `core` calls `agents` through Python
functions; no internal HTTP, message broker or separate agent server.

`core` loads owner-scoped data → `agents` runs Saarthi through ADK → `core` saves
the reply → client displays it.

End request → freeze the transcript and mark ended → extraction agent returns
validated changes → `core` commits knowledge changes and marks extraction complete.
The End request waits for extraction. If it fails, preserve the ended conversation
and show Retry. No background worker for this version. Confirmed: a failed
extraction does not prevent starting a new conversation. Show a warning that the
previous chat has not updated knowledge. A subsequent successful retry affects
future invocations; it does not rewrite replies already generated.
Detailed crash recovery remains to be specified.

The application database should be the canonical transcript store. ADK session
handling must not create a conflicting second history. Exact session lifecycle
still needs selection and an implementation check.

Confirmed provider: Groq API, with the API key supplied later. Keep `GROQ_API_KEY`
server-side; select a model through configuration rather than hardcoding it in
prompts. Proposed integration: ADK `LiteLlm` connector → Groq, using a
`groq/<model-id>` model name. No custom provider abstraction or separate proxy.
Use the lower-cost `openai/gpt-oss-20b` for both agents initially, configured as
`groq/openai/gpt-oss-20b` through LiteLLM. User requested a cheap initial model;
this is the selected starting default, upgradeable through configuration.
Groq lists $0.075 input / $0.30 output per million tokens and strict structured
output support, checked 2026-10-17. Sources: [models and pricing](https://console.groq.com/docs/models)
and [structured outputs](https://console.groq.com/docs/structured-outputs).
No claim of evaluated Hindi/Hinglish, Gita or extraction quality yet.

Documentation checked 2026-10-17: [ADK LiteLLM connector](https://adk.dev/agents/models/litellm/),
[LiteLLM Groq provider](https://docs.litellm.ai/docs/providers/groq), and
[Groq structured outputs](https://console.groq.com/docs/structured-outputs).
ADK documents the connector, LiteLLM documents Groq routing, and Groq documents
model-dependent schema support. This is a documented integration path, not a
live verification. Test Doval's schema through the pinned ADK/LiteLLM versions
with the selected model before treating structured output as working. Do not
silently substitute a tool-based output mechanism: Doval must not call tools.

## Code quality and minimal low-level design

Confirmed: maintain clear API, business logic and data-access boundaries without
building a framework around them. Proposed starting structure:

```text
backend/
  main.py              # app setup and router registration
  config.py            # validated settings; secrets from environment
  database.py          # engine and request-scoped database session
  core/
    routes.py          # HTTP input/output, authentication dependency, status codes
    schemas.py         # request/response validation
    service.py         # auth, onboarding, chat lifecycle and knowledge workflows
    data.py            # owner-scoped database queries and writes
    models.py          # application tables and constraints
  agents/
    saarthi.py         # chat agent and persona prompt
    doval.py           # extraction agent, prompt and output schema
    runner.py          # shared ADK invocation setup, only where actually shared
client/                # browser dev/test UI
```

- Route functions validate HTTP input, call a business function and map expected
  failures to HTTP responses. No SQL or prompt construction in routes.
- Business functions enforce ownership, onboarding and lifecycle rules; assemble
  context; invoke agents; validate their output; and own transaction boundaries.
- Data functions contain queries and persistence operations. They accept a
  database session and do not independently commit a business transaction.
- Agents accept explicit input data and return text or validated structured data.
  They do not import database models, mutate records or know about HTTP.
- Use ordinary functions and concrete dependencies. No base repository classes,
  generic CRUD services, dependency-injection container, event bus or speculative
  domain framework. Split files only when their actual size warrants it.
- Keep database transactions short; do not hold a transaction or row lock while
  waiting for Groq. Use persisted claims/status for race-safe processing.
- Use database constraints for uniqueness and valid states, and validate untrusted
  values with schemas. Structured JSON does not replace ownership validation.
- Use resource-oriented routes, consistent request/response shapes, bounded list
  queries, appropriate status codes and stable error codes. Never trust client IDs
  as authorization. Define retry semantics for state-changing chat operations.
- Keep targeted tests for ownership, lifecycle/retries, knowledge application,
  manual-edit conflicts and mock-auth boundaries. Add one live agent smoke check
  when credentials arrive; no test suite mirroring trivial accessors.

The file structure is a proposal, not a requirement to create every file before
it has useful code. ORM and migration tooling still need selection.

## Proposed database — fields are provisional

| Table | Minimum useful fields | Decisions still open |
| --- | --- | --- |
| `users` | `id`, unique normalized `phone`, `name`, `gender`, `age`, `onboarded_at`, `session_token_hash`, `session_expires_at`, `created_at` | Session lifetime |
| `conversations` | `id`, `user_id`, `title`, `status`, `created_at`, `updated_at`, `ended_at`, `knowledge_status` | Extraction crash recovery |
| `messages` | `id`, `conversation_id`, `role`, `content`, `created_at` | Retry identity, pending/failed generations and concurrent sends |
| `user_knowledge` | `id`, `user_id`, `type`, `status`, `content`, `source_conversation_id`, `created_at`, `updated_at` | Manual-edit conflict enforcement |

### Concrete proposal for review

All IDs are UUIDs; timestamps are timezone-aware UTC. All fields are required
unless marked nullable. These types and constraints are proposed, not locked.

```text
users
  id                 uuid primary key
  phone              text unique              # normalized international number
  name               text nullable            # absent before onboarding
  gender             text nullable
  age                integer nullable
  onboarded_at       timestamptz nullable
  session_token_hash text nullable            # hash only; one active login
  session_expires_at timestamptz nullable
  created_at         timestamptz

conversations
  id                 uuid primary key
  user_id            uuid references users
  title              text                     # New conversation, then first user message excerpt
  status             text                     # active | ended
  knowledge_status   text                     # not_started | processing | completed | failed
  created_at         timestamptz
  updated_at         timestamptz
  ended_at           timestamptz nullable

messages
  id                 uuid primary key
  conversation_id    uuid references conversations
  role               text                     # user | assistant
  content            text
  created_at         timestamptz

user_knowledge
  id                 uuid primary key
  user_id            uuid references users
  type               text                     # factual | behavioural | contextual | summary
  status             text                     # active | inactive
  content            text                     # one detail, or a short bullet summary
  source_conversation_id uuid nullable references conversations
  created_at         timestamptz
  updated_at         timestamptz
```

Confirmed: one active conversation per user; closing the app or signing out does
not end it. Only End closes it. Enforce this with a unique partial index
on `conversations(user_id)` where status is `active`. Ended chats stay read-only.
Index conversations by owner and update time, messages by conversation and
creation time, and knowledge by owner.

Proposed simplification following review: omit `sequence`; order messages by
server-generated `created_at`, then `id` for deterministic timestamp ties.
The ID tie-breaker does not establish causal order. Do not insert a whole transcript
with one shared timestamp. Define serialized send behavior before implementation;
revisit explicit ordering if concurrent/batched messages become necessary.

Confirmed knowledge categories:

| Type | Meaning | Example |
| --- | --- | --- |
| `factual` | Relatively lasting user-reported information | Works as a software engineer |
| `behavioural` | Reported or agent-inferred habits and patterns | Seems to avoid difficult conversations |
| `contextual` | Current circumstances that may become stale | Preparing for an interview next week |
| `summary` | A few points describing a completed conversation | Concern discussed, perspectives explored, chosen next step and unresolved question |

Confirmed: knowledge is editable in the dev/test UI, including add/edit/delete.
These controls are for developers/test users, not a promised end-user feature.
Doval may infer behavioural patterns without asking the user to confirm them.
Agent inferences are interpretations, not clinical diagnoses or verified facts;
the prompt should preserve that distinction in their wording.
The extractor automatically proposes additions, corrections and removals for the
backend to apply. The backend validates ownership and output before committing
the changes together. Exact change-set JSON remains to be defined.

Proposed provenance: `source_conversation_id`, rather than one source message,
because a detail or summary can depend on several exchanges. It identifies the
conversation where a record was first derived or last substantively updated; it
is not a complete evidence history. It is null for manually added records. A
conversation reference provides traceability, not automatic proof of truth.
Do not turn an assistant's own statements into evidence that the user said them.
Confirmed: manual edits win over extraction already in flight. A deleted detail
may be learned again only if the user brings it up in a later conversation.
Exact conflict detection and enforcement remain to be designed; hard deletion
alone cannot enforce this on a retry of the same source conversation.

Confirmed summary handling: one `summary` record per ended conversation. Proposed
constraint: enforce this
by a unique partial index on `source_conversation_id` for type `summary` with a
non-null source. This prevents duplicate summaries on extraction retry.
Inject all active factual, behavioural and contextual records plus only the
latest active conversation summary. Order summaries by their source conversation's
`ended_at`, not the summary's edit time. Older summaries remain stored and visible
in the test UI; a late retry must not replace a newer conversation's summary.

Confirmed: use `status` instead of `expires_at`. Values are `active` and
`inactive`; only active records enter agent context. There is no automatic expiry,
TTL or scheduler in this version. Future expiry/invalidation rules are deferred.
Doval may propose marking outdated/contradicted knowledge inactive in its JSON;
only the backend application function performs the database changes.

Generation status/retry fields and an extraction recovery timestamp may be added
after failure behavior is decided. This is not yet a complete delivery schema.

Every conversation and knowledge query must be scoped to the authenticated user.
Message access must verify ownership through its conversation. User identity for
agent context comes from authentication, never a caller-supplied user ID.

No vector database is needed for the requested all-knowledge context injection.
Knowledge and transcript limits need an explicit behavior when they no longer fit.
The confirmed single-session design stores session fields on users; it requires
no separate auth table in this iteration.

## Authentication and onboarding

Confirmed: accept India-only mobile numbers; normalize to `+91` plus the national
number before lookup. Validate the input shape; do not claim that formatting
proves a number exists. The mocked OTP accepts any entered value and performs
no SMS delivery or real verification. Keep mock auth restricted to development
and test; refuse startup in a real deployment configuration until replaced.

Confirmed: one active login per account. On login generate a cryptographically
random opaque session token, store only its hash and expiry on `users`, and set
the raw token in an HTTP-only cookie. A subsequent login replaces that session.
Logout clears the server-side session and the browser cookie. Never return the
hash or token in user payloads or log them.

Proposed defaults: seven-day session; SameSite=Lax cookie; Secure on HTTPS, with
an explicit localhost HTTP development exception. Serve the client and API from
the same origin. Validate Origin for mutating browser requests. No JWT refresh
flow, password, SMS integration or multi-device session management.

Before onboarding, only authentication and profile endpoints are available.
Save required name, gender and age together and set `onboarded_at` only after
validating them. Database nullability permits the pre-onboarding state; it does
not make these fields optional in the completed onboarding request.
Confirmed: no adult-only eligibility filter in this iteration. Age is required
and validated as an age value, but being under 18 does not block onboarding.
Proposed input limits: trimmed name 1–100 characters, gender 1–100 characters,
and integer age 1–120. These are input-shape limits, not an adult eligibility rule.

## Proposed API surface — contracts follow decisions

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/auth/otp/request` | Validate/normalize phone; acknowledge mocked delivery |
| POST | `/auth/otp/verify` | Accept entered mock OTP; create/find user and establish login |
| POST | `/auth/logout` | Invalidate the current session and clear its cookie |
| GET | `/me` | Current user and onboarding state |
| PATCH | `/me` | Save validated onboarding fields |
| GET | `/conversations` | Recent conversations with status; identify active one |
| GET | `/conversations/{id}` | Owned conversation and ordered transcript |
| POST | `/conversations` | Create a conversation and generate Saarthi's opening greeting |
| POST | `/conversations/{id}/messages` | Append a user message and generate Saarthi's response |
| POST | `/conversations/{id}/end` | End the chat and trigger knowledge extraction |
| GET | `/knowledge` | Dev/test: list the authenticated user's knowledge |
| POST | `/knowledge` | Dev/test: manually add a knowledge record |
| PATCH | `/knowledge/{id}` | Dev/test: edit an owned knowledge record |
| DELETE | `/knowledge/{id}` | Dev/test: delete an owned knowledge record |

Keep the existing `/health`. Replies are complete JSON responses, not streams.
Conversation creation/greeting must be retry-safe.
Knowledge CRUD is confirmed for dev/test use only and must still enforce ownership.
Disable these routes outside the test environment; no admin permission system is
requested. Status transitions and field validation still need definition.

### Concrete request/response proposals for review

Return resource objects directly, without a generic `success/data` wrapper.
Authentication endpoints never expose session token fields.

| Endpoint | Request body | Success response |
| --- | --- | --- |
| `POST /auth/otp/request` | `{"phone":"9876543210"}` | `200 {"phone":"+919876543210","mock":true}` |
| `POST /auth/otp/verify` | `{"phone":"9876543210","otp":"123456"}` | `200 {"user":{...},"onboarding_required":true}` plus cookie |
| `POST /auth/logout` | None | `204`, cookie and server session cleared |
| `GET /me` | None | `200` public user fields and `onboarding_required` |
| `PATCH /me` | `{"name":"Aman","gender":"male","age":27}` | `200` updated public user fields |
| `POST /conversations` | `{"id":"<client-generated UUID>"}` | `201 {"conversation":{...},"message":{...}}` with greeting |
| `POST /conversations/{id}/messages` | `{"id":"<client-generated user-message UUID>","content":"I feel stuck at work."}` | `201 {"user_message":{...},"assistant_message":{...}}` |
| `POST /conversations/{id}/end` | None | `200 {"conversation":{...}}` including `knowledge_status` |
| `POST /knowledge` | `{"type":"contextual","content":"Considering a job change.","status":"active"}` | `201` created record; source is null |
| `PATCH /knowledge/{id}` | Subset of `type`, `content`, `status` | `200` updated record |
| `DELETE /knowledge/{id}` | None | `204`; removed from subsequent context |

Client-generated UUIDs are retry identities, never authorization. Reusing a
conversation/message ID after a lost HTTP response must return the saved result,
not generate a second greeting/reply. Reusing a message ID with different content
returns `409`. Persisted retry fields and handling of an in-flight replay still
need to be finalized with generation failure recovery.

Proposed list contract: `GET /conversations?limit=30&before=<cursor>` returns
`{"items":[...],"active_conversation_id":null,"next_cursor":null}`. Active ID is
looked up independently of the history page. `GET /conversations/{id}` returns
`{"conversation":{...},"messages":[...]}` in chronological order, sufficient for
the bounded prototype transcript. Knowledge listing includes active and inactive
records for dev inspection. Final list limits/context bounds remain to be set.

Proposed errors: `{"error":{"code":"conversation_ended","message":"This conversation has ended."}}`.
Use `401` for a missing/expired session, `403` for incomplete onboarding, `404`
for missing or foreign-owned records, `409` for lifecycle/concurrency conflicts,
`422` for invalid input, and `502`/`504` for provider failure/timeout. Adapt FastAPI
validation errors to the same envelope; never leak prompts, secrets or SQL errors.
An extraction failure can occur after End was committed: return the error code
`knowledge_extraction_failed` with the owned conversation ID and persisted
`knowledge_status=failed`, so the client presents End as complete and offers
Retry extraction. Repeating End retries extraction without reopening the chat;
after success it returns the stored completed state without invoking Doval again.

## Agent contracts to define

### Saarthi

Inputs: system prompt, onboarding profile where useful, active non-summary knowledge
and the latest active summary,
ordered current transcript and the new user message exactly once.
For the opening invocation there is no user message. Saarthi greets proactively;
when useful, it asks a question grounded in the prior summary or current context.
Do not greet again when merely resuming an active chat.

Output: assistant text. No scripture retrieval tools in this iteration.
Treat stored knowledge and transcript as user data, never as system instructions.
No direct auth access or arbitrary database mutation tools.

### Doval — knowledge extractor

Inputs: ended conversation transcript and previous user knowledge.

Output: a schema-validated JSON change set covering typed knowledge additions,
updates, deactivations and the completed conversation's summary. Doval has no
tools and never edits the database. A core business function validates the entire
change set and applies it atomically. Reject malformed output without partial
database writes. Normal agent-driven forgetting uses inactive status, not hard
deletion; explicit dev/test deletion remains a separate operation.

Proposed output shape for review:

```json
{
  "additions": [
    {"type": "contextual", "content": "Considering a job change."}
  ],
  "updates": [],
  "deactivate_ids": [],
  "summary": [
    "Discussed dissatisfaction with current work.",
    "Plans to compare two possible roles before deciding."
  ]
}
```

Each update contains an existing `id`, `type`, `content` and `status`. Addition
types exclude `summary`; the backend creates/updates that record from `summary`.
The backend assigns new IDs, owner, source conversation and timestamps. Doval
cannot supply an owner or arbitrary source conversation. Reject unknown/foreign
record IDs, duplicate/conflicting operations and invalid types/statuses. Handle
manual-edit conflicts before committing; this policy still needs a concrete
revision/locking design. Finalize field limits and empty-summary behavior later.

Confirmed: synchronous extraction during End, with retry on failure.
Open: detailed retry recovery, deduplication, contradictions, implementation of
manual-edit/deletion precedence, and which personal details are appropriate to retain.
Repeated End requests must not apply the same changes twice.

## Testing client

Confirmed: create a separate `client/` browser testing UI when implementation
begins. Leave the existing Expo `mobile/` starter alone. Include knowledge
inspection and add/edit/delete controls.
No UI folder or application code has been created as part of this spec draft.

Confirmed emphasis: extremely minimal and lightweight. White background, black
text, ordinary form controls and basic CSS only for alignment, spacing, readable
text and layout. No accent colours, animations, gradients, illustrations, decorative
effects, component library or frontend state framework. Proposed implementation:
plain HTML, CSS and browser JavaScript served by FastAPI, keeping auth same-origin.
Use safe text rendering for messages; do not inject model output as raw HTML.

Flow: phone → OTP → incomplete onboarding → chat. Login of an onboarded user goes
directly to their active chat. If there is none, automatically start a conversation
with Saarthi's proactive greeting. After End, show New conversation; do not
automatically start another in the same visit.
Show loading and recoverable errors for login, sending and ending. Ended chats
remain accessible in history and cannot resume. While End runs, show that Saarthi
is saving what it learned; offer Retry if extraction fails.

## Decision queue

1. Detailed guardrail wording (persona, candid tone and recurring Gita presence are confirmed).
2. API payloads, greeting retries and failure recovery.
3. Extraction retry recovery, contradictions and implementation of manual-edit/deletion precedence.
4. ORM/migrations and final database constraints.
5. ADK session handling and context limits; live Groq verification after key arrives.
6. Final validation limits and session lifetime (no adult-only eligibility filter).
7. Final prompts and targeted acceptance checks.

## Acceptance checks to finalize

- New user can sign in through mocked phone OTP, onboard, send and receive a reply.
- Returning user resumes the active chat; ended chats appear in history.
- A user cannot read or modify another user's messages or knowledge.
- Saarthi receives only the authenticated user's knowledge and current transcript.
- Ending produces validated knowledge updates; retry does not duplicate them.
- Generation/extraction failures preserve messages and have a clear retry path.
- Mock authentication cannot accidentally be used as real phone verification.

These are proposed checks for implementation. No implementation or behavioral
verification has been performed for v2.
