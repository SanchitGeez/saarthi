# Parth live conversations

Saarthi now has a native/web LiveKit call path alongside its existing typed chat.
The single temple reference image dims before the call and lights after the agent/audio
connection is ready. A locally synthesized bell plays once. The client publishes the
microphone and calls the readiness RPC; the worker claims one greeting per session.
The LLM decides whether to greet generally or gently return to something previously
shared. No fixed opener, required check-in, gap-based guilt, or invented outcomes.

## Run

Set root `.env`: `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`,
`OPENROUTER_API_KEY` and `ELEVEN_LABS_API_KEY`. Keep credentials on the API/worker.
The current user-approved preset (2026-10-04) is:

```dotenv
LLM_PROVIDER=openrouter
OPENROUTER_MODEL=google/gemini-2.5-flash-lite
STT_PROVIDER=elevenlabs
ELEVEN_LABS_STT_MODEL=scribe_v2
TTS_PROVIDER=elevenlabs
VOICE_TTS_MODEL=eleven_multilingual_v2
ELEVEN_LABS_TTS_MODEL=eleven_multilingual_v2
ELEVEN_LABS_VOICE_ID=JBFqnCBsd6RMkjVDRZzb
```

Live recognition uses `scribe_v2_realtime`; recorded notes use `scribe_v2`.
George is a built-in English voice and may retain an English accent in Hindi.
The user chose it temporarily after the free plan blocked a native Hindi library
voice through the API. Model names and public voice IDs are not credentials.

To use the earlier tested Murf/Deepgram alternative, set the following and provide
`MURF_API_KEY` (`MURF_AI` alias also works) and `DEEPGRAM_API_KEY`:

```dotenv
STT_PROVIDER=deepgram
DEEPGRAM_MODEL=nova-3
DEEPGRAM_LANGUAGE=multi
TTS_PROVIDER=murf
MURF_MODEL=FALCON
MURF_VOICE=en-IN-abhinav
MURF_STYLE=Conversational
MURF_LOCALE=
```

Restart both API and worker after editing `.env`. The three selectors are independent:
`LLM_PROVIDER=gemini` uses the Google key/models; `STT_PROVIDER=elevenlabs` uses
Scribe; `TTS_PROVIDER=elevenlabs` uses the selected ElevenLabs TTS model. Unused provider keys are
not required. Missing selected keys disable calls and prevent worker startup; a quota
failure ends the call with an actionable message rather than silently billing another
provider. Google has one explicitly configured fallback model; OpenRouter has no
application fallback. OpenRouter manages its own upstream provider routing.

The LLM selector also applies to Type. Its bounded tool loop shares the ADK prompt,
verified scripture and exact-evidence memory checks. Embeddings remain independently
optional and use `OPENAI_API_KEY`; the OpenRouter key is never used for embeddings.
Both `/voice/speak` and `/voice/transcribe` follow the selected speech providers.

Falcon voice IDs are model-specific. Verify using Murf's
`GET /v1/speech/voices?model=FALCON`; the default catalog lists Gen2 voices which
may fail on Falcon. Abhinav was verified in the account's Falcon catalog with English
India and Hindi India. Set `MURF_LOCALE=hi-IN` to force Hindi; leave blank for the
voice default. Natural Hinglish and voice character still need listening evaluation.

The current OpenRouter model catalog quotes Flash Lite at $0.10 per million input
and $0.40 per million output tokens (checked 2026-10-03). This excludes STT, TTS,
LiveKit and any provider-specific extras. Model limits and prices can change.

Start PostgreSQL: `docker compose up -d postgres`.

From `backend`:

```sh
uv sync
uv run python -m app.voice_worker download-files
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# Separate terminal, same backend directory:
uv run python -m app.voice_worker dev
# Production worker instead:
uv run python -m app.voice_worker start
```

