"""The Word wallpaper and Word widget screens: pick the words and style, preview, and set
them up on Android. Both screens work the same way; each keeps its own settings."""

import random
from typing import Callable

import flet as ft

from app import glass
from app.data import LEVELS, Library
from app.storage import MyWords
from app.theme import level_color
from app.topics import TOPIC_BY_KEY, TOPICS
from app.views import _pill
from app.wallpaper import WallpaperSettings, WordWallpaper, build_cards, is_android, payload

# Same colours as the native code (WordCardPainter.kt, WordWidgetProvider.kt and the
# word_widget_bg_*.xml drawables), so the previews match.
STYLES = {
    "light": dict(top="#E8EAF6", bottom="#F7F7FB", card="#FFFFFF", accent="#3949AB",
                  text="#1B1B21", muted="#5F5F6E", divider="#E0E0EA",
                  glass=["#E6FFFFFF", "#B8EEF0FF"], edge="#B3FFFFFF"),
    "dark": dict(top="#151829", bottom="#0B0C12", card="#1F2233", accent="#9FA8FF",
                 text="#F1F1F6", muted="#B0B2C3", divider="#33374D",
                 glass=["#D9262A40", "#B30E1020"], edge="#33FFFFFF"),
}
WIDGET_ACCENT = {"light": "#3949AB", "dark": "#B4BCFF"}
# A colourful sample home screen behind the widget preview, so the glass shows.
HOME_SCREEN = {"light": ["#A5B4FC", "#F0ABFC", "#FDE68A"], "dark": ["#1E1B4B", "#4C1D95", "#0F172A"]}
EMPTY_CARD = {
    "headword": "Noch keine Wörter", "tag": "", "english": "No words to show yet",
    "example_de": "", "example_en": "",
}


def _card_body(card: dict, c: dict, accent: str, sizes: tuple[int, int, int]) -> list[ft.Control]:
    head, meaning, example = sizes
    body: list[ft.Control] = []
    if card.get("tag"):
        body.append(ft.Text(card["tag"].upper(), size=9, weight=ft.FontWeight.BOLD, color=accent))
    body += [
        ft.Text(card["headword"], size=head, weight=ft.FontWeight.BOLD, color=c["text"],
                max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
        ft.Text(card["english"], size=meaning, color=c["text"], max_lines=2,
                overflow=ft.TextOverflow.ELLIPSIS),
    ]
    if card.get("example_de"):
        body += [
            ft.Container(height=1, bgcolor=c["divider"], margin=ft.Margin.symmetric(vertical=5)),
            ft.Text(card["example_de"], size=example, italic=True, color=c["text"], max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS),
            ft.Text(card["example_en"], size=example - 2, color=c["muted"], max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS),
        ]
    return body


def _phone(content: ft.Control, colors: list[str], **kwargs) -> ft.Control:
    return ft.Container(
        width=250,
        height=440,
        border_radius=34,
        border=ft.Border.all(6, "#202020"),
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT, colors=colors,
        ),
        padding=14,
        content=content,
        **kwargs,
    )


def wallpaper_preview(card: dict, theme: str) -> ft.Control:
    """A small phone-shaped picture of the wallpaper."""
    c = STYLES[theme]
    return _phone(
        ft.Container(
            bgcolor=c["card"],
            border_radius=18,
            padding=14,
            shadow=ft.BoxShadow(blur_radius=10, color=ft.Colors.with_opacity(0.15, ft.Colors.BLACK)),
            content=ft.Column(_card_body(card, c, c["accent"], (22, 13, 12)), tight=True, spacing=4),
        ),
        [c["top"], c["bottom"]],
        alignment=ft.Alignment.CENTER,
    )


