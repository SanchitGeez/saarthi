> Historical snapshot, superseded by [the current document](../agent-handoff.md). Provider choices and test counts below describe the earlier implementation.

# Saarthi — agent handoff

Updated 2026-10-03. Repository: `/home/sanchit/projects/gita-as-a-service`.

## Start here

The latest user request is to hand off the implementation and debugging learnings in Markdown. They will test the latest voice fixes and report to another agent session. Do not assume those phone checks passed. The next task is to incorporate their results, finish native voice reliability checks, and fix any reproduced issue.

Latest report before the handoff:

- Voice transcription failed on the first attempt, then worked. The user considers error handling unfinished.
- Listen on a reply containing a shlok failed with `ExponentFileSystem.writeAsStringAsync` → Android `FileNotFoundException`/ENOENT for `reply-*.mp3` inside Expo Go's experience cache.
- The fixes below are implemented and bundle successfully; the user has not yet confirmed them on the phone.

No ongoing automation or delegated agent was created. The user's API/Metro processes should be preserved. No isolated verification server remains from the preceding test work; the final exports are files in `/tmp`.

## Product decisions and working preferences

- Name the product and companion **Saarthi**. Do not split Mitra and Saarthi into separate personas.
- Audience: religiously inclined Hindu adults roughly 25–40, dealing with work, relationships, family, and life decisions, often without someone to listen.
- Original, approachable spiritual companion; candid reflection and practical steps, one useful question at a time. Not a deity, clinical therapist, or human with fabricated lived experiences.
- Gita first; broader sources and a fictional character backstory are future work. Do not spend the next session designing that backstory.
- English, Hindi, and Hinglish. Original Sanskrit plus English/Hindi renderings should appear naturally when relevant.
- Lean React Native/Expo application, Android first, with iOS support. FastAPI, one Google ADK agent, Gemini, PostgreSQL. No microservice expansion, separate vector server, audio storage, or background job infrastructure for v1.
- Elegant light devotional interface, simple for nontechnical users. The polish pass uses maroon/saffron accents and a restrained diya/lotus mark. See `DESIGN.md`; do not infer final user approval of the new visuals.
- New app launch opens a new draft; conversations are created on first Send. History lives in a drawer on phones and a sidebar on wide screens.
- Save lasting memory automatically, selectively. Users edit/delete and can disable it. No per-message memory approvals or personality diagnoses.
- Failed chat messages must offer Retry/Remove and avoid duplicate replies. Voice transcription failures now have their own Retry/Discard flow.
- Test actual APIs/providers, not mocked provider replies. Synthetic input and disposable accounts are acceptable. Distinguish real provider tests, database regression tests, browser checks, and phone checks.
- The user dislikes repeated questions/approval interruptions. Continue authorized fixes autonomously and ask only for information genuinely needed.

Earlier discovery and marketing research is retained in `docs/product-discovery.md` and `docs/marketing-and-product-angles.md`. Those record comparisons with devotional/spiritual products and persona/messaging ideas; profitability and product-market fit are not established by the implementation or testing.

## Read these files in this order

| File | Purpose |
| --- | --- |
| `README.md` | Local startup, API inspection, feature walkthrough |
| `docs/product-polish-testing.md` | Detailed verification history and remaining device checks |
| `backend/app/turns.py` | Chat delivery states, stable IDs, retry/failure behavior, legacy import |
| `backend/app/agent.py` | Persona, memory rules/tools, context reconstruction, model calls |
| `mobile/src/screens/ChatHome.tsx` | Chat/composer, recording/transcription recovery, navigation guards |
| `mobile/src/components/ChatMessage.tsx` | Failed-message actions, scripture rendering, playback lifecycle |
| `mobile/src/voice.ts` | New playback cache helper, temporary-file cleanup, friendly errors |
| `mobile/src/api.ts` | Explicit Expo fetch, multipart uploads, timeouts, auth and diagnostics |
| `backend/app/main.py`, `schemas.py`, `voice.py` | Auth/routes, speech schema, actual ElevenLabs integration |
| `backend/tests/test_product.py`, `live_product.py` | Real DB/ADK regressions and live Gemini suite |

`docs/architecture-v1.md` and most of `docs/architecture-lean-candidate.md` are historical design proposals. A prominent current-implementation note now identifies superseded details. Do not restore four-table/ADK-event history or pending-only memory from those documents. Code plus this handoff describes current behavior.

## Current architecture

