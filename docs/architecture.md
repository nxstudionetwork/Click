# Click architecture

## Repository map

| Responsibility          | Location                                | Notes |
|-------------------------|-----------------------------------------|-------|
| Customer App            | `apps/customer`                         | React + TypeScript (Vite) |
| Partner App             | `apps/partner`                          | React + TypeScript (Vite); Click phone OTP sign-in |
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
- **Partner sign-in:** Click phone OTP and the shared `auth/identity/exchange` (code verified server-side), then
  `auth/identity/partner-signup` for a newly verified phone (creates a phone-only Click account)
- **Partner:** `partner/categories` (public catalogue), `partner/me`, `partner/onboarding/{category,profile,location,submit}`
  - Drivers (transport partners): `partner/rides/offers`, `partner/rides/<id>/accept`, `partner/rides/<id>/decline`,
    `partner/rides/<id>/status`, `partner/driver/location`.
  - Partner Home: `partner/home` (whole dashboard, sections fail independently), `partner/availability`,
    `partner/work?view=`, `partner/work/<kind>/<id>/<action>`, `partner/earnings?days=7|30`,
    `partner/notifications` (+ `/read-all`, `/<id>/read`). `partner/dev-login` exists only with DEBUG.
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

- **Wallet:** the balance is always the sum of an append-only ledger, in two buckets.
  - *Cash* (money added, refunds of cash) and *promo credit* (promotional credit, cashback, rewards conversions). Promo
    credits are lots with an expiry; payments spend promo first, soonest-expiring first, then cash. Expired remainders
    are written off by `sweep_expired` as "Credit expired" lines. Refunds return each part to the bucket it came from.
  - Every write locks the customer row, so concurrent payments can't overspend; constraints stop a payment being
    debited twice or a source (cashback, reward, top-up) being credited twice.
  - **Adding money** goes amount → method → review → payment provider → server verification → credit. The intent never
    credits; only a provider event whose HMAC signature verifies (`X-Click-Signature`, `POST /payments/webhooks/<provider>`)
    does, once (`apply_provider_result` is idempotent). Limits (per top-up, day, month, maximum balance) come from settings.
    The only provider today is a **sandbox test mode** (on when `CLICK_PAYMENT_SANDBOX`, default DEBUG); in production
    without a provider, adding money is shown as unavailable.
  - Account states (active / restricted / locked / suspended / closed) pause adding money and paying; the balance stays visible.
  - No withdrawal, peer-to-peer transfer or split wallet + card payment: the API reports `partialPayment: false`.
- **Payments** (`/customer/payments`): every payment record the customer owns (orders, rides, parcels, services, shows,
  events, hotels, travel, bookings, wallet top-ups) with filters, search, detail (breakdown, wallet movements, refunds,
  retry on the booking that owns it) and a default method stored on the server. Cash on delivery is captured when the
  order is delivered; unpaid cash / pay-at-venue rows show as "pay later", never as stuck.
- **Rewards:** points ledger with FIFO lots and expiry; tiers from `CLICK_REWARD_TIERS` measured on 365-day points;
  campaign multipliers; missions measured from real orders and bookings and awarded once (`mission:<code>`);
  redemption deducts points and issues a promo Wallet credit in one transaction (idempotency key per tap); refunds
  reverse the points they earned.
- **Offers** (`/offers/hub`): aggregates store, hotel, show, service, ride, travel, experience, cashback and points
  offers into one shape. Badges and "best value" come from stated rules. Claimed codes are suggested at the Hotels,
  Travel and Bookings checkouts; each service still validates the code.
- **Notifications vs Activity:** notifications are what Click. told the customer (grouped, read state, mutable
  non-essential categories); Activity (`/customer/activity`) is what the customer did, read from each service's own
  records with a cursor that stays correct under search and status filters.
- **Help & Support:** articles (data migration from `apps/support/articles.py`) with feedback; requests carry one
  related record the customer owns (checked server-side), get an urgency-based priority, are rate limited and
  duplicate-safe, and hold a conversation with attachments (JPEG / PNG / WebP / PDF up to 5 MB, checked by content).
  A support reply (`SupportMessage` with sender "support", from Django admin today) notifies the customer.
- **Scheduled jobs needed in production:** `wallet.sweep_expired` / `remind_expiring`, `wallet.expire_topups`,
  `rewards.sweep_expired`.
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

## Shopping (marketplace)

- **Listings:** retail `Store`s are sellers; a `Product` with a `shop_category` (two-level `ShopCategory` tree) is a
  marketplace listing. Brands (`Brand`), specs as category `AttributeDefinition`s with per-product
  `ProductAttributeValue`s (no per-category columns), purchasable `ProductVariant`s (size/colour, own price and stock),
  a photo gallery (`ProductImage`: uploads re-encoded to 320/640/1280 px WebP in media storage, never in PostgreSQL),
  time-boxed `ProductDeal`s (optionally limited by quantity) and policies (return window, replacement-only, warranty, COD).
