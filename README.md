# Deutsch mit Geschichten

A Flet app for German exam prep: graded stories from A1 to C2. Tap any word to see its
meaning and an example sentence, and save words to **My Words** to review later. **Word
search** looks up any dictionary word, and the **Gap game** hides one word in an example
sentence for you to pick from four options. **Word scroll** shows one word card at a time:
swipe up (or use the mouse wheel or arrow keys) for the next word and double-tap to save it. **Topics** groups the stories by exam theme
(Wohnen, Arbeit, Gesundheit …), with each topic's key words and a gap game for them. On
Android, the **Word widget** puts a glass word card on the home screen (a new word every 30
minutes, or tap its arrow), and the **Word wallpaper** shows a word card on the lock and home
screen with a new one each time the screen is turned on. The interface uses a frosted-glass
style with soft gradients and iOS-style page transitions, in light and dark mode.

You sign in with your phone number and a code sent on WhatsApp. The first 10 stories of each
level are free; **Premium** (€10 for 3 months) opens all of them. **Profile** shows your plan
and the time you've spent learning.

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
flet build apk                # Android app (includes the word widget and wallpaper)
```

The word widget and wallpaper only exist in the Android build. On desktop and web their
screens show a preview only.

### Sign-in codes on WhatsApp

Without configuration the app runs in **demo mode**: the code is shown on the sign-in screen
(and printed in the console). To send real codes on WhatsApp, create a
[Twilio Verify](https://www.twilio.com/docs/verify) service with the WhatsApp channel and set:

```bash
TWILIO_ACCOUNT_SID=AC...      # Twilio account
TWILIO_AUTH_TOKEN=...
TWILIO_VERIFY_SID=VA...       # the Verify service
```

These keys must not be shipped inside a public app build. For a release, use the accounts
server below. Without the server, Premium is a test flow (no money is charged). With it, Premium
is bought with **Stripe** on desktop/web or **Google Play** on Android, and the server confirms
each payment; see [server/README.md](server/README.md#setting-up-payments).

### Accounts server

`server/` is a small backend (standard library + SQLite). With it, the server sends and checks
the WhatsApp codes, keeps one account per phone number, stores the Premium plan, and keeps your
time stats across devices. It also sells ads: businesses book and pay on `/ads`, you approve
them on `/ads/admin`, and free users see them in the app until the booked views are reached
(see [server/README.md](server/README.md#ads)). Start it, then point the app at it with
`DMG_API_URL` (PowerShell):

```bash
python -m server --port 8600
$env:DMG_API_URL="http://127.0.0.1:8600"; python main.py
```

Without `DMG_API_URL` the app keeps everything on the device, as before. Settings, the API and
deployment notes are in [server/README.md](server/README.md); `python tools/test_server.py`
runs an end-to-end check.

## Project layout

```
main.py                 app entry point and routing
app/data.py             loads stories and the dictionary, tokenizer, word lookup
app/views.py            home, level, story-reader, My Words, word search, gap game and topic screens
app/glass.py            the glass look: light/dark themes, backdrop gradient, frosted panels
app/topics.py           the exam topics (key, German and English name, icon)
app/game.py             gap game: builds questions and distractors from example sentences
app/storage.py          saved words (My Words), stored as JSON on the device
app/account.py          the account (on this device, or on the accounts server), the Premium plan, time tracking
app/otp.py              phone numbers and sign-in codes (demo or Twilio WhatsApp), shared with the server
app/api.py              JSON client for the accounts server
app/billing.py          buying Premium: which provider on this device, and the Google Play bridge
app/feed.py             word scroll: the deck of word cards, unseen words first
app/feed_view.py        word scroll screen (swipe, wheel, keys, double-tap to save)
app/account_view.py     sign-in, Premium, locked-story and profile screens
app/theme.py            level names and colours
app/wallpaper.py        word wallpaper and widget: settings, the word cards, the bridge to Android
app/wallpaper_view.py   word wallpaper and word widget screens (choose words and style, preview)
extensions/flet_word_wallpaper/
                        Flet extension with the native Android live wallpaper and home-screen
                        widget (Kotlin), added to the APK by `flet build` via
                        [tool.flet.dev_packages]
extensions/flet_play_billing/
                        Flet extension for Google Play Billing (Flutter in_app_purchase)
server/                 accounts server: sign-in, one account per number, plan, payments
                        (Stripe, Google Play), time stats, ads sold per view (SQLite)
data/stories/*.json     stories, one file per level
data/dictionary/*.txt   dictionary entries: word | lemma | pos | english | example_de | example_en
tools/check_coverage.py lists story words that have no dictionary entry
tools/test_server.py    end-to-end check of the accounts server
communication.md        daily feature notes and review feedback
```

## Your data

Everything is kept in the app's data folder: the folder Flet provides for packaged
desktop/mobile apps (`FLET_APP_STORAGE_DATA`), or `~/.deutsch-mit-geschichten/` when running
from source. Saved words go to `my_words.json`. The signed-in phone number and the Premium plan
go to `account.json`, and the minutes spent in the app per day to `usage.json`. Delete a file
to start over. Word scroll remembers which words you've already seen in `feed.json`. With the accounts server, `account.json` only holds the session token and a copy
of the plan; the account itself lives in the server's `accounts.db`.
The word wallpaper's choices go to `wallpaper.json` and the widget's to `widget.json` in the
same folder; the words they show are copied to `word_wallpaper.json` and `word_widget.json`
in the Android app's private files.

## Adding a story

1. Add an object to `data/stories/<level>.json` with `id`, `title`, `title_en`,
   `summary_en`, `topics` (1–3 keys from `app/topics.py`, e.g. `["wohnen", "familie"]`) and
   `paragraphs`.
2. Run `python tools/check_coverage.py` to list the words that still need entries.
3. Add those words to `data/dictionary/<level>.txt`. The file decides the word's level in
   the gap game (`00_core.txt` counts as A1), so put new words in the story's level file.

A topic's key words are not stored anywhere: the app picks the base forms that occur much
more often in that topic's stories than in the others, so tagging a story is all it takes.

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

**`flet build apk` stops with "Building with plugins requires symlink support".** The
word-wallpaper extension needs symlinks during the build. Turn on Windows Developer Mode once
(Settings → System → For developers → Developer Mode) and build again.
