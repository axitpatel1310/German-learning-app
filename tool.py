"""Helpers: merge story batches, list missing words, append dictionary chunks.

python tool.py merge b1 batch.json
python tool.py missing [limit]
python tool.py dict b1 chunk.txt
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(r"Z:\German Language App")
sys.path.insert(0, str(ROOT))
from app.data import WORD_RE, Library, load_dictionary  # noqa: E402


def merge(level, batch):
    path = ROOT / "data" / "stories" / f"{level}.json"
    stories = json.loads(path.read_text(encoding="utf-8"))
    new = json.loads(Path(batch).read_text(encoding="utf-8"))
    titles = {s["title"] for s in stories}
    n = len(stories)
    for s in new:
        assert s["title"] not in titles, s["title"]
        for k in ("title", "title_en", "summary_en", "paragraphs"):
            assert s.get(k), (s.get("title"), k)
        n += 1
        story = {"id": f"{level}-{n:03d}"}
        story.update(s)
        stories.append(story)
        titles.add(s["title"])
    path.write_text(json.dumps(stories, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{level}: {len(stories)} stories (+{len(new)})")


def missing(limit=10**9):
    lib = Library()
    seen = {}
    for stories in lib.stories.values():
        for story in stories:
            for para in story.paragraphs:
                for sent in re.split(r"(?<=[.!?“])\s+", para):
                    for w in WORD_RE.findall(sent):
                        k = w.lower()
                        if lib.lookup(w, story) is None and k not in seen:
                            seen[k] = (w, story.id, sent)
    print(len(seen), "missing")
    for i, (k, (w, sid, sent)) in enumerate(seen.items()):
        if i >= limit:
            break
        print(w, sid[3:], end=", ")


def add_dict(level, chunk):
    existing = load_dictionary()
    lines = Path(chunk).read_text(encoding="utf-8").splitlines()
    out, keys, bad = [], set(), 0
    for line in lines:
        if not line.strip() or line.startswith("#"):
            out.append(line)
            continue
        parts = [p.strip() for p in line.split("|")]
        k = parts[0].lower()
        if len(parts) != 6 or not all(parts) or parts[0] != k:
            print("BAD:", line)
            bad += 1
        elif k in existing or k in keys:
            print("DUP:", k)
            bad += 1
        keys.add(k)
        out.append(" | ".join(parts))
    if bad:
        print(bad, "problems; nothing written")
        return
    path = ROOT / "data" / "dictionary" / f"{level}.txt"
    with path.open("a", encoding="utf-8") as f:
        f.write("\n" + "\n".join(out) + "\n")
    print(f"added {len(keys)} entries to {path.name}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1]
    if cmd == "merge":
        merge(sys.argv[2], sys.argv[3])
    elif cmd == "missing":
        missing(int(sys.argv[2]) if len(sys.argv) > 2 else 10**9)
    elif cmd == "dict":
        add_dict(sys.argv[2], sys.argv[3])
