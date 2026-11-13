# Click authentication (phone OTP)

Customer and Partner apps share this identity layer and the `@click/phone-auth` package. Click runs the OTP itself:
no third-party auth SDK is loaded in any app.

```
App ──POST /api/v1/auth/otp/request {phone}──► Click API (Django)
                                                 │ create OtpChallenge (hash of a 6-digit code, 5-minute expiry)
                                                 │ text the code through CLICK_SMS_PROVIDER
    ◄── {challengeId, expiresIn, resendIn} ──────┘
App ──POST /api/v1/auth/identity/exchange {provider: "phone_otp", token: "<challengeId>.<code>"}
                                                 │ PhoneOtpVerifier: code matches, not expired, not used, attempts left
                                                 │ ExternalIdentity(phone_otp, <E.164 phone>) → User
        existing customer ◄──────────────────────┤→ Click session (access token + httpOnly refresh cookie)
        new customer      ◄──────────────────────┘→ signed signupToken (20 min)
App ──POST /api/v1/auth/identity/signup {signupToken, fullName, email, addresses[1..5]} → Click session
```

- **The OTP:** `apps/identity/otp.py`.
  - Codes are 6 random digits; only an HMAC of the code is stored (`OtpChallenge.code_hash`).
  - A code expires after `CLICK_OTP_TTL_SECONDS` (300), allows `CLICK_OTP_MAX_ATTEMPTS` (5) wrong tries, is used
    once, and requesting a new code invalidates the previous one.
  - Requests are limited per phone (`CLICK_OTP_MAX_PER_HOUR`, 5), per IP (`CLICK_OTP_MAX_PER_IP_HOUR`, 30) and by a
    resend cooldown (`CLICK_OTP_RESEND_SECONDS`, 30), on top of the `auth` API throttle.
  - Errors the customer sees: wrong code, expired code, too many attempts, wait before resending, sign-in unavailable.
- **Sending the code:** `apps/identity/sms.py`. `CLICK_SMS_PROVIDER` is
  - `""` in production until you configure a provider: requesting a code returns "Phone sign-in is temporarily
    unavailable" (nothing is faked);
  - `console` in development: the code is printed in the API terminal (`[development SMS] to +1650…: 123456 is your
    Click. verification code…`); it is forced off when `DEBUG` is off;
  - a dotted path to your SMS sender class with `send(phone_e164, text)`. Its credentials go in `backend/.env`.
- **Identity model:**
  - `users.User` has an internal UUID primary key.
  - `customers.CustomerProfile.customer_code` is the permanent, customer-facing Click ID (`CLK-CS-XXXXXX`, random,
    non-sequential).
  - `identity.ExternalIdentity(provider, subject)` links a user to the identity that proved their phone
    (`phone_otp`, subject = E.164 phone).
  - A verified phone already on an account links back to it instead of creating a duplicate, so customers who signed
    in with the earlier provider sign straight in with their existing account.

## Adding your SMS provider

1. Write a class in the backend with `send(self, phone: str, text: str) -> None` that calls your provider's API and
   raises on failure (a failed send never leaves a usable code behind).
2. Set `CLICK_SMS_PROVIDER=<dotted.path.ToYourSender>` and the provider's credentials in `backend/.env`.

No app, screen, session or data-model change is needed.

## Development-only sign-in

- **Login as Test Customer** on the sign-in screen (development builds only; the backend endpoint returns 404 unless `DEBUG`).
- **Email/password** endpoints exist only for development and tests (`CLICK_PASSWORD_AUTH`, off in production).

## Click Partner

The Partner App uses the same OTP request and exchange. For a new phone, instead of the customer profile signup it calls
`POST /api/v1/auth/identity/partner-signup {signupToken}`, which creates a **phone-only** Click user (no email, no
password) linked by `ExternalIdentity`. Business details are collected during partner onboarding and stored on the
`Partner` (`apps/partners`). A phone already verified on a customer account resolves to that same user, so one
person can be both a customer and a partner. Partner data is always resolved from the signed-in user's
`PartnerMembership`, never from client input.
