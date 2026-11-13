import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings import engagement
from apps.bookings.models import (BookedSeat, Booking, ConcessionItem, Credit, Event, HeldSeat, Screen, SeatHold, Show, ShowFeature,
                                  ShowInterest, ShowOffer, Venue)
from apps.notifications.models import Notification
from apps.wallet.models import WalletTransaction
from conftest import make_customer

pytestmark = pytest.mark.django_db
D = Decimal
TZ = ZoneInfo(settings.CLICK_LOCAL_TIMEZONE)
LAYOUT = {"tiers": [{"code": "classic", "name": "Classic"}, {"code": "recliner", "name": "Recliner"}],
          "rows": [{"row": "A", "tier": "classic", "seats": 6, "gaps": [3], "accessible": [1], "unavailable": [6]},
                   {"row": "B", "tier": "classic", "seats": 6, "gaps": [3]},
                   {"row": "C", "tier": "recliner", "seats": 4, "gaps": [2]}]}


@pytest.fixture
def world(db):
    cinema = Venue.objects.create(name="Click Cineplex", slug="click-cineplex", kind="cinema", city="Bengaluru", locality="Indiranagar",
                                  latitude=D("12.971900"), longitude=D("77.641200"), facilities=["Parking"])
    far = Venue.objects.create(name="Far Talkies", slug="far-talkies", kind="cinema", city="Bengaluru", latitude=D("13.100000"), longitude=D("77.600000"))
    screen = Screen.objects.create(venue=cinema, name="Audi 1", formats="IMAX, 2D", sound="Dolby Atmos", layout=LAYOUT)
    far_screen = Screen.objects.create(venue=far, name="Main", formats="2D", layout=LAYOUT)
    film = Event.objects.create(title="Monsoon Protocol", slug="monsoon-protocol", kind="movie", status="now_showing", genres="Action, Thriller",
                                languages="Telugu, Hindi", certification="UA", duration_minutes=140)
    soon = Event.objects.create(title="Kaveri Nights", slug="kaveri-nights", kind="movie", status="coming_soon", genres="Romance", languages="Kannada")
    Credit.objects.create(event=film, name="Aarav Sen", role="cast", part="Lead")
    today = timezone.localtime(timezone.now(), TZ).date()

    def show(venue, scr, day, hh, fmt="2D", lang="Telugu"):
        return Show.objects.create(event=film, venue=venue, screen_ref=scr, starts_at=datetime.combine(today + timedelta(days=day), time(hh, 0), TZ),
                                   language=lang, format=fmt, rows=3, seats_per_row=6, price=D("200"), premium_price=D("450"),
                                   tier_prices={"classic": "200.00", "recliner": "450.00"})

    imax = show(cinema, screen, 1, 19, "IMAX")
    hindi = show(far, far_screen, 1, 21, "2D", "Hindi")
    show(cinema, screen, 2, 13)
    cust = make_customer("viewer@example.com")
    WalletTransaction.objects.create(customer=cust.customer_profile, kind="promo", amount=D("5000"), description="test")
    api = APIClient()
    api.force_authenticate(cust)
    return {"cinema": cinema, "far": far, "film": film, "soon": soon, "imax": imax, "hindi": hindi, "api": api, "user": cust, "screen": screen}


def hold(api, show, seats):
    return api.post("/api/v1/customer/showtime/holds", {"showId": str(show.id), "seats": seats}, format="json")


def book(api, hold_id, **extra):
    return api.post("/api/v1/customer/bookings", {"holdId": hold_id, "paymentMethod": extra.pop("method", "wallet"),
                                                  "idempotencyKey": extra.pop("key", str(uuid.uuid4())), **extra}, format="json")


def test_title_page_has_dates_cinemas_by_distance_and_seat_map_from_screen_layout(world):
    api = APIClient()
    t = api.get("/api/v1/showtime/titles/monsoon-protocol", {"lat": "12.97", "lng": "77.64"}).json()
    assert len(t["dates"]) == 2 and t["allFormats"] == ["IMAX", "2D"] and t["allLanguages"] == ["Hindi", "Telugu"]
    assert [v["venue"]["name"] for v in t["schedule"]] == ["Click Cineplex", "Far Talkies"]  # nearest first
    assert t["schedule"][0]["distanceKm"] < 1 and t["rating"] is None  # no reviews yet: no rating shown
    assert t["credits"][0]["name"] == "Aarav Sen"
    only_hindi = api.get("/api/v1/showtime/titles/monsoon-protocol", {"language": "Hindi"}).json()
    assert [v["venue"]["name"] for v in only_hindi["schedule"]] == ["Far Talkies"]
    m = api.get(f"/api/v1/shows/{world['imax'].id}").json()
    assert [t["price"] for t in m["tiers"]] == ["200.00", "450.00"]
    a = m["rows"][0]["seats"]
    assert a[0]["accessible"] and a[5]["state"] == "unavailable" and m["rows"][0]["gaps"] == [3]


