# What the 4096-token budget means

Checked 2026-10-20 against OpenRouter documentation, its public model metadata,
and the installed ADK/LiteLLM adapter.

- **Output budget:** an upper bound for one model invocation. Our runner previously
  hardcoded 4096; it is now `AGENT_MAX_OUTPUT_TOKENS`, still defaulting to 4096.
  ADK sends this as `max_completion_tokens` through LiteLLM. It resets for each
  invocation, not each hour, user account, or entire conversation.
- **Context window:** the space available to process input and generated tokens
  together. The prompt, profile, knowledge, summary and transcript are input. The
  model's available context is separate from our much smaller chosen output cap.
- **Rate/account limits:** requests or tokens allowed over a time period, or credit
  limits. Those are provider/account policies; they are not our 4096 setting.
- **Timeout:** our separate 60-second wall-clock limit for an invocation.

Tokens are pieces of text rather than words. With reasoning models, the output
budget can include internal reasoning as well as the answer the user sees. A
short visible reply does not establish that few output tokens were consumed.
OpenRouter documents that reasoning can exhaust a small output cap before a final
answer is produced, resulting in `finish_reason: length` (mapped by ADK to MAX_TOKENS).

The public model metadata for `minimax/minimax-m3.1-flash:free` currently lists:

```json
{
  "context_length": 1000000,
  "top_provider.max_completion_tokens": 524288,
  "reasoning.mandatory": true,
  "reasoning.default_effort": "max",
  "reasoning.supported_efforts": ["max", "xhigh", "high", "medium", "low"]
}
```

Those model limits are not what our application requests. Prior runs omitted an
effort override, so they selected the provider default. The salary case proves
the invocation hit its output cap, but its old error record did not contain token
usage; the exact split between reasoning and visible output cannot be recovered.

We tested low effort, keeping the output cap at 4096. Those samples exposed
language/response-quality concerns and simulator formatting issues; they do not
justify adopting low effort as the product default. The app retains
`AGENT_REASONING_EFFORT=provider_default`. Stress experiments can explicitly select
`medium` or another supported effort. These are experiments to inspect latency,
completion and guardrail quality, not proof that a smaller effort is better.
Doval extraction keeps its existing provider-default reasoning independently.

New error records include available prompt, completion and reasoning token counts
from ADK usage metadata without storing reasoning text. With the pinned LiteLLM
adapter, completion tokens include reasoning; do not add them together again.
Unknown/missing usage stays unknown rather than being inferred from visible length.

Sources:

- [OpenRouter request parameters](https://openrouter.ai/docs/api_reference/parameters)
- [Reasoning and max_tokens](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens)
- [Rate limits](https://openrouter.ai/docs/api_reference/limits)
- [Public model metadata API](https://openrouter.ai/api/v1/models)
- [Current MiniMax model listing](https://openrouter.ai/minimax/minimax-m3.1-flash:free)

## Account check and comparison budget

See [MODEL_COMPARISON.md](MODEL_COMPARISON.md) for the 2026-10-20 read-only
account check and costed model shortlist. A per-key spending limit is not funded
credit. At that check the account had no positive purchased balance and the free
request quota was exhausted, so new comparisons were not launched.

## Measured funded round (2026-10-20)

Before the v7 persona suite, 301 generation attempts completed 295 replies, with
observed usage since funding verification of $0.319567416 and $9.671955784 remaining.
The account counter can lag; do not describe zero immediate deltas as free calls.
Persistent reservations total $2.632449732, much more than observed spending, since
full conservative input/output allowances are retained even after success/failure.
The implemented round reservation guard refuses above $4; v7 also has a $0.65 stage
limit. No retries or additional suites after this run without user approval.
See ROUND_RESULTS.md and the per-stage spending/billing artifacts for evidence.
