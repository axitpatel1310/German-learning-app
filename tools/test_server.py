"""End-to-end check of the accounts server with the app's ServerAccount client.

Runs a server on a free port with a temporary database and demo codes, then signs in from
several "devices", checks Stripe and Google Play payments against fake provider APIs, and runs
an ad campaign from booking to the end-of-run email.
Prints "Server OK." when everything passes.
"""

import base64
import hashlib
import hmac
import json
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server.app as srv  # noqa: E402
from server.billing import GooglePlay, Stripe  # noqa: E402
from app.account import ServerAccount, Usage  # noqa: E402
from app.api import Api, ApiError  # noqa: E402
from app.otp import OtpError  # noqa: E402


def start(tmp: Path, **env) -> tuple[str, object]:
    config = srv.Config({"DMG_DB": str(tmp / f"accounts-{len(env)}.db"), **env})
    httpd = srv.serve("127.0.0.1", 0, config)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{httpd.server_address[1]}", httpd


def sign_in(url: str, folder: Path, phone: str) -> ServerAccount:
    folder.mkdir(exist_ok=True)
    acc = ServerAccount(url, folder / "account.json")
    code = acc.send_code(phone)
    assert code and len(code) == 6, "demo mode returns the code"
    wrong = "000000" if code != "000000" else "111111"
    assert acc.verify(wrong) is False, "a wrong code is refused"
    assert acc.verify(code) is True and acc.signed_in
    return acc


def main():
    srv.RESEND_AFTER = 0  # the 30 s wait is checked separately below
    tmp = Path(tempfile.mkdtemp())
    url, httpd = start(tmp, DMG_TEST_PAYMENTS="1", DMG_MAX_DEVICES="3")
    phone = "+4915123456789"

    try:
        Api(url).post("/v1/auth/start", {"phone": "12345"})
        raise AssertionError("an invalid number is refused")
    except ApiError as e:
        assert e.status == 400

    # Device A signs in, buys the plan and records some minutes.
    a = sign_in(url, tmp / "a", phone)
    assert not a.premium and a.payments == ["test"]
    a.buy()
    assert a.premium and 89 <= a.days_left() <= 91
    ua = Usage(tmp / "a" / "usage.json")
    ua.days = {"2026-10-20": 600.0, "2026-10-21": 300.0}
    a.sync_usage(ua)
    assert ua.others == {}

    # Device B, same number: the same account, so the plan and A's minutes come along.
    b = sign_in(url, tmp / "b", phone)
    assert b.premium, "one account per number: the plan is kept"
    ub = Usage(tmp / "b" / "usage.json")
    ub.days = {"2026-10-21": 120.0}
    b.sync_usage(ub)
    assert ub.others == {"2026-10-20": 600.0, "2026-10-21": 300.0}
    assert ub.total() == 1020.0
    b.sync_usage(ub)  # uploading twice changes nothing
    a.sync_usage(ua)
    assert ua.others == {"2026-10-21": 120.0}

    # A different number is a different account.
    c = sign_in(url, tmp / "c", "+436601234567")
    assert not c.premium

    # A fourth device on the first number signs out the least recently used one (A).
    time.sleep(0.01)
    b.refresh()
    time.sleep(0.01)
    sign_in(url, tmp / "d", phone)
    sign_in(url, tmp / "e", phone)
    assert a.refresh() is False and not a.signed_in, "oldest device is signed out"
    assert b.refresh() is True

    # Signing out ends the session on the server too.
    token = b.api.token
    b.sign_out()
    assert not b.signed_in
    try:
        Api(url, token).get("/v1/me")
        raise AssertionError("the old token no longer works")
    except ApiError as e:
        assert e.status == 401

    # The 30-second wait between codes for the same number.
    srv.RESEND_AFTER = 30
    try:
        ServerAccount(url, tmp / "f.json").send_code(phone)
        raise AssertionError("a second code within 30 s is refused")
    except OtpError:
        pass
    httpd.shutdown()

    # Without test payments the server refuses to activate Premium.
    url2, httpd2 = start(tmp)
    srv.RESEND_AFTER = 0
    d = sign_in(url2, tmp / "g", phone)
    assert d.payments == []
    try:
        d.buy()
        raise AssertionError("no payments configured")
    except OtpError as e:
        assert "not connected" in str(e)
    assert not d.premium
    httpd2.shutdown()

    billing_checks(tmp, phone)
    ads_checks(tmp)
    print("Server OK.")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def web(url: str, path: str, form: dict | None = None, password: str = "") -> tuple[int, dict, str]:
    """A browser-style request to the ads pages: (status, headers, page), without following redirects."""
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    req = urllib.request.Request(url + path, data=data, method="POST" if data is not None else "GET")
    if password:
        req.add_header("Authorization", "Basic " + base64.b64encode(f"admin:{password}".encode()).decode())
    try:
        with urllib.request.build_opener(NoRedirect).open(req) as resp:
            return resp.status, dict(resp.headers), resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


