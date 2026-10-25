# Hindi/English script adherence — 2026-10-25

Production prompt updated: Hindi words use Devanagari; English words use Latin script. English-only preferences remain supported. Romanized input, earlier assistant replies and a request for Roman Hindi do not override the script rule. Existing prompt examples were updated to match.

## Method

- Seven synthetic development checkpoints in `../script-checkpoints.json`; one reply each, no simulator, no automated judge or retries.
- Actual product `saarthi.reply` for six cases and `saarthi.stream` for the voice case.
- Model: `openrouter/openai/gpt-6-luna`; provider: `openai`, no fallback; reasoning: `low`; output cap: 4096; timeout: 60 seconds.
- Production prompt SHA-256: `076cc5ed5c0951d4e9e1b539aec3b705b8f0e09be702943dffa212a7c783b747`.
- Endpoint prices refreshed before this run; $0.05 stage cap and existing $4 round reservation guard retained.
- Manual Codex review: 7/7 generated replies adhere to the requested script rule. This is a small sample, not guaranteed enforcement. Proper names such as Aman were left as supplied.

## Observed replies

### roman-hindi — script pass

अभी यह घबराहट काफ़ी भारी लग रही होगी। “सब आगे निकल गए” वाली बात किस वजह से उभरी—आज कुछ हुआ, या किसी से अपनी तुलना करते-करते मन वहाँ पहुँच गया?

### mixed-work — script pass

एक project पर खराब feedback मिलना, इस बात का सबूत नहीं कि तुम इस job के लायक नहीं हो। Manager ने किस बात पर feedback दिया—काम की quality, deadline, या कुछ और? उसमें शायद सुधार का साफ़ संकेत छिपा हो।

### hindi-script — script pass

गीता का मतलब यह नहीं कि फल की परवाह ही मत करो। मतलब है—अपना ध्यान उस काम पर रखो जो तुम्हारे हाथ में है: तैयारी, मेहनत और सही फ़ैसले; नतीजे पर पूरा क़ाबू तुम्हारे हाथ में नहीं होता।

फल की चिंता आए तो उसे दबाने के बजाय पूछो: “अभी इस काम को ठीक से करने के लिए मैं क्या कर सकता हूँ?” फिर उसी पर लौट आओ। लक्ष्य रखना ठीक है—बस अपनी शांति को नतीजे का बंधक मत बनाओ।

### english-only — script pass

Care about the work by giving your attention to what you can shape—your effort, choices, and craft—while remembering that results also depend on timing, other people, and chance. The Gita’s idea of acting without clinging to the outcome isn’t “don’t care”; it’s “let the outcome matter without letting it define you.”

When a result disappoints, try asking: “What does this teach me about the work?” rather than “What does this prove about me?”

### legacy-roman-history — script pass

खराब feedback का डर समझ आता है—पर feedback project पर होगा, तुम्हारी पूरी काबिलियत पर नहीं। क्या पहले कभी किसी के feedback ने तुम्हें चौंकाया हो, अच्छा या बुरा?

### roman-script-request — script pass

अरे, बढ़िया! Interview में ऐसा क्या हुआ जिससे तुम्हें लगा कि बात अच्छी बनी?

### voice-mixed — script pass

अरे वाह, Aman—project launch होना बड़ी बात है! अब launch के बाद वाला इंतज़ार शुरू: email बार-बार check करने का मन हो रहा है, या तुम आराम से feedback आने दे रहे हो?

## Validation and limits

- `uv run --group evals pytest -q tests/test_agents.py evals/tests/test_screen.py`: 39 passed, 1 skipped, 1 failed.
- Existing failure: `test_luna_omits_temperature_without_eval_hooks` asserts no `extra_body`, but the existing Luna preset pins provider `openai`, which adds provider routing. This test passes the literal instruction `prompt` and does not use the modified Saarthi prompt. Its unrelated expectation was left unchanged.
- Ruff and `git diff --check` passed.
- Voice response streaming was checked as text; microphone, STT, TTS pronunciation and audio playback were not tested. No deployment or running-server restart was performed.
- Prompt guidance governs generation; no post-generation transliterator or script filter was added. No broad quality, safety or long-conversation regression suite was run.
- Retained worst-case reservation: $0.026398; per-call token-cost estimate: $0.0020791, with usage available for every call.
- Immediate account usage delta: $0.00051869. Counters can lag; the token estimate is not a billed total.

## Raw local artifacts

`evals/runs/20261020-budget-round/script-adherence-20261025/screen/` contains the exact prompt, source snapshots, fixtures, responses, routing plan, usage ledger and run metadata. Raw artifacts remain ignored; this report preserves all seven replies for review.
