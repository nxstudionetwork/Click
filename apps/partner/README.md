# Click Partner App

The app businesses and service providers use to operate on Click: drivers, restaurants, grocery and retail stores,
parcel/logistics partners, manpower and service providers, cinemas, hotels/venues and local businesses.

React + TypeScript (Vite), port **5174**. Uses the shared `@click/api` (contract + session client), `@click/ui` (primitives and the Click logo) and
`@click/phone-auth` (phone OTP) packages, and the backend's `/api/v1/auth/identity/*` and `/api/v1/partner/*` APIs.

## Phase 1 flow (implemented)

```
Splash → Login (mobile number) → Click OTP → Verify
       → existing partner: Partner Home
       → new partner: Partner type + category → Profile (category-specific) → Location → Review
                      → Partner ID (CLK-PT-000001) → Partner card (Save / Share) → Partner Home
```

| Route                    | Screen |
|--------------------------|--------|
| `/login`, `/verify`      | Phone entry and OTP (Click OTP from the backend) |
| `/onboarding/category`   | What do you provide through Click? (types and categories from the API) |
| `/onboarding/profile`    | Basic details + fields defined for the chosen category |
| `/onboarding/location`   | Manual address, optional "use my current location", service area |
| `/onboarding/review`     | Summary; creates the Partner ID |
| `/card`                  | Partner identity card |
| `/home`                  | Partner Home: the category-driven operations dashboard (see below) |
| `/work`                  | Work queue for the partner's workspace (Rides / Orders / Shows & bookings), same items and actions as Home |
| `/earnings`              | Daily totals (7 or 30 days) and recent completed work |
| `/notifications`         | Partner notifications (new work, cancellations, verification) with read state |

Routes are UX only; the API enforces sign-in and ownership on every request.

## How sign-in works

The Partner App uses the same identity layer as the Customer App (see `docs/authentication.md`):

1. `@click/phone-auth` asks the backend to text a code (`POST /api/v1/auth/otp/request`).
2. `POST /api/v1/auth/identity/exchange {provider: "phone_otp", token: "<challenge>.<code>"}`: Django verifies the code and resolves the
   Click user by verified phone (or by an already-verified phone, so a customer who becomes a partner is one person).
3. A new phone gets `{status: "profile_required", signupToken}`; the app calls
   `POST /api/v1/auth/identity/partner-signup {signupToken}`, which creates a phone-only Click user.
4. Either way the app now has the normal Click session (in-memory access token + httpOnly refresh cookie), and
   `GET /api/v1/partner/me` returns the partner and its onboarding step.

Reopening the app restores the Click session from its cookie (14 days by default); after that the partner verifies
by OTP again and lands on the same partner. Sign out revokes the Click refresh token and clears cached data. It
never deletes the partner. If Click can't be reached right after a successful OTP, "Try again" reuses the verified
credential, so no new code is needed.

## Configuration

No client-side auth configuration is needed; the backend's `CLICK_SMS_PROVIDER` decides how codes are sent.

## Categories and visuals

Partner types, categories, their onboarding fields and their Home modules are defined once in
`backend/apps/partners/catalog.py` and served by `GET /api/v1/partner/categories`. Adding a category is a catalogue
change (`manage.py sync_partner_catalog` or a migration); the app renders it without code changes.
`src/config/visuals.ts` is the only place that maps a type slug to photography; unknown types get a fallback.

Photos are real Unsplash photographs (see `public/media/CREDITS.md`), WebP at two sizes, lazy-loaded with `srcset`.
The animated sequences are photo crossfades rather than video, so low-end phones and slow networks stay fast.

## Partner Home (operations)

One common Home framework, category-specific content:

```
Partner → category → resolved Home configuration (backend/apps/partners/catalog.py, HOME / CATEGORY_HOME)
        → workspace provider (backend/apps/partners/workspace/) → real domain data → GET /api/v1/partner/home
```

| Workspace  | Categories (today)                                   | Reads                                   | Status labels |
|------------|-------------------------------------------------------|-----------------------------------------|---------------|
| `rides`    | Driver, Cab / Auto Driver, Bike Rider                 | Click. Ride offers, trips, ratings      | Online / Offline |
| `orders`   | Food & Dining, Grocery & Retail, Local Business       | Orders at the storefronts the partner operates (`PartnerStore`) | Open / Closed |
| `venue`    | Cinema & Entertainment                                | Shows and seat bookings at the partner's venues (`PartnerVenue`) | Bookings open / closed |
| `upcoming` | Hotels & Venues, Parcel & Logistics, Manpower & Services, Delivery Rider, fleet categories | Nothing yet: Home says the service hasn't launched | shown, not switchable |

- `GET /partner/home` returns every section in one request; each section is `ok`, `error` (that module only) or
  `unavailable` (not live / not connected, with the reason). The app polls every 10 s while visible (no push channel yet).
- Availability (`POST /partner/availability`) is persisted, audited (`PartnerAvailabilityEvent`) and applied where
  customers see it: a store stops accepting orders, a venue stops taking bookings, a driver going offline gives up
  pending ride requests. Drivers can't go offline mid-trip. Only verified/active partners can switch on.