```text
Expo React Native client
  └── authenticated HTTP → FastAPI
       ├── PostgreSQL: users, conversations, chat_turns, memories, auth_codes
       ├── per-turn ADK Runner + in-memory reconstructed successful history
       │    └── one Saarthi LlmAgent → Gemini
       │         └── trusted, owner-scoped memory and scripture tools
       ├── legacy ADK DatabaseSessionService → old history import/deletion
       └── ElevenLabs: transient STT upload / MP3 TTS response
```

Application-owned tables:

- `users`: email identity, language, memory preference.
- `conversations`: owner, title, private flag, timestamps.
- `chat_turns`: stable UUID, user text, answer, processing/completed/failed/discarded state, errors/status code, scripture references and timestamps. This is canonical chat history and delivery tracking.
- `memories`: owner, kind, content, source conversation, exact evidence excerpt, status, optional 1536-dimensional vector/model and timestamps. Old pending/proposed fields remain for compatibility; new eligible agent writes are confirmed automatically.
- `auth_codes`: hashed one-time email codes, expiry, attempt count, consumed timestamp.

ADK's database service may also have runtime tables from older history. It is retained for legacy operations, not used as the canonical record of new turns. PostgreSQL pgvector is available, but current agent memory retrieval is bounded owner-filtered text ranking, not semantic vector search. Optional embeddings can be generated during manual edits; automatic turn commits clear embeddings and use text retrieval. Do not claim active semantic search just because a vector column exists.

Database startup uses SQLAlchemy `create_all` and creates the vector extension. There is no versioned Alembic migration setup; future schema changes need an explicit migration strategy.

### Chat delivery

- Mobile generates a stable `client_id` and reuses it for Retry. A completed replay returns the saved answer; changing text under an existing ID is rejected.
- Processing conflicts are rejected instead of starting a second generation. Conversation ownership is enforced.
- The request saves its processing state, generates synchronously, and saves completion/failure. There is no jobs table or worker.
- A 120-second processing lease turns interrupted jobs into visible retryable failures when history is loaded.
- Removed failed turns leave content-free discarded tombstones to prevent legacy import resurrecting them.
- Only successful exchanges are reconstructed into the next ADK prompt: at most the last 24 turns. ADK permits at most five model calls per invocation.
- Generation and one permitted fallback share a 90-second deadline. Fallback is only for provider 429/503, with staged memory/scripture changes reset before the fallback. No infinite retry loop.
- Mobile reconciles a lost response against server history; an HTTP/network failure alone does not prove the server failed.

### Agent memory and scripture

Tools: `find_memories`, `remember_detail`, `update_remembered_detail`, `get_gita_verse`. Trusted user/conversation context is supplied server-side through a ContextVar and checked against ADK context. The LLM cannot choose another owner's ID.

Relevant memories are prefetched, with the lookup tool available for more context. Memory writes stage at most one explicitly supported lasting detail per turn; exact evidence must occur in the latest user message. The prompt excludes transient feelings, diagnoses, speculative traits, sensitive identifiers and advice. Recurring patterns must be reported as recurring by the user. Normalized/word-overlap deduplication prevents many duplicate notes; explicit correction uses the update tool. Eligible changes commit with a successful answer, and failed generation commits none. This remains a heuristic policy, not proof that every model decision will be ideal.

Private chats and disabled memory block cross-chat retrieval and writes. The commit rechecks the account's preference. Users edit/delete memories in settings; deleting a source conversation removes sourced memories.

`backend/app/scripture.py` contains six source-checked verses: 2.14, 2.47, 2.48, 6.5, 6.26, 12.13. The tool returns Sanskrit, our English/Hindi renderings, source link and `[[gita:chapter.verse]]` marker. The mobile inserts a verse card at the marker. The prompt asks for at most one relevant verse and no adjacent repetition. Unsupported verses are not verified by this collection. Spoken text currently substitutes the verse title and selected-language rendering for the marker, not the original Sanskrit.

### Auth and voice

First-party SMTP email OTP plus signed PyJWT bearer tokens; no Supabase Auth or Resend dependency. Development with SMTP unset returns `dev_code`. Production does not and validates the JWT secret. Native session tokens use Expo SecureStore; web uses sessionStorage. OTP has expiry/attempt/resend controls.

ElevenLabs is the actual speech provider. Murf is not integrated despite credentials potentially existing in the sibling environment. STT uses `scribe_v2`; TTS uses `eleven_multilingual_v2`, MP3 44.1 kHz/128 kbps. TTS JSON accepts stripped text up to 10,000 characters; chat text is limited to 6,000. STT accepts multipart `file`, validates nonempty/at most 12 MiB, and buffers audio transiently. Backend provider timeout is 75 seconds; mobile voice timeout is 90 seconds. There is no audio database table/object store.

