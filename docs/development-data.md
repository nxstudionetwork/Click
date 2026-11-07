# Development data and test login

> **DEVELOPMENT MOCK DATA.** Everything here is fictional and exists only for local development and UI testing.
> Never load it into production.

## Load it

```bash
cd backend
python manage.py migrate
python manage.py seed_dev_data            # catalogue + movies/events + test customer with history
python manage.py seed_dev_data --catalog-only
```

- **Development only:** the command refuses to run unless `DJANGO_DEBUG=true`.
- **Safe to re-run:** catalogue rows are updated in place by natural keys (store slug, product name, event slug). The
  test customer's history is created only once per section. Nothing is ever deleted, so you can re-run it at any
  time; re-running also tops up bookable shows for the next 3 days.
- **Where the data lives:** `backend/devseed/` (`catalog.py`, `events.py`, `customer.py`).
- **Real code paths:** customer history goes through the same services real customers use (cart, order placement,
  status changes, bookings, wallet, rewards, notifications), so every relationship is genuine.

## Test customer

| Field | Value |
|---|---|
| Name | Click Test User |
| Click Customer ID | `CLK-CS-TEST001` |
| Email | `test.customer@click.local` (the reserved `.local` domain can't be a real inbox) |
| Phone | `+91 00000 00001` (not an allocatable Indian mobile number) |
| Password (dev only) | `ClickDev@2026` |

**Ways to sign in (development only):**
1. **One click:** on the Sign in screen, the dashed **Development mode** box has **Login as Test Customer**.
2. **Normal form:** sign in with the email and password above.

**Safety:**
- **Backend:** `POST /api/v1/auth/dev-login` exists only when `DEBUG` is on (`CLICK_DEV_LOGIN_ENABLED` is forced off
  otherwise) and returns 404 in production.
- **Frontend:** the panel is behind `import.meta.env.DEV`, so Vite removes it from production builds.

**OTP:** Click's authentication is currently email + password. When OTP login is added, the test customer's phone
number will be configured as the provider's sandbox number.

## What gets seeded

| Data | Count |
|---|---|
| Restaurants | 20 (2 not accepting orders, 1 unrated, 1 very long name) |
| Food items (menus) | 84 (some sold out) |
| Grocery stores / products | 5 / 24 (some out of stock, low stock, discounted) |
| Shops / shopping products | 5 / 20 |
| Offers | 20 active + 2 expired |
| Movies | 20 (15 now showing, 5 coming soon) |
| Live events | 20 (18 bookable, 2 coming soon) |
| Venues / upcoming shows | 6 / about 300 |
| Test customer: addresses | 4 |
| Test customer: orders / order items | 20 / 39 (delivered, cancelled, in progress, wallet and cash) |
| Test customer: bookings | 20 (4 cancelled; pay at venue and wallet) |
| Test customer: wallet transactions | 19 (3 credits; payments and refunds created by real orders and bookings) |
| Test customer: reward transactions | 11 (earned by delivered orders) |
| Test customer: notifications | about 130 (8 newest unread) |
| Test customer: wishlist | 20 (10 stores, 10 products) |
| Test customer: support tickets | 20 (all statuses) |
| Test customer: cart | 2 items |

Rides, parcels, home services and Buzz aren't seeded because those features don't exist yet; their records
would have no real model, API or flow behind them. They will be seeded when each feature is built.
