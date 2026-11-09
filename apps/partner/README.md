# Click Partner App

The app businesses and service providers use to operate on Click: drivers, restaurants, grocery and retail stores,
parcel/logistics partners, manpower and service providers, cinemas, hotels/venues and local businesses.

React + TypeScript (Vite), port **5174**. Uses the shared `@click/api` (contract + session client), `@click/ui` (primitives and the Click logo) and
`@click/phone-auth` (phone OTP) packages, and the backend's `/api/v1/auth/identity/*` and `/api/v1/partner/*` APIs.

## Phase 1 flow (implemented)

```
Splash → Login (mobile number) → Firebase OTP → Verify
       → existing partner: Partner Home
       → new partner: Partner type + category → Profile (category-specific) → Location → Review
                      → Partner ID (CLK-PT-000001) → Partner card (Save / Share) → Partner Home
```

| Route                    | Screen |
|--------------------------|--------|
| `/login`, `/verify`      | Phone entry and OTP (Firebase Phone Auth, invisible reCAPTCHA) |
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

1. `@click/phone-auth` sends and checks the SMS code with Firebase Phone Authentication (lazy-loaded on the sign-in
   path only), returns the Firebase ID token, and signs out of Firebase.
2. `POST /api/v1/auth/identity/exchange {provider: "firebase", token}`: Django verifies the token and resolves the
   Click user by Firebase UID (or by an already-verified phone, so a customer who becomes a partner is one person).
3. A new phone gets `{status: "profile_required", signupToken}`; the app calls
   `POST /api/v1/auth/identity/partner-signup {signupToken}`, which creates a phone-only Click user.
4. Either way the app now has the normal Click session (in-memory access token + httpOnly refresh cookie), and
   `GET /api/v1/partner/me` returns the partner and its onboarding step.

Reopening the app restores the Click session from its cookie (14 days by default); after that the partner verifies
by OTP again and lands on the same partner. Sign out revokes the Click refresh token and clears cached data. It
never deletes the partner. If Click can't be reached right after a successful OTP, "Try again" reuses the verified
credential, so no new code is needed.

## Configuration

Copy `.env.example` to `.env.local` and fill in the Firebase **web app** values (public identifiers, not secrets,
the same as the Customer App's). The backend's `FIREBASE_PROJECT_ID` defaults to `clickstartup26`. No service-account
key is used anywhere.

In Firebase console: enable **Authentication → Sign-in method → Phone**, and add your domains under
**Authentication → Settings → Authorized domains** (`localhost` is included by default). For testing without real SMS,
add test phone numbers there, or use the Auth Emulator exactly as described in `docs/authentication.md`
(run `npm run dev:partner` for this app).

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
