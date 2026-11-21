import uuid

import pytest
from rest_framework.test import APIClient

from apps.orders.models import Order, OrderStatus
from apps.orders.services import transition_order

pytestmark = pytest.mark.django_db


def place(api, address, products, method="cash_on_delivery"):
    api.post("/api/v1/customer/cart/items", {"productId": str(products[0].id), "quantity": 2})
    return Order.objects.get(pk=api.post("/api/v1/customer/orders", {"addressId": str(address.id), "paymentMethod": method,
                                                                         "idempotencyKey": str(uuid.uuid4())}).json()["id"])


def deliver(order):
    for s in [OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED]:
        order = transition_order(order, s)
    return order


def test_invoice_only_once_paid_owner_only_and_matches_the_order(auth_api, customer, other_customer, address, products):
    order = place(auth_api, address, products)
    cards = auth_api.get("/api/v1/customer/invoices").json()["results"]
    assert cards[0]["invoiceStatus"] == "pending" and cards[0]["id"] is None  # cash on delivery: not paid yet
    deliver(order)
    card = auth_api.get("/api/v1/customer/invoices").json()["results"][0]
    assert card["invoiceStatus"] == "generated" and card["number"].startswith("INV-") and card["reference"] == order.number
    d = auth_api.get(f"/api/v1/customer/invoices/{card['id']}").json()
    assert d["totals"]["total"] == f"{order.total:.2f}" and d["lines"][0]["quantity"] == 2 and d["seller"]["name"] == order.store.name
    assert "not a GST tax invoice" in d["gstNote"] and d["title"] == "Invoice"
    assert auth_api.get("/api/v1/customer/invoices", {"q": card["number"]}).json()["results"][0]["number"] == card["number"]
    other = APIClient()
    other.force_authenticate(other_customer)
    assert other.get(f"/api/v1/customer/invoices/{card['id']}").status_code == 404
    assert other.get(f"/api/v1/customer/invoices/{card['id']}/document").status_code == 404
    doc = auth_api.get(f"/api/v1/customer/invoices/{card['id']}/document")
    assert doc.status_code == 200 and card["number"].encode() in doc.content and b"attachment" in doc["Content-Disposition"].encode()


def test_refund_shows_a_refund_document(auth_api, customer, address, products):
    from decimal import Decimal

    from apps.wallet.models import WalletTransaction

    WalletTransaction.objects.create(customer=customer.customer_profile, kind="adjustment", amount=Decimal("5000"), description="Opening balance")
    order = place(auth_api, address, products, "wallet")
    auth_api.post(f"/api/v1/customer/orders/{order.id}/cancel", {"reason": "x"})
    card = auth_api.get("/api/v1/customer/invoices").json()["results"][0]
    assert card["invoiceStatus"] == "refund_document" and card["refunded"]
    d = auth_api.get(f"/api/v1/customer/invoices/{card['id']}").json()
    assert d["refunds"][0]["number"].startswith("CN-") and d["refunds"][0]["to"] == "Click. Wallet"


def test_reviews_only_for_completed_purchases_once(auth_api, customer, other_customer, address, products):
    order = place(auth_api, address, products)
    body = {"kind": "order", "targetId": str(order.id), "rating": 5}
    assert auth_api.post("/api/v1/customer/reviews", body, format="json").json()["error"]["code"] == "review_not_allowed"  # not delivered yet
    deliver(order)
    pending = auth_api.get("/api/v1/customer/reviews").json()["pending"]
    assert any(p["targetId"] == str(order.id) for p in pending)
    other = APIClient()
    other.force_authenticate(other_customer)
    assert other.post("/api/v1/customer/reviews", body, format="json").status_code == 404  # not their order
    r = auth_api.post("/api/v1/customer/reviews", {**body, "liked": "Hot and fresh", "better": "More raita"}, format="json")
    assert r.status_code == 201 and r.json()["mine"][0]["rating"] == 5 and "Could be better: More raita" in r.json()["mine"][0]["comment"]
    assert not any(p["targetId"] == str(order.id) for p in r.json()["pending"])
    assert auth_api.post("/api/v1/customer/reviews", body, format="json").json()["error"]["code"] == "review_exists"


@pytest.mark.django_db(transaction=True)
def test_invoice_issued_on_capture_review_reminder_activity_and_jobs(auth_api, customer, address, products):
    from django.core.management import call_command

    from apps.invoices.models import Invoice
    from apps.notifications.models import Notification

    order = deliver(place(auth_api, address, products))
    assert Invoice.objects.filter(payment__order=order).exists()  # issued when the cash was collected, not only when viewed
    assert Notification.objects.filter(customer=customer.customer_profile, title__startswith="How was your order").exists()
    r = auth_api.post("/api/v1/customer/reviews", {"kind": "order", "targetId": str(order.id), "rating": 4}, format="json")
    assert r.status_code == 201 and Notification.objects.filter(title="Thanks — your review is published").exists()
    rows = auth_api.get("/api/v1/customer/activity", {"category": "reviews"}).json()["results"]
    assert rows and rows[0]["title"].startswith("Reviewed ")
    call_command("click_jobs")  # every scheduled job runs cleanly