- Work actions (`POST /partner/work/<kind>/<id>/<action>`) run the domain's own state machine (`transition_order`,
  `driver_accept` / `driver_decline` / `driver_step`); the UI updates only after the server confirms.
- A restaurant or shop partner sees orders only once Click staff connect their storefront (Django admin → Partner →
  Partner stores). Until then Home says so instead of showing empty numbers.
- Drivers share live location only while online, after choosing to, while the app is open.
- Adding a category: catalogue change. Adding a new kind of work: one provider registered in `workspace.PROVIDERS`.

### Development test partners

`python manage.py seed_dev_data` creates one verified test partner per Home configuration (restaurant, grocery store,
shop, cinema linked to seeded records; hotel, parcel, electrician on the "not live yet" Home) besides the seeded
drivers. In development builds the sign-in screen has **Login as test partner** (backend endpoint is 404 unless DEBUG).

## Restaurant mode

When the server says `partner.mode === 'restaurant'`, the app switches to restaurant navigation
(phone: Home | Orders | Kitchen | Menu | More; the desktop rail also lists Offers, Insights, Earnings and Alerts).
The backend lives in `backend/apps/orders/restaurant.py` (`/api/v1/partner/restaurant/*`) and refuses every other partner type.

- **Kitchen** (`/restaurant/kitchen`): live orders in New → Accepted → Preparing → Ready columns with a target ready time
  (accepted time + preparation time + any busy minutes). The same order actions as Home, confirmed by the server.
- **Orders** (`/restaurant/orders`): stage filters, search by order number, a date filter and paging.
- **Menu** (`/restaurant/menu`): categories and items (price, food type, photo link, sizes/add-ons as option groups),
  one-tap availability, hide/show, reorder. Customers see changes on their next request; duplicates are refused.
- **Kitchen card on Home**: busy (+10/20/30 min on the delivery window customers see, for an hour), temporary closure
  with a reason and automatic reopening, usual preparation time. Expiry runs on partner requests, at add-to-cart and
  order placement, and in `python manage.py click_jobs --frequent`.
- **Offers** (`/restaurant/offers`): partner offers are validated server-side and stay hidden from customers until
  Click approves them (Django admin → Store offers → Approve). Approved offers can be paused and resumed.
- **Insights** (`/restaurant/insights`): sales, orders, preparation time, acceptance/cancellation, best sellers and
  ratings, computed only from real orders, status history and reviews.

Not built yet: partner support tickets, staff roles, menu photo upload (items take an https image link), and pickup
orders (all Click food orders are delivery today). Buzz posts: see Click. Buzz below.

## Driver mode

When `partner.mode === 'driver'`: phone bar Home | Rides | Buzz | Earnings | Menu (Alerts on the desktop rail).
Backend: `backend/apps/rides/driver.py` and `driver_views.py` (`/api/v1/partner/driver/*`), plus the ride actions on
`/partner/work/ride/<id>/<action>`.

- **Requests** expire after 40 s (a countdown shows on the card) and pass to the next nearest driver. Accepting an
  expired request is refused. `click_jobs --frequent` also expires them.
- **Active trip**: arrived → start → complete (each confirmed), cancel before pickup with a reason (the rider goes back
  to matching), and “Rider didn’t show”, offered only after 5 minutes waiting at the pickup. Safety (SOS / report) is
  on the trip and in the Safety centre.
- **History** (`/driver/rides?view=history`): rate the rider once per completed trip and report a past trip.
- **Earnings** (`/driver/earnings`): today, yesterday, week and month from completed trips, split into cash collected
  and paid via Click. Commission and payouts aren’t configured yet, so nothing is deducted (the page says so).
- **Profile & vehicle** (`/driver/profile`) shows what riders see. **Documents** (`/documents`, every partner type):
  number and expiry, verified or rejected by Click in the admin. An expired required document blocks going online and
  matching.

## Click. Buzz (every partner type)

`/buzz` (`backend/apps/buzz/partner.py`, `/api/v1/partner/buzz/*`). Partners post photos or one short video, a
headline and caption, and **one button that leads to their own live Click listing**: store or menu item, hotel,
services profile, event team, shows, ride booking or parcels. The server rejects anything else. Optional: a featured
item (customers see its live availability) and one of the partner’s live offers.

- **Review**: posts go to Click (Django admin → Buzz posts → Approve / Reject / Take down). Editing a reviewed post
  sends it back to review. Statuses: draft, in review, scheduled, live, paused, expired, not approved, removed, archived.
- **Media**: JPG/PNG/WebP up to 8 MB, re-encoded to WebP (480 and 1080 px, metadata stripped). MP4/WebM up to 25 MB,
  one per post, at most 4 files per post. Files go to Django media storage (object storage in production), never the
  database. Uploads not attached to a post are removed by `click_jobs --daily`.
- **Performance**: views and button taps from the Customer App, counted once per viewer per day, plus likes and saves.
- **Customers** see approved posts first in Click. Buzz, can like, save and report them (reports go to Buzz reports in
  the admin), and the button opens the real listing.
- **Partner community** tab: approved posts from other partners, with like and report.

Not built yet: comments on posts, video transcoding (videos are validated, not re-encoded) and paid Buzz promotion.
