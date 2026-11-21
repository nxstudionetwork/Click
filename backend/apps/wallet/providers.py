"""
Payment providers for adding money to the Click. Wallet. A provider creates an intent, collects the payment on its own
page / app, and confirms the result with a *signed* event to /api/v1/payments/webhooks/<provider>. Click. credits the
wallet only after that signature is verified (apps.wallet.services.apply_provider_result), and only once.

  sandbox   test mode for development: Click. plays the provider. The customer approves or declines a test payment and
            the outcome is sent through exactly the same signed-event path. Enabled only when CLICK_PAYMENT_SANDBOX is on
            (DEBUG by default) — never in production, where no money would move.
  razorpay  apps.payments.razorpay (CLICK_PAYMENT_PROVIDER=razorpay + RAZORPAY_* keys in the environment).

Every provider implements: create_intent(target, amount) -> reference, client_data(target), parse_event(body, headers)
-> (reference, outcome, amount, reason) | None after verifying its own signature, and refund(payment).
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

    def create_intent(self, target, amount=None) -> str:
        return "SBX-" + secrets.token_hex(6).upper()

    def parse_event(self, body: bytes, headers) -> tuple:
        from decimal import Decimal

        from apps.core.api.exceptions import DomainError

        if not verify(body, headers.get("X-Click-Signature", "")):
            raise DomainError("Invalid signature.", code="invalid_signature", status_code=400)
        data = json.loads(body)
        return str(data["reference"]), str(data["outcome"]), Decimal(str(data["amount"])), str(data.get("reason") or "")

    def client_data(self, topup) -> dict:
        return {"provider": self.name, "test_mode": True, "reference": topup.provider_reference,
                "instructions": "Test mode: approve or decline a test payment. No real money moves."}

    def refund(self, payment) -> str:
        """Test mode: the refund is accepted immediately. A real gateway calls its refund API here."""
        return "SBXR-" + secrets.token_hex(5).upper()

    def event(self, topup, outcome: str, reason: str = "") -> tuple[bytes, str]:
        body = json.dumps({"reference": topup.provider_reference, "outcome": outcome, "amount": str(topup.amount), "reason": reason},
                          sort_keys=True).encode()
        return body, sign(body)


def current():
    """The connected provider, or None (online payment then reports itself unavailable; nothing is faked)."""
    name = getattr(settings, "CLICK_PAYMENT_PROVIDER", "") or ("sandbox" if settings.CLICK_PAYMENT_SANDBOX else "")
    if name == "sandbox" and settings.CLICK_PAYMENT_SANDBOX:
        return SandboxProvider()
    if name == "razorpay":
        from apps.payments.razorpay import RazorpayNotConfigured, RazorpayProvider

        try:
            return RazorpayProvider()
        except RazorpayNotConfigured as e:
            import logging

            logging.getLogger("click.payments").error("Razorpay is selected but not ready: %s", e)
    return None


def apply(reference: str, outcome: str, amount, reason: str = ""):
    """Apply a verified outcome to a wallet top-up or to checkout payments (orders, gift cards)."""
    from .models import WalletTopUp
    from .services import apply_provider_result

    if WalletTopUp.objects.filter(provider_reference=reference).exists():
        return apply_provider_result(reference, outcome, amount, reason)
    from apps.payments.gateway import apply_result

    return apply_result(reference, outcome, amount, reason)


def handle_webhook(provider, body: bytes, headers) -> dict:
    """A provider's webhook: it verifies its own signature and maps its event; ignored events are acknowledged."""
    parsed = provider.parse_event(body, headers)
    if parsed is None:
        return {"received": True, "status": "ignored"}
    result = apply(*parsed)
    status = result.get("status") if isinstance(result, dict) else getattr(result, "status", "")
    return {"received": True, "status": status}


def handle_event(body: bytes, signature: str):
    """Verify a provider event and apply it. Raises on a bad signature; replays are harmless."""
    from decimal import Decimal

    from apps.core.api.exceptions import DomainError

    if not verify(body, signature):
        raise DomainError("Invalid signature.", code="invalid_signature", status_code=400)
    data = json.loads(body)
    return apply(str(data["reference"]), str(data["outcome"]), Decimal(str(data["amount"])), str(data.get("reason") or ""))
