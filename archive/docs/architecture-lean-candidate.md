# Current lean architecture

Updated 2026-10-04. The filename retains the original proposal's name; this document
now describes implemented boundaries. The [earlier lean proposal](history/lean-architecture-2026-10-03.md)
and [larger v1 proposal](architecture-v1.md) are historical designs.

## Components

Expo React Native/web owns the temple call scene, Type and the drawer. FastAPI owns
auth, account/conversation ownership, preferences, durable turns, room dispatch,
memory policy and deletion. One named Python LiveKit worker handles calls. PostgreSQL
stores continuity; the LLM does not run between visits.

Typed turns select either an OpenRouter tool loop or Google ADK/Gemini. Both share
persona, verified scripture and evidence rules. Voice independently selects STT,
LLM and TTS through `providers.py`. The current preset is ElevenLabs Scribe →
OpenRouter Flash Lite → ElevenLabs Multilingual v2/George. Deepgram/Murf and Gemini
are configurable alternatives. No separate vector service, task queue or audio store.

## Data and delivery

| App table | Responsibility |
| --- | --- |
| users | Identity, language and memory preference |
| auth_codes | Hashed expiring email codes and attempt/consumption state |
| conversations | Owned title, privacy flag and timestamps |
| chat_turns | Canonical stable-ID typed delivery, response, failure and discarded tombstones |
| memories | Owned selective lasting facts, source/evidence, status and optional embedding |
| voice_sessions | Stable-ID room lifecycle, worker/opening claims, deadlines and cleanup |
| voice_messages | Finalized user/assistant transcripts and interruption metadata |

Legacy ADK database tables support old history import/deletion. They are not the
canonical store for new turns. Memory uses bounded owner-scoped text ranking;
pgvector columns do not imply active semantic search. Optional OpenAI embeddings
are independent of the answer provider. SQLAlchemy `create_all` is currently the
additive local bootstrap; versioned schema migrations remain work for deployment.

Typed retries reuse the client UUID. Successful replay returns the stored answer;
changed text under the same ID is rejected. A 120-second lease detects abandoned
processing, and generation has a 90-second deadline. Successful history alone feeds
future context. Eligible typed memory commits with a successful response.

Call start uses a stable UUID, user-row locking, explicit dispatch and one active
session per account. Room tokens publish microphone and permit readiness data.
End marks closing before room deletion; late writes are denied and failed cleanup
blocks the next call until retried. Current call defaults: 15 minutes total, two
minutes idle, 60 seconds abandoned connection, 30 seconds client readiness.

## Context and tools

`continuity.py` supplies bounded permitted recent chats/memories and elapsed time.
The LLM chooses a contextual opening or general greeting. The worker refreshes
current privacy/language and the copied turn context before each user turn. Voice
memory tools require a trusted current user transcript ID and exact quote, and
commit immediately if accepted. Typed tools stage their changes until success.

Private mode/memory off prevents cross-chat context and new saves but retains the
current chat. Delete a chat to remove source messages and associated memories;
deleting only memory does not erase source text. The six verified Gita verses are
2.14, 2.47, 2.48, 6.5, 6.26 and 12.13. Broader scripture retrieval is not implemented.

## Client and security boundaries

The call controller owns media resources and cancellation across permission, HTTP,
connection, bell, readiness and cleanup. Platform adapters implement web/native
LiveKit transport. Captions/states come from media events. End on background is
intentional; lock-screen calls are future work. Expo Go supports Type, while live
native calls need a development build with WebRTC modules.

SMTP email OTP and signed bearer tokens are first-party. Native tokens use SecureStore;
web uses sessionStorage. Development can return an OTP when SMTP is absent;
production requires SMTP and a strong secret. LiveKit/provider keys stay server-side.
App audio is not recorded; transcripts persist. Provider retention remains separate.

Current limits and the remaining Hindi/device quality work are in [the handoff](agent-handoff.md).
Use [live setup](live-voice.md), [testing](api-e2e-testing.md) and
[debugging gotchas](voice-debugging-gotchas.md) before changing these boundaries.
