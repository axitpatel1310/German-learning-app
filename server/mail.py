"""Emails to advertisers ("your ad is live", "your ad run is complete") over SMTP.

Without DMG_SMTP_HOST nothing is sent: the message stays in the notifications table and is
shown on the admin page, so it can be forwarded by hand.
"""

import os
import smtplib
import threading
from email.message import EmailMessage


class Mailer:
    def __init__(self, env=os.environ):
        self.host = env.get("DMG_SMTP_HOST", "")
        self.port = int(env.get("DMG_SMTP_PORT", "587"))
        self.user = env.get("DMG_SMTP_USER", "")
        self.password = env.get("DMG_SMTP_PASSWORD", "")
        self.sender = env.get("DMG_MAIL_FROM", self.user)

    @property
    def enabled(self) -> bool:
        return bool(self.host and self.sender)

    def send(self, to: str, subject: str, body: str) -> bool:
        if not self.enabled:
            return False
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender, to, subject
        msg.set_content(body)
        try:
            with smtplib.SMTP(self.host, self.port, timeout=20) as smtp:
                smtp.starttls()
                if self.user:
                    smtp.login(self.user, self.password)
                smtp.send_message(msg)
        except (OSError, smtplib.SMTPException) as e:
            print(f"email to advertiser failed: {e.__class__.__name__}")
            return False
        return True

    def send_later(self, to: str, subject: str, body: str, done=lambda ok: None):
        """Sends in the background, so a slow mail server never holds up the app."""
        threading.Thread(target=lambda: done(self.send(to, subject, body)), daemon=True).start()
