"""The screens: level picker, story list, story reader, My Words, word search and the gap game."""

from typing import Callable

import random

import flet as ft

from app import glass
from app.data import LEVELS, Entry, Library, Story, tokenize
from app.game import GAP, GapGame, level_choices
from app.storage import MyWords
from app.theme import HIGHLIGHT, level_color, level_name
from app.topics import TOPIC_BY_KEY, TOPICS, Topic

Navigate = Callable[[str], Callable]


def _pill(label: str, color: str, selected: bool, on_click: Callable) -> ft.Control:
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=14, vertical=7),
        border_radius=20,
        bgcolor=color if selected else glass.PANEL,
        border=ft.Border.all(1, color if selected else glass.EDGE),
        animate=ft.Animation(180, ft.AnimationCurve.EASE_OUT),
        on_click=on_click,
        content=ft.Text(
            label, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE if selected else color
        ),
    )


def _search_field(**kwargs) -> ft.TextField:
    return ft.TextField(
        prefix_icon=ft.Icons.SEARCH,
        dense=True,
        filled=True,
        fill_color=glass.PANEL,
        border_radius=14,
        border_color=glass.EDGE,
        focused_border_color=ft.Colors.PRIMARY,
        **kwargs,
    )


def _list_panel(tiles: list[ft.Control]) -> ft.Control:
    """Rows inside one frosted panel with hairlines between them (an iOS grouped list)."""
    rows: list[ft.Control] = []
    for i, tile in enumerate(tiles):
        if i:
            rows.append(ft.Divider(height=1, leading_indent=58))
        rows.append(tile)
    return glass.panel(ft.Column(rows, spacing=0), padding=ft.Padding.symmetric(vertical=4))


def _topic_chip(topic: Topic, on_click: Callable) -> ft.Control:
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=6),
        border_radius=16,
        bgcolor=glass.PANEL,
        border=ft.Border.all(1, glass.EDGE),
        on_click=on_click,
        content=ft.Row(
            [ft.Icon(topic.icon, size=14, color=ft.Colors.PRIMARY), ft.Text(topic.name, size=12)],
            spacing=4,
            tight=True,
        ),
    )


def _story_card(
    story: Story, badge: str, color: str, route: str, nav: Navigate, locked: bool = False
) -> ft.Card:
    return ft.Card(
        data=f"{story.title} {story.title_en}".lower(),
        content=ft.ListTile(
            leading=ft.Container(
                width=40,
                height=40,
                border_radius=12,
                alignment=ft.Alignment.CENTER,
                gradient=ft.LinearGradient(
                    begin=ft.Alignment.TOP_CENTER,
                    end=ft.Alignment.BOTTOM_CENTER,
                    colors=[ft.Colors.with_opacity(0.75, color), color],
                ),
                content=ft.Text(badge, color=ft.Colors.WHITE, weight=ft.FontWeight.W_600),
            ),
            title=ft.Text(story.title, weight=ft.FontWeight.W_600),
            subtitle=ft.Text(
                f"{story.title_en} · {story.word_count} words · ~{story.minutes} min",
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            trailing=ft.Icon(
                ft.Icons.LOCK_OUTLINE if locked else ft.Icons.CHEVRON_RIGHT,
                color=ft.Colors.OUTLINE,
                tooltip="Premium" if locked else None,
            ),
            on_click=nav(route),
        ),
    )


def _menu_row(icon: str, color: str, title: str, subtitle: str, on_click: Callable) -> ft.Control:
    return ft.ListTile(
        leading=glass.icon_tile(icon, color),
        title=ft.Text(title, weight=ft.FontWeight.W_600),
        subtitle=ft.Text(subtitle, size=13, color=ft.Colors.ON_SURFACE_VARIANT),
        trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, color=ft.Colors.OUTLINE),
        on_click=on_click,
    )


def _level_card(lib: Library, lvl: str, nav: Navigate) -> ft.Control:
    color = level_color(lvl)
    count = len(lib.stories[lvl])
    return ft.Container(
        col={"xs": 6, "md": 4},
        border_radius=glass.RADIUS,
        padding=18,
        ink=True,
        on_click=nav(f"/level/{lvl}"),
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
            colors=[ft.Colors.with_opacity(0.72, color), color],
        ),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.35, ft.Colors.WHITE)),
        shadow=ft.BoxShadow(
            blur_radius=20, spread_radius=-6, offset=ft.Offset(0, 8),
            color=ft.Colors.with_opacity(0.35, color),
        ),
        content=ft.Column(
            spacing=2,
            controls=[
                ft.Text(lvl, size=34, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                ft.Text(level_name(lvl), size=14, weight=ft.FontWeight.W_500, color=ft.Colors.WHITE),
                ft.Text(
                    f"{count} {'story' if count == 1 else 'stories'}",
                    size=12,
                    color=ft.Colors.with_opacity(0.85, ft.Colors.WHITE),
                ),
            ],
        ),
    )


