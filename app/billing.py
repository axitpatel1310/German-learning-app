"""Buying Premium: Google Play on Android, Stripe Checkout in the browser everywhere else.
The accounts server confirms every payment; the app only shows the result.

Google Play is native code in extensions/flet_play_billing (Flutter's in_app_purchase).
"""

import flet as ft


@ft.control("PlayBilling")
class PlayBilling(ft.Service):
    """Bridge to Google Play Billing. Answers None/False on other platforms."""

    async def is_supported(self) -> bool:
        return bool(await self._invoke_method("is_supported"))

    async def buy(self, product_id: str, account_ref: str) -> dict:
        """Opens the Play purchase sheet. Answers {"status": "purchased", "purchase_token": ...},
        or a status of "pending", "cancelled" or "error" (with a "message")."""
        args = {"product_id": product_id, "account_ref": account_ref}
        return await self._invoke_method("buy", args, timeout=900) or {"status": "error"}

    async def pending(self) -> list[dict]:
        """Purchases Play has delivered but the server hasn't confirmed yet (e.g. the app
        closed while paying)."""
        return await self._invoke_method("pending", timeout=30) or []

    async def finish(self, purchase_token: str) -> bool:
        return bool(await self._invoke_method("finish", {"purchase_token": purchase_token}))


def provider_for(payments: list[str], android: bool) -> str:
    """Which way to pay on this device: "google_play", "stripe", "test" or "" (none yet).
    Android apps must sell digital content through Google Play, so no Stripe there."""
    if android and "google_play" in payments:
        return "google_play"
    if not android and "stripe" in payments:
        return "stripe"
    return "test" if "test" in payments else ""
