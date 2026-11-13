"""Click. Hotels: search and server-side filters, inventory-aware rooms, review → book → pay (wallet hold, failure and
retry), pay at property, policy-based cancellation and refunds, verified reviews, ownership, wishlist, offers, GST,
partner workspace."""

import uuid
from datetime import time, timedelta
from decimal import Decimal as D

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.hotels import engine
from apps.hotels.models import (
    Amenity, Destination, HotelBooking, HotelOffer, HotelProperty, Landmark, RatePlan, RoomInventory, RoomType,
)
from apps.partners.models import Partner, PartnerCategory, PartnerMembership, PartnerProfile
from apps.users.models import User
from apps.wallet.models import WalletTransaction
from apps.wallet.services import balance

pytestmark = pytest.mark.django_db
CUST = "/api/v1/customer/hotels"


@pytest.fixture
def city(db):
    from apps.partners.catalog import apply_catalog
    from apps.partners.models import PartnerType

    apply_catalog(PartnerType, PartnerCategory)
    d = Destination.objects.create(slug="hyderabad", name="Hyderabad", region="Telangana", latitude=D("17.385"), longitude=D("78.4867"), synonyms=["hyd"],
                                   tags=["city"])
    Landmark.objects.create(destination=d, name="Charminar", kind="centre", latitude=D("17.3616"), longitude=D("78.4747"))
    air = Landmark.objects.create(destination=d, name="RGI Airport", kind="airport", latitude=D("17.2403"), longitude=D("78.4294"))
    am = {s: Amenity.objects.create(slug=s, name=s.title()) for s in ("wifi", "pool", "breakfast", "parking")}
    return {"d": d, "air": air, "am": am}


def hotel(city, name, at=("17.3620", "78.4750"), stars=3, ptype="hotel", amen=("wifi",), units=2, price="3000", weekend=None, breakfast=True,
          refundable_days=2, payment="either", listed=True, good_for=()):
    pc = PartnerCategory.objects.select_related("partner_type").get(slug="hotel")
    user = User.objects.create_user(f"{uuid.uuid4().hex[:8]}@hotel.test", "S3cure-pass-123", full_name=name)
    partner = Partner.objects.create(partner_type=pc.partner_type, category=pc, business_name=name, status=Partner.Status.ACTIVE, is_available=True,
                                     partner_code=f"CLK-PT-{uuid.uuid4().hex[:6]}")
    PartnerMembership.objects.create(partner=partner, user=user, role="owner")
    PartnerProfile.objects.create(partner=partner, contact_name=name, details={})
    p = HotelProperty.objects.create(partner=partner, destination=city["d"], property_type=ptype, star_rating=stars, address="Somewhere", area="Old City",
                                     latitude=D(at[0]), longitude=D(at[1]), check_in_time=time(14), check_out_time=time(11), is_listed=listed, good_for=list(good_for))
    p.amenities.set([city["am"][a] for a in amen])
    room = RoomType.objects.create(property=p, name="Deluxe", room_class="double", beds="1 King", max_adults=2, max_children=1, max_occupancy=3, total_units=units)
    fam = RoomType.objects.create(property=p, name="Family", room_class="family", beds="2 Queen", max_adults=4, max_children=2, max_occupancy=5, total_units=1)
    rates = [RatePlan.objects.create(room_type=room, name="Room only", price=D(price), weekend_price=D(weekend) if weekend else None,
                                     free_cancel_days=refundable_days, cancel_fee_percent=100, payment=payment)]
    if breakfast:
        rates.append(RatePlan.objects.create(room_type=room, name="With breakfast", meal_plan="breakfast", price=D(price) + 500, free_cancel_days=refundable_days,
                                             cancel_fee_percent=50, payment="pay_now"))
    rates.append(RatePlan.objects.create(room_type=fam, name="Family room only", price=D(price) * 2, free_cancel_days=refundable_days, payment="pay_now"))
    c = APIClient()
    c.force_authenticate(user)
    return p, room, rates, c


