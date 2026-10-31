"""The sentence builder: a deck of cards on top, the drawn card below.

Each card is a sentence and a structure (sowohl … als auch, obwohl, Passiv …).
Rewrite the sentence with it, then check the answer.
"""

import asyncio

import flet as ft

from app import glass
from app.structures import Card, StructureDeck
from app.theme import level_color
from app.views import _pill

DECK_W, DECK_H = 230, 140
DECK_COLOR = ft.Colors.INDIGO_400


def structures_view(page: ft.Page, deck: StructureDeck, state: dict) -> ft.View:
    levels = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=6)
    kinds = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=6)
    switcher = ft.AnimatedSwitcher(
        transition=ft.AnimatedSwitcherTransition.SCALE,
        duration=260,
        reverse_duration=120,
        switch_in_curve=ft.AnimationCurve.EASE_OUT_BACK,
        content=ft.Container(),
        left=0, top=0, right=0, bottom=0,
    )
    top_label = ft.Column(spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                          alignment=ft.MainAxisAlignment.CENTER)
    top = ft.Container(
        width=DECK_W, height=DECK_H, left=14, top=6,
        border_radius=18,
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
            colors=[ft.Colors.with_opacity(0.78, DECK_COLOR), DECK_COLOR],
        ),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.4, ft.Colors.WHITE)),
        shadow=ft.BoxShadow(blur_radius=18, spread_radius=-4, offset=ft.Offset(0, 6),
                            color=ft.Colors.with_opacity(0.35, DECK_COLOR)),
        alignment=ft.Alignment.CENTER,
        content=top_label,
        animate_offset=ft.Animation(200, ft.AnimationCurve.EASE_IN_OUT),
        animate_opacity=ft.Animation(200, ft.AnimationCurve.EASE_IN_OUT),
        on_click=lambda e: page.run_task(draw),
        tooltip="Draw a card",
    )
    behind = [
        ft.Container(
            width=DECK_W, height=DECK_H, left=14, top=6, border_radius=18,
            rotate=ft.Rotate(angle), offset=ft.Offset(dx, 0),
            bgcolor=ft.Colors.with_opacity(0.35 + 0.2 * i, DECK_COLOR),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.4, ft.Colors.WHITE)),
        )
        for i, (angle, dx) in enumerate([(-0.09, -0.03), (0.06, 0.03)])
    ]
    deck_stack = ft.Stack([*behind, top], width=DECK_W + 28, height=DECK_H + 16)

    def pill_level(lvl: str) -> ft.Control:
        color = ft.Colors.PRIMARY if lvl == "ALL" else level_color(lvl)
        return _pill("All" if lvl == "ALL" else lvl, color, deck.level == lvl,
                     lambda e: reshuffle(level=lvl))

    def pill_kind(kind: str) -> ft.Control:
        label = "All structures" if kind == "ALL" else deck.kinds[kind]
        return _pill(label, ft.Colors.PRIMARY, deck.kind == kind, lambda e: reshuffle(kind=kind))

    def reshuffle(level: str | None = None, kind: str | None = None):
        deck.shuffle(level, kind)
        show()

    def show_deck():
        if deck.pile:
            n = len(deck.pile)
            top_label.controls = [
                ft.Icon(ft.Icons.STYLE_OUTLINED, color=ft.Colors.WHITE, size=30),
                ft.Text("Tap to draw a card", color=ft.Colors.WHITE, weight=ft.FontWeight.W_600, size=16),
                ft.Text(f"{n} {'card' if n == 1 else 'cards'} left",
                        color=ft.Colors.with_opacity(0.85, ft.Colors.WHITE), size=12),
            ]
        else:
            top_label.controls = [
                ft.Icon(ft.Icons.REPLAY, color=ft.Colors.WHITE, size=30),
                ft.Text("Deck finished", color=ft.Colors.WHITE, weight=ft.FontWeight.W_600, size=16),
                ft.Text(f"Tap to shuffle all {deck.size} again",
                        color=ft.Colors.with_opacity(0.85, ft.Colors.WHITE), size=12),
            ]
        for card in behind:
            card.visible = len(deck.pile) > 1

    async def draw():
        if not deck.pile:
            deck.shuffle()
            show()
            return
        top.offset, top.opacity = ft.Offset(0, 0.6), 0
        top.update()
        await asyncio.sleep(0.2)
        deck.draw()
        state.update(revealed=False, attempt="")
        top.offset, top.opacity = ft.Offset(0, 0), 1
        show()

    def card_panel(card: Card) -> ft.Control:
        color = level_color(card.level)
        attempt = ft.TextField(
            value=state["attempt"],
            hint_text="Write your sentence (optional)",
            filled=True, fill_color=glass.PANEL, border_radius=14, border_color=glass.EDGE,
            focused_border_color=ft.Colors.PRIMARY, dense=True,
            on_change=lambda e: state.update(attempt=e.control.value or ""),
            on_submit=lambda e: reveal(),
        )
        controls: list[ft.Control] = [
            ft.Row(spacing=8, controls=[
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=10, vertical=3), border_radius=10,
                    bgcolor=ft.Colors.with_opacity(0.14, color),
                    content=ft.Text(card.level, size=11, weight=ft.FontWeight.BOLD, color=color),
                ),
                ft.Text(deck.kinds[card.kind].upper(), size=11, weight=ft.FontWeight.W_600,
                        color=ft.Colors.ON_SURFACE_VARIANT),
            ]),
            ft.Text(card.prompt, size=20, weight=ft.FontWeight.W_500),
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=12, vertical=8), border_radius=12,
                bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.PRIMARY),
                content=ft.Text(spans=[
                    ft.TextSpan("Use: ", ft.TextStyle(color=ft.Colors.ON_SURFACE_VARIANT)),
                    ft.TextSpan(card.cue, ft.TextStyle(weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY)),
                ], size=16),
            ),
        ]
        if not state["revealed"]:
            controls += [
                attempt,
                ft.FilledButton(content="Check answer", icon=ft.Icons.VISIBILITY_OUTLINED,
                                on_click=lambda e: reveal()),
            ]
        else:
            tried = state["attempt"].strip()
            if tried:
                right = deck.check(card, tried)
                controls += [
                    ft.Text(f"You wrote: {tried}", italic=True, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Text("Richtig!" if right else "Compare with the answer:", size=15,
                            weight=ft.FontWeight.W_600,
                            color=ft.Colors.GREEN if right else ft.Colors.ORANGE_700),
                ]
            controls += [
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=14, vertical=10), border_radius=12,
                    bgcolor=ft.Colors.with_opacity(0.14, ft.Colors.GREEN),
                    border=ft.Border.all(1, ft.Colors.with_opacity(0.5, ft.Colors.GREEN)),
                    content=ft.Column(tight=True, spacing=4, controls=[
                        ft.Text(card.answer, size=19, weight=ft.FontWeight.W_600, selectable=True),
                        ft.Text(card.en, italic=True, color=ft.Colors.ON_SURFACE_VARIANT),
                    ]),
                ),
                *([ft.Text("Also correct: " + "  ·  ".join(card.alt), size=13,
                           color=ft.Colors.ON_SURFACE_VARIANT)] if card.alt else []),
                ft.Row(vertical_alignment=ft.CrossAxisAlignment.START, controls=[
                    ft.Icon(ft.Icons.LIGHTBULB_OUTLINE, size=18, color=ft.Colors.AMBER_700),
                    ft.Text(card.tip, size=14, expand=True),
                ]),
                ft.FilledButton(content="Next card" if deck.pile else "Shuffle again",
                                icon=ft.Icons.ARROW_UPWARD,
                                on_click=lambda e: page.run_task(draw)),
            ]
        return glass.panel(
            key=f"{card.cue}-{state['revealed']}",
            expand=True,
            padding=ft.Padding.only(left=18, right=18, top=14, bottom=14),
            content=ft.Column(controls, spacing=10, scroll=ft.ScrollMode.AUTO,
                              horizontal_alignment=ft.CrossAxisAlignment.START),
        )

    def reveal():
        state["revealed"] = True
        show(animate=False)

    def show(update: bool = True, animate: bool = True):
        levels.controls = [pill_level(lvl) for lvl in deck.levels()]
        kinds.controls = [pill_kind(k) for k in deck.kinds_for_level()]
        show_deck()
        switcher.duration = 260 if animate else 0
        switcher.content = card_panel(deck.current) if deck.current else ft.Container()
        if update:
            page.update()

    show(update=False)
    return ft.View(
        route="/structures",
        padding=ft.Padding.only(left=16, right=16, top=4, bottom=16),
        spacing=8,
        appbar=ft.AppBar(title=ft.Text("Sentence builder")),
        controls=[
            levels,
            kinds,
            ft.Column(expand=True, spacing=12, controls=[
                ft.Container(deck_stack, expand=1, alignment=ft.Alignment.CENTER),
                ft.Stack([switcher], expand=1),
            ]),
        ],
    )
