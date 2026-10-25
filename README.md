# Saarthi v2

A text and optional browser voice companion inspired by the Bhagavad Gita. One FastAPI app, PostgreSQL,
independent Google ADK agents (`saarthi` for conversation, `doval` for extraction),
and a plain same-origin browser testing client. The Expo `mobile/` starter is unchanged.

This is a **development/test prototype**. OTP accepts any nonempty value, sends no
SMS, and does not verify phone ownership. Do not expose it publicly or use real
private data. `ENVIRONMENT=production` refuses startup until mock auth is replaced.

## Run locally

The backend environment is pinned to Python 3.12 by `backend/.python-version`.
Install it with [uv](https://docs.astral.sh/uv/) and Docker Compose (or local PostgreSQL 16).

```sh
docker compose up -d db
cd backend
cp .env.example .env
# Put your OpenRouter key in backend/.env: OPENROUTER_API_KEY=...
uv sync --locked --extra voice
uv run alembic upgrade head
uv run uvicorn main:app --reload
```

Open <http://localhost:8000>. Keep this exact host/port or update `APP_ORIGIN`;
mutating requests require an exact matching `Origin` header. `/health` remains
available. The client uses HTTP-only, SameSite=Lax cookies; HTTPS origins require
Secure cookies. HTTP is permitted only for localhost/testserver. Login replaces
the account's previous seven-day session. Logout preserves the active chat.

Use a test Indian mobile number, enter any OTP, and provide name, self-described
gender (or “Prefer not to say”), and age (1–120; minors are allowed). Entry resumes
the active conversation or creates one with a proactive greeting. End freezes the
chat and waits for extraction. A failed extraction offers Retry and does not block
New conversation. Knowledge inspection supports add/edit/delete and inactive
records. All routes enforce ownership and onboarding.

Without `OPENROUTER_API_KEY`, login/onboarding and knowledge controls work; generation
returns a recoverable error. There are no fake model replies in the application.
Change `SAARTHI_MODEL` near the top of [backend/config.py](backend/config.py) to
`"gemma"` for free development or `"luna"` for GPT-6 Luna at low effort, then restart.
Luna is the current selection and is billed at OpenRouter's listed rate.
Leave `AGENT_MODEL`, `AGENT_PROVIDER`, and `AGENT_REASONING_EFFORT` unset to use
the switch; explicit environment settings override it.
The key stays on the server. Live language, Gita and extraction quality still need
evaluation with your key; schema transport is tested locally through ADK/LiteLLM.

## Optional browser voice

The [`backend/voice`](backend/voice/README.md) module connects Deepgram STT,
Pipecat, the existing Saarthi agent, and Cartesia TTS (Rohan) over browser WebRTC. Its packages
are included in the Python 3.12 environment above; configure the voice keys in
`.env`. Rohan is the default voice; Murf remains available in the codebase. Voice is disabled by default.
See the module README for setup, recovery behavior and required microphone tests,
and [the maintained architecture](docs/voice-architecture.md) for design decisions.

## Verify

```sh
cd backend
uv sync --locked --extra voice
# Uses a temporary schema; never truncates application tables outside that schema.
TEST_DATABASE_URL=postgresql+psycopg://saarthi:saarthi@localhost:5432/saarthi uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run alembic check
node --check ../client/app.js
# Optional real-provider smoke test, with OPENROUTER_API_KEY configured:
RUN_LIVE_AGENT_TEST=1 uv run pytest -q -m live
```

Tests cover auth, ownership, lifecycle, retries, leases, malformed extraction,
atomic changes, knowledge context, manual conflicts and the native structured
output adapter. CI runs the PostgreSQL suite and migration checks. The opt-in live
test is skipped without credentials. Run the API with `--host 127.0.0.1` for local
use. For non-browser API clients, also send `Origin: http://localhost:8000` and retain
the session cookie.

See [working spec](docs/saarthi-v2-spec.md) and
[implementation decisions](docs/saarthi-v2-implementation.md) for contracts and limits.

For full-conversation experiments using the real Saarthi agent, adaptive DeepEval
users, local human/Codex review and prompt comparison, see
[the separate evals module](backend/evals/README.md). Its dependencies are optional
(`uv sync --locked --extra voice --group evals`); the web application does not import it.

## Mobile and archive

The existing Expo starter remains independent: `cd mobile && npm ci && npm start`;
`npm run typecheck` checks it. Voice is deferred. [archive/](archive/) contains
superseded plans; the old full app is preserved on
`backup/full-app-2026-10-17`.
