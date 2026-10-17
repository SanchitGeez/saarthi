# Saarthi — implementation handoff

Updated 2026-10-04. Repository: `/home/sanchit/projects/gita-as-a-service`.
This is the current handoff. The [October 3 handoff](history/agent-handoff-2026-10-03.md)
is retained for the earlier text app and voice-note debugging evidence.

## Start here

Saarthi now has a LiveKit conversation with **Parth**, plus Type, voice notes,
spoken replies, shared history and selective memory. The current local preset is
OpenRouter Flash Lite for answers and ElevenLabs for recognition and speech.
The user explicitly chose a built-in ElevenLabs voice after the free account
blocked native Hindi library voices. Do not silently replace that choice.

The next priority is the **quality of Hindi conversation**, followed by physical
Android call/playback testing. The final real Hindi call passed its technical
checks, but the cheap answer model sometimes answered its own greeting, repeated
the user's words or missed explicit memory requests. A passing pipeline smoke test
is not proof of useful advice. No product-market fit, production launch or physical
phone call has been established by these checks.

## Decisions to preserve

- Product name Saarthi; companion name Parth, visibly identified as AI. An original
  approachable companion, not Krishna, a human priest, therapist or divine authority.
- Target hypothesis: Hindu adults around 25–40 working through relationships, work,
  family and life decisions. The strongest promise is **helping work through something
  over time**. Customer demand and willingness to pay remain hypotheses.
- One supplied temple portrait for all states. Dim before starting; Baat karein with
  microphone takes roughly 80% of the start bar, with a smaller TYPE/keyboard action.
  Connection lights the scene and plays one local temple bell before the opening.
- The LLM chooses the opening using permitted recent conversations, memory and time
  since the last visit. General greetings are fine. No fixed opener, compulsory
  check-in, timing buckets, invented outcomes or guilt about returning late.
- Actual listening/thinking/speaking/reconnecting state, captions, mute and End.
  History and memory are in the drawer. Type/settings retain the light devotional theme.
- Continuity comes from durable context. The worker waits for calls, but no LLM runs
  between visits. No scheduled check-ins, background tasks, concern-tracking table,
  random activities, extra poses or lip sync have been implemented.
- Calls end on background/unmount. No lock-screen calling integration yet.
- Lasting facts save selectively and automatically with exact evidence. Users can
  edit/delete or disable memory; no per-memory approval workflow.
- Gita first: six verified verses only. Broader scripture and persona backstory are
  future work. Avoid adding infrastructure to solve an unverified product hypothesis.
- Continue authorized work autonomously. Keep provider usage intentional and state
  whether evidence is a unit/API test, real provider call, browser check or phone check.

## Current models, in plain words

| Job | Current local selection | Important limit |
| --- | --- | --- |
| Writes typed and spoken answers | OpenRouter `google/gemini-2.5-flash-lite` | Cheap testing brain; Hindi instruction following needs evaluation |
| Hears a live call | ElevenLabs `scribe_v2_realtime` | Hindi/English hints and server VAD configured |
| Transcribes a recorded note | ElevenLabs `scribe_v2` | Separate recorded-upload route |
| Speaks answers, live and Listen | ElevenLabs `eleven_multilingual_v2` | Slower/costlier than Flash; built-in George can retain an English accent |
| Voice | George, `JBFqnCBsd6RMkjVDRZzb` | User-approved temporary choice, not a native Hindi voice |

`LLM_PROVIDER`, `STT_PROVIDER` and `TTS_PROVIDER` are independent root `.env`
selectors. Key presence does not select a provider. Restart both API and worker
when changing them. Existing environment variables override dotenv values; avoid
stale exported selectors. `.env.example` documents the current preset; omitted
settings can have different code defaults. Optional OpenAI embeddings are separate
from OpenRouter. Credentials and temporary logs stay local.

Implemented alternatives: Gemini; Deepgram Nova-3 multilingual recognition; Murf
Falcon with verified `en-IN-abhinav`, Conversational style; ElevenLabs Flash v2.5.
No application fallback switches between speech vendors on a billing failure.
Google has an explicitly configured bounded model fallback; OpenRouter may perform
its own upstream routing. See [live voice setup](live-voice.md).