def widget_card(card: dict, theme: str, on_next: Callable | None = None, width: int | None = None) -> ft.Control:
    """The widget itself: a frosted card with the word and a round arrow button."""
    c = STYLES[theme]
    accent = WIDGET_ACCENT[theme]
    body = _card_body(card, c, accent, (21, 12, 11))
    arrow = ft.Container(
        width=30, height=30, border_radius=15, alignment=ft.Alignment.CENTER,
        bgcolor="#1F8C93C9", on_click=on_next,
        content=ft.Icon(ft.Icons.ARROW_FORWARD, size=16, color=accent),
    )
    top = body.pop(0) if card.get("tag") else ft.Container()
    return ft.Container(
        width=width,
        border_radius=24,
        padding=ft.Padding.only(left=16, right=10, top=10, bottom=12),
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT, colors=c["glass"],
        ),
        border=ft.Border.all(1, c["edge"]),
        blur=ft.Blur(12, 12),
        shadow=ft.BoxShadow(blur_radius=18, spread_radius=-4, offset=ft.Offset(0, 6),
                            color=ft.Colors.with_opacity(0.18, ft.Colors.BLACK)),
        content=ft.Column(
            tight=True, spacing=3,
            controls=[
                ft.Row([ft.Container(top, expand=True), arrow],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                *body,
            ],
        ),
    )


def widget_preview(card: dict, theme: str, on_next: Callable) -> ft.Control:
    """A phone home screen with a few app icons and the widget at the top."""
    icon = ft.Container(width=38, height=38, border_radius=11,
                        bgcolor=ft.Colors.with_opacity(0.45, ft.Colors.WHITE))
    icons = ft.Row([icon] * 4, alignment=ft.MainAxisAlignment.SPACE_EVENLY)
    return _phone(
        ft.Column(
            spacing=14,
            controls=[
                ft.Container(height=6),
                widget_card(card, theme, on_next),
                ft.Container(expand=True),
                icons,
                icons,
            ],
        ),
        HOME_SCREEN[theme],
    )


KINDS = {
    "wallpaper": dict(
        route="/wallpaper",
        title="Word wallpaper",
        intro="Your lock screen and home screen show one word with its meaning and an example. "
              "Each time you turn the screen on, you get a new one.",
        apply="Set as wallpaper",
        icon=ft.Icons.WALLPAPER,
        not_android="The wallpaper works in the Android app. Here you can only preview it.",
    ),
    "widget": dict(
        route="/widget",
        title="Word widget",
        intro="A glass card on your home screen with one word, its meaning and an example. "
              "It shows a new word every 30 minutes, and the arrow skips to the next one. "
              "Tap the card to open the app.",
        apply="Add widget to home screen",
        icon=ft.Icons.WIDGETS_OUTLINED,
        not_android="The widget works in the Android app. Here you can only preview it.",
    ),
}


def wallpaper_view(page, lib, my_words, settings, get_service) -> ft.View:
    return _word_screen(page, lib, my_words, settings, get_service, "wallpaper")


def widget_view(page, lib, my_words, settings, get_service) -> ft.View:
    return _word_screen(page, lib, my_words, settings, get_service, "widget")


