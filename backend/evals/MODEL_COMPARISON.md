# Budget model comparison for Saarthi

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

Updated 2026-10-20T11:50:27.676247+00:00. Research only; no generation calls.

## Decision

Drop Sonnet from the initial comparison. The user plans to add $10 and wants that
credit used efficiently. Prioritize affordable widely distributed model families,
not premium models as an automatic reference. GPT Luna means **GPT-6 Luna**, not
Luna Pro. Standard Luna is cheaper than older GPT-5.6 Luna in the checked catalog.
We have not yet measured any alternative on Saarthi; benchmarks nominate candidates,
not winners. Do not use the $10 as a target to spend completely.

## Checked shortlist

Rates below are the live /api/v1/models catalog snapshot in USD per million tokens,
not cached-input rates or an assurance every routed endpoint charges that amount.
OpenRouter page summaries and individual endpoints can quote different or newer
prices. Query endpoint prices immediately before runs and record actual billed cost.

| Model ID | Purpose | Input $/M | Output $/M |
| --- | --- | ---: | ---: |
| `minimax/minimax-m3.1-flash:free` | Existing baseline | 0 | 0 |
| `qwen/qwen3.7-flash` | Lowest-cost alternative | 0.03 | 0.13 |
| `deepseek/deepseek-v4-flash` | Older 0423 cost baseline | 0.091 | 0.182 |
| `deepseek/deepseek-v4.1-flash` | Low-cost main contender | 0.056 | 0.12 |
| `openai/gpt-6-luna` | Main conversational contender | 0.1 | 0.5 |
| `deepseek/deepseek-v4.1-flash-1017` | Updated DeepSeek challenger | 0.15 | 0.6 |
| `google/gemini-3.8-flash` | Higher-cost Flash challenger | 0.825 | 4.125 |

DeepSeek 1017 has scheduled peak/off-peak overrides: budget up to **$0.30 input /
$1.20 output**, not just the $0.15/$0.60 base rate. Qwen has higher long-context
tiers starting at 32K prompt tokens; keep checkpoint inputs below that tier.
Gemini is about 8.25x Luna's listed per-token rates in this snapshot. It can still
fit in the budget, but should earn its place through measured response quality.

## What the benchmarks establish

Artificial Analysis Intelligence Index scores are broad capability indicators.
They do not measure natural Roman Hindi, spiritual nuance, listening, or safe
companion conversation. Higher effort scores cannot be attributed to lower effort.

- **GPT-6 Luna:** AA reports about **30 at medium**, **38 at max**. Medium has
  much less aggregate output-token use in that benchmark than max (29M vs 140M).
  This supports explicitly testing effort rather than assuming the highest setting
  is necessary for short conversation. Those are benchmark totals, not per-message
  forecasts or visible-answer lengths. Start with medium; test low/high on finalists.
- **DeepSeek V4.1 Flash:** AA release page reports **39 at max**. Its 1017 update
  has its own AA page reporting **45 at max** and about 211 output tokens/second.
  The 1017 result is worth a cheap checkpoint comparison, but does not establish
  better Hindi or lower end-to-end latency. The AA page also calls max verbose.
- **Gemini 3.8 Flash:** AA reports about **41 at high**, about 149 output tokens/
  second. Keep it as a bounded challenger, not the presumed winner. AA first-party
  pricing differs from the OpenRouter catalog snapshot, so use OpenRouter pricing
  for our budget. Token throughput is not time until a useful finished reply.
- **DeepSeek V4 Flash:** the April 0423 and July 0731 models are distinct. The
  OpenRouter April page maps AA scores to 0420 (roughly 24), so that is an imperfect
  historical mapping, not a verified exact-0423 measurement. Its July 0731 page
  lists about 34 at max; do not attach that score to April. July catalog rates
  ($0.44/$1.32) exceed the listed base V4.1 rates, so it is not a first-round
  bargain on this snapshot. Screen April briefly as requested, prioritize V4.1.
- **MiniMax M3.1 Flash:** OpenRouter lists AA score **42.7** but the benchmark
  summary does not identify effort. The exact AA page could not be independently
  retrieved in this pass. Our own medium-effort Saarthi failures matter more than
  that headline; high index scores have already failed to guarantee our voice.
- **Qwen3.7 Flash:** the exact-model independent benchmark score was not verified.
  Keep it as an inexpensive empirical candidate; do not borrow Plus/Max scores.

The latest 1017 OpenRouter benchmark summary appears to reuse the earlier V4.1
39.5 result; the primary AA 1017 page reports 45. Preserve this discrepancy instead
of pretending the two sources identify the same result. Sources have different
update times and model/effort mappings. Avoid mixing ranks across comparison classes.

## Model author versus hosting provider

OpenAI, Google, DeepSeek, Alibaba/Qwen and MiniMax are model authors. OpenRouter
can route one model ID to multiple hosting providers. A very cheap endpoint can
differ in supported settings, latency and reliability. Verify endpoint availability
and model version, record the actual provider/model identity where returned, and
keep routing consistent across repeats. An unversioned model ID is not a permanent
checkpoint guarantee. No silent fallback to another model or paid route.

DeepSeek's own API retired original V4 Flash and temporarily maps its old direct
API names to V4.1. OpenRouter still catalogs third-party V4 entries; do not assume
an older model name on every provider proves the old weights were served.

