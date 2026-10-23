"""Word wallpaper and word widget (Android): their settings, and the word cards sent to them.

Both are native Android code in extensions/flet_word_wallpaper. The wallpaper shows one card
at a time and moves on each time the screen is turned on; the home-screen widget moves on
every 30 minutes or when its arrow is tapped. Each has its own word choice and style.
"""

import json
import random
from typing import Optional

import flet as ft

from app.data import KEY_WORD_CLASSES, LEVELS, Entry, Library, lemma_key
from app.storage import MyWords, user_data_dir

MAX_WORDS = 1500  # "All levels" is sampled down to this, the native side reads it all at once

DEFAULTS = {"source": "level", "level": "A1", "topic": "wohnen", "theme": "light", "enabled": False}


@ft.control("WordWallpaper")
class WordWallpaper(ft.Service):
    """Bridge to the Android plugin (wallpaper and widget). Every call answers False on
    other platforms."""

    async def is_supported(self) -> bool:
        return bool(await self._invoke_method("is_supported"))

    async def set_words(self, payload: dict) -> bool:
        data = json.dumps(payload, ensure_ascii=False)
        return bool(await self._invoke_method("set_words", {"json": data}, timeout=30))

    async def open_picker(self) -> bool:
        return bool(await self._invoke_method("open_picker"))

    async def is_active(self) -> bool:
        return bool(await self._invoke_method("is_active"))

    async def set_widget_words(self, payload: dict) -> bool:
        data = json.dumps(payload, ensure_ascii=False)
        return bool(await self._invoke_method("set_widget_words", {"json": data}, timeout=30))

    async def pin_widget(self) -> bool:
        return bool(await self._invoke_method("pin_widget"))

    async def widget_count(self) -> int:
        return int(await self._invoke_method("widget_count") or 0)


def is_android(page: ft.Page) -> bool:
    return page.platform == ft.PagePlatform.ANDROID and not page.web


class WallpaperSettings:
    """Which words the wallpaper (or widget) shows and in which style, kept in a JSON file."""

    def __init__(self, filename: str = "wallpaper.json"):
        self.path = user_data_dir() / filename
        self.values = dict(DEFAULTS)
        try:
            self.values.update(json.loads(self.path.read_text(encoding="utf-8")))
        except (FileNotFoundError, ValueError, TypeError):
            pass

    def __getitem__(self, key: str):
        return self.values[key]

    def set(self, **changes):
        self.values.update(changes)
        self.path.write_text(json.dumps(self.values, indent=1), encoding="utf-8")


def _headword(word: str, lemma: str) -> str:
    """'die Miete' for nouns, the base form for everything else."""
    if lemma and lemma.lower().endswith(" " + word.lower()):
        return lemma
    return lemma or word


def _card(entry: Entry, level: str) -> dict:
    return {
        "headword": _headword(entry.display, entry.lemma),
        "tag": f"{level} · {entry.pos}" if level else entry.pos,
        "english": entry.english,
        "example_de": entry.example_de,
        "example_en": entry.example_en,
    }


def level_cards(lib: Library, level: str, rng: Optional[random.Random] = None) -> list[dict]:
    """Base forms (nouns, verbs, adjectives) from a level's dictionary file."""
    entries = [
        e for e in lib.dictionary.values()
        if (level == "ALL" or e.level == level)
        and e.pos.startswith(KEY_WORD_CLASSES)
        and lemma_key(e) == e.word.lower()
        and e.example_de and e.english and "/" not in e.lemma
    ]
    if len(entries) > MAX_WORDS:
        entries = (rng or random.Random()).sample(entries, MAX_WORDS)
    return [_card(e, e.level) for e in entries]


def topic_cards(lib: Library, topic: str) -> list[dict]:
    cards = []
    for entry, stories in lib.topic_words(topic):
        first = min((s.level for s in stories), key=LEVELS.index)
        cards.append(_card(entry, first))
    return cards


def my_word_cards(my_words: MyWords) -> list[dict]:
    return [
        {
            "headword": _headword(d["word"], d.get("lemma", "")),
            "tag": " · ".join(x for x in (d.get("level", ""), d.get("pos", "")) if x),
            "english": d.get("english", ""),
            "example_de": d.get("example_de", ""),
            "example_en": d.get("example_en", ""),
        }
        for d in my_words.all()
    ]


def build_cards(lib: Library, my_words: MyWords, settings: WallpaperSettings) -> list[dict]:
    if settings["source"] == "my_words":
        return my_word_cards(my_words)
    if settings["source"] == "topic":
        return topic_cards(lib, settings["topic"])
    return level_cards(lib, settings["level"])


def payload(cards: list[dict], settings: WallpaperSettings) -> dict:
    return {"theme": settings["theme"], "words": cards}
