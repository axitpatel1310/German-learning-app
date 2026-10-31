"""The admin dashboard: accounts, Premium and money, behind the same password as /ads/admin.

- /admin                 Overview: users, Premium, active learners, sign-ups and revenue.
- /admin/users           Find an account by phone number or id (u12); filter by plan.
- /admin/users/<id>      One account: plan, payments, devices, learning time, admin history.
                         Add days, end Premium, mark a payment refunded, sign out everywhere.
- /admin/purchases       Every payment, with a CSV export (/admin/purchases.csv).

Every change made here is written to the account's admin history with your note.
"""

import csv
import io
import re
import time
import urllib.parse

from server.ads import STYLE, e, euros

EXTRA_STYLE = (
    "body{max-width:64em}nav{display:flex;gap:1.2em;flex-wrap:wrap;margin-bottom:1em}"
    "nav a{text-decoration:none;font-weight:600}nav a.on{text-decoration:underline}"
    ".cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(11em,1fr));gap:.8em}"
    ".card{border:1px solid #ccc;border-radius:14px;padding:.8em 1em}"
    ".card b{display:block;font-size:1.7em}.chart{display:flex;align-items:flex-end;gap:2px;"
    "height:110px;border-bottom:1px solid #ccc}.chart i{flex:1;background:#3f51b5;min-height:1px}"
    ".wrap{overflow-x:auto}th{text-align:left;font-size:.85em;color:#666;padding:.3em}"
    ".pill{font-size:.8em;padding:.1em .6em;border-radius:10px;background:#e8eaf6;color:#283593}"
    ".pill.off{background:#eee;color:#555}.pill.bad{background:#fde7e9;color:#b3261e}"
    "form.row{display:flex;gap:.5em;flex-wrap:wrap;align-items:center;margin:.4em 0}"
    "form.row input{width:auto;flex:1;min-width:8em}form.row input.n{flex:0 0 6em}"
    "@media(prefers-color-scheme:dark){.card,.chart{border-color:#49454f}th{color:#a8a3ad}"
    ".pill{background:#2b2f55;color:#c5cae9}.pill.off{background:#2b2930;color:#bbb}"
    ".pill.bad{background:#4a1f22;color:#f2b8b5}}"
)

PROVIDERS = {"stripe": "Stripe", "google_play": "Google Play", "manual": "Given by admin", "test": "Test"}
PAID_PROVIDERS = ("stripe", "google_play")
STATUSES = {"": "All", "premium": "Premium", "expired": "Expired", "free": "Never had Premium"}
PAGE_SIZE = 50


def page(title: str, body: str, section: str = "") -> bytes:
    links = [("/admin", "Overview", "overview"), ("/admin/users", "Users", "users"),
             ("/admin/purchases", "Payments", "purchases"), ("/ads/admin", "Ads", "ads")]
    nav = "".join(f"<a href={href}{' class=on' if key == section else ''}>{label}</a>"
                  for href, label, key in links)
    return (
        "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
        f"<title>{e(title)} · Admin</title><style>{STYLE}{EXTRA_STYLE}</style><body>"
        f"<nav>{nav}</nav>{body}"
    ).encode()


def day(t: float | None) -> str:
    return time.strftime("%d %b %Y", time.localtime(t)) if t else "–"


def moment(t: float | None) -> str:
    return time.strftime("%d %b %Y, %H:%M", time.localtime(t)) if t else "–"


def amount_cents(text: str) -> int:
    """'10.00 EUR' (Stripe) or '€10' (Google Play) -> 1000. All prices are in euros."""
    m = re.search(r"\d+(?:[.,]\d{1,2})?", text or "")
    return round(float(m.group().replace(",", ".")) * 100) if m else 0


def counts_as_revenue(p) -> bool:
    return p["provider"] in PAID_PROVIDERS and not p["refunded_at"]


def plan(user, now: float | None = None) -> str:
    now = now or time.time()
    if user["premium_until"] > now:
        return f"<span class=pill>Premium until {day(user['premium_until'])}</span>"
    if user["premium_until"]:
        return f"<span class='pill off'>Expired {day(user['premium_until'])}</span>"
    return "<span class='pill off'>Free</span>"


def message_part(message: str) -> str:
    return f"<p><b>{e(message)}</b></p>" if message else ""


# --- overview ---

