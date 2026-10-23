"""Ads from businesses, shown to free users in the app and sold per view.

- /ads                The public page: the view packages and the booking form.
- /ads/c/<token>      The advertiser's own page: pay, then follow views and taps.
- /ads/admin          Your page (HTTP Basic auth, password DMG_ADMIN_KEY): approve paid ads,
                      pause or decline them, or start one that was paid by invoice.

An advertiser pays upfront (Stripe Checkout, or the test payment), you approve the ad, and it
runs until its views reach the package size. Then it stops by itself and the advertiser gets
an email.
"""

import base64
import hashlib
import hmac
import html
import os
import re
import urllib.parse

PACKAGES = [1_000, 10_000, 100_000]  # views
DEFAULT_PRICES = "1000=10,10000=80,100000=600"  # euros per package
REQUESTS_PER_IP = 10  # bookings per address per hour
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LIMITS = {"business": 60, "headline": 40, "body": 140, "link": 200, "email": 120}
STATES = {
    "unpaid": "Waiting for payment",
    "paid": "Paid, waiting for approval",
    "active": "Running",
    "paused": "Paused",
    "completed": "Completed",
    "declined": "Declined",
}


def prices(env=os.environ) -> dict[int, int]:
    """Package size -> price in cents."""
    found = {}
    for part in env.get("DMG_AD_PRICES", DEFAULT_PRICES).split(","):
        size, _, euros = part.partition("=")
        try:
            found[int(size)] = round(float(euros) * 100)
        except ValueError:
            continue
    defaults = dict(p.split("=") for p in DEFAULT_PRICES.split(","))
    return {n: found.get(n, int(defaults[str(n)]) * 100) for n in PACKAGES}


def euros(cents: int) -> str:
    return f"€{cents / 100:,.0f}" if cents % 100 == 0 else f"€{cents / 100:,.2f}"


def clean_link(link: str) -> str:
    link = link.strip()
    parts = urllib.parse.urlsplit(link)
    return link if parts.scheme == "https" and parts.netloc and " " not in link else ""


def validate(form: dict) -> tuple[dict, str]:
    """The campaign fields from the booking form, or an error message."""
    f = {k: " ".join(form.get(k, "").split()) for k in LIMITS}
    try:
        views = int(form.get("views", ""))
    except ValueError:
        views = 0
    if not all(f.values()):
        return {}, "Please fill in every field."
    too_long = next((k for k, n in LIMITS.items() if len(f[k]) > n), "")
    if too_long:
        return {}, f"The {too_long} can be at most {LIMITS[too_long]} characters."
    if not EMAIL_RE.match(f["email"]):
        return {}, "Please enter a valid email address."
    f["link"] = clean_link(f["link"])
    if not f["link"]:
        return {}, "The link must be a full https:// address."
    if views not in PACKAGES:
        return {}, "Please choose a package."
    return {**f, "views_target": views}, ""


def public_ad(c) -> dict:
    """What the app shows: no email, no counts."""
    return {"id": c["id"], "business": c["business"], "headline": c["headline"],
            "body": c["body"], "link": c["link"]}


# --- emails ---


def live_email(c, status_url: str) -> tuple[str, str]:
    return (
        "Your ad is live",
        f"Hello {c['business']},\n\nyour ad \"{c['headline']}\" is now shown in Deutsch mit "
        f"Geschichten. It runs until it has reached {c['views_target']:,} views, then it stops "
        f"by itself and we'll write to you again.\n\nFollow the views here: {status_url}\n",
    )


def completed_email(c, status_url: str) -> tuple[str, str]:
    return (
        "Your ad run is complete",
        f"Hello {c['business']},\n\nyour ad \"{c['headline']}\" has reached {c['views']:,} views "
        f"and has been switched off. It was tapped {c['clicks']:,} times.\n\n"
        f"Details: {status_url}\n\nThank you for advertising with Deutsch mit Geschichten. "
        "Book another run any time on our ads page.\n",
    )


def declined_email(c, status_url: str) -> tuple[str, str]:
    return (
        "Your ad was not approved",
        f"Hello {c['business']},\n\nwe're sorry, but we can't run your ad \"{c['headline']}\". "
        "If you have paid, we will refund the full amount. Reply to this email if you have "
        f"questions.\n\n{status_url}\n",
    )


