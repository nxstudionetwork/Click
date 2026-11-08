"""
Server-side verification of Firebase Authentication ID tokens.

The Partner App signs in with Firebase Phone Authentication (Firebase sends
and checks the SMS code). The client then hands its Firebase *ID token* to
Click, and this module proves it is genuine before Click trusts the UID:

  * RS256 signature against Google's published Firebase signing keys (JWKS,
    cached in-process and refreshed when a new key ID appears),
  * `aud` is our Firebase project, `iss` is securetoken.google.com/<project>,
  * not expired / not issued in the future, non-empty `sub` (the Firebase UID),
  * signed in with the phone provider and carrying a phone number.

No Firebase service-account key is needed for this: verification uses public
keys only. The client-supplied UID is never trusted on its own.

Local development may point at the Firebase Auth Emulator
(FIREBASE_AUTH_EMULATOR_HOST). Emulator tokens are unsigned, so this is only
honoured when DEBUG or tests are on; settings refuse it in production.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from functools import lru_cache

import jwt
from django.conf import settings

logger = logging.getLogger(__name__)

JWKS_URL = "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
CLOCK_SKEW_SECONDS = 10


class FirebaseAuthError(Exception):
    """The token is not acceptable. `code` is stable; never expose `str(exc)` to clients."""

    def __init__(self, code: str, reason: str = ""):
        super().__init__(reason or code)
        self.code = code


class FirebaseUnavailable(Exception):
    """Firebase verification could not run (not configured, or Google keys unreachable)."""


@dataclass(frozen=True)
class FirebaseClaims:
    uid: str
    phone_number: str
    auth_time: int


def project_id() -> str:
    return settings.FIREBASE_PROJECT_ID


def emulator_enabled() -> bool:
    return bool(settings.FIREBASE_AUTH_EMULATOR_HOST) and (settings.DEBUG or settings.TESTING)


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    # PyJWKClient caches the key set and refetches when it sees an unknown `kid`.
    return jwt.PyJWKClient(JWKS_URL, cache_jwk_set=True, lifespan=3600, timeout=5)


def _signing_key(token: str):
    try:
        return _jwks_client().get_signing_key_from_jwt(token).key
    except jwt.PyJWKClientConnectionError as exc:
        logger.warning("Firebase signing keys unreachable: %s", exc)
        raise FirebaseUnavailable("signing keys unreachable") from exc
    except (jwt.PyJWKClientError, jwt.DecodeError) as exc:
        raise FirebaseAuthError("invalid_token", "unknown signing key") from exc


def verify_id_token(token: str) -> FirebaseClaims:
    pid = project_id()
    if not pid:
        raise FirebaseUnavailable("FIREBASE_PROJECT_ID is not configured")
    if not token or not isinstance(token, str) or len(token) > 4096:
        raise FirebaseAuthError("invalid_token", "malformed")

    issuer = f"https://securetoken.google.com/{pid}"
    options = {"require": ["exp", "iat", "sub", "aud", "iss"]}
    try:
        if emulator_enabled():
            # Emulator tokens use alg "none"; audience/issuer/expiry are still checked.
            emulator_options = {
                **options, "verify_signature": False, "verify_exp": True, "verify_iat": True,
                "verify_aud": True, "verify_iss": True,
            }
            claims = jwt.decode(token, options=emulator_options, audience=pid, issuer=issuer, leeway=CLOCK_SKEW_SECONDS)
        else:
            claims = jwt.decode(
                token, _signing_key(token), algorithms=["RS256"], audience=pid, issuer=issuer,
                leeway=CLOCK_SKEW_SECONDS, options=options,
            )
    except jwt.ExpiredSignatureError as exc:
        raise FirebaseAuthError("token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise FirebaseAuthError("invalid_token", type(exc).__name__) from exc

    now = time.time()
    uid = claims.get("sub")
    if not isinstance(uid, str) or not uid or len(uid) > 128:
        raise FirebaseAuthError("invalid_token", "bad subject")
    if claims.get("iat", 0) > now + CLOCK_SKEW_SECONDS or claims.get("auth_time", 0) > now + CLOCK_SKEW_SECONDS:
        raise FirebaseAuthError("invalid_token", "issued in the future")

    firebase = claims.get("firebase") or {}
    phone = claims.get("phone_number") or ""
    if firebase.get("sign_in_provider") != "phone" or not phone:
        raise FirebaseAuthError("phone_required", "token was not issued for phone sign-in")

    return FirebaseClaims(uid=uid, phone_number=phone, auth_time=int(claims.get("auth_time") or claims["iat"]))
