# Saarthi eval learnings and next experiment

## Current checkpoint — supersedes historical planning below

**V7 suite complete: 4/4 conversations, 50/50 calls; observed cost ~$0.04,
remaining ~$9.63. Waiting for user feedback/approval.**
See [V7_REVIEW.md](V7_REVIEW.md) for the full verdict and artifacts.

Read [ROUND_RESULTS.md](ROUND_RESULTS.md) for the funded experiment results and
latest user steering. Seven models were screened; effort and v5/v6 prompt tests
and eight full development conversations have run. Luna is the current candidate,
not a mature final choice. The user finds v6 too generic and wants a recognisable
Krishna-inspired Hindu/Gita voice. V7 is the new candidate, inspired by the supplied
Madhav prompt, retaining Saarthi and Roman Hindi.

**Approval gate:** after EVERY conversational suite, stop for Sanchit's feedback
and explicit approval before another suite or paid follow-up. This supersedes the
earlier instruction to proceed through all experiments without interim approval.
The authorised Luna v7 suite completed all four development cases: 50/50 calls,
13 messages per case. Read [V7_REVIEW.md](V7_REVIEW.md). Awaiting Sanchit's feedback
and approval; no further suite is authorised.
Fresh holdouts have not run and must remain reserved until approval.

Switch app models with `SAARTHI_MODEL = "minimax"` or `"luna"` near the top of
`backend/config.py`, then restart. This selects model/provider/effort together.
Environment overrides still take precedence; local legacy model overrides were
commented out so the switch works. App defaults remain MiniMax; app prompt remains
v4 pending candidate review. Eval model/prompt are explicitly recorded separately.

## Historical notes / earlier plan

For a new-session continuation, read [HANDOFF.md](HANDOFF.md) first.

Updated 2026-10-20. This document separates observations from hypotheses. Human
judgment remains final; no API judge has scored these runs.

## Current verdict and intended experience

Grounded-v4 is a development baseline, not a mature or safety-certified prompt.
Saarthi should sound like a warm, perceptive, candid spiritual companion: natural
Roman Hindi, occasional wit, meaningful Gita connections, and concise replies.
It should understand before challenging, accept corrections, celebrate naturally,
and let casual conversation remain casual. Practical honesty must not become
humiliation, guilt, invented authority, or a philosophical substitute for urgent
human help. See REVIEW_GUIDE.md for the full judging criteria.

## Where the latest eight conversations are

The latest round was two separate runs, not eight cases in one report:

- `runs/20261020T110259Z-245ff763/report.md`: six stress conversations.
  Five acceptable, one bad in the manual Codex review.
- `runs/20261020T110331Z-4e021540/report.md`: comparison/self-worth and casual story.
  Both bad in the manual Codex review.

All eight completed, each with six user messages plus seven assistant messages
(including the greeting). Completion means generation succeeded, not quality or
safety. Human reviews remain blank. Start with each run's codex-review.md, then
report.md; JSON files contain fixtures, settings and records for debugging.

## What we have tried

All live runs so far used `openrouter/minimax/minimax-m3.1-flash:free` for Saarthi.
The simulator also used that model, in separate requests. Saarthi temperature was
0.7 and the per-call output cap 4096. No alternative model, explicit high-effort
comparison, temperature comparison, or larger-cap comparison has been completed.

- Original smoke and reflective-v1 replay: storytelling/coherence problems. Replay
  could become unnatural when new replies changed the story under fixed user turns.
- starting-v1: listening initially useful, then verbose/repetitive coaching and an
  incorrect scripture citation. Final provider failure had insufficient diagnostic
  data to recover the exact cause.
- concise-v2: first six substantive comparison replies averaged about 49 words
  versus 131 in the earlier run. Fresh simulated paths prevent a causal claim.
  Salary failed with MAX_TOKENS at 4096; the reasoning/visible split was not saved.
- guardrails-v3, low effort: poor Hindi and simulator schema failures. Later fixes
  improved simulator JSON instructions and diagnosed raw user utterances that were
  valid dialogue but did not use the requested JSON wrapper.
- Simulator adapter: accepts a plain utterance verbatim only for DeepEval's
  single-field SimulatedInput schema; malformed structured JSON still fails.
  This does not relax Doval or product output validation.
- guardrails-v3, medium effort: six stress cases completed, four acceptable/two bad.
  Draft commentary appeared in a panic reply; crisis invented an emergency-chat
  option. Other boundaries held for the sampled direct attacks and poisoned memory.
- grounded-v4, medium effort: latest eight cases, five acceptable/three bad. No
  invented emergency channel or visible drafting commentary appeared in this sample.
  Repetition, lengthy advice, garbled Hindi, stale opening assumptions, actor
  confusion and weak story coherence remained. One reply reversed the user's
  explicit meaning. No model/effort/provider cause has been isolated.

Earlier runs with no effort override used provider_default; do not label their
actual effort as a known measured value. The app still defaults to provider_default;
medium was an explicit eval override. Doval effort was not changed.

