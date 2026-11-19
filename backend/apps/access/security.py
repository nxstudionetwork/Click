"""
Security primitives for Business OS sign-in: TOTP (RFC 6238), encrypted MFA secrets, recovery codes,
signed short-lived flow tokens. Standard library + `cryptography` only.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core import signing

TOTP_STEP = 30
TOTP_DIGITS = 6


def _fernet() -> Fernet:
    key = hashlib.sha256(("click-os-mfa:" + settings.SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode() if value else ""


def decrypt(value: str) -> str:
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return ""


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _hotp(secret_b32: str, counter: int) -> str:
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** TOTP_DIGITS)
    return f"{code:0{TOTP_DIGITS}d}"


def totp_now(secret_b32: str, at: float | None = None) -> str:
    return _hotp(secret_b32, int((at or time.time()) // TOTP_STEP))


def verify_totp(secret_b32: str, code: str, *, last_counter: int = 0, window: int = 1, at: float | None = None) -> int | None:
    """Return the matched time step (to store, so the same code can't be replayed) or None."""
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(code) != TOTP_DIGITS or not secret_b32:
        return None
    now = int((at or time.time()) // TOTP_STEP)
    for counter in range(now - window, now + window + 1):
        if counter > last_counter and hmac.compare_digest(_hotp(secret_b32, counter), code):
            return counter
    return None


def otpauth_uri(secret_b32: str, account_label: str, issuer: str = "Click Business OS") -> str:
    return f"otpauth://totp/{quote(issuer)}:{quote(account_label)}?secret={secret_b32}&issuer={quote(issuer)}&digits=6&period=30"


def new_recovery_codes(n: int = 10) -> tuple[list[str], list[str]]:
    codes = [f"{secrets.token_hex(3)}-{secrets.token_hex(3)}" for _ in range(n)]
    return codes, [hash_code(c) for c in codes]


def hash_code(code: str) -> str:
    return hashlib.sha256(("click-os-recovery:" + code.strip().lower()).encode()).hexdigest()


# --- signed flow tokens (identify → password → MFA), never stored ---------------
def sign(purpose: str, payload: dict) -> str:
    return signing.dumps(payload, salt=f"click-os:{purpose}", compress=True)


def unsign(purpose: str, token: str, max_age: int) -> dict | None:
    try:
        return signing.loads(token or "", salt=f"click-os:{purpose}", max_age=max_age)
    except signing.BadSignature:
        return None
