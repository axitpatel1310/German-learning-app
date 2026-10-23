"""Exam topics (Goethe/telc/TestDaF "Themen") that stories are tagged with."""

from dataclasses import dataclass

import flet as ft


@dataclass(frozen=True)
class Topic:
    key: str
    name: str  # German
    name_en: str
    icon: str


TOPICS = [
    Topic("wohnen", "Wohnen", "Home and housing", ft.Icons.HOME_OUTLINED),
    Topic("familie", "Familie & Freunde", "Family and relationships", ft.Icons.PEOPLE_OUTLINE),
    Topic("essen", "Essen & Trinken", "Food and drink", ft.Icons.RESTAURANT),
    Topic("einkaufen", "Einkaufen & Konsum", "Shopping and consumers", ft.Icons.SHOPPING_BAG_OUTLINED),
    Topic("gesundheit", "Gesundheit", "Health and the body", ft.Icons.LOCAL_HOSPITAL_OUTLINED),
    Topic("arbeit", "Arbeit & Beruf", "Work and careers", ft.Icons.WORK_OUTLINE),
    Topic("bildung", "Schule & Bildung", "School and education", ft.Icons.SCHOOL_OUTLINED),
    Topic("reisen", "Reisen & Verkehr", "Travel and transport", ft.Icons.TRAIN_OUTLINED),
    Topic("freizeit", "Freizeit & Kultur", "Free time, sport and culture", ft.Icons.PALETTE_OUTLINED),
    Topic("feste", "Feste & Traditionen", "Holidays and traditions", ft.Icons.CELEBRATION_OUTLINED),
    Topic("aemter", "Ämter & Dienstleistungen", "Offices, bank and post", ft.Icons.ACCOUNT_BALANCE_OUTLINED),
    Topic("umwelt", "Umwelt & Natur", "Environment, nature and weather", ft.Icons.ECO_OUTLINED),
    Topic("medien", "Medien & Technik", "Media, science and technology", ft.Icons.DEVICES_OUTLINED),
    Topic("gesellschaft", "Gesellschaft & Politik", "Society and politics", ft.Icons.GROUPS_OUTLINED),
    Topic("wirtschaft", "Wirtschaft & Geld", "Economy and money", ft.Icons.EURO),
    Topic("sprache", "Sprache & Kommunikation", "Language and communication", ft.Icons.FORUM_OUTLINED),
    Topic("psyche", "Mensch & Psyche", "Feelings, habits and personality", ft.Icons.PSYCHOLOGY_OUTLINED),
]

TOPIC_BY_KEY = {t.key: t for t in TOPICS}
