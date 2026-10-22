"""Fill-the-gap game: a dictionary example sentence with one word hidden."""

import random
import re
from dataclasses import dataclass

from app.data import LEVELS, Entry, Library

GAP = "_____"
WORD_CLASSES = ("noun", "verb", "adjective", "adverb")


@dataclass
class Question:
    entry: Entry
    before: str
    after: str
    options: list[str]  # shuffled, one of them is entry's form in the sentence
    answer: str


def _word_class(entry: Entry) -> str:
    return entry.pos.split()[0] if entry.pos else ""


class GapGame:
    """Builds questions from example sentences, per level, with same-kind distractors."""

    def __init__(self, lib: Library, rng: random.Random | None = None):
        self.lib = lib
        self.rng = rng or random.Random()
        self._pools: dict[str, list[tuple[Entry, re.Match]]] = {}

    def pool(self, level: str) -> list[tuple[Entry, re.Match]]:
        if level not in self._pools:
            items = []
            for e in self.lib.dictionary.values():
                if level != "ALL" and e.level != level:
                    continue
                if _word_class(e) not in WORD_CLASSES or len(e.word) < 3 or "-" in e.word:
                    continue
                matches = list(re.finditer(rf"\b{re.escape(e.word)}\b", e.example_de, re.I))
                if len(matches) == 1:
                    items.append((e, matches[0]))
            self._pools[level] = items
        return self._pools[level]

    def question(self, level: str = "ALL") -> Question | None:
        items = self.pool(level)
        if not items:
            return None
        entry, m = self.rng.choice(items)
        answer = m.group()
        options = self._distractors(entry, items, answer) + [answer]
        self.rng.shuffle(options)
        return Question(
            entry, entry.example_de[: m.start()], entry.example_de[m.end() :], options, answer
        )

    def _distractors(self, entry: Entry, items, answer: str, n: int = 3) -> list[str]:
        # Prefer words with the very same part of speech ("verb (past)", "noun (f), plural"),
        # so the options look alike and grammar alone doesn't give the answer away.
        taken = {answer.lower(), entry.lemma.lower()}
        exact, loose = [], []
        for other, _ in self.rng.sample(items, min(len(items), 400)):
            if other.word in taken or other.lemma.lower() in taken:
                continue
            if other.pos == entry.pos:
                exact.append(other)
            elif _word_class(other) == _word_class(entry):
                loose.append(other)
        picks = []
        for other in exact + loose:
            # Match the answer's capital letter (sentence start), so case gives nothing away.
            form = other.word[:1].upper() + other.word[1:] if answer[:1].isupper() else other.display
            if form.lower() not in taken:
                taken.add(form.lower())
                taken.add(other.lemma.lower())
                picks.append(form)
            if len(picks) == n:
                break
        return picks


def level_choices() -> list[str]:
    return ["ALL", *LEVELS]
