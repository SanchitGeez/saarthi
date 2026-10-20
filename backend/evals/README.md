# Saarthi conversation experiments

**Continuing in a new session? Start with [HANDOFF.md](HANDOFF.md).** It records
the implementation state, decisions, pending work and budgeted execution order.

A separate offline module using DeepEval 4.3.1 for adaptive user simulation and
conversation test cases. You and Codex/Sol review the results locally. No automated
quality metric, API judge, or prompt optimizer runs. The built-in optimizer needs
metric scores, which is a different workflow from the human feedback chosen here.

Current dialogue prompt: `prompts/grounded-v4.txt`. Short common Hindi, no unsolicited
document templates, and stronger emotion/memory/injection handling. See
`MODEL_BUDGET.md` for the difference between per-call output, reasoning, context and
account rate limits. The app retains `provider_default` reasoning; experiments can
override effort explicitly. Doval always retains provider-default reasoning.
Low-effort trials exposed language issues, so that setting was not promoted.
Runtime overrides as well as prompt changes are recorded in each run.

Start with [LEARNINGS.md](LEARNINGS.md) for experiment history, current limitations,
and completed comparisons. The eight-case Luna v6 round is in one report; the
latest v7 suite has four cases. Final full-chat report snapshots are versioned in
[reports/](reports/), while raw ledgers/intermediate artifacts stay local. Start with [ROUND_RESULTS.md](ROUND_RESULTS.md) and
[V7_REVIEW.md](V7_REVIEW.md). Raw runs are local ignored artifacts; tracked summaries
preserve the results in a fresh checkout. See [MODEL_COMPARISON.md](MODEL_COMPARISON.md)
for the checked model shortlist, prices, parameter compatibility and account budget.

## Run

From `backend/`:

```sh
uv sync --locked --group evals
uv run --group evals python -m evals list

# Uses backend/.env / environment: OPENROUTER_API_KEY, AGENT_MODEL.
# First run one full conversation before spending calls on the whole suite.
uv run --group evals python -m evals run --case comparison-and-worth

# All development cases; holdout cases are excluded by default.
uv run --group evals python -m evals run

# Frozen starting baseline: the app prompt revised after our judging discussion.
uv run --group evals python -m evals run \
  --prompt evals/prompts/starting-v1.txt --case comparison-and-worth

# Earlier exploratory candidate, retained for comparison; not the starting baseline.
uv run --group evals python -m evals run \
  --prompt evals/prompts/reflective-v1.txt --case comparison-and-worth

# Final check on scenarios kept apart from prompt development.
uv run --group evals python -m evals run --split holdout \
  --prompt evals/prompts/reflective-v1.txt
```

Each run prints its new directory under `evals/runs/`. Set `--output PATH` to choose
a new directory. Existing directories are refused. Files are saved after every
generated turn; provider failures keep partial results, are marked failed, and
return a nonzero exit status. Error text is restricted to the exception type because
provider messages can include credentials. New failures also save `error_details`:
category, safe explanation, error ID, failing phase, elapsed time, timeout flag,
exception types, HTTP status and model finish reason when available. The shared
runner logs these records in the app too; API errors include a correlation error ID.
Raw provider messages, prompts and credentials are excluded. Ctrl-C preserves partial transcripts.

The default simulator model is the same configured OpenRouter model as Saarthi.
Change it with `--simulator-model openrouter/PROVIDER/MODEL`. It generates user
messages, not quality scores. It must support native JSON-schema output through
the existing ADK/LiteLLM transport. There is no silent fallback to another model.
No OpenAI key or Confident AI account is required. DeepEval telemetry and trace
sampling are disabled for this local module; generation still calls OpenRouter.

`AGENT_MAX_OUTPUT_TOKENS` controls the per-invocation output budget (default 4096).
`AGENT_REASONING_EFFORT=medium` (or another supported effort) sets dialogue/simulator
reasoning effort; the default `provider_default` omits it. Use that default for
models without effort support. Changing effort is an experiment, not a quality fix.

`--max-turns N` overrides the scenario's user-turn budget (1–20). A fresh N-turn
conversation uses one Saarthi greeting call, N simulator calls, and N Saarthi reply
calls: 2N+1 model calls. Runs are sequential and have no automatic retries. A turn
budget is a testing bound, not a measure of successful conversation completion.

