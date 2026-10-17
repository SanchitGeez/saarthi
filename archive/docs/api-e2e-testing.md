# Current testing runbook

Updated 2026-10-04. The [initial API walkthrough](history/api-e2e-testing-2026-10-03.md)
is preserved as history; its per-memory confirmation and Gemini-only assumptions
are superseded. See [live voice setup](live-voice.md) for API/worker/client startup.

## Regression checks

Start this project's PostgreSQL with `docker compose up -d postgres`. Use the root
`.env`, a separate local database and development mode. These tests exercise real
PostgreSQL/API policy plus controlled external boundaries; they are not live vendor tests.

```sh
# From backend/
uv sync --locked
uv run python -m unittest discover -s tests -p 'test_*.py' -v

# From mobile/ in another terminal
npm ci
npm test -- --runInBand
npm run typecheck
npm run build:web -- --clear
npx expo export --platform android --output-dir /tmp/saarthi-android-export
```

Last verified October 4: 30 backend and 16 mobile tests, typecheck/web export, earlier
Android plugin prebuild/native JS export. No APK or real phone audio has been verified
on this machine. Export success cannot establish device permissions/audio routing.

## Real-provider media smoke

This spends configured provider credits. Start the API and one named worker with the
same `.env`/database/LiveKit project. A convenient isolated API port is 8001; the smoke
script defaults there. Do not start a second stale worker with the same agent name.

```sh
# backend/, API/worker already running
SAARTHI_TEST_API=http://127.0.0.1:8001/api uv run python tests/live_voice.py
SAARTHI_TEST_API=http://127.0.0.1:8001/api SAARTHI_TEST_LANGUAGE=hi uv run python tests/live_voice.py
```

The script creates a disposable development account, synthesizes speech, joins the
real room and checks received audio, recognition, answer delivery, exact-evidence
memory, shared history, duplicate-ready opening suppression and cleanup. Use synthetic
content. Successful assertions establish mechanics; listen and read replies separately
for helpfulness, pronunciation, code switching and accurate memory decisions.

The earlier English Murf/Deepgram/OpenRouter run and latest Hindi
ElevenLabs/OpenRouter run passed. Hindi answer quality remained weak despite the
mechanical pass. One recognition-delay sample improved from about 20 seconds to
1.10 seconds with server VAD; this is not a full latency benchmark.

`live_product.py` is the historical real Gemini typed suite:

```sh
# backend/, two isolated APIs required by this suite
uv run python tests/live_product.py --base http://127.0.0.1:8001/api --failure-base http://127.0.0.1:8002/api
```

Run those APIs with `LLM_PROVIDER=gemini`. The failure API must use a nonexistent
Gemini-prefixed model, e.g. `GEMINI_MODEL=gemini-saarthi-test-unavailable`, and empty
`GEMINI_FALLBACK_MODEL`. Otherwise OpenRouter selection ignores the deliberately
bad Gemini setting and invalidates the failure test. The suite historically passed
15 checks; that is not a new verification of today's OpenRouter preset. `--keep`
retains temporary auth state for debugging; prefer default cleanup and never publish it.

## Manual browser and phone checks

Use `npm run web` with `EXPO_PUBLIC_API_URL=http://localhost:8000/api` and matching
`MOBILE_ORIGINS`. Browser mic needs localhost or HTTPS; plain phone LAN HTTP is
insufficient. Restart/clear Metro after environment changes. For native calls use
`npm run android` or `npm run ios` on macOS with required platform tooling; Expo Go
can test Type but cannot load this app's LiveKit native modules.

1. Sign in; confirm fresh dim temple and clear AI identity. Baat karein should light
   after connection, play the bell once and produce an LLM-chosen opening. Reconnect
   or duplicate readiness must not replay it.
2. Speak Hindi/Hinglish, interrupt naturally, mute/unmute, End and start again. Check
   actual captions and agent states. End during permission/connection and background
   the app; microphone and room must close. Test a real brief network interruption.
3. Type in the same conversation, then reopen history. Confirm successful typed and
   finalized voice messages merge without duplicate user bubbles. Check failed typed
   Retry/Remove and reconciliation after a lost response.
4. Ask explicitly to remember a lasting preference. Verify the saved note has source
   evidence; edit/delete it. In private/memory-off mode, verify no imported cross-chat
   details or new saves, while the current conversation remains readable.
5. Check a verified shlok and Listen, Stop/replay, recording after playback, failed
   transcription Retry/Discard and double taps. Voice notes append to draft without
   auto-sending. Denied permission and missing cached recordings need readable recovery.
6. On a physical phone check Bluetooth/speaker/echo, software keyboard, large fonts,
   TalkBack, drawer Back/focus and captions. Browser checks do not establish these.
7. Delete the disposable account and confirm its rooms/history/memory are removed.
   Preserve the user's real account, data and PostgreSQL volume.

## Diagnosis and evidence

Open `/docs` for endpoint schemas; use Expo Network or browser DevTools for client
traffic. `POST /api/voice/speak` expects JSON text and returns audio; a 200 followed
by native ENOENT points at the local cache/player. Backend/worker logs establish
provider failures. Log status, duration, provider/model and reproducible steps without
keys, OTPs, tokens or personal stories. The inspector itself can expose sensitive data.

Provider readiness means keys are configured, not that credits/models/voices work.
Quota failures, 402 voice-plan restrictions, stale worker readiness errors and bad
language detection have different fixes. Read [the observed gotchas](voice-debugging-gotchas.md).
Record exact test date, selected providers, mechanical assertions, subjective listening
results and untested device behavior in [verification history](product-polish-testing.md).
