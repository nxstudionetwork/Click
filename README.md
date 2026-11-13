# Click

## Run Click on Windows (easy way)

**One-time installs** (keep the default options in each installer):
1. **Node.js 22 LTS**: https://nodejs.org
2. **Python 3.12+**: https://www.python.org/downloads/ (tick **"Add python.exe to PATH"** on the first screen)
3. **PostgreSQL 16**: https://www.postgresql.org/download/windows/ (write down the password you choose for
   the `postgres` user)

**Every time:**
1. Get the latest code: open the Click folder, then run `git pull` in a terminal (or GitHub Desktop → *Pull origin*).
2. Double-click **`START-CLICK.bat`**.
   - The first run installs everything and asks once for your PostgreSQL password.
   - Click opens in your browser at http://localhost:5173.
   - Two windows stay open (the API and the App). Close them to stop Click.
3. To sign in quickly while testing, use **Login as Test Customer** on the sign-in screen.

Click is a platform that brings everyday services (food, groceries, rides, deliveries and more) into one ecosystem.

## Repository layout

```
apps/
  customer/        Customer App (React + TypeScript, Vite)       ← active
  partner/         Click Partner App (React + TypeScript, Vite)   ← phase 1: sign-in → onboarding → Partner ID → Home
  business-os/     Internal Click Business OS                     ← Phase 6 (boundary README only)
packages/
  api/             @click/api: shared typed API contract, HTTP client and session client for all apps
  ui/              @click/ui: shared UI primitives and the Click logo (each app supplies its own tokens)
  phone-auth/      @click/phone-auth: provider-neutral phone OTP sign-in (Click backend OTP) for every app
backend/           Django + DRF shared API (PostgreSQL)
docs/              Architecture notes (see docs/architecture.md)
infrastructure/    Local dev infrastructure (Postgres via docker compose)
  config/          settings (env-driven), urls
  apps/core        base models (UUID + timestamps), camelCase API contract, error envelope, permissions
  apps/users       single identity for every actor, JWT auth (refresh in httpOnly cookie)
  apps/partners    Click Partner: types/categories catalogue, partner identity, profile, location, verification, Partner ID
  apps/customers   customer profile, addresses
  apps/stores      storefronts (restaurant/grocery/retail), categories, display offers
  apps/catalog     menu categories, products
  apps/carts       server-side single-store cart
  apps/orders      transactional, idempotent order placement; status state machine + audit trail
  apps/payments    payment records for every order and booking, refunds, default method, failed/pending handling, signed provider webhooks
  apps/wishlists   saved stores/products per customer
  apps/notifications in-app inbox: grouped categories, read state, per-category preferences (essential ones can't be muted)
  apps/rewards     points ledger with expiry, tiers, campaigns, missions, achievements, reversals, atomic redemption to Wallet credit
  apps/support     Help & Support: knowledge-base articles with feedback, requests with related item, conversation and attachments
  apps/wallet      Click. Wallet: cash + promo-credit ledger, verified top-ups (provider abstraction, sandbox test mode), cashback, expiry, limits
  apps/offers      Click. Offers: one hub over every service's offers, save / claim codes, savings from real discounts
  apps/activity    Activity timeline across every service (cursor paging) and the activity event log
  apps/search      Click. Global Search: one engine over every service, suggestions, private recent searches, ID lookup
  apps/reviews     shared Reviews & Ratings layer over each service's reviews (eligibility, history, reports)
  apps/invoices    Invoice Center: invoices built from payments and their orders / bookings, refund documents
  apps/giftcards   Click. Gift Cards: designs, purchase, delivery, redemption, balance ledger, pay at checkout
  apps/discover    Discover: organic discovery sections + sponsored placement auction, budgets, tracking
  apps/pharma      Pharma: pharmacies, medicines, prescription upload and pharmacist review, refill reminders
  apps/bookings    Showtime: titles, cinemas, screens and seat layouts, showtimes, seat holds, food & drinks, offers, tickets, reviews
  apps/ai          Buddy: provider-agnostic AI layer + customer-scoped tools (basic mode by default)
  apps/buzz        Click. Buzz: actionable discovery feed built from real offers, shows and stores
  apps/rides       rides: ride types, upfront pricing, driver matching, trip lifecycle, safety, ratings
  apps/shop        Shopping marketplace: campaigns, discovery, search interpretation, reviews, delivery estimates
  apps/groceries   Groceries: category registry, canonical items, vendor delivery settings and hours, slots, buy again, lists, vendor listings API
  apps/parcels     Parcel: services, vehicles, coverage, quotes, bookings, partner matching, PIN-verified lifecycle, tracking, sharing
  apps/professionals  Services: local professionals, jobs and pricing models, availability, estimates, quotes, booking lifecycle, reviews
  apps/hotels      Hotels: destinations, properties, rooms, rates, inventory, offers, bookings, cancellation, verified reviews
  apps/travel      Travel: bus / train / flight timetables, search, seats & berths (RAC / waitlist), tickets, cancellation, fare alerts
  apps/experiences Bookings: temples, attractions, experiences (tickets, slots, darshan), entry codes, and the list of every booking
  apps/eventhub    Events: plan events, event teams/specialists/venues, packages, quotes, bookings, milestones, checklist, reviews
```

**One API, role-scoped surfaces:** `/api/v1/stores` (public), `/api/v1/auth/*` and `/api/v1/me` (shared identity),
`/api/v1/customer/*` (customers, ownership enforced in querysets), `/api/v1/partner/*` (partner resolved from the
signed-in user, never from client input). `/api/v1/os/*` comes later.

## Local development

Requirements: Python 3.12+, Node 22+, PostgreSQL 16.

```bash
# Database (or: docker compose -f infrastructure/docker-compose.yml up -d)
createuser click -P   # password: click (dev only)
createdb click -O click

# Backend API (http://localhost:4000)
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_dev_data      # DEVELOPMENT MOCK DATA + test customer (see docs/development-data.md)
python manage.py runserver

# Frontend (http://localhost:5173, proxies /api to Django)
npm install
npm run dev:customer
npm run dev:partner   # Click Partner App on http://localhost:5174 (see apps/partner/README.md)
```

## Customer sign-in

Phone OTP run by the Click backend (code generated, texted through `CLICK_SMS_PROVIDER`, verified, then Click's own
session). In development the code is printed in the API terminal. Adding the SMS provider: [docs/authentication.md](docs/authentication.md).

## Development test login

After `seed_dev_data`, use **Login as Test Customer** on the sign-in screen (development builds only), or sign in
with `+1 650 555 0101` and the code printed in the API terminal. Details: [docs/development-data.md](docs/development-data.md).

## Temporary mock data

`apps/customer/src/mock/` holds **TEMPORARY MOCK DATA** (10 restaurants with menus), typed against the real
`@click/api` contract. Turn it on with `VITE_STORES_SOURCE=mock` to review the discovery UI without the backend.
Add `?mockScenario=slow|empty|error` to the URL to see the loading, empty and error states. Components never import
mock data directly; `src/data/stores-source.ts` is the only switch. Cart, checkout and orders always use the real API.

## Tests

```bash
cd backend && . .venv/bin/activate && pytest   # needs PostgreSQL running
npm test                                       # frontend + shared package
npm run typecheck
```
