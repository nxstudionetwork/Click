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
| Wallet & rewards rules (`devseed/money.py`) | 5 reward catalog items, 7 missions, 1 points campaign, 2 cashback offers; opening balance + 2 promo credits (one expiring in 5 days) |
| Help articles | about 28, loaded by the `support` data migration (not seed data) |
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

Showtime (`devseed/showtime.py`, run after `devseed/events.py`): 5 cinemas with real screen layouts (IMAX, 4DX,
Dolby Atmos screens), food & drinks menus, a week of showtimes in local time with titles in each of their languages,
offers (one ended), an editorial feature (one ended), cast & crew, and three Creative Commons films by the Blender
Foundation (Big Buck Bunny, Sintel, Elephants Dream) whose real posters/trailers are hotlinked from blender.org with
attribution. Other titles are fictional and have no artwork (the app shows a typographic poster). Ratings are not
seeded: eight dev viewers (`viewer.<name>@click.local`) attended past shows and reviewed them, and follow upcoming
titles. The test customer attended The Last Lighthouse yesterday (so they can write a review).

Groceries (`devseed/groceries.py`, run from `devseed/catalog.py`): 17 categories, 81 canonical items, 10 vendors in
Bengaluru (5 existing grocery stores plus Sri Lakshmi Provisions, Gokul Dairy Corner, Bake Street Breads, Green Basket
Farm Produce and Metro Mart, which is temporarily unavailable) with opening hours, delivery settings, verification
state, offers and deals; each store lists the items it carries at its own price, MRP, stock (some sold out or low) and
received date. Loose produce uses 25 licensed Wikimedia Commons photos with credits (`devseed/grocery_media.py`);
packaged goods of the fictional brands have no photo. Store ratings come only from dev customers' order reviews:
`seed_grocery_history` adds delivered orders for the test customer (milk and bread every ~5 days, so Buy again and
Running low have real history) and the dev viewers (so Popular Near You and Frequently bought together have data).

Parcel (`devseed/parcels.py`, run from `devseed/partners.py`): the Bengaluru service area, 4 vehicles, 4 services,
13 content types (4 not accepted), package rules, and 5 delivery riders (bike, scooters, 3-wheeler, mini truck) online
with a fresh location as if their Partner App had just reported it; the dev Parcel Partner delivers by bike. Partners
are only offered jobs while their reported location is under 10 minutes old, so re-run the seed (or report a location
from the Partner App) to test matching. The test customer has 5 parcels (delivered, cash-paid, cancelled, failed, in
transit) with real status events and PIN proofs, and 2 saved recipients.

Services (`devseed/professionals.py`, run from `devseed/partners.py`): 15 service categories with 42 common jobs, 21
fictional Bengaluru professionals (no photos: they show a monogram until a real professional uploads their own),
most with an approved verification, weekly hours, their own prices and 4 offers (1 ended). `seed_service_history`
(run from `devseed/customer.py`) adds 129 paid, reviewed and cancelled jobs from dev customers so ratings, jobs
completed and rates are real aggregates; the test customer has 2 paid bookings (one reviewed), 1 cancelled and
Ramesh Kumar saved in My Professionals.

Events (`devseed/eventhub.py`, run from `devseed/partners.py`): 25 event types, 21 services, 20 fictional event teams and
specialists (planners, decorators, photographers, DJs, a band, an anchor, makeup, caterers, staff, transport, invitations,
cakes) and 10 fictional venues with capacities, amenities, rules and 47 packages. None has a logo, cover or portfolio photo.
A few upcoming dates are blocked so availability differs. `seed_event_history` (from `devseed/customer.py`) adds completed,
reviewed bookings from the dev viewers so ratings and counts are real aggregates; the test customer has one completed and
reviewed birthday, one upcoming confirmed booking, one saved event team and a 25th-anniversary plan with one quote waiting
and one request not answered yet. (`devseed/events.py` remains the Showtime movies/live-events seed.)

Hotels (`devseed/hotels.py`, from `devseed/partners.py`): 6 real destinations (Hyderabad, Bengaluru, Goa, Mysuru, Coorg,
Vijayawada) with real public landmarks and coordinates, 19 amenities, and 20 fictional properties with room types, rate plans
(room only / breakfast / non-refundable saver; weekday and weekend prices), a few sold-out nights and 5 offers (incl. coupon
STAYCLICK). No photos (a designed placeholder shows). The dev Partner App hotel login ("Lakeview Residency") owns a listing.
`seed_hotel_history` (from `devseed/customer.py`) adds completed stays with verified reviews from dev viewers (ratings are
recomputed from them); the test customer has one past reviewed stay, one upcoming stay and one saved hotel.

Travel (`devseed/travel.py`, from `devseed/partners.py`): 16 real cities with their real airports (IATA codes), railway stations (station
codes) and well-known bus boarding points, approximately located; 5 fictional bus operators, 3 fictional airlines and a fictional rail partner
with 120 timetabled services (both directions) — seat layouts, classes, fares, cancellation tiers and baggage are samples in the provider
shape, not real schedules. 2 offers (bus 10% auto; coupon FLYCLICK). `seed_travel_history` adds completed, rated trips by dev viewers
(operator ratings are recomputed from them); the test customer has an upcoming bus, a past flight, 2 saved travellers, a saved route and a
recent search.

Bookings (`devseed/experiences.py`): 16 real temples and landmarks as information only (brief general descriptions, where they're booked;
no prices, slots or timings), and 25 fictional bookable providers onboarded as partners (temples with darshan / seva / archana, museums, a
planetarium, water and theme parks, an aquarium, adventure parks, a ropeway, walks, tours, cruises, a workshop, cycling, a food trail) with
ticket types, slots, capacity and policies; a closure day and 2 offers (parks 10% auto; coupon EXPLORE15). No images. `seed_experience_history`
adds reviewed visits by dev viewers; the test customer has an upcoming special darshan, a past museum visit and a saved water park.


## Adding money in development

Wallet top-ups run against the **sandbox test provider** while `CLICK_PAYMENT_SANDBOX` is on (it follows `DEBUG`).
Add money → choose amount and method → review → the test-mode step offers *Approve* / *Decline*. The server signs and
verifies the provider event exactly as it would a real webhook, so the wallet is credited only on a verified approval.
No real money moves. With the sandbox off and no provider configured, the app shows adding money as unavailable.
