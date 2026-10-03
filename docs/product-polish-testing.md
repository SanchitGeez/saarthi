# Current verification update — 2026-10-04

The October 3 record below is historical. Companion naming, home scene and worker
architecture have since changed: Saarthi is the product, Parth the companion, and
LiveKit provides live conversations. See [the current handoff](agent-handoff.md).

| Check | Last established result |
| --- | --- |
| Backend regression | 30 passed: 11 product, 11 voice, eight provider; real database with controlled external boundaries |
| Mobile regression / typecheck | 16 passed; TypeScript passed |
| Web / native bundle | Web export passed; Android plugin prebuild and JS/Hermes export passed; no APK/device call |
| Real English Cloud call | Earlier Murf + Deepgram + OpenRouter preset passed audio, transcript, reply, memory, shared history, duplicate opening suppression, cleanup |
| Real Hindi Cloud call | Current ElevenLabs + OpenRouter preset passed the mechanical flow; semantic answer quality still weak |
| Hindi recorded speech | Real TTS/STT roundtrip passed; not a subjective pronunciation evaluation |
| Browser | Phone/desktop layouts, dim/lit scene, captions, mute/End, Type and real OpenRouter typed reply checked |

Latest Hindi recognition-delay sample improved to about 1.10 seconds after server
VAD, versus about 20 seconds with manual commit. This measures transcript delay in
one synthetic run, not end-to-end latency. Flash Lite sometimes repeated the user's
request, answered its own greeting or missed memory requests in earlier runs. The
final memory assertion passed, but Hindi advice quality needs broader evaluation.
George is a user-approved temporary built-in voice because the free ElevenLabs plan
blocked native Hindi library voices; an English accent remains possible.

Physical-device call, echo/interruptions, Bluetooth, software keyboard, TalkBack,
latest playback cache fix and voice-note Retry/Discard remain pending. SMTP,
production deployment and customer demand have not been validated. Use the
[current runbook](api-e2e-testing.md) and [gotchas](voice-debugging-gotchas.md).

---

# Product polish: changes and verification

Date: 2026-10-03. This supplements [the API runbook](api-e2e-testing.md).

## Implemented product contract

- One identity: Saarthi. White, deep maroon, and restrained saffron; original diya/lotus mark and launcher/favicon assets. No separate Mitra persona.
- App launch restores the account but starts a fresh local chat draft. A conversation is created only when sending the first message. Old history is accessible through a searchable drawer.
- Keyboard-aware composer and settings editor on Android/iOS, safe-area offsets, scrolling content, named 44 px controls, and native back navigation.
- A stable client UUID identifies each turn. PostgreSQL stores processing/completed/failed states. Re-sending a completed ID returns its saved reply. Retrying a failed ID generates a reply for that same question; no duplicate user bubble.
- Lost responses reconcile with saved history. Processing older than 120 seconds becomes failed/retryable. No background worker or jobs table is introduced. The API request owns generation, with a 90-second overall deadline.
- Failed messages have Retry and Remove. Removal erases content and leaves a content-free tombstone so the last imported legacy failed message cannot reappear. Legacy ADK events are imported lazily; successful exchanges alone enter new agent context.
- A configured Gemini fallback is tried once on upstream 429/503. If both attempts fail, quota errors remain 429 with a retry message. `GEMINI_FALLBACK_MODEL` can be empty to disable fallback.
- Automatic memory saves select lasting, explicitly supported facts, preferences, long-term goals, or user-described recurring patterns. At most one new detail per successful turn, most turns none. Exact source evidence is required; duplication is checked. Failed turns never commit their staged memory changes. Private/disabled memory blocks retrieval and persistence.
- Users edit/delete memories and can turn memory off. Individual approval is removed. Existing suggestions remain editable/removable and become confirmed when edited.
- Six source-checked Gita verses supply original Sanskrit, our English/Hindi renderings, and source links. Verse cards appear in the reply where the model places a verified marker. Unsupported references are not invented. Broader scripture coverage remains future work.
- Saarthi speaks as an approachable spiritual teacher, with plain language, candid reflection, occasional gentle metaphor, and concrete next steps. It does not claim to know divine will or diagnose the user.
- Drawer/account sign-out, themed destructive confirmations, searchable memories, OTP resend countdown, network timeouts, and recoverable session-loading errors.

