"""Gift cards: bought only when paid, delivered to the recipient's account or shared by code, redeemed once by one
customer, spent server-side on eligible orders (never below zero, never twice), refunded to the card on cancel."""

import uuid
from datetime import timedelta
from decimal import Decimal as D

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.giftcards import services
from apps.giftcards.models import GiftCard, GiftCardDesign
from apps.wallet.models import WalletTransaction

pytestmark = pytest.mark.django_db


@pytest.fixture
def design(db):
    return GiftCardDesign.objects.create(title="Click. Gift Card", category="click", colors=["#000", "#333"], presets=[500, 1000],
                                         services=["food", "groceries", "shop"], min_amount=D("100"), max_amount=D("10000"))


def fund(user, amount="5000"):
    WalletTransaction.objects.create(customer=user.customer_profile, kind="adjustment", amount=D(amount), description="Opening balance")


def buy(api, design, **kw):
    body = {"designId": str(design.id), "amount": "500", "recipientName": "Ravi", "delivery": "share", "paymentMethod": "wallet",
            "idempotencyKey": str(uuid.uuid4()), **kw}
    return api.post("/api/v1/customer/gift-cards", body, format="json")


def client(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def test_buy_with_wallet_delivers_to_recipient_by_phone_and_redeem_is_once(customer, other_customer, design):
    fund(customer)
    other_customer.phone, other_customer.phone_verified = "+919000000055", True
    other_customer.save()
    a = client(customer)
    r = buy(a, design, delivery="click", recipientPhone="+919000000055")
    assert r.status_code == 201, r.content
    card = GiftCard.objects.get(pk=r.json()["id"])
    assert card.status == "active" and card.holder == other_customer.customer_profile and services.balance(card) == D("500")
    assert r.json()["code"].startswith("••••")  # the buyer never sees the code of a card already delivered to someone
    b = client(other_customer)
    held = b.get("/api/v1/customer/gift-cards").json()["held"]
    assert held[0]["balance"] == "500.00" and not held[0]["code"].startswith("••••")
    third = client(__import__("conftest").make_customer("third@example.com"))
    assert third.post("/api/v1/customer/gift-cards/redeem", {"code": card.code}).json()["error"]["code"] == "giftcard_redeemed"
    assert third.get(f"/api/v1/customer/gift-cards/{card.id}").status_code == 404


def test_shared_code_redeem_spend_on_order_and_refund_back(customer, other_customer, design, products, address):
    fund(customer)
    card_id = buy(client(customer), design).json()["id"]
    card = GiftCard.objects.get(pk=card_id)
    b = client(other_customer)
    assert b.post("/api/v1/customer/gift-cards/redeem", {"code": card.code.replace("-", "").lower()}).status_code == 200
    from apps.customers.models import Address

    addr = Address.objects.create(customer=other_customer.customer_profile, label="home", recipient_name="R", phone="+919000000000", line1="1 Rd",
                                  city="Bengaluru", postal_code="560001", latitude=12.9, longitude=77.6)
    b.post("/api/v1/customer/cart/items", {"productId": str(products[0].id), "quantity": 2})
    usable = b.get("/api/v1/customer/gift-cards/usable", {"service": "food"}).json()["results"]
    assert usable[0]["id"] == card_id
    r = b.post("/api/v1/customer/orders", {"addressId": str(addr.id), "paymentMethod": "gift_card", "giftCardId": card_id, "idempotencyKey": str(uuid.uuid4())})
    assert r.status_code == 201, r.content
    total = D(r.json()["total"])
    assert services.balance(card) == D("500") - total
    b.post(f"/api/v1/customer/orders/{r.json()['id']}/cancel", {"reason": "x"})
    assert services.balance(card) == D("500")  # refund goes back to the card, not to the wallet
    cust_c = client(customer)
    cust_c.post("/api/v1/customer/cart/items", {"productId": str(products[0].id), "quantity": 1})
    stolen = cust_c.post("/api/v1/customer/orders", {"addressId": str(address.id), "paymentMethod": "gift_card", "giftCardId": card_id, "idempotencyKey": str(uuid.uuid4())})
    assert stolen.json()["error"]["code"] == "giftcard_invalid"  # the buyer can't spend a card someone else redeemed


def test_insufficient_balance_scheduled_and_expiry(customer, design, products, address):
    fund(customer)
    a = client(customer)
    later = buy(a, design, deliverOn=(timezone.localdate() + timedelta(days=3)).isoformat()).json()
    assert later["status"] == "scheduled"
    assert a.post("/api/v1/customer/gift-cards/redeem", {"code": GiftCard.objects.get(pk=later["id"]).code}).json()["error"]["code"] == "giftcard_not_yet"
    small = buy(a, design, amount="100").json()
    a.post("/api/v1/customer/gift-cards/redeem", {"code": GiftCard.objects.get(pk=small["id"]).code})
    a.post("/api/v1/customer/cart/items", {"productId": str(products[0].id), "quantity": 2})
    r = a.post("/api/v1/customer/orders", {"addressId": str(address.id), "paymentMethod": "gift_card", "giftCardId": small["id"], "idempotencyKey": str(uuid.uuid4())})
    assert r.json()["error"]["code"] == "giftcard_insufficient"
    GiftCard.objects.filter(pk=small["id"]).update(expires_at=timezone.now() - timedelta(minutes=1))
    assert services.run_due()["expired"] == 1 and services.balance(GiftCard.objects.get(pk=small["id"])) == 0
    assert buy(a, design, amount="50").json()["error"]["code"] == "giftcard_amount"
