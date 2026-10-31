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

- **Payments, confirmed by the server** (`server/billing.py`). Only the server grants Premium:
  - **Stripe Checkout** (desktop and web): the app asks for a Checkout Session and opens it in
    the browser. Stripe calls the webhook when the payment is done; the server checks the
    signature and adds 3 months. The app asks the server every few seconds until Premium shows.
  - **Google Play Billing** (Android): the app buys the one-time product with Google Play and
    sends the purchase token here. The server checks it with the Google Play Developer API
    (state "purchased", and bought by this account), adds 3 months, then consumes it so the
    plan can be bought again. Purchases the server never confirmed are sent again on the next
    start.
  - Each payment reference (Checkout Session id, Play order id) counts once, so repeated
    webhooks or retries never add extra months. Providers see the account as `u<id>`, never the
    phone number.
  - With `DMG_TEST_PAYMENTS=1` there is also a free 3-month test purchase. With no provider set,
    the app says payments are coming soon.

- **Ads, sold per view** (`server/ads.py`, `server/mail.py`). Businesses book an ad on
  `/ads`: a name, a headline, one sentence and an https link, for 1,000, 10,000 or 100,000
  views. They pay upfront, you approve the ad on `/ads/admin`, and free users see it as a small
  "Anzeige" card on the home screen and after each story. A view counts when the card is shown,
  at most once per person per ad every 30 minutes. When the views reach the package size the
  ad stops by itself and the advertiser gets an email ("Your ad run is complete"). Premium users
  never see ads. Each advertiser has a private page (`/ads/c/<token>`) with views, taps and the
  state.
- **Ads aimed at levels:** an advertiser can tick the CEFR levels the ad is for (e.g. B1 and
  B2 for a B2 exam course; none or all ticked = every learner). The app sends the level of the
  last story the learner opened, and an aimed ad only goes to learners at one of its levels.
  Learners whose level isn't known yet (no story opened) only get ads for every learner.
  Older databases get the new `levels` column automatically on start.
- **Invoices** (`server/invoice.py`): on their page, advertisers enter a billing address and
  get a one-page PDF invoice (Rechnung), numbered in order (`DMG-2026-0001`, …). It's made out
  once and never changes afterwards. Paid bookings show "Bezahlt am …"; on a server without
  online payment it asks for a bank transfer within 14 days. Your admin page links each one.

## Admin dashboard

Open `https://<your server>/admin` and sign in with `DMG_ADMIN_KEY` (any user name). The same
sign-in also opens `/ads/admin`. Without `DMG_ADMIN_KEY` the admin pages don't exist.

- **Overview** (`/admin`): users and new sign-ups this week, Premium accounts (and how many end in
  the next 7 days), learners active this week, revenue this month and in total, a sign-up chart for
  the last 30 days, revenue per month split into Stripe, Google Play and ads, and the latest
  payments. Amounts are gross: Google Play and Stripe take their fees before paying you out.
- **Users** (`/admin/users`): search by part of a phone number or by account id (`u12`, the id
  Stripe and Google Play see), and filter by Premium, expired or never had Premium.
- **One account** (`/admin/users/<id>`): plan, payments, signed-in devices, learning time, and:
  - **Add days of Premium**: for testers, prizes or support cases. Listed as "Given by admin".
  - **End Premium now.**
  - **Mark refunded**: after you refund a payment in the Stripe dashboard or the Play Console,
    record it here. Its days come off the plan, and it no longer counts as revenue. For days you
    gave by hand the button is called **Take back**.
  - **Sign out on all devices**: for example when someone has lost their phone.

  Every change is kept in the account's **admin history**, with the note you typed.
- **Payments** (`/admin/purchases`): every payment, and **Download all as CSV** for your accountant.

## Ads

1. Set `DMG_ADMIN_KEY` to a long random password. `/ads/admin` asks for it (any user name).
   Without it there is no admin page, so booked ads can't be approved.
2. Prices: `DMG_AD_PRICES` in euros, default `1000=10,10000=80,100000=600`.
3. Payment: with Stripe set up (see below) advertisers pay by card. Add nothing in Stripe: the
   same webhook handles ad payments, and only the full price of the package counts. With
   `DMG_TEST_PAYMENTS=1` there's a "Test payment" button instead. Without either, the booking
   page says you'll send an invoice; once it's paid, press **Start (paid by invoice)**.
4. Emails: set `DMG_SMTP_HOST`, `DMG_SMTP_PORT` (587, STARTTLS), `DMG_SMTP_USER`,
   `DMG_SMTP_PASSWORD` and `DMG_MAIL_FROM`. Without them the emails are kept and shown on the
   admin page, so you can forward them by hand.
5. **Declining a paid ad doesn't refund it automatically.** Refund it in the Stripe dashboard;
   the advertiser gets an email saying the money will be refunded.
6. Invoices: set `DMG_INVOICE_NAME`, `DMG_INVOICE_ADDRESS` (lines separated by `|`, e.g.
   `Hauptstraße 1|10115 Berlin`) and `DMG_INVOICE_TAX_ID` (Steuernummer or USt-IdNr.).
   Optional: `DMG_INVOICE_EMAIL`, `DMG_INVOICE_BANK` (shown on unpaid invoices) and
   `DMG_INVOICE_VAT` (default 19). Package prices count as the **total incl. VAT**, so €10 is
   €8.40 + €1.60. With `DMG_INVOICE_VAT=0` the invoice has the small-business note
   (§ 19 UStG) instead. Until name, address and tax number are set, and for test payments,
   the PDF is marked "MUSTER / SAMPLE". Please have your tax adviser check the layout once.
7. Link the ads page from your website, e.g. `https://<your server>/ads`. The app shows it in
   Profile → "Advertise your business".