## Regression tests with actual PostgreSQL and ADK

Run from `backend` with the local database running:

```bash
uv run --locked python -m unittest discover -s tests -p test_product.py -v
```

No provider is mocked; this suite does not make model calls. It uses real PostgreSQL, real ADK tool/session contexts, and HTTP through FastAPI's ASGI application. Fixtures are disposable accounts, removed through the actual account-deletion endpoint.

The original nine checks cover completed-delivery idempotency and ownership, active processing conflicts, interrupted-job expiry/removal, legacy success/orphan import, last-orphan deletion, staged automatic memory and deduplication/correction, private/disabled memory, verified/unknown scripture, and OTP throttling/consumed-code behavior. A tenth check, added after the Listen failure below, verifies that the complete OpenAPI schema resolves, speech uses a JSON body, invalid speech text is rejected at `body.text`, and unauthenticated requests are rejected.

## Live Gemini suite

`backend/tests/live_product.py` performs actual HTTP, PostgreSQL, and Gemini calls. It requires development OTP delivery and two isolated API processes. Run a normal API on one port and a failure API with an intentionally nonexistent model on another:

```bash
# Terminal A, from backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8001

# Terminal B: a real provider rejection, not a mocked response
GEMINI_MODEL=gemini-saarthi-test-unavailable GEMINI_FALLBACK_MODEL= \
  uv run uvicorn app.main:app --host 127.0.0.1 --port 8002

# Terminal C
uv run python tests/live_product.py
```

The suite passed 15 checks: auth and ownership, original Sanskrit and translations in a real response, repeat-delivery idempotency, no overwriting a stable ID, automatic lasting-memory save, generation-failure persistence, no memory side effects from failure, successful retry without duplication, no temporary-emotion memory, cross-chat recall, private-chat isolation, persisted preferences, memory editing, and blank-memory validation.

The initial failure API used a name without `gemini-`, which ADK rejected locally. That did not verify an upstream outage. The final failure check used `gemini-saarthi-test-unavailable`: server logs confirmed `ClientError, upstream_status=404` from the actual Gemini API, returned as our friendly 502. The failed turn was saved without memories, retrying the same client ID through the working Gemini alias produced exactly one answer, and the disposable account was deleted. The command above uses this corrected provider-routed name.

During this session the configured `gemini-3.8-flash` produced both successful replies and upstream 503/429. To finish the suite without hammering the quota-limited model, a separate API on port 8003 used `GEMINI_MODEL=gemini-flash-lite-latest`, the fallback alias that passed a real availability check. Both memory and scripture tests used this real model. The older `gemini-2.5-flash` was listed in the catalog but rejected for this key; it is not the fallback default.

`--keep` retains only the first disposable account after a successful run for subsequent browser QA. Without it, all created accounts are deleted. With it, `/tmp/saarthi-test-cleanup.json` contains the local cleanup token (file mode 0600); never publish that file. Results without credentials go to `/tmp/saarthi-product-results.json`.

## Browser walkthrough and static checks

The Expo web build was tested against an isolated real API using agent-browser at phone viewports, with desktop/narrow checks. Walkthroughs covered email OTP, new-chat startup, history drawer, settings, source/translation controls, visible failed-message actions, retry success, memory editing, and sign-out. The retry button recovered a real saved provider failure: the failure controls disappeared and exactly one reply was added.

Keyboard focus restoration and Escape dismissal were checked on dialogs. Background controls are made inert/hidden while a web modal is open, body scrolling is restored, and the drawer's accessibility tree contains only its own controls. Radio selections expose actual checked state. Reduced-motion settings disable animated scrolling/drawer transitions.

