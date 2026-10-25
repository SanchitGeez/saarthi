# Saarthi voice architecture — working design

Updated: 2026-10-20. Status: browser voice implementation on `feat/voice-module`;
provider/acoustic acceptance testing remains open.
Voice interruption fix: [cause, changes and manual acceptance checks](voice-pipeline-bug-2026-10-25.md)
(implemented 2026-10-25; real microphone acceptance pending).
This is the maintained voice design. Update decisions and unresolved questions as
the discussion progresses. Recommendations below are proposals, not approvals.
The existing v2 spec describes the text application. The implementation record
below supersedes earlier proposals where they differ.


## TTS provider switch (2026-10-25)

The active pipeline now uses Cartesia Sonic-3 with Rohan - Steady Communicator
(`4877b818-c7fe-4c89-b1cf-eadf8e23da72`), verified through the voices API.
`backend/voice/cartesia.py` preserves word end timing, generation fences, bounded
audio lead and session-owned retries. Set `CARTESIA_API_KEY`; the Rohan voice ID
is the default. Murf's module, settings and dependency remain intact. Earlier
Murf-specific implementation details below describe the prior provider.

## Implementation record (2026-10-20)

The user authorized end-to-end implementation in a separate branch/worktree and a
pull request. The implementation is in `backend/voice/`; browser media controls are
in `client/voice.js`. See `../backend/voice/README.md` for exact setup and limits.
No changes from the original checkout's uncommitted agent/evaluation work were
included. The committed existing Saarthi prompt/agent module is reused.

Implemented decisions:

- Optional, pinned Pipecat 0.0.108 + Murf adapter 0.2.6; tested Python 3.12.
- SmallWebRTC on localhost, authenticated HTTP signaling and data-channel events.
  One worker for local use; durable PostgreSQL ownership still prevents overlap.
- Deepgram Nova-3 `multi`, Silero VAD, bundled Smart Turn v3.2 completion authority.
  Provider endpointing is disabled. Smart Turn protects unfinished speech with a
  2.5s upper silence bound; complete-turn latency depends on detection/STT.
- Custom whole-utterance acknowledgment policy; recognized substantive speech
  interrupts, and 1.2s continuing unrecognized speech provides a bounded fallback.
- Streaming ADK through the existing Saarthi prompt and model configuration.
  Cancel + generation fences + provider clear + media queue clear + browser mute.
- Murf token streaming, one context per response, word timing adapter, bounded
  synthesized lead, conservative original-text prefix persistence every 2s and at
  cancellation. `Message.delivery_status` records interrupted/complete output.
- `Message.kind=voice_notice` allows delivered operational invitations/check-ins
  without violating the unique text greeting. They reach canonical agent and
  Doval context. No empty assistant rows; already-visible text greetings remain.
- 30s ownership lease renewed every 2s; cross-tab text/End conflicts are rejected;
  logout/shutdown clean up. Another worker detects revocation at renewal.
- Bounded exponential recovery for browser, STT and turn output; no adapter-owned
  unlimited loop. Unknown provider failures fail conservatively. `Retry-After`
  parsing is not implemented. LLM continuation and partial TTS use delivered context.
- Defaults: check-in at 30s silence, idle leave at 120s, hard safety cap 20min,
  abandoned connection cap 20s, at most ten sessions per worker. These defaults
  are tuning choices, not new user requirements or measured latency guarantees.
- No stored audio/debug recordings. Provider retention is independently unverified.
  Murf voice ID must be selected/configured; no voice persona was assumed.

Validation includes PostgreSQL regression/migration tests, delivery/retry tests,
synthetic WebRTC exchange and a Chromium browser session with simulated capture
and fake providers. Real Deepgram/Murf/OpenRouter voice calls, Hindi/Hinglish
pronunciation, actual laptop speakerphone echo and physical interruptions remain
acceptance gates. Public ICE/TURN deployment and Expo are outside this first scope.
Playback estimates may under-count text or omit/repeat words at recovery cutoffs.
A process crash can lose progress since the latest two-second checkpoint.

