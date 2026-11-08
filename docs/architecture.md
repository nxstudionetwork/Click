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
speech-to-text extension point) · `buzz` (actionable discovery feed composed from real offers, shows and stores) ·
`rides` (ride types and rates, upfront pricing, driver matching, trip lifecycle, safety, ratings).

Food, groceries and shopping share one commerce model. A `Store` has a `store_type` (`restaurant`, `grocery`,
`retail`), and its products, cart, orders and payments are the same tables. A new commerce vertical is a new
`store_type` plus UI, not a new system. Rides, bookings and (later) deliveries have their own domains because
their lifecycles differ.

## API surfaces (`/api/v1`)

- **Public discovery:** `stores`, `stores/<slug>`, `stores/<slug>/menu`, `store-categories`, `products/<id>`, `search`, `offers`, `events`, `events/<slug>`, `shows/<id>`, `buzz`
  - `stores?lat=&lng=&radius=` returns only stores with known coordinates within `radius` km (default 10, max 50), nearest
    first, each with `distanceKm` (haversine in PostgreSQL; `null` on non-location queries). `sort=popular|rating|new|distance`.
  - `buzz?limit=` (1–30) returns `{results: [BuzzItem]}`: each item is a real offer, now-showing event or top-rated open
    store with exactly one `action {label, path}` into the matching flow. Media is the record's own image/video only.
- **Shared identity:** `auth/register|login|refresh|logout`, `me`
- **Customer:** `customer/{addresses, cart, orders, wishlist, notifications, rewards, wallet, bookings, support/tickets, assistant/messages,
  assistant/capabilities, assistant/transcribe, profile/summary,
  cart/offer (POST apply / DELETE), orders/<id>/review, recommendations/stores}`
  - Rides: `customer/rides/places?q=`, `customer/rides/quote` (POST trip → options with fares and pickup ETAs),
    `customer/rides` (GET list, POST book; idempotent), `customer/rides/<id>`, `/cancel`, `/rating`, `/safety`.
  - `stores` also accepts `veg=true`, `min_rating`, `offers=true`, `max_price` and `sort=eta|price_low|price_high`.
- **Partner sign-in:** the shared `auth/identity/exchange` (Firebase ID token verified server-side), then
  `auth/identity/partner-signup` for a newly verified phone (creates a phone-only Click account)
- **Partner:** `partner/categories` (public catalogue), `partner/me`, `partner/onboarding/{category,profile,location,submit}`
  - Drivers (transport partners): `partner/rides/offers`, `partner/rides/<id>/accept`, `partner/rides/<id>/status`,
    `partner/driver/location`.
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

## Offers, customisation and reviews

- **Offers:** a `StoreOffer` with a `discount_type` (`percent` with optional cap, `flat`, `free_delivery`) and
  `min_order_amount` can be applied to the cart (`Cart.offer`). It is re-checked on every price calculation and again
  at order placement; a lapsed offer stops placement with a reason instead of silently changing the total. Offers
  without a rule type stay display-only. Orders store `discount` and an `offer_title` snapshot.
- **Customisation:** `ProductOptionGroup` (min/max selections) → `ProductOption` (`price_delta`). Cart lines hold the
  chosen options (`options_key` keeps one line per combination); unit price = product price + option deltas, always
  read server-side. Order items snapshot `options_summary`; reorder maps names back to today's options.
- **Reviews:** `OrderReview` (one per delivered order, 1–5 + comment) updates the store's `rating_average`/`rating_count`
  in the same transaction.

## Wallet and bookings

- **Wallet:** the balance is always the sum of an append-only ledger. Writes lock the customer row, so concurrent
  payments can't overspend. Wallet payments are captured immediately, and cancelling refunds them to the wallet.
  Top-ups wait for a payment gateway; staff can issue promotional credit in Django admin.
- **Bookings:**
  - A database unique constraint stops any seat being sold twice, even under concurrent requests.
  - Placement is idempotent and prices are computed on the server.
  - Cancelling releases the seats and refunds wallet payments; it's allowed up to 2 hours before the show.

