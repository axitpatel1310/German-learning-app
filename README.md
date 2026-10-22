# Deutsch mit Geschichten

A Flet app for German exam prep: graded stories from A1 to C2. Tap any word to see its
meaning and an example sentence, and save words to **My Words** to review later. **Word
search** looks up any dictionary word, and the **Gap game** hides one word in an example
sentence for you to pick from four options.

## Setup

Requires Python 3.10 or newer.

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

## Run

```bash
python main.py                # desktop window
flet run --web main.py        # in the browser
```

## Project layout

```
main.py                 app entry point and routing
app/data.py             loads stories and the dictionary, tokenizer, word lookup
app/views.py            home, level, story-reader, My Words, word search and gap game screens
app/game.py             gap game: builds questions and distractors from example sentences
app/storage.py          saved words (My Words), stored as JSON on the device
app/theme.py            level names and colours
app/splash.py           intro animation shown on start (Skip button, auto-continues after 10 s)
assets/intro.webp       the Sprach Up intro video as an animated WebP (no sound)
data/stories/*.json     stories, one file per level
data/dictionary/*.txt   dictionary entries: word | lemma | pos | english | example_de | example_en
tools/check_coverage.py lists story words that have no dictionary entry
communication.md        daily feature notes and review feedback
```

## Your data

No account or login. Saved words go to `my_words.json` in the app's data folder: the folder
Flet provides for packaged desktop/mobile apps (`FLET_APP_STORAGE_DATA`), or
`~/.deutsch-mit-geschichten/` when running from source. Delete that file to start over.

## Adding a story

1. Add an object to `data/stories/<level>.json` with `id`, `title`, `title_en`,
   `summary_en` and `paragraphs`.
2. Run `python tools/check_coverage.py` to list the words that still need entries.
3. Add those words to `data/dictionary/<level>.txt`. The file decides the word's level in
   the gap game (`00_core.txt` counts as A1), so put new words in the story's level file.

A story can also have an optional `"glossary"` object. It overrides the dictionary for that
story only, which is useful when a word means something special in that context:

```json
"glossary": { "bank": { "lemma": "die Bank", "pos": "noun (f)", "english": "bench",
                        "example_de": "Wir sitzen auf der Bank.", "example_en": "We sit on the bench." } }
```

## Troubleshooting

**The app window stays blank or "Working..." never finishes.** An old `msgpack-python`
package in your global Python can shadow the `msgpack` that Flet needs. Use a virtual
environment (see Setup), or fix the global install:

```bash
pip uninstall -y msgpack-python
pip install --force-reinstall msgpack
```