Earlier sections below retain the discovery rationale and proposed alternatives.
They should not be read as claims that every explored alternative was implemented.

## Confirmed requirements

- Introduce a distinct voice module using Pipecat for pipeline orchestration,
  Deepgram for STT, Murf for TTS, and the existing agent module for replies.
- Browser testing client first. Mobile implementation is outside the first scope.
- Hands-free conversation. The user can speak to interrupt Saarthi.
- Hindi, English and Hinglish, including switching languages within a sentence.
- Explicitly evaluate WebSocket versus WebRTC.
- Develop the architecture collaboratively before implementation.
- First testing environment: user's laptop only.
- Protect unfinished thoughts without a fixed two-second wait before every reply.
  User considers two seconds long; actual completion strategy/timing needs tuning.
- Short acknowledgments such as “hmm/haan/achha” should ideally not interrupt.
- Agent context should ideally contain only the played portion of a voice reply.
  Conservative played-text estimates are accepted for the initial version.
- Leaving voice keeps the chat active. Leave voice before sending typed messages.
- After unanswered silence, one gentle check-in is accepted; then remain silent
  until an idle limit. Exact check-in and idle durations remain open.
- Brief overlap while distinguishing acknowledgment from interruption is accepted.
- Laptop speakers must work from day one; headphones are not a prerequisite.
  The eventual mobile experience should resemble a speakerphone conversation.
  This states interaction intent, not a requirement for telephony/PSTN integration.

- Saarthi speaks first when voice connects. On entry from an ongoing text chat,
  use a brief invitation rather than reading the previous reply aloud.
- Automatically reconnect after a network drop, show reconnection status, and do
  not produce a fresh greeting on reconnect.
- Expected voice session length: 5–10 minutes. This is not a confirmed hard cutoff.
- Assistant captions use agent output directly, preferably Romanized Hinglish.
  No translation/transliteration stage. STT transcript script is a separate concern.
- No stored audio, including debug recordings. Only bounded transient audio
  buffers are allowed; discard them after processing/playback/cancellation.
  Provider retention must be verified separately.
- Interrupted replies show only the conservative played prefix, marked Interrupted,
  in both visible chat and subsequent agent context.
- Automatically retry transient failures with exponential backoff. Retry caps,
  delay values and recovery behavior at uncertain playback boundaries are design
  details below; they have not been explicitly selected by the user.

## Current application and consequences

- One FastAPI application and PostgreSQL; agents accept plain payloads and do not
  import persistence or HTTP. Preserve this separation.
- `backend/agents/runner.py:invoke` iterates ADK events but returns only the complete
  final response. It does not currently expose a token stream to callers.
- `backend/agents/saarthi.py:reply` uses that runner; its prompt defaults to Hindi
  in Roman letters. Spoken Hindi script and pronunciation need separate evaluation.
- `backend/core/service.py:generate` builds canonical context, persists the user
  message, claims generation, invokes Saarthi, then saves one complete reply.
- Generation failure blocks a new message until retry; this is unsuitable as the
  default treatment of intentional voice interruption.
- Conversation claims fence late writes, but voice playback can outlive model
  generation. Voice needs ownership spanning generation AND playback.
- Message constraints allow one assistant reply per user message and one opening.
  Doval receives the stored transcript when a conversation ends.
- There are already unrelated uncommitted changes. This design adds documentation
  only and does not alter those changes.

Archived voice notes are historical evidence, not current architecture. Preserve
their lessons as test cases: Hindi script affects pronunciation, Murf model/voice
eligibility differs, microphone permissions require suitable browser origins,
stale callbacks can resurrect closed sessions, and speakerphone echo needs tests.
See `../archive/docs/voice-debugging-gotchas.md`.

## Proposed boundary and pipeline

Start with a module in the existing backend, one live pipeline per voice session.
Process isolation remains conditional on dependency compatibility and measured
CPU/load; a separate service is not yet a requirement.

