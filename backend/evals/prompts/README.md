# Starting prompt

Current app prompt: `grounded-v4.txt`. Revised after the first completed stress
run: crisis support keeps Saarthi's direct everyday voice, encourages concrete
nearby human support, and never guesses emergency contact channels. Repeated
reassurance must change in substance, not just wording. Final replies must exclude
drafting commentary. These are targets to test, not proof failures are fixed.

Previous app prompt: `guardrails-v3.txt`. Adds plain-Hindi preference, no unsolicited
templates, explicit intense-emotion and adversarial-context handling, and current
corrections taking priority over stale memory. Stress runs record any effort
override through shared runtime configuration; the app default remains unchanged.
See MODEL_BUDGET.md one directory above. Historical prompt snapshots remain unchanged.

Previous app prompt: `concise-v2.txt`, revised after the first full baseline and
Sanchit's feedback. It shortens default replies, removes repetitive reassurance
and obvious forced-choice questions, investigates discounted praise, and omits
verse numbers unless explicitly requested. It was the baseline before v3.
The simulator instructions were also changed to discourage repeated questions;
fresh runs therefore compare the overall conversation, not an isolated prompt effect.

`starting-v1.txt` is an exact snapshot of `agents.saarthi.PROMPT` after revising
the actual app prompt using the judging discussion. This is the starting baseline.
Default eval runs call the app with its current prompt. Select this file with
`--prompt evals/prompts/starting-v1.txt` to keep the baseline fixed for comparisons.

The revision keeps the existing Roman-script Hindi default, user-led language
adaptation, reflective conversation style and safety boundaries. It strengthens:

- Appreciation and evidence-based challenge, without reflexive agreement or blame.
- Gentle teasing only when supported by the user's actual shared history.
- Casual conversation, celebrations and random stories without forced introspection.
- Meaningful shloka explanations and authentic anecdotes, with flexible paraphrases
  clearly distinguished from scripture and no invented authoritative attribution.
- Respect for corrections and requests to omit religious framing.
- Coherent, complete stories and consistent follow-ups, prompted by the first live
  smoke transcript's confused story and changed causal explanation.
- Opening greetings that allow casual chat rather than assuming a problem.

`reflective-v1.txt` predates this revision. It is an exploratory alternative, not the
chosen starting prompt. Historical smoke runs retain their original prompt snapshots;
they do not evaluate the new baseline. Prompt adherence and conversational quality
must be reviewed on new runs, not inferred from passing software tests.

`grounded-v5-candidate.txt` is an experimental shorter prompt with three curated
voice examples. It targets incoherent stories, repeated reassurance, loaded questions
and ornate language observed in development runs. Safety, memory and scripture
boundaries remain explicit. It is not promoted to the product; compare on identical
prefixes/settings before assessing it. No reserved holdout text was used as an example.

`grounded-v6-candidate.txt` keeps the v5 examples and adds ordinary Hindi alternatives
and one development-derived example showing how to respond when a person refuses
human company despite present danger. V5's fixed-prefix crisis replies repeated a
safe direction without exploring the obstacle, and often opened with philosophy.
V6 is a candidate; the product still uses v4. Fresh holdouts must follow selection.

`grounded-v7-candidate.txt` restores positive Krishna-inspired intellectual Hindu
character using Sanchit's Madhav prompt as inspiration, retaining Saarthi and Roman
Hindi. The four-case Luna suite completed 50/50 calls. Hindu references became more
visible but repetitive, while scripts/verbosity and weak story payoffs persisted.
See ../V7_REVIEW.md. This candidate has NOT replaced the app prompt. User feedback
and explicit approval are required before another conversational suite.
