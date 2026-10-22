"""Loading stories and the dictionary from the data/ folder."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STORIES_DIR = DATA_DIR / "stories"
DICTIONARY_DIR = DATA_DIR / "dictionary"

LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]

# A word is a run of letters, optionally joined by hyphens (E-Mail, Start-up).
# [^\W\d_] means "any Unicode letter", so ä, ß, é (Café) all count.
WORD_RE = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*")


@dataclass
class Entry:
    word: str
    lemma: str
    pos: str
    english: str
    example_de: str
    example_en: str
    level: str = ""  # from the dictionary file name, e.g. b1.txt -> B1

    @property
    def display(self) -> str:
        """The word as written in a text: dictionary keys are lowercase, nouns are not."""
        if self.pos.startswith(("noun", "proper noun")):
            return self.word[:1].upper() + self.word[1:]
        return self.word


@dataclass
class Story:
    id: str
    level: str
    title: str
    title_en: str
    summary_en: str
    paragraphs: list[str]
    # Optional per-story overrides, same shape as dictionary entries.
    glossary: dict[str, Entry] = field(default_factory=dict)

    @property
    def word_count(self) -> int:
        return sum(len(WORD_RE.findall(p)) for p in self.paragraphs)

    @property
    def minutes(self) -> int:
        # Learners read far slower than natives; ~80 words/min is a fair guess.
        return max(1, round(self.word_count / 80))


def tokenize(text: str) -> list[tuple[str, bool]]:
    """Split text into (chunk, is_word) pieces, keeping punctuation and spaces."""
    pieces = []
    pos = 0
    for m in WORD_RE.finditer(text):
        if m.start() > pos:
            pieces.append((text[pos : m.start()], False))
        pieces.append((m.group(), True))
        pos = m.end()
    if pos < len(text):
        pieces.append((text[pos:], False))
    return pieces


def load_dictionary(folder: Path = DICTIONARY_DIR) -> dict[str, Entry]:
    """Parse every data/dictionary/*.txt file.

    Each line: `word | lemma | pos | english | example_de | example_en`.
    Blank lines and lines starting with # are ignored.
    """
    entries: dict[str, Entry] = {}
    for path in sorted(folder.glob("*.txt")):
        level = path.stem.upper() if path.stem.upper() in LEVELS else "A1"
        for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) != 6:
                print(f"{path.name}:{lineno}: expected 6 fields, got {len(parts)}")
                continue
            entry = Entry(*parts, level=level)
            key = entry.word.lower()
            if key in entries:
                print(f"{path.name}:{lineno}: duplicate entry '{key}'")
            entries[key] = entry
    return entries


def _entry_from_dict(word: str, d: dict) -> Entry:
    return Entry(
        word=word,
        lemma=d.get("lemma", word),
        pos=d.get("pos", ""),
        english=d.get("english", ""),
        example_de=d.get("example_de", ""),
        example_en=d.get("example_en", ""),
    )


def load_stories() -> dict[str, list[Story]]:
    by_level: dict[str, list[Story]] = {lvl: [] for lvl in LEVELS}
    for lvl in LEVELS:
        path = STORIES_DIR / f"{lvl.lower()}.json"
        if not path.exists():
            continue
        for d in json.loads(path.read_text(encoding="utf-8")):
            glossary = {
                w.lower(): _entry_from_dict(w, g) for w, g in d.get("glossary", {}).items()
            }
            by_level[lvl].append(
                Story(
                    id=d["id"],
                    level=lvl,
                    title=d["title"],
                    title_en=d.get("title_en", ""),
                    summary_en=d.get("summary_en", ""),
                    paragraphs=d["paragraphs"],
                    glossary=glossary,
                )
            )
    return by_level


_FOLD = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss"})
_LEMMA_PREFIX = re.compile(r"^(der|die|das|sich)\s+")


def fold(text: str) -> str:
    """Lowercase and drop umlauts, so 'uber' finds 'über' and 'strasse' finds 'Straße'."""
    return text.lower().translate(_FOLD)


class Library:
    def __init__(self):
        self.stories = load_stories()
        self.dictionary = load_dictionary()
        self._by_id = {s.id: s for lst in self.stories.values() for s in lst}
        self._search_index: list[tuple[str, str, str, Entry]] | None = None
        self._word_stories: dict[str, list[Story]] | None = None

    def get_story(self, story_id: str) -> Story | None:
        return self._by_id.get(story_id)

    def lookup(self, word: str, story: Story | None = None) -> Entry | None:
        key = word.lower()
        if story and key in story.glossary:
            return story.glossary[key]
        return self.dictionary.get(key)

    def search(self, query: str, limit: int = 50) -> list[Entry]:
        """Dictionary search: exact word, then word or base form starting with the
        query, then English meanings containing it as a word."""
        q = fold(query.strip())
        if not q:
            return []
        if self._search_index is None:
            self._search_index = [
                (fold(e.word), _LEMMA_PREFIX.sub("", fold(e.lemma)), e.english.lower(), e)
                for e in self.dictionary.values()
            ]
        english_re = re.compile(r"\b" + re.escape(query.strip().lower()))
        ranked = []
        for word, lemma, english, entry in self._search_index:
            if word == q:
                rank = 0
            elif lemma == q:
                rank = 1
            elif word.startswith(q) or lemma.startswith(q):
                rank = 2
            elif english_re.search(english):
                rank = 3
            else:
                continue
            ranked.append((rank, len(word), word, entry))
        ranked.sort(key=lambda t: t[:3])
        return [t[3] for t in ranked[:limit]]

    def stories_with(self, word: str) -> list[Story]:
        """Stories that use this exact word form, easiest level first."""
        if self._word_stories is None:
            self._word_stories = {}
            for stories in self.stories.values():
                for story in stories:
                    for para in story.paragraphs:
                        for w in WORD_RE.findall(para):
                            found = self._word_stories.setdefault(w.lower(), [])
                            if not found or found[-1] is not story:
                                found.append(story)
        return self._word_stories.get(word.lower(), [])
