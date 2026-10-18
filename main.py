"""Deutsch mit Geschichten — graded German stories with tap-to-translate.

Run:  python main.py
"""

import flet as ft

from app.data import LEVELS, Library
from app.storage import MyWords
from app.views import StoryReader, home_view, level_view, words_view


def main(page: ft.Page):
    page.title = "Deutsch mit Geschichten"
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.INDIGO)
    page.dark_theme = ft.Theme(color_scheme_seed=ft.Colors.INDIGO)
    page.theme_mode = ft.ThemeMode.LIGHT
    page.window.width = 480
    page.window.height = 860

    lib = Library()
    my_words = MyWords()

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
        # A word sheet left open would otherwise float over the next screen.
        page.pop_dialog()
        page.views.clear()
        page.views.append(home_view(lib, my_words, nav, toggle_theme))

        parts = page.route.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "level" and parts[1] in LEVELS:
            page.views.append(level_view(lib, parts[1], nav))
        elif parts == ["words"]:
            page.views.append(words_view(page, lib, my_words, nav))
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

    page.on_route_change = route_change
    page.on_view_pop = view_pop
    route_change()


if __name__ == "__main__":
    ft.run(main)