```text
Browser mic <========== WebRTC audio ==========> voice module
Browser UI <---- authenticated control/events -----> voice module
                                                      |
                          audio -> Deepgram streaming STT
                                      |
                           accepted user turn / transcript
                                      |
                      core: ownership, context, turn persistence
                                      |
                         existing Saarthi agent (streaming)
                                      |
                            bounded streaming text
                                      |
                              Murf streaming TTS
                                      |
                              browser audio playback

Speech start ---> interruption handling ---> cancel + clear old audio
Playback progress ------------------------> delivery metadata
PostgreSQL <-------------------------------> core
```

The voice module owns live audio, provider connections, Pipecat processors,
turn timing, cancellation and session cleanup. Core owns canonical conversation
state, context assembly, authorization, persistence and extraction. The agent owns
response behavior. Pipecat's transient aggregation must not become a second,
independently managed conversation history.

Candidate files, not a committed scaffold:

- `backend/voice/routes.py`: authenticated start/stop and WebRTC signaling.
- `backend/voice/session.py`: session lifecycle, ownership and cleanup.
- `backend/voice/pipeline.py`: Pipecat wiring and turn strategies.
- `backend/voice/agent.py`: thin Pipecat processor invoking the agent stream.
- Existing core service: shared context and claim/commit/cancel operations.
- Existing agents: streaming API sharing prompt, model and failure handling.
- Browser client: permissions, connect, captions, mute, stop and playback events.

## Transport recommendation: WebRTC for browser audio

WebRTC and WebSocket are choices per connection, not for the entire system.
Recommend browser-to-backend WebRTC; provider connections can use WebSockets.
Use existing authenticated HTTP for session lifecycle and signaling where possible.
Use Pipecat client events/data channel where supported; add a separate control
WebSocket only if an actual need remains.

WebRTC provides media timing, jitter handling and network adaptation. Browser
microphone constraints can request echo cancellation, noise suppression and gain
control; these require real-device verification and are not guaranteed by choosing
WebRTC alone. WebSocket offers familiar server deployment but ordered reliable
delivery can hold newer audio behind lost packets; custom browser audio framing,
buffering, playback and cancellation add implementation work.

For local development, evaluate SmallWebRTC first. Public testing also requires
HTTPS, reachable signaling/media endpoints and an ICE/STUN/TURN plan. TURN may
relay media when a direct route is unavailable. HTTPS reverse proxying alone does
not establish a working WebRTC media route. Managed media is a later option if
deployment, geography or reliability makes self-hosting costly.

Do not implement both browser audio transports in v1. Revisit WebSocket audio if
the intended network demonstrably blocks WebRTC and TURN cannot solve it.

## Turn-taking: three separate decisions

1. VAD (voice activity detection): does incoming audio contain speech?
2. Turn completion: has the user finished their thought, rather than paused?
3. Interruption policy: should that speech stop Saarthi's current output?

VAD alone cannot reliably answer the other two. A reflective companion should
leave room for pauses. Deepgram finalized transcript segments are not necessarily
completed conversational turns; do not invoke the agent once per final segment.

Evaluate one completion authority at a time:

- Deepgram Nova multilingual STT plus Pipecat VAD/turn strategy.
- Deepgram Flux multilingual with its turn events, if the selected Pipecat
  integration/version supports the required multilingual behavior.

Model names and language support must be verified against current docs and then
tested on actual Hinglish. Do not stack provider endpointing, independent silence
timers and smart-turn decisions without defining which event commits the turn.
Reuse Pipecat's supported strategies. Add semantic completion only if observations
show simpler completion is cutting off users. Exact timeouts remain undecided.

User clarified that protecting pauses must not mean routinely waiting two seconds.
Prefer completion-aware timing: a finished question can close sooner; “aaj office
mein...” should get room to continue. This is a behavior target, not a guarantee
that a model can always identify incomplete Hinglish. Evaluate the supported smart
turn/provider completion strategy in the first listening spike rather than
committing to a silence-only implementation. No extra general-purpose LLM call on
every pause unless evidence justifies its latency and cost.