def stay(days=10, nights=2):
    ci = engine.today() + timedelta(days=days)
    return ci, ci + timedelta(days=nights)


def q(ci, co, **extra):
    return {"destination": "Hyderabad", "check_in": ci.isoformat(), "check_out": co.isoformat(), "adults": 2, "rooms": 1, **extra}


def fund(customer, amount="100000"):
    WalletTransaction.objects.create(customer=customer.customer_profile, kind="topup", amount=D(amount), description="Test top-up")


def guest(**extra):
    return {"guestName": "Asha Rao", "guestPhone": "+91 98765 43210", "guestEmail": "asha@example.com", **extra}


def book(api, rate, ci, co, **extra):
    body = {"rateId": str(rate.id), "checkIn": ci.isoformat(), "checkOut": co.isoformat(), "adults": 2, "rooms": 1}
    review = api.post(f"{CUST}/review", body, format="json").json()
    return api.post(f"{CUST}/bookings", {**body, **guest(), "expectedTotal": review.get("total"), "idempotencyKey": str(uuid.uuid4()), **extra}, format="json")


def test_search_filters_sort_distance_and_honest_data(api, city):
    a, *_ = hotel(city, "Old City Inn", price="2000", amen=("wifi", "breakfast"))
    hotel(city, "Airport Hotel", at=("17.2450", "78.4300"), price="4000", stars=4, amen=("wifi", "pool", "parking"), breakfast=False)
    hotel(city, "Hidden Hotel", listed=False)
    hotel(city, "Pricey Palace", price="12000", stars=5, amen=("wifi", "pool"))
    ci, co = stay()
    names = lambda **f: [c["name"] for c in api.get("/api/v1/hotels/search", q(ci, co, **f)).json()["results"]]
    assert set(names()) == {"Old City Inn", "Airport Hotel", "Pricey Palace"}  # unlisted never shown
    assert names(sort="price_asc")[0] == "Old City Inn" and names(sort="price_desc")[0] == "Pricey Palace"
    assert names(amenities="pool") and set(names(amenities="pool")) == {"Airport Hotel", "Pricey Palace"}
    assert set(names(stars="4,5")) == {"Airport Hotel", "Pricey Palace"}
    assert names(breakfast="true", max_price="5000") == ["Old City Inn"]
    assert names(near=str(city["air"].id), sort="distance")[0] == "Airport Hotel"
    assert names(destination="hyd") and api.get("/api/v1/hotels/search", q(ci, co, destination="Atlantis")).json()["count"] == 0
    card = next(c for c in api.get("/api/v1/hotels/search", q(ci, co)).json()["results"] if c["name"] == "Old City Inn")
    assert card["rating"] is None and card["starRating"] == 3 and card["price"]["nights"] == 2 and card["distanceKm"] < 1
    # GST: ₹2,000 a night → 12%.
    assert D(card["price"]["tax"]) == D("480.00") and D(card["price"]["total"]) == D("4480.00")
    assert api.get("/api/v1/hotels/search", q(ci, ci)).status_code == 400  # check-out must be after check-in
    d = api.get(f"/api/v1/hotels/properties/{a.id}", {"check_in": ci.isoformat(), "check_out": co.isoformat(), "adults": 2}).json()
    assert d["images"] == [] and d["reviews"] == [] and d["rooms"][0]["name"] == "Deluxe" and len(d["rooms"][0]["rates"]) == 2