The final nested-modal check found and fixed an inactive confirmation portal inheriting the drawer's `inert` state. A shared modal stack now enables only the top portal. Verified: opening a drawer deletion confirmation exposes only Cancel/Delete, initially focuses Cancel, Escape closes only that confirmation, focus returns to the originating delete button, and a second Escape closes the drawer and restores the main page.

All 22 reading-text contrast combinations across main, drawer, and scripture surfaces met 4.5:1. TypeScript, Python compilation, lockfile validation, and both Android and web Expo exports passed. The initial polish regression suite passed 9/9; the Listen regression brought it to 10/10, and the transcription validation regression brought it to 11/11. No new ADK database session is created for new conversations; ADK database tables are retained for importing/deleting older history.

A final real turn using the configured primary Gemini model on the latest backend returned 200. Replaying the same client ID returned the same reply with exactly one question and one answer in history. The final 390 × 844 browser layout had no horizontal overflow and kept the composer within the viewport.

Cleanup was verified through the real account-deletion endpoint: the retained integration-test account and browser-only account were removed, the retained token returned 401 afterwards, and no disposable product QA accounts remained. The temporary credential file was removed. The isolated QA browser/API/static-server processes were stopped; the user's development server was not touched.

## Device checks still needed

### Expo Go startup follow-up

After a reported spinner/generic Expo Go error, the running Metro status endpoint, Android manifest, and backend health were reachable at the laptop's Wi-Fi address. The mobile environment was still using the Android-emulator-only `10.0.2.2`; it was corrected to the current laptop LAN address. This is a confirmed API setup defect, but does not by itself explain a failure before Expo Go loads JavaScript.

Online Expo Doctor found three setup issues: SDK 57 no longer accepts `newArchEnabled` in app config, `expo-audio` required the direct `expo-asset` peer dependency, and TypeScript needed alignment to `~6.0.3`. All three were corrected using Expo's dependency installer. The `npm run doctor` command now runs the official checks; all 21 checks passed and TypeScript passed.

A separate clean LAN Metro instance was started with `--go --lan --clear`. Its Android SDK 57 manifest and exact development bundle returned 200 and included the corrected LAN API URL. This verifies bundler delivery from the laptop; it does not establish that the phone can reach the laptop or execute the native runtime. The README now includes a phone browser `/status` connectivity check and the official SDK-compatible Expo Go link.

The user then restarted Metro and confirmed that the app opens in Expo Go on the phone. The isolated verification server on port 8082 was stopped; the user's normal Metro/backend processes remain running. This confirms startup recovery, not the remaining keyboard/recording/playback device checklist.

The user subsequently identified the phone's active VPN as the QR-loading problem. The Expo dependency/configuration corrections and LAN API address fixed separate setup defects; they should not be presented as the proven cause of the QR-loading failure.

### Listen request regression and fix

An actual authenticated `POST /api/voice/speak` reproduced HTTP 422 with `loc: ["query", "payload"]`, although the app sent `{"text":"..."}` correctly. The earlier refactor removed the `TurnRequest` import still used in the speech route's postponed type annotation. The unresolved annotation made FastAPI infer a query parameter and also broke `/openapi.json` with HTTP 500. This was a backend regression, before any ElevenLabs call.

The route now imports a dedicated `SpeechRequest`: whitespace is stripped, empty text is rejected, and up to 10,000 characters are supported, matching the default Eleven Multilingual v2 limit. Speech and chat schemas are independent. OpenAPI now declares the JSON request and MP3 response. The previous 2,400-character speech limit was removed. Mobile voice requests allow 90 seconds, beyond the provider request's 75-second timeout, and voice validation errors are described as playback errors instead of a generic form error.

Verified against the actual running API and ElevenLabs, without mocks: OpenAPI returned 200; English speech returned 74,022 MP3 bytes; Hindi returned 106,623 bytes. `ffprobe` decoded both in memory as MP3 at 44,100 Hz. Missing, blank, and over-limit JSON were rejected with HTTP 422 at `body.text`; unauthenticated speech was rejected with 401. Disposable voice accounts were removed and no audio files were written. The updated regression suite passed 10/10; mobile TypeScript passed.