# --- pages ---

STYLE = (
    "body{font:16px/1.5 system-ui,sans-serif;max-width:40em;margin:2em auto;padding:0 16px;color:#1d1b20}"
    "h1{font-size:1.6em}label{display:block;margin:.8em 0 .2em;font-weight:600}"
    "input,textarea{width:100%;box-sizing:border-box;padding:.5em;font:inherit;border:1px solid #ccc;"
    "border-radius:8px}button{font:inherit;padding:.5em 1.1em;border-radius:20px;border:0;"
    "background:#3f51b5;color:#fff;cursor:pointer;margin:.2em .2em .2em 0}button.alt{background:#777}"
    ".pk{display:flex;gap:.6em;flex-wrap:wrap}.pk label{flex:1;min-width:9em;border:1px solid #ccc;"
    "border-radius:12px;padding:.7em;font-weight:400}.ad{border:1px solid #ccc;border-radius:14px;"
    "padding:.8em 1em;margin:.6em 0}.tag{font-size:.75em;font-weight:700;color:#777}"
    ".bar{height:10px;background:#eee;border-radius:5px;overflow:hidden}.bar i{display:block;"
    "height:100%;background:#3f51b5}.err{color:#b3261e}.muted{color:#666;font-size:.9em}"
    "table{border-collapse:collapse;width:100%}td{border-top:1px solid #ddd;padding:.5em .3em;"
    "vertical-align:top}:root{color-scheme:light dark}body{background:#fdfbff}"
    "input,textarea{background:#fff;color:inherit}"
    "@media(prefers-color-scheme:dark){body{background:#141218;color:#e6e0e9}"
    "input,textarea{background:#1d1b20;border-color:#49454f}.muted,.tag{color:#a8a3ad}"
    ".pk label,.ad{border-color:#49454f}.bar{background:#2b2930}a{color:#a8b4ff}}"
)


def page(title: str, body: str) -> bytes:
    return (
        "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
        f"<title>{html.escape(title)}</title><style>{STYLE}</style><body>{body}"
    ).encode()


def e(value) -> str:
    return html.escape(str(value))


def ad_preview(c) -> str:
    return (f"<div class=ad><div class=tag>ANZEIGE · {e(c['business'])}</div>"
            f"<b>{e(c['headline'])}</b><div>{e(c['body'])}</div>"
            f"<div class=muted>{e(c['link'])}</div></div>")


def progress(c) -> str:
    share = min(100, 100 * c["views"] / c["views_target"])
    return (f"<div class=bar><i style='width:{share:.1f}%'></i></div>"
            f"<p>{c['views']:,} of {c['views_target']:,} views · {c['clicks']:,} taps · "
            f"{euros(c['price_cents'])} · <b>{STATES.get(c['status'], c['status'])}</b></p>")


def request_page(price_list: dict[int, int], error: str = "", form: dict | None = None) -> bytes:
    form = form or {}

    def field(name: str, label: str, area: bool = False) -> str:
        value = e(form.get(name, ""))
        tag = (f"<textarea id={name} name={name} rows=3 maxlength={LIMITS[name]}>{value}</textarea>" if area
               else f"<input id={name} name={name} maxlength={LIMITS[name]} value='{value}'>")
        return f"<label for={name}>{label}</label>{tag}"

    chosen = str(form.get("views", PACKAGES[0]))
    packages = "".join(
        f"<label><input type=radio name=views value={n} style='width:auto'"
        f"{' checked' if str(n) == chosen else ''}> <b>{n:,} views</b><br>{euros(price_list[n])}</label>"
        for n in PACKAGES
    )
    return page("Advertise with us", (
        "<h1>Advertise in Deutsch mit Geschichten</h1>"
        "<p>Reach people who are learning German: language schools, translators, tutors, shops "
        "and services for newcomers. Your ad is a small card in the app with your name, a "
        "headline, one sentence and a link. You pay once, upfront, for a number of views; when "
        "they're reached, the ad stops by itself and we email you.</p>"
        + (f"<p class=err>{e(error)}</p>" if error else "")
        + "<form method=post action=/ads/request>"
        + f"<label>Package</label><div class=pk>{packages}</div>"
        + field("business", "Business name")
        + field("headline", f"Headline (up to {LIMITS['headline']} characters)")
        + field("body", f"Text (up to {LIMITS['body']} characters)", area=True)
        + field("link", "Link (https://…)")
        + field("email", "Your email (for the receipt and the end-of-run notice)")
        + "<p><button>Continue to payment</button></p></form>"
        "<p class=muted>We check every ad before it runs; if we can't run it, you get a full "
        "refund. A view is counted when the card is shown to someone, at most once per person "
        "every 30 minutes. Premium users don't see ads.</p>"
    ))


