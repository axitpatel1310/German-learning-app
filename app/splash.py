"""Intro animation shown every time the app starts."""

import asyncio
from typing import Callable

import flet as ft

# assets/intro.webp is the Sprach Up intro video converted to an animated WebP
# (Flet's video control needs a `flet build` app; an animated image plays everywhere).
INTRO_SRC = "intro.webp"
INTRO_SECONDS = 10
FADE_MS = 400
# Matches the video's light-grey background so the edges blend in on any window size.
INTRO_BG = "#E1E1E1"


def splash_view(page: ft.Page, on_done: Callable[[], None]) -> ft.View:
    done = False

    # Pinned to all four edges so the image gets the whole screen and CONTAIN
    # scales it down to fit (letterboxed) instead of overflowing narrow windows.
    content = ft.Container(
        left=0,
        top=0,
        right=0,
        bottom=0,
        animate_opacity=FADE_MS,
        content=ft.Image(src=INTRO_SRC, fit=ft.BoxFit.CONTAIN, gapless_playback=True),
    )

    async def finish():
        nonlocal done
        if done:
            return
        done = True
        content.opacity = 0
        page.update()
        await asyncio.sleep(FADE_MS / 1000)
        on_done()

    async def auto_finish():
        await asyncio.sleep(INTRO_SECONDS)
        await finish()

    async def skip(e):
        await finish()

    page.run_task(auto_finish)

    return ft.View(
        route="/splash",
        bgcolor=INTRO_BG,
        padding=0,
        controls=[
            ft.Stack(
                expand=True,
                controls=[
                    content,
                    ft.Container(
                        right=16,
                        top=16,
                        content=ft.TextButton(
                            "Skip",
                            icon=ft.Icons.SKIP_NEXT,
                            style=ft.ButtonStyle(color=ft.Colors.BLUE_GREY_700),
                            on_click=skip,
                        ),
                    ),
                ],
            )
        ],
    )