## Architecture and ownership

```text
Expo client ─ authenticated HTTP ─ FastAPI ─ PostgreSQL
     │                              ├ typed turn: OpenRouter or ADK/Gemini
     │                              └ room token + explicit agent dispatch
     └ LiveKit room ─ named Python worker ─ STT → LLM/tools → TTS
                              └ owned transcript/memory writes to PostgreSQL
```

Seven app tables: `users`, `conversations`, `chat_turns`, `memories`, `auth_codes`,
`voice_sessions`, `voice_messages`. Older ADK runtime tables remain for legacy
import/deletion. No audio store, recording table, jobs queue or ongoing-concern table.
Startup `create_all` supports additive local tables; it is not an Alembic migration
system. Future column changes need actual migrations.

Typed delivery uses stable client UUIDs, persisted processing/completed/failed
states, reconciliation after a lost response and content-free discarded tombstones.
A processing lease is 120 seconds; generation has a 90-second overall deadline.
OpenRouter has a bounded five-call tool loop; Gemini uses ADK. Failed typed
responses do not commit staged memory or enter the reconstructed successful history.

Calls use a stable client UUID as the durable session ID, one active call per account,
explicit worker name/claim, microphone-only publishing and data enabled for readiness
RPC. Token TTL is two minutes; call defaults are 15 minutes total, two minutes idle,
60 seconds abandoned initial connection and 30 seconds client readiness. Closing is
committed before room deletion so late writes are refused. Failed room cleanup stays
retryable and blocks another call. Do not reopen an ended ID.

Context includes bounded owned history: last three eligible conversations plus the
current conversation, up to eight successful typed turns and 16 voice events across
those selected conversations, merged down to the last 16 messages, plus up to eight confirmed
memories. See `continuity.py` for truncation/ranking details. Time is supplied to the
LLM as context, not a greeting algorithm. Current privacy/language/context refreshes
before each user turn, including LiveKit's copied turn context.

Voice memory saves require a trusted current user transcript ID, exact source text,
an active owned session and current memory/privacy permission. At most one saved
detail per user turn. An accepted voice tool commits immediately; it does not wait
for a successfully completed spoken answer. Typed memory stages until success.
The model's choice remains heuristic even with these persistence checks.

Memory-off/private mode blocks cross-chat recall and new saves, but keeps current
chat history. Deleting only a memory leaves its original source messages available
for later context; deleting the source chat removes associated memory and voice data.
The app saves finalized playout transcripts, including interruption markers; they do
not prove what the user heard. The app does not record audio. Provider retention is
separate; free ElevenLabs accounts may ignore zero-retention requests. Do not claim
end-to-end encryption or provider-zero-retention.

## Files worth reading

| File | Responsibility |
| --- | --- |
| `backend/app/config.py`, `providers.py`, `voice.py` | Explicit selectors, provider construction, recorded STT/TTS |
| `backend/app/voice_sessions.py` | Ownership, token/dispatch, idempotency, end/cleanup and evidence writes |
| `backend/app/voice_worker.py` | Ready handshake, opening, real media pipeline, tools, transcripts and guards |
| `backend/app/continuity.py`, `conversation_history.py` | Permitted context and merged typed/voice history |
| `backend/app/turns.py`, `agent.py`, `openrouter_turn.py`, `guidance.py` | Durable typed delivery, prompts and shared tool policy |
| `backend/app/models.py`, `main.py`, `scripture.py` | Schema, auth/settings/deletion, verified verses |
| `mobile/src/call/`, `mobile/src/screens/CallHome.tsx` | Resource ownership, platform media transport, scene and controls |
| `mobile/src/screens/ChatHome.tsx`, `components/ChatMessage.tsx`, `voice.ts`, `api.ts` | Type, voice-note recovery, playback cache and uploads |
| `backend/tests/test_product.py`, `test_voice.py`, `test_providers.py`, `live_voice.py` | Regression suite and opt-in real-provider media smoke |

