# Click authentication (phone OTP)

Customer and Partner apps share this identity layer and the `@click/phone-auth` package. The customer flow is
shown below; the partner flow differs only after the exchange (see *Click Partner* at the end).

```
Customer App ──(phone)──► Phone-OTP provider (Firebase Phone Auth today)
      │                         │ OTP verified → provider ID token
      └──── POST /api/v1/auth/identity/exchange {provider, token} ────► Click API :4000 (Django)
                                                                            │ verify token server-side
                                                                            │ ExternalIdentity(provider, subject) → User
                                          existing customer ◄───────────────┤→ Click session (access token + httpOnly refresh cookie)
                                          new customer      ◄───────────────┘→ signed signupToken (20 min)
      └──── POST /api/v1/auth/identity/signup {signupToken, fullName, email, addresses[1..5]} → Click session
```

- **Firebase proves phone ownership, nothing more.** Click's PostgreSQL holds the customer, profile, addresses and
  all activity. Right after OTP the app signs out of Firebase and uses only Click's own session.
- **Identity model:**
  - `users.User` has an internal UUID primary key.
  - `customers.CustomerProfile.customer_code` is the permanent, customer-facing Click ID (`CLK-CS-XXXXXX`, random,
    non-sequential, so it doesn't reveal how many customers Click has).
  - `identity.ExternalIdentity(provider, subject)` stores the Firebase UID, unique per provider. The same UID always
    maps to the same customer.
  - A verified phone already on an account links back to it instead of creating a duplicate.
- **Token verification:** `apps/identity/firebase.py` follows Firebase's documented third-party-JWT procedure:
  - RS256 signature against Google's public `securetoken` certificates (cached)
  - `aud` = project ID and `iss` = `https://securetoken.google.com/<project>`
  - `exp`, `iat` and `auth_time` checked
  - non-empty `sub`
  - sign-in must be by `phone`, with a valid `phone_number`

  **No service account or private key is used anywhere.** Nothing to leak.

## Firebase Console setup (project `clickstartup26`)

1. **Authentication → Sign-in method → Phone:** enable.
2. **Authentication → Settings → Authorized domains:** keep `localhost`, and add your production domain when you
   deploy.
3. **Test number (optional, for development):** under Authentication → Sign-in method → Phone → *Phone numbers for
   testing*, add `+1 650-555-0101` with a 6-digit code of your choice. Signing in with that number reaches the seeded
   test customer (`CLK-CS-TEST001`). No SMS is sent, and the code only works for that test number. The code is
   stored in Firebase Console, never in Click's code.
4. **Optional:** App Check, and SMS region policy (Authentication → Settings) to limit SMS to the countries you serve.

**Frontend config** goes in `apps/customer/.env.local` (Git-ignored); see `apps/customer/.env.example`. Firebase *web*
config values are public client identifiers, not secrets. Only Firebase Auth is loaded: no Analytics or other
Google services.

**Backend:** `FIREBASE_PROJECT_ID` (default `clickstartup26`).

## Local end-to-end testing without SMS (Firebase Auth Emulator)

```bash
npx firebase-tools emulators:start --only auth --project demo-click     # in a scratch folder
# backend
DJANGO_DEBUG=true FIREBASE_PROJECT_ID=demo-click FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099 python manage.py runserver
# frontend
VITE_FIREBASE_PROJECT_ID=demo-click VITE_FIREBASE_API_KEY=demo-key VITE_FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099 npm run dev:customer
```

The emulator shows OTP codes at `http://127.0.0.1:9099/emulator/v1/projects/demo-click/verificationCodes`. The backend
accepts emulator tokens only when `DEBUG` is on and the emulator host is set.

## Changing the auth provider later

1. **Backend:** add a verifier class next to `apps/identity/firebase.py` that returns
   `VerifiedIdentity(provider, subject, phone_number)`, then register it in `settings.CLICK_IDENTITY_PROVIDERS`.
2. **Frontend:** add an adapter implementing `PhoneAuthProvider` in `apps/customer/src/auth/phone/` and set
   `VITE_PHONE_AUTH_PROVIDER`.

No screen, session, customer or data model changes. Existing customers re-link automatically on their first sign-in
with the new provider, because their phone number is already verified.

## Development-only sign-in

- **Login as Test Customer** on the sign-in screen (development builds only; the backend endpoint returns 404 unless `DEBUG`).
- **Email/password** endpoints exist only for development and tests (`CLICK_PASSWORD_AUTH`, off in production).

## Click Partner

The Partner App uses the same exchange. For a new phone, instead of the customer profile signup it calls
`POST /api/v1/auth/identity/partner-signup {signupToken}`, which creates a **phone-only** Click user (no email, no
password) linked by `ExternalIdentity`. Business details are collected during partner onboarding and stored on the
`Partner` (`apps/partners`). A phone already verified on a customer account resolves to that same user, so one
person can be both a customer and a partner. Partner data is always resolved from the signed-in user's
`PartnerMembership`, never from client input.
