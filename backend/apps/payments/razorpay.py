"""
Razorpay as Click.'s online payment provider (UPI, cards, net banking). Switched on with
CLICK_PAYMENT_PROVIDER=razorpay plus RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET and RAZORPAY_WEBHOOK_SECRET (environment only).

  intent   POST /v1/orders → the Razorpay order id is Click.'s provider reference for the payment
  client   the app opens Razorpay Checkout with {key_id, order_id, amount, currency}; card / UPI details go to Razorpay
  webhook  POST /api/v1/payments/webhooks/razorpay, verified with X-Razorpay-Signature (HMAC-SHA256 of the raw body);
           payment.captured / order.paid → succeeded, payment.failed → failed. Click. credits or places orders only here.
  refund   finds the captured payment of the order and calls POST /v1/payments/<id>/refund for the amount

The money and status always come from Razorpay's signed webhook, never from the browser.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import urllib.request
from decimal import ROUND_HALF_UP, Decimal

from apps.core.api.exceptions import DomainError

logger = logging.getLogger("click.payments")
API = "https://api.razorpay.com/v1"
TIMEOUT = 10


class RazorpayNotConfigured(Exception):
    pass


def _paise(amount) -> int:
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class RazorpayProvider:
    name = "razorpay"
    methods = ("upi", "card", "netbanking")
    test_mode = False

    def __init__(self):
        self.key_id = os.environ.get("RAZORPAY_KEY_ID", "").strip()
        self.key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "").strip()
        self.webhook_secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "").strip()
        if not (self.key_id and self.key_secret and self.webhook_secret):
            raise RazorpayNotConfigured("RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET and RAZORPAY_WEBHOOK_SECRET are required")
        self.test_mode = self.key_id.startswith("rzp_test_")

    # -- HTTP --------------------------------------------------------------------------------------------------------
    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        auth = base64.b64encode(f"{self.key_id}:{self.key_secret}".encode()).decode()
        req = urllib.request.Request(f"{API}{path}", data=json.dumps(body).encode() if body is not None else None, method=method,
                                     headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 — fixed provider URL
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            logger.error("razorpay %s %s failed: %s", method, path, e)
            raise DomainError("The payment provider didn’t respond. Please try again.", code="payment_provider_error", status_code=502) from e

    # -- provider interface ------------------------------------------------------------------------------------------
    def create_intent(self, target, amount=None) -> str:
        amount = amount if amount is not None else getattr(target, "amount", None)
        if amount is None:
            raise DomainError("Amount missing for payment.", code="payment_amount_missing")
        order = self._call("POST", "/orders", {"amount": _paise(amount), "currency": "INR",
                                               "receipt": f"click-{getattr(target, 'id', '') or 'checkout'}"[:40], "payment_capture": 1})
        return order["id"]

    def client_data(self, target) -> dict:
        return {"provider": self.name, "test_mode": self.test_mode, "key_id": self.key_id, "order_id": target.provider_reference,
                "amount": _paise(target.amount), "currency": "INR", "name": "Click.",
                "instructions": "Pay securely on Razorpay. Click. never sees your card number, CVV or UPI PIN."}

    def parse_event(self, body: bytes, headers) -> tuple[str, str, Decimal, str] | None:
        sig = headers.get("X-Razorpay-Signature", "")
        expected = hmac.new(self.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        if not sig or not hmac.compare_digest(expected, sig):
            raise DomainError("Invalid signature.", code="invalid_signature", status_code=400)
        data = json.loads(body)
        event = data.get("event", "")
        payment = ((data.get("payload") or {}).get("payment") or {}).get("entity") or {}
        order_id = payment.get("order_id") or (((data.get("payload") or {}).get("order") or {}).get("entity") or {}).get("id")
        if not order_id:
            return None
        amount = Decimal(payment.get("amount", 0)) / 100
        if event in ("payment.captured", "order.paid"):
            return order_id, "succeeded", amount, ""
        if event == "payment.failed":
            return order_id, "failed", amount, payment.get("error_description") or "Payment declined"
        return None  # other events (authorized, refunds…) need no action here

    def refund(self, payment) -> str:
        payments = self._call("GET", f"/orders/{payment.provider_reference}/payments").get("items", [])
        captured = next((p for p in payments if p.get("status") == "captured"), None)
        if captured is None:
            raise DomainError("No captured payment to refund.", code="refund_unavailable", status_code=409)
        r = self._call("POST", f"/payments/{captured['id']}/refund", {"amount": _paise(payment.amount), "speed": "normal"})
        return r["id"]
