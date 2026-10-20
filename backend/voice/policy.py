"""Pure interruption and conservative delivery policy, independent of providers."""

import re
import unicodedata
from dataclasses import dataclass, field

ACKS = {
    "hmm",
    "hm",
    "hmmm",
    "mhm",
    "uh huh",
    "haan",
    "han",
    "ha",
    "achha",
    "acha",
    "okay",
    "ok",
    "हां",
    "हाँ",
    "हूँ",
    "अच्छा",
    "जी",
}


def normalized(text):
    value = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(
        "".join(
            c for c in value if c.isspace() or unicodedata.category(c)[0] in {"L", "M", "N"}
        ).split()
    )


def acknowledgment(text):
    return normalized(text) in ACKS


@dataclass
class Delivery:
    text: str = ""
    sent_seconds: float = 0
    # (word end in synthesized audio, character offset in original agent text)
    words: list[tuple[float, int]] = field(default_factory=list)
    matched: int = 0
    aligned: bool = True

    def timestamps(self, words, ends):
        if not self.aligned:
            return
        for word, end in zip(words, ends, strict=True):
            match = re.search(r"\S+", self.text[self.matched :])
            if not match or normalized(match.group()) != normalized(word):
                # Numbers/normalization can differ: under-count instead of guessing heard text.
                self.aligned = False
                return
            self.matched += match.end()
            self.words.append((float(end), self.matched))

    def prefix(self, margin=0.35):
        cutoff = max(0, self.sent_seconds - margin)
        offsets = [offset for end, offset in self.words if end <= cutoff]
        return self.text[: max(offsets, default=0)].rstrip()
