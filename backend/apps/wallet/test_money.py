"""Wallet, Payments, Rewards, Offers, Notifications, Activity and Support — the scenarios their specs list: verified top-ups
(success, failure, replayed callback), spending (promo first, insufficient balance), refunds back to their bucket,
cashback, expiry, ownership, payments separation, rewards redemption / missions / reversal, notification read state and
preferences, the activity timeline, support requests (ownership, attachments, rate limit) and offer save / claim."""

import uuid
from datetime import timedelta
from decimal import Decimal as D

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.notifications.models import Notification
from apps.payments.models import Payment
from apps.rewards import services as rewards
from apps.rewards.models import RewardCatalogItem, RewardMission, RewardTransaction
from apps.wallet import providers, services as wallet
from apps.wallet.models import CashbackOffer, WalletAccount, WalletTransaction as T
from conftest import make_customer

pytestmark = pytest.mark.django_db


def client(user):
    c = APIClient(SERVER_NAME="localhost")
    c.force_authenticate(user)
    return c


def cash(user, amount):
    return T.objects.create(customer=user.customer_profile, kind="adjustment", bucket="cash", amount=D(amount), description="Opening balance")


def promo(user, amount, days=30):
    return T.objects.create(customer=user.customer_profile, kind="promo", bucket="promo", amount=D(amount), description="Welcome credit",
                            expires_at=timezone.now() + timedelta(days=days))


def topup(api, amount="500"):
    return api.post("/api/v1/customer/wallet/top-ups", {"amount": amount, "method": "upi", "idempotencyKey": str(uuid.uuid4())}, format="json")


@pytest.fixture(autouse=True)
def sandbox(settings):
    settings.CLICK_PAYMENT_SANDBOX = True
    settings.CLICK_PAYMENT_PROVIDER = ""


def test_topup_only_after_verified_confirmation_and_once(customer):
    api = client(customer)
    r = topup(api).json()
    assert r["status"] == "created" and wallet.balance(customer.customer_profile) == 0  # an intent never credits
    t = api.post(f"/api/v1/customer/wallet/top-ups/{r['id']}/sandbox", {"outcome": "succeeded"}, format="json").json()
    assert t["status"] == "succeeded" and wallet.balance(customer.customer_profile) == D("500")
    from apps.wallet.models import WalletTopUp

    tu = WalletTopUp.objects.get(pk=r["id"])
    body, sig = providers.SandboxProvider().event(tu, "succeeded")
    replay = APIClient(SERVER_NAME="localhost").post("/api/v1/payments/webhooks/sandbox", body, content_type="application/json", HTTP_X_CLICK_SIGNATURE=sig)
    assert replay.status_code == 200 and wallet.balance(customer.customer_profile) == D("500")  # duplicate callback: no second credit
    forged = APIClient(SERVER_NAME="localhost").post("/api/v1/payments/webhooks/sandbox", body, content_type="application/json", HTTP_X_CLICK_SIGNATURE="00")
    assert forged.status_code == 400
    p = Payment.objects.get(pk=r["paymentId"])
    assert p.status == "captured" and p.method == "upi"  # Payments records how it was paid; Wallet records the credit
    assert api.get(f"/api/v1/customer/payments/{p.id}").json()["label"] == "Wallet top-up"


def test_failed_topup_and_limits(customer, settings):
    api = client(customer)
    r = topup(api).json()
    t = api.post(f"/api/v1/customer/wallet/top-ups/{r['id']}/sandbox", {"outcome": "failed"}, format="json").json()
    assert t["status"] == "failed" and wallet.balance(customer.customer_profile) == 0
    assert Payment.objects.get(pk=r["paymentId"]).status == "failed"
    assert topup(api, "50").json()["error"]["code"] == "topup_amount"
    settings.CLICK_WALLET_DAILY_TOPUP_LIMIT = "600"
    ok = topup(api, "500").json()
    api.post(f"/api/v1/customer/wallet/top-ups/{ok['id']}/sandbox", {"outcome": "succeeded"}, format="json")
    assert topup(api, "200").json()["error"]["code"] == "topup_daily_limit"
    settings.CLICK_PAYMENT_SANDBOX = False
    assert topup(api).status_code == 503  # no provider: adding money is honestly unavailable


