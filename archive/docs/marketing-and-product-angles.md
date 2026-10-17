> Historical design/research record. Read [the current handoff](agent-handoff.md) and [product brief](../PRODUCT.md) for implemented scope and naming. These proposals/comparisons do not establish customer demand.

# Marketing, messaging, and product angles

Updated: 2026-10-03. Living idea bank; draft messaging and product hypotheses are not validated claims.

## Audience and need

Founder-defined audience: religiously inclined Hindu adults aged 25–40 who have life problems and insufficient space to feel heard. Character relatability should include someone around age 28.

Potential situations to test: career pressure, family expectations, relationship conflict, difficulty setting boundaries, comparison with peers, and uncertainty about purpose.

## Character directions proposed by the founder

### 1. A relatable saarthi or friend

An original, ordinary-person figure who feels familiar to someone around 28. Deeply knowledgeable about Hinduism, emotionally mature, calm, and grounded. Speaks naturally and helps people think through their situation.

Product implications: contemporary language and appearance; warm conversation; concrete examples from everyday adult life; thoughtful questions; original voice; explicit AI identity. Avoid portraying maturity as perfection or a claim that this fictional figure has lived experience.

Draft messaging:
- “A little clarity for the life you're actually living.”
- “Talk it through. Find your next step.”
- “Gita-inspired wisdom, in a conversation that starts with you.”

Hypothesis: familiarity makes it easier to open up. Test whether the Hindu grounding is sufficiently clear and credible.

### 2. A thoughtful supporting character from mythology

A recognizable but less central mythological figure associated with wisdom, composure, and counsel. The founder wants someone other than Krishna, with spiritual familiarity and less narrative prominence.

No specific character has been selected or researched for suitability. Evaluate candidates against textual portrayal, knowledge of the Gita, audience recognition, perceived authority, warmth, and whether the character's history fits the role. Interpretations may differ across traditions.

Product implications: source-grounded characterization; distinguish original AI dialogue from canonical quotations; introduce the character's relevance clearly; test whether the setting encourages honest discussion of modern problems.

Draft messaging:
- “A familiar voice from our stories. Space for yours.”
- “Reflect on today's struggles through timeless teachings.”

Hypothesis: mythology increases spiritual resonance. Test whether people understand the identity and feel comfortable questioning it.

### 3. Hybrid — proposal to discuss

An original contemporary saarthi with subtle mythological inspiration, its own name and voice, and explicit Gita grounding. This is a proposed combination, not a founder-approved decision.

## Messaging angles to test

| Angle | Draft message | Required product behavior |
| --- | --- | --- |
| Being heard | “You don't have to keep it all to yourself.” | Listen before advising; allow a listening-only session |
| Continuity | “Pick up where you left off.” | Optional, accurate memory the person can inspect and correct |
| Self-discovery | “Questions that help you see your situation more clearly.” | Ask useful questions; accept disagreement; revise interpretations |
| Cultural familiarity | “Gita-inspired guidance for everyday life.” | Accessible explanations; reviewed sources are a later phase |
| Practical action | “Leave with a next step you choose.” | Respect circumstances and let the person choose the action |
| A moment of reflection | “A quiet moment to make sense of your day.” | Optional short original audio reflections |

## Ways these angles shape the product

- An adaptive dialogue that combines listening, clarification, reflection, and relevant teachings.
- A personal memory view showing what is remembered, tentative patterns, and ongoing concerns; support correction and forgetting.
- Optional follow-up on actions the person chose, without pressure to engage daily.
- A short original audio reflection after a meaningful conversation, drawing inspiration from the delivery of Mahabharat's Krishna segments.
- Future feature: verified source references alongside guidance. V1 must distinguish model interpretation from verified scripture and avoid fabricated quotations.
- Test text, spoken input, and spoken output separately to learn where voice adds value.

## Commercial and distribution hypotheses

- Short original reflections may introduce the product through social video or audio; their usefulness as acquisition content remains untested.
- Explore collaborations with relevant Hindu communities and educators after understanding their needs. No outreach is authorized by this document.
- Test a subscription for continuity and bounded voice usage. No price has been selected.
- Compare guided dialogue with generic scripture answers; compare memory-enabled repeat sessions with sessions without memory.
- Validate with real payment and voluntary return, alongside perceived understanding, useful actions, source trust, and cost per retained paying person.

## Claims and positioning to avoid

