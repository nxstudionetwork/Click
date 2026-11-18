import uuid

import pytest
from rest_framework.test import APIClient

from apps.orders.models import Order, OrderStatus
from apps.orders.services import transition_order
from apps.referrals.models import Referral
from apps.rewards.services import balance
from conftest import otp_credential

pytestmark = pytest.mark.django_db
ADDR = {"label": "home", "recipientName": "Meera", "phone": "+919000011111", "line1": "1 Road", "city": "Bengaluru", "postalCode": "560001",
        "latitude": "12.97", "longitude": "77.59", "isDefault": True}


def signup(phone, code=""):
    api = APIClient()
    st = api.post("/api/v1/auth/identity/exchange", {"provider": "phone_otp", "token": otp_credential(api, phone)}).json()["signupToken"]
    r = api.post("/api/v1/auth/identity/signup", {"signupToken": st, "fullName": "Meera Rao", "email": f"{phone[-4:]}@example.com",
                                                  "addresses": [ADDR], "referralCode": code}, format="json")
    assert r.status_code == 201, r.content
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
    return api


def test_new_customer_ids_are_sequential_and_referral_rewards_once_on_first_delivery(auth_api, customer, products, settings):
    code = auth_api.get("/api/v1/customer/referrals").json()["code"]
    assert APIClient().get(f"/api/v1/referrals/{code}").json()["inviter"] == "Asha"
    assert APIClient().get("/api/v1/referrals/NOPE123").status_code == 404
    friend = signup("+919000022222", code)
    me = friend.get("/api/v1/me").json()
    assert me["customerCode"].startswith("CL-CU-") and len(me["customerCode"]) == 12
    ref = Referral.objects.get()
    assert ref.referrer == customer.customer_profile and ref.status == "joined"
    from apps.customers.models import Address

    addr = Address.objects.filter(customer=ref.referee).first()
    friend.post("/api/v1/customer/cart/items", {"productId": str(products[0].id), "quantity": 2})
    order = Order.objects.get(pk=friend.post("/api/v1/customer/orders", {"addressId": str(addr.id), "paymentMethod": "cash_on_delivery",
                                                                         "idempotencyKey": str(uuid.uuid4())}).json()["id"])
    for s in [OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED]:
        order = transition_order(order, s)
    ref.refresh_from_db()
    assert ref.status == "rewarded"
    assert balance(customer.customer_profile)["balance"] == settings.CLICK_REFERRAL_REFERRER_POINTS
    before = balance(ref.referee)["balance"]
    assert before >= settings.CLICK_REFERRAL_REFEREE_POINTS
    from apps.referrals.services import qualify

    assert qualify(order) is False  # once only
    rows = auth_api.get("/api/v1/customer/referrals").json()
    assert rows["referrals"][0]["name"] == "Meera" and rows["earnedPoints"] == settings.CLICK_REFERRAL_REFERRER_POINTS


def test_bad_codes_never_block_signup_and_cap_holds(auth_api, settings):
    signup("+919000033333", "WRONG99")
    assert Referral.objects.count() == 0
    code = auth_api.get("/api/v1/customer/referrals").json()["code"]
    settings.CLICK_REFERRAL_MONTHLY_CAP = 0
    signup("+919000044444", code.lower())
    r = Referral.objects.get()
    from apps.referrals.services import qualify

    class O:  # a delivered first order for the referee
        customer = r.referee
        pk = None
    assert qualify(O) is False and Referral.objects.get().status == "not_eligible"


def test_preferences_and_analytics_are_allow_listed(auth_api, customer):
    from apps.analytics.models import AnalyticsEvent

    r = auth_api.patch("/api/v1/customer/preferences", {"language": "te", "personalized": False}, format="json").json()
    assert r["language"] == "te" and r["personalized"] is False and {"en", "hi", "te"} == {x["code"] for x in r["languages"]}
    assert auth_api.patch("/api/v1/customer/preferences", {"language": "xx"}, format="json").status_code == 400
    auth_api.get("/api/v1/search/global", {"q": "paneer"})
    assert customer.customer_profile.search_history.count() == 0  # not personalised: searches aren't kept
    body = {"session": "s-123", "platform": "web", "events": [
        {"name": "product_viewed", "props": {"product_id": "abc-123", "service": "food", "email": "x@y.com"}},
        {"name": "search_performed", "props": {"group": "My phone is 98765 43210", "results": 4}},
        {"name": "not_an_event", "props": {}}]}
    assert APIClient().post("/api/v1/analytics/events", body, format="json").json()["accepted"] == 2
    pv = AnalyticsEvent.objects.get(name="product_viewed")
    assert pv.props == {"product_id": "abc-123", "service": "food"}  # unknown keys dropped
    assert AnalyticsEvent.objects.get(name="search_performed").props == {"results": 4}  # free text dropped
