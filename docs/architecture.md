# Click architecture

## Repository map

| Responsibility          | Location                                | Notes |
|-------------------------|-----------------------------------------|-------|
| Customer App            | `apps/customer`                         | React + TypeScript (Vite) |
| Partner App             | `apps/partner`                          | React + TypeScript (Vite); Firebase phone sign-in |
| Business OS             | `apps/business-os`                      | Phase 6 (internal) |
| Shared code             | `packages/api`, `packages/ui`           | `@click/api`: contract, HTTP + session client; `@click/ui`: primitives + logo |
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
- **Partner identity:** `auth/firebase` exchanges a server-verified Firebase ID token for a Click session
- **Partner:** `partner/categories` (public catalogue), `partner/me`, `partner/onboarding/{category,profile,location,submit}`
- **Business OS:** `os/*` (Phase 6)

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

## Click Partner identity

- **Phone identity:** Firebase Authentication verifies the phone number. Django verifies the Firebase ID token
  (Google public keys, `aud`/`iss` for `FIREBASE_PROJECT_ID`, phone provider) and links it through
  `users.AuthIdentity(provider="firebase", subject=<Firebase UID>)`. The UID, not the phone number, is the key, and
  phone-only users have no email or password. No Firebase service-account key is used.
- **Partner model:** `PartnerType` → `PartnerCategory` (catalogue with JSON configuration) · `Partner` (UUID PK,
  public `partner_code`) · `PartnerMembership` (user ↔ partner, owner today, staff later; one owned partner per user) ·
  `PartnerProfile` (contact + category-specific `details`) · `PartnerAddress` · `PartnerVerification` ·
  `PartnerStatusEvent` (audit).
- **Partner ID:** `CLK-PT-000001`, from the `partners_partner_code_seq` PostgreSQL sequence, assigned once at
  submission and never changed or reused.
- **Status:** `draft → profile_completed → verification_pending → verified → active`, plus `rejected`, `suspended`,
  `inactive`. Transitions are explicit and audited. Only staff review (Django admin today) can mark a partner verified.
- **Isolation:** no partner endpoint accepts a partner ID; every request resolves the partner from the signed-in
  user's owner membership.
- **Category configuration:** `apps/partners/catalog.py` defines fields, location options and Home modules per
  type, with category overrides. The API serves the resolved configuration, and the server validates profile
  details against it.