## Verification as of October 4

- **30 backend regressions** passed: 11 product, 11 voice, eight provider tests.
  Database/API tests use actual PostgreSQL; selected external boundaries are mocked
  in deterministic tests. These are not 30 live vendor calls.
- **16 mobile tests**, TypeScript and web export passed. Android plugin prebuild and
  native JS/Hermes export passed. No Android SDK/adb was available: no APK or physical
  device call was verified here.
- Real Cloud English smoke with Murf/Deepgram/OpenRouter passed received audio,
  recognition, reply, exact-evidence memory, shared history, duplicate-ready opening
  suppression and cleanup. That was the earlier alternative preset.
- Latest real Hindi Cloud smoke with ElevenLabs/OpenRouter passed the same mechanical
  flow. Recognition delay measured about **1.10 seconds** in one synthetic run after
  the server-VAD fix, versus about 20 seconds before it. This is transcript delay,
  not a whole-call latency benchmark. The answer quality was still weak: the model
  thanked its own greeting and repeated the user's preference instead of useful advice.
- Recorded Hindi TTS → STT roundtrip passed. George's accent and natural conversational
  quality have not been certified by that roundtrip.
- Browser checks at phone and desktop sizes covered dim/lit scene, captions, mute,
  End, Type and a real typed OpenRouter reply. Earlier browser work covered OTP,
  memory/settings, failed-turn Retry, modal focus and contrast.
- Original playback cache ENOENT and voice-note retry fixes bundle successfully;
  latest native behavior still awaits physical-device confirmation.

Temporary `/tmp` logs/screenshots are session-local evidence, not durable artifacts.
No new paid smoke run is required just to verify these documentation edits. See the
[testing runbook](api-e2e-testing.md) and [verification history](product-polish-testing.md).

## Learnings and next checks

Read [voice debugging gotchas](voice-debugging-gotchas.md) before changing the pipeline.
It records the language/script/commit fixes, stale workers, free-plan restrictions,
Murf catalogs, SDK constraints, native cache/upload failures and privacy limitations.

1. Evaluate short natural Hindi/Hinglish exchanges: relevant answer, one useful question,
   correct memory choice, scripture restraint, code switching and pronunciation. Compare
   answer models deliberately; keep provider selectors configurable.
2. Build a native development app and test permission denial, real room start, bell,
   interruption/echo, Bluetooth/speaker routing, mute, reconnect, End during connection,
   backgrounding and repeated start/end. Expo Go only supports Type for this app.
3. Recheck Listen for a shlok reply, stop/completion/replay, record after playback,
   failed transcription Retry/Discard and double taps. Check large fonts, keyboard,
   TalkBack and drawer focus/back behavior.
4. Deployment still needs SMTP, secrets, migrations, reviewed safety/privacy terms,
   rate/spend limits and operational monitoring. Do not present a local smoke as launch readiness.

## Local operations and Git

Use the app's PostgreSQL at host port 54330; preserve the user's data and unrelated
services. Root `.env` is canonical. Development only may inherit allowlisted
OpenAI/ElevenLabs credentials from `../mindlap/.env`; it ignores that database URL.
Never reset the volume or copy neighboring database credentials.

An API on 8000 and isolated QA API on 8001 were used; temporary process IDs, LAN IPs
and ports are not guarantees for the next session. Inspect actual processes before
starting or stopping them. Only one worker with `LIVEKIT_AGENT_NAME=saarthi-parth`
should receive jobs for this environment. A stale duplicate was the cause of an
otherwise unexplained readiness failure.

`origin` is `git@github.com-personal:SanchitGeez/saarthi.git`, using the personal SSH
host configuration. HTTPS previously authenticated to an account without write access.
Do not print private keys, switch unrelated account defaults or force push. All keys,
cache files, provider audio and temporary test accounts must stay out of Git.

The [voice-companion proposal](../plans/voice-companion/README.md) is preserved as
historical planning/prototype material. Its simulated call and superseded greeting,
persona and future-feature choices are not the current implementation contract.