def _word_hero(page: ft.Page, cards: list[dict], nav: Navigate) -> ft.Control:
    """A word card like the home-screen widget, with an arrow for the next word."""
    body = ft.Column(spacing=3, tight=True)
    rng = random.Random()

    def show(update: bool = True):
        card = rng.choice(cards)
        body.controls = [
            ft.Text(card["tag"].upper(), size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY),
            ft.Text(card["headword"], size=26, weight=ft.FontWeight.BOLD),
            ft.Text(card["english"], size=15),
            ft.Divider(height=14),
            ft.Text(card["example_de"], size=14, italic=True),
            ft.Text(card["example_en"], size=12, color=ft.Colors.ON_SURFACE_VARIANT),
        ]
        if update:
            body.update()

    show(update=False)
    return glass.panel(
        padding=ft.Padding.only(left=20, right=12, top=12, bottom=16),
        blur=ft.Blur(16, 16),
        content=ft.Row(
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                ft.Container(body, expand=True, padding=ft.Padding.only(top=6)),
                ft.Column(
                    spacing=4,
                    controls=[
                        ft.IconButton(
                            icon=ft.Icons.ARROW_FORWARD,
                            tooltip="Next word",
                            icon_color=ft.Colors.PRIMARY,
                            bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.PRIMARY),
                            on_click=lambda e: show(),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.WIDGETS_OUTLINED,
                            tooltip="Put this on your home screen",
                            icon_color=ft.Colors.PRIMARY,
                            on_click=nav("/widget"),
                        ),
                    ],
                ),
            ],
        ),
    )


def home_view(
    page: ft.Page,
    lib: Library,
    my_words: MyWords,
    nav: Navigate,
    toggle_theme: Callable,
    word_cards: Callable[[], list[dict]],
    ad: ft.Control | None = None,
) -> ft.View:
    n = len(my_words)
    cards = word_cards()
    return ft.View(
        route="/",
        scroll=ft.ScrollMode.AUTO,
        padding=ft.Padding.symmetric(horizontal=18, vertical=8),
        spacing=10,
        appbar=ft.AppBar(
            actions=[
                ft.IconButton(icon=ft.Icons.SEARCH, tooltip="Word search", on_click=nav("/search")),
                ft.IconButton(icon=ft.Icons.BOOKMARKS_OUTLINED, tooltip="My Words", on_click=nav("/words")),
                ft.IconButton(
                    icon=ft.Icons.BRIGHTNESS_6_OUTLINED,
                    tooltip="Toggle dark mode",
                    on_click=toggle_theme,
                ),
                ft.IconButton(icon=ft.Icons.ACCOUNT_CIRCLE_OUTLINED, tooltip="Profile", on_click=nav("/profile")),
            ],
        ),
        controls=[
            ft.Text("Deutsch mit Geschichten", size=30, weight=ft.FontWeight.BOLD),
            ft.Text(
                "Read graded stories and tap any word to see its meaning and an example.",
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            *([glass.section_label("Your word"), _word_hero(page, cards, nav)] if cards else []),
            glass.section_label("Choose your level"),
            ft.ResponsiveRow(controls=[_level_card(lib, lvl, nav) for lvl in LEVELS], spacing=12, run_spacing=12),
            *([ft.Container(height=2), ad] if ad else []),
            glass.section_label("Learn"),
            _list_panel([
                _menu_row(ft.Icons.SWIPE_UP_OUTLINED, ft.Colors.RED_400, "Word scroll",
                          "New words one by one: swipe up for the next, double-tap to save.", nav("/feed")),
                _menu_row(ft.Icons.CATEGORY_OUTLINED, ft.Colors.INDIGO_400, "Topics",
                          f"{len(TOPICS)} exam topics: stories and key words for each.", nav("/topics")),
                _menu_row(ft.Icons.EXTENSION_OUTLINED, ft.Colors.TEAL_400, "Gap game",
                          "A word is missing from a sentence. Pick the right one.", nav("/game")),
                _menu_row(ft.Icons.MANAGE_SEARCH, ft.Colors.BLUE_400, "Word search",
                          f"Look up any of {len(lib.dictionary):,} words, in German or English.", nav("/search")),
                _menu_row(ft.Icons.BOOKMARKS, ft.Colors.ORANGE_400, "My Words",
                          f"{n} saved {'word' if n == 1 else 'words'}" if n
                          else "Save words while you read to review them here.", nav("/words")),
            ]),
            glass.section_label("On your phone"),
            _list_panel([
                _menu_row(ft.Icons.WIDGETS_OUTLINED, ft.Colors.PURPLE_400, "Word widget",
                          "A word card on your home screen, new every 30 minutes (Android).", nav("/widget")),
                _menu_row(ft.Icons.WALLPAPER, ft.Colors.PINK_400, "Word wallpaper",
                          "A new word on your lock screen each time you turn on the phone (Android).",
                          nav("/wallpaper")),
            ]),
            ft.Container(height=12),
        ],
    )


def level_view(lib: Library, level: str, nav: Navigate, locked: Callable[[Story], bool]) -> ft.View:
    stories = lib.stories.get(level, [])
    cards = [
        _story_card(s, str(i), level_color(level), f"/story/{s.id}", nav, locked(s))
        for i, s in enumerate(stories, 1)
    ]
    no_match = ft.Text("No stories match your search.", visible=False)
    results = ft.Column(cards + [no_match], spacing=4)
    query = {"text": "", "topic": ""}
    chips = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=6)

    def refresh():
        for card, story in zip(cards, stories):
            card.visible = query["text"] in card.data and (
                not query["topic"] or query["topic"] in story.topics
            )
        no_match.visible = not any(c.visible for c in cards)
        chips.controls = topic_pills()
        results.update()
        chips.update()

    def on_search(e):
        query["text"] = (e.control.value or "").strip().lower()
        refresh()

    def pick_topic(key: str):
        query["topic"] = "" if query["topic"] == key else key
        refresh()

    def topic_pills() -> list[ft.Control]:
        used = {k for s in stories for k in s.topics}
        return [
            _pill(t.name, level_color(level), query["topic"] == t.key,
                  lambda e, k=t.key: pick_topic(k))
            for t in TOPICS if t.key in used
        ]

    controls: list[ft.Control] = []
    if len(stories) > 10:
        chips.controls = topic_pills()
        controls += [
            _search_field(hint_text=f"Search {len(stories)} stories", on_change=on_search),
            chips,
        ]
    controls.append(results if stories else ft.Text("No stories at this level yet."))

    return ft.View(
        route=f"/level/{level}",
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        spacing=8,
        appbar=ft.AppBar(title=ft.Text(f"{level} · {level_name(level)}")),
        controls=controls,
    )


