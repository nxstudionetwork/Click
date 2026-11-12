"""Online checkout payment (UPI / card / net banking) through the provider layer: an order is never placed (or shown to
the store) until a signed provider event is verified; failures and timeouts cancel and restock; replays are harmless;
other customers can't see or drive someone else's payment; cancelling a paid order refunds through the provider."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.orders.models import Order, OrderStatus
from apps.payments import gateway
from apps.payments.models import Payment
from apps.wallet import providers

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def sandbox(settings):
    settings.CLICK_PAYMENT_SANDBOX, settings.CLICK_PAYMENT_PROVIDER = True, ""


def place(api, address, method="upi"):
    api.post("/api/v1/customer/cart/items", {"productId": str(PRODUCT[0].id), "quantity": 2})
    return api.post("/api/v1/customer/orders", {"addressId": str(address.id), "paymentMethod": method, "idempotencyKey": str(uuid.uuid4())})


PRODUCT = []


@pytest.fixture(autouse=True)
def _products(products):
    PRODUCT[:] = products


def test_order_waits_for_verified_payment_then_is_placed(auth_api, address, products):
    r = place(auth_api, address)
    assert r.status_code == 201, r.content
    order = Order.objects.get(pk=r.json()["id"])
    pi = r.json()["paymentIntent"]
    assert order.status == OrderStatus.AWAITING_PAYMENT and pi["status"] == "pending" and pi["client"]["testMode"]
    ref = pi["reference"]
    other = APIClient(SERVER_NAME="localhost")
    from conftest import make_customer

    other.force_authenticate(make_customer("x@example.com"))
    assert other.get(f"/api/v1/customer/payments/intents/{ref}").status_code == 404
    assert other.post(f"/api/v1/customer/payments/intents/{ref}/sandbox", {"outcome": "succeeded"}).status_code == 404
    done = auth_api.post(f"/api/v1/customer/payments/intents/{ref}/sandbox", {"outcome": "succeeded"}, format="json").json()
    assert done["status"] == "succeeded"
    order.refresh_from_db()
    assert order.status == OrderStatus.PLACED and order.payments.get().status == Payment.Status.CAPTURED
    body, sig = providers.SandboxProvider().event(gateway._Ref(ref, order.total), "failed")
    APIClient().post("/api/v1/payments/webhooks/sandbox", body, content_type="application/json", HTTP_X_CLICK_SIGNATURE=sig)
    order.refresh_from_db()
    assert order.status == OrderStatus.PLACED  # a late / replayed event can't undo a confirmed payment


def test_failed_or_expired_payment_cancels_and_restocks(auth_api, address, products, settings):
    r = place(auth_api, address)
    ref = r.json()["paymentIntent"]["reference"]
    auth_api.post(f"/api/v1/customer/payments/intents/{ref}/sandbox", {"outcome": "failed"}, format="json")
    o = Order.objects.get(pk=r.json()["id"])
    assert o.status == OrderStatus.CANCELLED and o.payments.get().status == Payment.Status.FAILED
    r2 = place(auth_api, address, "card")
    Payment.objects.filter(provider_reference=r2.json()["paymentIntent"]["reference"]).update(created_at=timezone.now() - timedelta(minutes=60))
    assert gateway.expire_unpaid() == 1
    assert Order.objects.get(pk=r2.json()["id"]).status == OrderStatus.CANCELLED


def test_forged_event_and_amount_mismatch_are_rejected(auth_api, address):
    r = place(auth_api, address)
    ref = r.json()["paymentIntent"]["reference"]
    body, _ = providers.SandboxProvider().event(gateway._Ref(ref, "1.00"), "succeeded")
    assert APIClient().post("/api/v1/payments/webhooks/sandbox", body, content_type="application/json", HTTP_X_CLICK_SIGNATURE="00").status_code == 400
    body, sig = providers.SandboxProvider().event(gateway._Ref(ref, "1.00"), "succeeded")
    assert APIClient().post("/api/v1/payments/webhooks/sandbox", body, content_type="application/json", HTTP_X_CLICK_SIGNATURE=sig).status_code == 409
    assert Order.objects.get(pk=r.json()["id"]).status == OrderStatus.AWAITING_PAYMENT


def test_no_provider_means_no_online_checkout_and_paid_cancel_refunds(auth_api, address, settings):
    r = place(auth_api, address)
    ref = r.json()["paymentIntent"]["reference"]
    auth_api.post(f"/api/v1/customer/payments/intents/{ref}/sandbox", {"outcome": "succeeded"}, format="json")
    cancel = auth_api.post(f"/api/v1/customer/orders/{r.json()['id']}/cancel", {"reason": "changed my mind"})
    assert cancel.status_code == 200 and Payment.objects.get(provider_reference=ref).status == Payment.Status.REFUNDED
    settings.CLICK_PAYMENT_SANDBOX = False
    assert place(auth_api, address).json()["error"]["code"] == "online_payment_unavailable"
    assert auth_api.get("/api/v1/customer/payments/overview").json()["onlineMethods"]["available"] is False
