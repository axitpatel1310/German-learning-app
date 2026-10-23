# flet_word_wallpaper

Android live wallpaper for Sprach Up. It draws one German word card (word, meaning,
example) and moves to the next word after each screen-off, so every time the screen is
turned on there is a new word.

- `WordWallpaperService.kt`: the wallpaper; listens for screen-off and redraws on visibility.
- `WordStore.kt`: reads `word_wallpaper.json` from the app's files folder, shuffled order.
- `WordCardPainter.kt`: draws the background and the card.
- `FletWordWallpaperPlugin.kt`: method channel `flet_word_wallpaper` (`setWords`,
  `openPicker`, `isActive`).
- `lib/`: the Flet extension; the Python side is `app/wallpaper.py` in the app.