class StoryReader:
    """Builds the reader view and keeps track of the highlighted word."""

    MIN_FONT, MAX_FONT = 14, 30

    def __init__(
        self, page: ft.Page, lib: Library, story: Story, my_words: MyWords, nav: Navigate,
        ad: ft.Control | None = None,
    ):
        self.page = page
        self.nav = nav
        self.ad = ad
        self.lib = lib
        self.story = story
        self.my_words = my_words
        self.font_size = 19
        self.selected: ft.TextSpan | None = None
        self.paragraph_texts: list[ft.Text] = []
        self.spans: dict[str, list[ft.TextSpan]] = {}

    # --- building ---

    def _paragraph(self, text: str) -> ft.Text:
        spans = []
        for chunk, is_word in tokenize(text):
            if is_word:
                span = ft.TextSpan(
                    chunk, data=chunk, style=self._style(chunk), on_click=self._on_word_click
                )
                self.spans.setdefault(chunk.lower(), []).append(span)
                spans.append(span)
            else:
                spans.append(ft.TextSpan(chunk))
        return ft.Text(spans=spans, size=self.font_size, style=ft.TextStyle(height=1.6))

    def build(self) -> ft.View:
        self.paragraph_texts = [self._paragraph(p) for p in self.story.paragraphs]
        level = self.story.level
        return ft.View(
            route=f"/story/{self.story.id}",
            scroll=ft.ScrollMode.AUTO,
            padding=ft.Padding.symmetric(horizontal=20, vertical=16),
            appbar=ft.AppBar(
                title=ft.Text(self.story.title),
                actions=[
                    ft.IconButton(
                        icon=ft.Icons.TEXT_DECREASE,
                        tooltip="Smaller text",
                        on_click=lambda e: self._change_font(-2),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.TEXT_INCREASE,
                        tooltip="Larger text",
                        on_click=lambda e: self._change_font(2),
                    ),
                ],
            ),
            controls=[
                ft.Text(self.story.title, size=28, weight=ft.FontWeight.BOLD),
                ft.Row(
                    wrap=True,
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Container(
                            padding=ft.Padding.symmetric(horizontal=10, vertical=3),
                            border_radius=10,
                            bgcolor=level_color(level),
                            content=ft.Text(level, size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                        ),
                        ft.Text(
                            f"{self.story.title_en} · ~{self.story.minutes} min",
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                ),
                ft.Row(
                    wrap=True,
                    spacing=6,
                    run_spacing=6,
                    controls=[
                        _topic_chip(TOPIC_BY_KEY[k], self.nav(f"/topic/{k}"))
                        for k in self.story.topics if k in TOPIC_BY_KEY
                    ],
                ),
                ft.Container(
                    margin=ft.Margin.only(top=4),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    border_radius=14,
                    bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.PRIMARY),
                    content=ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.TOUCH_APP_OUTLINED, size=18, color=ft.Colors.PRIMARY),
                            ft.Text(
                                "Tap any word to see its meaning. Saved words are underlined.",
                                size=13,
                                expand=True,
                            ),
                        ]
                    ),
                ),
                glass.panel(
                    ft.Column(self.paragraph_texts, spacing=14),
                    padding=ft.Padding.symmetric(horizontal=20, vertical=18),
                    margin=ft.Margin.symmetric(vertical=8),
                ),
                *([self.ad, ft.Container(height=8)] if self.ad else []),
                glass.panel(
                    ft.ExpansionTile(
                        title=ft.Text("English summary"),
                        leading=ft.Icon(ft.Icons.TRANSLATE, color=ft.Colors.PRIMARY),
                        controls=[
                            ft.Container(
                                padding=ft.Padding.only(left=16, right=16, bottom=16),
                                content=ft.Text(self.story.summary_en),
                            )
                        ],
                    ),
                    padding=0,
                ),
                ft.Container(height=12),
            ],
        )

    # --- interaction ---

    def _change_font(self, delta: int):
        self.font_size = max(self.MIN_FONT, min(self.MAX_FONT, self.font_size + delta))
        for t in self.paragraph_texts:
            t.size = self.font_size
        self.page.update()

    def _style(self, word: str) -> ft.TextStyle | None:
        if self.my_words.has(word):
            return ft.TextStyle(
                decoration=ft.TextDecoration.UNDERLINE,
                decoration_style=ft.TextDecorationStyle.DOTTED,
                decoration_color=ft.Colors.PRIMARY,
                decoration_thickness=2,
            )
        return None

    def _set_selected(self, span: ft.TextSpan | None):
        if self.selected is not None:
            self.selected.style = self._style(self.selected.data)
        self.selected = span
        if span is not None:
            span.style = ft.TextStyle(bgcolor=HIGHLIGHT, weight=ft.FontWeight.W_600)
        self.page.update()

    def _toggle_save(self, word: str, entry: Entry) -> bool:
        if self.my_words.has(word):
            self.my_words.remove(word)
        else:
            self.my_words.add(word, entry, self.story)
        for span in self.spans.get(word.lower(), []):
            if span is not self.selected:
                span.style = self._style(word)
        self.page.update()
        return self.my_words.has(word)

    def _on_word_click(self, e):
        span: ft.TextSpan = e.control
        word = span.data
        self._set_selected(span)
        entry = self.lib.lookup(word, self.story)
        sheet = ft.BottomSheet(
            content=word_card(
                word,
                entry,
                saved=self.my_words.has(word),
                on_toggle_save=(lambda: self._toggle_save(word, entry)) if entry else None,
            ),
            show_drag_handle=True,
            on_dismiss=lambda _: self._set_selected(None),
        )
        self.page.show_dialog(sheet)


