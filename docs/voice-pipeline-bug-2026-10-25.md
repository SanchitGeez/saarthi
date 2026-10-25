# Voice transcript loss during interruption

Reported and reproduced: 2026-10-25.
Status: **Fix implemented — real microphone acceptance pending.**
Severity: High. Before the fix, recognized speech could appear in the live UI
without reaching the accepted user turn, persistence, or the agent.

## Implemented fix

- Output clearing now sends `InterruptionFrame` downstream from `AgentOutput`.
  It clears synthesis/playback without cancelling input capture, STT, or turn
  detection.
- Final transcript segments enter the capture buffer before awaiting interruption.
- Speech onset cancels a pending response immediately when no audio has been sent.
  Resumed speech can then finish normally; previously saved fragments remain in
  the next agent request. Fragments can still appear as separate user messages.
- Acknowledgment suppression uses sent audio as the overlap signal, so speech
  during silent generation is not mistaken for an acknowledgment over output.
- Explicit interruption cleanup finishes even if its requester is cancelled,
  including a VAD fallback cancelled by a subsequent silence event.

Regression tests in `backend/tests/test_voice_capture.py` use real Pipecat queue
and interruption handling. They cover final-only and interim-then-final speech,
both before output and during output, multi-segment capture, cancellation on speech
onset, and preservation of both pause fragments in PostgreSQL and agent context.
The original failure cases were run against the old code and failed before the fix.

Validation after the fix: the full backend `tests` suite passed with 67 passed
and one opt-in live-provider test skipped. Tests used an isolated PostgreSQL schema
and `VOICE_ENABLED=false` as the default. Ruff lint and formatting checks passed
for the changed Python files, and `git diff --check` passed.

## Manual acceptance checklist

Restart the backend if it is not running with reload, refresh the browser, and
start a new voice session. First use the usual laptop speakers and comfortable
volume. For any failure, report the approximate time, what was spoken, pause length,
whether Saarthi was silent or speaking, and the resulting saved chat.

1. Say “मैं client meeting में था…”; pause roughly 0.5, 1, and 2 seconds in
   separate attempts; continue “…और manager ने salary कम करने को कहा.”
   Both parts should survive in saved chat and inform the reply. Separate user
   bubbles are acceptable. Report if Saarthi starts talking during the pause.
2. Finish a sentence, then continue with an extra detail while Saarthi is still
   silent/thinking. The old pending reply should stop and the next reply should
   consider both statements. No early words should disappear.
3. While Saarthi is speaking, say “रुको, पहले मेरी बात पूरी सुनो,” then explain.
   Old output should stop, the full interruption should be captured once, and the
   next reply should address it without resuming the old response.
4. Say a short “haan” or “hmm” over output: Saarthi should normally continue.
   Then try “haan, lekin meri baat सुनो”: that should interrupt and retain the
   correction. A standalone “haan” while listening should count as an answer.
5. Interrupt three successive replies and then let one finish. Check for old audio
   returning, duplicate turns, missing opening words, or a permanently stuck reply.
6. Leave voice, refresh/reopen the chat, and compare saved user messages with what
   was spoken. Check the chat bubbles, not just the temporary live transcript.

Keep transcription substitutions, missing words, premature replies, and sluggish
response time separate in the report. This patch fixes cancellation and protects
resumed speech; it does not change the STT model or tune Smart Turn's pause threshold.
The live transcript displays provisional recognition with a `Live speech` label;
accepted messages appear immediately as saved chat bubbles.

## Follow up from real microphone testing

Sanchit reported that only “क्या बोला?” remained visible after a longer sentence.
In conversation `55f89930-6b31-435a-9b62-65aec22d11bc`, PostgreSQL contains both
“मैं क्या बोल रहा था मैं भूल गया. क्या तुम बोल सकते हो मैंने last” and “क्या बोला?”
as separate user messages, saved at 08:51:52.639 and 08:51:52.950 UTC respectively.

The second report, ending “बीमारी कब आना देकर घर पर काम कर लूंगा but party थी तो
मैं काम कर ही नहीं पाया.”, also has a saved preceding fragment beginning
“अरे मैं manager को तो नहीं पता था…” and ending “तो मैं सोचा था”. They were
saved at 08:53:42.023 and 08:53:42.259 UTC. These are recognized transcripts;
their presence does not establish word-for-word accuracy against actual speech.

This exposed a separate display defect: the live transcript advances to the newest
fragment, but saved chat previously refreshed only after an assistant final event.
Earlier accepted fragments could therefore vanish from the live line before the
chat showed them. Overlapping chat refreshes could also restore an older snapshot.

Implemented follow-up:

- The backend emits `user_turn` with the saved message ID only after the user
  message transaction commits.
- The browser immediately displays that canonical message as a user bubble,
  deduplicates repeat events, and clears only matching provisional text. Newer
  live text is preserved when an earlier acceptance arrives late.
- Chat refreshes are fenced so older HTTP responses cannot overwrite newly saved
  voice messages or a newer conversation load.
- The provisional line is labelled `Live speech` and clears on leaving voice.

Verification: 25 backend voice tests and four Node browser-script regression tests
passed. Chromium checks with fake media and mocked HTTP verified that a saved
prefix stays visible while the live line advances to “क्या बोला?”; desktop and
mobile layouts were inspected. No actual microphone or provider call was used for
this display check. Pause-related turn splitting and recognition substitutions
still need evaluation independently of visibility.

## Reported experience

Sanchit reported that voice conversations feel fragmented. Interrupting spoken
output stops playback, but pausing and then continuing before Saarthi starts
speaking can appear to cut off part of the thought. The example included
“Basically मैं client meeting में था और client meeting में मैं ठीक से” followed
by “तो वह बोल रहे हैं कि कम कर दो.” Recognition also produced unexpected text
such as “Data.”

## Database findings

Conversation `97784144-d608-47ef-aa35-4a9a20586508` matches the pasted chat history.
Both client-meeting fragments are saved as separate user messages. The assistant
prefix “Client meeting mein kuch” is saved with interrupted delivery status.

`voice/store.py:prepare` builds the next agent payload from all saved messages.
Already-persisted fragments therefore survive into subsequent context. This does
not establish that every spoken word was recognized or persisted.

## Original cancellation bug

Before the fix, in `backend/voice/pipeline.py`, `CaptureTurn.process_frame`:

1. Emits the recognized text to the live transcript UI.
2. Awaits `session.interrupt()` when a response task is running.
3. Only afterward appends a final transcript to `self.parts` and forwards it.

In `backend/voice/session.py`, interruption called `_clear_output`, which broadcast
a Pipecat interruption upstream and downstream, then waits 50 ms before returning.
The upstream interruption reaches `CaptureTurn`. Pipecat 0.0.108 cancels that
processor's in-flight non-system frame handler, including its awaited interruption
call. Consequently:

- The final transcript can be displayed but never appended or forwarded.
- `_interrupt` can abort before `response_task.cancel()` and final persistence.
- The old response task can remain running after output has been cleared.

This also occurred during generation before any audio played: the condition checked
for a running response task, rather than actual assistant playback.

## Reproduction evidence

A synthetic pipeline using the installed Pipecat processors, real `CaptureTurn`,
real `VoiceSession.interrupt`, and `AgentOutput` reproduced the failure without
microphone input or provider calls. The response task was a sleeping asyncio task;
`start_response` recorded accepted turns instead of calling providers.

- With no response running, a final `TranscriptionFrame` was captured and accepted.
- With a response running and no audio played, the same final frame emitted a UI
  transcript and clear event, but left `capture.parts` and accepted turns empty.
  The original response task remained running.
- Interim frames also triggered the incomplete cancellation path. Interim text
  being absent from final storage by itself is expected; loss of a final frame is
  the decisive failure.

The original investigation script was `/tmp/repro_voice_capture.py`; durable
regression coverage now lives in `backend/tests/test_voice_capture.py`.

Before the fix, existing voice tests passed: 18 tests across `test_voice.py` and
`test_voice_transport.py`, using an isolated PostgreSQL test schema and
`VOICE_ENABLED=false` as the test default. The original interruption unit test
stubbed `broadcast_interruption`, so it did not exercise upstream cancellation.

## Pause handling and remaining uncertainty

A pause can commit an unfinished fragment and start generation. Continued speech
previously entered the broken interruption path even while the assistant was silent.
This explains the reproduced loss mechanism, but the exact event sequence in the
reported call cannot be reconstructed from stored message timestamps alone.

Smart Turn's configured `stop_secs=2.5` is an upper silence bound, not a guaranteed
minimum pause allowance. Its completion decision can end a turn sooner.

The live UI renders both interim and final recognition events as provisional speech;
separate chat bubbles now show accepted turns. A visible live transcript alone is
not proof of persistence. Recognition accuracy, acoustic echo, and the
origin of “Data” remain unverified; no audio recording was made.

## Further acceptance and diagnostics

- Retest ordinary listening, standalone acknowledgments, acknowledgments that
  expand into corrections, and real Hindi/Hinglish speakerphone conversations.
- Measure speech end, turn acceptance, first model text, first audio, and
  interruption completion using timing metadata without recording audio.

Existing conversation data has not been rewritten by this fix.