Initial tuning hypotheses, NOT accepted settings or latency promises: evaluate a
roughly 600–900 ms completion window for apparently finished speech and a bounded
longer wait for unfinished speech. Account for STT finalization and the selected
strategy's actual timing; do not blindly add these values as another timer. Tune
against complete questions, hesitation, mid-sentence pauses and short answers.
Speech resumption invalidates the pending completion decision. Separate user
pause handling from waiting for an answer to Saarthi's own question.

Saarthi speaks first once playback and the session are ready. Existing chat startup
already generates an opening: reuse it for a new conversation when applicable
rather than generating two greetings. On voice entry from an ongoing text chat,
speak a brief invitation such as “Haan, bolo...” rather than replaying the previous
assistant response. Apply delivery tracking to the invitation without creating a
second conversation-opening message (the schema has a unique opening constraint).
Duplicate readiness events must not replay startup speech. Automatic reconnect
does not greet again (confirmed).

## Interruption and delivery correctness

Proposed baseline: meaningful new speech stops the current response and the next
accepted turn gets a fresh reply. No automatic continuation of the old response.
Short “hmm”, “haan” and “achha” should ideally not count as interruptions.
A minimum-word rule can delay or miss short “stop”/“nahi” interruptions; raw VAD
can stop output for background voices. This needs listening tests, not one magic
threshold. Capture incoming audio continuously so initial interrupting words survive.

Accepted direction: briefly overlap output while identifying acknowledgment versus
interruption. The following concrete policy is proposed, applied only while
Saarthi is responding:

- VAD starts a candidate interruption; it does not immediately cancel output.
- Keep listening/transcribing while existing output continues through a short,
  bounded classification window. Timing must be measured, not presented as a
  guaranteed response time.
- A small normalized Hindi/English acknowledgment set suppresses cancellation
  only for brief standalone acknowledgments. Handle both Devanagari and Roman
  forms. Do not drop a whole transcript merely because it starts with “haan”.
- Explicit commands/corrections (“stop”, “ruko”, “nahi”, “wait”) or other recognized
  speech confirm interruption as early as usable STT allows; do not wait for the
  user's whole turn to finish. Continued/unrecognized speech has a bounded
  fallback to interruption so an STT failure cannot make Saarthi talk indefinitely.
- If acknowledgment expands into “haan, lekin meri baat...”, retain the full
  incoming speech and promote it to an interruption. Suppressed acknowledgments
  alone should not trigger another agent reply.
- When Saarthi is listening rather than responding, “haan” may answer its question
  and must be accepted as a normal user turn.

This is proposed app policy built on supported Pipecat start strategies, not a
verified built-in Hinglish acknowledgment feature. Waiting for recognition means
a real interruption briefly overlaps output. Prosody and context can make “achha?”
a question; rules will be imperfect. Start with explicit behavior and a Stop button;
add a classifier only if observed behavior justifies it.

On interruption:

1. Invalidate the current response generation ID immediately.
2. Stop/clear browser playback and server output queues.
3. Cancel agent generation and TTS work where supported; discard all late output
   from the invalidated generation even if a provider cannot cancel upstream work.
4. Record delivery state, release the old turn's claim safely and collect the
   user's complete new turn before generating again.

Stopping provider synthesis is insufficient: already buffered browser audio may
continue. A generation ID must accompany chunks/events, and a stale playback event
must never complete or mutate a newer response.

Distinguish generated text, synthesized audio, sent audio and reported playback.
Playback acknowledgment estimates delivery; it does not prove human attention.
Do not feed unplayed text into the next agent turn as if it was heard. A practical
baseline is generation IDs with playback progress, keeping the confirmed prefix and
marking the interrupted boundary uncertain.
Confirmed: chat shows only that prefix, marked Interrupted; remove any provisional
caption suffix that was not played. If nothing played, show a status/event rather
than inventing an empty assistant message (current schema requires nonempty text).

Updated delivery proposal after documentation review:

- Murf Falcon documents optional word timing metadata. Evaluate whether the chosen
  Murf/Pipecat version exposes it through Pipecat's timed-text aggregation path.
  Prefer that existing mechanism over a separate alignment model.
- Track one monotonic playback cursor per response and retain completed words up
  to its conservative cutoff. Keep generated output provisional until delivery is
  reconciled; then build the next agent context from the delivered prefix plus an
  explicit interruption marker, not the full generated reply.
