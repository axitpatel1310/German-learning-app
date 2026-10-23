# Accounts server

A small HTTP/JSON server for sign-in, the Premium plan and time stats. It uses only the Python
standard library and SQLite. The app uses it when `DMG_API_URL` is set. Without that setting the
app keeps everything on the device, as before.

What it does:
- **Sign-in with a WhatsApp code.** The server asks Twilio Verify to send the code and checks it.
  The Twilio keys stay on the server, never in the app.
- **One account per phone number.** The number is unique in the database. Signing in again
  with the same number, on any device, gives you the same account. At most 3 devices
  (`DMG_MAX_DEVICES`) stay signed in, and a new device signs out the least recently used one.
- **Limits on sending codes:** one code per number every 30 s, 5 per number per hour, and 20
  per IP address per hour, so nobody can run up the WhatsApp bill.
- **The plan:** `premium_until` is stored on the server, and the app reads it from there.
- **Time stats across devices:** each device uploads its own minutes per day, and gets the
  other devices' minutes back.

Payments are **not connected yet**. With `DMG_TEST_PAYMENTS=1` the "Get Premium" button adds a
free 3-month test period, so the flow can be tried. Without it, the app says payments are coming
soon.

## Run

```bash
python -m server --port 8600             # from the project folder
```

In a second terminal, start the app with the server's address (PowerShell):

```powershell
$env:DMG_API_URL="http://127.0.0.1:8600"; python main.py
```

Settings (environment variables):

| Variable | Meaning |
| --- | --- |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_VERIFY_SID` | Real WhatsApp codes. Without them the server runs in demo mode and returns the code to the app. |
| `DMG_ENV=production` | Refuses to start without Twilio, and turns test payments off. |
| `DMG_DB` | SQLite file (default `accounts.db` in the current folder). |
| `DMG_TEST_PAYMENTS=1` | Allows the free test purchase (never in production). |
| `DMG_MAX_DEVICES` | Devices signed in at once per account (default 3). |
| `DMG_TRUST_PROXY=1` | Use `X-Forwarded-For` for the IP limit (only behind your own proxy). |

For a public server, put it behind HTTPS (for example Caddy or nginx, or a host such as
Fly.io or Railway that provides HTTPS) and keep `accounts.db` on a persistent disk with backups.

## API

All bodies are JSON. Signed-in calls send `Authorization: Bearer <token>`.

| Call | Body | Answer |
| --- | --- | --- |
| `POST /v1/auth/start` | `{phone}` | `{sent}` (+ `demo_code` in demo mode) |
| `POST /v1/auth/verify` | `{phone, code}` | `{token, account}` |
| `POST /v1/auth/signout` | | `{ok}` |
| `GET /v1/me` | | `{phone, created_at, premium_until, payments}` |
| `POST /v1/usage` | `{device, days: {"YYYY-MM-DD": seconds}}` | `{others: {...}}` |
| `POST /v1/billing/checkout` | | `{account}` (test payments only) |
| `GET /v1/config`, `GET /health` | | server info |

## Test

```bash
python tools/test_server.py      # prints "Server OK."
```
