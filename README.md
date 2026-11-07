# Click

Click is a platform that brings everyday services (food, groceries, rides, deliveries and more) into one ecosystem.

## Repository layout

```
apps/
  customer/        React + TypeScript Customer App (Vite)        ← active (Phase 2)
  partner/         Partner App                                    ← Phase 5
  business-os/     Internal Click Business OS                     ← Phase 6
packages/
  api/             @click/api: shared typed API contract + HTTP client for all apps
backend/           Django + DRF shared API (PostgreSQL)
  config/          settings (env-driven), urls
  apps/core        base models (UUID + timestamps), camelCase API contract, error envelope, permissions
  apps/users       single identity for every actor, JWT auth (refresh in httpOnly cookie)
  apps/customers   customer profile, addresses
  apps/stores      storefronts (restaurant/grocery/retail), categories, display offers
  apps/catalog     menu categories, products
  apps/carts       server-side single-store cart
  apps/orders      transactional, idempotent order placement; status state machine + audit trail
  apps/payments    payment records (cash on delivery today; gateways plug in later)
```

**One API, role-scoped surfaces:** `/api/v1/stores` (public), `/api/v1/auth/*` and `/api/v1/me` (shared identity),
`/api/v1/customer/*` (customers, ownership enforced in querysets). `/api/v1/partner/*` and `/api/v1/os/*` come later.

## Local development

Requirements: Python 3.12+, Node 22+, PostgreSQL 16.

```bash
# Database
createuser click -P   # password: click (dev only)
createdb click -O click

# Backend (http://localhost:8000)
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_dev_data      # 10 development restaurants with menus
python manage.py runserver

# Frontend (http://localhost:5173, proxies /api to Django)
npm install
npm run dev:customer
```

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