## Short stress conversations

```sh
uv run --group evals python -m evals list --scenarios evals/stress-scenarios.json
AGENT_REASONING_EFFORT=medium uv run --group evals python -m evals run \
  --scenarios evals/stress-scenarios.json
```

This selects six development cases with six user turns each: up to 13 messages
including the opening. Two additional cases are reserved with `--split holdout`.
The cases cover panic, imminent self-harm, revenge, fake-admin jailbreaks, poisoned
knowledge/summary and stale-memory correction; holdouts cover minor dependency and
persecutory beliefs. Several include synthetic stored knowledge and latest summaries.

`first_user_message` fixes the first stress trigger so the simulator cannot avoid
the behaviour being tested. Later user messages adapt to actual Saarthi replies.
Such cases use 2N model calls rather than 2N+1 because the first user message needs
no model call. A fixed trigger is a test fixture, not a real user's report.
The simulator can return JSON or a plain next-user utterance; the adapter preserves
a plain utterance verbatim for the single-field `SimulatedInput` schema and records
format counts in the test-case artifact. Broken JSON is still an error. This fallback
does not apply to Doval or any structured product output. Earlier failed stress
attempts remain saved; the adapter change is not a retroactive pass for those runs.
Failures to generate remain separate from failures of a guardrail. A short successful
sample is evidence about that sample, not a guarantee of safety.

## Review and compare

Read `report.md` and the copied `REVIEW_GUIDE.md`. Write a review via the CLI:

```sh
uv run --group evals python -m evals review evals/runs/BASELINE \
  --case comparison-and-worth --verdict acceptable \
  --evidence 'Turn 7 assumes fear of judgment before the user mentions it.' \
  --change 'Ask what makes sharing the project difficult before interpreting it.'

# Codex/Sol can record a separate assessment with --reviewer codex-sol.
# Or edit reviews.json directly, then refresh the readable report:
uv run --group evals python -m evals report evals/runs/BASELINE

# Regenerate all assistant turns against the baseline's exact user messages.
uv run --group evals python -m evals run --replay evals/runs/BASELINE \
  --prompt evals/prompts/reflective-v1.txt

uv run --group evals python -m evals compare \
  evals/runs/BASELINE evals/runs/CANDIDATE --output evals/runs/comparison.md
```

Substitute actual directories for BASELINE/CANDIDATE. Replay uses snapshotted
scenarios and skips simulation. It refuses incomplete source runs; a successful
single-case run is a valid source. It regenerates the greeting and all assistant
responses, with the same user messages and fixture context. Inspect whether those
fixed user messages still make sense. Fresh simulations complement replay when
assessing how an actual conversation develops.

Review files preserve separate human and Codex/Sol opinions. There is no fabricated
numeric average or automatic promotion. Ask Codex/Sol to read the artifacts and
propose a new prompt file, then rerun. This is an interactive workflow, not a
background call to Codex or a use of your chat subscription as an API key.

## What is shared with the product?

```text
Product:
HTTP -> core.service.generate -> DB context/transcript
                             -> agents.saarthi.reply(settings, payload)
                             -> agents.runner.invoke
                             -> ADK -> LiteLLM -> OpenRouter

Eval:
Scenario fixtures + DeepEval simulated user + accumulated transcript
                             -> agents.saarthi.reply(settings, payload)
                             -> agents.runner.invoke
                             -> ADK -> LiteLLM -> OpenRouter
```

The assistant is the actual product function and transport, with the same configured
model, temperature (0.7), token budget, timeout and per-invocation ephemeral ADK
session. There is no simplified copy of Saarthi or a second prompt implementation.
Without `--prompt`, the module reads the current production `saarthi.PROMPT`.
With it, an explicit per-call keyword override passes a candidate through the same
function. No global monkeypatch or product configuration change is needed.

The surrounding context is synthetic. `Scenario.payload()` supplies the same fields
as `core.service`: profile, active knowledge, latest summary, opening flag and the
full transcript, with the latest user turn included exactly once. Every case begins
with a real opening=true greeting. Hidden persona facts and reviewer expectations
are never passed to Saarthi. Previous assistant statements are not injected as
knowledge. Memory fixtures stay constant during a conversation, as they do until
the product's End/extraction workflow (unless knowledge is manually edited).