def campaign_page(c, payments: list[str], message: str = "") -> bytes:
    """The advertiser's page: the payment buttons while unpaid, then the progress."""
    body = "<h1>Your ad</h1>" + (f"<p><b>{e(message)}</b></p>" if message else "") + ad_preview(c)
    if c["status"] == "unpaid":
        pay = "".join(
            f"<form method=post action=/ads/c/{e(c['token'])}/pay style='display:inline'>"
            f"<button name=provider value={p}>{label}</button></form>"
            for p, label in (("stripe", f"Pay {euros(c['price_cents'])} by card"),
                             ("test", f"Test payment {euros(c['price_cents'])} (no money)"))
            if p in payments
        )
        body += (f"<p>{c['views_target']:,} views for <b>{euros(c['price_cents'])}</b>.</p>"
                 + (pay or "<p>Online payment isn't connected yet. We'll email you an invoice; "
                    "the ad starts once it's paid.</p>"))
    else:
        body += progress(c)
    return page("Your ad", body + "<p class=muted>Keep this page's address to follow your "
                "campaign.</p>")


def admin_page(campaigns, csrf: str, notes: dict, mail_on: bool, message: str = "") -> bytes:
    def actions(c) -> str:
        buttons = {
            "unpaid": [("start", "Start (paid by invoice)"), ("decline", "Decline")],
            "paid": [("start", "Approve and start"), ("decline", "Decline (refund)")],
            "active": [("pause", "Pause")],
            "paused": [("resume", "Resume"), ("decline", "Stop")],
        }.get(c["status"], [])
        return "".join(
            f"<form method=post style='display:inline'><input type=hidden name=csrf value={csrf}>"
            f"<input type=hidden name=id value={c['id']}><button name=action value={a}"
            f"{' class=alt' if a in ('pause', 'decline') else ''}>{label}</button></form>"
            for a, label in buttons
        )

    def mails(c) -> str:
        return "".join(
            f"<details class=muted><summary>{'Sent' if n['sent'] else 'Not sent'}: {e(n['subject'])}"
            f"</summary><pre style='white-space:pre-wrap'>{e(n['body'])}</pre></details>"
            for n in notes.get(c["id"], [])
        )

    rows = "".join(
        f"<tr><td>#{c['id']}<br><span class=muted>{e(c['email'])}"
        f"{'<br>' + e(c['payment_ref']) if c['payment_ref'] else ''}</span></td>"
        f"<td>{ad_preview(c)}{progress(c)}{actions(c)}{mails(c)}</td></tr>"
        for c in campaigns
    )
    return page("Ads admin", (
        "<h1>Ads</h1>"
        + (f"<p><b>{e(message)}</b></p>" if message else "")
        + ("" if mail_on else "<p class=muted>No mail server set (DMG_SMTP_HOST), so emails to "
           "advertisers are kept below instead of being sent. Copy them by hand.</p>")
        + "<p class=muted>Declining a paid ad doesn't refund it automatically: refund it in "
          "the Stripe dashboard.</p>"
        + (f"<table>{rows}</table>" if rows else "<p>No campaigns yet.</p>")
    ))


# --- admin sign-in ---


def admin_ok(header: str, key: str) -> bool:
    if not key or not header.startswith("Basic "):
        return False
    try:
        _, _, password = base64.b64decode(header[6:]).decode().partition(":")
    except (ValueError, UnicodeDecodeError):
        return False
    return hmac.compare_digest(password.encode(), key.encode())


def csrf_token(key: str) -> str:
    """Ties the admin forms to the password, so another site can't submit them."""
    return hmac.new(key.encode(), b"ads-admin", hashlib.sha256).hexdigest()[:32]
