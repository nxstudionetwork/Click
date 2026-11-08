# Click Partner App

The app businesses and service providers use to operate on Click: drivers, restaurants, grocery and retail stores,
parcel/logistics partners, manpower and service providers, cinemas, hotels/venues and local businesses.

React + TypeScript (Vite), port **5174**. Uses the shared `@click/api` (contract + session client) and `@click/ui`
(shared primitives and the Click logo) packages and the backend's `/api/v1/auth/firebase` and `/api/v1/partner/*` APIs.

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

1. Firebase Phone Authentication sends and checks the SMS code (the SDK is lazy-loaded on the sign-in path only).
2. The app sends the Firebase **ID token** to `POST /api/v1/auth/firebase`.
3. Django verifies the token (Google's public keys, project audience/issuer, phone provider) and finds or creates
   the Click user by Firebase UID, then issues the normal Click session (in-memory access token + httpOnly refresh cookie).
4. `GET /api/v1/partner/me` returns the partner and its onboarding step; the app routes accordingly.

On reopen, the Click session cookie is tried first; if it has expired, an existing Firebase session is exchanged again.
Sign out revokes the Click refresh token, signs out of Firebase and clears cached data. It never deletes the partner.

## Configuration

Copy `.env.example` to `.env.local` and fill in the Firebase **web app** values (public identifiers, not secrets).
Set `FIREBASE_PROJECT_ID` in `backend/.env` to the same project. No service-account key is used anywhere.

In Firebase console: enable **Authentication → Sign-in method → Phone**, and add your domains under
**Authentication → Settings → Authorized domains** (`localhost` is included by default). For testing without real SMS,
add test phone numbers there, or use the Auth Emulator:

```bash
npx firebase-tools emulators:start --only auth --project <project-id>
```

Then set `VITE_FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099` (frontend) and `FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099`
(backend). The backend refuses the emulator setting outside DEBUG.

## Categories and visuals

Partner types, categories, their onboarding fields and their Home modules are defined once in
`backend/apps/partners/catalog.py` and served by `GET /api/v1/partner/categories`. Adding a category is a catalogue
change (`manage.py sync_partner_catalog` or a migration); the app renders it without code changes.
`src/config/visuals.ts` is the only place that maps a type slug to photography; unknown types get a fallback.

Photos are real Unsplash photographs (see `public/media/CREDITS.md`), WebP at two sizes, lazy-loaded with `srcset`.
The animated sequences are photo crossfades rather than video, so low-end phones and slow networks stay fast.
