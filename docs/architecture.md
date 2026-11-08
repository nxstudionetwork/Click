# Click architecture

## Repository map

| Responsibility          | Location                                | Notes |
|-------------------------|-----------------------------------------|-------|
| Customer App            | `apps/customer`                         | React + TypeScript (Vite) |
| Partner App             | `apps/partner`                          | React + TypeScript (Vite); Firebase phone sign-in |
| Business OS             | `apps/business-os`                      | Phase 6 (internal) |
| Shared code             | `packages/api`, `packages/ui`, `packages/phone-auth` | `@click/api`: contract, HTTP + session client; `@click/ui`: primitives + logo; `@click/phone-auth`: phone OTP adapter |
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
`bookings` (venues, events, shows, seat-safe bookings) · `ai` (Buddy: provider-agnostic AI layer + customer-scoped tools,
speech-to-text extension point) · `buzz` (actionable discovery feed composed from real offers, shows and stores).

Food, groceries and shopping share one commerce model. A `Store` has a `store_type` (`restaurant`, `grocery`,
`retail`), and its products, cart, orders and payments are the same tables. A new commerce vertical is a new
`store_type` plus UI, not a new system. Rides, deliveries, tickets and bookings get their own domains when they
launch, because their lifecycles differ.

## API surfaces (`/api/v1`)

- **Public discovery:** `stores`, `stores/<slug>`, `stores/<slug>/menu`, `store-categories`, `products/<id>`, `search`, `offers`, `events`, `events/<slug>`, `shows/<id>`, `buzz`
  - `stores?lat=&lng=&radius=` returns only stores with known coordinates within `radius` km (default 10, max 50), nearest
    first, each with `distanceKm` (haversine in PostgreSQL; `null` on non-location queries). `sort=popular|rating|new|distance`.
  - `buzz?limit=` (1–30) returns `{results: [BuzzItem]}`: each item is a real offer, now-showing event or top-rated open
    store with exactly one `action {label, path}` into the matching flow. Media is the record's own image/video only.
- **Shared identity:** `auth/register|login|refresh|logout`, `me`
- **Customer:** `customer/{addresses, cart, orders, wishlist, notifications, rewards, wallet, bookings, support/tickets, assistant/messages,
  assistant/capabilities, assistant/transcribe}`
- **Partner sign-in:** the shared `auth/identity/exchange` (Firebase ID token verified server-side), then
  `auth/identity/partner-signup` for a newly verified phone (creates a phone-only Click account)
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

- **Brand:** the logo is the supplied glossy app icon (`assets/Glossy Click App Logo.png`, cropped without stretching
  into `apps/customer/public/brand/`) followed by the "Click." wordmark; the period uses the logo's amber. Palette
  from `assets/Click Brand Style Guide Board.png`: blue #2F3CFF / #4F6BFF, amber #FBBF24, navy #0B1F44, white #F8FAFC.
- **Appearance:** White (default) or Dark navy, chosen in Settings (or "Match device"); stored per device and applied
  before first paint (`src/appearance.ts`, `data-appearance` on `<html>`). All colours are tokens in `styles/tokens.css`.
- **Navigation:** primary nav is Home | Ride | Food | Explore | Profile (`/`, `/rides`, `/food`, `/explore`, `/account`);
  each item carries its service colour. `/home`, `/ride` and `/profile` redirect to those routes.
- **Themes:** each service sets its accent (`--c-theme`, `-solid`, `-soft`, `-strong`) and hero gradient through
  `data-theme` on any element. Typography, spacing, components and motion are shared.
- **Header:** Click. logo, location ("Delivering to"), search (text with recent searches and hints, voice, camera QR scan),
  Buddy (GO / MAN chooser), notifications, cart (only when it has items) and profile (links to `/account`).
- **Home (`src/pages/HomePage.tsx`):** composed from `src/features/home/*`, in order: hero (greeting with the customer's
  name), quick services (from `config/services.ts`), offers, near you, popular, discover, Buzz, recent activity,
  rewards & wallet, then time-of-day moments from `config/home.ts`. Every section has loading, empty and error states.
  "Near you" uses the selected address's saved coordinates; without them it shows the address's city and says so.
- **Buzz:** `/buzz` is a full-screen vertical feed (own layout), plus a Home preview and a persistent edge handle.
- **Buddy:** GO = voice-first action mode (records only when the server reports a speech provider; otherwise says so
  and accepts typing), MAN = `/buddy`, the full conversation page with its own header (New chat, Home).
- **Imagery:** real photographs only. Service photos (`config/media.ts`) illustrate a category; a store without its own
  photo gets a branded gradient, never a borrowed stock photo.

## AI

`apps/ai/providers.py` defines the provider interface, and `CLICK_AI_PROVIDER` selects an implementation.

- **Default provider:** Buddy basic mode (`apps/ai/buddy.py`), a deterministic intent engine. It answers only
  through `apps/ai/tools.py`: read-only, customer-scoped functions over real data. Replies are structured as
  `{message, cards, actions}`.
- **Payments:** Buddy never places orders or payments.
- **Voice:** `CLICK_SPEECH_PROVIDER` (dotted path to an `apps.ai.speech.SpeechProvider`) enables
  `customer/assistant/transcribe`; it is empty by default, so `capabilities.voice` is false and the app does not record.
  Browser speech APIs send audio to third-party clouds such as Google's, so they aren't used.
- **Camera:** QR codes are scanned on the device (BarcodeDetector) and Click. links open in-app. Image recognition
  needs `CLICK_VISION_PROVIDER` and is not claimed until one is approved. The backend builds context per surface with permission
filters; clients never supply it. Google Cloud, Gemini, Vertex AI and AI Studio are intentionally not used.

## Click Partner identity

- **Phone identity:** the same identity layer as customers (`apps/identity`, see `docs/authentication.md`): Firebase
  verifies the phone, Django verifies the ID token, and `ExternalIdentity(provider, subject=<Firebase UID>)` links it to
  one Click user. A new phone gets a phone-only user (no email or password); a phone already verified on a customer
  account maps to that same person, so one human is never two users. No Firebase service-account key is used.
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
