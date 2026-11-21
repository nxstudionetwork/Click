"""Real-provider readiness: Razorpay orders, Checkout data, webhook signature and event mapping, refunds; MSG91 and
Twilio OTP senders. External calls are mocked; nothing here needs keys or the network."""

import hashlib
import hmac
import json
import uuid
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.identity import sms, sms_providers
from apps.orders.models import Order, OrderStatus
from apps.payments import razorpay
from apps.payments.models import Payment

pytestmark = pytest.mark.django_db
KEYS = {"RAZORPAY_KEY_ID": "rzp_test_abc", "RAZORPAY_KEY_SECRET": "secret", "RAZORPAY_WEBHOOK_SECRET": "whsec"}


@pytest.fixture
def rzp(settings, monkeypatch):
    settings.CLICK_PAYMENT_PROVIDER, settings.CLICK_PAYMENT_SANDBOX = "razorpay", False
    for k, v in KEYS.items():
        monkeypatch.setenv(k, v)
    calls = []

    def fake(self, method, path, body=None):
        calls.append((method, path, body))
        if path == "/orders":
            return {"id": "order_TEST123"}
        if path.endswith("/payments"):
            return {"items": [{"id": "pay_1", "status": "captured"}]}
        return {"id": "rfnd_1"}

    monkeypatch.setattr(razorpay.RazorpayProvider, "_call", fake)
    return calls


def _webhook(event, order_id, amount_paise):
    body = json.dumps({"event": event, "payload": {"payment": {"entity": {"id": "pay_1", "order_id": order_id, "amount": amount_paise,
                                                                           "error_description": "Bank declined"}}}}).encode()
    return body, hmac.new(b"whsec", body, hashlib.sha256).hexdigest()


def test_razorpay_checkout_end_to_end(auth_api, address, products, rzp):
    auth_api.post("/api/v1/customer/cart/items", {"productId": str(products[0].id), "quantity": 2})
    r = auth_api.post("/api/v1/customer/orders", {"addressId": str(address.id), "paymentMethod": "upi", "idempotencyKey": str(uuid.uuid4())})
    assert r.status_code == 201, r.content
    pi = r.json()["paymentIntent"]
    order = Order.objects.get(pk=r.json()["id"])
    assert pi["reference"] == "order_TEST123" and pi["client"]["provider"] == "razorpay" and pi["client"]["keyId"] == "rzp_test_abc"
    assert pi["client"]["amount"] == int(order.total * 100) and rzp[0][2]["amount"] == int(order.total * 100)
    # A forged webhook is refused; the real one places the order.
    body, sig = _webhook("payment.captured", "order_TEST123", int(order.total * 100))
    assert APIClient().post("/api/v1/payments/webhooks/razorpay", body, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE="bad").status_code == 400
    ok = APIClient().post("/api/v1/payments/webhooks/razorpay", body, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE=sig)
    assert ok.status_code == 200 and ok.json()["status"] == "succeeded"
    order.refresh_from_db()
    assert order.status == OrderStatus.PLACED and order.payments.get().status == Payment.Status.CAPTURED
    # Unhandled events are acknowledged without changing anything.
    body, sig = _webhook("payment.authorized", "order_TEST123", 1)
    assert APIClient().post("/api/v1/payments/webhooks/razorpay", body, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE=sig).json()["status"] == "ignored"
    # Refund goes to the captured Razorpay payment.
    assert razorpay.RazorpayProvider().refund(order.payments.get()) == "rfnd_1"
    assert rzp[-1][1] == "/payments/pay_1/refund"


def test_razorpay_failed_payment_cancels(auth_api, address, products, rzp):
    auth_api.post("/api/v1/customer/cart/items", {"productId": str(products[0].id), "quantity": 1})
    r = auth_api.post("/api/v1/customer/orders", {"addressId": str(address.id), "paymentMethod": "card", "idempotencyKey": str(uuid.uuid4())}).json()
    body, sig = _webhook("payment.failed", "order_TEST123", 100)
    assert APIClient().post("/api/v1/payments/webhooks/razorpay", body, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE=sig).json()["status"] == "failed"
    assert Order.objects.get(pk=r["id"]).status == OrderStatus.CANCELLED


def test_razorpay_without_keys_means_no_online_payment(settings, monkeypatch):
    settings.CLICK_PAYMENT_PROVIDER, settings.CLICK_PAYMENT_SANDBOX = "razorpay", False
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    from apps.wallet import providers

    assert providers.current() is None


def test_sms_senders_need_their_keys_and_send_the_code(settings, monkeypatch):
    settings.CLICK_SMS_PROVIDER = "msg91"
    monkeypatch.delenv("MSG91_AUTH_KEY", raising=False)
    assert sms.current() is None  # not configured: sign-in says unavailable, nothing is faked
    monkeypatch.setenv("MSG91_AUTH_KEY", "k")
    monkeypatch.setenv("MSG91_TEMPLATE_ID", "t1")
    sent = []
    monkeypatch.setattr(sms_providers, "_post", lambda url, data, headers: sent.append((url, json.loads(data), headers)) or {"type": "success"})
    sms.current().send("+919876543210", "482913 is your Click. verification code.")
    url, body, headers = sent[0]
    assert "msg91" in url and body["recipients"] == [{"mobiles": "919876543210", "otp": "482913"}] and headers["authkey"] == "k"

    settings.CLICK_SMS_PROVIDER = "twilio"
    for k, v in {"TWILIO_ACCOUNT_SID": "AC1", "TWILIO_AUTH_TOKEN": "tok", "TWILIO_FROM": "+15005550006"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(sms_providers, "_post", lambda url, data, headers: sent.append((url, data, headers)) or {"sid": "SM1"})
    sms.current().send("+919876543210", "111222 is your Click. verification code.")
    assert "Accounts/AC1/Messages.json" in sent[-1][0] and b"To=%2B919876543210" in sent[-1][1]