def overview(stats: dict, signups: list[float], purchases, campaigns, message: str = "") -> bytes:
    now = time.time()
    month = time.strftime("%Y-%m", time.localtime(now))
    by_month: dict[str, dict[str, int]] = {}
    for p in purchases:
        if counts_as_revenue(p):
            m = time.strftime("%Y-%m", time.localtime(p["at"]))
            by_month.setdefault(m, {}).setdefault(p["provider"], 0)
            by_month[m][p["provider"]] += amount_cents(p["amount"])
    for c in campaigns:
        if c["at"]:
            m = time.strftime("%Y-%m", time.localtime(c["at"]))
            by_month.setdefault(m, {}).setdefault("ads", 0)
            by_month[m]["ads"] += c["price_cents"]
    total = sum(sum(v.values()) for v in by_month.values())
    this_month = sum(by_month.get(month, {}).values())

    cards = [
        ("Users", f"{stats['users']:,}", f"+{stats['new_7d']:,} this week"),
        ("Premium now", f"{stats['premium']:,}", f"{stats['expiring_7d']:,} end in the next 7 days"),
        ("Active this week", f"{stats['active_7d']:,}", "opened the app signed in"),
        ("Revenue this month", euros(this_month), "Premium and ads, before fees"),
        ("Revenue all time", euros(total), "refunds left out"),
    ]
    card_html = "".join(f"<div class=card><span class=muted>{e(t)}</span><b>{e(v)}</b>"
                        f"<span class=muted>{e(sub)}</span></div>" for t, v, sub in cards)

    days = 30
    start = time.mktime(time.localtime(now)[:3] + (0, 0, 0, 0, 0, -1)) - (days - 1) * 86400
    per_day = [0] * days
    for t in signups:
        i = int((t - start) // 86400)
        if 0 <= i < days:
            per_day[i] += 1
    top = max(per_day) or 1
    bars = "".join(f"<i style='height:{100 * n / top:.0f}%' title='{n}'></i>" for n in per_day)

    months = sorted(by_month, reverse=True)[:12]
    rows = "".join(
        f"<tr><td>{m}</td><td>{euros(by_month[m].get('stripe', 0))}</td>"
        f"<td>{euros(by_month[m].get('google_play', 0))}</td><td>{euros(by_month[m].get('ads', 0))}</td>"
        f"<td><b>{euros(sum(by_month[m].values()))}</b></td></tr>"
        for m in months
    )
    recent = "".join(purchase_row(p) for p in purchases[:10])
    return page("Overview", (
        "<h1>Overview</h1>" + message_part(message)
        + f"<div class=cards>{card_html}</div>"
        + f"<h2>Sign-ups, last {days} days</h2><div class=chart>{bars}</div>"
        + f"<p class=muted>{sum(per_day):,} new accounts · most in one day: {max(per_day)}</p>"
        + "<h2>Revenue by month</h2>"
        + ("<div class=wrap><table><tr><th>Month<th>Stripe<th>Google Play<th>Ads<th>Total</tr>"
           f"{rows}</table></div><p class=muted>Gross amounts: Google Play keeps 15%, Stripe about "
           "1.5% + €0.25 per payment. Payouts are in the Play Console and the Stripe dashboard.</p>"
           if rows else "<p>No revenue yet.</p>")
        + "<h2>Latest payments</h2>"
        + (f"<div class=wrap><table>{PURCHASE_HEAD}{recent}</table></div>" if recent
           else "<p>No payments yet.</p>")
    ), "overview")


# --- users ---

def users_page(users, query: str, status: str, offset: int) -> bytes:
    now = time.time()
    tabs = " · ".join(
        f"<a href='/admin/users?{urllib.parse.urlencode({'q': query, 'status': k})}'>"
        f"{'<b>' + label + '</b>' if k == status else label}</a>"
        for k, label in STATUSES.items()
    )
    rows = "".join(
        f"<tr><td><a href=/admin/users/{u['id']}>{e(u['phone'])}</a><br>"
        f"<span class=muted>u{u['id']}</span></td><td>{day(u['created_at'])}</td>"
        f"<td>{plan(u, now)}</td><td>{u['paid']}</td><td>{u['devices']}</td>"
        f"<td>{day(u['last_seen'])}</td></tr>"
        for u in users
    )

    def more(delta: int, label: str) -> str:
        q = urllib.parse.urlencode({"q": query, "status": status, "from": max(0, offset + delta)})
        return f"<a href='/admin/users?{q}'>{label}</a>"

    paging = " · ".join(
        ([more(-PAGE_SIZE, "← Newer")] if offset else [])
        + ([more(PAGE_SIZE, "Older →")] if len(users) == PAGE_SIZE else [])
    )
    return page("Users", (
        "<h1>Users</h1>"
        "<form class=row method=get action=/admin/users>"
        f"<input name=q value='{e(query)}' placeholder='Phone number or account id (u12)'>"
        f"<input type=hidden name=status value='{e(status)}'><button>Search</button></form>"
        f"<p>{tabs}</p>"
        + ("<div class=wrap><table><tr><th>Account<th>Joined<th>Plan<th>Payments<th>Devices"
           f"<th>Last seen</tr>{rows}</table></div>" if rows else "<p>No accounts found.</p>")
        + (f"<p>{paging}</p>" if paging else "")
    ), "users")


def user_page(user, sessions, purchases, log, minutes_30d: float, minutes_all: float,
              csrf: str, message: str = "") -> bytes:
    uid = user["id"]

    def form(action: str, inner: str, button: str, alt: bool = False) -> str:
        return (f"<form class=row method=post><input type=hidden name=csrf value={csrf}>"
                f"<input type=hidden name=action value={action}>{inner}"
                f"<button{' class=alt' if alt else ''}>{button}</button></form>")

    note = "<input name=note placeholder='Note for the history (optional)' maxlength=200>"
    actions = (
        form("add_days", "<input class=n type=number name=days value=30 min=1 max=3650>" + note,
             "Add days of Premium")
        + (form("end_premium", note, "End Premium now", alt=True)
           if user["premium_until"] > time.time() else "")
        + (form("sign_out", note, "Sign out on all devices", alt=True) if sessions else "")
    )

    def refund_button(p) -> str:
        given = p["provider"] in ("manual", "test")  # no money involved: just take the days back
        if p["refunded_at"]:
            return f"<span class='pill bad'>{'Taken back' if given else 'Refunded'} {day(p['refunded_at'])}</span>"
        return (f"<form method=post style='display:inline'><input type=hidden name=csrf value={csrf}>"
                f"<input type=hidden name=action value=refund><input type=hidden name=purchase "
                f"value={p['id']}><button class=alt>{'Take back' if given else 'Mark refunded'}"
                f"</button></form>")

    pays = "".join(
        f"<tr><td>{moment(p['at'])}</td><td>{e(PROVIDERS.get(p['provider'], p['provider']))}</td>"
        f"<td>{e(p['amount']) or '–'}</td><td>{p['days']} days</td>"
        f"<td class=muted>{e(p['ref'])}</td><td>{refund_button(p)}</td></tr>"
        for p in purchases
    )
    devices = "".join(f"<tr><td>{moment(s['created_at'])}</td><td>{moment(s['last_seen'])}</td></tr>"
                      for s in sessions)
    history = "".join(f"<tr><td>{moment(h['at'])}</td><td>{e(h['action'])}</td>"
                      f"<td class=muted>{e(h['note'])}</td></tr>" for h in log)
    return page(user["phone"], (
        f"<p><a href=/admin/users>← Users</a></p><h1>{e(user['phone'])}</h1>"
        f"<p class=muted>Account u{uid} · joined {day(user['created_at'])} · "
        f"learned {minutes_30d:,.0f} min in the last 30 days ({minutes_all:,.0f} min in total)</p>"
        + message_part(message)
        + f"<p>{plan(user)}</p>{actions}"
        + "<p class=muted>Refunds themselves happen in the Stripe dashboard or the Play Console. "
          "\"Mark refunded\" records it here and takes that payment's days off the plan.</p>"
        + "<h2>Payments</h2>"
        + ("<div class=wrap><table><tr><th>When<th>How<th>Amount<th>Plan<th>Reference<th></tr>"
           f"{pays}</table></div>" if pays else "<p>No payments.</p>")
        + "<h2>Signed-in devices</h2>"
        + (f"<table><tr><th>Signed in<th>Last seen</tr>{devices}</table>" if devices
           else "<p>Not signed in anywhere.</p>")
        + "<h2>Admin history</h2>"
        + (f"<table><tr><th>When<th>Change<th>Note</tr>{history}</table>" if history
           else "<p>No changes by an admin.</p>")
    ), "users")


# --- payments ---

PURCHASE_HEAD = "<tr><th>When<th>Account<th>How<th>Amount<th>Plan<th></tr>"


def purchase_row(p) -> str:
    state = "<span class='pill bad'>Refunded</span>" if p["refunded_at"] else ""
    return (f"<tr><td>{moment(p['at'])}</td><td><a href=/admin/users/{p['user_id']}>{e(p['phone'])}</a></td>"
            f"<td>{e(PROVIDERS.get(p['provider'], p['provider']))}</td><td>{e(p['amount']) or '–'}</td>"
            f"<td>{p['days']} days</td><td>{state}</td></tr>")


def purchases_page(purchases) -> bytes:
    rows = "".join(purchase_row(p) for p in purchases)
    return page("Payments", (
        "<h1>Payments</h1><p><a href=/admin/purchases.csv>Download all as CSV</a> "
        "<span class=muted>(for your accountant; opens in Excel)</span></p>"
        + (f"<div class=wrap><table>{PURCHASE_HEAD}{rows}</table></div>" if rows
           else "<p>No payments yet.</p>")
    ), "purchases")


def purchases_csv(purchases) -> bytes:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["date", "account", "phone", "provider", "amount", "amount_eur", "days",
                "reference", "refunded"])
    for p in purchases:
        w.writerow([moment(p["at"]), f"u{p['user_id']}", p["phone"], p["provider"], p["amount"],
                    f"{amount_cents(p['amount']) / 100:.2f}", p["days"], p["ref"],
                    day(p["refunded_at"]) if p["refunded_at"] else ""])
    return ("﻿" + out.getvalue()).encode("utf-8")  # BOM so Excel reads ä/€ correctly
