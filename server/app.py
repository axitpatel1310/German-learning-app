"""The accounts server: sign-in with WhatsApp codes, one account per phone number, the
Premium plan, time stats that follow you across devices, and ads sold per view.

Standard library only. Run with `python -m server` (see server/README.md for the settings).
"""

import json
import os
import re
import secrets
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.otp import (
    CODE_LENGTH,
    RESEND_AFTER,
    OtpError,
    normalize_phone,
    otp_provider,
)
from server import admin, ads, invoice
from server.billing import BillingError, GooglePlay, Stripe
from server.db import Store
from server.mail import Mailer

PLAN_DAYS = 90
SENDS_PER_PHONE = 5  # codes per number per hour
SENDS_PER_IP = 20  # codes per address per hour (stops someone running up the WhatsApp bill)
MAX_BODY = 64 * 1024
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Config:
    def __init__(self, env=os.environ):
        self.db_path = env.get("DMG_DB", "accounts.db")
        self.production = env.get("DMG_ENV") == "production"
        self.test_payments = env.get("DMG_TEST_PAYMENTS") == "1" and not self.production
        self.trust_proxy = env.get("DMG_TRUST_PROXY") == "1"
        self.max_sessions = int(env.get("DMG_MAX_DEVICES", "3"))
        self.public_url = env.get("DMG_PUBLIC_URL", "http://127.0.0.1:8600")
        self.stripe_key = env.get("STRIPE_SECRET_KEY", "")
        self.stripe_webhook_secret = env.get("STRIPE_WEBHOOK_SECRET", "")
        self.stripe_price = env.get("STRIPE_PRICE_ID", "")
        self.play_package = env.get("GOOGLE_PLAY_PACKAGE", "")
        self.play_product = env.get("GOOGLE_PLAY_PRODUCT_ID", "premium_3_months")
        self.play_key_file = env.get("GOOGLE_PLAY_KEY_FILE", "")
        self.admin_key = env.get("DMG_ADMIN_KEY", "")
        self.ad_prices = ads.prices(env)
        self.seller = invoice.Seller(env)
        self.mail_env = env

    @property
    def stripe(self) -> bool:
        return bool(self.stripe_key and self.stripe_webhook_secret)

    @property
    def google_play(self) -> bool:
        return bool(self.play_package and self.play_key_file)


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class Server:
    def __init__(self, config: Config, otp=None, stripe=None, play=None):
        self.config = config
        self.store = Store(config.db_path, config.max_sessions)
        self.otp = otp or otp_provider()
        self.stripe = stripe
        if not stripe and config.stripe:
            self.stripe = Stripe(config.stripe_key, config.stripe_webhook_secret,
                                 config.public_url, config.stripe_price)
        self.play = play
        if not play and config.google_play:
            self.play = GooglePlay(config.play_package, config.play_product, config.play_key_file)
        self.otp_lock = threading.Lock()
        self.mailer = Mailer(config.mail_env)
        if config.production and self.otp.demo:
            raise SystemExit("DMG_ENV=production needs the TWILIO_* settings: demo codes are off.")

    def account(self, user) -> dict:
        return {
            "phone": user["phone"],
            "created_at": user["created_at"],
            "premium_until": user["premium_until"],
            "payments": self.payments,
            "billing_ref": billing_ref(user),
            "play_product": self.play.product_id if self.play else "",
        }

    @property
    def payments(self) -> list[str]:
        return ((["stripe"] if self.stripe else []) + (["google_play"] if self.play else [])
                + (["test"] if self.config.test_payments else []))

    # routes

    def auth_start(self, body: dict, ip: str) -> dict:
        phone = normalize_phone(body.get("phone", ""))
        if not phone:
            raise ApiError(400, "Enter your number with the country code, e.g. +49 151 23456789.")
        now = time.time()
        if self.store.sends_since(f"phone:{phone}", now - RESEND_AFTER):
            raise ApiError(429, f"Please wait {RESEND_AFTER} s before asking for another code.")
        if self.store.sends_since(f"phone:{phone}", now - 3600) >= SENDS_PER_PHONE \
                or self.store.sends_since(f"ip:{ip}", now - 3600) >= SENDS_PER_IP:
            raise ApiError(429, "Too many codes requested. Please try again in an hour.")
        try:
            with self.otp_lock:
                code = self.otp.send(phone)
        except OtpError as e:
            raise ApiError(502, str(e)) from e
        self.store.log_send(f"phone:{phone}", f"ip:{ip}")
        return {"sent": True, "demo_code": code} if self.otp.demo else {"sent": True}

    def auth_verify(self, body: dict) -> dict:
        phone = normalize_phone(body.get("phone", ""))
        code = re.sub(r"\D", "", str(body.get("code", "")))
        if not phone or len(code) != CODE_LENGTH:
            raise ApiError(400, "Enter the 6-digit code.")
        try:
            with self.otp_lock:
                ok = self.otp.check(phone, code)
        except OtpError as e:
            raise ApiError(400, str(e)) from e
        if not ok:
            raise ApiError(401, "That code is not right. Check WhatsApp and try again.")
        user, token = self.store.sign_in(phone)
        return {"token": token, "account": self.account(user)}

    def usage(self, user, body: dict) -> dict:
        device = str(body.get("device", ""))[:64]
        days = body.get("days")
        if not device or not isinstance(days, dict):
            raise ApiError(400, "device and days are required")
        clean = {
            d: min(float(s), 86400.0)
            for d, s in list(days.items())[:1000]
            if DAY_RE.match(str(d)) and isinstance(s, (int, float)) and s >= 0
        }
        self.store.save_usage(user["id"], device, clean)
        return {"others": self.store.other_usage(user["id"], device)}

    def checkout(self, user, body: dict) -> dict:
        """Stripe: the page to pay on. Test payments: Premium straight away."""
        provider = body.get("provider", "test")
        if provider == "stripe" and self.stripe:
            try:
                return {"url": self.stripe.checkout(user["id"])}
            except BillingError as e:
                print(f"stripe checkout failed: {e}")
                raise ApiError(502, "The payment page could not be opened. Please try again.") from e
        if provider == "test" and self.config.test_payments:
            self.store.grant(user["id"], "test", "test-" + secrets.token_hex(8), PLAN_DAYS, "€10 (test)")
            return {"account": self.account(self.store.user(user["id"]))}
        raise ApiError(503, "Payments are not connected yet. Please try again later.")

    def stripe_webhook(self, payload: bytes, signature: str) -> dict:
        """Stripe says a Checkout Session is paid. Only correctly signed events count."""
        if not self.stripe:
            raise ApiError(404, "Not found")
        try:
            session = self.stripe.paid_session(self.stripe.verify(payload, signature))
        except BillingError as e:
            raise ApiError(e.status, str(e)) from e
        ref = str(session.get("client_reference_id", "")) if session else ""
        if ref.startswith("ad-") and ref[3:].isdigit():
            self.ad_paid(int(ref[3:]), session)
        elif ref.isdigit():
            user = self.store.user(int(ref))
            if user:
                amount = f"{session.get('amount_total', 0) / 100:.2f} {session.get('currency', '').upper()}"
                self.store.grant(user["id"], "stripe", session["id"], PLAN_DAYS, amount)
        return {"received": True}

    def play_verify(self, user, body: dict) -> dict:
        """The app bought the product on Google Play: check the token, then grant and consume."""
        if not self.play:
            raise ApiError(503, "Google Play payments are not connected yet.")
        token = str(body.get("purchase_token", ""))
        if not token or body.get("product_id", self.play.product_id) != self.play.product_id:
            raise ApiError(400, "purchase_token is required")
        try:
            order = self.play.check(token, billing_ref(user))
        except BillingError as e:
            if e.status in (402, 403):
                raise ApiError(e.status, str(e)) from e
            print(f"google play check failed: {e}")
            raise ApiError(502, "Google Play could not confirm the purchase. Please try again.") from e
        self.store.grant(user["id"], "google_play", order, PLAN_DAYS, "€10")
        self.play.consume(token)
        return {"account": self.account(self.store.user(user["id"]))}

    # ads

    def next_ad(self, user, body: dict | None = None) -> dict:
        """An ad for free users; Premium is ad-free. The app sends the level the learner is
        reading at, for ads aimed at some levels only."""
        if user["premium_until"] > time.time():
            return {"ad": None}
        level = str((body or {}).get("level", "")).upper()
        c = self.store.next_ad(user["id"], level if level in ads.LEVELS else "")
        return {"ad": ads.public_ad(c) if c else None}

    def ad_seen(self, user, body: dict) -> dict:
        campaign_id = body.get("id")
        if not isinstance(campaign_id, int) or user["premium_until"] > time.time():
            return {"counted": False}
        result = self.store.count_view(campaign_id, user["id"])
        if result == "completed":
            self.notify(self.store.campaign(campaign_id), ads.completed_email)
        return {"counted": bool(result)}

    def ad_click(self, body: dict) -> dict:
        if isinstance(body.get("id"), int):
            self.store.count_click(body["id"])
        return {"ok": True}

    @property
    def ad_payments(self) -> list[str]:
        return (["stripe"] if self.stripe else []) + (["test"] if self.config.test_payments else [])

    def ad_paid(self, campaign_id: int, session: dict):
        """Stripe confirmed a booking. Only the full price in euros counts."""
        c = self.store.campaign(campaign_id)
        if not c or session.get("amount_total") != c["price_cents"] or session.get("currency") != "eur":
            print(f"ad payment for #{campaign_id} ignored: the amount or campaign doesn't match")
            return
        if self.store.mark_paid(campaign_id, session["id"]):
            print(f"ad #{campaign_id} paid, waiting for approval")

    def status_url(self, c) -> str:
        return f"{self.config.public_url.rstrip('/')}/ads/c/{c['token']}"

    def notify(self, c, email):
        """Keeps the email in the database, then sends it if a mail server is set."""
        subject, text = email(c, self.status_url(c))
        nid = self.store.add_notification(c["id"], c["email"], subject, text)
        self.mailer.send_later(c["email"], subject, text,
                               lambda ok: ok and self.store.notification_sent(nid))

    def book(self, form: dict, ip: str) -> tuple[int, bytes, dict]:
        if self.store.sends_since(f"ads:{ip}", time.time() - 3600) >= ads.REQUESTS_PER_IP:
            return 429, ads.page("Too many bookings", "<p>Please try again in an hour.</p>"), {}
        fields, error = ads.validate(form)
        if error:
            return 400, ads.request_page(self.config.ad_prices, error, form), {}
        self.store.log_send(f"ads:{ip}")
        c = self.store.add_campaign(**fields, price_cents=self.config.ad_prices[fields["views_target"]])
        print(f"new ad booking #{c['id']} ({c['views_target']} views)")
        return 303, b"", {"Location": f"/ads/c/{c['token']}"}

    def pay(self, c, provider: str) -> tuple[int, bytes, dict]:
        back = {"Location": f"/ads/c/{c['token']}"}
        if c["status"] != "unpaid":
            return 303, b"", back
        if provider == "stripe" and self.stripe:
            try:
                url = self.stripe.session(
                    f"ad-{c['id']}", f"Ad · {c['views_target']:,} views", c["price_cents"],
                    f"/ads/c/{c['token']}?paid=1", f"/ads/c/{c['token']}", email=c["email"])
            except BillingError as e:
                print(f"stripe checkout for an ad failed: {e}")
                return 502, ads.campaign_page(
                    c, self.ad_payments, "The payment page could not be opened. Please try again."), {}
            return 303, b"", {"Location": url}
        if provider == "test" and self.config.test_payments:
            self.store.mark_paid(c["id"], "test-" + secrets.token_hex(8))
            return 303, b"", {"Location": f"/ads/c/{c['token']}?paid=1"}
        return 400, ads.campaign_page(c, self.ad_payments, "This payment method isn't available."), {}

    def can_invoice(self, c) -> bool:
        """Paid bookings, and unpaid ones on a server without online payment (paid by transfer)."""
        return c["status"] in ("paid", "active", "paused", "completed") or (
            c["status"] == "unpaid" and not self.ad_payments)

    def invoice_number(self, c) -> str:
        inv = self.store.invoice(c["id"])
        return invoice.number(inv["number"], inv["issued_at"]) if inv else ""

    def invoice_pdf(self, c) -> tuple[int, bytes, dict]:
        inv = self.store.invoice(c["id"])
        if not inv:
            return 303, b"", {"Location": f"/ads/c/{c['token']}"}
        no = invoice.number(inv["number"], inv["issued_at"])
        return 200, invoice.render(c, inv, self.config.seller), {
            "Content-Type": "application/pdf",
            "Content-Disposition": f'inline; filename="Rechnung-{no}.pdf"'}

    def admin_action(self, form: dict) -> str:
        if not hmac_equal(form.get("csrf", ""), ads.csrf_token(self.config.admin_key)):
            return "That form has expired. Please reload the page."
        try:
            c = self.store.campaign(int(form.get("id", "")))
        except ValueError:
            c = None
        if not c:
            return "Campaign not found."
        moves = {"start": ("active", ("paid", "unpaid")), "pause": ("paused", ("active",)),
                 "resume": ("active", ("paused",)), "decline": ("declined", ("unpaid", "paid", "paused"))}
        action = form.get("action", "")
        if action not in moves or not self.store.set_status(c["id"], *moves[action]):
            return "That change isn't possible any more."
        if action == "start":
            self.notify(self.store.campaign(c["id"]), ads.live_email)
        elif action == "decline" and c["status"] != "paused":
            self.notify(c, ads.declined_email)
        return f"Campaign #{c['id']}: {ads.STATES[moves[action][0]].lower()}."

    def ads_page(self, method: str, path: str, query: str, raw: bytes, auth: str,
                 ip: str) -> tuple[int, bytes, dict]:
        """The HTML pages for advertisers and for you. Answers (status, page, extra headers)."""
        form = {k: ",".join(v) if k == "levels" else v[0]  # one checkbox per level
                for k, v in urllib.parse.parse_qs(raw.decode("utf-8", "replace")).items()}
        if (method, path) == ("GET", "/ads"):
            return 200, ads.request_page(self.config.ad_prices), {}
        if (method, path) == ("POST", "/ads/request"):
            return self.book(form, ip)
        if path.startswith("/ads/c/"):
            token, _, action = path[len("/ads/c/"):].partition("/")
            c = self.store.campaign_by_token(token)
            if c and method == "POST" and action == "pay":
                return self.pay(c, form.get("provider", ""))
            if c and method == "POST" and action == "invoice" and self.can_invoice(c):
                self.store.issue_invoice(c["id"], invoice.clean_address(form.get("address", "")))
                return 303, b"", {"Location": f"/ads/c/{c['token']}/invoice.pdf"}
            if c and method == "GET" and action == "invoice.pdf":
                return self.invoice_pdf(c)
            if c and method == "GET" and not action:
                message = ""
                if "paid=1" in query and c["status"] == "unpaid":
                    message = "Thank you! Stripe confirms the payment within seconds. Reload this page to check."
                elif "paid=1" in query and c["status"] == "paid":
                    message = "Payment received. We'll check your ad and email you when it goes live."
                return 200, ads.campaign_page(c, self.ad_payments, message, self.invoice_number(c),
                                              self.can_invoice(c)), {}
        if path == "/ads/admin" and self.config.admin_key:
            if not ads.admin_ok(auth, self.config.admin_key):
                return ADMIN_SIGN_IN
            message = self.admin_action(form) if method == "POST" else ""
            campaigns = self.store.campaigns()
            notes = {c["id"]: self.store.notifications(c["id"]) for c in campaigns}
            numbers = {c["id"]: self.invoice_number(c) for c in campaigns}
            return 200, ads.admin_page(campaigns, ads.csrf_token(self.config.admin_key), notes,
                                       self.mailer.enabled, message,
                                       {k: v for k, v in numbers.items() if v},
                                       self.config.seller.complete), {}
        return 404, ads.page("Not found", "<p>Not found.</p>"), {}

    def admin_pages(self, method: str, path: str, query: str, raw: bytes,
                    auth: str) -> tuple[int, bytes, dict]:
        """The admin dashboard (server/admin.py). Answers (status, page, extra headers)."""
        if not self.config.admin_key:
            return 404, ads.page("Not found", "<p>Set DMG_ADMIN_KEY to open the admin pages.</p>"), {}
        if not ads.admin_ok(auth, self.config.admin_key):
            return ADMIN_SIGN_IN
        args = {k: v[0] for k, v in urllib.parse.parse_qs(query).items()}
        store = self.store
        if path == "/admin":
            return 200, admin.overview(store.stats(), store.signups_since(time.time() - 31 * 86400),
                                       store.purchases(limit=100_000), store.paid_campaigns()), {}
        if path == "/admin/users":
            status = args.get("status", "") if args.get("status") in admin.STATUSES else ""
            offset = int(args["from"]) if args.get("from", "").isdigit() else 0
            users = store.find_users(args.get("q", ""), status, admin.PAGE_SIZE, offset)
            return 200, admin.users_page(users, args.get("q", ""), status, offset), {}
        if path == "/admin/purchases":
            return 200, admin.purchases_page(store.purchases()), {}
        if path == "/admin/purchases.csv":
            day = time.strftime("%Y-%m-%d")
            return 200, admin.purchases_csv(store.purchases(limit=1_000_000)), {
                "Content-Type": "text/csv; charset=utf-8",
                "Content-Disposition": f'attachment; filename="payments-{day}.csv"'}
        m = re.fullmatch(r"/admin/users/(\d+)", path)
        user = store.user(int(m.group(1))) if m else None
        if not user:
            return 404, admin.page("Not found", "<p>No such account.</p>"), {}
        if method == "POST":
            form = {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode("utf-8", "replace")).items()}
            message = self.admin_user_action(user, form)
            return 303, b"", {"Location": f"{path}?{urllib.parse.urlencode({'msg': message})}"}
        uid = user["id"]
        since = time.strftime("%Y-%m-%d", time.localtime(time.time() - 30 * 86400))
        return 200, admin.user_page(
            user, store.sessions(uid), store.purchases(uid), store.admin_log(uid),
            store.usage_seconds(uid, since) / 60, store.usage_seconds(uid) / 60,
            ads.csrf_token(self.config.admin_key), args.get("msg", "")[:200]), {}

    def admin_user_action(self, user, form: dict) -> str:
        if not hmac_equal(form.get("csrf", ""), ads.csrf_token(self.config.admin_key)):
            return "That form has expired. Please reload the page."
        note = form.get("note", "").strip()[:200]
        action = form.get("action", "")
        if action == "add_days":
            days = int(form["days"]) if form.get("days", "").isdigit() else 0
            if not 1 <= days <= 3650:
                return "Enter between 1 and 3650 days."
            self.store.add_days(user["id"], days, note)
            return f"Added {days} days of Premium."
        if action == "end_premium":
            self.store.end_premium(user["id"], note)
            return "Premium ended."
        if action == "refund":
            purchase = int(form["purchase"]) if form.get("purchase", "").isdigit() else 0
            mine = any(p["id"] == purchase for p in self.store.purchases(user["id"]))
            if not mine or not self.store.refund(purchase, note):
                return "That payment was already marked refunded."
            return "Payment marked refunded and its days taken off the plan."
        if action == "sign_out":
            self.store.sign_out_everywhere(user["id"], note)
            return "Signed out on all devices."
        return "Unknown action."

    def handle(self, method: str, path: str, body: dict, token: str, ip: str) -> dict:
        if (method, path) == ("GET", "/health"):
            return {"ok": True}
        if (method, path) == ("GET", "/v1/config"):
            return {"demo_codes": self.otp.demo, "payments": self.payments}
        if (method, path) == ("POST", "/v1/auth/start"):
            return self.auth_start(body, ip)
        if (method, path) == ("POST", "/v1/auth/verify"):
            return self.auth_verify(body)

        routes = {
            ("GET", "/v1/me"): lambda u: self.account(u),
            ("POST", "/v1/auth/signout"): lambda u: self.store.sign_out(token) or {"ok": True},
            ("POST", "/v1/usage"): lambda u: self.usage(u, body),
            ("POST", "/v1/billing/checkout"): lambda u: self.checkout(u, body),
            ("POST", "/v1/billing/google/verify"): lambda u: self.play_verify(u, body),
            ("GET", "/v1/ads/next"): lambda u: self.next_ad(u),
            ("POST", "/v1/ads/next"): lambda u: self.next_ad(u, body),
            ("POST", "/v1/ads/seen"): lambda u: self.ad_seen(u, body),
            ("POST", "/v1/ads/click"): lambda u: self.ad_click(body),
        }
        route = routes.get((method, path))
        if not route:
            raise ApiError(404, "Not found")
        user = self.store.user_for_token(token) if token else None
        if not user:
            raise ApiError(401, "Please sign in again.")
        return route(user)