- **Pricing:** `apps/catalog/pricing.py` is the only place a price is decided (variant price, active deal, genuine
  compare-at reference). Cards, product page, cart and order lines all use it.
- **Cart:** one Click. cart with two modes. `store` (food/groceries) holds one store; `marketplace` (Shopping) holds any
  number of sellers, priced per seller (delivery fee, free-delivery threshold, tax, that seller's offer). Mixing the
  two asks the customer first (`cart_store_conflict`).
- **Checkout:** `POST /customer/checkout` turns a marketplace cart into one order per seller under a `CheckoutGroup`, in
  one transaction (stock per variant, deal quantity, cash-on-delivery eligibility, wallet balance), idempotent per key.
  Retail orders move `placed → confirmed → packed → shipped → out_for_delivery → delivered`.
- **Delivery estimate:** rule-based (seller dispatch days + distance band), always shown as a date range and labelled an
  estimate. No courier is connected yet.
- **Returns:** `ReturnRequest` per delivered item within its snapshotted window; staff approve in admin (refund of the
  paid share to the Click Wallet, or a replacement).
- **Reviews:** `shop.ProductReview`, verified purchases only (delivered order), one per customer, editable; moderation
  hides without deleting; product rating is recomputed from published reviews.
- **Discovery:** `GET /shop/home` returns only sections with real content (deals, Just for You from the customer's own
  views/wishlist/purchases, trending from 7-day activity and orders, best sellers from units sold, configurable price
  bands `CLICK_SHOP_PRICE_BANDS`, new arrivals, brands, buy again). `/shop/feed` is cursor-paginated.
- **Search:** `apps/shop/query.py` interprets natural language (price, colour, brand, category word, gift/age) and
  reports only what it understood; filters/facets come from the category's attributes and variant options; trigram
  indexes (`pg_trgm`) back name search and "Did you mean". Buddy uses the same search.
- **Image search:** behind `CLICK_VISION_PROVIDER` (`apps/shop/vision.py`); with none configured the camera button is
  hidden and `/shop/visual-search` returns 503.

## Showtime (cinema and live shows)

Customer-facing name: **Showtime** (`/showtime`; old `/movies` and `/bookings` links redirect). It extends the
bookings domain (`apps/bookings`); nothing was rebuilt.

- **Records:** `Event` (a title: film or live show, with poster/backdrop/trailer URLs and a licence credit),
  `Credit` (cast & crew), `Venue` (coordinates, facilities) with `Screen`s (the real seat layout as JSON: rows front to
  back, tiers such as Classic/Prime/Recliner, aisles, accessible and out-of-service seats, supported formats, sound),
  `Show` (one showtime on a screen with `tier_prices`; legacy rows x seats still work), `ConcessionItem` (a venue's food
  & drinks), `ShowOffer`, `ShowFeature` (editorial hero with priority and date window), `ShowReview`, `ShowInterest`.
- **Booking flow:** seats -> `SeatHold` (8 minutes; `HeldSeat` unique per show seat; expired holds are released under
  the show's row lock) -> quote -> book from the hold (`BookedSeat` unique while active) -> payment (pay at venue or
  Click Wallet). The server re-validates seats, hold, food & drinks (that venue's, available), offer rules (dates,
  venue/title, minimum seats/amount, payment method) and prices; idempotent per key. A wallet shortfall rolls back and
  the hold survives for a retry.
- **Bill:** tickets + ₹20/seat convenience fee + food & drinks + tax (service-fee tax on the fee, `CLICK_TAX_RATE` on
  food) - offer discount (on tickets).
- **Tickets:** a signed code (`django.core.signing`) shown as a QR; venues verify it with
  `POST /partner/tickets/verify` (only the partner operating that venue, around show time; first scan checks in).
  Cancellation up to 2 hours before; wallet payments are refunded; the terms are shown before confirming.
- **Discovery:** `GET /showtime/home?lat&lng` (featured, highlights, tonight, now showing, coming soon, trending from
  7-day bookings/interest/views, top rated once 3+ reviews exist, trailers, live shows, cinemas by distance, special
  formats, offers; sections only with content). `/showtime/search` interprets language, genre, format, "tonight /
  today / tomorrow / this weekend", "near me", cast/crew and cinema names, and reports what it understood.
  `/showtime/titles/<slug>?date&format&language&lat&lng` loads one day of showtimes at a time, nearest cinema first.
- **Reviews and ratings:** only from customers whose booking's show has started; one per title; moderation hides.
  Titles show a rating only from `RATING_MIN` (3) reviews.
- **Interest:** "I'm interested" is stored; a `post_save` signal on new showtimes notifies followers once when booking
  opens.
- **Dates:** customer-facing days use `CLICK_LOCAL_TIMEZONE` (Asia/Kolkata); the server stays on UTC.
- **Across Click.:** Buddy uses the same search interpretation (it never books); Buzz shows trailers and titles that
  open the title page; the ticket offers a ride to the cinema (Ride's place search includes venues) and restaurants
  near the cinema; bookings appear in Activity and My Tickets (`/tickets`).

## Groceries (local vendor marketplace)

Customer-facing name: **Groceries** (`/groceries`). Built on the shared records (`apps/groceries` adds only what
groceries need): a vendor's storefront is a `stores.Store` (type grocery), each listing is a `catalog.Product` owned by
exactly one store with its own price, MRP, stock, availability and freshness date, the cart is the shared cart and
orders are the shared orders (same status machine, payments, notifications, Activity, Partner workspace).

- **Records:** `GroceryCategory` (registry with merchandising order, section, icon, search synonyms), `GroceryItem`
  (the canonical product: name, brand, pack size and unit; `Product.grocery_item` links each store's listing to it, which
  is what makes same-item same-size price comparison possible), `GroceryStoreSettings` (delivery radius, base km and
  per-km fee, prep minutes, pace, capacity, fast/standard/scheduled modes, slot length/capacity), `StoreHours`,
  `GroceryOrderDetails` (delivery mode, slot, substitution preference, distance, estimate), `StockAlert` ("notify me",
  sent once by a signal), `ShoppingList` / `ShoppingListItem`.
- **Basket:** cart mode `basket` holds items from several grocery stores; checkout makes one order per store under a
  `CheckoutGroup`, all in one transaction (any store's failure creates nothing). Each store's part has its own minimum
  order, delivery mode and fee. Food, Shopping and Groceries never share a cart (switching asks first).
- **Delivery (`apps/groceries/delivery.py`):** store status (open / closing soon / closed / temporarily unavailable)
  from hours and the partner's availability; distance from the customer's saved address pin; fee = store base fee
  (waived above its free-delivery threshold) + per-km beyond the base distance + fast surcharge; estimate = packing time +
  distance x pace + a queue allowance when the store is busy (labelled as an estimate; no live rider tracking exists).
  Scheduled slots come from opening hours and per-slot capacity (counted from orders; the store row is locked at
  checkout). An address without a map pin gets no time promise and no fast delivery.
- **Checkout checks (server):** live price vs the price the customer saw (`CartItem.price_seen`; a change must be
  acknowledged), stock (taken atomically at placement, restored on cancellation), store status, delivery mode and slot,
  minimum order, offer rules, payment (cash on delivery or Click Wallet), idempotency.
- **Discovery:** `GET /groceries/home` (stores near you, categories with stock, fresh / essentials / dairy / snacks /
  home / personal / more sections, deals, fast stores, Support Local, buy again, running low), `/groceries/search`
  (products grouped one card per item with the best nearby listing, stores, brands, categories, filters and sorts),
  `/groceries/stores/<slug>` (+ `/products`), `/groceries/products/<id>` (compare the same pack across stores,
  frequently bought together from 3+ real orders, similar items). Badges only from rules: Local Store (independent),
  Verified Vendor (verified by Click), Popular Near You (5+ orders in 30 days, top 3), Fresh Today (stock received today).
- **Personal:** buy again and "running low" (an item in 3+ delivered orders whose usual gap has passed; phrased as
  "you may be ready to reorder") from delivered orders only; reorder adds at today's prices and reports changes.
- **Shopping list:** "Find everything" matches each line to in-stock listings at stores that deliver to the customer
  and ranks stores by coverage, then total incl. delivery, then time and distance; a split plan when no single store has
  everything. Nothing is added to the basket until the customer chooses.
- **Vendors:** `GET/PATCH /partner/grocery/listings[/<id>]` lets a partner change price, MRP, stock, availability and
  received date only for storefronts it operates (others are 404); orders move through the shared Partner workspace.
- **Across Click.:** Buddy finds items, compares the same pack, lists open stores, shows buy-again and turns "I need milk
  and bread" into a shopping list link (it never adds to the basket or orders); Buzz shows produce a store received
  today and grocery offers.

## Parcel (local pickup and drop)

Customer-facing name: **Parcel** (`/parcels`; tracking pages `/parcels/<id>`, shared links `/track/<token>`). `apps/parcels`
reuses partners (delivery riders and Parcel & Logistics partners), their reported locations (`rides.DriverLocation`),
the route estimate of Click. Ride, payments (wallet / cash to the partner at pickup), notifications, support tickets
and Activity.

- **Configuration (admin / Business OS):** `ParcelServiceArea` (where Parcel operates), `ParcelService` (Express,
  Same Day, Standard, Scheduled: hours, cut-offs, delivery windows, max distance, stops, cash, cancellation fee, which
  vehicles), `ParcelVehicle` (capacity in kg and cm, base / per-km / minimum / per-stop rates, speed),
  `ParcelCategory` (what's inside; restricted categories can't be booked), `ParcelRule` (package rules and
  not-accepted items shown before booking).
- **Booking:** `POST /customer/parcels/quote` prices every vehicle under a service from these records (base, distance,
  service fee, stops, tax; straight-line route estimate, labelled). `POST /customer/parcels` re-prices and must match the
  total the customer saw (`price_changed` otherwise), checks coverage, package rules, vehicle capacity, contacts, the
  contents declaration and the payment method, and is idempotent. Store pickup takes the pickup point from the store's
  Click. listing. Express is offered only when an eligible partner is online nearby.
- **Lifecycle:** scheduled → searching → assigned → at pickup → picked up → in transit → near destination → delivered
  (or cancelled / failed / no partner), validated server-side under a row lock with a `ParcelStatusEvent` per step and a
  notification each time. Pickup and delivery are confirmed only with the 4-digit PINs the customer holds (never sent to
  the Partner App); each check creates a `ParcelProof` with the time and the partner's last reported position. Cash is
  marked collected at the PIN-verified pickup.
- **Matching:** jobs are offered (never assigned) to verified, available partners with a fresh location, a matching
  vehicle type, within range and not on another delivery; they appear in the partner's Home (the `parcels` workspace)
  and become assigned only when accepted.
- **Cancellation:** free while scheduled or searching; after assignment and before pickup the service's fee is kept
  from wallet payments and the rest refunded; not possible after pickup (support instead).
- **Tracking & privacy:** owner-only (others get 404, including `/customer/parcels/track?ref=`); the partner's position
  is shown only when their app reported it recently ("Live" within 45 s). Share links are signed, expire in 7 days and
  show status only (no phones, PINs, prices or exact addresses).
- **Across Click.:** Buddy prepares a booking (mode, saved recipient) and reports real status but never books or pays;
  parcels appear in Activity; help requests link to the parcel (`SupportTicket.parcel`).

## Services (local professionals)

Customer-facing name: **Services** (`/services`, `/services/:category`, `/services/pro/:id`, `/services/book`,
`/services/bookings/:id`). `apps/professionals` turns Partner App partners in the service categories (plumber,
electrician, cleaner…) into bookable professionals and reuses addresses, payments (wallet / cash), notifications,
wishlists (My Professionals), support tickets, Activity and the Partner App workspace framework.

- **Catalog (admin / Business OS):** `ServiceCategory` (group, icon, accent, synonyms for search, which partner
  categories do it) and `ServiceJob` (common jobs with a pricing model — fixed, starting price, hourly with a minimum,
  or quote after inspection with an optional visit fee — duration, includes / not included, now and/or scheduled).
- **Professionals:** `ProviderProfile` (one per partner: their own photo or a monogram, about, experience, skills,
  languages, quote jobs, listed), the services they do, their own price per job, weekly hours, certificates (shown once
  verified) and portfolio photos (EXIF stripped, resized). "Verified" means an approved partner verification. Ratings,
  jobs completed and response / completion rates come only from bookings (rates appear after 5 data points).
- **Availability:** "available now" needs the partner's online toggle, instant jobs enabled, being inside working hours
  and not on a job; slots are 60-minute starts inside working hours, from 90 minutes ahead, 7 days, without overlap.
- **Booking:** `POST /customer/services/estimate` computes price, offer, 18% tax, who can take it and free slots
  (for "any available", the union of eligible professionals' slots). `POST /customer/services/bookings` re-estimates and
  must match the amount the customer saw (`price_changed`), is idempotent and attaches up to 5 of the customer's own
  photos. A named professional gets the request; otherwise up to 5 eligible ones are offered it and the first to accept
  wins. Offers expire (10 min for now, up to 2 h for scheduled) and the booking closes as unassigned, uncharged.
- **Lifecycle:** requested → confirmed → on the way → arrived → (quote pending) → in progress → completed → paid, or
  cancelled / unassigned, validated under a row lock with a status event and a notification each time. Work can't start
  before arrival or while a quote waits; quote jobs need an approved quote; a higher price on a starting-price job
  needs the customer's approval (declining keeps the booked price; declining an inspection-only quote charges only the
  visit fee); hourly jobs are never billed beyond the booked hours unless a quote was approved.
- **Payment:** after completion only — wallet (captured immediately) or cash (closed when the professional confirms
  receipt). Cancellation is free until the professional is on the way; after that, support.
- **Reviews:** one per paid/completed booking, overall plus quality, behaviour and timeliness; only booked customers.
- **Across Click.:** Buddy maps a problem ("my kitchen tap is leaking") to a service and job and lists real professionals
  with real availability and pricing, but never books or pays; "Can't find your service?" stores a `ServiceNeed` for
  Click.'s team; the Partner App Home for service categories uses the `services` workspace (requests, active jobs,
  quote, start, complete, cash received).

## Events (plan events, find teams and venues)

Customer-facing name: **Events** (`/events`, `/events/plan`, `/events/plans/:id`, `/events/teams`, `/events/venues`,
`/events/providers/:id`, `/events/book`, `/events/bookings/:id`, `/events/mine`), registered in Explore through the central
service registry (`config/services.ts`, id `events`, theme `events`). API: `/api/v1/eventhub/...` (public),
`/api/v1/customer/eventhub/...`, `/api/v1/partner/eventhub/...` — `/api/v1/events` stays Click. Showtime's.

- **Attending events is Showtime.** Events lists Showtime's live events with bookable shows (venue, date, lowest ticket
  price, distance) and links to them; tickets, seats and payments stay in Showtime. The "Live Shows" Explore entry stays.
- **Registries (admin / Business OS):** `EventType` (group, icon, accent, synonyms, suggested services, checklist template,
  shown in the planner) and `EventService` (Decoration, Catering, Photography…).
- **Providers:** `EventProvider` is a Partner in an event category — event team, specialist or venue (`VenueDetails`:
  capacity, spaces, amenities, rules, parking, catering policy, hours). Listing/featuring is a Business OS decision. The
  provider's own logo/cover/portfolio uploads only (monogram otherwise); service area (base + radius), guest range, notice,
  events per day, FAQs and cancellation terms. Ratings, events completed and "usually quotes within" (median of 3+ answered
  requests) come only from bookings, reviews and enquiries. Availability on a date = blocked dates + notice + bookings.
- **Packages:** `EventPackage` (+ `PackageAddon`): fixed or per-guest price, guest range, duration, inclusions, terms.
- **Plan → quote → book:** `EventPlan` (type, date or flexible, a saved address, guests, optional budget, services,
  requirements, reference photos, checklist). Matching teams fit the services, area, guests, event type and date. A plan
  goes to up to 5 providers at a time (`Enquiry`); providers answer in the Partner App `events` workspace (text quote) or
  the itemised quote endpoint (`Quote`, versioned, optional items, validity, terms); the customer accepts (→ booking),
  rejects, asks for changes (→ revised quote) or messages (`Message`, kept on Click., no phone numbers).
- **Booking & payment:** `EventBooking` from the customer's quote or a package, re-priced on the server and matched
  against the total they saw (`price_changed`), idempotent, provider row-locked so a day isn't double-booked. Paid through
  the shared Payment/Click. Wallet now (confirmed) or held and paid later (released automatically 2 days before the event).
  Lifecycle: payment pending → confirmed → team preparing → in progress (event day only) → completed, or cancelled; each
  step has a `StatusEvent` and a notification. `Milestone`s (services confirmed, guest count, payment, event day) are ticked
  by the provider; the plan checklist ticks itself when a booking covers a service.
- **Cancellation & refunds:** by the provider's terms — full refund to the wallet up to N days before, a % kept after;
  within 2 days, support. **Reviews:** completed bookings only, once, with quality/communication/value; shown as verified.
- **Across Click.:** favourites are shared Wishlist rows (event teams/venues and packages); help tickets link to the
  booking (`SupportTicket.event_booking`); Activity lists event bookings; Buzz shows listed teams/venues with a real
  package (deep link to the profile); Buddy turns "plan a birthday for 30 next Saturday" into real matches, packages,
  availability and a checklist, pre-fills the planner and never sends, books or pays.

## Hotels (accommodation)

Customer-facing name: **Hotels** (`/hotels`, `/hotels/search`, `/hotels/:id`, `/hotels/compare`, `/hotels/book`, `/hotels/bookings`,
`/hotels/bookings/:id`), in Explore via the service registry (id `hotels`, theme `hotels`). Separate from Travel and Showtime.
API: `/api/v1/hotels/...` (public), `/api/v1/customer/hotels/...`, `/api/v1/partner/hotels/inventory`.

- **Destination ≠ current location.** The search destination is what the customer types (real `Destination`s, `Landmark`s and
  properties only); the Click. active location is never forced into it. Distances are straight-line km from the destination
  centre or a chosen landmark (airport, station, beach…).
- **Inventory:** `HotelProperty` (a Partner in Hotels & Venues, listed by Business OS), `RoomType` (beds, occupancy, size,
  units), `RatePlan` (meal plan, refundable + free-cancellation days, fee %, pay now / at property, weekday + weekend price),
  `RoomInventory` (per-night units / closures / price overrides). Free rooms per night = units − rooms held by pending
  bookings (until their hold expires) and confirmed bookings. `apps.hotels.search.ClickInventory` is the inventory
  provider; an external hotel-inventory provider would implement the same `search` / `rooms` methods
  (`CLICK_HOTEL_INVENTORY`) — none is connected.
- **Price:** nightly price × rooms, the best live offer the stay qualifies for (early booking, last minute, weekend,
  long stay, coupon) computed on the server, and GST on hotel stays by nightly tariff (none below ₹1,000, 12% up to
  ₹7,500, 18% above). A free-cancellation window that has already closed is never offered.
- **Search:** every filter is server-side (price per night, type, stars, guest rating, amenities, room class, breakfast,
  free cancellation, pay at property, near a landmark, distance) with sorts (recommended — a published score of shrunken
  verified rating, flexibility and distance — price, rating, distance, stars, best value). Highlights only when a data
  rule holds (Top rated, Best value, Great for families, Good for business, Free cancellation).
- **Booking:** room → guest details (no ID numbers collected) → review (server-priced) → confirm & pay → confirmation.
  The booking must match the reviewed total (`price_changed`), is idempotent and row-locks the room type. Pay now = Click.
  Wallet, verified in the same transaction; if it fails the room is held 15 minutes as *pending payment* for a retry, then
  the booking fails and the room is released. Pay at the property = confirmed, nothing charged online. The agreed policy is
  snapshotted on the booking.
- **After:** policy-based cancellation (free before the deadline → full wallet refund; after → fee %; non-refundable keeps
  all; pay-at-property never charged), confirmed stays complete after check-out, verified 1–10 reviews with six aspects.
  Modification (dates/room/guests) isn't online yet: cancel and rebook, or support.
- **Partner App:** hotel / resort / homestay / serviced-apartment partners use the `hotels` workspace (arrivals, in-house,
  departures; actions guest arrived, payment collected at property, check out) and the inventory endpoint.
- **Across Click.:** Wishlist (saved hotels), Activity ("Stays"), support tickets (`SupportTicket.hotel_booking`),
  notifications at each step, Buddy hotel search and "my hotel bookings". `HotelBooking.trip_ref` is reserved for a future
  Trip / itinerary. Card/UPI gateways and webhooks are not connected: only the wallet ledger and pay-at-property exist.

## Travel (long-distance transport)

Customer-facing name: **Travel** (`/travel`, `/travel/search`, `/travel/journey/:journey/:from/:to`, `/travel/compare`, `/travel/book`,
`/travel/bookings`, `/travel/bookings/:id`, `/travel/me`, `/travel/plan`), in Explore and Home via the service registry (id `travel`, theme
`travel`). Bus, train and flight only — local rides stay in Ride, stays in Hotels. API: `/api/v1/travel/...` (public: home, places, search,
dates, options) and `/api/v1/customer/travel/...` (review, bookings, ticket, pay / cancel / rate, recent, routes, travellers, alerts,
preferences, next).

- **Origin ≠ current location.** The journey search has its own From / To (cities, stations, airports, bus stops — each labelled
  "Hyderabad — Airport (HYD)"). "Leave from my city" is an offer, never a default.
- **Data:** `Place` (city + its stations / airports / bus stops), `Operator` (mode, status, source: Click. partner inventory, aggregator or
  direct API), `Service` (timetable: number, name, vehicle, running days, amenities, bus seat layout, baggage, cancellation tiers), `Stop`
  (time, day offset, km, boarding / dropping), `FareClass` (bus seat class, train class, flight cabin: capacity, RAC / waitlist, fares, GST,
  refundability, change fee), `Journey` (a dated run, materialised from the timetable inside the booking window; status, delay, notice),
  `TravelBooking` + `Passenger` (seat / coach-berth / CNF-RAC-WL status) + `StatusEvent`, `TripRating`, `SavedTraveller` (name, age, gender,
  berth preference — no ID numbers), `RecentSearch`, `Route` (saved in the shared Wishlist), `PriceAlert`, `TravelPreference`, `TravelOffer`.
- **Providers:** `apps.travel.search.ClickInventory` serves Click.'s own timetables; other providers implement the same `options()` and are
  listed in `CLICK_TRAVEL_PROVIDERS` (run with a timeout, results de-duplicated; if every provider fails the API says "Travel options are
  temporarily unavailable" — nothing is invented). Provider credentials stay on the server. No external provider is connected.
- **Availability and fares** (server only): bus seats from the operator layout, each sold once per journey (unique constraint), women-only
  seats enforced; train classes confirm a berth (preference honoured, seniors get a lower berth when free), then RAC, then a capped
  waitlist, and a cancellation promotes RAC → CNF and WL → RAC with notifications; flights: cabin capacity, fares step with load factor
  and closeness to departure. Bus fare = route fare × share of distance; train = per km (minimum) + reservation / superfast charges;
  GST as the provider applies it. Offers (`TravelOffer`) are computed on the server.
- **Results:** server-side filters (price, bus type, departure / arrival buckets, boarding / dropping point, operator / airline, amenities,
  rating from verified trips, cancellation type, stops, refundable, checked bag, train type, max duration) and sorts; the cheapest / fastest
  / best-value labels come from the result data (best value only when it's a different option); lowest fares on the 3 days either side
  come from the same search; compare 2–3 options of one mode. Saved preferences pre-select filters once per search.
- **Booking:** seats / class → passengers → review (re-checked now: availability, passenger rules, fare, offer, tax, policy, points) →
  Pay & book from the Click. Wallet. The booking must match the reviewed total (`price_changed` → "Fare updated: previous / current", the
  customer confirms), is idempotent and locks the service row. A failed payment holds the seats 10 minutes (pending payment, retry), then
  releases them; no PNR or ticket exists until it is paid. Round trips are two linked tickets (`trip_ref`): after the outbound, the return
  search opens.
- **After:** digital ticket only for a paid booking (PNR from Click.; no barcode the operator didn't issue), print / PDF, share, calendar
  (.ics), cancellation by the tiers agreed at booking with the exact fee and refund to the wallet (fully waitlisted train tickets refund in
  full), operator delay / platform notice / cancellation (admin action → notifications; operator cancellation refunds in full), reminders
  24 h before, completion after arrival with Click. Rewards points on the fare, verified trip rating → operator rating.
- **Across Click.:** Activity (Travel), Wishlist (saved routes), notifications, support (`SupportTicket.travel_booking`, attached from the
  booking), the central Bookings list, Buddy ("a bus from Hyderabad to Delhi tomorrow", "the cheapest train from Chennai to Odisha",
  "which is faster…", "book this train" opens the journey — Buddy never buys), fare alerts (re-checked when opened; a scheduler should
  run `check_alerts` and `booking.sweep`), Plan your journey (Travel + Hotels + places + Shows + Events, each linking into its own flow).

## Bookings (places, experiences and every booking)

Customer-facing name: **Bookings** (`/bookings`, `/bookings/search`, `/bookings/places/:slug`, `/bookings/book`, `/bookings/r/:id`,
`/bookings/mine`); theme `bookings`. It is the reservation hub: temples and spiritual places, tourist spots, parks and experiences, plus
the customer's bookings across Click. It links to Shows, Events, Hotels and Travel instead of duplicating them. API:
`/api/v1/experiences/...` (home, search, attractions, availability), `/api/v1/customer/experiences/...` (review, bookings, pay / cancel /
review, saved), `/api/v1/customer/reservations` (every booking), `/api/v1/partner/experiences/check-in`.

- **Bookable vs information.** `Attraction.bookable` is true only when an onboarded provider sells it through Click. with live offerings;
  everything else is "Information available" with `official_source` (e.g. a temple trust's own channels) — no prices, slots or timings
  are claimed for it.
- **Booking models:** `Offering` = entry ticket (any time that day) or time slot (darshan, seva, pooja, tours, activities), with days, slot
  times, capacity, max per booking, minimum age, pickup points, requirements and GST; `Price` = the provider's ticket types (adult, child,
  senior, student, family = 4 places, devotee, participant); `Closure` = provider closures.
- **Availability** = capacity − places used by confirmed bookings and pending ones inside their hold, per date / slot; slots within 15
  minutes have closed. A 14-day calendar comes with each offering.
- **Booking:** server-priced review (offer, GST, points) → lead visitor (names of others optional) → Pay & book (Click. Wallet) or confirm a
  free darshan registration. Price-changed guard, idempotency, offering row lock, 10-minute hold on payment failure. Confirmation issues
  an entry code the provider verifies in the Partner App (`check-in`: their own bookings only, today only, once).
- **After:** cancellation free until N hours before the visit, then the provider's fee %; refunds to the wallet; completion the day after
  the visit with Rewards points; verified 1–5 reviews → place rating.
- **Discovery:** categories with counts, cities from the data, sections by stated rules (in your city, near you by straight-line distance,
  temples, tourist spots, parks, experiences, kid-friendly, "most booked on Click." = confirmed bookings in 90 days, top rated = 4.0+ from 3+
  verified visits); search with filters (date availability, bookable, instant, free cancellation, verified, family / kids, indoor /
  outdoor, rating, price, distance) and sorts; matches elsewhere on Click. (hotels, travel, shows) for the same words. Global Search
  shows places & experiences and travel cities too.
- **My bookings** (`apps.experiences.hub`): reads Showtime tickets, hotel stays, travel tickets, event bookings, service bookings and
  place / experience bookings from their own tables, normalised (kind, title, when, status, amount, link); one domain failing doesn't hide
  the others. Nothing is copied.
- **Across Click.:** Wishlist (saved places), Activity ("Temples & places"), notifications, support (`SupportTicket.experience_booking`),
  Buddy ("temples I can visit this weekend", "a water park for 4 people", "what can I book in Vijayawada tomorrow?", "my booking
  tomorrow").

## Buddy (AI assistant and action layer)

Header icon → a **Man / Go** chooser. **MAN** (`/buddy`) is its own workspace (no Click header / bottom nav): Buddy header
(New chat, Home, Recent chats), conversation with rich cards, input dock (pin for Click. context, text, voice). **GO**
(`/buddy/go`) is voice first with an orb that shows Ready / Listening / Thinking / Acting / Speaking / Done / Error.

- **Intelligence:** `apps.ai.providers` (swappable via `CLICK_AI_PROVIDER`; default Buddy basic mode, which answers only
  from Click data through `apps.ai.tools` and the per-feature helpers: groceries, parcels, services, events, hotels). No
  Google AI services.
- **Conversations:** `Conversation` / `ConversationMessage` (owner-scoped; titles generated, renameable; archive; delete),
  explicit `context` = `{topic, query}` so "only vegetarian" / "the cheapest one" refine the last search. Likely secrets
  (card numbers, CVV/OTP/PIN) are redacted before storage. Reopening a chat only shows it — nothing re-runs.
- **Action layer (`apps.ai.actions`):** the AI can only propose typed actions; the server validates every argument
  (types, ownership, listing / stock / state) and checks the tier. *Safe* (run immediately): `open_page` (allow-listed
  routes), `wishlist_add`, `cart_add`, `cart_remove`. *Confirm* (server-built summary, customer taps Confirm, expires in
  10 min): `book_service` (a request, paid after the work), `cancel_order`. *High-risk* (account, security, payment
  methods) is refused — Buddy opens the page instead. Payments are never actions: Buddy opens the normal checkout.
  Every run is an `ActionExecution` (audit).
- **Voice:** recorded locally (stops after 8 s), transcribed only by Click.'s configured speech provider (off by default →
  Buddy says so and offers typing; the browser's built-in recognition is not used because it sends audio to Google).
  Spoken replies use on-device voices only.
- **Analytics:** `BuddyEvent` (opened, mode chosen, action requested/completed/failed, navigation, voice outcome, latency)
  with no message content and no audio.
- **Roles:** this is the customer surface; Partner and Business OS assistants would use the same provider layer with
  their own role-scoped context and action registries.

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
  Food, Groceries, Shopping, Bookings, Parcels, Services and Events.
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

- **Phone identity:** the same identity layer as customers (`apps/identity`, see `docs/authentication.md`): Click's
  OTP verifies the phone and `ExternalIdentity(provider="phone_otp", subject=<E.164 phone>)` links it to
  one Click user. A new phone gets a phone-only user (no email or password); a phone already verified on a customer
  account maps to that same person, so one human is never two users.
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
- **Category configuration:** `apps/partners/catalog.py` defines fields, location options and Home configuration per
  type, with category overrides. The API serves the resolved configuration, and the server validates profile
  details against it.
- **Partner Home:** `apps/partners/workspace/` composes Home from a workspace provider chosen by the category
  (`rides` in `apps/rides/partner_workspace.py`, `orders` in `apps/orders/partner_workspace.py`, `venue` in
  `apps/bookings/partner_workspace.py`, `upcoming` for services Click hasn't launched). Providers read the domain
  tables directly, so Customer App, Partner App and Business OS share one state. `PartnerStore` / `PartnerVenue` link a
  partner to the storefronts and venues it operates (staff-created). `PartnerAvailabilityEvent` logs every
  online/open toggle (online time is derived from it). `PartnerNotification` is created by signals on orders, bookings,
  ride offers/cancellations and verification decisions. "Today" is the business day in `Asia/Kolkata`
  (`CLICK_BUSINESS_TIME_ZONE`). Ride matching only offers trips to categories whose workspace is `rides`.
