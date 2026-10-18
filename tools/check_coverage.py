"""List every word in the stories that has no dictionary entry.

Run from the project root:  python tools/check_coverage.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data import WORD_RE, Library  # noqa: E402


def main() -> int:
    lib = Library()
    missing: dict[str, list[str]] = {}
    for stories in lib.stories.values():
        for story in stories:
            for para in story.paragraphs:
                for word in WORD_RE.findall(para):
                    if lib.lookup(word, story) is None:
                        missing.setdefault(word.lower(), [])
                        if story.id not in missing[word.lower()]:
                            missing[word.lower()].append(story.id)

    total = len(lib._by_id)
    print(f"{total} stories, {len(lib.dictionary)} dictionary entries")
    if not missing:
        print("All words covered.")
        return 0
    print(f"{len(missing)} words missing:")
    for word in sorted(missing):
        print(f"  {word}  ({', '.join(missing[word])})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