AD = {"business": "Sprachschule Nord", "headline": "Prüfung bestehen!", "email": "info@example.test",
      "body": "Goethe-Kurse in kleinen Gruppen, B1 bis C1.", "link": "https://sprachschule.example.test"}


def ads_checks(tmp: Path):
    """Booking, paying, approving, showing, counting and stopping an ad."""
    admin = "admin-test-key"
    url, httpd = start(tmp, DMG_TEST_PAYMENTS="1", DMG_ADMIN_KEY=admin, DMG_AD_PRICES="1000=10,10000=80")
    store = httpd.app.store

    status, _, page = web(url, "/ads")
    assert status == 200 and "€10" in page and "€80" in page and "€600" in page
    assert web(url, "/ads/request", {**AD, "link": "http://x.test", "views": "1000"})[0] == 400
    assert web(url, "/ads/request", {**AD, "views": "5000"})[0] == 400, "only the three packages"
    status, headers, _ = web(url, "/ads/request", {**AD, "views": "1000"})
    assert status == 303 and headers["Location"].startswith("/ads/c/")
    token = headers["Location"].rsplit("/", 1)[1]
    c = store.campaign_by_token(token)
    assert c["status"] == "unpaid" and c["price_cents"] == 1000 and c["views_target"] == 1000

    a = sign_in(url, tmp / "ad-a", "+4915100000001")
    assert a.next_ad() is None, "an unpaid ad never runs"
    status, _, page = web(url, f"/ads/c/{token}")
    assert "Test payment €10" in page and "<script" not in page
    assert web(url, f"/ads/c/{token}/pay", {"provider": "stripe"})[0] == 400, "no Stripe on this server"
    assert web(url, f"/ads/c/{token}/pay", {"provider": "test"})[0] == 303
    assert store.campaign(c["id"])["status"] == "paid"
    assert a.next_ad() is None, "a paid ad waits for approval"

    # Approval on the admin page: password and form token required.
    assert web(url, "/ads/admin")[0] == 401
    assert web(url, "/ads/admin", password="wrong")[0] == 401
    _, _, page = web(url, "/ads/admin", {"id": str(c["id"]), "action": "start", "csrf": "x"}, admin)
    assert "expired" in page and store.campaign(c["id"])["status"] == "paid"
    csrf = srv.ads.csrf_token(admin)
    _, _, page = web(url, "/ads/admin", {"id": str(c["id"]), "action": "start", "csrf": csrf}, admin)
    assert store.campaign(c["id"])["status"] == "active" and "Sprachschule Nord" in page
    assert [n["subject"] for n in store.notifications(c["id"])] == ["Your ad is live"]

    # Free users see it, a view counts once per person per 30 minutes, Premium is ad-free.
    ad = a.next_ad()
    assert ad and ad["headline"] == AD["headline"] and "email" not in ad
    assert a.api.post("/v1/ads/seen", {"id": ad["id"]})["counted"] is True
    assert a.api.post("/v1/ads/seen", {"id": ad["id"]})["counted"] is False, "the same person again"
    a.ad_click(ad["id"])
    p = sign_in(url, tmp / "ad-p", "+4915100000002")
    p.buy()
    assert p.next_ad() is None and p.api.post("/v1/ads/seen", {"id": ad["id"]})["counted"] is False

    # Reaching the target switches the ad off and tells the advertiser.
    store.conn.execute("UPDATE campaigns SET views = 998 WHERE id = ?", (c["id"],))
    b = sign_in(url, tmp / "ad-b", "+4915100000003")
    d = sign_in(url, tmp / "ad-d", "+4915100000004")
    b.ad_seen(ad["id"])
    assert store.campaign(c["id"])["status"] == "active"
    d.ad_seen(ad["id"])
    done = store.campaign(c["id"])
    assert done["status"] == "completed" and done["views"] == 1000 and done["clicks"] == 1
    assert d.next_ad() is None and d.api.post("/v1/ads/seen", {"id": ad["id"]})["counted"] is False
    note = store.notifications(c["id"])[-1]
    assert note["subject"] == "Your ad run is complete" and "1,000 views" in note["body"]
    assert note["email"] == AD["email"] and token in note["body"]
    assert "1,000 of 1,000 views" in web(url, f"/ads/c/{token}")[2]
    httpd.shutdown()

    # Stripe: the booking opens Checkout, and only a signed, paid, full-price event counts.
    url, httpd = start(tmp, DMG_ADMIN_KEY=admin, DMG_PUBLIC_URL="https://api.example.test")
    calls = []

    def fake_http(method, address, form=None, headers=None):
        calls.append(form or {})
        return {"id": "cs_ad_1", "url": "https://checkout.stripe.com/c/pay/cs_ad_1"}

    httpd.app.stripe = Stripe("sk_test_x", "whsec_ad", "https://api.example.test", request=fake_http)
    _, headers, _ = web(url, "/ads/request", {**AD, "views": "10000"})
    token = headers["Location"].rsplit("/", 1)[1]
    c = httpd.app.store.campaign_by_token(token)
    status, headers, _ = web(url, f"/ads/c/{token}/pay", {"provider": "stripe"})
    assert status == 303 and headers["Location"].startswith("https://checkout.stripe.com/")
    assert calls[-1]["client_reference_id"] == f"ad-{c['id']}"
    assert calls[-1]["line_items[0][price_data][unit_amount]"] == "8000"
    assert calls[-1]["customer_email"] == AD["email"]
    assert web(url, f"/ads/c/{token}/pay", {"provider": "test"})[0] == 400, "no test payments here"

    def paid(amount: int) -> bytes:
        return json.dumps({"type": "checkout.session.completed", "data": {"object": {
            "id": "cs_ad_1", "client_reference_id": f"ad-{c['id']}", "payment_status": "paid",
            "amount_total": amount, "currency": "eur"}}}).encode()

    def sign(payload: bytes) -> str:
        t = str(int(time.time()))
        return f"t={t},v1=" + hmac.new(b"whsec_ad", f"{t}.".encode() + payload, hashlib.sha256).hexdigest()

    assert post_webhook(url, paid(100), sign(paid(100))) == 200
    assert httpd.app.store.campaign(c["id"])["status"] == "unpaid", "a smaller amount doesn't count"
    assert post_webhook(url, paid(8000), sign(paid(8000))) == 200
    assert httpd.app.store.campaign(c["id"])["status"] == "paid"
    assert post_webhook(url, paid(8000), sign(paid(8000))) == 200, "Stripe may send an event twice"
    assert "Payment received" in web(url, f"/ads/c/{token}?paid=1")[2]

    # Declining a paid ad tells the advertiser about the refund.
    web(url, "/ads/admin", {"id": str(c["id"]), "action": "decline", "csrf": csrf}, admin)
    assert httpd.app.store.campaign(c["id"])["status"] == "declined"
    assert httpd.app.store.notifications(c["id"])[-1]["subject"] == "Your ad was not approved"
    httpd.shutdown()