These are agent-behavior evaluations, not HTTP/database integration tests. They do
not run authentication, ownership checks, database context assembly, transcript size
limits, generation leases/retries, persistence, End, or Doval extraction. Existing
API tests cover those paths. A separate future suite would be needed to evaluate
cross-conversation memory extraction and reloading through the full product.

## Files and extension points

- `scenarios.json`: 7 development and 3 holdout scenarios, languages, private user
  personas, fixture context and review expectations. Includes cooperative, resistant,
  casual, correction, religious opt-out, scripture and urgent-support cases.
- `simulation.py`: DeepEval user-model adapter and actual Saarthi callback; replay.
- `models.py`: validated scenarios, payload shape and human assessment format.
- `__main__.py`: CLI and run orchestration; `artifacts.py`: local reports/comparison.
- `REVIEW_GUIDE.md`: agreed rubric and prompt-edit workflow.
- `prompts/starting-v1.txt`: exact snapshot of the revised app prompt chosen as the
  starting baseline. Default runs use the current app prompt; selecting this file
  explicitly keeps the starting baseline fixed as the app changes.
- `prompts/reflective-v1.txt`: earlier exploratory candidate, retained for comparison.
- `prompts/concise-v2.txt`: revised app prompt after the first baseline review and
  Sanchit's feedback on length, repetitive reassurance, obvious questions and citations.
- `stress-scenarios.json`: separate development/holdout stress corpus with memory
  fixtures and fixed opening user triggers.
- `prompts/grounded-v4.txt`: current prompt for natural variety, persona-consistent
  crisis support, no guessed emergency channels, and finished replies only.
- `prompts/guardrails-v3.txt`: previous prompt after template/language feedback and
  adding explicit intense-emotion, context-injection and memory-correction guidance.
- `reference-conversation.txt`: the user's initial style reference; not a required
  script or an automatically judged answer key.

Each run contains the exact assistant and simulator prompts, prompt hash, installed
dependency versions, git revision, source snapshots of the agent/transport/simulator,
model/settings metadata, snapshotted scenarios, DeepEval conversation records,
partial/final transcripts, separate reviews and a readable report. Keys, database
URLs and entire environment/settings objects are not written. Model/provider output
is not deterministic, even with identical settings; these records support inspection,
not a promise of bit-for-bit reproduction. Runs are gitignored; use synthetic data.

```sh
uv run --group evals pytest -q evals/tests tests/test_agents.py
uv run --group evals ruff check evals agents/saarthi.py
uv run --group evals ruff format --check evals agents/saarthi.py
```

Tests use the real DeepEval simulator with mocked provider replies, so they verify
its actual callback contract, history and scenario isolation without spending calls.
They do not establish live conversational quality. Read actual transcripts and judge
those separately.

## Controlled fixed-prefix model screen

`checkpoints.json` freezes six development inputs extracted from earlier local runs.
Unlike replay, **no earlier assistant reply is regenerated**. The same product reply
function receives precisely the snapshotted payload; reviewer expectations stay out.

```sh
uv run --group evals python -m evals.screen \
  --output evals/runs/NEW_ROUND/screen-v4 --budget 1
```

The screen has its own small CLI because its records are individual replies rather
than simulated conversations. `--model ID`, `--case ID`, `--repeats 1..3`, `--prompt`,
`--plan`, and `--cap 4096|8192` select explicit comparisons. `screen-plan.json` holds
frozen endpoint/rate/capability data; refresh it before a new paid round. Candidate
labels in report.md separate replies from identities in key.json, but this is only
light masking, not a rigorous blind trial. The first fixture is also compatibility
preflight; a first-call generation failure skips further calls for that candidate.

`spending.json` persists worst-case reservations before each network generation and
never releases them, even if actual usage is lower. UTF-8 bytes plus framing allowance
bound text input; requests at/above 32K are refused to avoid long-context pricing.
Full output caps include billed reasoning. Missing token usage remains unknown.
`run.json` records account usage before/after; token-based per-call costs are estimates,
not bills. Concurrent unrelated account activity would confound that account delta.

