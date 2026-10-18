import flet as ft

LEVEL_INFO = {
    "A1": ("Beginner", ft.Colors.GREEN_600),
    "A2": ("Elementary", ft.Colors.LIGHT_GREEN_700),
    "B1": ("Intermediate", ft.Colors.AMBER_800),
    "B2": ("Upper intermediate", ft.Colors.ORANGE_800),
    "C1": ("Advanced", ft.Colors.DEEP_ORANGE_700),
    "C2": ("Proficient", ft.Colors.RED_700),
}

HIGHLIGHT = ft.Colors.with_opacity(0.35, ft.Colors.AMBER)


def level_name(level: str) -> str:
    return LEVEL_INFO[level][0]


def level_color(level: str) -> str:
    return LEVEL_INFO[level][1]