def test_spend_promo_first_insufficient_and_refund_to_same_bucket(customer):
    c = customer.customer_profile
    cash(customer, "500")
    promo(customer, "100")
    from apps.wallet.models import WalletTopUp  # a payment needs a target; a top-up record is the simplest owned one

    holder = WalletTopUp.objects.create(customer=c, amount=D("1"), method="upi", provider="sandbox", idempotency_key="x")
    p = Payment.objects.create(wallet_topup=holder, method="wallet", amount=D("400"))
    rows = wallet.pay(c, D("400"), p, "Order X")
    assert [(r.bucket, r.amount) for r in rows] == [("promo", D("-100")), ("cash", D("-300"))]
    assert wallet.balance(c) == D("200")
    p2 = Payment.objects.create(wallet_topup=holder, method="wallet", amount=D("300"))
    with pytest.raises(Exception):
        wallet.pay(c, D("300"), p2, "Too much")  # never negative
    assert wallet.balance(c) == D("200")
    wallet.refund(c, D("400"), p, "Refund for order X")
    b = wallet.breakdown(c)
    assert b["cash"] == D("500") and b["promo"] == D("100")  # promo spent comes back as promo, never as cash
    assert wallet.refund(c, D("400"), p, "again") is None


def test_expiry_cashback_restriction_and_ownership(customer, other_customer):
    c = customer.customer_profile
    lot = promo(customer, "80", days=1)
    T.objects.filter(pk=lot.id).update(expires_at=timezone.now() - timedelta(minutes=1))
    assert wallet.balance(c) == 0  # expired credit is never spendable
    wallet.sweep_expired(c)
    assert T.objects.filter(customer=c, kind="expiry").get().amount == D("-80")
    CashbackOffer.objects.create(title="5% back", service="shop", percent=5, max_cashback=D("50"), min_amount=D("100"),
                                 starts_at=timezone.now() - timedelta(days=1), ends_at=timezone.now() + timedelta(days=1))
    cb = wallet.award_cashback(c, "shop", D("2000"), "order:1", "Order 1", True)
    assert cb.amount == D("50") and cb.bucket == "promo"
    assert wallet.award_cashback(c, "shop", D("2000"), "order:1", "Order 1", True) is None  # once per purchase
    assert wallet.award_cashback(c, "shop", D("2000"), "order:2", "Order 2", False) is None  # wallet-only offer
    other = client(other_customer)
    assert other.get(f"/api/v1/customer/wallet/transactions/{cb.id}").status_code == 404
    WalletAccount.objects.update_or_create(customer=c, defaults={"status": "restricted", "status_reason": "Under review."})
    r = topup(client(customer)).json()
    assert r["error"]["code"] == "wallet_restricted" and "Under review" in r["error"]["message"]
    w = client(customer).get("/api/v1/customer/wallet").json()
    assert w["status"] == "restricted" and w["balance"] == "50.00" and w["topUpAvailable"] is False  # balance stays visible


def test_rewards_redeem_missions_and_reversal(customer):
    c = customer.customer_profile
    RewardTransaction.objects.create(customer=c, kind="earn", points=1200, description="Order", reference="seed",
                                     expires_at=timezone.now() + timedelta(days=300))
    item = RewardCatalogItem.objects.create(title="₹100 credit", points_cost=1000, value=D("100"))
    big = RewardCatalogItem.objects.create(title="₹500 credit", points_cost=5000, value=D("500"))
    api = client(customer)
    key = str(uuid.uuid4())
    r = api.post(f"/api/v1/customer/rewards/catalog/{item.id}/redeem", {"idempotencyKey": key}, format="json")
    assert r.status_code == 201 and r.json()["balance"] == 200
    again = api.post(f"/api/v1/customer/rewards/catalog/{item.id}/redeem", {"idempotencyKey": key}, format="json")
    assert again.json()["id"] == r.json()["id"] and rewards.balance(c)["balance"] == 200  # duplicate tap
    assert wallet.breakdown(c)["promo"] == D("100")  # linked wallet credit
    no = api.post(f"/api/v1/customer/rewards/catalog/{big.id}/redeem", {"idempotencyKey": str(uuid.uuid4())}, format="json")
    assert no.status_code == 409 and no.json()["error"]["code"] == "insufficient_points"
    RewardMission.objects.create(code="profile", title="Profile", description="", metric="profile", points=50)
    customer.full_name, customer.email = "Asha Rao", "asha@example.com"
    customer.save()
    from apps.customers.models import Address

    Address.objects.create(customer=c, label="home", recipient_name="Asha", phone="+91 90000 00000", line1="1 Road", city="Bengaluru",
                           postal_code="560001", latitude=12.9, longitude=77.6)
    assert rewards.check_missions(c) == 1 and rewards.check_missions(c) == 0  # awarded once
    earn = RewardTransaction.objects.create(customer=c, kind="earn", points=300, description="Order Y", reference="y",
                                            expires_at=timezone.now() + timedelta(days=300))
    rewards.reverse(earn, "refunded")
    assert rewards.reverse(earn, "refunded") is None and earn.reversals.get().points == -300
    hist = api.get("/api/v1/customer/rewards").json()
    assert hist["tier"]["code"] == "bronze" and any(m["completed"] for m in hist["missions"])


