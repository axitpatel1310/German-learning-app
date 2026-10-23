"""Screens for the account: sign-in with a WhatsApp code, the Premium plan, the profile."""

import asyncio
from datetime import datetime
from typing import Callable

import flet as ft

from app import glass
from app.account import (
    CODE_LENGTH,
    FREE_STORIES,
    PLAN_DAYS,
    PLAN_LABEL,
    PLAN_PRICE,
    Account,
    OtpError,
    Usage,
    fmt_duration,
    mask_phone,
    normalize_phone,
)
from app.billing import PlayBilling, provider_for
from app.data import Story
from app.storage import MyWords
from app.theme import level_color

Navigate = Callable[[str], Callable]

WHATSAPP_GREEN = "#25D366"


def _field(**kwargs) -> ft.TextField:
    return ft.TextField(
        filled=True,
        fill_color=glass.PANEL,
        border_radius=14,
        border_color=glass.EDGE,
        focused_border_color=ft.Colors.PRIMARY,
        text_size=18,
        **kwargs,
    )


def signin_view(page: ft.Page, account: Account, on_signed_in: Callable) -> ft.View:
    """Step 1: phone number. Step 2: the 6-digit code that arrives on WhatsApp."""
    phone_field = _field(
        label="Phone number",
        hint_text="+49 151 23456789",
        prefix_icon=ft.Icons.PHONE_OUTLINED,
        keyboard_type=ft.KeyboardType.PHONE,
        autofocus=True,
    )
    code_field = _field(
        label="Code",
        hint_text="6 digits",
        prefix_icon=ft.Icons.PIN_OUTLINED,
        keyboard_type=ft.KeyboardType.NUMBER,
        max_length=CODE_LENGTH,
    )
    error = ft.Text(color=ft.Colors.ERROR, visible=False)
    sent_to = ft.Text(color=ft.Colors.ON_SURFACE_VARIANT)
    demo_note = ft.Container(visible=False)
    send_btn = ft.FilledButton(
        content="Send code on WhatsApp",
        icon=ft.Icons.CHAT,
        style=ft.ButtonStyle(bgcolor=WHATSAPP_GREEN, color=ft.Colors.WHITE),
    )
    verify_btn = ft.FilledButton(content="Verify and continue", icon=ft.Icons.CHECK)
    step1 = ft.Column([phone_field, send_btn], spacing=14, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
    step2 = ft.Column(spacing=10, visible=False, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

    def show_error(text: str):
        error.value, error.visible = text, bool(text)

    def busy(btn: ft.FilledButton, on: bool):
        btn.disabled = on
        phone_field.disabled = code_field.disabled = on
        page.update()

    async def send(e=None):
        phone = normalize_phone(phone_field.value)
        if not phone:
            show_error("Enter your number with the country code, e.g. +49 151 23456789.")
            page.update()
            return
        show_error("")
        busy(send_btn, True)
        try:
            code = await asyncio.to_thread(account.send_code, phone)
        except OtpError as err:
            show_error(str(err))
            busy(send_btn, False)
            return
        sent_to.value = f"We sent a {CODE_LENGTH}-digit code to {phone} on WhatsApp."
        demo_note.visible = code is not None
        if code is not None:
            demo_note.content = _demo_note(code)
        step1.visible, step2.visible = False, True
        code_field.value = ""
        busy(send_btn, False)
        await code_field.focus()

    async def verify(e=None):
        busy(verify_btn, True)
        try:
            ok = await asyncio.to_thread(account.verify, code_field.value)
        except OtpError as err:
            show_error(str(err))
            busy(verify_btn, False)
            return
        if not ok:
            show_error("That code is not right. Check WhatsApp and try again.")
            busy(verify_btn, False)
            return
        await on_signed_in()

    def change_number(e):
        step1.visible, step2.visible = True, False
        show_error("")
        page.update()

    send_btn.on_click = send
    phone_field.on_submit = send
    verify_btn.on_click = verify
    code_field.on_submit = verify
    step2.controls = [
        sent_to,
        demo_note,
        code_field,
        verify_btn,
        ft.Row(
            [
                ft.TextButton(content="Change number", on_click=change_number),
                ft.TextButton(content="Resend code", on_click=send),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
    ]

    return ft.View(
        route="/signin",
        scroll=ft.ScrollMode.AUTO,
        padding=ft.Padding.symmetric(horizontal=24, vertical=24),
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Container(
                width=440,
                content=ft.Column(
                    spacing=14,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        ft.Container(height=24),
                        ft.Row([glass.icon_tile(ft.Icons.MENU_BOOK, ft.Colors.INDIGO_400, size=64)],
                               alignment=ft.MainAxisAlignment.CENTER),
                        ft.Text("Deutsch mit Geschichten", size=28, weight=ft.FontWeight.BOLD,
                                text_align=ft.TextAlign.CENTER),
                        ft.Text(
                            "Sign in with your phone number. We send you a code on WhatsApp, "
                            "no password needed.",
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        glass.panel(ft.Column([step1, step2, error], spacing=12,
                                              horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                                    padding=20),
                        ft.Text(
                            "One account per phone number. Your number is only used to sign you in.",
                            size=12,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ],
                ),
            )
        ],
    )


def _demo_note(code: str) -> ft.Control:
    return ft.Container(
        padding=12,
        border_radius=12,
        bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.AMBER),
        content=ft.Column(
            spacing=2,
            controls=[
                ft.Text("Demo mode: WhatsApp is not connected yet", weight=ft.FontWeight.W_600, size=13),
                ft.Text(f"Your code is {code}", size=13, selectable=True),
            ],
        ),
    )


def _benefit(text: str) -> ft.Control:
    return ft.Row(
        [ft.Icon(ft.Icons.CHECK_CIRCLE, size=20, color=ft.Colors.GREEN_600), ft.Text(text, expand=True)],
        vertical_alignment=ft.CrossAxisAlignment.START,
    )


PAID_WITH = {
    "google_play": " Paid through Google Play.",
    "stripe": " Paid securely with Stripe in your browser.",
}
_stripe_wait = {"on": False}  # one payment-status poll at a time
STRIPE_WAIT = 15 * 60
STRIPE_POLL = 4


def plan_view(
    page: ft.Page, lib, account: Account, refresh: Callable, play: Callable[[], PlayBilling] | None = None
) -> ft.View:
    """The Premium plan and buying it: Google Play on Android (play is given there), Stripe in
    the browser elsewhere, or the free test purchase on a test server."""
    total = sum(len(v) for v in lib.stories.values())
    provider = provider_for(account.payments, play is not None)

    def say(text: str):
        page.show_dialog(ft.SnackBar(ft.Text(text)))

    def activated():
        refresh()  # rebuilding closes open dialogs, so the snackbar comes after
        say(f"Premium is active until {account.premium_until:%d %b %Y}. Viel Spaß beim Lesen!")

    async def wait_for_stripe():
        # The webhook reaches the server, not the app, so ask the server until Premium shows up.
        was = account.premium_until
        _stripe_wait["on"] = True
        try:
            for _ in range(STRIPE_WAIT // STRIPE_POLL):
                await asyncio.sleep(STRIPE_POLL)
                await asyncio.to_thread(account.refresh)
                if account.premium_until != was:
                    activated()
                    return
        finally:
            _stripe_wait["on"] = False

    async def check_now(e):
        was = account.premium_until
        await asyncio.to_thread(account.refresh)
        if account.premium_until != was:
            activated()
        else:
            say("No payment yet. If you just paid, it can take a few seconds.")

    async def buy_stripe():
        try:
            url = await asyncio.to_thread(account.checkout_url)
        except OtpError as err:
            say(str(err))
            return
        await ft.UrlLauncher().launch_url(url)
        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Finish paying in your browser"),
                content=ft.Text(
                    f"{PLAN_LABEL}, paid securely with Stripe. Premium turns on here by itself "
                    "as soon as the payment is confirmed."
                ),
                actions=[
                    ft.TextButton(content="Close", on_click=lambda e: page.pop_dialog()),
                    ft.FilledButton(content="I've paid", on_click=check_now),
                ],
            )
        )
        if not _stripe_wait["on"]:
            page.run_task(wait_for_stripe)

    async def buy_play():
        billing = play()
        res = await billing.buy(account.play_product, account.billing_ref)
        status = res.get("status")
        if status == "pending":
            say("Google Play is still processing the payment. Premium turns on once it's done.")
            return
        if status != "purchased":
            if status != "cancelled":
                say(res.get("message") or "The purchase didn't work. No money was charged.")
            return
        try:
            await asyncio.to_thread(account.confirm_play, res["purchase_token"])
        except OtpError as err:
            say(f"{err} Your purchase is safe: it's checked again the next time the app starts.")
            return
        await billing.finish(res["purchase_token"])
        activated()

    def buy(e):
        async def confirm(e):
            page.pop_dialog()
            try:
                await asyncio.to_thread(account.buy)
            except OtpError as err:
                say(str(err))
                return
            activated()

        if provider == "stripe":
            page.run_task(buy_stripe)
            return
        if provider == "google_play":
            page.run_task(buy_play)
            return
        if not provider:
            page.show_dialog(
                ft.AlertDialog(
                    title=ft.Text("Coming soon"),
                    content=ft.Text("Payments are not connected yet. Premium will be available here soon."),
                    actions=[ft.TextButton(content="OK", on_click=lambda e: page.pop_dialog())],
                )
            )
            return
        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Get Premium"),
                content=ft.Text(
                    f"{PLAN_LABEL} ({PLAN_DAYS} days).\n\n"
                    "Test purchase: payments are not connected yet, so no money is charged."
                ),
                actions=[
                    ft.TextButton(content="Cancel", on_click=lambda e: page.pop_dialog()),
                    ft.FilledButton(content="Confirm test purchase", on_click=confirm),
                ],
            )
        )

    if account.premium:
        status = [
            ft.Text("You have Premium", size=20, weight=ft.FontWeight.BOLD),
            ft.Text(f"Active until {account.premium_until:%d %B %Y} · {account.days_left()} days left"),
        ]
        button = ft.FilledTonalButton(content=f"Add 3 more months · {PLAN_PRICE}", icon=ft.Icons.ADD, on_click=buy)
    else:
        status = [ft.Text("Free plan", size=20, weight=ft.FontWeight.BOLD),
                  ft.Text(f"The first {FREE_STORIES} stories of each level.")]
        button = ft.FilledButton(content=f"Get Premium · {PLAN_PRICE}", icon=ft.Icons.WORKSPACE_PREMIUM, on_click=buy)

    return ft.View(
        route="/premium",
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        spacing=10,
        appbar=ft.AppBar(title=ft.Text("Premium")),
        controls=[
            glass.panel(ft.Column(status, spacing=4)),
            glass.panel(
                ft.Column(
                    spacing=10,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        ft.Row([glass.icon_tile(ft.Icons.WORKSPACE_PREMIUM, ft.Colors.AMBER_700, size=40),
                                ft.Text("Premium", size=22, weight=ft.FontWeight.BOLD)]),
                        ft.Row(
                            [ft.Text(PLAN_PRICE, size=40, weight=ft.FontWeight.BOLD),
                             ft.Text("for 3 months", size=16, color=ft.Colors.ON_SURFACE_VARIANT)],
                            vertical_alignment=ft.CrossAxisAlignment.END,
                        ),
                        ft.Text("About €3.33 a month. One payment, no automatic renewal."
                                + PAID_WITH.get(provider, ""),
                                size=13, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Divider(),
                        _benefit(f"All {total} stories from A1 to C2, and every new story we add"),
                        _benefit("Tap-to-translate, My Words, word search and the games, as on the free plan"),
                        *([_benefit("No ads")] if account.server else []),
                        _benefit("Enough time to prepare for a Goethe, telc or TestDaF exam"),
                        ft.Container(height=4),
                        button,
                    ],
                ),
                padding=20,
            ),
        ],
    )


def locked_view(story: Story, position: int, nav: Navigate) -> ft.View:
    """Shown instead of the reader for a Premium story."""
    return ft.View(
        route=f"/story/{story.id}",
        padding=24,
        appbar=ft.AppBar(title=ft.Text(story.title)),
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            glass.panel(
                width=440,
                padding=24,
                content=ft.Column(
                    spacing=10,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        glass.icon_tile(ft.Icons.LOCK, level_color(story.level), size=56),
                        ft.Text(story.title, size=22, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                        ft.Text(f"{story.title_en} · {story.level} story {position}",
                                color=ft.Colors.ON_SURFACE_VARIANT, text_align=ft.TextAlign.CENTER),
                        ft.Text(
                            f"The first {FREE_STORIES} stories of each level are free. "
                            f"Premium opens all of them: {PLAN_LABEL}.",
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.FilledButton(content="See Premium", icon=ft.Icons.WORKSPACE_PREMIUM,
                                        on_click=nav("/premium")),
                    ],
                ),
            )
        ],
    )


def _stat(label: str, value: str, icon: str, color: str) -> ft.Control:
    return glass.panel(
        col={"xs": 6, "md": 3},
        padding=14,
        content=ft.Column(
            spacing=4,
            controls=[
                glass.icon_tile(icon, color, size=28),
                ft.Text(value, size=20, weight=ft.FontWeight.BOLD),
                ft.Text(label, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            ],
        ),
    )


def _week_chart(usage: Usage) -> ft.Control:
    days = usage.last_days(7)
    peak = max(max(s for _, s in days), 10 * 60)  # short days stay short bars
    bars = []
    for day, seconds in days:
        today = day == datetime.now().date()
        bars.append(
            ft.Column(
                expand=True,
                spacing=4,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.END,
                controls=[
                    ft.Text(f"{int(seconds // 60)}", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Container(
                        width=22,
                        height=max(4, 100 * seconds / peak),
                        border_radius=6,
                        bgcolor=ft.Colors.PRIMARY if today else ft.Colors.with_opacity(0.45, ft.Colors.PRIMARY),
                    ),
                    ft.Text(day.strftime("%a")[:2], size=12,
                            weight=ft.FontWeight.BOLD if today else ft.FontWeight.NORMAL),
                ],
            )
        )
    return glass.panel(
        ft.Column(
            [ft.Text("Minutes per day, last 7 days", size=13, color=ft.Colors.ON_SURFACE_VARIANT),
             ft.Container(ft.Row(bars, vertical_alignment=ft.CrossAxisAlignment.END), height=150)],
            spacing=8,
        )
    )


def profile_view(
    page: ft.Page, account: Account, usage: Usage, my_words: MyWords, nav: Navigate, on_sign_out: Callable
) -> ft.View:
    created = account.data.get("created_at")
    since = datetime.fromtimestamp(created).strftime("%d %B %Y") if created else "today"
    week = sum(s for _, s in usage.last_days(7))

    def sign_out(e):
        async def confirm(e):
            page.pop_dialog()
            await on_sign_out()

        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Sign out?"),
                content=ft.Text("Your saved words stay on this device. Sign in again with the same "
                                "number to keep your plan"
                                + (" and your time stats." if account.server else ".")),
                actions=[
                    ft.TextButton(content="Cancel", on_click=lambda e: page.pop_dialog()),
                    ft.FilledButton(content="Sign out", on_click=confirm),
                ],
            )
        )

    if account.premium:
        plan_row = ("Premium", f"Until {account.premium_until:%d %b %Y} · {account.days_left()} days left",
                    ft.Colors.AMBER_700)
    else:
        plan_row = ("Free plan", f"Upgrade: {PLAN_LABEL}", ft.Colors.BLUE_GREY_400)

    return ft.View(
        route="/profile",
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        spacing=10,
        appbar=ft.AppBar(title=ft.Text("Profile")),
        controls=[
            glass.panel(
                ft.Row(
                    [
                        ft.CircleAvatar(
                            content=ft.Icon(ft.Icons.PERSON, color=ft.Colors.WHITE),
                            bgcolor=ft.Colors.INDIGO_400,
                            radius=28,
                        ),
                        ft.Column(
                            [
                                ft.Text(mask_phone(account.phone), size=20, weight=ft.FontWeight.BOLD),
                                ft.Text(f"Member since {since}", color=ft.Colors.ON_SURFACE_VARIANT),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                    spacing=14,
                )
            ),
            glass.section_label("Plan"),
            glass.panel(
                ft.ListTile(
                    leading=glass.icon_tile(ft.Icons.WORKSPACE_PREMIUM, plan_row[2]),
                    title=ft.Text(plan_row[0], weight=ft.FontWeight.W_600),
                    subtitle=ft.Text(plan_row[1], size=13, color=ft.Colors.ON_SURFACE_VARIANT),
                    trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, color=ft.Colors.OUTLINE),
                    on_click=nav("/premium"),
                ),
                padding=ft.Padding.symmetric(vertical=4),
            ),
            glass.section_label("Time spent learning"),
            ft.ResponsiveRow(
                spacing=10,
                run_spacing=10,
                controls=[
                    _stat("Today", fmt_duration(usage.seconds(datetime.now().date())),
                          ft.Icons.TODAY, ft.Colors.INDIGO_400),
                    _stat("Last 7 days", fmt_duration(week), ft.Icons.DATE_RANGE, ft.Colors.TEAL_400),
                    _stat("All time", fmt_duration(usage.total()), ft.Icons.TIMER_OUTLINED,
                          ft.Colors.BLUE_400),
                    _stat("Day streak", str(usage.streak()), ft.Icons.LOCAL_FIRE_DEPARTMENT,
                          ft.Colors.ORANGE_400),
                ],
            ),
            _week_chart(usage),
            ft.Text(
                f"{len(my_words)} saved words · {usage.sessions} app sessions. Time counts while "
                "the app is open and visible"
                + (", on all your devices." if account.server else "."),
                size=12,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            *([
                glass.section_label("For businesses"),
                glass.panel(
                    ft.ListTile(
                        leading=glass.icon_tile(ft.Icons.CAMPAIGN_OUTLINED, ft.Colors.PINK_400),
                        title=ft.Text("Advertise your business", weight=ft.FontWeight.W_600),
                        subtitle=ft.Text("Show your ad to German learners. Pay per 1,000 views.",
                                         size=13, color=ft.Colors.ON_SURFACE_VARIANT),
                        trailing=ft.Icon(ft.Icons.OPEN_IN_NEW, color=ft.Colors.OUTLINE),
                        on_click=lambda e: page.run_task(ft.UrlLauncher().launch_url, account.ads_url),
                    ),
                    padding=ft.Padding.symmetric(vertical=4),
                ),
            ] if account.server else []),
            ft.Container(height=4),
            ft.OutlinedButton(content="Sign out", icon=ft.Icons.LOGOUT, on_click=sign_out),
            ft.Container(height=12),
        ],
    )