def test_holds_block_others_expire_and_are_released(world):
    api = world["api"]
    r = hold(api, world["imax"], ["B1", "B2"])
    assert r.status_code == 201
    other = APIClient()
    other.force_authenticate(make_customer("other@example.com"))
    assert hold(other, world["imax"], ["B2"]).json()["error"]["code"] == "seats_unavailable"
    assert hold(other, world["imax"], ["A6"]).json()["error"]["code"] == "invalid_seats"  # out of service
    states = {s["label"]: s["state"] for s in APIClient().get(f"/api/v1/shows/{world['imax'].id}").json()["rows"][1]["seats"]}
    assert states["B1"] == "held"
    SeatHold.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    assert hold(other, world["imax"], ["B2"]).status_code == 201  # the expired hold was released
    assert book(api, r.json()["id"]).json()["error"]["code"] in ("hold_not_found", "hold_expired")
    assert HeldSeat.objects.filter(label="B1").count() == 0


def test_booking_from_hold_prices_food_offer_and_creates_a_verifiable_ticket(world):
    api = world["api"]
    combo = ConcessionItem.objects.create(venue=world["cinema"], name="Combo", category="combo", price=D("300"))
    elsewhere = ConcessionItem.objects.create(venue=world["far"], name="Other combo", category="combo", price=D("100"))
    offer = ShowOffer.objects.create(title="20% off 2+", discount_type="percent", discount_value=D("20"), max_discount=D("100"), min_seats=2)
    wallet_only = ShowOffer.objects.create(title="₹50 wallet", discount_type="flat", discount_value=D("50"), payment_method="wallet")
    h = hold(api, world["imax"], ["C1", "B3"]).json()
    q = api.post("/api/v1/customer/showtime/quote", {"holdId": h["id"], "concessions": [{"id": str(combo.id), "quantity": 2}],
                                                     "offerId": str(offer.id), "paymentMethod": "pay_at_venue"}, format="json").json()
    # tickets 450 + 200; fee 2 x 20; tax = 18% of fee + 5% of food (600)
    assert q["lines"] == {"tickets": "650.00", "convenienceFee": "40.00", "concessions": "600.00", "tax": "37.20", "discount": "100.00", "total": "1227.20"}
    assert {o["title"]: o["problem"] for o in q["offers"]}["₹50 wallet"] == "Pay with Click. Wallet to use this offer."
    r = book(api, h["id"], concessions=[{"id": str(elsewhere.id), "quantity": 1}])
    assert r.json()["error"]["code"] == "concessions_unavailable"  # another venue's menu
    key = str(uuid.uuid4())
    r = book(api, h["id"], concessions=[{"id": str(combo.id), "quantity": 2}], offerId=str(offer.id), key=key)
    assert r.status_code == 201, r.json()
    b = r.json()
    assert b["total"] == "1227.20" and b["discount"] == "100.00" and [c["name"] for c in b["concessions"]] == ["Combo"]
    assert b["state"] == "upcoming" and b["ticketCode"].startswith("CLICKTKT:")
    assert book(api, h["id"], key=key).status_code == 200  # idempotent
    assert not SeatHold.objects.exists() and BookedSeat.objects.filter(is_active=True).count() == 2
    assert book(api, str(uuid.uuid4())).json()['error']['code'] == 'hold_not_found'
    # Venue check-in: only the operating partner, once.
    from apps.partners.models import Partner, PartnerCategory, PartnerMembership, PartnerType, PartnerVenue

    ptype = PartnerType.objects.create(slug="entertainment", name="Entertainment")
    cat = PartnerCategory.objects.create(partner_type=ptype, slug="cinema", name="Cinema")
    staff = make_customer("staff@example.com")
    partner = Partner.objects.create(partner_type=ptype, category=cat, business_name="Click Cineplex")
    PartnerMembership.objects.create(partner=partner, user=staff, role="owner")
    PartnerVenue.objects.create(partner=partner, venue=world["cinema"])
    Show.objects.filter(pk=world["imax"].pk).update(starts_at=timezone.now() + timedelta(minutes=30))
    door = APIClient()
    door.force_authenticate(staff)
    first = door.post("/api/v1/partner/tickets/verify", {"code": b["ticketCode"]}, format="json").json()
    assert first["firstScan"] is True and first["seats"] == ["B3", "C1"]
    assert door.post("/api/v1/partner/tickets/verify", {"code": b["ticketCode"]}, format="json").json()["firstScan"] is False
    assert door.post("/api/v1/partner/tickets/verify", {"code": b["ticketCode"] + "x"}, format="json").json()["error"]["code"] == "ticket_invalid"


