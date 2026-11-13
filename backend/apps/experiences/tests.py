"""Click. Bookings: information-only places can't be booked, discovery and filters, slot / day availability with
capacity, closures and expiry, free darshan without payment, server pricing with GST and offers, price changes,
payment failure and hold, idempotency, entry code verified by the provider only, policy-based cancellation, verified
reviews, wishlist, and the central list of every booking."""

import uuid
from datetime import timedelta
from decimal import Decimal as D

import pytest
from rest_framework.test import APIClient

from apps.experiences import booking
from apps.experiences.models import Attraction, Closure, ExperienceBooking, ExperienceOffer, Offering, Price
from apps.partners.models import Partner, PartnerCategory, PartnerMembership
from apps.users.models import User
from apps.wallet.models import WalletTransaction
from conftest import make_customer

pytestmark = pytest.mark.django_db
CUST = "/api/v1/customer/experiences"
ALL = list(range(7))


def provider(name):
    from apps.partners.catalog import apply_catalog
    from apps.partners.models import PartnerType

    if not PartnerCategory.objects.exists():
        apply_catalog(PartnerType, PartnerCategory)
    pc = PartnerCategory.objects.select_related("partner_type").get(slug="ticketing-venue")
    user = User.objects.create_user(f"{uuid.uuid4().hex[:8]}@venue.test", "S3cure-pass-123", full_name=name)
    p = Partner.objects.create(partner_type=pc.partner_type, category=pc, business_name=name, status=Partner.Status.ACTIVE, is_available=True,
                               partner_code=f"CLK-PT-{uuid.uuid4().hex[:6]}")
    PartnerMembership.objects.create(partner=p, user=user, role="owner")
    c = APIClient(SERVER_NAME="localhost")
    c.force_authenticate(user)
    return p, c


@pytest.fixture
def places(db):
    temple_p, temple_api = provider("Temple Trust")
    park_p, park_api = provider("Splash Park")
    temple = Attraction.objects.create(slug="sri-temple", name="Sri Temple", kind="temple", city="Hyderabad", provider=temple_p, bookable=True,
                                       opening={"days": ALL, "open": "05:00", "close": "21:00"}, free_cancel_hours=12, cancel_fee_percent=100)
    free = Offering.objects.create(attraction=temple, kind="darshan", booking_model="slot", name="Sarva darshan", days=ALL, slot_times=["06:00", "08:00"], capacity=3, max_per_booking=4)
    Price.objects.create(offering=free, visitor="devotee", amount=D("0"))
    special = Offering.objects.create(attraction=temple, kind="darshan", booking_model="slot", name="Special darshan", days=ALL, slot_times=["09:00"], capacity=10)
    Price.objects.create(offering=special, visitor="devotee", amount=D("150"))
    park = Attraction.objects.create(slug="splash", name="Splash Park", kind="water_park", city="Hyderabad", provider=park_p, bookable=True, kids_friendly=True,
                                     opening={"days": ALL, "open": "10:00", "close": "18:00"}, free_cancel_hours=24, cancel_fee_percent=50)
    day = Offering.objects.create(attraction=park, kind="entry", booking_model="ticket", name="Day pass", days=ALL, capacity=6, tax_percent=D("18"))
    Price.objects.create(offering=day, visitor="adult", amount=D("1000"))
    Price.objects.create(offering=day, visitor="child", amount=D("500"))
    Price.objects.create(offering=day, visitor="family", amount=D("2800"), units=4)
    info = Attraction.objects.create(slug="charminar", name="Charminar", kind="monument", city="Hyderabad", bookable=False,
                                     official_source="Entry tickets are sold by the ASI.")
    return {"temple": temple, "free": free, "special": special, "park": park, "day": day, "info": info, "temple_api": temple_api, "park_api": park_api}


def on(n=3):
    return booking.today() + timedelta(days=n)


def fund(user, amount="50000"):
    WalletTransaction.objects.create(customer=user.customer_profile, kind="topup", amount=D(amount), description="Test top-up")


def client(user):
    c = APIClient(SERVER_NAME="localhost")
    c.force_authenticate(user)
    return c


def req(o, d, tickets, slot=None, **extra):
    return {"offeringId": str(o.id), "visitDate": d.isoformat(), "slotTime": slot, "tickets": tickets, **extra}