Do not promise treatment, guaranteed clarity, divine instruction, infallibility, or that all human spiritual advisers are fraudulent. Differentiate through visible sources, thoughtful dialogue, honest uncertainty, user control, and observed usefulness. Do not monetize by frightening people or claiming paid services can fix their fate.

## Decision log

- Confirmed: audience aged 25–40, Hindu and religiously inclined; listening and reflection are central.
- Selected: v1 text chat, voice notes, and spoken replies; live voice conversations later.
- Selected: React Native for Android and iOS, with Android the launch priority.
- Selected: Hindi, English, and natural Hinglish for v1 text and voice conversations.
- Selected: v1 memory includes useful context, ongoing concerns, preferences, chosen actions/outcomes, and tentative patterns people can confirm or reject. Memory can be inspected, corrected, and deleted.
- Selected: separate conversations with shared personal memory; people can start a fresh discussion without re-explaining relevant life context.
- Latest decision: v1 uses the LLM's existing knowledge for Gita-inspired reflection; curated scripture and different sources are deferred. This supersedes the single-commentary selection. Avoid claims of verified scripture grounding or representation of every Hindu interpretation.
- Selected: everyday emotional support and decision-making, emphasizing candid advice and questions that help people figure things out themselves.

## Candid guidance angle

Founder direction: blunt, truthful advice and self-discovery, rather than generic reassurance. Truthfulness is an aspiration and evaluation criterion, not an infallibility claim.

Draft messages to test:
- “A space to be heard. A perspective that challenges you.”
- “Talk honestly. See your choices more clearly.”
- “Thoughtful questions. Straight answers. Your next step.”

Required behavior: listen and establish context, challenge reasoning or behavior respectfully, explain the basis of a challenge, accept correction, and leave decisions with the person. Do not equate bluntness with insults, blame, fabricated certainty, or a scripted conclusion the person must accept. Challenge timing selected: understand first, then challenge directly.
- Recorded: founder's original saarthi/friend and mythological supporting-character directions.
- Selected by founder: prototype an original relatable saarthi/friend first.
- Pending: specific name, tone, visual design, and backstory implementation.

## Character backstory and personal storytelling

Founder proposal: give the original saarthi a full backstory so people relate to the character. The character has imperfections, morally complicated choices, and learned maturity. It can share life incidents relevant to the person's problem, generated from established facts about its fictional life. The founder uses mythological figures as creative references for complexity; this does not establish a particular theological interpretation.

Selected by founder: a stable fictional biography and curated pivotal incidents, with constrained generation of supporting anecdotes.

- Define family, upbringing, work, relationships, turning points, mistakes, unresolved limitations, and how the character encountered Hindu philosophy.
- Define chronology, important people, and lessons learned; distinguish immutable facts from open narrative space.
- Permit new minor incidents only within that open space. Avoid inventing a major loss or identical trauma whenever the person mentions one.
- Establish the fictional AI identity in the character introduction; do not imply these are real human or model experiences.
- Anecdotes should be brief, occasional, and offered when useful. Return attention to the person's situation with a question, and allow skipping stories.
- Do not equate the character's outcome with what the person should do; different circumstances can justify different choices.
- Remember which anecdotes a person has heard and avoid repetition or contradictions.
- Test whether storytelling improves feeling understood and useful reflection, or comes across as manufactured or self-centered.

Draft positioning to test: “A thoughtful companion with a story of their own—and space for yours.” This describes a fictional character, not a real adviser.

Locked: constrained anecdotes within a fixed biography.

### Competence and relatability — clarification pending

The founder is unsure about the character being wrong about things. Do not treat earlier proposals for blind spots or continuing imperfections as approved persona traits.

Distinguish past learning experiences, present emotional struggles, and unreliable guidance. Proposed recommendation: the character is steady and thoughtful in present conversations, with relatability coming from the biography and ordinary human pressures. Past mistakes are an optional backstory choice still to confirm. Do not deliberately generate incorrect advice to make the character seem human.

Actual AI fallibility remains an implementation concern: the guide must invite correction of its interpretation, avoid fabricated scripture, and acknowledge uncertainty where appropriate. A calm persona must not be marketed as infallible.

Selected by founder: relatability through difficult situations without emphasizing mistakes. Examples can reference Hindu scriptures rather than the character's own experiences.

Scope decision: detailed character backstory and generated personal anecdotes are a future feature. Preserve these ideas for later; do not make them MVP requirements or spend further discovery time on them now.

See [product discovery](product-discovery.md) for architecture, research sources, and the evolving product brief.
