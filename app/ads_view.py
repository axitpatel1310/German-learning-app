"""The ad card free users see on the home screen and at the end of each story."""

import urllib.parse
from typing import Callable

import flet as ft

from app import glass


def ad_card(page: ft.Page, ad: dict, on_click: Callable[[], None], nav_premium: Callable) -> ft.Control:
    domain = urllib.parse.urlsplit(ad["link"]).netloc.removeprefix("www.")

    async def open_link(e):
        on_click()
        await ft.UrlLauncher().launch_url(ad["link"])

    return glass.panel(
        padding=ft.Padding.only(left=16, right=8, top=10, bottom=10),
        on_click=open_link,
        content=ft.Column(
            spacing=2,
            tight=True,
            controls=[
                ft.Row(
                    controls=[
                        ft.Text(f"ANZEIGE · {ad['business']}", size=11, weight=ft.FontWeight.BOLD,
                                color=ft.Colors.ON_SURFACE_VARIANT, expand=True,
                                max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.TextButton(content=ft.Text("Remove ads", size=11), on_click=nav_premium),
                    ],
                ),
                ft.Text(ad["headline"], size=16, weight=ft.FontWeight.W_600),
                ft.Text(ad["body"], size=14),
                ft.Row(
                    spacing=4,
                    controls=[
                        ft.Icon(ft.Icons.OPEN_IN_NEW, size=14, color=ft.Colors.PRIMARY),
                        ft.Text(domain, size=12, color=ft.Colors.PRIMARY),
                    ],
                ),
            ],
        ),
    )