def test_wallet_shortfall_creates_nothing_and_offer_rules_hold(world):
    api = world["api"]
    WalletTransaction.objects.create(customer=world["user"].customer_profile, kind="adjustment", amount=D("-4900"), description="drain")
    h = hold(api, world["imax"], ["C1", "C2"]).json()
    r = book(api, h["id"])
    assert r.json()["error"]["code"] == "insufficient_wallet_balance"
    assert not Booking.objects.exists() and SeatHold.objects.filter(pk=h["id"]).exists()  # the hold survives for a retry
    assert book(api, h["id"], method="pay_at_venue").status_code == 201


def test_home_sections_search_interpretation_and_featured_window(world):
    api = APIClient()
    now = timezone.now()
    ShowFeature.objects.create(event=world["soon"], headline="Ended", priority=99, starts_at=now - timedelta(days=5), ends_at=now - timedelta(days=1))
    h = api.get("/api/v1/showtime/home", {"lat": "12.97", "lng": "77.64"}).json()
    assert h["featured"]["slug"] == "monsoon-protocol"  # the ended feature is ignored
    ids = [s["id"] for s in h["sections"]]
    assert "now_showing" in ids and "coming_soon" in ids and "top_rated" not in ids and "trending" not in ids
    assert h["cinemas"][0]["name"] == "Click Cineplex" and h["cinemas"][0]["formats"] == ["IMAX", "2D"]
    assert {f["code"] for f in h["formats"]} == {"IMAX", "atmos"}
    d = api.get("/api/v1/showtime/search", {"q": "telugu imax"}).json()
    assert [u["label"] for u in d["understood"]] == ["Telugu", "IMAX"] and [t["slug"] for t in d["titles"]] == ["monsoon-protocol"]
    assert api.get("/api/v1/showtime/search", {"q": "kannada imax"}).json()["count"] == 0
    d = api.get("/api/v1/showtime/search", {"q": "aarav"}).json()
    assert d["people"][0]["name"] == "Aarav Sen" and d["titles"][0]["slug"] == "monsoon-protocol"
    s = api.get("/api/v1/showtime/suggest", {"q": "mon"}).json()
    assert "Monsoon Protocol — Hindi" in [x["text"] for x in s["suggestions"]]


def test_interest_notifies_once_when_booking_opens(world):
    api = world["api"]
    assert api.post("/api/v1/customer/showtime/titles/kaveri-nights/interest").json()["interested"] is True
    profile = world["user"].customer_profile
    assert not Notification.objects.filter(customer=profile, title__startswith="Booking is open").exists()
    Show.objects.create(event=world["soon"], venue=world["cinema"], screen_ref=world["screen"], starts_at=timezone.now() + timedelta(days=3),
                        rows=3, seats_per_row=6, price=D("200"), premium_price=D("450"), tier_prices={"classic": "200.00"})
    engagement.notify_booking_open(world["soon"])  # on_commit hooks don't run inside the test transaction
    engagement.notify_booking_open(world["soon"])
    assert Notification.objects.filter(customer=profile, title="Booking is open: Kaveri Nights").count() == 1
    assert ShowInterest.objects.get().notified_at is not None


def test_reviews_only_after_attending_and_rating_needs_three(world):
    api = world["api"]
    url = "/api/v1/customer/showtime/titles/monsoon-protocol/review"
    assert api.post(url, {"rating": 5}, format="json").status_code == 403
    h = hold(api, world["imax"], ["B1"]).json()
    book(api, h["id"], method="pay_at_venue")
    assert api.post(url, {"rating": 5}, format="json").status_code == 403  # booked, but the show hasn't happened
    Show.objects.filter(pk=world["imax"].pk).update(starts_at=timezone.now() - timedelta(hours=3))
    assert api.post(url, {"rating": 4, "body": "Great"}, format="json").status_code == 201
    assert api.post(url, {"rating": 5}, format="json").status_code == 409
    world["film"].refresh_from_db()
    assert world["film"].rating_count == 1
    assert APIClient().get("/api/v1/showtime/titles/monsoon-protocol").json()["rating"] is None  # below the minimum of 3
    b = APIClient()
    b.force_authenticate(world["user"])
    t = b.get("/api/v1/showtime/titles/monsoon-protocol").json()
    assert t["myReview"]["rating"] == 4 and t["canReview"] is False


def test_cancellation_terms_and_refund(world):
    api = world["api"]
    h = hold(api, world["imax"], ["B4"]).json()
    b = book(api, h["id"]).json()
    assert b["cancellation"]["refundAmount"] == b["total"] and b["cancellation"]["refundMethod"] == "Click. Wallet"
    r = api.post(f"/api/v1/customer/bookings/{b['id']}/cancel")
    assert r.json()["status"] == "cancelled" and r.json()["ticketCode"] is None and r.json()["state"] == "cancelled"
    assert APIClient().get(f"/api/v1/shows/{world['imax'].id}").json()["rows"][1]["seats"][3]["state"] == "available"
