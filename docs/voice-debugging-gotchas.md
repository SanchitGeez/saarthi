# Voice debugging learnings

Updated 2026-10-04. Read with [the handoff](agent-handoff.md) and
[live voice setup](live-voice.md). These are observed causes and implementation
constraints, not a claim that every device or Hindi conversation is reliable.

## Providers and Hindi

| Symptom | What we learned | Preserve / check |
| --- | --- | --- |
| Hindi turned into an unrelated language, including Russian | Unrestricted realtime Scribe detection chose badly | Hindi/auto/Hinglish preference hints Hindi plus English; English hints English plus Hindi |
| About 20 seconds before finalized transcript | Manual commit delayed finalization | ElevenLabs server VAD: `vad_silence_threshold_secs=0.8`, `min_silence_duration_ms=500`; one synthetic run improved to about 1.10 seconds |
| Delayed language metadata | Language reporting can delay delivery | `include_language_detection=False`; reported language follows primary hint, not a reliable code-switch classifier |
| Hindi pronunciation poor with Romanized words | Voice synthesis needs the right script as well as voice | Spoken Hindi parts use Devanagari; English parts English script. Type's Hinglish can stay Romanized |
| Native Hindi voice returns 402 `paid_plan_required` | New free account had credits but could not use library voices through API | User chose built-in George with Multilingual v2. Yash `XcVyMASZ3J9LrnSxDs2W` was added to the account but is not active. Paid access is needed for that library voice |
| Earlier ElevenLabs `insufficient_funds` / `quota_exceeded` | Billing exhaustion differs from voice plan eligibility | Read the actual status; don't hammer quota failures or assume a fresh key fixes plan restrictions |
| Murf voice rejected with 400 | Voice catalogs depend on model | Query `/v1/speech/voices?model=FALCON`; verified `en-IN-abhinav` supports Hindi/Indian English. Generic catalog's Gen2 `hi-IN-shaan` was not valid for this Falcon request |
| Provider status looks ready but real call fails | Status checks configured key presence | It does not certify funds, model/voice eligibility or upstream availability |
| Correct speech plumbing, poor advice | Cheap Flash Lite sometimes answered its own greeting, repeated the request or skipped memory | Evaluate semantic response quality separately. Lower temperature, explicit tools and Hindi memory examples improve prompting but do not prove adherence |

Both the live and recorded speech model settings matter: `VOICE_TTS_MODEL` and
`ELEVEN_LABS_TTS_MODEL`. Changing only one creates inconsistent experiences.
Restart API and worker after root `.env` edits; check exported environment overrides.
Selectors are explicit, not inferred from which keys happen to exist. No hidden
cross-vendor speech fallback. Multilingual v2 is the current quality-oriented choice;
Flash v2.5 is the cheaper/faster alternative. George's English accent remains possible.

## LiveKit and SDK boundaries

- The room token must enable data publishing for the readiness RPC, while publishing
  sources remain microphone-only. Disabling data caused the initial real handshake
  timeout. Two-minute token TTL and UUID-only dispatch metadata are intentional.
- Match explicit worker dispatch to `LIVEKIT_AGENT_NAME`. Duplicate workers with the
  same name can consume jobs with stale models/settings. Inspect process command and
  repository cwd before gracefully stopping a verified stale worker; don't kill unrelated calls.
- Claim the opening once after readiness; reconnect/duplicate RPC must not replay it.
  Let the LLM choose content. Skip the opening if the user already began speaking.
- LiveKit copies chat context before `on_user_turn_completed`. Updating only persistent
  instructions misses the current turn. Refresh its copied system message too, and
  attach the trusted current transcript ID. Regression coverage protects this behavior.
- `TurnHandlingOptions.preemptive_generation` expects `{"enabled": False}`, not a
  bare boolean. Speculation is disabled because the turn hook updates context and
  invalidates speculative work, wasting requests.
