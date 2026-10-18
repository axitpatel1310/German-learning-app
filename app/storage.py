"""The learner's saved words ("My Words"), kept in a JSON file on this device."""

import json
import os
import time
from pathlib import Path

from app.data import Entry, Story


def user_data_dir() -> Path:
    # Packaged Flet apps (desktop and mobile) get a private storage folder via this
    # variable; when running from source we fall back to a folder in the home directory.
    base = os.environ.get("FLET_APP_STORAGE_DATA")
    path = Path(base) if base else Path.home() / ".deutsch-mit-geschichten"
    path.mkdir(parents=True, exist_ok=True)
    return path


class MyWords:
    """Saved words keyed by their lowercase surface form, newest first."""

    def __init__(self, path: Path | None = None):
        self.path = path or user_data_dir() / "my_words.json"
        self._items: dict[str, dict] = {}
        try:
            for d in json.loads(self.path.read_text(encoding="utf-8")):
                self._items[d["word"].lower()] = d
        except (FileNotFoundError, ValueError, KeyError, TypeError):
            pass

    def __len__(self) -> int:
        return len(self._items)

    def has(self, word: str) -> bool:
        return word.lower() in self._items

    def all(self) -> list[dict]:
        return sorted(self._items.values(), key=lambda d: d.get("saved_at", 0), reverse=True)

    def add(self, word: str, entry: Entry, story: Story | None = None):
        self._items[word.lower()] = {
            "word": word,
            "lemma": entry.lemma,
            "pos": entry.pos,
            "english": entry.english,
            "example_de": entry.example_de,
            "example_en": entry.example_en,
            "story_id": story.id if story else "",
            "level": story.level if story else "",
            "saved_at": time.time(),
        }
        self._save()

    def restore(self, item: dict):
        self._items[item["word"].lower()] = item
        self._save()

    def remove(self, word: str) -> dict | None:
        item = self._items.pop(word.lower(), None)
        self._save()
        return item

    def _save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.all(), ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)
