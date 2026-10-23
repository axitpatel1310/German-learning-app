"""The accounts server: sign-in with WhatsApp codes, one account per phone number, the
Premium plan and time stats that follow you across devices.

Standard library only. Run with `python -m server` (see server/README.md for the settings).
"""

import json
import os
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.otp import (
    CODE_LENGTH,
    RESEND_AFTER,
    OtpError,
    normalize_phone,
    otp_provider,
)
from server.db import Store

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

    @property
    def payments(self) -> list[str]:
        return ["test"] if self.test_payments else []


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class Server:
    def __init__(self, config: Config, otp=None):
        self.config = config
        self.store = Store(config.db_path, config.max_sessions)
        self.otp = otp or otp_provider()
        self.otp_lock = threading.Lock()
        if config.production and self.otp.demo:
            raise SystemExit("DMG_ENV=production needs the TWILIO_* settings: demo codes are off.")

    def account(self, user) -> dict:
        return {
            "phone": user["phone"],
            "created_at": user["created_at"],
            "premium_until": user["premium_until"],
            "payments": self.config.payments,
        }

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

    def checkout(self, user) -> dict:
        if not self.config.test_payments:
            raise ApiError(503, "Payments are not connected yet. Please try again later.")
        self.store.grant(user["id"], "test", "test-" + secrets.token_hex(8), PLAN_DAYS, "€10 (test)")
        return {"account": self.account(self.store.user(user["id"]))}

    def handle(self, method: str, path: str, body: dict, token: str, ip: str) -> dict:
        if (method, path) == ("GET", "/health"):
            return {"ok": True}
        if (method, path) == ("GET", "/v1/config"):
            return {"demo_codes": self.otp.demo, "payments": self.config.payments}
        if (method, path) == ("POST", "/v1/auth/start"):
            return self.auth_start(body, ip)
        if (method, path) == ("POST", "/v1/auth/verify"):
            return self.auth_verify(body)

        routes = {
            ("GET", "/v1/me"): lambda u: self.account(u),
            ("POST", "/v1/auth/signout"): lambda u: self.store.sign_out(token) or {"ok": True},
            ("POST", "/v1/usage"): lambda u: self.usage(u, body),
            ("POST", "/v1/billing/checkout"): self.checkout,
        }
        route = routes.get((method, path))
        if not route:
            raise ApiError(404, "Not found")
        user = self.store.user_for_token(token) if token else None
        if not user:
            raise ApiError(401, "Please sign in again.")
        return route(user)


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

        def _run(self, method: str):
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY:
                    raise ApiError(413, "Request too large")
                raw = self.rfile.read(length) if length else b""
                try:
                    body = json.loads(raw) if raw else {}
                except ValueError as e:
                    raise ApiError(400, "Invalid JSON") from e
                if not isinstance(body, dict):
                    raise ApiError(400, "Invalid JSON")
                auth = self.headers.get("Authorization", "")
                token = auth[7:] if auth.startswith("Bearer ") else ""
                path = self.path.split("?", 1)[0]
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
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    httpd.app = app
    return httpd
