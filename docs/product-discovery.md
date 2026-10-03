# Product discovery — working brief

Updated: 2026-10-03. This is an evolving proposal, not a finalized specification.

## Confirmed founder direction

- Audience: religiously inclined Hindu adults aged 25–40, with everyday life problems and insufficient space to feel heard.
- Initial knowledge source: Bhagavad Gita.
- Desired experience: text/chat/voice, a spiritually inspired companion, and personalized guidance informed by previous conversations.
- Intended benefit: help people reflect on their situation and discover practical next steps.
- Creative references: Krishna's reflective segments in Star Plus's Mahabharat and the philosopher–youth dialogue in The Courage to Be Disliked.
- Character directions explored: a relatable original saarthi/friend with Hindu knowledge and maturity, or a wise mythological supporting character other than Krishna.
- Founder selected the relatable original saarthi/friend for the first prototype.
- Founder proposed a full fictional backstory and relevant personal anecdotes generated from established character facts, and selected a fixed biography with constrained anecdote generation.
- Founder is unsure about portraying the character as wrong. Past mistakes, present emotional struggles, and fallible guidance need to be distinguished; blind spots and continuing imperfections are not locked persona requirements.
- Founder selected relatability through difficult situations without emphasizing character mistakes. Illustrations can come from Hindu scriptures; they do not need to be autobiographical.
- Founder explicitly deferred detailed backstory and anecdote generation to a future feature. They are outside the initial build and must not drive MVP architecture.
- Launch interaction selected: v1 text chat, voice notes, and spoken replies. Live voice conversations with text fallback are a later phase.
- Client platform selected: React Native targeting Android and iOS, with Android prioritized for launch and validation. The iOS release timeline is not yet specified.
- V1 conversation languages selected: Hindi and English, including natural Hinglish, for typed input, voice notes, and spoken replies. Provider quality for mixed-language speech must be evaluated; no provider is selected yet.
- V1 cross-session memory selected: useful personal context, ongoing concerns, preferences, chosen actions and outcomes, and tentative patterns for user confirmation or rejection. People can inspect, correct, and delete memories. A detailed life timeline and relationship graph are outside the initial memory scope.
- Conversation organization selected: separate conversations with shared personal memory. New conversations retain their own message history; relevant user-level memories can inform guidance across conversations.
- Latest founder decision supersedes the earlier single-commentary plan: defer curated scripture ingestion, commentary selection, and source retrieval. V1 uses the LLM's existing knowledge and reasoning for Gita-inspired reflection. Add curated and potentially multiple sources in a later phase.
- V1 source limitation: guidance and any source references are unverified unless independently checked. Do not advertise source-verified scripture grounding, invent exact quotations or verse numbers, or present model interpretations as authoritative Hindu consensus. Verified quotations are not a v1 promise.
- Guidance scope selected: everyday emotional support and decision-making. Founder prioritizes candid, direct advice and questions that help people reach their own conclusions; generic reassurance and making decisions for people are not the desired experience. The request for “true” advice is a quality goal, not a guarantee of model correctness.
- Scope interpretation: no diagnosis or treatment offering. Earlier option 1 included responding supportively to serious distress and helping people connect with appropriate human support. Detailed handling remains to be specified.

Marketing angles, draft messaging, and character exploration are tracked separately in [marketing and product angles](marketing-and-product-angles.md).

## Proposed promise

A companion that listens, remembers what you choose to share, helps you examine your situation, and offers Gita-inspired perspectives and practical next steps.

The AI's treatment effectiveness is unproven. Do not describe it as a qualified therapist or its output as divine instruction. These are proposed product boundaries to discuss with the founder.

## Proposed conversation flow

1. Listen; establish whether the person wants space to speak or help exploring the problem.
2. Clarify the situation with one relevant question at a time.
3. Separate reported events, feelings, interpretations, and constraints.
4. Offer a tentative reframe, inviting disagreement.
5. Offer a relevant Gita-inspired perspective without forcing scripture into every response. V1 relies on model knowledge; reviewed passages and provenance are deferred.
6. Let the person choose a realistic next step.
7. Optionally close with a short original audio reflection.
8. With permission, remember the useful context and follow up on the chosen action.

These stages should be adaptive, not a compulsory interrogation script. The companion must be able to revise its interpretation.

Tone selected: understand first, then challenge directly. Establish enough context before challenging assumptions; distinguish reported facts from interpretations; challenge specific reasoning or behavior rather than insult the person. Do not invent motives, diagnose, or state uncertain interpretations as truth. Let the person disagree and choose their own next step.

## Proposed personal memory

| Type | Example | Handling |
| --- | --- | --- |
| User-reported fact | Living with parents | Store source message, date, and who reported it |
| Preference | Prefers Hindi and concise replies | Editable by the user |
| Active concern | Considering a job change | Track status and updated constraints |
| Tentative pattern | Conflict sometimes follows agreeing reluctantly | Require multiple supporting examples; ask the user whether it fits |
| Chosen action and outcome | Tried discussing workload | Follow up and learn from reported result |

Store reported claims about other people as claims, not established truth. Do not infer diagnoses. Tentative patterns must not silently become facts. Support correction, rejection, expiration, and deletion, including derived summaries and retrieval entries. Memory must be optional.

## Proposed architecture

The implemented v1 boundaries, connections, and data model are in [architecture-lean-candidate.md](architecture-lean-candidate.md). The earlier 17-table proposal in [architecture-v1.md](architecture-v1.md) is historical and superseded.

The v1 code uses a modular Expo app, FastAPI, one Google ADK agent, and PostgreSQL with pgvector. Email sign-in uses one-time codes, ElevenLabs handles voice, and conversation events live in ADK's database session service. Audio is not stored by the app; there is no object store or background worker.

