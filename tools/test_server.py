"""End-to-end check of the accounts server with the app's ServerAccount client.

Runs a server on a free port with a temporary database and demo codes, then signs in from
several "devices". Prints "Server OK." when everything passes.
"""

import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server.app as srv  # noqa: E402
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

    print("Server OK.")


if __name__ == "__main__":
    main()
