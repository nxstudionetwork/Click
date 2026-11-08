"""
Pluggable identity verification. A provider turns a client-supplied credential
(e.g. a Firebase ID token) into a VerifiedIdentity, or raises IdentityError.
Swapping Firebase for another phone-OTP provider = add a verifier class and
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

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class IdentityVerifier(Protocol):
    name: str

    def verify(self, credential: str) -> VerifiedIdentity: ...


def get_verifier(name: str) -> IdentityVerifier:
    path = settings.CLICK_IDENTITY_PROVIDERS.get(name)
    if not path:
        raise IdentityError(f"provider '{name}' is not enabled")
    return import_string(path)()