React Native targets Android and iOS, with Android first. The assistant uses the model's existing knowledge in v1; curated scripture ingestion and citations remain deferred.

- Conversation module: sessions, turns, streaming, text and voice transport.
- V1 voice flow: recorded message → transcription → the shared guidance flow → text response → optional speech synthesis. Preserve the same conversation and memory logic for future live voice; defer live-call transport and interruption handling.
- Guidance module: relevant personal memory retrieval, conversation-stage selection, LLM generation from its existing knowledge, and sensitive-situation handling. Future curated source retrieval should enter as optional context rather than require rewriting conversations or memory.
- Memory module: extraction, evidence, confirmation, correction, forgetting, and per-user retrieval.
- Scripture module (deferred): source editions, verse identifiers, reviewed translations/commentary, topic mappings, rights/provenance, content versioning, and verified citations. Do not build this ingestion/retrieval pipeline for v1.
- Reflection module: original short summaries and optional audio.
- Future character storytelling capability (deferred): versioned biography, curated incidents, narrative constraints, anecdote generation and consistency checks, and per-user story exposure. Do not build this in the MVP. Keep fictional character material separate from scripture and personal user memory when introduced.
- Account module: authentication, consent, billing, entitlements, usage accounting, and deletion workflows.
- Quality module: restricted review access and evaluations for source accuracy, useful questioning, memory fidelity, harmful advice, and language quality.

The first implementation owns four tables: users, conversations, memories, and short-lived auth codes. ADK manages dialogue event tables. Billing, detailed timelines, durable jobs, and source-corpus tables remain future work.

Use explicit user ownership for every personal record. Private chats disable shared memory. Voice notes are sent for transcription and discarded; spoken replies are temporary playback files in the phone cache.

V1 flow: input → relevant private context → adaptive LLM dialogue with Gita-inspired framing → response checks → text/voice output → proposed memory updates → optional follow-up. Later, add curated source context before generation and source verification before output.

## Commercial hypotheses to test

- People will return because of continuity and useful reflection, rather than only enjoying a spiritual voice once.
- A subscription covering bounded usage fits better than incentives to prolong conversations through per-minute billing.
- Original short reflections may attract users; repeat use and payment require a valuable conversation experience.
- Compare generic Gita answers, guided dialogue, and guided dialogue with memory. Compare text and voice separately.
- Interview people about recent behavior, then run a small repeated-use pilot and a real paid offer. Measure perceived understanding, source trust, useful actions, voluntary return, correction of memory, payment, and cost per retained paying user.

No price, retention threshold, or proven efficacy has been established.

## Research notes and limits

- Sri Mandir sells temple pujas and offerings alongside devotional content: https://www.srimandir.com/en-US
- AppsForBharat FY25 reporting: approximately ₹69.6 crore operating revenue and ₹45.3 crore net loss: https://inc42.com/buzz/appsforbharat-fy25-net-loss-widens-16-to-inr-45-cr/
- Astrotalk FY25 reporting: approximately ₹1,176 crore operating revenue and ₹285 crore adjusted profit before tax; this is not net profit: https://www.moneycontrol.com/news/business/startup/astrotalk-revenue-rises-85-to-rs-1-214-crore-in-fy25-13795476.html
- Separate reporting places Astrotalk FY25 profit after tax at approximately ₹33 crore: https://inc42.com/features/can-astrotalk-chart-a-future-beyond-astrology/
- Mahabharat series descriptions identify Sourabh Raaj Jain's Krishna and concluding philosophical segments: https://en.wikipedia.org/wiki/Mahabharat_%282013_TV_series%29
- One secondary account describes a Krishna Saar segment about justice, revenge, and self-examination: https://tellyreviews.com/2020/05/10/mahabharat-starplus/
- Publisher material describes The Courage to Be Disliked as five dialogues between a philosopher and a young man, based on Adlerian psychology: https://www.simonandschuster.net/books/The-Courage-to-Be-Disliked/Ichiro-Kishimi/9781501197277
- Research used public financial reporting, series descriptions, a segment account, and publisher material. It did not independently audit company accounts, watch all segments, or read the entire book. Popularity of these references does not establish clinical effectiveness or product demand.

## Next decision

Identity selected: an original relatable saarthi/friend. Future storytelling direction: constrained anecdotes within a stable biography, with relatability through difficult situations and scripture references; personal experience is optional. Detailed storytelling is deferred.

Interaction selected: v1 text chat with voice notes and spoken replies; live voice later. Client selected: React Native for Android and iOS, with Android priority. Languages selected: Hindi, English, and natural Hinglish for text and voice. Memory selected: useful context, ongoing concerns, preferences, chosen actions/outcomes, and tentative patterns users can confirm or reject, with inspection, correction, and deletion. Conversations selected: separate conversations with shared personal memory. Knowledge approach selected: use the LLM's existing knowledge for v1; curated and multiple sources later. Scope selected: everyday emotional support and decision-making, with candid guidance and self-discovery prioritized. Challenge timing selected: understand first, then challenge directly.

Founder requested an end to serial discovery questions and a move to architecture. That work has progressed into the initial build; use [architecture-lean-candidate.md](architecture-lean-candidate.md) for the current implementation.

Implementation choices for the first build: Expo React Native with a wide-screen sidebar and phone drawer; FastAPI and one ADK Runner; PostgreSQL with pgvector; first-party email OTP using SMTP in production; ElevenLabs for transcription and spoken replies. Supabase and Murf remain possible later substitutions. These choices are documented with their boundaries in [architecture-lean-candidate.md](architecture-lean-candidate.md).
