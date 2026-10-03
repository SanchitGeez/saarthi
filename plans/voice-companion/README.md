# Voice-companion proposal archive

This October 3 proposal and interactive prototype are preserved for design history.
The current implementation is described in [the handoff](../../docs/agent-handoff.md),
[product brief](../../PRODUCT.md) and [live setup](../../docs/live-voice.md).

- `plan.mdx` and `canvas.mdx`: original product/architecture exploration.
- `prototype.mdx` and `review.html`: simulated UI; they do not call a microphone,
  LiveKit or providers. Open the HTML locally to review the original proposal.
- `assets/temple-reference.png`: the user-supplied reference, not a new generated asset.

Superseded choices: the companion is now **Parth**; the **LLM** chooses openings
from permitted context, including a general greeting when appropriate. There are
no fixed timing/greeting rules. Only one image is used for all agent states.
Scheduled follow-ups, structured ongoing concerns, extra state images and background
tasking in the proposal remain future possibilities, not implemented features.
