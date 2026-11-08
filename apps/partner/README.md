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
| `/home`                  | Minimal Partner Home shell (category-aware empty modules) |

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
