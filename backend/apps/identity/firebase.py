"""
Firebase ID token verification without the Admin SDK or any service-account key,
following Firebase's documented third-party JWT procedure:
https://firebase.google.com/docs/auth/admin/verify-id-tokens#verify_id_tokens_using_a_third-party_jwt_library

  * header: alg RS256, kid present in Google's securetoken public certificates
  * aud == project id, iss == https://securetoken.google.com/<project id>
  * exp in the future, iat and auth_time in the past, sub non-empty (<= 128 chars)
  * Click additionally requires sign-in via phone and a phone_number claim.

Only public certificates are fetched (cached per Cache-Control). No private keys exist here.
In DEBUG with FIREBASE_AUTH_EMULATOR_HOST set, unsigned emulator tokens are accepted
(same behaviour as the official Admin SDK) so the flow can be tested locally.
"""

import json
import logging
import re
import time
import urllib.request

import jwt
from cryptography.x509 import load_pem_x509_certificate
from django.conf import settings
from django.core.cache import cache

from .providers import IdentityError, VerifiedIdentity

logger = logging.getLogger(__name__)
CERTS_URL = "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
CERTS_CACHE_KEY = "identity:firebase:certs"
CLOCK_SKEW = 60
E164 = re.compile(r"^\+[1-9]\d{6,14}$")


def fetch_certificates() -> dict[str, str]:
    certs = cache.get(CERTS_CACHE_KEY)
    if certs:
        return certs
    with urllib.request.urlopen(CERTS_URL, timeout=5) as resp:  # noqa: S310 (fixed https URL)
        certs = json.loads(resp.read())
        max_age = 3600
        for part in (resp.headers.get("Cache-Control") or "").split(","):
            if part.strip().startswith("max-age="):
                max_age = int(part.strip()[8:])
    cache.set(CERTS_CACHE_KEY, certs, max(60, max_age - 60))
    return certs


class FirebaseIdTokenVerifier:
    name = "firebase"

    def __init__(self):
        self.project_id = settings.FIREBASE_PROJECT_ID
        if not self.project_id:
            raise IdentityError("FIREBASE_PROJECT_ID is not configured")
        self.emulator = bool(settings.DEBUG and settings.FIREBASE_AUTH_EMULATOR_HOST)

    def _decode(self, token: str) -> dict:
        issuer = f"https://securetoken.google.com/{self.project_id}"
        options = {"require": ["exp", "iat", "aud", "iss", "sub"]}
        if self.emulator:
            claims = jwt.decode(token, options={"verify_signature": False, **options}, audience=self.project_id, issuer=issuer,
                                algorithms=["none", "RS256"], leeway=CLOCK_SKEW)
            return claims
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256":
            raise IdentityError("unexpected alg")
        try:
            pem = fetch_certificates()[header.get("kid", "")]
        except KeyError:
            raise IdentityError("unknown kid")
        except Exception as exc:  # network/cert errors
            logger.exception("Could not fetch Firebase certificates")
            raise IdentityError(f"certificates unavailable: {exc}")
        key = load_pem_x509_certificate(pem.encode()).public_key()
        return jwt.decode(token, key=key, algorithms=["RS256"], audience=self.project_id, issuer=issuer, leeway=CLOCK_SKEW, options=options)

    def verify(self, credential: str) -> VerifiedIdentity:
        try:
            claims = self._decode(credential)
        except IdentityError:
            raise
        except jwt.PyJWTError as exc:
            raise IdentityError(f"invalid token: {exc}")
        sub = claims.get("sub") or ""
        if not sub or len(sub) > 128:
            raise IdentityError("invalid sub")
        if claims.get("auth_time", 0) > time.time() + CLOCK_SKEW:
            raise IdentityError("auth_time in the future")
        if (claims.get("firebase") or {}).get("sign_in_provider") != "phone":
            raise IdentityError("not a phone sign-in")
        phone = claims.get("phone_number") or ""
        if not E164.match(phone):
            raise IdentityError("missing phone_number")
        return VerifiedIdentity(provider=self.name, subject=sub, phone_number=phone)