- Gemini's SDK needs at least a ten-second API deadline; an eight-second attempt
  caused SDK errors. Voice LLM attempts use 12 seconds with no automatic LLM retries.
  STT/TTS retry/timeout bounds and typed total deadlines are distinct.
- The production AgentServer default idle pool was excessive in this environment.
  Use the configured one idle process, prewarm imports/Silero and allow 30 seconds
  initialization. Download turn-detector/VAD models before testing.
- A LiveKit FFI destructor assertion can appear on synthetic client process exit
  after cleanup. Check test assertions, actual room deletion and exit status; don't
  dismiss a substantive call failure as destructor noise.

## Lifecycle, history and privacy

The client controller owns permissions, microphone, room, bell and pending server
cleanup. End can happen at any step. Stable session UUIDs permit cleanup after a lost
start response; generation guards ignore stale events. Local microphone shutdown
happens before waiting for server cleanup. Pending cleanup blocks another call.
Preserve these controls when simplifying the UI.

Typed and voice history merge by timestamp/ID. Finalized assistant playout transcripts
can be interrupted and are not proof the user heard the words. Voice evidence saves
are immediate upon accepted tool calls; typed evidence is staged until answer success.
Late writes after closing/deletion are refused.

Private/memory-off still preserves current conversation history. Deleting memory
alone does not erase its source chat. App audio is not recorded; vendor retention is
separate. ElevenLabs warned that the free account ignores `enable_logging=False`
zero-retention requests, which require eligible enterprise/trial access. Avoid stronger
privacy claims than the code and account contracts support.

## Expo and device failures

| Failure | Established fix / distinction |
| --- | --- |
| Native WebRTC unavailable in Expo Go | Use a native development build; Type works in Go. Prebuild/JS export does not verify an APK or phone audio |
| Phone browser cannot use mic on LAN HTTP | Browsers need localhost or HTTPS; API reachability alone does not grant microphone access |
| Old API URL after env change | Clear Metro/export cache after `EXPO_PUBLIC_API_URL` changes; use separate web/Android export directories |
| CORS fails despite similar-looking URL | Allow exact browser origin in `MOBILE_ORIGINS`; localhost and 127.0.0.1 are different origins |
| QR spinner | User confirmed a phone VPN problem. Check Metro `/status`, reachability and SDK independently |
| Upload fails before HTTP in about 9 ms | Expo serializer rejects `{uri,name,type}` native multipart parts. Use actual Expo File / web Blob with `expo/fetch`; validate exists/nonempty/12 MiB limit |
| Listen API returns 422 at query.payload | Dedicated imported `SpeechRequest` fixed the broken annotation/body contract. TTS accepts JSON text, not a query object |
| Listen MP3 200, then native ENOENT | Modern `Directory(Paths.cache, "saarthi-playback")`, intermediates/idempotent creation and byte writes replace legacy cache assumptions. Latest physical-device confirmation pending |
| Transcription fails once | Retain note in component memory for Retry/Discard, never auto-send or restore after relaunch. OS can evict cached files; missing/empty notes need a new recording |

Stop/cleanup playback on completion, error, unmount and recording; only one player
may be active. Keep single-flight guards on Finish/Retry/Listen. The shlok rendering
and cache/player path must be tested together on a real phone. Preserve the 6,000
character chat, 10,000 character speech and 12 MiB upload bounds.

Development API logs use `console.info` and omit tokens/bodies. Expo Network and SDK
debug logs can still contain stories or tokens; sanitize captures. A successful
`/voice/speak` followed by a native filesystem error belongs to the client player path,
not provider billing. The original intermittent transcription failure was not proven
to share the serializer cause: collect status, duration and native details if it recurs.

## Operational traps

Do not reset the user's PostgreSQL volume or touch the neighboring project's database.
`create_all` adds missing tables but does not migrate existing columns. Use disposable
accounts and cleanup through account deletion. Keep `.env`, provider audio, downloaded
models, temporary auth files and logs outside Git. Personal SSH solved the GitHub
account mismatch; no private-key copying or force pushing was needed.