def _save_button(saved: bool, on_toggle_save: Callable[[], bool]) -> ft.Control:
    def render(btn: ft.FilledTonalButton, is_saved: bool):
        btn.icon = ft.Icons.BOOKMARK if is_saved else ft.Icons.BOOKMARK_ADD_OUTLINED
        btn.content = "Saved to My Words" if is_saved else "Save to My Words"

    def on_click(e):
        render(e.control, on_toggle_save())
        e.control.update()

    btn = ft.FilledTonalButton(on_click=on_click)
    render(btn, saved)
    return btn


def word_card(
    word: str,
    entry: Entry | None,
    saved: bool = False,
    on_toggle_save: Callable[[], bool] | None = None,
    extra: list[ft.Control] | None = None,
) -> ft.Control:
    def label(text: str) -> ft.Text:
        return ft.Text(
            text.upper(), size=11, weight=ft.FontWeight.W_600, color=ft.Colors.PRIMARY
        )

    if entry is None:
        body = [
            ft.Text(word, size=28, weight=ft.FontWeight.BOLD),
            ft.Text("This word isn't in the dictionary yet.", color=ft.Colors.ON_SURFACE_VARIANT),
        ]
    else:
        header = [ft.Text(word, size=28, weight=ft.FontWeight.BOLD)]
        if entry.pos:
            header.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                    border_radius=12,
                    bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY),
                    content=ft.Text(entry.pos, size=12, color=ft.Colors.PRIMARY),
                )
            )
        body = [ft.Row(header, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER)]
        if entry.lemma and entry.lemma.lower() != word.lower():
            body.append(
                ft.Text(f"Base form: {entry.lemma}", italic=True, color=ft.Colors.ON_SURFACE_VARIANT)
            )
        body += [
            ft.Divider(),
            label("Meaning"),
            ft.Text(entry.english, size=17),
        ]
        if entry.example_de:
            body += [
                ft.Container(height=6),
                label("Example"),
                ft.Text(entry.example_de, size=16, italic=True),
                ft.Text(entry.example_en, color=ft.Colors.ON_SURFACE_VARIANT),
            ]
        if on_toggle_save:
            body += [ft.Container(height=6), _save_button(saved, on_toggle_save)]
    if extra:
        body += extra

    return ft.Container(
        padding=ft.Padding.only(left=24, right=24, bottom=28),
        content=ft.Column(body, tight=True, spacing=6),
    )


