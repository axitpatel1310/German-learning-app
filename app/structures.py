"""Sentence-structure cards: rewrite a sentence with a given connector or structure."""

import json
import random
import re
from dataclasses import dataclass, field

from app.data import DATA_DIR, LEVELS

STRUCTURES_FILE = DATA_DIR / "structures.json"


@dataclass
class Card:
    level: str
    kind: str
    cue: str  # the connector or structure to use, e.g. "sowohl … als auch"
    prompt: str
    answer: str
    en: str
    tip: str
    alt: list[str] = field(default_factory=list)  # other correct answers


def _norm(text: str) -> str:
    """Ignore punctuation, spacing and the case of the first letter when comparing."""
    text = re.sub(r"[.,!?;:„“\"'«»–-]", " ", text)
    text = " ".join(text.split())
    return text[:1].lower() + text[1:]


class StructureDeck:
    """All cards, and a shuffled pile per level and kind that you draw from."""

    def __init__(self, rng: random.Random | None = None):
        data = json.loads(STRUCTURES_FILE.read_text(encoding="utf-8"))
        self.kinds: dict[str, str] = data["kinds"]
        self.cards = [Card(**c) for c in data["cards"]]
        self.rng = rng or random.Random()
        self.level = "ALL"
        self.kind = "ALL"
        self.pile: list[Card] = []
        self.current: Card | None = None
        self.drawn = 0
        self.shuffle()

    def matching(self, level: str | None = None, kind: str | None = None) -> list[Card]:
        level = self.level if level is None else level
        kind = self.kind if kind is None else kind
        return [c for c in self.cards
                if level in ("ALL", c.level) and kind in ("ALL", c.kind)]

    def levels(self) -> list[str]:
        return ["ALL", *(lvl for lvl in LEVELS if self.matching(lvl, "ALL"))]

    def kinds_for_level(self) -> list[str]:
        used = {c.kind for c in self.matching(kind="ALL")}
        return ["ALL", *(k for k in self.kinds if k in used)]

    def shuffle(self, level: str | None = None, kind: str | None = None):
        if level is not None:
            self.level = level
        if kind is not None:
            self.kind = kind
        if self.kind not in self.kinds_for_level():
            self.kind = "ALL"
        self.pile = self.matching()
        self.rng.shuffle(self.pile)
        self.current = None
        self.drawn = 0

    def draw(self) -> Card | None:
        self.current = self.pile.pop() if self.pile else None
        self.drawn += self.current is not None
        return self.current

    @property
    def size(self) -> int:
        return self.drawn + len(self.pile)

    @staticmethod
    def check(card: Card, attempt: str) -> bool:
        return _norm(attempt) in {_norm(a) for a in (card.answer, *card.alt)}