## Setting up payments

**Stripe** (desktop/web):
1. In the Stripe dashboard, optionally create a product "Premium · 3 months" with a one-time
   price of €10 and copy the price id (`price_…`). Without it the server sends €10 inline.
2. Add a webhook endpoint `https://<your server>/v1/billing/stripe/webhook` for the events
   `checkout.session.completed` and `checkout.session.async_payment_succeeded`, and copy its
   signing secret (`whsec_…`).
3. Set `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `DMG_PUBLIC_URL` (and `STRIPE_PRICE_ID`).
   Start with test keys (`sk_test_…`) and Stripe's test cards; switch to live keys only when
   you're ready to take real money. For local testing, `stripe listen --forward-to
   localhost:8600/v1/billing/stripe/webhook` forwards webhooks to your computer.

**Google Play** (Android):
1. In the Play Console, create a one-time product with the id `premium_3_months` (or set
   `GOOGLE_PLAY_PRODUCT_ID`), price €10.
2. Create a Google Cloud service account, give it access to your app in the Play Console
   (Users and permissions → financial data / manage orders), and download its JSON key.
3. On the server: `pip install google-auth`, then set `GOOGLE_PLAY_PACKAGE` (the app id, e.g.
   `com.sprachup.sprach_up`) and `GOOGLE_PLAY_KEY_FILE` (path to the JSON key).
4. Build the app with `flet build apk`/`aab` and upload it to a test track: Play Billing only
   works for apps installed from Google Play, with a license-tester account.

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
| `DMG_PUBLIC_URL` | The server's public address, used for Stripe's return pages (default `http://127.0.0.1:8600`). |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | Turn on Stripe Checkout. |
| `STRIPE_PRICE_ID` | Optional Stripe price for the plan; without it €10 is sent inline. |
| `GOOGLE_PLAY_PACKAGE`, `GOOGLE_PLAY_KEY_FILE` | Turn on Google Play purchase checks (needs `google-auth`). |
| `GOOGLE_PLAY_PRODUCT_ID` | The Play product (default `premium_3_months`). |
| `DMG_MAX_DEVICES` | Devices signed in at once per account (default 3). |
| `DMG_TRUST_PROXY=1` | Use `X-Forwarded-For` for the IP limit (only behind your own proxy). |
| `DMG_ADMIN_KEY` | Password for the admin dashboard (`/admin`) and `/ads/admin`. |
| `DMG_AD_PRICES` | Ad prices in euros (default `1000=10,10000=80,100000=600`). |
| `DMG_INVOICE_NAME`, `DMG_INVOICE_ADDRESS`, `DMG_INVOICE_TAX_ID` | Your details on ad invoices (address lines separated by `|`). |
| `DMG_INVOICE_EMAIL`, `DMG_INVOICE_BANK`, `DMG_INVOICE_VAT` | Optional invoice details; VAT rate in % (default 19, `0` = small business, § 19 UStG). |
| `DMG_SMTP_HOST`, `DMG_SMTP_PORT`, `DMG_SMTP_USER`, `DMG_SMTP_PASSWORD`, `DMG_MAIL_FROM` | Emails to advertisers. Without them, emails are kept on the admin page. |

For a public server, put it behind HTTPS (for example Caddy or nginx, or a host such as
Fly.io or Railway that provides HTTPS) and keep `accounts.db` on a persistent disk with backups.

## API

All bodies are JSON. Signed-in calls send `Authorization: Bearer <token>`.

| Call | Body | Answer |
| --- | --- | --- |
| `POST /v1/auth/start` | `{phone}` | `{sent}` (+ `demo_code` in demo mode) |
| `POST /v1/auth/verify` | `{phone, code}` | `{token, account}` |
| `POST /v1/auth/signout` | | `{ok}` |
| `GET /v1/me` | | `{phone, created_at, premium_until, payments, billing_ref, play_product}` |
| `POST /v1/usage` | `{device, days: {"YYYY-MM-DD": seconds}}` | `{others: {...}}` |
| `POST /v1/billing/checkout` | `{provider: "stripe"}` | `{url}`: the Stripe payment page |
| `POST /v1/billing/checkout` | `{provider: "test"}` | `{account}` (test payments only) |
| `POST /v1/billing/stripe/webhook` | Stripe event (signed) | `{received}`; grants Premium for paid sessions |
| `POST /v1/billing/google/verify` | `{purchase_token, product_id}` | `{account}` after Google confirms |
| `GET /billing/done`, `GET /billing/cancel` | | small pages Stripe returns to |
| `GET /v1/ads/next` | | `{ad}`: an ad for every learner (`null` for Premium or when none runs) |
| `POST /v1/ads/next` | `{level}` | `{ad}`: the same, including ads aimed at that level; `ad.levels` lists its levels (`[]` = all) |
| `POST /v1/ads/seen` | `{id}` | `{counted}`; once per person per ad every 30 minutes |
| `POST /v1/ads/click` | `{id}` | `{ok}` |
| `GET /ads`, `POST /ads/request` | form | booking page for advertisers |
| `GET /ads/c/<token>`, `POST /ads/c/<token>/pay` | form | the advertiser's page and payment |
| `POST /ads/c/<token>/invoice`, `GET /ads/c/<token>/invoice.pdf` | form `{address}` | makes out the invoice once, then serves the PDF |
| `GET`/`POST /ads/admin` | form, Basic auth | your page for approving ads |
| `GET /admin`, `/admin/users`, `/admin/users/<id>`, `/admin/purchases(.csv)` | form, Basic auth | the admin dashboard |
| `GET /v1/config`, `GET /health` | | server info |

## Test

```bash
python tools/test_server.py      # prints "Server OK." (Stripe and Google Play are faked)
```