## Compatibility before any paid run

- Luna: medium initially; supported named effort options include none/low/medium/
  high/xhigh/max. OpenRouter does not list temperature support. The shared runner
  must omit unsupported temperature for Luna, with a transport test. Do not silently
  send the current fixed 0.7 or rely on it being ignored. This sampling difference
  must be disclosed in cross-model comparisons. No Pro mode, tools or web search.
- Qwen3.7 Flash: omit named reasoning_effort (not listed as supported); record
  default reasoning. It is not valid to force medium on every model.
- V4.1 and 1017: low/high/max/none supported; no medium. Start low for inexpensive
  screening and test high on finalists. A max benchmark is not that low result.
- April V4: high/xhigh/none listed; use high initially, separately labelled.
- Gemini: low/medium/high supported; medium initially. Revisit high only if useful.
- MiniMax baseline: low/medium/high comparison. Same free model ID as prior runs.
  No exact paid M3.1 Flash route was listed in this catalog; MiniMax M3 is a
  different model and must not silently substitute for the free baseline.
- A small compatibility call per candidate precedes repeats. Count it in the
  stage budget. Flag unsupported parameters as transport failures, not bad persona.

## Spend less by staging the experiment

1. Freeze v4 and six transcript checkpoints. Generate three responses per model
   (18 calls/model). No simulator calls are needed. Include interpretation reversal,
   story coherence, repetition, crisis resistance and stored-context attacks.
2. Drop clearly failing candidates. Spend effort comparisons and compact-prompt/
   example comparisons on only the best two or three. Keep inputs fixed and use
   manual review, not a paid judge. Do not average away a critical failure.
3. Run six-turn adaptive conversations only for finalists. Keep one inexpensive
   simulator model and its settings fixed across assistant candidates; a short
   simulator compatibility test is necessary. It need not be a premium model or
   the same model as Saarthi. Record simulator and assistant costs separately.
4. Reserve fresh holdouts until choosing a candidate. Repeated development runs
   do not substitute for fresh evaluation. Keep one index for the whole round.

At 8192 input tokens and a full 4096 billed output tokens per request (including
reasoning where billed as output), the catalog-based 18-call estimates are:

| Candidate | 18-call estimate |
| --- | ---: |
| `minimax/minimax-m3.1-flash:free` | $0.000 |
| `qwen/qwen3.7-flash` | $0.014 |
| `deepseek/deepseek-v4-flash` | $0.027 |
| `deepseek/deepseek-v4.1-flash` | $0.017 |
| `openai/gpt-6-luna` | $0.052 |
| `deepseek/deepseek-v4.1-flash-1017` | $0.133 |
| `google/gemini-3.8-flash` | $0.426 |

Combined estimate: **$0.67** (126 assistant calls, no simulator).
Allow a **$1 first-stage working budget** for screening and compatibility calls.
These are token/rate assumptions, not an enforced monetary cap. If high effort
exhausts 4096, a separate 8192-cap run must be costed; do not simply lower effort
and call the capped comparison fair. No automatic retry loops or costly full grid.

For the planned $10 top-up, target **at most $4 for the initial experiment cycle**:
$1 screening, $1 targeted effort/prompt comparisons, $2 finalist conversations.
Keep **$6 unspent** for later iteration unless results justify using it. This is
a plan, not a deployed spend limiter. Before executing, enforce stage reservations
using allowed endpoint rates, input/output bounds, and current balance; reconcile
actual billed usage between stages. Routing/caching/fees can change actual charges.

## Account status

The user has asked us to assume a future $10 top-up for planning. That is not
evidence the top-up has arrived. At the previous read-only check, purchased
credits were $0, usage $0.0084768, and remaining free requests 0. The $50 API-key
limit was a cap, not available credit. No account check or generation was charged
for this research. Recheck funding before launching requests; do not buy credit.

## Sources checked

- [User-requested catalog](https://openrouter.ai/models?order=pricing-low-to-high&output_modalities=text)
- [Live pricing/parameter metadata](https://openrouter.ai/api/v1/models)
- [Official Luna specification](https://developers.openai.com/api/docs/models/gpt-6-luna)
- [Luna medium benchmark](https://artificialanalysis.ai/models/gpt-6-luna-medium)
- [Luna max benchmark](https://artificialanalysis.ai/models/gpt-6-luna)
- [Gemini high benchmark](https://artificialanalysis.ai/models/gemini-3-8-flash)
- [DeepSeek V4.1 release benchmark](https://artificialanalysis.ai/models/releases/deepseek-v4-1-flash)
- [DeepSeek 1017 primary benchmark](https://artificialanalysis.ai/models/deepseek-v4-1-flash-1017)
- [April V4 listing and historical benchmark mapping](https://openrouter.ai/deepseek/deepseek-v4-flash)
- [July V4 listing](https://openrouter.ai/deepseek/deepseek-v4-flash-0731)
- [MiniMax listing](https://openrouter.ai/minimax/minimax-m3.1-flash:free)
- [Qwen listing](https://openrouter.ai/qwen/qwen3.7-flash)
- [DeepSeek official retirement notice](https://api-docs.deepseek.com/news/news260910/)
