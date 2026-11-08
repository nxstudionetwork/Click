import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.bookings.models import Event, Show, Venue
from apps.wallet.models import WalletTransaction

pytestmark = pytest.mark.django_db


@pytest.fixture
def show(db):
    venue = Venue.objects.create(name="Test Cinema", slug="test-cinema", kind="cinema", city="Bengaluru")
    event = Event.objects.create(title="Test Movie", slug="test-movie", kind="movie", status="now_showing", genres="Drama")
    return Show.objects.create(event=event, venue=venue, starts_at=timezone.now() + timedelta(days=1), rows=5, seats_per_row=8,
                               premium_rows=1, price=Decimal("200"), premium_price=Decimal("350"))


def book(api, show, seats, method="pay_at_venue", key=None):
    return api.post("/api/v1/customer/bookings", {"showId": str(show.id), "seats": seats, "paymentMethod": method,
                                                  "idempotencyKey": str(key or uuid.uuid4())})


def test_event_listing_detail_and_seat_map(api, show):
    assert [e["title"] for e in api.get("/api/v1/events?kind=movie").json()["results"]] == ["Test Movie"]
    detail = api.get("/api/v1/events/test-movie").json()
    assert detail["shows"][0]["seatsLeft"] == 40 and detail["genres"] == ["Drama"]
    seatmap = api.get(f"/api/v1/shows/{show.id}").json()
    assert len(seatmap["layout"]["rows"]) == 5 and seatmap["layout"]["rows"][-1]["tier"] == "premium"
    assert api.get("/api/v1/search?q=test movie&scope=events").json()["events"][0]["slug"] == "test-movie"


def test_book_seats_prices_and_seat_map_updates(auth_api, show):
    r = book(auth_api, show, ["a1", "E2"])
    assert r.status_code == 201, r.json()
    b = r.json()
    assert [s["label"] for s in b["seats"]] == ["A1", "E2"]
    assert b["subtotal"] == "550.00" and b["convenienceFee"] == "40.00" and b["tax"] == "7.20" and b["total"] == "597.20"
    assert b["payments"][0]["method"] == "pay_at_venue" and b["payments"][0]["status"] == "pending"
    a1 = auth_api.get(f"/api/v1/shows/{show.id}").json()["layout"]["rows"][0]["seats"][0]
    assert a1 == {"label": "A1", "available": False}


def test_double_booking_is_rejected_and_idempotency_holds(api, customer, other_customer, show):
    api.force_authenticate(customer)
    key = uuid.uuid4()
    first = book(api, show, ["B3"], key=key)
    assert book(api, show, ["B3"], key=key).json()["id"] == first.json()["id"]  # retry = same booking
    api.force_authenticate(other_customer)
    r = book(api, show, ["B3", "B4"])
    assert r.status_code == 409 and r.json()["error"]["details"]["seats"] == ["B3"]


def test_invalid_seats_and_counts(auth_api, show):
    assert book(auth_api, show, ["Z99"]).json()["error"]["code"] == "invalid_seats"
    assert book(auth_api, show, [f"A{i}" for i in range(1, 9)] + ["B1", "B2", "B3"]).status_code == 400


def test_wallet_booking_and_cancel_refund_frees_seats(auth_api, customer, show):
    WalletTransaction.objects.create(customer=customer.customer_profile, kind="promo", amount=Decimal("1000"), description="credit")
    b = book(auth_api, show, ["C1"], method="wallet").json()
    assert b["payments"][0]["status"] == "captured"
    assert auth_api.get("/api/v1/customer/wallet").json()["balance"] == "776.40"
    r = auth_api.post(f"/api/v1/customer/bookings/{b['id']}/cancel")
    assert r.json()["status"] == "cancelled"
    assert auth_api.get("/api/v1/customer/wallet").json()["balance"] == "1000.00"
    assert auth_api.get(f"/api/v1/shows/{show.id}").json()["layout"]["rows"][2]["seats"][0]["available"] is True


def test_cancellation_cutoff_and_isolation(api, customer, other_customer, show):
    api.force_authenticate(customer)
    b = book(api, show, ["D1"]).json()
    api.force_authenticate(other_customer)
    assert api.get(f"/api/v1/customer/bookings/{b['id']}").status_code == 404
    assert api.post(f"/api/v1/customer/bookings/{b['id']}/cancel").status_code == 404
    api.force_authenticate(customer)
    Show.objects.filter(pk=show.pk).update(starts_at=timezone.now() + timedelta(minutes=60))
    r = api.post(f"/api/v1/customer/bookings/{b['id']}/cancel")
    assert r.status_code == 409 and r.json()["error"]["code"] == "booking_not_cancellable"


def test_past_or_cancelled_shows_not_bookable(auth_api, show):
    Show.objects.filter(pk=show.pk).update(status="cancelled")
    assert book(auth_api, show, ["A1"]).status_code == 404