def words_view(page: ft.Page, lib: Library, my_words: MyWords, nav: Navigate) -> ft.View:
    """Saved words, newest first, with search and remove (undo via snackbar)."""
    title = ft.Text()
    results = ft.Column(spacing=8)
    search = _search_field(hint_text="Search German or English", on_change=lambda e: refresh())

    def remove(item: dict):
        my_words.remove(item["word"])
        refresh()

        def undo(e):
            my_words.restore(item)
            refresh()

        page.show_dialog(
            ft.SnackBar(ft.Text(f"Removed “{item['word']}”"), action="Undo", on_action=undo)
        )

    def card(item: dict) -> ft.Control:
        header: list[ft.Control] = [ft.Text(item["word"], size=20, weight=ft.FontWeight.BOLD)]
        if item.get("lemma") and item["lemma"].lower() != item["word"].lower():
            header.append(ft.Text(item["lemma"], italic=True, color=ft.Colors.ON_SURFACE_VARIANT))
        if item.get("pos"):
            header.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                    border_radius=10,
                    bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY),
                    content=ft.Text(item["pos"], size=11, color=ft.Colors.PRIMARY),
                )
            )
        body: list[ft.Control] = [
            ft.Row(
                [
                    ft.Row(header, wrap=True, expand=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        tooltip="Remove",
                        on_click=lambda e: remove(item),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            ft.Text(item.get("english", ""), size=16),
        ]
        if item.get("example_de"):
            body += [
                ft.Text(item["example_de"], italic=True),
                ft.Text(item.get("example_en", ""), size=13, color=ft.Colors.ON_SURFACE_VARIANT),
            ]
        story = lib.get_story(item.get("story_id", ""))
        if story:
            body.append(
                ft.TextButton(
                    content=f"From: {story.title} ({story.level})",
                    icon=ft.Icons.MENU_BOOK_OUTLINED,
                    on_click=nav(f"/story/{story.id}"),
                    style=ft.ButtonStyle(padding=0),
                )
            )
        return ft.Card(
            content=ft.Container(padding=ft.Padding.only(left=16, right=4, top=8, bottom=8),
                                 content=ft.Column(body, spacing=4, tight=True))
        )

    def refresh(update: bool = True):
        q = (search.value or "").strip().lower()
        items = my_words.all()
        title.value = f"My Words ({len(items)})"
        if q:
            items = [
                d for d in items
                if q in d["word"].lower() or q in d.get("lemma", "").lower()
                or q in d.get("english", "").lower()
            ]
        if items:
            results.controls = [card(d) for d in items]
        elif len(my_words):
            results.controls = [ft.Text("No saved words match your search.")]
        else:
            results.controls = [
                ft.Container(
                    padding=24,
                    content=ft.Column(
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.BOOKMARK_ADD_OUTLINED, size=48, color=ft.Colors.PRIMARY),
                            ft.Text("No saved words yet", size=18, weight=ft.FontWeight.W_600),
                            ft.Text(
                                "Open a story, tap a word and press “Save to My Words”.",
                                text_align=ft.TextAlign.CENTER,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                    ),
                )
            ]
        if update:
            page.update()

    refresh(update=False)
    return ft.View(
        route="/words",
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        appbar=ft.AppBar(title=title),
        controls=[search, results],
    )


def search_view(page: ft.Page, lib: Library, my_words: MyWords, nav: Navigate, state: dict) -> ft.View:
    """Look up any dictionary word, by German form, base form or English meaning."""
    results = ft.Column(spacing=0)
    search = _search_field(
        value=state.get("query", ""),
        hint_text="Type a German or English word",
        autofocus=True,
        on_change=lambda e: refresh(),
    )

    def toggle_save(entry: Entry, stories: list[Story]) -> bool:
        if my_words.has(entry.word):
            my_words.remove(entry.word)
        else:
            my_words.add(entry.display, entry, stories[0] if stories else None)
        refresh()
        return my_words.has(entry.word)

    def open_entry(entry: Entry):
        stories = lib.stories_with(entry.word)
        extra: list[ft.Control] = []
        if stories:
            extra.append(ft.Container(height=6))
            extra.append(
                ft.Text(
                    f"USED IN {len(stories)} {'STORY' if len(stories) == 1 else 'STORIES'}",
                    size=11,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.PRIMARY,
                )
            )
            for story in stories[:3]:
                extra.append(
                    ft.TextButton(
                        content=f"{story.title} ({story.level})",
                        icon=ft.Icons.MENU_BOOK_OUTLINED,
                        on_click=nav(f"/story/{story.id}"),
                        style=ft.ButtonStyle(padding=0),
                    )
                )
        page.show_dialog(
            ft.BottomSheet(
                content=word_card(
                    entry.display,
                    entry,
                    saved=my_words.has(entry.word),
                    on_toggle_save=lambda: toggle_save(entry, stories),
                    extra=extra,
                ),
                show_drag_handle=True,
                scrollable=True,
            )
        )

    def tile(entry: Entry) -> ft.Control:
        title = entry.display
        if entry.lemma.lower().endswith(" " + entry.word.lower()):
            title = entry.lemma  # "die Wohnung" rather than "Wohnung → die Wohnung"
        elif entry.lemma and entry.lemma.lower() != entry.word.lower():
            title += f"  →  {entry.lemma}"
        return ft.ListTile(
            leading=ft.Icon(
                ft.Icons.BOOKMARK if my_words.has(entry.word) else ft.Icons.TRANSLATE,
                color=ft.Colors.PRIMARY,
            ),
            title=ft.Text(title, weight=ft.FontWeight.W_600),
            subtitle=ft.Text(
                f"{entry.pos} · {entry.english}" if entry.pos else entry.english,
                max_lines=2,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
            on_click=lambda e: open_entry(entry),
        )

    def refresh(update: bool = True):
        q = (search.value or "").strip()
        state["query"] = q
        if not q:
            results.controls = [
                ft.Container(
                    padding=24,
                    content=ft.Column(
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.MANAGE_SEARCH, size=48, color=ft.Colors.PRIMARY),
                            ft.Text(
                                f"{len(lib.dictionary):,} words",
                                size=18,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Text(
                                "Search a German word (ging, Wohnung, uber) or an English "
                                "meaning (apartment, to decide).",
                                text_align=ft.TextAlign.CENTER,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                    ),
                )
            ]
        else:
            found = lib.search(q)
            results.controls = [_list_panel([tile(e) for e in found])] if found else [
                ft.Container(padding=16, content=ft.Text(f"No words found for “{q}”."))
            ]
        if update:
            page.update()

    refresh(update=False)
    return ft.View(
        route="/search",
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        spacing=12,
        appbar=ft.AppBar(title=ft.Text("Word search")),
        controls=[search, results],
    )


def game_view(page: ft.Page, game: GapGame, my_words: MyWords, state: dict, topic: str = "") -> ft.View:
    """Fill-the-gap: guess the hidden word in an example sentence, four options.
    With a topic, only that topic's key words are asked."""
    score = ft.Text(color=ft.Colors.ON_SURFACE_VARIANT)
    levels = ft.Row(wrap=True, spacing=6, run_spacing=6)
    body = ft.Column(spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
    choices = level_choices()
    if topic:
        used = {s.level for s in game.lib.topic_stories(topic)}
        choices = [c for c in choices if c == "ALL" or c in used]
        if state["level"] not in choices:
            state["level"] = "ALL"

    def pill(lvl: str) -> ft.Control:
        return _pill(
            "All" if lvl == "ALL" else lvl,
            ft.Colors.PRIMARY if lvl == "ALL" else level_color(lvl),
            state["level"] == lvl,
            lambda e: pick_level(lvl),
        )

    def pick_level(lvl: str):
        state["level"] = lvl
        next_question()

    def show_score():
        n, ok = state["answered"], state["correct"]
        score.value = (
            f"{ok} of {n} correct · streak {state['streak']}" if n else "Pick the missing word."
        )

    def answer(q, chosen: str, buttons: list[ft.Container], extra: ft.Column):
        if extra.controls:
            return  # already answered
        right = chosen == q.answer
        state["answered"] += 1
        state["correct"] += right
        state["streak"] = state["streak"] + 1 if right else 0
        for btn in buttons:
            if btn.data == q.answer:
                btn.bgcolor = ft.Colors.with_opacity(0.25, ft.Colors.GREEN)
                btn.border = ft.Border.all(2, ft.Colors.GREEN)
            elif btn.data == chosen:
                btn.bgcolor = ft.Colors.with_opacity(0.25, ft.Colors.RED)
                btn.border = ft.Border.all(2, ft.Colors.RED)
        entry = q.entry
        lemma = f"  ({entry.lemma})" if entry.lemma.lower() != q.answer.lower() else ""
        extra.controls = [
            ft.Text(
                ("Right! " if right else "Not quite. ") + f"{q.answer}{lemma}",
                size=17,
                weight=ft.FontWeight.W_600,
                color=ft.Colors.GREEN if right else ft.Colors.RED,
            ),
            ft.Text(f"{entry.pos} · {entry.english}"),
            ft.Text(entry.example_en, italic=True, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Row(
                wrap=True,
                controls=[
                    _save_button(my_words.has(entry.word), lambda: toggle_save(entry)),
                    ft.FilledButton(
                        content="Next sentence",
                        icon=ft.Icons.ARROW_FORWARD,
                        on_click=lambda e: next_question(),
                    ),
                ],
            ),
        ]
        show_score()
        page.update()

    def toggle_save(entry: Entry) -> bool:
        if my_words.has(entry.word):
            my_words.remove(entry.word)
        else:
            my_words.add(entry.display, entry)
        return my_words.has(entry.word)

    def next_question(update: bool = True):
        levels.controls = [pill(lvl) for lvl in choices]
        show_score()
        q = game.question(state["level"], topic)
        if q is None:
            body.controls = [ft.Text("No sentences for this level yet.")]
        else:
            translation = ft.Text(
                q.entry.example_en, visible=False, color=ft.Colors.ON_SURFACE_VARIANT
            )

            def toggle_hint(e):
                translation.visible = not translation.visible
                e.control.content = "Hide English" if translation.visible else "Show English"
                page.update()

            extra = ft.Column(spacing=8)
            buttons: list[ft.Container] = []
            for option in q.options:
                buttons.append(
                    ft.Container(
                        data=option,
                        padding=ft.Padding.symmetric(horizontal=18, vertical=14),
                        border_radius=16,
                        bgcolor=glass.PANEL,
                        border=ft.Border.all(1, glass.EDGE),
                        shadow=glass.SHADOW,
                        animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
                        ink=True,
                        on_click=lambda e: answer(q, e.control.data, buttons, extra),
                        content=ft.Text(option, size=17),
                    )
                )
            body.controls = [
                ft.Card(
                    content=ft.Container(
                        padding=20,
                        content=ft.Column(
                            tight=True,
                            spacing=6,
                            controls=[
                                ft.Text(
                                    size=21,
                                    style=ft.TextStyle(height=1.5),
                                    spans=[
                                        ft.TextSpan(q.before),
                                        ft.TextSpan(
                                            GAP,
                                            style=ft.TextStyle(
                                                color=ft.Colors.PRIMARY, weight=ft.FontWeight.BOLD
                                            ),
                                        ),
                                        ft.TextSpan(q.after),
                                    ],
                                ),
                                translation,
                                ft.TextButton(
                                    content="Show English",
                                    icon=ft.Icons.TRANSLATE,
                                    on_click=toggle_hint,
                                    style=ft.ButtonStyle(padding=0),
                                ),
                            ],
                        ),
                    )
                ),
                *buttons,
                extra,
            ]
        if update:
            page.update()

    next_question(update=False)
    return ft.View(
        route=f"/topic/{topic}/game" if topic else "/game",
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        appbar=ft.AppBar(
            title=ft.Text(f"Gap game · {TOPIC_BY_KEY[topic].name}" if topic else "Gap game")
        ),
        controls=[levels, score, body],
    )


def topics_view(lib: Library, nav: Navigate) -> ft.View:
    cards = []
    for t in TOPICS:
        count = len(lib.topic_stories(t.key))
        cards.append(
            glass.panel(
                col={"xs": 6, "md": 4},
                on_click=nav(f"/topic/{t.key}"),
                content=ft.Column(
                    spacing=4,
                    controls=[
                        glass.icon_tile(t.icon, ft.Colors.INDIGO_400, size=36),
                        ft.Container(height=2),
                        ft.Text(t.name, size=16, weight=ft.FontWeight.W_600),
                        ft.Text(t.name_en, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text(f"{count} {'story' if count == 1 else 'stories'}", size=12),
                    ],
                ),
            )
        )
    return ft.View(
        route="/topics",
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        appbar=ft.AppBar(title=ft.Text("Topics")),
        controls=[
            ft.Text(
                "The themes of the Goethe, telc and TestDaF exams. Open one to read its stories "
                "and learn its key words.",
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.ResponsiveRow(controls=cards, spacing=12, run_spacing=12),
        ],
    )


def topic_view(
    page: ft.Page,
    lib: Library,
    my_words: MyWords,
    nav: Navigate,
    topic: Topic,
    state: dict,
    locked: Callable[[Story], bool],
) -> ft.View:
    """One topic: its stories, or its key words, filtered by level."""
    state.setdefault("level", "ALL")
    state.setdefault("tab", "stories")
    all_stories = lib.topic_stories(topic.key)
    choices = ["ALL"] + [lvl for lvl in LEVELS if any(s.level == lvl for s in all_stories)]
    if state["level"] not in choices:
        state["level"] = "ALL"
    header = ft.Column(spacing=8)
    body = ft.Column(spacing=4)

    def pick(key: str, value: str):
        state[key] = value
        refresh()

    def toggle_save(entry: Entry, stories: list[Story]) -> bool:
        if my_words.has(entry.word):
            my_words.remove(entry.word)
        else:
            my_words.add(entry.display, entry, stories[0] if stories else None)
        refresh()
        return my_words.has(entry.word)

    def open_word(entry: Entry, stories: list[Story]):
        extra: list[ft.Control] = [
            ft.Container(height=6),
            ft.Text(
                f"IN {len(stories)} {topic.name.upper()} {'STORY' if len(stories) == 1 else 'STORIES'}",
                size=11,
                weight=ft.FontWeight.W_600,
                color=ft.Colors.PRIMARY,
            ),
        ]
        for story in stories[:3]:
            extra.append(
                ft.TextButton(
                    content=f"{story.title} ({story.level})",
                    icon=ft.Icons.MENU_BOOK_OUTLINED,
                    on_click=nav(f"/topic/{topic.key}/story/{story.id}"),
                    style=ft.ButtonStyle(padding=0),
                )
            )
        page.show_dialog(
            ft.BottomSheet(
                content=word_card(
                    entry.display,
                    entry,
                    saved=my_words.has(entry.word),
                    on_toggle_save=lambda: toggle_save(entry, stories),
                    extra=extra,
                ),
                show_drag_handle=True,
                scrollable=True,
            )
        )

    def word_tile(entry: Entry, stories: list[Story]) -> ft.Control:
        first = min((s.level for s in stories), key=LEVELS.index)
        return ft.ListTile(
            leading=ft.Icon(
                ft.Icons.BOOKMARK if my_words.has(entry.word) else ft.Icons.TRANSLATE,
                color=ft.Colors.PRIMARY,
            ),
            title=ft.Text(entry.lemma or entry.display, weight=ft.FontWeight.W_600),
            subtitle=ft.Text(
                f"{entry.pos} · {entry.english}", max_lines=2, overflow=ft.TextOverflow.ELLIPSIS
            ),
            trailing=ft.Text(first, weight=ft.FontWeight.W_600, color=level_color(first)),
            on_click=lambda e: open_word(entry, stories),
        )

    def refresh(update: bool = True):
        level = state["level"]
        stories = lib.topic_stories(topic.key, level)
        words = lib.topic_words(topic.key, level)
        header.controls = [
            ft.Row(
                wrap=True,
                spacing=6,
                run_spacing=6,
                controls=[
                    _pill(
                        "All" if lvl == "ALL" else lvl,
                        ft.Colors.PRIMARY if lvl == "ALL" else level_color(lvl),
                        level == lvl,
                        lambda e, lvl=lvl: pick("level", lvl),
                    )
                    for lvl in choices
                ],
            ),
            ft.Row(
                spacing=6,
                controls=[
                    _pill(f"Stories ({len(stories)})", ft.Colors.PRIMARY,
                          state["tab"] == "stories", lambda e: pick("tab", "stories")),
                    _pill(f"Key words ({len(words)})", ft.Colors.PRIMARY,
                          state["tab"] == "words", lambda e: pick("tab", "words")),
                ],
            ),
        ]
        if state["tab"] == "stories":
            body.controls = [
                _story_card(s, s.level, level_color(s.level), f"/topic/{topic.key}/story/{s.id}", nav,
                            locked(s))
                for s in stories
            ]
        else:
            body.controls = [
                ft.Text(
                    "Words that come up far more often in these stories than elsewhere. "
                    "The badge is the easiest level that uses the word. Tap a word for its card.",
                    size=13,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.FilledTonalButton(
                    content="Practise these words",
                    icon=ft.Icons.EXTENSION_OUTLINED,
                    on_click=nav(f"/topic/{topic.key}/game"),
                ),
                _list_panel([word_tile(e, st) for e, st in words]),
            ] if words else []
        if not body.controls:
            body.controls = [ft.Text("Nothing here yet at this level.")]
        if update:
            page.update()

    refresh(update=False)
    return ft.View(
        route=f"/topic/{topic.key}",
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        appbar=ft.AppBar(title=ft.Text(topic.name)),
        controls=[
            ft.Text(topic.name_en, color=ft.Colors.ON_SURFACE_VARIANT),
            header,
            body,
        ],
    )
