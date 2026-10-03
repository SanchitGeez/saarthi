> Current product behavior: memories now save automatically, and chat delivery uses persisted turn states and idempotent retries. For the updated runnable tests and verification record, see [Product polish testing](product-polish-testing.md). The earlier record below documents the initial implementation.

# API end-to-end testing runbook

This runbook exercises Saarthi against the real local PostgreSQL database and the configured Gemini and ElevenLabs services. It does not replace a provider with a mock. Use a disposable account and synthetic text; the API's development OTP is intended only for local development.

## Before testing

1. In the repository root, make sure `.env` exists and has a valid `GOOGLE_API_KEY`. `GEMINI_MODEL` defaults to `gemini-3.8-flash`. ElevenLabs checks require `ELEVEN_LABS_API_KEY` (or the supported `ELEVEN_LABS` alias). Memory embeddings are optional; without a working OpenAI-compatible embedding configuration, memory lookup uses an owner-filtered text search fallback.
2. Start PostgreSQL with `docker compose up -d postgres`.
3. From `backend`, run `uv sync`, then start the API with `uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`.
4. Check `http://localhost:8000/api/health` and open `http://localhost:8000/docs` if you want to inspect the live OpenAPI schema.

The shell examples use `curl` and `jq`.

Do not use shell tracing (`set -x`) while handling tokens. Do not paste API keys, OTPs, access tokens, or real personal stories into a shared log. These commands use an `example.com` address and do not send email when the API is in development with SMTP unset.

## Sign in with a disposable development account

The development request response includes `dev_code` when SMTP is not configured. Verify it to receive a bearer token:

```bash
set -euo pipefail
export SAARTHI_API="http://localhost:8000/api"
export SAARTHI_EMAIL="saarthi-e2e-$(date +%s)@example.com"

curl -fsS "$SAARTHI_API/health" | jq .

export SAARTHI_OTP="$(curl -fsS -X POST "$SAARTHI_API/auth/request-code" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$SAARTHI_EMAIL\"}" | jq -r '.dev_code')"

export SAARTHI_TOKEN="$(curl -fsS -X POST "$SAARTHI_API/auth/verify-code" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$SAARTHI_EMAIL\",\"code\":\"$SAARTHI_OTP\"}" \
  | jq -r '.access_token')"

curl -fsS "$SAARTHI_API/auth/me" \
  -H "Authorization: Bearer $SAARTHI_TOKEN" | jq .
```

The OTP is single-use. Replaying the same verification request should return HTTP 400. A wrong code also returns 400 and consumes one of the limited attempts. Real SMTP delivery is a separate production configuration test; this runbook's development OTP flow does not test email delivery.

## Conversation and Gemini turn

Create a normal conversation, send a short synthetic message, and read its history:

```bash
export SAARTHI_CONVERSATION_ID="$(curl -fsS -X POST "$SAARTHI_API/conversations" \
  -H "Authorization: Bearer $SAARTHI_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"private":false}' | jq -r '.id')"

curl -fsS -X PATCH "$SAARTHI_API/me/preferences" \
  -H "Authorization: Bearer $SAARTHI_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"memory_enabled":true,"language":"en"}' | jq .

curl -fsS -X POST "$SAARTHI_API/conversations/$SAARTHI_CONVERSATION_ID/turns" \
  -H "Authorization: Bearer $SAARTHI_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"text":"I am testing the app locally. Please reply in one short sentence."}' | jq .

curl -fsS "$SAARTHI_API/conversations" \
  -H "Authorization: Bearer $SAARTHI_TOKEN" | jq .

curl -fsS "$SAARTHI_API/conversations/$SAARTHI_CONVERSATION_ID/messages" \
  -H "Authorization: Bearer $SAARTHI_TOKEN" | jq .
```

Also create a private conversation with `{"private":true}` and send one turn. Confirm its response has `private: true`; private conversations must not use or create personal memories. The `/turns` call makes a live Gemini request, so a successful auth or conversation-creation response alone does not prove chat is working.

## Memory proposal and approval

Use a low-sensitivity, explicit preference that the agent is allowed to remember:

```bash
curl -fsS -X POST "$SAARTHI_API/conversations/$SAARTHI_CONVERSATION_ID/turns" \
  -H "Authorization: Bearer $SAARTHI_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"text":"Please remember this stable preference: I prefer practical advice with one clear next step. I want this saved for future conversations."}' | jq .

curl -fsS "$SAARTHI_API/memories" \
  -H "Authorization: Bearer $SAARTHI_TOKEN" | jq .
```

If the agent created a pending proposal, take its `id` from the response above and test the user-controlled lifecycle:

```bash
export SAARTHI_MEMORY_ID="<pending-memory-id>"

curl -fsS -X PATCH "$SAARTHI_API/memories/$SAARTHI_MEMORY_ID" \
  -H "Authorization: Bearer $SAARTHI_TOKEN" \
  -H 'Content-Type: application/json' -d '{"action":"confirm"}' | jq .

curl -fsS -X PATCH "$SAARTHI_API/memories/$SAARTHI_MEMORY_ID" \
  -H "Authorization: Bearer $SAARTHI_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"content":"I prefer practical advice with one clear next step."}' | jq .

curl -i -X DELETE "$SAARTHI_API/memories/$SAARTHI_MEMORY_ID" \
  -H "Authorization: Bearer $SAARTHI_TOKEN"
```