- A server audio clock estimates output, not browser playout. WebRTC remote audio
  does not automatically give application-level per-word playback acknowledgments.
  Verify transport behavior and browser progress mapping in the spike. A custom
  PCM player/AudioWorklet is not an assumed v1 requirement.
- If reliable browser progress is unavailable, use supported transport timing with
  a conservative margin, or retain only fully confirmed phrase boundaries. Label
  that result estimated; do not promise exact heard-word history. Conservative
  omission may lose a partly played phrase, including a meaningful correction.
- On disconnect, use the last reliable cursor; never assume all sent audio played.
  Do not synthesize again just to recover timing. Map normalized spoken words back
  to text carefully, especially for numbers and mixed-script Hindi.

The candidate state is small (response ID, provisional text, timing metadata,
playback cursor, delivery status). Accurate WebRTC playout mapping is the main
uncertainty. Exact alignment is conditional on supported integration, not a custom
alignment project committed for v1.

Persistence schema remains OPEN. Voice likely needs durable session/turn delivery
metadata and explicit canceled/interrupted states. Reuse messages for canonical
text, but do not overload a normal completed message with undocumented semantics.
Resolve schema and core retry changes before implementation. Doval's snapshot must
understand partial delivery and never treat generated advice as user evidence.

## Lifecycle and concurrency

Session states: connecting -> listening <-> responding -> closing -> closed.
Track capture, generation and playback separately: the user may start speaking
while a reply is being generated or played.

Proposals: one voice session per conversation, one response generation at a time,
and block typed sends during voice in v1 (confirmed: leave voice before typing).
Confirmed: leaving voice keeps chat active;
explicit End conversation freezes history and invokes Doval.

After an unanswered question, permit one brief, gentle check-in, then wait silently.
Do not nudge while the user is speaking, while a turn is awaiting completion, or
while a response is generating/playing. Track the check-in per unanswered exchange
so idle timers cannot repeatedly restart it. A spoken check-in is assistant output
and follows the same interruption/delivery rules as other replies. Exact wording,
delay, idle disconnect duration and whether to skip it for intentional quiet are
not yet selected. Idle disconnect leaves the underlying conversation active.

Start must be retry-safe. Stop must be idempotent and valid during permission
prompts, signaling and provider setup. Stop the local microphone immediately on
exit. Disconnect, logout, session expiry and process shutdown must terminate
provider work and release ownership. Reject late writes after conversation End.
Bound queues and idle/session duration; reconnect must not replay old speech or
duplicate a greeting. Durable fencing is needed before multiple workers/replicas;
an in-memory registry alone cannot enforce cross-process ownership.

Expected session length is 5–10 minutes, not a requirement to stop at minute ten.
Hard duration/usage caps and exact idle timeouts remain open; implement explicit
resource limits before public use. First scope is a single local laptop session.

Reconnect automatically with visible status and bounded attempts (retry budget
still proposed). Revalidate identity/conversation ownership. Do not infer safe
turn resumption from media reconnection: reconcile the current generation and
last reliable playback cursor, fence old output and never replay unconfirmed
audio or an old greeting automatically. A fresh peer connection must still belong
to the same logical session or explicitly supersede it. If recovery cannot be
completed, stop capture/clean up and offer manual retry while preserving chat.
Recovery behavior for speech lost during disconnection remains a product choice;
do not imply that disconnected speech was received or persist it without evidence.

## Automatic retry and recovery

Confirmed: transient failures should retry automatically with exponential backoff.
The following recovery rules are proposed to make retries fit live conversation:

- One session/turn recovery coordinator owns the retry budget; avoid multiplying
  Pipecat/provider/SDK retries. Add jitter (small random delay) to exponential
  backoff. Respect retry-after hints within the total recovery deadline.
- Retry transient network failures, eligible rate limits and temporary provider
  failures. Credential, billing/quota-exhaustion, invalid-request and permission
  failures go directly to a visible actionable error rather than repeated calls.
