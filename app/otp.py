"""Phone numbers and one-time sign-in codes (demo, or Twilio Verify on WhatsApp).

Shared by the app (local mode) and the server, so it only uses the standard library.
"""

import base64
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

CODE_LENGTH = 6
CODE_TTL = 10 * 60
MAX_ATTEMPTS = 5
RESEND_AFTER = 30

PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_phone(text: str) -> str | None:
    """'+49 151 2345-6789' or '0049…' -> '+4915123456789' (E.164), or None if invalid."""
    phone = re.sub(r"[\s\-()/.]", "", text or "")
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    return phone if PHONE_RE.match(phone) else None


def mask_phone(phone: str) -> str:
    return phone[:4] + " ••• " + phone[-3:] if len(phone) > 8 else phone


class OtpError(Exception):
    pass


class DemoOtp:
    """Used when no WhatsApp service is set up: the code is shown in the app instead."""

    demo = True

    def __init__(self):
        self._codes: dict[str, dict] = {}

    def send(self, phone: str) -> str:
        code = "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))
        self._codes[phone] = {"code": code, "expires": time.time() + CODE_TTL, "attempts": 0}
        print(f"[demo sign-in] code for {phone}: {code}")
        return code

    def check(self, phone: str, code: str) -> bool:
        pending = self._codes.get(phone)
        if not pending or time.time() > pending["expires"]:
            raise OtpError("The code has expired. Ask for a new one.")
        pending["attempts"] += 1
        if pending["attempts"] > MAX_ATTEMPTS:
            raise OtpError("Too many wrong codes. Ask for a new one.")
        if secrets.compare_digest(pending["code"], code):
            del self._codes[phone]
            return True
        return False


class TwilioWhatsAppOtp:
    """Twilio Verify with the WhatsApp channel. Twilio creates, sends and checks the code."""

    demo = False
    API = "https://verify.twilio.com/v2/Services/{sid}/{path}"

    def __init__(self, account_sid: str, auth_token: str, service_sid: str):
        self.service_sid = service_sid
        token = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
        self.auth = f"Basic {token}"

    def _post(self, path: str, fields: dict) -> dict:
        req = urllib.request.Request(
            self.API.format(sid=self.service_sid, path=path),
            data=urllib.parse.urlencode(fields).encode(),
            headers={"Authorization": self.auth},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 404 and path == "VerificationCheck":
                raise OtpError("The code has expired. Ask for a new one.") from e
            if e.code == 429:
                raise OtpError("Too many attempts. Please wait a few minutes.") from e
            raise OtpError("WhatsApp could not send the code. Check the number.") from e
        except OSError as e:
            raise OtpError("No connection. Check your internet and try again.") from e

    def send(self, phone: str) -> None:
        self._post("Verifications", {"To": phone, "Channel": "whatsapp"})

    def check(self, phone: str, code: str) -> bool:
        return self._post("VerificationCheck", {"To": phone, "Code": code}).get("status") == "approved"


def otp_provider():
    sid, token, service = (
        os.environ.get(k, "") for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_VERIFY_SID")
    )
    return TwilioWhatsAppOtp(sid, token, service) if sid and token and service else DemoOtp()