def test_notifications_read_state_preferences_and_ownership(customer, other_customer):
    from apps.notifications.services import notify

    c = customer.customer_profile
    n = notify(c, "orders", "Order confirmed", "", "/orders/x")
    notify(c, "wallet", "₹100 added", "", "/wallet")
    api = client(customer)
    assert api.get("/api/v1/customer/notifications/summary").json()["unread"] == 2
    assert client(other_customer).post(f"/api/v1/customer/notifications/{n.id}/read").status_code == 404
    api.post(f"/api/v1/customer/notifications/{n.id}/read")
    assert api.get("/api/v1/customer/notifications/summary").json()["unread"] == 1
    assert [x["title"] for x in api.get("/api/v1/customer/notifications", {"group": "wallet"}).json()["results"]] == ["₹100 added"]
    api.post("/api/v1/customer/notifications/read-all")
    assert api.get("/api/v1/customer/notifications/summary").json()["unread"] == 0
    api.patch("/api/v1/customer/notifications/preferences", {"muted": ["offers", "wallet"]}, format="json")
    assert api.get("/api/v1/customer/notifications/preferences").json()["muted"] == ["offers"]  # wallet can't be muted
    assert notify(c, "offers", "New deal") is None and notify(c, "wallet", "Debit") is not None


def test_activity_timeline_routes_and_failed_payment(customer, other_customer):
    from apps.wallet.models import WalletTopUp

    c = customer.customer_profile
    cash(customer, "100")
    t = WalletTopUp.objects.create(customer=c, amount=D("100"), method="upi", provider="sandbox", idempotency_key="f")
    Payment.objects.create(wallet_topup=t, method="upi", amount=D("100"), status="failed")
    api = client(customer)
    rows = api.get("/api/v1/customer/activity").json()["results"]
    pay = next(r for r in rows if r["category"] == "payments")
    assert pay["title"] == "Payment failed" and pay["tone"] == "bad" and pay["link"].startswith("/account/payments/")
    assert all(r["category"] == "wallet" for r in api.get("/api/v1/customer/activity", {"category": "wallet"}).json()["results"])
    assert client(other_customer).get("/api/v1/customer/activity").json()["results"] == []
    old = T.objects.create(customer=c, kind="adjustment", amount=D("1"), description="Needle entry")
    T.objects.filter(pk=old.id).update(created_at=timezone.now() - timedelta(days=30))
    for i in range(70):
        cash(customer, "1")
    found, cursor, pages = [], None, 0
    while pages < 5:  # a search keeps paging back past the newest rows instead of stopping early
        r = api.get("/api/v1/customer/activity", {"q": "needle", **({"cursor": cursor} if cursor else {})}).json()
        found += r["results"]
        cursor, pages = r["nextCursor"], pages + 1
        if found or not cursor:
            break
    assert [x["subtitle"] for x in found] == ["Needle entry"] and pages > 1