From `mobile`, set the phone-reachable `EXPO_PUBLIC_API_URL`, run `npm ci`, then
`npm run android` or `npm run ios` on macOS. Live calls need a native development
build; Expo Go supports Type. Android requires the Android SDK/emulator or a phone.
For web: `npm run web` with a localhost API; the API's `MOBILE_ORIGINS` must include
the exact browser origin. Microphone access requires localhost or HTTPS. Re-export
with `--clear` after changing an Expo public environment variable to avoid stale values.

## Implementation

- `app/voice_sessions.py`: authenticated start/status/end. The request UUID is the
  durable session UUID. Retries return the same call; an ended ID cannot be reopened.
  User-row locks serialize starts, evidence writes and deletion. One active call per
  user. Room tokens expire in two minutes, publish microphone only, and enable data
  for the readiness RPC. Metadata contains only a session ID, never memory or secrets.
- `app/voice_worker.py`: explicit agent dispatch, one worker claim, named participant
  binding, readiness, streaming selected STT → LLM → TTS (currently ElevenLabs Scribe →
  OpenRouter Flash Lite → ElevenLabs Multilingual v2), configured through `app/providers.py`. Silero VAD and the multilingual turn detector support interruptions.
  Gemini fallback is bounded and does not replay partially streamed responses.
  Worker models are prewarmed; a small fixed worker pool avoids unbounded idle workers.
- `app/continuity.py`: bounded recent history and permitted memory. Private chats and
  memory-off sessions import nothing from other conversations. Elapsed time is context
  for the LLM, not a greeting-selection rule. Context refreshes before each user turn.
- `app/conversation_history.py`: typed and finalized voice messages in one ordered
  history. Interrupted assistant text remains marked; a playout transcript is not
  proof that the user heard it. ADK typed replies also receive the merged history.
- `app/guidance.py`: shared evidence checks. Voice memory writes require a trusted
  current user transcript ID, an exact quote, active session, live account, and current
  privacy settings. One saved detail per user turn. Scripture comes from the verified
  collection; the voice agent cannot invent a tool-verified passage.
- `mobile/src/call/`: resource-owning controller and platform transport adapters.
  Cancellation, stale events, lost responses, permission failure, failed cleanup,
  reconnection, backgrounding and a client-side time limit are handled explicitly.
- `mobile/src/screens/CallHome.tsx`: scene, controls and drawer; Type retains the existing
  text experience. Agent states and captions come from LiveKit, not animation timers.

New tables are additive: `voice_sessions` and `voice_messages`; existing tables do
not change. Startup `create_all` works for this additive local upgrade. A production
rollout should apply its normal reviewed schema migration before exposing the API.

## Limits and privacy

Defaults: 15 minutes per call, two minutes of inactivity, one active call per account,
30 seconds for client agent readiness, 60 seconds for abandoned initial connections.
Workers close rooms on normal shutdown; empty rooms also expire. An ended call or
account deletion refuses late transcript/memory writes. A failed room cleanup stays
retryable and blocks another call until it succeeds. This is continuity from durable
context, not an LLM continually running between visits.

Saarthi does not record audio or enable LiveKit recording. Transcripts remain in chat
history. Memory off disables cross-chat context and new memory saves; it does not
remove transcripts. Deleting a chat/account cascades its voice data and associated
memories. Deleting a memory alone leaves original chat messages. Provider retention
is separate: Deepgram requests opt-out from its model improvement program (which may
affect billing); ElevenLabs may decline zero-retention on non-enterprise plans. Murf
and OpenRouter retention follows their account/provider settings.
Do not market these calls as end-to-end encrypted or as provider-zero-retention.

Hindi recognition currently uses ElevenLabs Scribe with Hindi/English hints; Deepgram Nova-3 multilingual is an alternative. Natural Hinglish,
accents, pauses, Bluetooth routing and speaker echo still need real-device testing;
no language-quality or latency benchmark is claimed by the automated suite.

## Tests