def book(api, o, d, tickets, slot=None, key=None, **extra):
    r = api.post(f"{CUST}/review", req(o, d, tickets, slot), format="json").json()
    return api.post(f"{CUST}/bookings", {**req(o, d, tickets, slot, **extra), "leadName": "Asha Rao", "leadPhone": "+91 98765 43210",
                                          "expectedTotal": r.get("total"), "idempotencyKey": key or str(uuid.uuid4())}, format="json")


def test_discovery_information_only_and_filters(api, places):
    detail = api.get("/api/v1/experiences/attractions/charminar").json()
    assert not detail["bookable"] and detail["offerings"] == [] and detail["fromPrice"] is None and "ASI" in detail["officialSource"]
    a = client(make_customer())
    r = a.post(f"{CUST}/review", req(places["day"], on(), {"adult": 1}) | {"offeringId": str(uuid.uuid4())}, format="json")
    assert r.status_code == 404
    names = lambda **q: [c["name"] for c in api.get("/api/v1/experiences/search", q).json()["results"]]  # noqa: E731
    assert set(names(q="hyderabad")) == {"Sri Temple", "Splash Park", "Charminar"}
    assert names(group="spiritual") == ["Sri Temple"] and names(bookable=1, kids=1) == ["Splash Park"]
    assert names(sort="price_asc")[0] == "Sri Temple"  # free darshan
    t = api.get("/api/v1/experiences/attractions/sri-temple").json()
    assert [o["name"] for o in t["offerings"]] == ["Sarva darshan", "Special darshan"] and t["fromPrice"] == "0.00"
    home = api.get("/api/v1/experiences/home", {"city": "Hyderabad"}).json()
    assert {s["code"] for s in home["sections"]} >= {"near", "temples", "tourist", "parks"}
    Attraction.objects.filter(slug="sri-temple").update(latitude="17.3920", longitude="78.3380")
    Attraction.objects.filter(slug="splash").update(latitude="17.2540", longitude="78.3990")
    near = api.get("/api/v1/experiences/home", {"lat": "17.39", "lng": "78.34"}).json()
    nearby = next(s for s in near["sections"] if s["code"] == "nearby")["items"]
    assert [c["name"] for c in nearby] == ["Sri Temple", "Splash Park"] and nearby[0]["distanceKm"] < 1
    assert names(sort="nearest", lat="17.25", lng="78.40")[0] == "Splash Park"
    assert names(lat="17.39", lng="78.34", max_km="5") == ["Sri Temple"]


def test_slots_capacity_closure_and_free_darshan(places):
    a, b = make_customer("a@x.com"), make_customer("b@x.com")
    ca, cb = client(a), client(b)
    d = on()
    r = book(ca, places["free"], d, {"devotee": 3}, "06:00")
    assert r.status_code == 201 and r.json()["status"] == "confirmed" and r.json()["paymentStatus"] == "free" and r.json()["entryCode"]
    slots = {s["time"]: s for s in cb.get(f"/api/v1/experiences/offerings/{places['free'].id}/availability", {"date": d.isoformat()}).json()["slots"]}
    assert slots["06:00"]["status"] == "sold_out" and slots["08:00"]["left"] == 3
    full = book(cb, places["free"], d, {"devotee": 1}, "06:00")
    assert full.status_code == 409 and "Sold out" in full.json()["error"]["message"]
    assert not cb.post(f"{CUST}/review", req(places["free"], d, {"devotee": 1}), format="json").json()["bookable"]  # slot required
    Closure.objects.create(attraction=places["temple"], date=on(5), reason="Festival")
    av = cb.get(f"/api/v1/experiences/offerings/{places['free'].id}/availability", {"date": on(5).isoformat()}).json()
    assert av["state"] == "closed" and av["slots"] == [] and av["reason"] == "Festival"
    past = cb.post(f"{CUST}/review", req(places["free"], booking.today() - timedelta(days=1), {"devotee": 1}, "06:00"), format="json").json()
    assert not past["bookable"]