To inspect future failures, open the app, press `j` in Metro, select Network/Expo Network, and repeat Listen. Inspect the `/api/voice/speak` request payload and response. The development Console now also reports `[api]` method/route/status/duration and validation field metadata, omitting credentials and request bodies. The README describes this workflow and the distinction between phone-to-API calls and server-to-provider calls.

A browser phone viewport cannot verify the actual Android/iOS software keyboard, native microphone permissions, phone navigation bars, screen readers, or audio routing. On a device, check:

1. Long multiline text stays above the keyboard; Send and voice actions remain reachable.
2. Settings memory edit and OTP entry remain visible at large system text sizes.
3. Record, cancel, deny permission, finish, and transcribe. The transcript should append to the draft and require review before sending.
4. Listen/stop, change chat during playback, finish playback, and verify temporary playback files are removed.
5. Background/reopen during a pending reply, toggle airplane mode, reconnect, and retry. One question and at most one completed reply should remain.
6. Back closes settings/drawer. Sign-out leaves no visible account data.

No Android SDK/adb is installed in this environment. SMTP delivery was not exercised, and provider-level data retention is governed by the provider's terms. The app does not store server audio.


### Voice-note upload and playback cache follow-up (2026-10-03)

The Android upload initially failed in about 9 ms, before an HTTP response. Installed SDK 57 source revealed the cause: Expo fetch's multipart serializer rejects the old React Native `{uri, name, type}` FormData object. It accepts a Blob/File with byte access. `mobile/src/api.ts` now appends a real `expo-file-system` File on native and a Blob on web, and explicitly uses `expo/fetch`. Empty, missing, and over-12-MiB files are checked before upload. Recoverable request failures use development `console.info` rather than a blocking yellow LogBox warning.

Actual provider verification, without mocks: a disposable account requested English TTS, the MP3 was converted to AAC/M4A with ffmpeg pipes, and a 43,194-byte M4A was uploaded through authenticated multipart HTTP to the running API and ElevenLabs Scribe v2. The transcript was: “I am feeling worried about work today. I want to take one small calm step.” Audio stayed in memory; the account was deleted. The eleventh PostgreSQL/ASGI regression verifies authenticated multipart handling, required file validation, and empty-file rejection. All 11 regression tests passed. The user confirmed transcription reached the app, although their first attempt still failed.

The user then reported Listen failing with native `FileNotFoundException`/ENOENT while legacy `writeAsStringAsync` wrote `reply-*.mp3` into Expo Go's experience cache. This is a local filesystem error after audio generation, not evidence that the shlok or provider failed. Playback now uses `Directory(Paths.cache, "saarthi-playback")`, creates intermediate directories idempotently, and writes MP3 bytes with the current File API. Base64 conversion and the unused base64 dependency were removed.

Recording failures now retain the temporary voice note for explicit Retry/Discard. Success appends the transcript once to the existing draft, then deletes the note; discard and component unmount also clean up. While recording, preparing, or transcribing, playback controls are unmounted to release active audio. Single-flight guards prevent overlapping microphone/upload operations. Failed-note recovery blocks changing chats and sending until the note is resolved. A transcript that would exceed the 6,000-character draft limit is preserved for retry after shortening the draft. Readable messages replace raw native playback/recording exceptions; details remain in development logs.

After these changes, TypeScript passed and both Android and web exports passed to `/tmp/saarthi-voice-recovery-export`. These checks establish type and bundle correctness, not successful native playback. A local Android debugger target was visible, but a read-only `Runtime.evaluate` attempt returned protocol `-32601`; no cache operation was executed. Do not describe this as a passed phone filesystem test.

The user will check in a later session. Remaining device checks: reload Expo Go and Listen to the same shlok reply; stop/finish/change chat during playback; record and finish a fresh note; cause a real network failure, restore connectivity and Retry the retained note (one transcript); Discard another failed note; double-tap Finish/Retry; deny microphone permission; record then Listen and Listen then record. Record exact HTTP status/duration and native error separately if something fails. See [Agent handoff](agent-handoff.md) for continuation instructions.