def test_inventory_hold_pay_failure_retry_and_last_room(auth_api, city, customer, other_customer):
    p, room, rates, _ = hotel(city, "Old City Inn", units=1, price="3000", payment="pay_now")
    ci, co = stay()
    # No balance: the room is held as pending payment, nothing is charged, and nobody else can take it meanwhile.
    r = book(auth_api, rates[0], ci, co)
    b = r.json()
    assert r.status_code == 201 and b["status"] == "pending_payment" and b["paymentError"] and b["canPay"]
    other = APIClient()
    other.force_authenticate(other_customer)
    assert other.post(f"{CUST}/review", {"rateId": str(rates[0].id), "checkIn": ci.isoformat(), "checkOut": co.isoformat(), "adults": 2}, format="json").json()["problem"] == "Sold out for these dates."
    fund(customer)
    paid = auth_api.post(f"{CUST}/bookings/{b['id']}/pay", {}, format="json").json()
    assert paid["status"] == "confirmed" and paid["paymentStatus"] == "paid" and paid["payment"]["amount"] == b["total"]
    # An expired hold fails and releases the room.
    p2, room2, rates2, _ = hotel(city, "Second Inn", units=1, payment="pay_now")
    held = book(other, rates2[0], ci, co).json()
    HotelBooking.objects.filter(pk=held["id"]).update(hold_expires_at=timezone.now() - timedelta(minutes=1))
    assert other.get(f"{CUST}/bookings/{held['id']}").json()["status"] == "failed"
    assert engine.free_units(room2, engine.nights_of(ci, co)) == 1
    # Closed nights and price changes are caught.
    RoomInventory.objects.create(room_type=room2, date=ci, closed=True)
    assert book(other, rates2[0], ci, co).status_code == 409
    stale = auth_api.post(f"{CUST}/bookings", {"rateId": str(rates[1].id), "checkIn": (ci + timedelta(days=5)).isoformat(),
                                               "checkOut": (co + timedelta(days=5)).isoformat(), "adults": 2, **guest(), "expectedTotal": "1.00", "idempotencyKey": "k1"}, format="json")
    assert stale.status_code == 409 and stale.json()["error"]["code"] in ("price_changed", "room_unavailable")


def test_pay_at_property_cancellation_policy_refunds_and_ownership(auth_api, city, customer, other_customer):
    p, room, rates, _ = hotel(city, "Old City Inn", price="3000", refundable_days=2, units=3)
    fund(customer, "50000")
    ci, co = stay(days=10)
    at = book(auth_api, rates[0], ci, co, paymentMode="at_property").json()
    assert at["status"] == "confirmed" and at["paymentStatus"] == "at_property" and at["payment"] is None
    assert at["cancellation"]["fee"] == "0.00"
    # Pay now, free window open → full refund.
    paid = book(auth_api, rates[0], ci + timedelta(days=3), co + timedelta(days=3), paymentMode="pay_now").json()
    assert paid["cancellation"]["refund"] == paid["total"]
    other = APIClient()
    other.force_authenticate(other_customer)
    assert other.get(f"{CUST}/bookings/{paid['id']}").status_code == 404
    assert other.post(f"{CUST}/bookings/{paid['id']}/cancel", {"reason": "x y"}, format="json").status_code == 404
    before = balance(customer.customer_profile)
    c = auth_api.post(f"{CUST}/bookings/{paid['id']}/cancel", {"reason": "Plans changed"}, format="json").json()
    assert c["status"] == "cancelled" and c["paymentStatus"] == "refunded" and balance(customer.customer_profile) == before + D(paid["total"])
    # Inside the window on a 50% plan → half kept.
    late = book(auth_api, rates[1], ci + timedelta(days=6), co + timedelta(days=6), paymentMode="pay_now").json()
    HotelBooking.objects.filter(pk=late["id"]).update(free_cancel_until=timezone.now() - timedelta(hours=1))
    pol = auth_api.get(f"{CUST}/bookings/{late['id']}").json()["cancellation"]
    assert D(pol["fee"]) == (D(late["total"]) / 2).quantize(D("0.01"))
    # Non-refundable keeps everything; nothing is refunded.
    nr = RatePlan.objects.create(room_type=room, name="Saver", price=D("2500"), refundable=False, payment="pay_now")
    s = book(auth_api, nr, ci + timedelta(days=9), co + timedelta(days=9)).json()
    assert s["cancellation"]["refund"] == "0.00" and "Non-refundable" in s["policy"]


