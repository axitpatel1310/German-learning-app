"""The word scroll screen: swipe up for the next word, double-tap to save it."""

import asyncio
import time

import flet as ft

from app import glass
from app.data import Library
from app.feed import SOURCES, WordFeed, headword
from app.storage import MyWords
from app.theme import level_color
from app.views import Navigate, _pill

SWIPE_SPEED = 250  # px/s: a slower drag is just a wobble
WHEEL_STEP = 40  # px of mouse-wheel scroll per card
DOUBLE_TAP = 0.45  # s between the two taps


def feed_view(page: ft.Page, lib: Library, my_words: MyWords, feed: WordFeed, nav: Navigate) -> ft.View:
    sources = ft.Row(wrap=True, spacing=6, run_spacing=6)
    switcher = ft.AnimatedSwitcher(
        transition=ft.AnimatedSwitcherTransition.FADE,
        duration=220,
        reverse_duration=120,
        switch_in_curve=ft.AnimationCurve.EASE_OUT,
        content=ft.Container(),
        left=0, top=0, right=0, bottom=0,
    )
    heart = ft.Container(
        content=ft.Icon(ft.Icons.BOOKMARK, size=110, color=ft.Colors.with_opacity(0.85, ft.Colors.ORANGE_400)),
        alignment=ft.Alignment.CENTER,
        opacity=0,
        scale=0.6,
        animate_opacity=ft.Animation(220, ft.AnimationCurve.EASE_OUT),
        animate_scale=ft.Animation(260, ft.AnimationCurve.EASE_OUT_BACK),
        ignore_interactions=True,
        left=0, top=0, right=0, bottom=0,
    )
    wheel = {"sum": 0.0}
    taps = {"last": 0.0}

    def pill(src: str) -> ft.Control:
        label = {"ALL": "All", "MINE": "My Words"}.get(src, src)
        color = level_color(src) if src not in ("ALL", "MINE") else (
            ft.Colors.PRIMARY if src == "ALL" else ft.Colors.ORANGE_400)
        return _pill(label, color, feed.source == src, lambda e: pick(src))

    def pick(src: str):
        feed.shuffle(src)
        show()

    def toggle_save(update: bool = True) -> bool:
        entry = feed.current
        if my_words.has(entry.word):
            my_words.remove(entry.word)
        else:
            my_words.add(entry.display, entry)
        if update:
            show(animate=False)
        return my_words.has(entry.word)

    async def on_tap(e):
        # Two taps close together are a double-tap. Timed here because Flet's own
        # double-tap doesn't fire in the web build.
        now = time.monotonic()
        double = now - taps["last"] < DOUBLE_TAP
        taps["last"] = 0.0 if double else now
        if double:
            await double_tap()

    async def double_tap():
        if not feed.current:
            return
        if not my_words.has(feed.current.word):
            toggle_save()
        heart.opacity, heart.scale = 1, 1
        heart.update()
        await asyncio.sleep(0.55)
        heart.opacity, heart.scale = 0, 0.6
        heart.update()

    def move(step: int):
        if feed.move(step):
            show()
        elif step > 0 and feed.deck:
            page.show_dialog(ft.SnackBar(ft.Text("That was the last word here. Pick another level, or shuffle.")))

    def on_drag_end(e: ft.DragEndEvent):
        if e.velocity.y < -SWIPE_SPEED:
            move(1)
        elif e.velocity.y > SWIPE_SPEED:
            move(-1)

    def on_scroll(e: ft.ScrollEvent):
        wheel["sum"] += e.scroll_delta.y
        if abs(wheel["sum"]) >= WHEEL_STEP:
            step = 1 if wheel["sum"] > 0 else -1
            wheel["sum"] = 0
            move(step)

    def on_key(e: ft.KeyboardEvent):
        if page.route != "/feed":
            return
        if e.key in ("Arrow Down", "Page Down", " "):
            move(1)
        elif e.key in ("Arrow Up", "Page Up"):
            move(-1)
        elif e.key.lower() == "s":
            toggle_save()

    def card() -> ft.Control:
        entry = feed.current
        if entry is None:
            return glass.panel(
                ft.Text("No saved words yet. Save words while you read, then scroll through them here."
                        if feed.source == "MINE" else "No words here yet."),
                padding=24,
            )
        saved = my_words.has(entry.word)
        stories = lib.stories_with(entry.word)
        color = level_color(entry.level) if entry.level else ft.Colors.PRIMARY
        tag = " · ".join(x for x in (entry.level, entry.pos) if x)
        lemma = entry.lemma if entry.lemma and entry.lemma.lower() != headword(entry).lower() else ""
        return glass.panel(
            key=f"{feed.source}-{feed.index}-{saved}",
            expand=True,
            padding=ft.Padding.only(left=24, right=12, top=20, bottom=16),
            blur=ft.Blur(16, 16),
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    ft.Column(
                        expand=True,
                        spacing=8,
                        alignment=ft.MainAxisAlignment.CENTER,
                        controls=[
                            ft.Container(
                                padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                                border_radius=12,
                                bgcolor=ft.Colors.with_opacity(0.14, color),
                                content=ft.Text(tag.upper(), size=11, weight=ft.FontWeight.BOLD, color=color),
                            ),
                            ft.Text(headword(entry), size=38, weight=ft.FontWeight.BOLD),
                            *([ft.Text(lemma, italic=True, color=ft.Colors.ON_SURFACE_VARIANT)] if lemma else []),
                            ft.Text(entry.english, size=21),
                            ft.Divider(height=24),
                            ft.Text(entry.example_de, size=18, italic=True),
                            ft.Text(entry.example_en, size=14, color=ft.Colors.ON_SURFACE_VARIANT),
                            ft.Container(height=6),
                            *([ft.TextButton(
                                content=f"Read it in “{stories[0].title}” ({stories[0].level})",
                                icon=ft.Icons.MENU_BOOK_OUTLINED,
                                on_click=nav(f"/story/{stories[0].id}"),
                                style=ft.ButtonStyle(padding=0),
                            )] if stories else []),
                        ],
                    ),
                    ft.Column(
                        alignment=ft.MainAxisAlignment.CENTER,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=6,
                        controls=[
                            ft.IconButton(icon=ft.Icons.KEYBOARD_ARROW_UP, tooltip="Previous word (↑)",
                                          on_click=lambda e: move(-1), disabled=feed.index == 0),
                            ft.IconButton(
                                icon=ft.Icons.BOOKMARK if saved else ft.Icons.BOOKMARK_BORDER,
                                icon_color=ft.Colors.ORANGE_400 if saved else None,
                                icon_size=30,
                                tooltip="Remove from My Words" if saved else "Save to My Words (S)",
                                on_click=lambda e: toggle_save(),
                            ),
                            ft.IconButton(icon=ft.Icons.SHUFFLE, tooltip="Shuffle",
                                          on_click=lambda e: pick(feed.source)),
                            ft.IconButton(icon=ft.Icons.KEYBOARD_ARROW_DOWN, tooltip="Next word (↓)",
                                          on_click=lambda e: move(1),
                                          disabled=feed.index >= len(feed.deck) - 1),
                        ],
                    ),
                ],
            ),
        )

    def show(update: bool = True, animate: bool = True):
        sources.controls = [pill(s) for s in SOURCES]
        if feed.deck:
            new = feed.new_left
            counter.value = (f"{feed.index + 1} of {len(feed.deck):,}"
                             + (f" · {new:,} new words left" if feed.source != "MINE" else ""))
        else:
            counter.value = ""
        switcher.duration = 220 if animate else 0
        switcher.content = card()
        if update:
            page.update()

    counter = ft.Text(size=12, color=ft.Colors.ON_SURFACE_VARIANT)
    show(update=False)
    page.on_keyboard_event = on_key
    return ft.View(
        route="/feed",
        padding=ft.Padding.only(left=16, right=16, top=4, bottom=16),
        spacing=10,
        appbar=ft.AppBar(title=ft.Text("Word scroll")),
        controls=[
            sources,
            ft.GestureDetector(
                expand=True,
                on_vertical_drag_end=on_drag_end,
                on_scroll=on_scroll,
                on_tap=on_tap,
                content=ft.Stack([switcher, heart], expand=True),
            ),
            ft.Row(
                [counter, ft.Text("Swipe up for the next word · double-tap to save",
                                  size=12, color=ft.Colors.ON_SURFACE_VARIANT)],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                wrap=True,
            ),
        ],
    )