## Voice failures and fixes: do not conflate them

| Report | Established cause / evidence | Fix / status |
| --- | --- | --- |
| QR spinner / generic Expo error | User identified active phone VPN | User confirmed Expo opens after resolving VPN. Separate config/dependency issues also corrected. |
| Listen said “check details” | Actual speech request returned 422 at query.payload; OpenAPI broke because an annotation referenced removed `TurnRequest` import | Dedicated imported `SpeechRequest`; correct JSON body and MP3 OpenAPI schema. Real English/Hindi TTS passed; user confirmed playback at that time. |
| Recording upload failed in ~9 ms | Installed SDK's multipart serializer rejects plain `{uri,name,type}` before network | Real Expo File on native, Blob on web; explicit `expo/fetch`. Live real M4A transcription passed. User reported subsequent phone success after one failure. |
| Latest Listen ENOENT | Native legacy file write could not find the experience cache parent | Modern Directory/File cache creation and byte write implemented. Android/web bundles passed. **Awaiting phone confirmation.** |

Current voice files/behavior:

- `api.ts` checks a native file exists, is nonempty and is under 12 MiB before upload. Do not restore the old URI-object FormData part. Explicit Expo fetch keeps the client aligned with Blob/File uploads.
- `voice.ts` creates `Directory(Paths.cache, "saarthi-playback")` with `intermediates: true, idempotent: true`, writes a uniquely named MP3 from Uint8Array, and supplies its URI. Browser playback uses an object URL.
- `ChatMessage.tsx` cleans up on stop, completion, failure and unmount. A module-level stop function limits active players. Single-flight guards prevent double-tap generation from the same button. Friendly inline errors expose “Try listening again”; native details go to development info logs. Legacy file/base64 code and the unused `base64-arraybuffer` dependency were removed.
- `ChatHome.tsx` holds a failed recording URI only in component memory. Retry transcribes the same note; Discard deletes it. Success appends once to the current draft and deletes the file. Component unmount deletes the retained failed note. No persistence across app launches was added.
- Preparing/recording/transcribing hides playback controls and releases their active audio. Mic/upload operations have single-flight guards; chat switching and Send are blocked while a recording/upload/failed note needs resolution.
- Native permission/recording failures receive readable messages. Failed transcription remains actionable near the composer rather than a dismissible notification. A transcript that would exceed 6,000 characters remains retryable after shortening the existing draft.
- API request diagnostics use `console.info`, not `console.warn`, so expected offline failures do not create blocking yellow LogBox overlays. Logs omit tokens and message bodies; the network inspector can expose both, so sanitize captures.

The first intermittent recording failure is not proven to share the old serializer cause. Collect the exact new status/duration and native details if it recurs rather than guessing. Missing/empty recordings may need Discard/new recording rather than repeated retries. Retained files can be removed by the OS cache policy; the client detects a missing file.

## Verified work and limits

Detailed evidence lives in `docs/product-polish-testing.md`.

- **11/11** `test_product.py` regressions passed against real PostgreSQL and real ADK contexts, via FastAPI ASGI transport. They make no provider calls and use no provider mocks.
- Historical live product suite passed **15 checks** using actual Gemini and actual HTTP/database calls. It covered ownership, scripture, automatic memory, private mode, preferences, idempotency, failure and retry.
- The final failure test used nonexistent `gemini-saarthi-test-unavailable`, proving an actual upstream 404. An earlier non-Gemini-prefixed name had failed locally and was not adequate provider-failure evidence.
- Primary `gemini-3.8-flash` had both success and 429/503 during testing. `gemini-flash-lite-latest` passed actual calls and was used for an isolated full-suite server when the primary was unavailable. A catalog-listed `gemini-2.5-flash` was rejected for the key. Availability/quota observations are dated, not guarantees. Do not keep retrying quota failures blindly.
- Actual ElevenLabs English/Hindi TTS returned 74,022 and 106,623 MP3 bytes, decoded in RAM by ffprobe at 44.1 kHz.
- Actual STT: TTS synthetic English → ffmpeg AAC/M4A conversion through pipes → 43,194-byte authenticated multipart upload → correct transcript. No audio was written to disk and the disposable account was deleted.
- Previous browser walkthroughs covered OTP, fresh draft, drawer/history, settings, verified verses, real failed-turn Retry, memory editing, sign-out, modal focus/Escape, and responsive layout. 22 reading-text color combinations met 4.5:1. These are not native keyboard/audio tests.
- Latest **TypeScript passed** and **Android/web Expo exports passed** to `/tmp/saarthi-voice-recovery-export` after playback/recovery changes. Earlier Expo Doctor passed all 21 checks after dependency/config correction.
- Test accounts/temporary credential files and isolated QA servers from prior testing were cleaned up. Do not delete the user's account/history or reset the PostgreSQL volume.
- No Android SDK/adb exists here. Native debugger targets were visible intermittently, but the last read-only `Runtime.evaluate` probe returned protocol `-32601`; it did not execute a phone filesystem test. Do not claim that it verified cache creation.
- Latest native playback, retained-note Retry/Discard, software keyboard behavior, TalkBack, and audio routing still need phone verification. SMTP sending and production readiness were not tested.