```sh
# Backend policy/API regression tests, with real local PostgreSQL:
cd backend
uv run python -m unittest discover -s tests -p 'test_*.py' -v
# Opt-in real media + provider test: API/worker already running; consumes usage.
SAARTHI_TEST_API=http://127.0.0.1:8001/api uv run python tests/live_voice.py

# Mobile controller and screen tests:
cd mobile
npm test
npm run typecheck
npm run build:web -- --clear
# Native bundle verification without an installed Android SDK:
npx expo export --platform android --output-dir /tmp/saarthi-android-export
```

The live smoke test uses a temporary account and synthetic speech to check actual
received audio, duplicate-ready greeting suppression, speech recognition, generated
reply, evidence-backed memory, shared history and cleanup. It is deliberately separate
from the deterministic regression suite; provider quotas can block it.

Testing on 2026-10-04 passed **30 backend regression tests**, **16 mobile tests**,
TypeScript checking and web export. Android plugin prebuild and native JS/Hermes
export passed earlier; an APK and physical-device call remain unverified without
the Android SDK/device. Deterministic tests control selected external boundaries;
they must not be described as real-provider tests.

The earlier English Cloud smoke received actual Murf audio, recognized speech with
Deepgram, generated an OpenRouter reply, saved exact-evidence memory, suppressed a
duplicate opening and cleaned up the room. The latest Hindi smoke uses ElevenLabs
and is described below. Browser checks covered lighting, captions, mute/End, Type
and a real typed reply. Regression coverage protects current privacy/context refresh.

## ElevenLabs Hindi preset (2026-10-04)

The local `.env` now selects `STT_PROVIDER=elevenlabs`, `TTS_PROVIDER=elevenlabs`,
`VOICE_TTS_MODEL=eleven_multilingual_v2` and
`ELEVEN_LABS_TTS_MODEL=eleven_multilingual_v2`. Live recognition uses
`scribe_v2_realtime`; recorded notes use `scribe_v2`. OpenRouter Flash Lite still
writes both voice and typed replies. Live recognition hints Hindi plus English for
auto/Hindi/Hinglish preferences, or English plus Hindi for English preference. This
avoids unrestricted language detection choosing an unrelated language. Delayed
language-reporting metadata is disabled so the ordinary committed transcript can
reach the answer model without waiting for that metadata. Reported language follows
the primary hint. ElevenLabs server VAD commits after 0.8 seconds of silence instead
of waiting for a manual transcript flush.
Hindi/Hinglish voice instructions produce Hindi
words in Devanagari, while typed Hinglish keeps its existing Roman script behavior.

The new ElevenLabs key authenticated, but its free plan returned `paid_plan_required`
for a native Hindi library voice (Yash, `XcVyMASZ3J9LrnSxDs2W`). The app therefore
uses the existing built-in George voice (`JBFqnCBsd6RMkjVDRZzb`) with Multilingual v2.
This can speak Hindi, but the English source voice may retain its accent. A paid key
is needed to use the selected native Hindi library voice through the API. Switching
providers cannot itself guarantee native pronunciation. Multilingual v2 favors voice
quality over the lower latency and lower price of Flash v2.5.

For Hindi live smoke testing, run the API/worker with the current settings and use:
`SAARTHI_TEST_LANGUAGE=hi uv run python tests/live_voice.py`.

Validation for this preset: 30 backend regressions passed. A real LiveKit Hindi smoke
call passed generated Hindi audio, Hindi transcription, a spoken reply, history,
exact-evidence memory and room cleanup. The free-account built-in voice can retain
an English accent. The cheap answer model also showed inconsistent instruction
following in earlier Hindi runs; passing the speech test is not a quality guarantee
for Hindi advice. Model/voice listening evaluation remains necessary.

See [the current handoff](agent-handoff.md), [testing runbook](api-e2e-testing.md)
and [observed debugging gotchas](voice-debugging-gotchas.md) for the copied-context
fix, duplicate workers, SDK option constraints, native playback/upload failures and
remaining device checks.