def _word_screen(
    page: ft.Page,
    lib: Library,
    my_words: MyWords,
    settings: WallpaperSettings,
    get_service: Callable[[], WordWallpaper],
    kind: str,
) -> ft.View:
    k = KINDS[kind]
    android = is_android(page)
    state = {"cards": [], "shown": 0}
    rng = random.Random()
    choices = ft.Column(spacing=10)
    count = ft.Text(size=13, color=ft.Colors.ON_SURFACE_VARIANT)
    phone = ft.Container(alignment=ft.Alignment.CENTER)
    status = ft.Text(color=ft.Colors.ON_SURFACE_VARIANT)
    apply_btn = ft.FilledButton(icon=k["icon"], content=k["apply"])

    def pick(**changes):
        settings.set(**changes)
        refresh()

    def show_another(e=None):
        if state["cards"]:
            state["shown"] = rng.randrange(len(state["cards"]))
        render_preview()
        page.update()

    def render_preview():
        cards = state["cards"]
        sample = cards[state["shown"] % len(cards)] if cards else EMPTY_CARD
        if kind == "widget":
            phone.content = widget_preview(sample, settings["theme"], show_another)
        else:
            phone.content = wallpaper_preview(sample, settings["theme"])

    def pills(items, current, color=ft.Colors.PRIMARY, key="") -> ft.Row:
        return ft.Row(
            wrap=True, spacing=6, run_spacing=6,
            controls=[
                _pill(label, color(value) if callable(color) else color, current == value,
                      lambda e, v=value: pick(**{key: v}))
                for value, label in items
            ],
        )

    def refresh(update: bool = True):
        source = settings["source"]
        rows: list[ft.Control] = [
            pills([("level", "Level"), ("topic", "Topic"), ("my_words", "My Words")], source, key="source")
        ]
        if source == "level":
            rows.append(pills(
                [(lvl, "All" if lvl == "ALL" else lvl) for lvl in ["ALL", *LEVELS]],
                settings["level"],
                lambda v: ft.Colors.PRIMARY if v == "ALL" else level_color(v),
                key="level",
            ))
        elif source == "topic":
            rows.append(pills([(t.key, t.name) for t in TOPICS], settings["topic"], key="topic"))
        rows.append(pills([("light", "Light"), ("dark", "Dark")], settings["theme"], key="theme"))
        choices.controls = rows

        state["cards"] = build_cards(lib, my_words, settings)
        state["shown"] = rng.randrange(len(state["cards"])) if state["cards"] else 0
        n = len(state["cards"])
        if source == "my_words" and not n:
            count.value = "You haven't saved any words yet. Save words while reading, then come back."
        else:
            what = {
                "level": "All levels" if settings["level"] == "ALL" else f"Level {settings['level']}",
                "topic": TOPIC_BY_KEY[settings["topic"]].name if settings["topic"] in TOPIC_BY_KEY else "",
                "my_words": "My Words",
            }[source]
            count.value = f"{what}: {n:,} {'word' if n == 1 else 'words'}, in random order."
        apply_btn.disabled = not android or not n
        render_preview()
        if update:
            page.update()

    async def apply_wallpaper(service: WordWallpaper, cards: list[dict]):
        if not await service.set_words(payload(cards, settings)):
            status.value = "Couldn't send the words to the wallpaper."
            return
        settings.set(enabled=True)
        if await service.is_active():
            status.value = f"Wallpaper updated: {len(cards):,} words."
        elif await service.open_picker():
            status.value = "Press “Set wallpaper” on the next screen and choose Home and lock screen."
        else:
            status.value = "This phone has no live-wallpaper picker."

    async def apply_widget(service: WordWallpaper, cards: list[dict]):
        if not await service.set_widget_words(payload(cards, settings)):
            status.value = "Couldn't send the words to the widget."
            return
        settings.set(enabled=True)
        if await service.widget_count():
            status.value = f"Widget updated: {len(cards):,} words."
        elif await service.pin_widget():
            status.value = "Confirm on the next screen to place the widget on your home screen."
        else:
            status.value = (
                "Words saved. Now long-press your home screen, choose Widgets, "
                "and drag “Sprach Up word” onto it."
            )

    async def apply(e):
        service = get_service()
        cards = state["cards"]
        await (apply_widget if kind == "widget" else apply_wallpaper)(service, cards)
        page.update()

    async def check_active():
        service = get_service()
        active = await (service.widget_count() if kind == "widget" else service.is_active())
        if active:
            apply_btn.content = "Update widget" if kind == "widget" else "Update wallpaper"
            status.value = f"The word {kind} is on. Changes apply after you press Update."
            page.update()

    apply_btn.on_click = apply
    refresh(update=False)
    if android:
        page.run_task(check_active)
    else:
        status.value = k["not_android"]

    return ft.View(
        route=k["route"],
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        appbar=ft.AppBar(title=ft.Text(k["title"])),
        controls=[
            ft.Text(k["intro"], color=ft.Colors.ON_SURFACE_VARIANT),
            glass.section_label("Words and style"),
            glass.panel(ft.Column([choices, count], spacing=10)),
            ft.Container(height=4),
            phone,
            ft.Row(
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[ft.TextButton(content="Show another word", icon=ft.Icons.SHUFFLE, on_click=show_another)],
            ),
            apply_btn,
            status,
        ],
    )