## Rides

- **Ride types** (`RideType`) hold the rates: base, per km, per minute, minimum, booking fee, per stop, and which
  vehicle types serve them. Offers (`RideOffer`) are percent or flat, with an optional cap, minimum fare and ride types.
- **Pricing** (`apps/rides/pricing.py`): distance is the straight line between points × 1.3 (road factor), labelled
  `straight_line` in quotes and shown as "estimated from your points (no live traffic)". No routing or traffic
  provider is connected yet. The fare is computed on the server and locked when the ride is booked. Trips must be
  0.3 to 60 km, with at most 2 stops.
- **Matching** (`matching.py`): eligible drivers are verified, available transport partners whose vehicle type fits,
  whose location is at most 10 minutes old and within 6 km, and who aren't on another trip. The nearest 5 get an
  offer and the first to accept gets the ride. Nobody is assigned at random. With no eligible driver the ride ends
  as `no_driver`. A driver location counts as live only if it is at most 45 seconds old; otherwise the app shows its time.
- **Lifecycle:** `scheduled → searching → driver_assigned → driver_arrived → in_progress → completed`, plus
  `cancelled` and `no_driver`. Transitions are checked against `ALLOWED_TRANSITIONS` and logged as `RideStatusEvent`s.
  Wallet rides are charged at booking and refunded on cancel or no driver; cash is recorded as captured on completion.
  Scheduled rides (30 minutes to 7 days ahead) are dispatched by `manage.py dispatch_scheduled_rides` (run it from cron).
- **Safety:** the share, SOS (opens the phone's emergency call to 112 and logs the event) and report actions are stored
  as `RideSafetyEvent`. The driver card shows first name, rating, vehicle, colour and plate. Location is visible only
  during an active trip.
- **Map:** Leaflet with configurable tiles (`VITE_MAP_TILE_URL`, `VITE_MAP_ATTRIBUTION`; default OpenStreetMap tiles
  for development only). Google Maps is not used. Place search covers saved addresses with coordinates, recent ride
  places and Click. stores. No external geocoder is connected yet.
- **Updates:** the trip page polls every 5 seconds while a ride is active (no push channel yet).

## Customer App frontend

- **Brand:** the logo is the supplied glossy app icon (`assets/Glossy Click App Logo.png`, cropped without stretching
  into `apps/customer/public/brand/`) followed by the "Click." wordmark; the period uses the logo's amber. Palette
  from `assets/Click Brand Style Guide Board.png`: blue #2F3CFF / #4F6BFF, amber #FBBF24, navy #0B1F44, white #F8FAFC.
- **Appearance:** White (default) or Dark navy, chosen in Settings (or "Match device"); stored per device and applied
  before first paint (`src/appearance.ts`, `data-appearance` on `<html>`). All colours are tokens in `styles/tokens.css`.
- **Navigation:** primary nav is Home | Ride | Food | Services | Explore (`/`, `/rides`, `/food`, `/services`, Explore sheet);
  each item carries its service colour (Services uses the Shopping indigo). Profile is reached from the header avatar.
  Shopping, Groceries and Movies are reached from Home and Explore. `/home`, `/ride`, `/shop` and
  `/profile` redirect to their routes.
- **Header rule:** the Click. header is sticky on every shell page and content starts below it. The global search bar
  appears only on Home (and `/search`); Food, Groceries and Shop have their own search; other pages have none.
- **Location rule:** the active location is chosen on Home only, from the addresses saved in Profile → Addresses
  (the selector never adds or edits them; with none saved it links to Addresses). It is stored per device
  (`click.selectedAddressId`) and used across the app: Home, store distances, delivery, and the Ride pickup.
  Other pages never show it in the header. Long addresses are truncated.
- **Themes:** each service sets its accent (`--c-theme`, `-solid`, `-soft`, `-strong`) and hero gradient through
  `data-theme` on any element. Typography, spacing, components and motion are shared.
- **Header:** Click. logo, location ("Delivering to", Home only), search (Home only) (text with recent searches and hints, voice, camera QR scan),
  Buddy (GO / MAN chooser), notifications, cart (only when it has items) and profile (links to `/account`).
- **Home (`src/pages/HomePage.tsx`):** composed from `src/features/home/*`, in order: hero (greeting with the customer's
  name), quick services (from `config/services.ts`), offers, near you, popular, discover, Buzz, recent activity,
  rewards & wallet, then time-of-day moments from `config/home.ts`. Every section has loading, empty and error states.
  "Near you" uses the selected address's saved coordinates; without them it shows the address's city and says so.
- **Explore (signed-in):** Click.'s discovery hub. The bottom (and desktop) navigation opens it as a bottom sheet (~80% of
  the screen, page behind blurred and dimmed, scrolls internally, closes on Escape/backdrop/navigation); `/explore` renders
  the same `ExploreContent` for deep links. Order: a banner that advances one step each time Explore opens (`config/explore.ts`, deterministic, remembered
  per device; only the shown banner's image loads), then every feature from `CLICK_FEATURES` (services + Activity,
  Buddy, Offers, Rewards, Wallet) sorted A–Z by name in code, then Your Click. (Wallet masked until revealed, Rewards
  points, Activity, live Offers count, all real data), Account (Payments, Settings, Help & Support, Addresses), and the
  footer "Everything you need. One Click. away." / "A venture of IFX Group". Feature tiles are compact; unlaunched
  services carry a "Soon" tag.