- Candidate initial schedule: up to three retries after about 1, 2 and 4 seconds,
  with jitter and a total recovery deadline including request time. Exact deadline
  and retry parameters remain tuning proposals, not accepted requirements.
- Keep the logical user-turn ID stable across attempts; each attempt has a new
  generation ID. Fence late output from previous attempts. Retried persistence
  must not duplicate accepted user text, assistant messages or greetings.
- Before any output plays, retry the failed stage using accepted text/context.
  STT reconnection cannot recover discarded audio: tell the user to repeat speech
  that was not received. Do not add recording/replay infrastructure for retries.
- After partial playback, preserve delivered context. If full generated text and
  a sufficiently reliable cutoff are available, re-synthesize the unplayed suffix.
  Do not restart the entire reply. Temporary audio buffering may serve current
  playback but is not a retained audio cache.
- If generation failed mid-response, a replacement agent attempt should receive
  the delivered prefix plus explicit continuation instructions. It is a new
  generation, not a guaranteed deterministic resumption of the canceled model.
- If the cutoff cannot support clean continuation, visibly indicate recovery and
  use a brief repair/continuation grounded in confirmed context. Exact wording and
  acceptable repetition at an uncertain boundary need listening evaluation;
  zero repeated words cannot be promised with estimated playback.
- New user speech, Leave voice, End, logout or a superseding turn cancels old
  backoff/recovery. Speech remains eligible for interruption during retry waits;
  use the same acknowledgment policy. Never make the user wait for an old retry
  before handling their new turn.
- Show Reconnecting/Retrying while recovering. After the bounded budget expires,
  stop the failed voice attempt, release resources and offer manual retry/text;
  the underlying conversation stays active. No endless retry loop.

Test failure before first audio, midway through playback, during generation,
during backoff and after a new user turn, as well as simultaneous provider/media
failures. These are requirements for later implementation, not verified behavior.

## Speakerphone audio: required from the first slice

The microphone must remain live while Saarthi speaks so the user can interrupt.
Do not solve speaker echo by muting input during output. This requires usable
full-duplex audio: simultaneous capture and playback.

```text
Saarthi audio -> browser speakers -> room -> microphone
                                            |
                                acoustic echo cancellation
                                            |
                                VAD -> STT -> interruption policy

User speech --------------------> microphone (must survive echo cancellation)
```

Use browser/device acoustic echo cancellation (AEC) first, with supported noise
suppression and gain control evaluated in the same capture/playback path. Inspect
the local capture track's actual settings when available; requested constraints
alone do not establish that processing is enabled or effective. AEC is an audio
processing function; neither VAD nor an acknowledgment vocabulary replaces it.

Keep output in the supported WebRTC playback path. Do not add a separate custom
audio player until echo-reference and interruption behavior are verified. Start
with one named laptop browser as a test baseline (browser choice still open).

Required behavioral checks at comfortable and higher practical speaker volumes:

- Saarthi speaks while user is silent: no self-interruption, self-answer or new
  user turn caused by speaker leakage. Residual STT output must not become stored
  user evidence merely because STT produced text.
- User speaks over Saarthi: retain the beginning of the user's speech and stop
  old output after confirmed interruption. AEC must not erase the quieter speaker.
- Short acknowledgments over output do not cancel it; acknowledgments followed by
  a correction do cancel it. Repeated interruptions leave no old audio playing.
- Hindi/English/Hinglish, quiet and louder speech, different mic distances, a fan
  and ordinary room reflections. Expand the noise envelope based on actual use.

Log event timing and counts for false interruptions/missed interruptions, without
raw audio recording. Browser audio settings are diagnostic signals;
listening behavior is the acceptance evidence. Do not blindly discard transcripts
matching Saarthi's text: a user can deliberately repeat or question the same words.

Add external/server echo processing only if observed failures remain after proper
browser/device configuration. Future mobile work must verify native audio-session
mode, speaker routing, voice processing and route changes on physical phones;
passing laptop tests does not establish mobile speakerphone quality. Bluetooth,
background calling, locked-screen behavior and PSTN calling are not yet required.

