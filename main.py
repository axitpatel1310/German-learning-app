"""Deutsch mit Geschichten — graded German stories with tap-to-translate.

"""

import asyncio
from pathlib import Path

import flet as ft

from app import glass
from app.account import OtpError, Usage, make_account
from app.account_view import locked_view, plan_view, profile_view, signin_view
from app.ads_view import ad_card
from app.billing import PlayBilling
from app.data import LEVELS, Library
from app.feed import WordFeed
from app.feed_view import feed_view
from app.game import GapGame
from app.storage import MyWords
from app.topics import TOPIC_BY_KEY
from app.views import (
    StoryReader,
    game_view,
    home_view,
    level_view,
    search_view,
    topic_view,
    topics_view,
    words_view,
)
from app.wallpaper import (
    WallpaperSettings,
    WordWallpaper,
    build_cards,
    is_android,
    level_cards,
    payload,
)
from app.wallpaper_view import wallpaper_view, widget_view


def main(page: ft.Page):
    page.title = "Deutsch mit Geschichten"
    page.theme = glass.theme(dark=False)
    page.dark_theme = glass.theme(dark=True)
    page.theme_mode = ft.ThemeMode.LIGHT
    page.window.width = 480
    page.window.height = 860

    lib = Library()
    my_words = MyWords()
    account = make_account()
    usage = Usage()
    usage.claim(account.phone)
    search_state = {"query": ""}
    game = GapGame(lib)
    feed: list[WordFeed] = []  # the word scroll deck, built on first visit
    game_state = {"level": "ALL", "answered": 0, "correct": 0, "streak": 0}
    topic_states: dict[str, dict] = {}  # per topic: level, tab and its own game score
    wallpaper_settings = WallpaperSettings()
    widget_settings = WallpaperSettings("widget.json")
    wallpaper: list[WordWallpaper] = []  # created on first use, Android only
    home_words: list[dict] = []  # sample for the word card on the home screen, built once

    def home_word_cards() -> list[dict]:
        if not home_words:
            home_words.extend(level_cards(lib, "ALL"))
        return home_words

    play: list[PlayBilling] = []  # Google Play Billing, Android with an accounts server only

    def play_billing() -> PlayBilling:
        if not play:
            play.append(PlayBilling())
        return play[0]

    async def recover_purchases():
        # A Play purchase the server never confirmed (the app closed while paying, or no
        # connection) is sent again, so nobody pays without getting Premium.
        if "google_play" not in account.payments or not account.signed_in:
            return
        billing = play_billing()
        for item in await billing.pending():
            try:
                await asyncio.to_thread(account.confirm_play, item["purchase_token"])
            except OtpError:
                continue
            await billing.finish(item["purchase_token"])
            route_change()

    def wallpaper_service() -> WordWallpaper:
        if not wallpaper:
            wallpaper.append(WordWallpaper())
        return wallpaper[0]

    async def sync_android():
        # Resend the words on start, so newly saved My Words reach the wallpaper and widget.
        service = wallpaper_service()
        if wallpaper_settings["enabled"]:
            cards = build_cards(lib, my_words, wallpaper_settings)
            if cards:
                await service.set_words(payload(cards, wallpaper_settings))
        if widget_settings["enabled"]:
            cards = build_cards(lib, my_words, widget_settings)
            if cards:
                await service.set_widget_words(payload(cards, widget_settings))

    def nav(route: str):
        async def handler(e):
            await page.push_route(route)

        return handler

    def toggle_theme(e):
        page.theme_mode = (
            ft.ThemeMode.DARK if page.theme_mode == ft.ThemeMode.LIGHT else ft.ThemeMode.LIGHT
        )
        route_change()  # the backdrop gradient is per mode

    def locked(story) -> bool:
        return account.locked(lib, story)

    # Ads: free users with an accounts server see one ad card, refreshed with each sync.
    current_ad: dict = {"ad": None}

    async def fetch_ad():
        if not account.server:
            return
        ad = await asyncio.to_thread(account.next_ad)
        changed = (ad or {}).get("id") != (current_ad["ad"] or {}).get("id")
        current_ad["ad"] = ad
        if changed and page.route == "/":  # elsewhere it shows from the next screen on
            route_change()

    def ad_control() -> ft.Control | None:
        ad = current_ad["ad"]
        if not ad or account.premium:
            return None
        page.run_task(asyncio.to_thread, account.ad_seen, ad["id"])  # the server counts once per 30 min
        return ad_card(page, ad, lambda: page.run_task(asyncio.to_thread, account.ad_click, ad["id"]),
                       nav("/premium"))

    def reader(story) -> ft.View:
        if locked(story):
            return locked_view(story, lib.stories[story.level].index(story) + 1, nav)
        return StoryReader(page, lib, story, my_words, nav, ad_control()).build()

    async def signed_in():
        usage.claim(account.phone)
        page.run_task(sync_account)
        if page.route == "/":
            route_change()
        else:
            await page.push_route("/")

    async def signed_out():
        account.sign_out()
        await page.push_route("/signin")

    connected = {"on": True}  # a web tab can drop its connection without closing

    async def sync_account():
        # With an accounts server: fetch the plan and exchange time stats. Offline is fine.
        was = (account.signed_in, account.premium)
        await asyncio.to_thread(account.refresh)
        await asyncio.to_thread(account.sync_usage, usage)
        if (account.signed_in, account.premium) != was:
            route_change()
        await fetch_ad()

    async def track_usage():
        n = 0
        while True:
            await asyncio.sleep(Usage.TICK)
            usage.tick(page.app_visible and connected["on"])
            n += 1
            if account.server and n % 8 == 0:  # every 2 minutes
                await sync_account()

    def set_connected(on: bool):
        connected["on"] = on

    def route_change(e=None):
        # Rebuild the view stack from the route so back navigation always works:
        #   /                -> home
        #   /level/B1        -> home, level
        #   /story/b1-001    -> home, level, story
        #   /words           -> home, my words
        #   /search          -> home, word search
        #   /game            -> home, gap game
        #   /feed            -> home, word scroll
        #   /wallpaper       -> home, word wallpaper
        #   /widget          -> home, word widget
        #   /topics          -> home, topics
        #   /topic/wohnen    -> home, topics, topic
        #   /topic/wohnen/story/a1-004 and /topic/wohnen/game -> ... topic, story or game
        #   /profile         -> home, profile
        #   /premium         -> home, premium plan
        # Without an account only the sign-in screen is shown.
        # A word sheet left open would otherwise float over the next screen.
        page.pop_dialog()
        page.views.clear()
        if not account.signed_in:
            page.views.append(signin_view(page, account, signed_in))
            _decorate()
            return
        parts = page.route.strip("/").split("/")
        page.views.append(home_view(page, lib, my_words, nav, toggle_theme, home_word_cards,
                                    ad_control() if parts == [""] else None))

        if len(parts) == 2 and parts[0] == "level" and parts[1] in LEVELS:
            page.views.append(level_view(lib, parts[1], nav, locked))
        elif parts == ["words"]:
            page.views.append(words_view(page, lib, my_words, nav))
        elif parts == ["search"]:
            page.views.append(search_view(page, lib, my_words, nav, search_state))
        elif parts == ["feed"]:
            if not feed:
                feed.append(WordFeed(lib, my_words))
            page.views.append(feed_view(page, lib, my_words, feed[0], nav))
        elif parts == ["game"]:
            page.views.append(game_view(page, game, my_words, game_state))
        elif parts == ["wallpaper"]:
            page.views.append(
                wallpaper_view(page, lib, my_words, wallpaper_settings, wallpaper_service)
            )
        elif parts == ["widget"]:
            page.views.append(widget_view(page, lib, my_words, widget_settings, wallpaper_service))
        elif parts == ["profile"]:
            page.views.append(profile_view(page, account, usage, my_words, nav, signed_out))
        elif parts == ["premium"]:
            android_play = account.server and is_android(page)
            page.views.append(plan_view(page, lib, account, route_change, play_billing if android_play else None))
        elif parts == ["topics"]:
            page.views.append(topics_view(lib, nav))
        elif len(parts) >= 2 and parts[0] == "topic" and parts[1] in TOPIC_BY_KEY:
            key = parts[1]
            state = topic_states.setdefault(
                key, {"level": "ALL", "tab": "stories", "answered": 0, "correct": 0, "streak": 0}
            )
            page.views.append(topics_view(lib, nav))
            page.views.append(topic_view(page, lib, my_words, nav, TOPIC_BY_KEY[key], state, locked))
            story = lib.get_story(parts[3]) if len(parts) == 4 and parts[2] == "story" else None
            if story:
                page.views.append(reader(story))
            elif parts[2:] == ["game"]:
                page.views.append(game_view(page, game, my_words, state, key))
        elif len(parts) == 2 and parts[0] == "story":
            story = lib.get_story(parts[1])
            if story:
                page.views.append(level_view(lib, story.level, nav, locked))
                page.views.append(reader(story))
        _decorate()

    def _decorate():
        decoration = glass.backdrop(page.theme_mode == ft.ThemeMode.DARK)
        for view in page.views:
            view.decoration = decoration
            view.bgcolor = ft.Colors.TRANSPARENT
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
    usage_task = page.run_task(track_usage)
    if account.server and account.signed_in:
        page.run_task(sync_account)
    page.on_connect = lambda e: set_connected(True)
    page.on_disconnect = lambda e: set_connected(False)
    page.on_close = lambda e: usage_task.cancel()
    if account.server and is_android(page):
        page.run_task(recover_purchases)
    if is_android(page) and (wallpaper_settings["enabled"] or widget_settings["enabled"]):
        page.run_task(sync_android)


ASSETS_DIR = str(Path(__file__).resolve().parent / "assets")

if __name__ == "__main__":
    ft.run(main, assets_dir=ASSETS_DIR)
