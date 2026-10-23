"""Sign-in by phone number (code sent on WhatsApp), the Premium plan and time spent in the app.

Two kinds of account:
- Account: everything on this device (demo or Twilio codes, test purchases). Used when no
  server is configured.
- ServerAccount: the accounts server (server/) sends and checks the codes, keeps one account
  per number, confirms payments and keeps the time stats across devices. Used when DMG_API_URL
  is set.
"""

import json
import re
import secrets
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from app.api import Api, ApiError, api_url
from app.otp import (  # noqa: F401  (re-exported for the views)
    CODE_LENGTH,
    RESEND_AFTER,
    OtpError,
    mask_phone,
    normalize_phone,
    otp_provider,
)
from app.storage import user_data_dir

PLAN_PRICE = "€10"
PLAN_DAYS = 90
PLAN_LABEL = f"{PLAN_PRICE} for 3 months"
FREE_STORIES = 10  # per level; the rest need Premium


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}


def _save(path: Path, data: dict):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


# --- the account on this device ---


class Account:
    """The signed-in phone number and its plan, in account.json."""

    server = False
    payments = ["test"]

    def __init__(self, path: Path | None = None, otp=None):
        self.path = path or user_data_dir() / "account.json"
        self.otp = otp or otp_provider()
        self.data = _load(self.path)
        self.pending_phone = ""
        self.sent_at = 0.0

    @property
    def phone(self) -> str:
        return self.data.get("phone", "")

    @property
    def signed_in(self) -> bool:
        return bool(self.phone)

    # sign-in

    def send_code(self, phone: str) -> str | None:
        """Sends a code to phone. Returns the code itself only in demo mode."""
        wait = self.resend_in(phone)
        if wait:
            raise OtpError(f"Please wait {wait} s before asking for another code.")
        code = self.otp.send(phone)
        self.pending_phone, self.sent_at = phone, time.time()
        return code

    def resend_in(self, phone: str) -> int:
        if phone != self.pending_phone:
            return 0
        return max(0, int(self.sent_at + RESEND_AFTER - time.time()))

    def verify(self, code: str) -> bool:
        code = re.sub(r"\D", "", code or "")
        if len(code) != CODE_LENGTH or not self.pending_phone:
            return False
        if not self.otp.check(self.pending_phone, code):
            return False
        phone = self.pending_phone
        # A different number on this device starts a fresh account.
        if phone != self.data.get("phone_last"):
            self.data = {"created_at": time.time()}
        self.data.update(phone=phone, phone_last=phone, signed_in_at=time.time())
        self.pending_phone = ""
        _save(self.path, self.data)
        return True

    def sign_out(self):
        self.data.pop("phone", None)
        _save(self.path, self.data)

    def refresh(self) -> bool:
        return True

    def sync_usage(self, usage: "Usage"):
        pass

    # plan

    @property
    def premium_until(self) -> datetime | None:
        ts = self.data.get("premium_until")
        return datetime.fromtimestamp(ts) if ts else None

    @property
    def premium(self) -> bool:
        return self.signed_in and self.data.get("premium_until", 0) > time.time()

    def days_left(self) -> int:
        return max(0, int((self.data.get("premium_until", 0) - time.time()) // 86400) + 1) if self.premium else 0

    def buy(self):
        """The test purchase: no money is charged."""
        self.activate_premium()

    def activate_premium(self):
        """Adds 3 months, from today or from the end of the current period."""
        start = max(time.time(), self.data.get("premium_until", 0))
        self.data["premium_until"] = start + PLAN_DAYS * 86400
        self.data.setdefault("purchases", []).append(
            {"at": time.time(), "price": PLAN_PRICE, "days": PLAN_DAYS, "test": True}
        )
        _save(self.path, self.data)

    def locked(self, lib, story) -> bool:
        """The first FREE_STORIES of each level are free; the rest need Premium."""
        return not self.premium and lib.stories[story.level].index(story) >= FREE_STORIES


class ServerAccount(Account):
    """An account on the accounts server. account.json only keeps the session token and the
    last plan the server reported, so the app also opens offline."""

    server = True

    def __init__(self, base_url: str, path: Path | None = None):
        self.path = path or user_data_dir() / "account.json"
        self.data = _load(self.path)
        if self.data.get("server") != base_url:  # a local account or another server
            self.data = {"server": base_url}
        self.api = Api(base_url, self.data.get("token", ""))
        self.pending_phone = ""
        self.sent_at = 0.0

    @property
    def signed_in(self) -> bool:
        return bool(self.data.get("token"))

    @property
    def payments(self) -> list[str]:
        return self.data.get("payments", [])

    def send_code(self, phone: str) -> str | None:
        wait = self.resend_in(phone)
        if wait:
            raise OtpError(f"Please wait {wait} s before asking for another code.")
        try:
            res = self.api.post("/v1/auth/start", {"phone": phone})
        except ApiError as e:
            raise OtpError(str(e)) from e
        self.pending_phone, self.sent_at = phone, time.time()
        return res.get("demo_code")

    def verify(self, code: str) -> bool:
        code = re.sub(r"\D", "", code or "")
        if len(code) != CODE_LENGTH or not self.pending_phone:
            return False
        try:
            res = self.api.post("/v1/auth/verify", {"phone": self.pending_phone, "code": code})
        except ApiError as e:
            if e.status == 401:
                return False
            raise OtpError(str(e)) from e
        self.api.token = res["token"]
        self.data = {"server": self.api.base_url, "token": res["token"]}
        self._apply(res["account"])
        self.pending_phone = ""
        return True

    def refresh(self) -> bool:
        """Fetches the plan from the server. False when offline or signed out remotely."""
        if not self.signed_in:
            return False
        try:
            self._apply(self.api.get("/v1/me"))
        except ApiError as e:
            if e.status == 401:
                self._forget()
            return False
        return True

    def sign_out(self):
        try:
            self.api.post("/v1/auth/signout")
        except ApiError:
            pass  # the token expires on the server anyway
        self._forget()

    def buy(self):
        """The server's test purchase (only when the server allows it)."""
        try:
            res = self.api.post("/v1/billing/checkout")
        except ApiError as e:
            raise OtpError(str(e)) from e
        self._apply(res["account"])

    def sync_usage(self, usage: "Usage"):
        """Uploads this device's minutes and gets the other devices' minutes back."""
        if not self.signed_in:
            return
        try:
            res = self.api.post("/v1/usage", {"device": usage.device, "days": usage.days})
        except ApiError as e:
            if e.status == 401:
                self._forget()
            return
        usage.set_others(res.get("others", {}))

    def _apply(self, info: dict):
        self.data.update(
            phone=info["phone"],
            created_at=info.get("created_at"),
            premium_until=info.get("premium_until") or 0,
            payments=info.get("payments", []),
        )
        _save(self.path, self.data)

    def _forget(self):
        self.api.token = ""
        self.data = {"server": self.api.base_url}
        _save(self.path, self.data)


def make_account() -> Account:
    url = api_url()
    return ServerAccount(url) if url else Account()


# --- time spent in the app ---


class Usage:
    """Seconds of active use per day, in usage.json. With a server account, `others` holds the
    minutes from the account's other devices, so the stats follow you to a new phone."""

    TICK = 15
    MAX_GAP = 2 * TICK  # a longer gap means the computer slept: don't count it

    def __init__(self, path: Path | None = None):
        self.path = path or user_data_dir() / "usage.json"
        data = _load(self.path)
        self.days: dict[str, float] = data.get("days", {})
        self.others: dict[str, float] = data.get("others", {})
        self.owner: str = data.get("owner", "")
        self.device: str = data.get("device") or secrets.token_hex(8)
        self.sessions = data.get("sessions", 0) + 1
        self._last = time.monotonic()
        self._save()

    def claim(self, phone: str):
        """Minutes belong to one phone number: another number on this device starts from zero."""
        if phone and phone != self.owner:
            if self.owner:
                self.days, self.others, self.sessions = {}, {}, 1
            self.owner = phone
            self._save()

    def set_others(self, others: dict):
        self.others = {k: float(v) for k, v in others.items()}
        self._save()

    def tick(self, active: bool):
        now = time.monotonic()
        gap, self._last = now - self._last, now
        if active and gap <= self.MAX_GAP:
            key = date.today().isoformat()
            self.days[key] = self.days.get(key, 0) + gap
            self._save()

    def seconds(self, day: date) -> float:
        key = day.isoformat()
        return self.days.get(key, 0) + self.others.get(key, 0)

    def last_days(self, n: int = 7) -> list[tuple[date, float]]:
        today = date.today()
        return [(d, self.seconds(d)) for d in (today - timedelta(days=i) for i in range(n - 1, -1, -1))]

    def total(self) -> float:
        return sum(self.days.values()) + sum(self.others.values())

    def streak(self) -> int:
        """Days in a row with at least a minute of use, ending today or yesterday."""
        day, n = date.today(), 0
        if self.seconds(day) < 60:
            day -= timedelta(days=1)
        while self.seconds(day) >= 60:
            n += 1
            day -= timedelta(days=1)
        return n

    def _save(self):
        _save(self.path, {"days": self.days, "others": self.others, "owner": self.owner,
                          "device": self.device, "sessions": self.sessions})


def fmt_duration(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60:02d} min"