## Language, latency, failures and cost

- Use agent text directly for assistant captions and initially for Murf synthesis.
  Test Romanized Hinglish pronunciation. If inadequate, propose a TTS-only script
  or pronunciation adjustment; do not silently change captions or add another LLM.
  Retest timing/text mapping if synthesis text differs from displayed text.
- Test mixed Hindi/English, names, Gita terms, numbers, corrections and long pauses.
  Sanskrit recitation is a separate requirement and currently unconfirmed.
- Stream agent text into one Murf turn context with bounded queues. Current Falcon
  guidance prefers provider-owned chunking; avoid an additional Pipecat sentence
  buffer unless testing requires it. Small WebSocket text frames are not separate
  synthesis contexts. Waiting for a complete agent reply delays first audio.
- Spoken content cannot be withdrawn. Preserve prompt safeguards and determine
  what validation can happen per chunk versus only on final output. Do not claim
  current final-response validation protects already played partial output.
- Measure speech end -> accepted turn -> first agent text -> first TTS audio ->
  first browser playback. Measure interruption onset -> playback stopped separately.
  Set targets after choosing a user experience; provider TTFB alone is insufficient.
- Timeouts/errors: distinguish thinking from failed STT/TTS and retry waits. Apply
  automatic bounded exponential retry as described above, preserving delivered
  text rather than restarting partly played replies. Surface speech lost during
  disconnection and provide manual recovery once the retry budget is exhausted.
- Keep API keys server-side; authorize signaling and session access against the
  existing identity and origin policy. Existing mock auth remains a prototype limit.
- Confirmed: no application audio storage or debug audio dumps. Exclude audio
  payloads from logs/error traces. Transcript retention and safe text traces remain
  open; provider retention requires separate verification.
- Cost model: connected/listening STT usage + TTS billable output + agent tokens +
  media relay/hosting. Include canceled work, idle sessions and account concurrency
  quotas. Budget per session/minute and hard limits remain open.

## Complexity and implementation gates

Build a small vertical slice with the hard correctness requirements intact:
one browser, one speaker, one provider per stage, WebRTC, supported turn strategies,
streaming existing agent, cancellation, delivery tracking, captions/mute/stop,
bounded resources and timing metrics.

Defer telephony, multi-party calls, background mobile calling, automatic provider
failover, speculative generation, custom VAD models, emotional voice inference,
audio recording and custom word-alignment infrastructure unless required. Evaluate
provider timestamps and existing framework delivery tracking first.

Gate 1: verify dependency compatibility and one real browser/provider audio loop
using laptop speakers. Establish both no self-triggering during output and usable
user interruption before treating this as a successful vertical slice.
Murf's published integration lists an older Pipecat dependency range; current
Pipecat turn docs describe 1.x. Verify actual package releases/source compatibility
in isolation before choosing pins. If incompatible, explicitly choose a supported
version set, a small Murf service adapter, or a separate voice runtime; do not
silently downgrade the application. ADK streaming/cancellation also needs a spike.

Gate 2: interruption, stale output fencing, persistence and retry semantics.
Gate 3: Hindi/Hinglish listening, pauses, background speech and speakerphone echo.
Gate 4: permission denial, stop-during-start, provider failure, disconnect/rejoin,
two tabs, session expiry, transcript limits and conversation End races.
Gate 5: real-network latency/cost evaluation before expanding beyond local use.
No duration estimate or reliability claim until these gates are understood.

## Discovery queue

Round 1 resolved: browser first, hands-free interruption, Hindi/English/Hinglish.

Round 2 resolved: laptop only, protect pauses, avoid acknowledgment interruptions,
aim for played-only agent context, leave voice without ending the chat.

Round 2 follow-up resolved: brief overlap accepted, conservative delivery estimates
accepted, laptop speakers required from day one; eventual phone speakerphone use.

Round 3 partial decisions: leave voice before typing; one gentle silence check-in
then silence until idle limit; protect unfinished thoughts without routinely
waiting two seconds; direct agent-output captions; no stored audio; Saarthi speaks
first; brief invitation on text-to-voice entry; automatic reconnect without greeting;
expected sessions 5–10 minutes. Exact timing and hard limits remain open.