## Local setup and diagnostics

The root `.env` contains the user's temporary Gemini credential. Optional ElevenLabs/OpenAI-compatible embedding values can be read from `../mindlap/.env` in development through an allowlist; its database URL is deliberately ignored. Never paste credentials into documentation, logs, commits or messages. Actual secret values are unnecessary for continuing.

Use `SAARTHI_DATABASE_URL` for this app. Default local PostgreSQL host port is 54330, container `saarthi-postgres`; `docker-compose.yml` uses pgvector PostgreSQL 17. Never connect to or modify the neighboring MindLap database.

```bash
# Repository root
docker compose up -d postgres

# Terminal A, backend/
uv sync --locked
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal B, mobile/
npm install
npx expo start --go --lan --clear
```

Installed mobile target is Expo SDK 57, React 19.2.3, RN 0.86.3, TypeScript ~6.0.3. `expo-asset` is a direct dependency/plugin required by audio; obsolete `newArchEnabled` config was removed. Use compatible Expo Go.

`mobile/.env` last pointed to `http://192.168.1.9:8000/api`. This was the laptop's Wi-Fi IP, not a permanent address. Check the current IP before changing it. `10.0.2.2` is only for the Android emulator. Phone and laptop must be mutually reachable, usually on the same Wi-Fi with VPN off. Phone browser `/api/health` tests API reachability; port 8081 `/status` should say `packager-status:running`. Missing `adb` when pressing `a` does not prevent QR/Expo Go use.

For phone requests: open the app, press `j` in Metro, open **Expo Network** and reproduce. API client uses Expo fetch. Inspect route, status, payload and response; Uvicorn logs establish whether a request reached FastAPI. Provider calls happen on the backend, not in the phone's network panel. A native playback error after a successful `/voice/speak` response belongs to the phone file/player path.

```bash
# mobile/
npm run typecheck
npm run doctor
npx expo export --platform android --platform web --output-dir /tmp/saarthi-check-export

# backend/, with local PostgreSQL running
uv run --locked python -m unittest discover -s tests -p test_product.py -v
```

For real Gemini re-runs, use the isolated-server commands in `docs/product-polish-testing.md` and `backend/tests/live_product.py`. Use disposable accounts; account deletion should be the cleanup path. Keep test tokens out of output. Do not substitute mocks and call it end-to-end verification.

## Next session: exact device checklist

1. Read the user's new result first. Reload Expo Go to ensure the latest bundle is loaded; restart Metro if environment/dependencies changed.
2. Listen to the same shlok-containing reply that produced ENOENT. Confirm sound, Stop, natural completion and listening again. A 200 MP3 response plus native error requires file/player tracing.
3. Record a fresh 5–10-second note, Finish, confirm transcript appears in the draft and is not sent automatically. Record immediately after playback and play immediately after recording.
4. Cause a real temporary connection failure during transcription, then restore it. The failed note should show Retry/Discard. Retry should add exactly one transcript without overwriting existing draft text; Discard should clear the state and allow another recording.
5. Double-tap Finish/Retry/Listen and verify no overlapping upload/playback. Deny microphone permission and verify readable recovery. Check 60-second auto-finish and silence/empty note handling.
6. Check chat-switch guards while voice work is unresolved. Sign-out/unmount should discard the retained note and release playback. Check background/reopen and Android audio routing; these were not proven by exports.
7. Check multiline composer above software keyboard, large font settings, TalkBack labels, drawer Back/focus, and failed chat-message Retry/Remove. Native UI checks remain separate from earlier web QA.
8. Update `docs/product-polish-testing.md` with exact evidence and this handoff with the new state. State what was actually verified and what remains uncertain.

The original product/architecture is implemented enough for iterative device QA. Avoid starting a new architecture rewrite, new paid integrations, persona backstory, background queue, or broad provider retries as a substitute for finishing this specific voice experience.