To test rejection instead, use `{"action":"reject"}` on a pending proposal and verify it disappears from `GET /memories`. Memory proposal creation is controlled by the live model; if it does not propose a memory, do not treat the rest of this flow as passed. A separate cross-conversation recall test should confirm a saved, confirmed preference is available in a newly created conversation.

## Real voice-provider check without writing audio to disk

This requests a short ElevenLabs reply, keeps the returned MP3 bytes in process memory, and sends those bytes directly to transcription. Run it from `backend` while the API is running. Export `SAARTHI_TOKEN` in the same shell used above.

```bash
uv run python - <<'PY'
import asyncio
import os

import httpx


async def main():
    api = os.environ.get("SAARTHI_API", "http://localhost:8000/api")
    headers = {"Authorization": f"Bearer {os.environ['SAARTHI_TOKEN']}"}
    async with httpx.AsyncClient(timeout=90) as client:
        audio = await client.post(
            f"{api}/voice/speak",
            headers=headers,
            json={"text": "This is a short voice service test."},
        )
        print("TTS:", audio.status_code, audio.headers.get("content-type"), len(audio.content), "bytes")
        audio.raise_for_status()

        transcript = await client.post(
            f"{api}/voice/transcribe",
            headers=headers,
            files={"file": ("voice-check.mp3", audio.content, "audio/mpeg")},
        )
        print("STT:", transcript.status_code, transcript.json().get("text", ""))
        transcript.raise_for_status()


asyncio.run(main())
PY
```

`GET /voice/status` only confirms that a key is configured; the TTS and STT requests above verify that the live provider accepts it. The test keeps audio in memory and does not create an audio file.

## Access-control and cleanup checks

- Call `GET /auth/me` without an Authorization header; expect HTTP 401.
- Sign in as a second disposable account and request the first account's conversation messages; expect HTTP 404.
- Delete test conversations with `DELETE /conversations/{id}` when needed.
- At the end, remove the disposable account and all of its conversations, memories, and OTP records:

```bash
curl -i -X DELETE "$SAARTHI_API/auth/me" \
  -H "Authorization: Bearer $SAARTHI_TOKEN"
```

Expect HTTP 204. Use this only with the test account's token. Account deletion invalidates the account and removes its ADK conversation sessions.

## When Gemini returns 429

The API now passes Gemini's HTTP 429 through to the app with a friendly “chat limit” message. A 429 can mean the project exceeded requests per minute, input tokens per minute, requests per day, or another model-specific limit. These limits are attached to the Google Cloud project, not a single API key. Check the project's active limits and usage in [Google AI Studio](https://aistudio.google.com/) before retrying. Daily request limits reset at midnight Pacific Time; other limits may clear on shorter rolling windows. Avoid rapid repeated retries while the provider is rejecting requests.

Google's current guidance: [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) and [troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting).

## When Gemini returns 503

HTTP 503 means Gemini reports that the service is temporarily overloaded or unavailable. The API now returns 503 to the mobile app with a brief retry message. Wait before trying again and check the [Google AI Studio and Gemini API status page](https://aistudio.google.com/status). If this model keeps returning 503, Google recommends checking for an incident and temporarily trying another supported Gemini model; the app selects its model from `GEMINI_MODEL` in the root `.env`, so restart the API after changing it. See Google's [API error guidance](https://ai.google.dev/gemini-api/docs/api-errors).

## Current test record

Last exercised against the real services on 2026-10-03. Tests used an isolated API process on port 8001 and the configured PostgreSQL database; the user's port-8000 process was left untouched.

- Passed: development OTP request/verify and replay protection, authenticated profile and preferences, conversation creation/list/history setup/deletion, private conversation, cross-user conversation isolation, account deletion, ElevenLabs TTS, and ElevenLabs STT.
- Passed after fixing a discovered bug: Gemini-created pending memory, user confirmation, confirmed-memory edit, and deletion. `backend/app/main.py` now imports `embed`, which the edit route uses.
- Gemini was intermittent: the ADK-backed chat returned upstream 503 and 429 (`ResourceExhausted`) during the run, although other real turns and direct requests to the configured model succeeded. The model was present in Google's live model catalog for the configured key. Check the provider's usage/quota when this occurs; do not repeatedly hammer the endpoint. After that run, the API was updated to preserve upstream 429/503 status codes with a friendly message; other agent failures still return 502.
- Not verified in that run: a confirmed memory being recalled by a later conversation, real SMTP email delivery, and the native Android UI. The cross-conversation recall request was stopped by Gemini 503/429 responses. The local terminal also reported that Android SDK/`adb` were unavailable, so API testing was performed separately from device UI testing.
- No audio was written to disk. Synthetic test users and OTP records were audited after the run and count was zero.

## API surface covered

The main user flows touch `GET /api/health`, auth request/verify/me/delete, preference update, conversation list/create/messages/turn/delete, memory list/update/delete, and voice status/transcribe/speak. The full route schema is available at `/docs` while the API is running.
