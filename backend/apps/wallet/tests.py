import uuid
from decimal import Decimal

import pytest

from apps.payments.models import Payment
from apps.wallet.models import WalletTransaction

pytestmark = pytest.mark.django_db


def credit(customer, amount):
    WalletTransaction.objects.create(customer=customer.customer_profile, kind="promo", amount=Decimal(amount), description="Welcome credit")


def place(api, address, method="wallet"):
    return api.post("/api/v1/customer/orders", {"addressId": str(address.id), "paymentMethod": method, "idempotencyKey": str(uuid.uuid4())})


def test_wallet_starts_empty_and_is_isolated(api, customer, other_customer, settings):
    settings.CLICK_PAYMENT_SANDBOX = False  # no payment provider configured → adding money is honestly unavailable
    credit(customer, "100.00")
    api.force_authenticate(other_customer)
    assert api.get("/api/v1/customer/wallet").json()["balance"] == "0.00"
    api.force_authenticate(customer)
    body = api.get("/api/v1/customer/wallet").json()
    assert body["balance"] == "100.00" and body["topUpAvailable"] is False
    api.force_authenticate(None)
    assert api.get("/api/v1/customer/wallet").status_code == 401


def test_pay_order_with_wallet_then_refund_on_cancel(auth_api, customer, products, address):
    credit(customer, "500.00")
    auth_api.post("/api/v1/customer/cart/items", {"productId": str(products[0].id), "quantity": 1})  # total 156.00
    order = place(auth_api, address).json()
    assert order["payments"][0]["status"] == "captured" and order["payments"][0]["method"] == "wallet"
    assert auth_api.get("/api/v1/customer/wallet").json()["balance"] == "344.00"

    auth_api.post(f"/api/v1/customer/orders/{order['id']}/cancel")
    assert auth_api.get("/api/v1/customer/wallet").json()["balance"] == "500.00"
    assert Payment.objects.get().status == "refunded"
    kinds = [t["kind"] for t in auth_api.get("/api/v1/customer/wallet").json()["transactions"]]
    assert kinds == ["refund", "payment", "promo"]


def test_insufficient_wallet_balance_rolls_back_order(auth_api, customer, products, address):
    from apps.orders.models import Order

    credit(customer, "10.00")
    auth_api.post("/api/v1/customer/cart/items", {"productId": str(products[0].id), "quantity": 1})
    r = place(auth_api, address)
    assert r.status_code == 400 and r.json()["error"]["code"] == "insufficient_wallet_balance"
    assert Order.objects.count() == 0 and auth_api.get("/api/v1/customer/cart").json()["itemCount"] == 1


def test_wallet_sign_constraint():
    from django.db import IntegrityError

    from conftest import make_customer

    c = make_customer("z@example.com")
    with pytest.raises(IntegrityError):
        WalletTransaction.objects.create(customer=c.customer_profile, kind="promo", amount=Decimal("-5"), description="bad")
