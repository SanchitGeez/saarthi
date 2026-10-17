> Historical snapshot, superseded by [the current document](../architecture-lean-candidate.md). Provider choices and test counts below describe the earlier implementation.

# Current implementation note (2026-10-03)

The lean candidate below is a historical design record, not a description of every current implementation detail. Read [the current agent handoff](../agent-handoff.md) for the implemented architecture. The product polish pass changes these decisions:

- `chat_turns` is now the canonical delivery record, with stable IDs, saved processing/completed/failed states, and idempotent retries. ADK prompts are rebuilt from successful exchanges. Legacy ADK session events are imported when a conversation is opened.
- Memory tools stage at most one explicitly supported lasting detail per successful turn and automatically save it when account memory is enabled. Edit/delete and the master switch remain user controls; individual approval is removed.
- A small curated Gita collection provides original shlok text, our Hindi/English renderings, and source links. The persona and app are both named Saarthi. One configurable Gemini fallback handles temporary model unavailability or rate limits.

Current agent tools are `find_memories`, `remember_detail`, `update_remembered_detail`, and `get_gita_verse`. Memory is prefetched before generation; eligible writes are staged and committed automatically with a successful turn. New turns use an in-memory ADK session reconstructed from at most 24 successful exchanges, with a maximum of five model calls. The ADK database session service remains for legacy import/deletion. There are five app-owned tables, including `chat_turns`. Old references below to pending-only memory, four tables, database events as canonical history, and deferred retries have been superseded.

There is no background jobs table or worker. The request performs the generation; a 120-second processing lease makes interrupted requests visibly retryable. See `backend/app/turns.py` for the implemented contract.

---

# Lean v1 architecture — implementation

Updated: 2026-10-03. This is the first implementation shape, kept small so it can change as usage teaches us more.

## Verdict

The app → FastAPI → Google ADK → PostgreSQL and personal memory shape is implemented. PostgreSQL with pgvector keeps each memory's readable text and vector together. A separate vector service is not needed for the initial version. Supabase remains a possible hosting/auth option around PostgreSQL, not a competing database model.

The earlier 17-table proposal separated many operational concerns before the first product workflow existed. Preserve its failure-handling ideas, but do not treat its tables as mandatory v1 scope.

## User interface

React Native/Expo provides Android and iOS clients. Recent conversations sit beside chat on wide screens and open as a drawer on phones.

## Connections

```text
React Native app
  └─ email one-time code / bearer token → FastAPI
       ├─ ADK Runner → one Saarthi agent → Gemini API
       │    ├─ ADK DatabaseSessionService → PostgreSQL events
       │    └─ owner-scoped memory tools → PostgreSQL + pgvector
       └─ transient voice upload / reply → ElevenLabs
```

FastAPI, ADK, Expo, PostgreSQL, Gemini, and ElevenLabs are used by the code. Chat responses use the configured Gemini model. Optional memory embeddings use an OpenAI-compatible endpoint when configured. Email delivery uses configured SMTP; local development returns a code in the API response. Supabase hosting/auth and Murf remain replaceable options and are not required to run this version.

## ADK and application boundaries

- FastAPI owns authentication, account ownership, request validation, and bounded synchronous chat turns. Production rate limiting and spend quotas remain launch work.
- ADK Runner manages the agent's model/tool loop and session events. It does not automatically implement our personal-memory policy or authorization.
- One saarthi agent handles guidance. Do not start with a multi-agent team.
- Tools: `find_memories(query)`, `propose_memory(content, kind, evidence)`, and `propose_memory_update(memory_id, content, evidence)`.
- Tools receive trusted owner/context from the backend; the model cannot supply an arbitrary user ID or SQL.
- Memory retrieval is currently tool-driven; prefetching can be evaluated later if the agent misses useful context.
- Writes validate the user's consent and exact supporting excerpt, then keep notes or corrections pending. Confirmation and forgetting remain explicit user actions.
- Private mode disables cross-conversation memory reads and writes. Normal session context still applies.
- Bound request runtime (90 seconds), tool result sizes, provider timeouts, and conversation length (100 ADK events). The current ADK Runner does not enforce a separate model-call count.

ADK has a PostgreSQL-backed `DatabaseSessionService`. Its runtime stores session/event/state tables. Those events are the canonical dialogue history; the app maps user messages and Saarthi's final replies to chat bubbles and does not mirror every message into a custom table. Conversation metadata uses the conversation UUID as the ADK session ID. Tool-call events are not ordinary chat bubbles.

The ADK session service creates or updates its own tables when the first session operation runs. The API uses final-response events for display and deletes the ADK session when a conversation is deleted. Chat runs synchronously with a request timeout and bounded conversation length. A durable job queue and stronger retry/idempotency reconciliation are deferred until background work or production traffic requires them. Do not expose ADK's development server to the mobile client; FastAPI is the authenticated boundary.

## Minimal data model

Four application-owned tables plus ADK-managed runtime tables:

| Logical group | Storage | Minimum fields |
| --- | --- | --- |
| User profile | users | auth UUID, email, preferred language, memory consent, creation time |
| Conversation metadata | conversations | ID, owner, ADK session ID, title, private mode, timestamps |
| Messages/history | ADK session events | Persisted user/assistant content and runtime events, scoped by authenticated owner/session |
| Personal memory | memories | ID, owner, kind, text, source conversation and exact user excerpt, pending/confirmed state, optional embedding, timestamps |
| Email sign-in | auth_codes | normalized email, code hash, attempts, expiry, one-time use time |

ADK maintains additional internal session/event/state tables. The four app-owned tables are not the full physical schema.

Represent concerns, preferences, and actions as memory kinds instead of separate concern/commitment tables. Store a short exact excerpt from the user's latest message and its conversation ID on each memory. Add separate evidence, usage, or summary tables only if real product workflows need them.

This consolidation reduces tables; it does not remove ownership checks, consent, or deletion work. A memory tool can only propose a note when its cited excerpt exactly occurs in the current user message. New notes and changes stay pending until the person accepts them. Private conversations and disabled memory block both retrieval and writes. Deleting a conversation cascades to memories sourced from it; forgetting a memory deletes its text and vector.

All v1 work is request/response, so there is no background worker or jobs table. Add a maintained PostgreSQL job queue once a task needs to continue after the HTTP request or survive a process restart.

## Vector memory

An embedding is a numeric representation of a piece of text. Embed individual memory statements, not one vector for the entire person. A memories row holds readable text, metadata and a vector column together. user_id is the ownership filter, not the embedding itself.

Example record:

```text
owner: user_123
kind: concern
text: "Considering a job change but worried about disappointing parents."
status: confirmed
source_excerpt: "..."
embedding: [0.08, -0.21, ...]
embedding_model: selected-model/version
```

Retrieval: embed the current question, search only eligible memories owned by the authenticated person, rank by semantic distance, and combine with explicit preferences/recent active concerns. An example query is:

```sql
SELECT id, content, kind, source_excerpt
FROM memories
WHERE user_id = $1
  AND status = 'confirmed'
  AND embedding_model = $3
ORDER BY embedding <=> $2::vector
LIMIT 5;
```

This assumes pgvector is installed and `$2` comes from the same embedding model/dimension as stored vectors. Values are bound parameters; the backend supplies `$1`. Similarity is not proof of truth or relevance. Tentative patterns require separate eligibility and confirmation behavior.

For a small per-user memory set, begin with an owner index and exact filtered similarity search. Approximate vector indexes may reduce recall under filters; add and evaluate them only as needed. Do not omit ownership filters to improve retrieval.

Changing memory text invalidates its old embedding. Compute/update a new embedding against the expected revision so a stale job cannot overwrite a correction. Deletion removes both text and vector. A future embedding-model switch requires re-embedding or segregating model versions; incompatible vectors must not be mixed.

## Candidate packages

- Mobile uses Expo/React Native with expo-audio, secure session storage and a small typed API client.
- Python API: fastapi, uvicorn, pydantic, pydantic-settings.
- Agent runtime: google-adk and the selected model integration.
- Database: SQLAlchemy asyncio, asyncpg, and pgvector's SQLAlchemy integration.
- Backend token verification: signed PyJWT bearer tokens. Email codes use SMTP outside development; replace the small first-party auth module with Supabase Auth if hosting/auth operations justify it.
- Chat uses ADK's native Gemini integration and `GOOGLE_API_KEY`; speech uses ElevenLabs REST endpoints through `httpx`; optional embeddings use the OpenAI SDK, with owner-scoped text search as a fallback.
- No Node backend, Vercel AI SDK, Drizzle or pg-boss if the Python candidate is adopted.

## Sources checked

- ADK PostgreSQL session example: https://github.com/google/adk-python/blob/main/contributing/samples/context_management/postgres_session_service/README.md
- ADK sessions: https://adk.dev/sessions/session/
- ADK memory services: https://adk.dev/sessions/memory/
- ADK function tools: https://adk.dev/tools-custom/function-tools/
- PostgreSQL vector extension: https://github.com/pgvector/pgvector
- FastAPI background tasks: https://fastapi.tiangolo.com/tutorial/background-tasks/

Audio is transient: no audio database table or object storage exists. ElevenLabs receives voice-note uploads for transcription and returns generated speech; playback audio is held temporarily in the phone cache and removed after playback.

## Implemented files

- API: `backend/app` (configuration, auth, database models, ADK tools, voice provider, routes)
- Mobile: `mobile/App.tsx` and `mobile/src` (sign-in, chat, conversation drawer, memory/privacy settings, visual components)
- Local PostgreSQL with pgvector: `docker-compose.yml`
- Product/design source: `PRODUCT.md` and `DESIGN.md`

The app uses its own local development database by default. Do not point it at the neighboring MindLap database.
