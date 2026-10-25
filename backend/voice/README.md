# Browser voice

Local, hands-free voice using WebRTC, Pipecat, Deepgram Nova-3 multilingual,
Saarthi's existing ADK agent and Cartesia Sonic-3 (Rohan). Expo/mobile is outside this module.

## Run

From `backend/`:

```sh
uv sync --locked --extra voice
uv run alembic upgrade head
# Set these in backend/.env (see .env.example):
# VOICE_ENABLED=true
# DEEPGRAM_API_KEY=...
# CARTESIA_API_KEY=...
# CARTESIA_VOICE_ID=4877b818-c7fe-4c89-b1cf-eadf8e23da72 # optional; Rohan is the default
# OPENROUTER_API_KEY=...
uv run uvicorn main:app --host 127.0.0.1 --port 8000
```

Open `http://localhost:8000`, sign in, start/resume a chat, then **Start voice**.
Allow microphone access. If playback is blocked, use **Play audio**. **Leave voice**
restores typing; it does not end the conversation. **Stop speaking** cancels the
current reply while the microphone stays live. **Mute microphone** is explicit.
Voice defaults off and returns an actionable error when keys or the voice ID are
missing. The default voice is Rohan - Steady Communicator (Hindi), verified via
Cartesia's voices API. Murf's adapter and settings remain available in the codebase.

Use one Uvicorn worker for this local release. Database leases prevent duplicate
owners across workers, but live signaling requires the owning process. Local
WebRTC uses host ICE candidates without STUN/TURN. Public/mobile deployment needs
its own media routing and authentication work; changing the reverse proxy is
insufficient. Python 3.12 is the tested voice runtime. Text-only installs retain
Python 3.11+ support and do not import the optional media dependencies.

## Components

- `routes.py`: authenticated start/stop, SDP offer; same-origin cookie boundary.
- `store.py`: PostgreSQL ownership and delivered-text transactions.
- `pipeline.py`: Silero VAD, Smart Turn v3.2, STT, interruption policy, output fencing.
- `session.py`: one reply at a time, cancellation, delivery, retries and cleanup.
- `deepgram.py`: bounded recovery replacing the adapter's unlimited loop.
- `cartesia.py`: active streaming adapter with word end timings, bounded audio
  lead, generation fences and coordinated turn retries.
- `murf.py`: retained Murf adapter; not used by the active pipeline.
- `policy.py`: acknowledgment normalization and conservative original-text prefixes.
- `client/voice.js`: microphone, WebRTC, playback, captions, reconnect and teardown.

STT receives Hindi/English code-switching audio. Agent output and captions use Devanagari for Hindi words
and Latin script for English words, following the shared Saarthi prompt. Smart Turn is the completion authority;
Deepgram endpointing is disabled. VAD starts a candidate interruption. Recognized
speech other than a standalone acknowledgment cancels immediately; continuing
unrecognized speech cancels after 1.2s. Short `haan/hmm/achha` during output is
suppressed; `haan lekin...` interrupts. The same acknowledgment while listening is
a real user answer. This rule needs listening tests for prosody and background voices.

Operational invitations/check-ins are assistant messages with `kind=voice_notice`.
They use delivery tracking and reach later agent/Doval context without violating
the single opening constraint. Reusing an already-visible text greeting does not
create or rewrite that message. New voice replies save only delivered text;
checkpoints every 2s reduce loss after a process crash. No empty assistant messages
are created when nothing was delivered. Completed text-only messages are unchanged.

## Recovery and limits

Browser reconnection uses up to three exponential delays near 1/2/4s with jitter,
creates a fresh fenced media session, and suppresses another greeting. STT also
has three bounded recovery attempts over its live connection; speech lost during
a gap must be repeated. LLM/TTS recovery has three retries and a 120s total turn
budget. Missing credentials/invalid input and non-transient errors stop retries.
Provider/account errors whose classification is unknown fail conservatively.
Server responses do not currently parse provider `Retry-After` headers.

A reliable generated reply retries TTS from its estimated unplayed suffix. If model
generation failed, regeneration receives the played prefix and a continuation
instruction. New user speech, Stop speaking, Leave, logout and shutdown cancel the
pending attempt/backoff. Retries share the same user-message ID. There is no
promise of deterministic model continuation or zero repeated/omitted boundary words.

Ownership renews every 2s, expires after 30s, and fences late writes. A failed worker
therefore releases ownership after at most 30s; a new owner cannot be cleared by
an old session. A connection that never becomes ready closes after 20s. Defaults:
one check-in after 30s silence, disconnect after 120s silence, hard safety cap 20min.
The usual 5–10min call is not a hard cutoff. These are tuning defaults, not measured
latency promises. At most 10 sessions per worker are allowed.

Cartesia's generated audio lead is bounded to roughly 5s plus the provider's current
WebSocket frame/queue. Each synthesis attempt is capped at 120s of audio. Incoming
Smart Turn audio is bounded by the framework's eight-second rolling window.
No audio is saved to disk or database, including debug recordings. The application
disables provider/framework Loguru namespaces and rejects Smart Turn audio logging.
Provider retention policies are separate; Deepgram model-improvement opt-out is
requested, which is not a zero-retention guarantee.

Delivery uses Cartesia word end times against audio sent at real-time pace with a
350ms margin. Normalization mismatch (e.g. `50` vs `fifty`) freezes alignment at the
last matching prefix. Missing timestamps may yield no partial transcript. Successful
full playback commits the complete reply. Browser mute/jitter/route changes mean
this remains an estimate; it cannot establish what a human actually heard.
The browser mutes the old jitter tail while the server flushes TTS/output queues.

## Verify

```sh
TEST_DATABASE_URL=postgresql+psycopg://saarthi:saarthi@localhost:5432/saarthi uv run --extra voice pytest -q
uv run ruff check .
uv run ruff format --check .
node --check ../client/voice.js
node --test ../client/tests/*.test.cjs
```

Tests include ownership/lease expiry, late writes, interrupted context, checkpoints,
notice messages, cancellation during backoff, acknowledgment rules, word timings,
ADK streaming and synthetic WebRTC audio between two peers. Browser QA uses a fake
microphone and fake provider boundaries; it is not a real-provider/acoustic test.

Before calling speakerphone support accepted, manually test Hindi, English and
mixed Hinglish with the Rohan voice; unfinished thoughts and short answers;
`hmm` vs `ruko` vs `haan lekin`; loud output with no speech (no self-trigger); actual
speech over output at different volumes/distances; mute/unmute; Wi-Fi loss; Leave
while connecting/retrying/speaking; a second tab; account expiration and reconnect.
Check Chrome's displayed capture settings. AEC being enabled does not prove echo
is controlled. No microphone recordings should be enabled for this work.
