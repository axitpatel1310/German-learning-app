"""SQLite storage for the accounts server: users, sessions, purchases, time stats, ad
campaigns and the admin history."""

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
    levels TEXT NOT NULL DEFAULT '',
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
CREATE TABLE IF NOT EXISTS admin_log (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    action TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS invoices (
    number INTEGER PRIMARY KEY,
    campaign_id INTEGER NOT NULL UNIQUE REFERENCES campaigns(id),
    address TEXT NOT NULL,
    issued_at REAL NOT NULL
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
        columns = {r["name"] for r in self.conn.execute("PRAGMA table_info(campaigns)")}
        if "levels" not in columns:  # databases from before level targeting
            self.conn.execute("ALTER TABLE campaigns ADD COLUMN levels TEXT NOT NULL DEFAULT ''")
        columns = {r["name"] for r in self.conn.execute("PRAGMA table_info(purchases)")}
        if "refunded_at" not in columns:  # databases from before the admin dashboard
            self.conn.execute("ALTER TABLE purchases ADD COLUMN refunded_at REAL")

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
                     views_target: int, price_cents: int, levels: str = "") -> sqlite3.Row:
        """levels: comma-separated CEFR levels the ad is shown to, or "" for every learner."""
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO campaigns (token, business, email, headline, body, link, levels, "
                "views_target, price_cents, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (secrets.token_urlsafe(18), business, email, headline, body, link, levels,
                 views_target, price_cents, time.time()),
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

    def next_ad(self, user_id: int, level: str = "") -> sqlite3.Row | None:
        """A running ad for this person: one they haven't seen lately first, then the one
        furthest behind its target, so all campaigns move forward at a similar pace.
        Ads aimed at some levels only go to learners reading at one of them; when the
        level isn't known, only ads for every learner qualify."""
        with self.lock:
            return self._one(
                "SELECT c.* FROM campaigns c "
                "LEFT JOIN ad_views v ON v.campaign_id = c.id AND v.user_id = ? "
                "WHERE c.status = 'active' AND (c.levels = '' OR "
                "(? != '' AND instr(',' || c.levels || ',', ',' || ? || ',') > 0)) "
                "ORDER BY COALESCE(v.at, 0) > ?, CAST(c.views AS REAL) / c.views_target, RANDOM() LIMIT 1",
                user_id, level, level, time.time() - VIEW_GAP,
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

    # invoices: numbered in order, one per campaign, never changed once issued

    def issue_invoice(self, campaign_id: int, address: str) -> sqlite3.Row:
        with self.lock:
            self.conn.execute(
                "INSERT OR IGNORE INTO invoices (campaign_id, address, issued_at) VALUES (?, ?, ?)",
                (campaign_id, address, time.time()),
            )
            return self._one("SELECT * FROM invoices WHERE campaign_id = ?", campaign_id)

    def invoice(self, campaign_id: int) -> sqlite3.Row | None:
        with self.lock:
            return self._one("SELECT * FROM invoices WHERE campaign_id = ?", campaign_id)

    # admin dashboard: look up accounts, change Premium by hand, keep a history of every change

    def stats(self) -> dict:
        now = time.time()

        def one(sql: str, *args):
            return self._one(sql, *args)[0]

        with self.lock:
            return {
                "users": one("SELECT COUNT(*) FROM users"),
                "new_7d": one("SELECT COUNT(*) FROM users WHERE created_at > ?", now - 7 * 86400),
                "premium": one("SELECT COUNT(*) FROM users WHERE premium_until > ?", now),
                "expiring_7d": one("SELECT COUNT(*) FROM users WHERE premium_until BETWEEN ? AND ?",
                                   now, now + 7 * 86400),
                "active_7d": one("SELECT COUNT(DISTINCT user_id) FROM sessions WHERE last_seen > ?",
                                 now - 7 * 86400),
            }

    def signups_since(self, since: float) -> list[float]:
        with self.lock:
            return [r[0] for r in self.conn.execute(
                "SELECT created_at FROM users WHERE created_at > ?", (since,))]

    def find_users(self, query: str = "", status: str = "", limit: int = 50,
                   offset: int = 0) -> list[sqlite3.Row]:
        """query: part of a phone number, or an account id like u12. status: premium, expired
        (had Premium, not any more) or free (never had it)."""
        now = time.time()
        where, args = [], []
        q = query.strip().lower().lstrip("#")
        if q.startswith("u") and q[1:].isdigit():
            where.append("u.id = ?")
            args.append(int(q[1:]))
        elif q:
            digits = "".join(ch for ch in q if ch.isdigit())
            where.append("u.phone LIKE ?")
            args.append(f"%{digits or q}%")
        if status == "premium":
            where.append("u.premium_until > ?")
            args.append(now)
        elif status == "expired":
            where.append("u.premium_until BETWEEN 1 AND ?")
            args.append(now)
        elif status == "free":
            where.append("u.premium_until = 0")
        sql = (
            "SELECT u.*, (SELECT COUNT(*) FROM sessions s WHERE s.user_id = u.id) AS devices, "
            "(SELECT MAX(last_seen) FROM sessions s WHERE s.user_id = u.id) AS last_seen, "
            "(SELECT COUNT(*) FROM purchases p WHERE p.user_id = u.id AND p.provider NOT IN "
            "('manual', 'test') AND p.refunded_at IS NULL) AS paid "
            "FROM users u" + (" WHERE " + " AND ".join(where) if where else "")
            + " ORDER BY u.id DESC LIMIT ? OFFSET ?"
        )
        with self.lock:
            return self.conn.execute(sql, (*args, limit, offset)).fetchall()

    def sessions(self, user_id: int) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(
                "SELECT created_at, last_seen FROM sessions WHERE user_id = ? ORDER BY last_seen DESC",
                (user_id,),
            ).fetchall()

    def purchases(self, user_id: int | None = None, limit: int = 500) -> list[sqlite3.Row]:
        """Newest first, with the buyer's phone number."""
        sql = "SELECT p.*, u.phone FROM purchases p JOIN users u ON u.id = p.user_id"
        args: tuple = ()
        if user_id is not None:
            sql += " WHERE p.user_id = ?"
            args = (user_id,)
        with self.lock:
            return self.conn.execute(sql + " ORDER BY p.at DESC LIMIT ?", (*args, limit)).fetchall()

    def usage_seconds(self, user_id: int, since_day: str = "") -> float:
        with self.lock:
            return self._one(
                "SELECT COALESCE(SUM(seconds), 0) FROM usage WHERE user_id = ? AND day >= ?",
                user_id, since_day,
            )[0]

    def admin_log(self, user_id: int) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(
                "SELECT * FROM admin_log WHERE user_id = ? ORDER BY id DESC", (user_id,)
            ).fetchall()

    def _log(self, user_id: int, action: str, note: str):
        self.conn.execute(
            "INSERT INTO admin_log (user_id, action, note, at) VALUES (?, ?, ?, ?)",
            (user_id, action, note, time.time()),
        )

    def add_days(self, user_id: int, days: int, note: str = ""):
        """Premium given by hand (a tester, a support case). Listed as a 'manual' purchase."""
        self.grant(user_id, "manual", "manual-" + secrets.token_hex(8), days)
        with self.lock:
            self._log(user_id, f"Added {days} days of Premium", note)

    def end_premium(self, user_id: int, note: str = ""):
        with self.lock:
            self.conn.execute(
                "UPDATE users SET premium_until = MIN(premium_until, ?) WHERE id = ?", (time.time(), user_id)
            )
            self._log(user_id, "Ended Premium", note)

    def refund(self, purchase_id: int, note: str = "") -> bool:
        """Marks a purchase refunded and takes its days back off the plan. Only once per purchase."""
        now = time.time()
        with self.lock:
            p = self._one("SELECT * FROM purchases WHERE id = ? AND refunded_at IS NULL", purchase_id)
            if not p:
                return False
            self.conn.execute("UPDATE purchases SET refunded_at = ? WHERE id = ?", (now, purchase_id))
            # Take the days off, but never move the end before now (it's then simply over).
            self.conn.execute(
                "UPDATE users SET premium_until = MAX(MIN(premium_until, ?), premium_until - ?) WHERE id = ?",
                (now, p["days"] * 86400, p["user_id"]),
            )
            self._log(p["user_id"], f"Marked {p['provider']} payment {p['ref']} refunded "
                                    f"({p['days']} days removed)", note)
        return True

    def sign_out_everywhere(self, user_id: int, note: str = ""):
        with self.lock:
            self.conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            self._log(user_id, "Signed out on all devices", note)

    def paid_campaigns(self) -> list[sqlite3.Row]:
        """Ad bookings that brought in money (ads started on an invoice count too)."""
        with self.lock:
            return self.conn.execute(
                "SELECT price_cents, COALESCE(paid_at, started_at) AS at FROM campaigns "
                "WHERE status IN ('paid', 'active', 'paused', 'completed')"
            ).fetchall()
