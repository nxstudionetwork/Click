# Click architecture

## Repository map

| Responsibility          | Location                                | Notes |
|-------------------------|-----------------------------------------|-------|
| Customer App            | `apps/customer`                         | React + TypeScript (Vite) |
| Partner App             | `apps/partner`                          | Phase 5 |
| Business OS             | `apps/business-os`                      | Phase 6 (internal) |
| Shared code             | `packages/api`                          | `@click/api`: typed API contract + HTTP client for all apps |
| Backend                 | `backend/`                              | Django + DRF, one shared API |
| Database                | PostgreSQL; migrations in `backend/apps/*/migrations` | Django owns the schema |
| Infrastructure          | `infrastructure/`                       | Local dev compose; deployment config later |
| Docs                    | `docs/`                                 | |

Folder names use the `apps/` and `packages/` workspace convention, not names with spaces, so npm workspaces,
TypeScript and CI tooling work without quoting.

## Backend domains (`backend/apps`)

`core` (base models, API contract, errors, permissions) · `users` (identity, auth) · `customers` (profiles,
addresses) · `stores` (storefronts of every vertical, categories, offers) · `catalog` (sections, products,
inventory, search) · `carts` · `orders` (placement, state machine, reorder) · `payments` · `wishlists` ·
`notifications` · `rewards` (points ledger) · `support` (tickets) · `wallet` (append-only money ledger) ·
`bookings` (venues, events, shows, seat-safe bookings) · `ai` (Buddy: provider-agnostic AI layer + customer-scoped tools).

Food, groceries and shopping share one commerce model. A `Store` has a `store_type` (`restaurant`, `grocery`,
`retail`), and its products, cart, orders and payments are the same tables. A new commerce vertical is a new
`store_type` plus UI, not a new system. Rides, deliveries, tickets and bookings get their own domains when they
launch, because their lifecycles differ.

## API surfaces (`/api/v1`)

- **Public discovery:** `stores`, `stores/<slug>`, `stores/<slug>/menu`, `store-categories`, `products/<id>`, `search`, `offers`, `events`, `events/<slug>`, `shows/<id>`
- **Shared identity:** `auth/register|login|refresh|logout`, `me`
- **Customer:** `customer/{addresses, cart, orders, wishlist, notifications, rewards, wallet, bookings, support/tickets, assistant/messages}`
- **Partner:** `partner/*` (Phase 5) · **Business OS:** `os/*` (Phase 6)

Rules:
- JSON is camelCase.
- Every error has the shape `{error: {code, message, details}}`.
- Money values are decimal strings.

## Data ownership

Every customer endpoint uses `IsCustomer` and scopes its queryset to `request.user.customer_profile`, so other
customers' records return 404. Ownership is tested for addresses, cart items, orders, wishlist, notifications
and support tickets. Frontend route guards are UX only.

## Commerce integrity

- **Server-computed totals:** prices are recomputed on the server at placement, and orders snapshot item names,
  prices and the delivery address.
- **Idempotent placement:** placing an order is idempotent per client key and serialized per customer by locking
  the cart row.
- **Inventory:** stock is reserved with a conditional atomic decrement (it cannot oversell) and restocked on
  cancellation.
- **Status changes:** order status follows an explicit transition table, and every change writes an audit event
  and a notification.
- **Rewards:** points are an append-only ledger with one earn per delivered order, and the balance is derived
  from the ledger.

## Development ports

- **Backend API:** `python manage.py runserver` serves on **port 4000** (`CLICK_DEV_PORT`).
- **Customer App:** `npm run dev:customer` serves on 5173. It proxies `/api` to port 4000 (override with `CLICK_API_PROXY`).
- **API base URL:** the frontend reads it from one place, `VITE_API_BASE_URL` (default `/api/v1`).

## Wallet and bookings

- **Wallet:** the balance is always the sum of an append-only ledger. Writes lock the customer row, so concurrent
  payments can't overspend. Wallet payments are captured immediately, and cancelling refunds them to the wallet.
  Top-ups wait for a payment gateway; staff can issue promotional credit in Django admin.
- **Bookings:**
  - A database unique constraint stops any seat being sold twice, even under concurrent requests.
  - Placement is idempotent and prices are computed on the server.
  - Cancelling releases the seats and refunds wallet payments; it's allowed up to 2 hours before the show.

## Customer App frontend

- **Navigation:** primary nav is Home | Ride | Food | Services | Menu. Menu opens a bottom-up hub driven by
  `apps/customer/src/config/services.ts`, which lists every service with its status, group and theme.
- **Themes:** each service sets its own accent colours and hero gradient through `data-theme`. Typography,
  spacing, components and motion are shared.
- **Header:** a location selector, global search (text, voice, camera, Ask Buddy), Buddy, notifications, cart
  and a profile menu.

## AI

`apps/ai/providers.py` defines the provider interface, and `CLICK_AI_PROVIDER` selects an implementation.

- **Default provider:** Buddy basic mode (`apps/ai/buddy.py`), a deterministic intent engine. It answers only
  through `apps/ai/tools.py`: read-only, customer-scoped functions over real data. Replies are structured as
  `{message, cards, actions}`.
- **Payments:** Buddy never places orders or payments.
- **Voice and camera search:** these need an approved speech or vision provider. Browser speech APIs send audio to
  third-party clouds such as Google's, so they aren't used. The backend builds context per surface with permission
filters; clients never supply it. Google Cloud, Gemini, Vertex AI and AI Studio are intentionally not used.
