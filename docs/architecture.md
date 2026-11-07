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
`notifications` · `rewards` (points ledger) · `support` (tickets) · `ai` (provider-agnostic AI layer).

Food, groceries and shopping share one commerce model. A `Store` has a `store_type` (`restaurant`, `grocery`,
`retail`), and its products, cart, orders and payments are the same tables. A new commerce vertical is a new
`store_type` plus UI, not a new system. Rides, deliveries, tickets and bookings get their own domains when they
launch, because their lifecycles differ.

## API surfaces (`/api/v1`)

- **Public discovery:** `stores`, `stores/<slug>`, `stores/<slug>/menu`, `store-categories`, `products/<id>`, `search`, `offers`
- **Shared identity:** `auth/register|login|refresh|logout`, `me`
- **Customer:** `customer/{addresses, cart, orders, wishlist, notifications, rewards, support/tickets, assistant/messages}`
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

## AI

`apps/ai/providers.py` defines the provider interface. `CLICK_AI_PROVIDER` selects an implementation, and none is
configured by default (the API returns `ai_unavailable`). The backend builds context per surface with permission
filters; clients never supply it. Google Cloud, Gemini, Vertex AI and AI Studio are intentionally not used.