def test_pricing_offer_payment_failure_idempotency_and_family(places):
    a = make_customer("p@x.com")
    api = client(a)
    d = on()
    q = api.post(f"{CUST}/review", req(places["day"], d, {"adult": 2, "child": 1}), format="json").json()
    assert q["subtotal"] == "2500.00" and q["tax"] == "450.00" and q["total"] == "2950.00" and q["points"] > 0
    assert not api.post(f"{CUST}/review", req(places["day"], d, {"child": 2}), format="json").json()["bookable"]  # adult needed
    fam = api.post(f"{CUST}/review", req(places["day"], d, {"family": 1, "adult": 2}), format="json").json()
    assert fam["units"] == 6 and fam["visitors"] == 6
    assert not api.post(f"{CUST}/review", req(places["day"], d, {"family": 2}), format="json").json()["bookable"]  # 8 > capacity 6
    r = book(api, places["day"], d, {"adult": 2})
    assert r.json()["status"] == "pending_payment" and r.json()["paymentError"] and r.json()["entryCode"] is None
    fund(a)
    paid = api.post(f"{CUST}/bookings/{r.json()['id']}/pay").json()
    assert paid["status"] == "confirmed" and paid["entryCode"]
    ExperienceOffer.objects.create(group="parks", title="10% off parks", percent=10, starts_at=paid["createdAt"], ends_at="2099-01-01T00:00:00Z")
    stale = api.post(f"{CUST}/bookings", {**req(places["day"], d, {"adult": 1}), "leadName": "Asha", "leadPhone": "+91 98765 43210",
                                          "expectedTotal": "1180.00", "idempotencyKey": str(uuid.uuid4())}, format="json")
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "price_changed"
    key = str(uuid.uuid4())
    one = book(api, places["day"], d, {"adult": 1}, key=key)
    two = book(api, places["day"], d, {"adult": 1}, key=key)
    assert one.status_code == 201 and two.status_code == 200 and one.json()["id"] == two.json()["id"]
    assert one.json()["discount"] == "100.00" and one.json()["total"] == "1062.00"


def test_entry_code_cancel_review_and_ownership(places):
    a, other = make_customer("e@x.com"), make_customer("o@x.com")
    fund(a)
    api = client(a)
    today = booking.today()
    r = book(api, places["special"], on(2), {"devotee": 2}, "09:00").json()
    assert client(other).get(f"{CUST}/bookings/{r['id']}").status_code == 404
    assert places["park_api"].post("/api/v1/partner/experiences/check-in", {"code": r["entryCode"]}, format="json").status_code == 404  # other provider
    wrong_day = places["temple_api"].post("/api/v1/partner/experiences/check-in", {"code": r["entryCode"]}, format="json")
    assert wrong_day.status_code == 409 and wrong_day.json()["error"]["code"] == "wrong_date"
    ExperienceBooking.objects.filter(pk=r["id"]).update(visit_date=today)
    ok = places["temple_api"].post("/api/v1/partner/experiences/check-in", {"code": r["entryCode"].lower()}, format="json")
    assert ok.status_code == 200 and ok.json()["visitors"] == 2
    assert places["temple_api"].post("/api/v1/partner/experiences/check-in", {"code": r["entryCode"]}, format="json").json()["error"]["code"] == "already_used"
    c = book(api, places["day"], on(5), {"adult": 1}).json()
    pol = api.get(f"{CUST}/bookings/{c['id']}").json()["cancellation"]
    assert pol["allowed"] and pol["fee"] == "0.00"
    done = api.post(f"{CUST}/bookings/{c['id']}/cancel", {"reason": "Rain"}, format="json").json()
    assert done["status"] == "cancelled" and done["refunded"] == done["total"]
    assert api.post(f"{CUST}/bookings/{r['id']}/review", {"rating": 5}, format="json").status_code == 409  # not completed yet
    ExperienceBooking.objects.filter(pk=r["id"]).update(visit_date=today - timedelta(days=1))
    booking.complete_past()
    assert api.post(f"{CUST}/bookings/{r['id']}/review", {"rating": 4, "comment": "Calm"}, format="json").json()["review"]["rating"] == 4
    assert Attraction.objects.get(pk=places["temple"].pk).rating_count == 1
    fav = api.post("/api/v1/customer/wishlist", {"attractionId": str(places["park"].id)}, format="json")
    assert fav.status_code == 201 and fav.json()["kind"] == "attraction"
    hub = api.get("/api/v1/customer/reservations", {"group": "all"}).json()
    assert hub["counts"] == {"upcoming": 0, "completed": 1, "cancelled": 1, "all": 2}
    assert {r_["kind"] for r_ in hub["results"]} == {"temple", "attraction"}
