"""The screens: level picker, story list, story reader and My Words."""

from typing import Callable

import flet as ft

from app.data import LEVELS, Entry, Library, Story, tokenize
from app.storage import MyWords
from app.theme import HIGHLIGHT, level_color, level_name

Navigate = Callable[[str], Callable]


def home_view(lib: Library, my_words: MyWords, nav: Navigate, toggle_theme: Callable) -> ft.View:
    cards = []
    for lvl in LEVELS:
        count = len(lib.stories[lvl])
        cards.append(
            ft.Container(
                col={"xs": 6, "md": 4},
                bgcolor=level_color(lvl),
                border_radius=16,
                padding=20,
                ink=True,
                on_click=nav(f"/level/{lvl}"),
                content=ft.Column(
                    spacing=4,
                    controls=[
                        ft.Text(lvl, size=36, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                        ft.Text(level_name(lvl), size=15, color=ft.Colors.WHITE),
                        ft.Text(
                            f"{count} {'story' if count == 1 else 'stories'}",
                            size=13,
                            color=ft.Colors.with_opacity(0.85, ft.Colors.WHITE),
                        ),
                    ],
                ),
            )
        )

    return ft.View(
        route="/",
        scroll=ft.ScrollMode.AUTO,
        padding=20,
        appbar=ft.AppBar(
            title=ft.Text("Deutsch mit Geschichten"),
            actions=[
                ft.IconButton(
                    icon=ft.Icons.BOOKMARKS_OUTLINED,
                    tooltip="My Words",
                    on_click=nav("/words"),
                ),
                ft.IconButton(
                    icon=ft.Icons.BRIGHTNESS_6_OUTLINED,
                    tooltip="Toggle dark mode",
                    on_click=toggle_theme,
                )
            ],
        ),
        controls=[
            ft.Text("Choose your level", size=22, weight=ft.FontWeight.W_600),
            ft.Text(
                "Read graded stories and tap any word to see its meaning and an example.",
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.Container(height=8),
            ft.ResponsiveRow(controls=cards, spacing=12, run_spacing=12),
            ft.Container(height=8),
            ft.Card(
                content=ft.ListTile(
                    leading=ft.Icon(ft.Icons.BOOKMARKS, color=ft.Colors.PRIMARY),
                    title=ft.Text("My Words", weight=ft.FontWeight.W_600),
                    subtitle=ft.Text(
                        f"{len(my_words)} saved {'word' if len(my_words) == 1 else 'words'}"
                        if len(my_words)
                        else "Save words while you read to review them here."
                    ),
                    trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT),
                    on_click=nav("/words"),
                )
            ),
        ],
    )


def level_view(lib: Library, level: str, nav: Navigate) -> ft.View:
    stories = lib.stories.get(level, [])
    cards: list[ft.Control] = []
    for i, story in enumerate(stories, 1):
        cards.append(
            ft.Card(
                data=f"{story.title} {story.title_en}".lower(),
                content=ft.ListTile(
                    leading=ft.CircleAvatar(
                        content=ft.Text(str(i), color=ft.Colors.WHITE),
                        bgcolor=level_color(level),
                    ),
                    title=ft.Text(story.title, weight=ft.FontWeight.W_600),
                    subtitle=ft.Text(
                        f"{story.title_en} · {story.word_count} words · ~{story.minutes} min"
                    ),
                    trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT),
                    on_click=nav(f"/story/{story.id}"),
                ),
            )
        )
    no_match = ft.Text("No stories match your search.", visible=False)
    results = ft.Column(cards + [no_match], spacing=4)

    def on_search(e):
        q = (e.control.value or "").strip().lower()
        for card in cards:
            card.visible = q in card.data
        no_match.visible = not any(c.visible for c in cards)
        results.update()

    controls: list[ft.Control] = []
    if len(stories) > 10:
        controls.append(
            ft.TextField(
                hint_text=f"Search {len(stories)} stories",
                prefix_icon=ft.Icons.SEARCH,
                dense=True,
                border_radius=12,
                on_change=on_search,
            )
        )
    controls.append(results if stories else ft.Text("No stories at this level yet."))

    return ft.View(
        route=f"/level/{level}",
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        appbar=ft.AppBar(
            title=ft.Text(f"{level} · {level_name(level)}"),
            bgcolor=level_color(level),
            color=ft.Colors.WHITE,
        ),
        controls=controls,
    )


class StoryReader:
    """Builds the reader view and keeps track of the highlighted word."""

    MIN_FONT, MAX_FONT = 14, 30

    def __init__(self, page: ft.Page, lib: Library, story: Story, my_words: MyWords):
        self.page = page
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
                bgcolor=level_color(level),
                color=ft.Colors.WHITE,
                actions=[
                    ft.IconButton(
                        icon=ft.Icons.TEXT_DECREASE,
                        icon_color=ft.Colors.WHITE,
                        tooltip="Smaller text",
                        on_click=lambda e: self._change_font(-2),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.TEXT_INCREASE,
                        icon_color=ft.Colors.WHITE,
                        tooltip="Larger text",
                        on_click=lambda e: self._change_font(2),
                    ),
                ],
            ),
            controls=[
                ft.Text(self.story.title, size=26, weight=ft.FontWeight.BOLD),
                ft.Text(
                    f"{self.story.title_en} · {level} · ~{self.story.minutes} min",
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Container(
                    margin=ft.Margin.symmetric(vertical=8),
                    padding=10,
                    border_radius=10,
                    bgcolor=ft.Colors.SECONDARY_CONTAINER,
                    content=ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.TOUCH_APP_OUTLINED, size=18),
                            ft.Text(
                                "Tap any word to see its meaning. Saved words are underlined.",
                                size=13,
                                expand=True,
                            ),
                        ]
                    ),
                ),
                *self.paragraph_texts,
                ft.Container(height=8),
                ft.ExpansionTile(
                    title=ft.Text("English summary"),
                    leading=ft.Icon(ft.Icons.TRANSLATE),
                    controls=[
                        ft.Container(
                            padding=ft.Padding.only(left=16, right=16, bottom=16),
                            content=ft.Text(self.story.summary_en),
                        )
                    ],
                ),
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
                    bgcolor=ft.Colors.SECONDARY_CONTAINER,
                    content=ft.Text(entry.pos, size=12),
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

    return ft.Container(
        padding=ft.Padding.only(left=24, right=24, bottom=28),
        content=ft.Column(body, tight=True, spacing=6),
    )


def words_view(page: ft.Page, lib: Library, my_words: MyWords, nav: Navigate) -> ft.View:
    """Saved words, newest first, with search and remove (undo via snackbar)."""
    title = ft.Text()
    results = ft.Column(spacing=8)
    search = ft.TextField(
        hint_text="Search German or English",
        prefix_icon=ft.Icons.SEARCH,
        dense=True,
        border_radius=12,
        on_change=lambda e: refresh(),
    )

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
                    bgcolor=ft.Colors.SECONDARY_CONTAINER,
                    content=ft.Text(item["pos"], size=11),
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