## What the evidence does and does not establish

Observed: the instructions are not reliably expressed in actual responses. V4 is
about 1828 words and largely describes rules rather than demonstrating the intended
voice with curated examples. Adding more rules has not resolved the recurring issues.

Hypotheses to test: model capability, effort/output-cap interaction, prompt length
and examples, and sampling variability. None is yet the proven dominant cause.
The free route may also differ operationally from paid routes; paid access alone
is not evidence of better quality. Do not conflate transport failures with judgment.

The same model simulates users and sometimes praises incoherent stories or repeats
company requests. Simulated satisfaction is not a quality metric. Review actual
replies and annotate simulator limitations. Hidden persona facts are not evidence
Saarthi knows those facts. Current corrections outrank stale stored context.

## Experiment plan: one variable at a time

1. Freeze grounded-v4, context payloads, temperature, timeout and exact conversation
   checkpoints. Include reversed meaning, story continuation, repeated reassurance,
   resistance to human help, scripture nuance and injected/stale memory. Freeze
   transcript prefixes rather than regenerating earlier assistant messages.
2. On the existing model, compare low/medium/high effort on identical checkpoints,
   with three repeats per cell. Keep the same cap initially. Record truncation and
   latency separately from quality. If high hits the cap, run a separately labelled
   larger-cap experiment; do not interpret truncation as evidence high is worse.
3. Compare a small set of alternative models on identical checkpoints with the
   frozen prompt. Use only supported parameters; document each model's default or
   explicit reasoning setting. Cross-model effort labels are not equivalent compute.
4. Review manually, preferably with shuffled/blinded candidate labels. Judge
   understanding, voice, Hindi clarity, concision, coherent stories, accurate
   spiritual interpretation and boundaries. Do not average away critical failures.
5. With the best viable model/settings fixed, compare v4 against a shorter prompt
   containing a few curated good/bad response examples. Examples must not be copied
   from reserved holdouts. Keep the same checkpoints and repeats.
6. Validate promising combinations with full adaptive conversations (10-15 total
   messages), then fresh holdouts. Keep simulator model/settings fixed across
   candidates. Repeat critical cases; one clean sample does not establish reliability.
7. Produce one round index linking every run, configuration, cost and review. Do not
   silently promote a model, effort or prompt into the product configuration.

## Runtime parity and limits

Evaluations call actual agents.saarthi.reply -> shared runner -> ADK/LiteLLM ->
OpenRouter. There is no mirror implementation. Synthetic context replaces the DB;
HTTP, auth, persistence, leases/retries and Doval extraction are outside these runs.
Software tests verify plumbing, not conversational quality. Local manual review
uses Codex in this session, not a billed API judge.

## Model shortlist and affordability

See [MODEL_COMPARISON.md](MODEL_COMPARISON.md) for the checked exact model IDs,
pricing, compatibility issues, staged cost assumptions and account result. The
configured account reports no positive purchased balance and zero remaining free
requests. The $50 key cap is not account credit. No new model generations were
launched in this documentation/budget pass. Experiment execution remains pending
funding/quota; do not interpret a prepared plan as completed experiments.

## Cost-priority correction

The initial Sonnet reference was unnecessary for the user's cost goal. The revised
shortlist in MODEL_COMPARISON.md replaces it with GPT-6 Luna, adds the requested
older DeepSeek V4 comparison and separates inexpensive V4.1 hosting from the
1017 update. Gemini is a bounded challenger. Aim to learn with under $4 of the
planned $10 and preserve the rest; benchmark rankings do not prove persona fit.
The top-up is assumed for planning, not confirmed, and no new generations ran.

## Funded continuation — 2026-10-20

Top-up verified: total credits $10, historical usage $0.0084768, remaining
$9.9915232. Free quota now reports 700 remaining. Earlier unfunded account statements
above describe the prior check. Implemented frozen-prefix screen and conservative
persistent request reservations, provider routing/price limits, optional shared-runner
usage observation and temperature omission. Focused checks: 26 passed, 1 optional
live test skipped. New round: `runs/20261020-budget-round/README.md`.
The seven-model v4 screen has finished; see ROUND_RESULTS.md and V7_REVIEW.md
for completed comparisons, subsequent validation and current stopping point.

## Pull-request preparation

Review found that the generic exception handler reused the call-status variable
for an HTTP status, causing observed provider failures to have null/numeric status
instead of `failed`. Separated those variables and extended the existing six-mode
mocked failure test to assert the observer consistently records `failed`. Historical
ledgers are preserved unchanged; older failures may contain the old status value.
Raw runs remain local and gitignored. Tracked round/review docs carry conclusions;
links under runs/ require the original local artifacts. No paid calls were made
while preparing the PR. A pull request is authorised; merging/deployment and another
conversational suite are not. Separate voice design and output/ are excluded.

The final v6 and v7 Markdown reports are now versioned under reports/ so reviewers
can inspect the actual conversations in the PR. Only raw/intermediate run artifacts
remain local. No additional generations were used to produce these snapshots.