def test_completion_verified_review_offers_and_wishlist(auth_api, city, customer):
    p, room, rates, _ = hotel(city, "Old City Inn", price="2000")
    fund(customer)
    now = timezone.now()
    HotelOffer.objects.create(title="Early 10%", kind="early", percent=10, min_days_ahead=7, starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=30))
    HotelOffer.objects.create(title="Coupon", kind="coupon", percent=20, code="STAY20", min_nights=2, starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=30))
    ci, co = stay(days=10)
    r = auth_api.post(f"{CUST}/review", {"rateId": str(rates[0].id), "checkIn": ci.isoformat(), "checkOut": co.isoformat(), "adults": 2}, format="json").json()
    assert r["offer"] == "Early 10%" and r["discount"] == "400.00"
    r2 = auth_api.post(f"{CUST}/review", {"rateId": str(rates[0].id), "checkIn": ci.isoformat(), "checkOut": co.isoformat(), "adults": 2, "coupon": "stay20"}, format="json").json()
    assert r2["offer"] == "Coupon" and r2["discount"] == "800.00"
    b = book(auth_api, rates[0], ci, co).json()
    assert auth_api.post(f"{CUST}/bookings/{b['id']}/review", {k: 9 for k in ("overall", "cleanliness", "location", "comfort", "facilities", "staff", "value")},
                         format="json").status_code == 409  # not stayed yet
    HotelBooking.objects.filter(pk=b["id"]).update(check_in=engine.today() - timedelta(days=3), check_out=engine.today() - timedelta(days=1))
    assert auth_api.get(f"{CUST}/bookings/{b['id']}").json()["status"] == "completed"
    rv = auth_api.post(f"{CUST}/bookings/{b['id']}/review", {**{k: 8 for k in ("overall", "cleanliness", "location", "comfort", "facilities", "staff", "value")},
                                                             "comment": "Nice", "traveller": "couple"}, format="json")
    assert rv.status_code == 200
    p.refresh_from_db()
    assert p.rating_count == 1 and p.rating_average == D("8.0")
    assert auth_api.post("/api/v1/customer/wishlist", {"hotelId": str(p.id)}, format="json").status_code == 201
    assert auth_api.get(f"{CUST}/saved").json()["results"][0]["name"] == "Old City Inn"
    rev = APIClient().get(f"/api/v1/hotels/properties/{p.id}/reviews?sort=highest").json()
    assert rev["results"][0]["verifiedStay"] and rev["aspects"]["cleanliness"] == 8.0


def test_partner_workspace_arrival_payment_checkout_and_buddy(auth_api, city, customer):
    p, room, rates, pc = hotel(city, "Old City Inn", price="2000", good_for=("family",))
    ci, co = stay(days=10)
    b = book(auth_api, rates[0], ci, co, paymentMode="at_property").json()
    HotelBooking.objects.filter(pk=b["id"]).update(check_in=engine.today(), check_out=engine.today() + timedelta(days=2))
    home = pc.get("/api/v1/partner/home").json()
    assert home["workspace"]["kind"] == "hotels"
    item = next(i for i in home["actionRequired"]["data"] if i["kind"] == "hotel_booking")
    act = lambda a: pc.post(f"/api/v1/partner/work/hotel_booking/{item['id']}/{a}", {}, format="json")
    assert act("check_out").status_code == 409  # not checked in
    assert act("check_in").status_code == 200
    assert act("check_out").json()["error"]["code"] == "not_paid"
    assert act("paid_at_property").status_code == 200 and act("check_out").status_code == 200
    assert HotelBooking.objects.get(pk=b["id"]).status == "completed"
    r = auth_api.post("/api/v1/customer/assistant/messages", {"messages": [{"role": "user", "content": "Find me a hotel in Hyderabad for 2 adults under ₹5,000 with breakfast"}]},
                      format="json").json()
    assert "Old City Inn" in r["message"]["content"]
    assert any(a.get("path", "").startswith("/hotels/search?") and "breakfast=true" in a["path"] for a in r["actions"])
    assert HotelBooking.objects.count() == 1  # Buddy never books
