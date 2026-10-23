"""SQLite storage for the accounts server: users, sessions, purchases, time stats and ad
campaigns."""

import hashlib
import secrets
import sqlite3
import threading
import time

SESSION_TTL = 180 * 86400  # a device stays signed in for 6 months after its last visit

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    phone TEXT NOT NULL UNIQUE,
    created_at REAL NOT NULL,
    premium_until REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at REAL NOT NULL,
    last_seen REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    provider TEXT NOT NULL,
    ref TEXT NOT NULL UNIQUE,
    days INTEGER NOT NULL,
    amount TEXT NOT NULL DEFAULT '',
    at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS usage (
    user_id INTEGER NOT NULL REFERENCES users(id),
    device TEXT NOT NULL,
    day TEXT NOT NULL,
    seconds REAL NOT NULL,
    PRIMARY KEY (user_id, device, day)
);
CREATE TABLE IF NOT EXISTS code_sends (
    key TEXT NOT NULL,
    at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS code_sends_key ON code_sends (key, at);
CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY,
    token TEXT NOT NULL UNIQUE,
    business TEXT NOT NULL,
    email TEXT NOT NULL,
    headline TEXT NOT NULL,
    body TEXT NOT NULL,
    link TEXT NOT NULL,
    views_target INTEGER NOT NULL,
    price_cents INTEGER NOT NULL,
    views INTEGER NOT NULL DEFAULT 0,
    clicks INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'unpaid',
    payment_ref TEXT UNIQUE,
    created_at REAL NOT NULL,
    paid_at REAL,
    started_at REAL,
    completed_at REAL
);
CREATE TABLE IF NOT EXISTS ad_views (
    campaign_id INTEGER NOT NULL REFERENCES campaigns(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    at REAL NOT NULL,
    PRIMARY KEY (campaign_id, user_id)
);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY,
    campaign_id INTEGER NOT NULL REFERENCES campaigns(id),
    email TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    at REAL NOT NULL,
    sent INTEGER NOT NULL DEFAULT 0
);
"""

VIEW_GAP = 30 * 60  # the same person counts as a new view of an ad after 30 minutes


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Store:
    """One connection shared by the request threads, guarded by a lock."""

    def __init__(self, path: str, max_sessions: int = 3):
        self.max_sessions = max_sessions
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)

    def _one(self, sql: str, *args) -> sqlite3.Row | None:
        return self.conn.execute(sql, args).fetchone()

    # users and sessions

    def user(self, user_id: int) -> sqlite3.Row:
        with self.lock:
            return self._one("SELECT * FROM users WHERE id = ?", user_id)

    def sign_in(self, phone: str) -> tuple[sqlite3.Row, str]:
        """The user for this number (created on first sign-in) and a new session token.
        Only the newest max_sessions devices stay signed in."""
        token = secrets.token_urlsafe(32)
        now = time.time()
        with self.lock:
            self.conn.execute("INSERT OR IGNORE INTO users (phone, created_at) VALUES (?, ?)", (phone, now))
            user = self._one("SELECT * FROM users WHERE phone = ?", phone)
            self.conn.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?)", (_hash(token), user["id"], now, now)
            )
            self.conn.execute(
                "DELETE FROM sessions WHERE user_id = ? AND token_hash NOT IN "
                "(SELECT token_hash FROM sessions WHERE user_id = ? ORDER BY last_seen DESC LIMIT ?)",
                (user["id"], user["id"], self.max_sessions),
            )
        return user, token

    def user_for_token(self, token: str) -> sqlite3.Row | None:
        now = time.time()
        with self.lock:
            row = self._one(
                "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token_hash = ? AND s.last_seen > ?",
                _hash(token), now - SESSION_TTL,
            )
            if row:
                self.conn.execute("UPDATE sessions SET last_seen = ? WHERE token_hash = ?", (now, _hash(token)))
        return row

    def sign_out(self, token: str):
        with self.lock:
            self.conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash(token),))

    # purchases

    def grant(self, user_id: int, provider: str, ref: str, days: int, amount: str = "") -> bool:
        """Adds days of Premium, from now or from the end of the current period.
        Each payment reference counts once, so repeated webhooks are harmless."""
        now = time.time()
        with self.lock:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO purchases (user_id, provider, ref, days, amount, at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, provider, ref, days, amount, now),
            )
            if not cur.rowcount:
                return False
            self.conn.execute(
                "UPDATE users SET premium_until = MAX(premium_until, ?) + ? WHERE id = ?",
                (now, days * 86400, user_id),
            )
        return True

    # time stats

    def save_usage(self, user_id: int, device: str, days: dict[str, float]):
        # A device always sends its own running totals, so keeping the larger value makes
        # repeated or out-of-order uploads safe.
        with self.lock:
            self.conn.executemany(
                "INSERT INTO usage VALUES (?, ?, ?, ?) ON CONFLICT (user_id, device, day) "
                "DO UPDATE SET seconds = MAX(seconds, excluded.seconds)",
                [(user_id, device, day, sec) for day, sec in days.items()],
            )

    def other_usage(self, user_id: int, device: str) -> dict[str, float]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT day, SUM(seconds) AS s FROM usage WHERE user_id = ? AND device != ? GROUP BY day",
                (user_id, device),
            ).fetchall()
        return {r["day"]: r["s"] for r in rows}

    # rate limits for sending codes

    def sends_since(self, key: str, since: float) -> int:
        with self.lock:
            return self._one("SELECT COUNT(*) FROM code_sends WHERE key = ? AND at > ?", key, since)[0]

    def log_send(self, *keys: str):
        now = time.time()
        with self.lock:
            self.conn.executemany("INSERT INTO code_sends VALUES (?, ?)", [(k, now) for k in keys])
            self.conn.execute("DELETE FROM code_sends WHERE at < ?", (now - 86400,))

    # ad campaigns: unpaid -> paid (waiting for your review) -> active -> completed,
    # or paused / declined on the way

    def add_campaign(self, business: str, email: str, headline: str, body: str, link: str,
                     views_target: int, price_cents: int) -> sqlite3.Row:
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO campaigns (token, business, email, headline, body, link, views_target, "
                "price_cents, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (secrets.token_urlsafe(18), business, email, headline, body, link, views_target,
                 price_cents, time.time()),
            )
            return self._one("SELECT * FROM campaigns WHERE id = ?", cur.lastrowid)

    def mark_paid(self, campaign_id: int, ref: str) -> bool:
        """Unpaid -> paid. Each payment reference counts once, so repeated webhooks are harmless."""
        with self.lock:
            try:
                cur = self.conn.execute(
                    "UPDATE campaigns SET status = 'paid', payment_ref = ?, paid_at = ? "
                    "WHERE id = ? AND status = 'unpaid'",
                    (ref, time.time(), campaign_id),
                )
            except sqlite3.IntegrityError:  # this payment was already used for another campaign
                return False
        return bool(cur.rowcount)

    def campaign(self, campaign_id: int) -> sqlite3.Row | None:
        with self.lock:
            return self._one("SELECT * FROM campaigns WHERE id = ?", campaign_id)

    def campaign_by_token(self, token: str) -> sqlite3.Row | None:
        with self.lock:
            return self._one("SELECT * FROM campaigns WHERE token = ?", token)

    def campaigns(self) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute("SELECT * FROM campaigns ORDER BY id DESC LIMIT 200").fetchall()

    def set_status(self, campaign_id: int, status: str, was: tuple[str, ...]) -> bool:
        with self.lock:
            cur = self.conn.execute(
                f"UPDATE campaigns SET status = ?, started_at = COALESCE(started_at, "
                f"CASE WHEN ? = 'active' THEN ? END) WHERE id = ? AND status IN ({', '.join('?' * len(was))})",
                (status, status, time.time(), campaign_id, *was),
            )
        return bool(cur.rowcount)

    def next_ad(self, user_id: int) -> sqlite3.Row | None:
        """A running ad for this person: one they haven't seen lately first, then the one
        furthest behind its target, so all campaigns move forward at a similar pace."""
        with self.lock:
            return self._one(
                "SELECT c.* FROM campaigns c "
                "LEFT JOIN ad_views v ON v.campaign_id = c.id AND v.user_id = ? "
                "WHERE c.status = 'active' "
                "ORDER BY COALESCE(v.at, 0) > ?, CAST(c.views AS REAL) / c.views_target, RANDOM() LIMIT 1",
                user_id, time.time() - VIEW_GAP,
            )

    def count_view(self, campaign_id: int, user_id: int) -> str:
        """Counts a view, at most one per person per ad every 30 minutes. Answers "counted",
        "completed" (this view reached the target, so the ad stops) or "" (not counted)."""
        now = time.time()
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                c = self._one("SELECT * FROM campaigns WHERE id = ? AND status = 'active'", campaign_id)
                seen = self._one(
                    "SELECT at FROM ad_views WHERE campaign_id = ? AND user_id = ?", campaign_id, user_id
                )
                if not c or (seen and seen["at"] > now - VIEW_GAP):
                    self.conn.execute("COMMIT")
                    return ""
                self.conn.execute(
                    "INSERT INTO ad_views VALUES (?, ?, ?) ON CONFLICT (campaign_id, user_id) "
                    "DO UPDATE SET at = excluded.at",
                    (campaign_id, user_id, now),
                )
                done = c["views"] + 1 >= c["views_target"]
                self.conn.execute(
                    "UPDATE campaigns SET views = views + 1, status = ?, completed_at = ? WHERE id = ?",
                    ("completed" if done else "active", now if done else None, campaign_id),
                )
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
        return "completed" if done else "counted"

    def count_click(self, campaign_id: int):
        with self.lock:
            self.conn.execute(
                "UPDATE campaigns SET clicks = clicks + 1 WHERE id = ? AND status IN ('active', 'completed')",
                (campaign_id,),
            )

    # emails to advertisers (kept even when no mail server is set, so nothing is lost)

    def add_notification(self, campaign_id: int, email: str, subject: str, body: str) -> int:
        with self.lock:
            return self.conn.execute(
                "INSERT INTO notifications (campaign_id, email, subject, body, at) VALUES (?, ?, ?, ?, ?)",
                (campaign_id, email, subject, body, time.time()),
            ).lastrowid

    def notification_sent(self, notification_id: int):
        with self.lock:
            self.conn.execute("UPDATE notifications SET sent = 1 WHERE id = ?", (notification_id,))

    def notifications(self, campaign_id: int) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(
                "SELECT * FROM notifications WHERE campaign_id = ? ORDER BY id", (campaign_id,)
            ).fetchall()
