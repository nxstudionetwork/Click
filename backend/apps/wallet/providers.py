"""
Payment providers for adding money to the Click. Wallet. A provider creates an intent, collects the payment on its own
page / app, and confirms the result with a *signed* event to /api/v1/payments/webhooks/<provider>. Click. credits the
wallet only after that signature is verified (apps.wallet.services.apply_provider_result), and only once.

  sandbox   test mode for development: Click. plays the provider. The customer approves or declines a test payment and
            the outcome is sent through exactly the same signed-event path. Enabled only when CLICK_PAYMENT_SANDBOX is on
            (DEBUG by default) — never in production, where no money would move.
  (real)    a UPI / card gateway implements the same four methods and is chosen with CLICK_PAYMENT_PROVIDER; its keys
            stay in server settings. None is connected yet.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets

from django.conf import settings


def _secret() -> bytes:
    return (settings.CLICK_PAYMENT_WEBHOOK_SECRET or settings.SECRET_KEY).encode()


def sign(body: bytes) -> str:
    return hmac.new(_secret(), body, hashlib.sha256).hexdigest()


def verify(body: bytes, signature: str) -> bool:
    return bool(signature) and hmac.compare_digest(sign(body), signature)


class SandboxProvider:
    name = "sandbox"
    methods = ("upi", "card", "netbanking")
    test_mode = True

    def create_intent(self, topup) -> str:
        return "SBX-" + secrets.token_hex(6).upper()

    def client_data(self, topup) -> dict:
        return {"provider": self.name, "test_mode": True, "reference": topup.provider_reference,
                "instructions": "Test mode: approve or decline a test payment. No real money moves."}

    def event(self, topup, outcome: str, reason: str = "") -> tuple[bytes, str]:
        body = json.dumps({"reference": topup.provider_reference, "outcome": outcome, "amount": str(topup.amount), "reason": reason},
                          sort_keys=True).encode()
        return body, sign(body)


def current():
    name = getattr(settings, "CLICK_PAYMENT_PROVIDER", "") or ("sandbox" if settings.CLICK_PAYMENT_SANDBOX else "")
    if name == "sandbox" and settings.CLICK_PAYMENT_SANDBOX:
        return SandboxProvider()
    return None


def handle_event(body: bytes, signature: str):
    """Verify a provider event and apply it. Raises on a bad signature; replays are harmless."""
    from decimal import Decimal

    from apps.core.api.exceptions import DomainError

    from .services import apply_provider_result

    if not verify(body, signature):
        raise DomainError("Invalid signature.", code="invalid_signature", status_code=400)
    data = json.loads(body)
    return apply_provider_result(str(data["reference"]), str(data["outcome"]), Decimal(str(data["amount"])), str(data.get("reason") or ""))
