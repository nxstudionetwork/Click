"""
Pluggable identity verification. A provider turns a client-supplied credential
(Click's phone OTP today) into a VerifiedIdentity, or raises IdentityError.
Adding another identity provider = add a verifier class and
register it in settings.CLICK_IDENTITY_PROVIDERS; nothing else changes.
"""

from dataclasses import dataclass
from typing import Protocol

from django.conf import settings
from django.utils.module_loading import import_string


@dataclass(frozen=True)
class VerifiedIdentity:
    provider: str
    subject: str
    phone_number: str  # E.164, verified by the provider


class IdentityError(Exception):
    """The credential was not valid. `reason` is for logs only, never shown to users."""

    def __init__(self, reason: str, public_code: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.public_code = public_code  # safe to show: invalid_code / code_expired / too_many_attempts


class IdentityVerifier(Protocol):
    name: str

    def verify(self, credential: str) -> VerifiedIdentity: ...


def get_verifier(name: str) -> IdentityVerifier:
    path = settings.CLICK_IDENTITY_PROVIDERS.get(name)
    if not path:
        raise IdentityError(f"provider '{name}' is not enabled")
    return import_string(path)()