def hmac_equal(a: str, b: str) -> bool:
    return secrets.compare_digest(a.encode(), b.encode())


def billing_ref(user) -> str:
    """The account id the payment providers see, instead of the phone number."""
    return f"u{user['id']}"


# One realm for /admin and /ads/admin, so the browser asks for the password only once.
ADMIN_SIGN_IN = (401, ads.page("Sign in", "<p>Admin password needed.</p>"),
                 {"WWW-Authenticate": 'Basic realm="Sprach Up admin", charset="UTF-8"'})

PAGES = {  # where Stripe sends the browser after paying
    "/billing/done": ("Payment received", "Thank you! Go back to the app: Premium turns on within a few seconds."),
    "/billing/cancel": ("Payment cancelled", "No money was charged. You can close this page and go back to the app."),
}


def make_handler(server: Server):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _ip(self) -> str:
            forwarded = self.headers.get("X-Forwarded-For", "")
            if server.config.trust_proxy and forwarded:
                return forwarded.split(",")[0].strip()
            return self.client_address[0]

        def _respond(self, status: int, data: dict):
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _page(self, title: str, text: str):
            self._html(200, (
                "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                f"<title>{title}</title><body style='font:18px system-ui;max-width:28em;"
                f"margin:3em auto;padding:0 16px'><h1>{title}</h1><p>{text}</p>"
            ).encode())

        def _html(self, status: int, body: bytes, headers: dict | None = None):
            headers = dict(headers or {})
            kind = headers.pop("Content-Type", "text/html; charset=utf-8")
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if kind.startswith("text/html"):  # a PDF is shown by the browser's own viewer
                self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")
            for k, v in headers.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _run(self, method: str):
            try:
                path, _, query = self.path.partition("?")
                if method == "GET" and path in PAGES:
                    return self._page(*PAGES[path])
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY:
                    raise ApiError(413, "Request too large")
                raw = self.rfile.read(length) if length else b""
                if path == "/ads" or path.startswith("/ads/"):
                    auth = self.headers.get("Authorization", "")
                    return self._html(*server.ads_page(method, path, query, raw, auth, self._ip()))
                if path == "/admin" or path.startswith("/admin/"):
                    auth = self.headers.get("Authorization", "")
                    return self._html(*server.admin_pages(method, path, query, raw, auth))
                if (method, path) == ("POST", "/v1/billing/stripe/webhook"):
                    # Stripe signs the raw bytes, so this one is checked before any JSON parsing.
                    signature = self.headers.get("Stripe-Signature", "")
                    return self._respond(200, server.stripe_webhook(raw, signature))
                try:
                    body = json.loads(raw) if raw else {}
                except ValueError as e:
                    raise ApiError(400, "Invalid JSON") from e
                if not isinstance(body, dict):
                    raise ApiError(400, "Invalid JSON")
                auth = self.headers.get("Authorization", "")
                token = auth[7:] if auth.startswith("Bearer ") else ""
                self._respond(200, server.handle(method, path, body, token, self._ip()))
            except ApiError as e:
                self._respond(e.status, {"error": str(e)})
            except Exception:  # noqa: BLE001  (never leak details to the client)
                self.log_error("unexpected error on %s %s", method, self.path)
                self._respond(500, {"error": "Something went wrong on the server. Try again later."})

        def do_GET(self):
            self._run("GET")

        def do_POST(self):
            self._run("POST")

        def log_message(self, fmt, *args):
            # Request lines only; bodies (phone numbers, codes) are never logged.
            print(f"{self.log_date_time_string()} {fmt % args}")

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8600, config: Config | None = None) -> ThreadingHTTPServer:
    app = Server(config or Config())
    if app.otp.demo:
        print("WARNING: TWILIO_* not set, so sign-in codes are returned to the app (demo mode).")
    print(f"Payments: {', '.join(app.payments) or 'none (Get Premium says coming soon)'}")
    if not app.config.admin_key:
        print("Admin: set DMG_ADMIN_KEY to open /admin (users, Premium, revenue) and /ads/admin.")
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    httpd.app = app
    return httpd