def test_support_requests_ownership_attachments_duplicates(customer, other_customer):
    c = customer.customer_profile
    w = cash(customer, "100")
    api = client(customer)
    body = {"category": "wallet", "issueType": "Transaction I don’t recognise", "subject": "Unknown entry", "message": "I don't recognise this.",
            "walletTransactionId": str(w.id)}
    r = api.post("/api/v1/customer/support/tickets", body, format="json")
    assert r.status_code == 201 and r.json()["priority"] == "urgent" and r.json()["related"]["type"] == "wallet_transaction"
    assert api.post("/api/v1/customer/support/tickets", body, format="json").json()["error"]["code"] == "duplicate_ticket"
    stolen = client(other_customer).post("/api/v1/customer/support/tickets", {**body, "subject": "x"}, format="json")
    assert stolen.status_code == 400  # can't attach someone else's wallet entry
    tid = r.json()["id"]
    assert client(other_customer).get(f"/api/v1/customer/support/tickets/{tid}").status_code == 404
    fake = SimpleUploadedFile("evil.png", b"<script>alert(1)</script>", content_type="image/png")
    assert api.post(f"/api/v1/customer/support/tickets/{tid}/messages", {"attachment": fake}, format="multipart").json()["error"]["code"] == "attachment_type"
    png = SimpleUploadedFile("shot.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32, content_type="image/png")
    ok = api.post(f"/api/v1/customer/support/tickets/{tid}/messages", {"body": "Screenshot", "attachment": png}, format="multipart")
    assert ok.status_code == 201 and ok.json()["attachment"]["type"] == "image/png"
    from apps.support.models import SupportMessage

    SupportMessage.objects.create(ticket_id=tid, sender="support", body="We’re checking this.")
    assert Notification.objects.filter(customer=c, title="Click. Support replied to your request").exists()
    from apps.support import articles

    articles.sync()
    found = api.get("/api/v1/support/articles", {"q": "refund"}).json()["results"]
    assert found and api.get(f"/api/v1/support/articles/{found[0]['slug']}").status_code == 200


def test_offers_hub_save_claim(customer):
    from apps.travel.models import TravelOffer

    o = TravelOffer.objects.create(mode="flight", title="FLY 8%", code="FLY8", percent=8, starts_at=timezone.now() - timedelta(days=1),
                                   ends_at=timezone.now() + timedelta(hours=10))
    api = client(customer)
    hub = api.get("/api/v1/offers/hub").json()
    row = next(x for x in hub["results"] if x["id"] == f"travel:{o.id}")
    assert "ending_soon" in row["badges"] and "coupon" in row["badges"] and row in hub["sections"]["coupons"]
    assert api.post(f"/api/v1/customer/offers/travel:{o.id}/save").status_code == 201
    assert api.post(f"/api/v1/customer/offers/travel:{o.id}/claim").json()["code"] == "FLY8"
    assert api.get("/api/v1/customer/offers/claimed", {"service": "travel"}).json()["results"][0]["code"] == "FLY8"
    mine = api.get("/api/v1/customer/offers/mine").json()
    assert mine["saved"][0]["id"] == f"travel:{o.id}" and mine["savings"]["offersUsed"] == 0
    assert api.post("/api/v1/customer/offers/travel:00000000-0000-0000-0000-000000000000/claim").status_code == 404




def test_buddy_money_intents_read_ledgers_and_never_act(customer):
    from apps.ai.buddy import ClickBasicBuddy
    from apps.ai.providers import AIContext, AIMessage

    c = customer.customer_profile
    cash(customer, "250")
    promo(customer, "40", days=3)
    ask = lambda q: ClickBasicBuddy().reply([AIMessage(role="user", content=q)], AIContext(surface="customer", actor_id="x", facts={}, customer=c))
    r = ask("what's my wallet balance?")
    assert "₹290" in r.content and "₹40 of promo credit expires within 7 days" in r.content
    r = ask("add money to my wallet")
    assert r.actions == [{"label": "Add money", "path": "/wallet?add=1"}] and wallet.balance(c) == D("290")  # opens the flow, adds nothing
    assert "can’t be withdrawn" in ask("withdraw my wallet balance to my bank").content
    assert ask("redeem my points").actions[0]["path"] == "/rewards?tab=redeem"
    assert "no open support requests" in ask("status of my support request").content
    assert "Wallet" not in ask("gold earrings").content  # shopping words aren't money intents
