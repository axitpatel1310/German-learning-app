"""SQLite storage for the accounts server: users, sessions, purchases and time stats."""

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
"""


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