def post_webhook(url: str, payload: bytes, signature: str) -> int:
    req = urllib.request.Request(url + "/v1/billing/stripe/webhook", data=payload, method="POST",
                                 headers={"Stripe-Signature": signature, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def billing_checks(tmp: Path, phone: str):
    """Stripe and Google Play with fake provider APIs: only confirmed payments grant Premium,
    and each payment counts once."""
    url, httpd = start(tmp, DMG_PUBLIC_URL="https://api.example.test")
    calls, play_answer = [], {}

    def fake_http(method, address, form=None, headers=None):
        calls.append((method, address, form or {}))
        if address.endswith("/checkout/sessions"):
            return {"id": "cs_test_1", "url": "https://checkout.stripe.com/c/pay/cs_test_1"}
        if address.endswith(":consume"):
            return {}
        return dict(play_answer)

    secret = "whsec_test"
    httpd.app.stripe = Stripe("sk_test_x", secret, "https://api.example.test", request=fake_http)
    httpd.app.play = GooglePlay("com.sprachup.sprach_up", "premium_3_months", "", request=fake_http,
                                access_token=lambda: ("fake", time.time() + 3600))

    acc = sign_in(url, tmp / "pay", phone)
    assert acc.payments == ["stripe", "google_play"] and acc.play_product == "premium_3_months"
    try:
        acc.buy()
        raise AssertionError("no test purchases on this server")
    except OtpError:
        pass

    # Stripe: a Checkout Session for this account, €10, coming back to the server's pages.
    assert acc.checkout_url().startswith("https://checkout.stripe.com/")
    form = calls[-1][2]
    user_id = form["client_reference_id"]
    assert form["line_items[0][price_data][unit_amount]"] == "1000"
    assert form["line_items[0][price_data][currency]"] == "eur"
    assert form["success_url"] == "https://api.example.test/billing/done"
    acc.refresh()
    assert not acc.premium, "opening the payment page grants nothing"

    def event(status: str) -> bytes:
        return json.dumps({"type": "checkout.session.completed", "data": {"object": {
            "id": "cs_test_1", "client_reference_id": user_id, "payment_status": status,
            "amount_total": 1000, "currency": "eur"}}}).encode()

    def sign(payload: bytes, key: str = secret, at: int | None = None) -> str:
        t = str(at or int(time.time()))
        return f"t={t},v1=" + hmac.new(key.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()

    paid = event("paid")
    assert post_webhook(url, paid, sign(paid, "whsec_wrong")) == 400, "a forged event is refused"
    assert post_webhook(url, paid, sign(paid, at=int(time.time()) - 3600)) == 400, "an old event is refused"
    assert post_webhook(url, event("unpaid"), sign(event("unpaid"))) == 200
    acc.refresh()
    assert not acc.premium, "an unpaid session grants nothing"
    assert post_webhook(url, paid, sign(paid)) == 200
    acc.refresh()
    assert acc.premium and 89 <= acc.days_left() <= 91
    assert post_webhook(url, paid, sign(paid)) == 200, "Stripe may send an event twice"
    acc.refresh()
    assert acc.days_left() <= 91, "the same payment counts once"

    # Google Play: the server checks the token, the account and the state, then consumes it.
    play_answer.update(purchaseState=0, obfuscatedExternalAccountId=acc.billing_ref, orderId="GPA.1")
    acc.confirm_play("token-1")
    assert 179 <= acc.days_left() <= 181, "a second purchase adds 3 more months"
    assert calls[-1][1].endswith("/tokens/token-1:consume")
    acc.confirm_play("token-1")
    assert acc.days_left() <= 181, "the same order counts once"
    for answer, status in (({"obfuscatedExternalAccountId": "u999"}, "another account"),
                           ({"purchaseState": 1}, "not completed")):
        play_answer.update({"purchaseState": 0, "obfuscatedExternalAccountId": acc.billing_ref,
                            "orderId": "GPA.2", **answer})
        try:
            acc.confirm_play("token-2")
            raise AssertionError(f"a purchase that is {status} is refused")
        except OtpError:
            pass
    assert acc.days_left() <= 181

    with urllib.request.urlopen(url + "/billing/done") as resp:
        assert resp.status == 200 and b"Payment received" in resp.read()
    httpd.shutdown()


if __name__ == "__main__":
    main()