Experiment call hooks in the **shared runner** omit unsupported temperature and apply
explicit routing/price limits. With no hook, product defaults and return type remain
unchanged. This mechanism also allows one spending ledger to cover assistant and
simulator calls in later conversation stages, configured independently. The old
`python -m evals run` CLI does not yet enforce these spending limits on its own.

For a budgeted adaptive stage with a separately fixed simulator:

```sh
uv run --group evals python -m evals.conversations \
  --model openai/gpt-6-luna --simulator qwen/qwen3.7-flash \
  --prompt evals/prompts/grounded-v5-candidate.txt \
  --case comparison-and-worth --case casual-story \
  --budget .5 --output evals/runs/NEW_ROUND/basic-finalist
```

This wrapper uses the existing DeepEval conversation runner with explicit independent
Settings objects. It does not change `.env` or product defaults. Shared call hooks
reserve both assistant and simulator costs into one ledger. Effort comes from each
model's plan entry rather than being inherited. `--scenarios`, `--split holdout`,
`--case` and a six-user-turn cap keep the rounds small and explicit. Select finalists
from evidence before running this example; the example does not declare a winner.

Keep every stage inside a **new, shared round directory**. The budgeted wrappers
also sum retained `spending.json` reservations in sibling stages and refuse the next
request above a $4 round ceiling. This check assumes sequential stages; it is not a
cross-process locking service. Do not run concurrent stages or delete their ledgers
to recover budget. The original screen's $1 cap bounds it before this round check
was added; later stages include its retained reservations.

Conversation wrapper simulator cap is fixed independently at 2048; assistant cap
remains 4096. A model can play both roles with separate settings/prompts, but record
that self-play limitation and never treat simulated praise as a judge. The round's
lead tests use Luna assistant and a fixed Gemini low-effort user simulator.
Account usage counters can lag requests: a zero before/after delta is **not** proof
of a free stage. Report final observed round usage plus retained reservations, and
keep per-call ceiling-rate usage estimates distinct from billed charges.

Luna temperature omission also applies without eval hooks in the shared runner,
using its verified exact model ID. Selecting Luna in the product therefore does
not depend on the eval policy. The configured default model remains MiniMax.

## Current model switch and persona experiment

See [ROUND_RESULTS.md](ROUND_RESULTS.md) for completed comparisons and limits.
At the top of `../config.py`, change `SAARTHI_MODEL` between `"minimax"` (development)
and `"luna"` (better-quality testing), then restart the backend. The preset selects
model, provider and effort together. `AGENT_MODEL`, `AGENT_PROVIDER` and
`AGENT_REASONING_EFFORT` environment values override their respective defaults;
leave them unset for the one-line switch. Eval CLI flags deliberately override app
defaults and record the actual model/prompt, so old experiments stay reproducible.
Current eval candidate: `prompts/grounded-v7-candidate.txt`; production prompt still v4.
After every conversational suite, user feedback and explicit approval are required
before another suite or paid follow-up. Do not automatically run holdouts.

The authorised v7 persona suite is reproducible with the command below. Running it
again makes paid calls and needs Sanchit's approval; use a new output directory.

```sh
uv run --group evals python -m evals.conversations \
  --plan evals/persona-sanity-plan.json \
  --model openai/gpt-6-luna --simulator fixed-gemini-user \
  --scenarios evals/persona-sanity.json \
  --case comparison-and-worth --case casual-story \
  --case revenge-under-dharma --case imminent-self-harm \
  --prompt evals/prompts/grounded-v7-candidate.txt \
  --budget .65 --output evals/runs/20261020-budget-round/NEW-STAGE
```

To read the current run, open
`runs/20261020-budget-round/luna-v7-persona-sanity/conversations/report.md`.
`reviews.json` separates Codex from human feedback; `run.json` records configuration,
per-case JSON records partial/full turns and failures, and the parent `spending.json`
and `billing.json` separate reservations/estimates from observed account counters.
For the shared $4 guard, new stages must use the same round parent. Do not change
the parent to bypass existing reservations. NEW-STAGE is a new directory name.
