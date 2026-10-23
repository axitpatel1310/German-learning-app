"""Word scroll: one word card at a time, swiped like a social media feed. Words you haven't
seen yet come first; the ones you've seen are remembered in feed.json on this device."""

import json
import random

from app.data import KEY_WORD_CLASSES, Entry, Library, lemma_key
from app.storage import MyWords, user_data_dir

MAX_SEEN = 20000
SOURCES = ["ALL", "A1", "A2", "B1", "B2", "C1", "C2", "MINE"]


def feed_entries(lib: Library, level: str) -> list[Entry]:
    """Base forms of nouns, verbs and adjectives with an example sentence."""
    return [
        e for e in lib.dictionary.values()
        if (level == "ALL" or e.level == level)
        and e.pos.startswith(KEY_WORD_CLASSES)
        and lemma_key(e) == e.word.lower()
        and e.example_de and e.english and "/" not in e.lemma
    ]


def headword(entry: Entry) -> str:
    """'die Miete' for nouns, the word itself for everything else."""
    lemma = entry.lemma
    return lemma if lemma and lemma.lower().endswith(" " + entry.word.lower()) else entry.display


class WordFeed:
    def __init__(self, lib: Library, my_words: MyWords, rng: random.Random | None = None):
        self.lib = lib
        self.my_words = my_words
        self.rng = rng or random.Random()
        self.path = user_data_dir() / "feed.json"
        try:
            self.seen: list[str] = list(json.loads(self.path.read_text(encoding="utf-8")).get("seen", []))
        except (FileNotFoundError, ValueError, AttributeError):
            self.seen = []
        self._seen = set(self.seen)
        self.source = "ALL"
        self.deck: list[Entry] = []
        self.index = 0
        self.shuffle()

    def shuffle(self, source: str | None = None):
        """A new deck for a level (or "MINE" for My Words): unseen words first, in random order."""
        self.source = source or self.source
        if self.source == "MINE":
            entries = [self.lib.lookup(d["word"]) for d in self.my_words.all()]
            entries = [e for e in entries if e]
            self.rng.shuffle(entries)
        else:
            entries = feed_entries(self.lib, self.source)
            self.rng.shuffle(entries)
            entries.sort(key=lambda e: e.word in self._seen)  # stable: stays random inside each part
        self.deck, self.index = entries, 0
        if self.deck:
            self.mark_seen()

    @property
    def current(self) -> Entry | None:
        return self.deck[self.index] if self.deck else None

    @property
    def new_left(self) -> int:
        return sum(1 for e in self.deck[self.index + 1:] if e.word not in self._seen)

    def move(self, step: int) -> bool:
        """Next (+1) or previous (-1) card. False at either end of the deck."""
        i = self.index + step
        if not 0 <= i < len(self.deck):
            return False
        self.index = i
        self.mark_seen()
        return True

    def mark_seen(self):
        word = self.deck[self.index].word
        if word in self._seen or self.source == "MINE":
            return
        self._seen.add(word)
        self.seen.append(word)
        if len(self.seen) > MAX_SEEN:
            self._seen.discard(self.seen.pop(0))
        self._save()

    def _save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"seen": self.seen}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)
