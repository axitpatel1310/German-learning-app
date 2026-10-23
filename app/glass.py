"""Glass style: soft gradient backdrops, frosted rounded panels and smooth transitions."""

from typing import Callable

import flet as ft

RADIUS = 22

# Backdrop gradients, top-left to bottom-right: pale lilac, near white, mint (light);
# deep navy, aubergine, petrol (dark). The panels on top are translucent, so these show
# through faintly and give the frosted look.
BACKDROP = {
    False: ["#E9ECFF", "#F7F5FB", "#E6F4F1"],
    True: ["#0F1222", "#1A1530", "#0C1B22"],
}
PANEL = ft.Colors.with_opacity(0.62, ft.Colors.SURFACE_CONTAINER_LOWEST)
# A bright hairline in light mode, a faint one in dark mode.
EDGE = ft.Colors.with_opacity(0.8, ft.Colors.SURFACE_BRIGHT)
SHADOW = ft.BoxShadow(
    blur_radius=24, spread_radius=-6, offset=ft.Offset(0, 8),
    color=ft.Colors.with_opacity(0.10, ft.Colors.BLACK),
)


def theme(dark: bool) -> ft.Theme:
    rounded = ft.RoundedRectangleBorder(radius=RADIUS)
    return ft.Theme(
        color_scheme_seed=ft.Colors.INDIGO,
        scaffold_bgcolor=BACKDROP[dark][1],
        page_transitions=ft.PageTransitionsTheme(
            android=ft.PageTransitionTheme.CUPERTINO,
            ios=ft.PageTransitionTheme.CUPERTINO,
            macos=ft.PageTransitionTheme.CUPERTINO,
            windows=ft.PageTransitionTheme.CUPERTINO,
            linux=ft.PageTransitionTheme.CUPERTINO,
        ),
        appbar_theme=ft.AppBarTheme(
            bgcolor=ft.Colors.TRANSPARENT,
            elevation=0,
            elevation_on_scroll=0,
            center_title=True,
            title_text_style=ft.TextStyle(size=17, weight=ft.FontWeight.W_600),
        ),
        card_theme=ft.CardTheme(
            color=PANEL,
            elevation=0,
            margin=ft.Margin.symmetric(vertical=4),
            shape=ft.RoundedRectangleBorder(radius=RADIUS, side=ft.BorderSide(1, EDGE)),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        ),
        bottom_sheet_theme=ft.BottomSheetTheme(
            bgcolor=ft.Colors.with_opacity(0.97, ft.Colors.SURFACE_CONTAINER_LOW),
            elevation=0,
            shape=ft.RoundedRectangleBorder(radius=ft.BorderRadius.only(top_left=28, top_right=28)),
            drag_handle_color=ft.Colors.OUTLINE_VARIANT,
        ),
        snackbar_theme=ft.SnackBarTheme(
            behavior=ft.SnackBarBehavior.FLOATING,
            shape=ft.RoundedRectangleBorder(radius=16),
        ),
        list_tile_theme=ft.ListTileTheme(shape=rounded),
        expansion_tile_theme=ft.ExpansionTileTheme(shape=rounded, collapsed_shape=rounded),
        filled_button_theme=ft.FilledButtonTheme(style=ft.ButtonStyle(shape=ft.StadiumBorder())),
        divider_theme=ft.DividerTheme(color=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE), thickness=1),
    )


def backdrop(dark: bool) -> ft.BoxDecoration:
    return ft.BoxDecoration(
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
            colors=BACKDROP[dark],
        )
    )


def panel(
    content: ft.Control,
    padding: int | ft.Padding = 16,
    radius: int = RADIUS,
    on_click: Callable | None = None,
    **kwargs,
) -> ft.Container:
    """A frosted, rounded panel with a hairline edge and a soft shadow."""
    return ft.Container(
        content=content,
        padding=padding,
        border_radius=radius,
        bgcolor=PANEL,
        border=ft.Border.all(1, EDGE),
        shadow=SHADOW,
        ink=on_click is not None,
        on_click=on_click,
        **kwargs,
    )


def icon_tile(icon: str, color: str, size: int = 32) -> ft.Control:
    """A coloured rounded square with a white icon, like the rows in iOS Settings."""
    return ft.Container(
        width=size,
        height=size,
        border_radius=size * 0.28,
        alignment=ft.Alignment.CENTER,
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_CENTER,
            end=ft.Alignment.BOTTOM_CENTER,
            colors=[ft.Colors.with_opacity(0.80, color), color],
        ),
        content=ft.Icon(icon, size=size * 0.58, color=ft.Colors.WHITE),
    )


def section_label(text: str) -> ft.Control:
    return ft.Container(
        padding=ft.Padding.only(left=6, top=10, bottom=2),
        content=ft.Text(
            text.upper(), size=12, weight=ft.FontWeight.W_600, color=ft.Colors.ON_SURFACE_VARIANT
        ),
    )