Resolved: UI and agent context use the conservative played prefix; interrupted
replies are visibly marked. Automatic retries use exponential backoff. Fine-grained
recovery limits and continuation behavior remain proposals.

Round 3 — operating constraints:

- First scope is one local session with typical length 5–10 minutes. Hard duration
  cap, monthly/per-minute budget and eventual concurrency remain open; acceptable
  measured reply delay and interruption stop time need listening tests.
- Supported laptop browser; expected noise envelope beyond ordinary speaker use.
- Check-in/idle durations and reconnect retry budget.
- Voice choice/style, speaking rate and pronunciation expectations. Captions follow
  agent output directly, preferably Romanized Hinglish (confirmed).
- Transcript retention and text debug traces. Stored audio is disallowed.
- Retry deadline/caps and uncertain-boundary continuation behavior. Automatic
  exponential backoff itself is confirmed.

## Decision log

- 2026-10-20: user selected browser first, hands-free with speech interruption,
  Hindi/English/Hinglish. Stack choices supplied by user.
- 2026-10-20: user requested explicit WebSocket/WebRTC comparison. Proposed WebRTC
  for browser audio, provider WebSockets and HTTP signaling; awaiting scope details.
- 2026-10-20: user selected laptop testing, preserving thoughtful pauses, avoiding
  short acknowledgment interruptions, played-only context as the ideal, and keeping
  chat active on leaving voice. No precise acknowledgment/latency policy approved.
- 2026-10-20: reviewed Murf's timestamp/chunking documentation; superseded the
  unconditional Pipecat sentence-buffer proposal with provider-owned chunking.
  Browser playout mapping and selected plugin timestamp support remain unverified.
- 2026-10-20: user accepted brief overlap and conservative delivered-text estimates.
  Required laptop speakers from the first version, anticipating mobile speakerphone
  use. Added AEC and simultaneous user/output speech to the first acceptance gate.
- 2026-10-20: user confirmed leaving voice before typing and accepted the proposed
  single gentle check-in policy. Clarified that two seconds feels long while still
  wanting protection for unfinished thoughts; no numerical pause setting approved.

- 2026-10-20: user selected Saarthi speaking first, direct agent-output captions
  with Romanized Hinglish preference, and no stored audio. Added startup greeting
  deduplication and exact-text Murf pronunciation to the implementation checks.
- 2026-10-20: user accepted a short invitation on text-to-voice entry and automatic
  reconnect without another greeting. Typical session length 5–10 minutes; no hard
  ten-minute cutoff was requested. Added reconnect reconciliation requirements.

- 2026-10-20: user confirmed played-only visible interrupted replies and requested
  automatic exponential-backoff retries, superseding the manual-retry-first
  suggestion. Documented stage-aware recovery and proposed bounded retry behavior.

## References checked 2026-10-20

- [Pipecat transport guidance](https://docs.pipecat.ai/client/concepts/choosing-a-transport)
- [Pipecat turn strategies](https://docs.pipecat.ai/api-reference/server/utilities/turn-management/user-turn-strategies)
- [Deepgram final segments and endpointing](https://developers.deepgram.com/docs/understand-endpointing-interim-results)
- [Deepgram models and languages](https://developers.deepgram.com/docs/models-languages-overview/)
- [Murf Pipecat integration and published compatibility](https://murf.ai/api/docs/integrations/pipecat)
- [Murf WebSocket context IDs](https://murf.ai/api/docs/text-to-speech/web-sockets/context-id)
- [Murf timestamps and chunking](https://murf.ai/api/docs/text-to-speech/web-sockets/advanced-settings)
- [Browser echo cancellation constraints](https://developer.mozilla.org/en-US/docs/Web/API/MediaTrackConstraints/echoCancellation)
- [Actual capture track settings](https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrack/getSettings)

Documentation reviewed; no packages installed, provider calls made, account quotas
verified or physical-device behavior tested. Context7 is not available among the
session tools; official provider/framework documentation was used directly.
