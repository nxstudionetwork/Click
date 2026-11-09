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
| Phone (verified) | `+1 650-555-0101` (US 555-01xx numbers are reserved for fiction); add it as a Firebase test phone number (see docs/authentication.md) |
| Password (dev only) | `ClickDev@2026` |

**Ways to sign in:**
1. **Phone OTP (the real flow):** sign in with `+1 650 555 0101`, using the code you configured for that test
   number in Firebase Console.
2. **One click (development builds only):** on the sign-in screen, the dashed **Development mode** box has
   **Login as Test Customer**.

**Safety:**
- **Backend:** `POST /api/v1/auth/dev-login` exists only when `DEBUG` is on (`CLICK_DEV_LOGIN_ENABLED` is forced off
  otherwise) and returns 404 in production.
- **Frontend:** the panel is behind `import.meta.env.DEV`, so Vite removes it from production builds.

**OTP:** Click signs customers in with Firebase Phone Auth. There is no fake OTP in Click's code: the test code
lives in Firebase Console and only works for the test number.

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

Stores and the test customer's addresses have coordinates near real Bengaluru locality centres (stable per record,
`devseed.locality_point`), so Home's "Near you" can be tested with real distance queries. Address coordinates are
only filled where missing, never overwritten.

Food (`devseed/food.py`, run after the catalogue): extra dishes per cuisine (about 180 dishes in total),
customisations on about 40 dishes (pizza sizes and toppings, biryani portions and add-ons, burger meals and extras,
coffee sizes, momo dips), and checkout rules for the five offers the engine can express. Offers with other
conditions (first order, weekends, time of day, specific items, buy-one-get-one) stay display-only.

Click. Buzz needs no seed: its feed is built from the offers, shows and stores above.

Rides (`devseed/rides.py`): 4 ride types (Bike, Auto, Cab, XL) with rates, 2 ride offers, and 7 verified test drivers
(transport partners with vehicles, colour and plate) online near Indiranagar, Koramangala, Jayanagar, HSR Layout and
Whitefield. Driver locations count as fresh for 10 minutes, so re-run the seed before testing a ride. A pickup far from
those areas (for example Yelahanka) gets "no driver".

To play the driver while testing (DEBUG only), run these in order:

```
python manage.py ride_driver latest accept     # or a ride number, e.g. CLK-R-3XZVVNM
python manage.py ride_driver latest arrived
python manage.py ride_driver latest start
python manage.py ride_driver latest complete
```

Test partners (`devseed/partners.py`): one verified partner per Partner Home configuration: a restaurant
(Basil & Lime Thai Kitchen), grocery store (FreshCart Daily) and shop (Stride Sports Co.) linked to those seeded
storefronts, a cinema linked to Click Cineplex Indiranagar, and a hotel, parcel partner and electrician (verification
pending) that show the "not live yet" Home. Sign in with **Login as test partner** in the Partner App (development
builds only; `partner/dev-login` is 404 unless DEBUG). Orders and bookings the test customer makes at those places
appear on the partner's Home.

Shopping (`devseed/shop.py`, run with the catalogue): 16 categories / 38 subcategories with attributes, 38 fictional
brands, 12 retail sellers (one in Mumbai, one unverified, one prepaid-only), about 200 listings with variants and
stock, 14 deals with real end times, redeemable seller offers and campaigns (one ended, one not started). Six dev
reviewers (`reviewer.<name>@click.local`) buy and receive orders through the real checkout and review them, so
ratings, best sellers and trending come from records. The test customer gets a delivered two-seller checkout
(returnable) and a shipped order. Listings have no photos (the app shows a placeholder); upload real ones in admin.

Parcels and home services aren't seeded because those features don't exist yet.
