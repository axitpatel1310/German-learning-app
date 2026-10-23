"""Payments for the Premium plan, confirmed by the server.

- Stripe Checkout (desktop and web): the server creates a Checkout Session and Stripe calls the
  webhook when the payment is done. Only the signed webhook grants Premium.
- Google Play Billing (Android): the app buys the one-time product and sends the purchase token
  here. The server checks it with the Google Play Developer API, then consumes it so the plan
  can be bought again.

Each payment reference (Checkout Session id, Play order id) is granted once only.
"""

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request

PLAN_CENTS = 1000  # €10
CURRENCY = "eur"
STRIPE_API = "https://api.stripe.com/v1"
STRIPE_TOLERANCE = 300  # seconds a webhook signature stays valid
PLAY_API = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications"
PLAY_SCOPE = "https://www.googleapis.com/auth/androidpublisher"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


class BillingError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def http(method: str, url: str, form: dict | None = None, headers: dict | None = None) -> dict:
    """A form-encoded request that answers JSON (both Stripe and Google work this way)."""
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read())
        except ValueError:
            detail = {}
        raise BillingError(f"payment provider answered {e.code}: {detail}", e.code) from e
    except OSError as e:
        raise BillingError("payment provider not reachable") from e


class Stripe:
    def __init__(self, secret_key: str, webhook_secret: str, public_url: str, price_id: str = "", request=http):
        self.secret_key = secret_key
        self.webhook_secret = webhook_secret
        self.public_url = public_url.rstrip("/")
        self.price_id = price_id
        self.request = request

    def checkout(self, user_id: int) -> str:
        """A Checkout Session for one 3-month plan. Returns the page to pay on."""
        return self.session(str(user_id), "Premium · 3 months", PLAN_CENTS, "/billing/done",
                            "/billing/cancel", price_id=self.price_id)

    def session(self, ref: str, name: str, cents: int, success_path: str, cancel_path: str,
                price_id: str = "", email: str = "") -> str:
        """A one-off Checkout Session; `ref` comes back in the webhook as client_reference_id."""
        form = {
            "mode": "payment",
            "client_reference_id": ref,
            "metadata[ref]": ref,
            "line_items[0][quantity]": "1",
            "success_url": f"{self.public_url}{success_path}",
            "cancel_url": f"{self.public_url}{cancel_path}",
        }
        if email:
            form["customer_email"] = email
        if price_id:
            form["line_items[0][price]"] = price_id
        else:
            form.update({
                "line_items[0][price_data][currency]": CURRENCY,
                "line_items[0][price_data][unit_amount]": str(cents),
                "line_items[0][price_data][product_data][name]": name,
            })
        session = self.request(
            "POST", f"{STRIPE_API}/checkout/sessions", form,
            {"Authorization": f"Bearer {self.secret_key}"},
        )
        if not session.get("url"):
            raise BillingError("Stripe did not return a payment page")
        return session["url"]

    def verify(self, payload: bytes, signature: str, now: float | None = None) -> dict:
        """The webhook event, if its Stripe-Signature header is valid and recent."""
        parts = [p.split("=", 1) for p in signature.split(",") if "=" in p]
        stamp = next((v for k, v in parts if k == "t"), "")
        sigs = [v for k, v in parts if k == "v1"]
        if not stamp.isdigit() or not sigs:
            raise BillingError("bad signature", 400)
        if abs((now or time.time()) - int(stamp)) > STRIPE_TOLERANCE:
            raise BillingError("signature too old", 400)
        expected = hmac.new(
            self.webhook_secret.encode(), stamp.encode() + b"." + payload, hashlib.sha256
        ).hexdigest()
        if not any(hmac.compare_digest(expected, s) for s in sigs):
            raise BillingError("bad signature", 400)
        try:
            return json.loads(payload)
        except ValueError as e:
            raise BillingError("bad payload", 400) from e

    @staticmethod
    def paid_session(event: dict) -> dict | None:
        """The Checkout Session from a 'paid' event, or None for every other event."""
        if event.get("type") not in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
            return None
        session = event.get("data", {}).get("object", {})
        if session.get("payment_status") != "paid" or not session.get("client_reference_id"):
            return None
        return session


class GooglePlay:
    """Checks one-time product purchases with the Google Play Developer API, using a service
    account key file (needs `pip install google-auth` on the server)."""

    def __init__(self, package: str, product_id: str, key_file: str, request=http, access_token=None):
        self.package = package
        self.product_id = product_id
        self.key_file = key_file
        self.request = request
        self._token_source = access_token or self._service_account_token
        self._token, self._token_until = "", 0.0

    def _service_account_token(self) -> tuple[str, float]:
        from google.auth import crypt, jwt  # optional dependency, only for Google Play

        with open(self.key_file, encoding="utf-8") as f:
            info = json.load(f)
        now = int(time.time())
        assertion = jwt.encode(crypt.RSASigner.from_service_account_info(info), {
            "iss": info["client_email"], "scope": PLAY_SCOPE, "aud": GOOGLE_TOKEN_URL,
            "iat": now, "exp": now + 3600,
        })
        res = self.request("POST", GOOGLE_TOKEN_URL, {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion.decode() if isinstance(assertion, bytes) else assertion,
        })
        return res["access_token"], now + int(res.get("expires_in", 3600))

    def _auth(self) -> dict:
        if time.time() > self._token_until - 60:
            self._token, self._token_until = self._token_source()
        return {"Authorization": f"Bearer {self._token}"}

    def _url(self, token: str, action: str = "") -> str:
        quote = urllib.parse.quote
        return (f"{PLAY_API}/{quote(self.package)}/purchases/products/{quote(self.product_id)}"
                f"/tokens/{quote(token, safe='')}{action}")

    def check(self, token: str, account_ref: str) -> str:
        """The order id of a valid purchase made by this account. Raises BillingError otherwise."""
        purchase = self.request("GET", self._url(token), None, self._auth())
        if purchase.get("purchaseState") != 0:
            raise BillingError("The purchase is not completed (yet).", 402)
        if purchase.get("obfuscatedExternalAccountId") != account_ref:
            raise BillingError("This purchase belongs to another account.", 403)
        return purchase.get("orderId") or token

    def consume(self, token: str):
        """Marks the purchase as used, so the plan can be bought again. A failure here is
        harmless for the user: the grant is already saved and counted once."""
        try:
            self.request("POST", self._url(token, ":consume"), {}, self._auth())
        except BillingError:
            pass