- **Profile (`/account`, signed-in; `/profile` redirects):** a dedicated page with its own header (no app header, search,
  location or bottom navigation). Identity from `/me`: photo (take/choose/remove via `/me/avatar`, validated and re-encoded
  server-side; the UI changes only after the server stores it), name (editable, validated on both sides), immutable
  Click. ID with copy, masked verified phone, email (read-only: email and phone changes need verification flows that
  don't exist yet). Badges (Activity, Wishlist, Rewards, Wallet masked until revealed) use
  `GET /customer/profile/summary` (counts only; detail pages load their own data). Account rows: Click. ID Card,
  Addresses, Payments, Notifications (unread count), Settings, Help & Support. Security sheet and Log out (confirmation;
  ends the Click. session server-side and clears all cached customer data). Account deletion is not offered: there is
  no backend deletion workflow yet.
- **Activity (`/activity`):** a timeline read from the source domains (orders, bookings, rides), filterable by Rides,
  Food, Groceries, Shopping and Bookings; parcels and service bookings join as those services launch.
- **Ride (`/rides`, `/rides/:id`):** map first, then pickup (starts at the active location), up to 2 stops and the
  drop, quick chips (Home, Work, Recent, Schedule, For someone), ride options with server fares and pickup ETAs,
  offers, payment (cash or wallet), then Confirm. The trip page shows status, the driver card, safety tools, the
  receipt, Ride again and a one-time rating. Ride pages are lazy-loaded so the map library loads only when needed.
- **Service pages (`/food`, `/groceries`, `/shopping`):** one pattern (`pages/ServicePage.tsx`, `features/service/*`, config in
  `config/servicePages.ts`): intro (title + fixed tagline) → horizontal categories from the API → service search
  (debounced; stores incl. menu matches + dishes/products) → filter bar (Pure veg, Rating 4.0+, Offers, Open now,
  Budget; sort Recommended/Rating/Delivery time/Price/Distance when the address has coordinates) → Offers, Nearby,
  Popular near you, Recommended for you (rule-based, each with its reason), Explore categories → All (20 per page,
  infinite scroll). Category, search and filters live in the URL.
- **Ordering:** customisation groups (size, add-ons) are chosen in the item sheet / product page; quick-add on an item
  with required choices opens the picker. A cart from another store triggers an in-app confirmation (never silently
  cleared). Checkout lists the store's applicable offers; the server validates and prices everything again at
  placement (idempotent). The order page shows the confirmation, a polled status timeline, options per line, and a
  one-time rating once delivered.
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
