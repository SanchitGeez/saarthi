# Saarthi v2

A text companion inspired by the Bhagavad Gita. One FastAPI app, PostgreSQL,
independent Google ADK agents (`saarthi` for conversation, `doval` for extraction),
and a plain same-origin browser testing client. The Expo `mobile/` starter is unchanged.

This is a **development/test prototype**. OTP accepts any nonempty value, sends no
SMS, and does not verify phone ownership. Do not expose it publicly or use real
private data. `ENVIRONMENT=production` refuses startup until mock auth is replaced.

## Run locally

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), and Docker Compose (or a
local PostgreSQL 16 database).

```sh
docker compose up -d db
cd backend
cp .env.example .env
# Put your Groq key in backend/.env: GROQ_API_KEY=...
uv sync --locked
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

Without `GROQ_API_KEY`, login/onboarding and knowledge controls work; generation
returns a recoverable error. There are no fake model replies in the application.
Set `AGENT_MODEL` to change the default `groq/openai/gpt-oss-20b` for both agents.
The key stays on the server. Live language, Gita and extraction quality still need
evaluation with your key; schema transport is tested locally through ADK/LiteLLM.

## Verify

```sh
cd backend
uv sync --locked
# Uses a temporary schema; never truncates application tables outside that schema.
TEST_DATABASE_URL=postgresql+psycopg://saarthi:saarthi@localhost:5432/saarthi uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run alembic check
node --check ../client/app.js
# Optional real-provider smoke test, with GROQ_API_KEY configured:
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

## Mobile and archive

The existing Expo starter remains independent: `cd mobile && npm ci && npm start`;
`npm run typecheck` checks it. Voice is deferred. [archive/](archive/) contains
superseded plans; the old full app is preserved on
`backup/full-app-2026-10-17`.
