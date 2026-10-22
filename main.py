"""Deutsch mit Geschichten — graded German stories with tap-to-translate.

"""

from pathlib import Path

import flet as ft

from app.data import LEVELS, Library
from app.game import GapGame
from app.splash import splash_view
from app.storage import MyWords
from app.views import StoryReader, game_view, home_view, level_view, search_view, words_view


def main(page: ft.Page):
    page.title = "Deutsch mit Geschichten"
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.INDIGO)
    page.dark_theme = ft.Theme(color_scheme_seed=ft.Colors.INDIGO)
    page.theme_mode = ft.ThemeMode.LIGHT
    page.window.width = 480
    page.window.height = 860

    lib = Library()
    my_words = MyWords()
    search_state = {"query": ""}
    game = GapGame(lib)
    game_state = {"level": "ALL", "answered": 0, "correct": 0, "streak": 0}

    def nav(route: str):
        async def handler(e):
            await page.push_route(route)

        return handler

    def toggle_theme(e):
        page.theme_mode = (
            ft.ThemeMode.DARK if page.theme_mode == ft.ThemeMode.LIGHT else ft.ThemeMode.LIGHT
        )
        page.update()

    def route_change(e=None):
        # Rebuild the view stack from the route so back navigation always works:
        #   /                -> home
        #   /level/B1        -> home, level
        #   /story/b1-001    -> home, level, story
        #   /words           -> home, my words
        #   /search          -> home, word search
        #   /game            -> home, gap game
        # A word sheet left open would otherwise float over the next screen.
        page.pop_dialog()
        page.views.clear()
        page.views.append(home_view(lib, my_words, nav, toggle_theme))

        parts = page.route.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "level" and parts[1] in LEVELS:
            page.views.append(level_view(lib, parts[1], nav))
        elif parts == ["words"]:
            page.views.append(words_view(page, lib, my_words, nav))
        elif parts == ["search"]:
            page.views.append(search_view(page, lib, my_words, nav, search_state))
        elif parts == ["game"]:
            page.views.append(game_view(page, game, my_words, game_state))
        elif len(parts) == 2 and parts[0] == "story":
            story = lib.get_story(parts[1])
            if story:
                page.views.append(level_view(lib, story.level, nav))
                page.views.append(StoryReader(page, lib, story, my_words).build())
        page.update()

    async def view_pop(e: ft.ViewPopEvent):
        if e.view is not None:
            page.views.remove(e.view)
        else:
            page.views.pop()
        await page.push_route(page.views[-1].route)

    def show_app():
        page.on_route_change = route_change
        page.on_view_pop = view_pop
        route_change()

    page.views.clear()
    page.views.append(splash_view(page, show_app))
    page.update()


ASSETS_DIR = str(Path(__file__).resolve().parent / "assets")

if __name__ == "__main__":
    ft.run(main, assets_dir=ASSETS_DIR)
