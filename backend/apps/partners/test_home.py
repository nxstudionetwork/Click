"""Partner Home: category configuration, availability, real Customer App → Partner → Customer connection, isolation."""

import uuid
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Event, Show, Venue
from apps.orders.models import Order
from apps.partners.models import (
    Partner, PartnerAvailabilityEvent, PartnerCategory, PartnerMembership, PartnerNotification, PartnerProfile,
    PartnerStore, PartnerType, PartnerVenue,
)
from apps.rides.models import DriverLocation, Ride, RideDriverOffer, RideType
from apps.stores.models import Store
from apps.users.models import User

pytestmark = pytest.mark.django_db
INDIRANAGAR = {"label": "Home", "address": "12th Cross, Indiranagar", "lat": 12.9719, "lng": 77.6412}
KORAMANGALA = {"label": "Office", "address": "Koramangala 5th Block", "lat": 12.9352, "lng": 77.6245}
_codes = iter(range(900000, 999999))


@pytest.fixture(autouse=True)
def partner_catalog(db):
    from apps.partners.catalog import apply_catalog

    apply_catalog(PartnerType, PartnerCategory)


def make_partner(category_slug, email, status=Partner.Status.ACTIVE, available=False, details=None, name="Partner Biz"):
    category = PartnerCategory.objects.select_related("partner_type").get(slug=category_slug)
    user = User.objects.create_user(email, "S3cure-pass-123", full_name="Ravi Kumar")
    partner = Partner.objects.create(partner_type=category.partner_type, category=category, business_name=name, status=status,
                                     is_available=available, partner_code=f"CLK-PT-{next(_codes)}")
    PartnerMembership.objects.create(partner=partner, user=user, role="owner")
    PartnerProfile.objects.create(partner=partner, contact_name="Ravi Kumar", details=details or {})
    client = APIClient()
    client.force_authenticate(user)
    return partner, client


@pytest.fixture
def restaurant(store):
    partner, client = make_partner("restaurant", "kitchen@click.test", available=True)
    PartnerStore.objects.create(partner=partner, store=store)
    return partner, client


def order_food(auth_api, products, address):
    from django.test import TestCase

    auth_api.post("/api/v1/customer/cart/items", {"productId": str(products[0].id), "quantity": 2})
    # Partner notifications are sent after commit; run those callbacks inside the test transaction.
    with TestCase.captureOnCommitCallbacks(execute=True):
        r = auth_api.post("/api/v1/customer/orders", {"addressId": str(address.id), "paymentMethod": "cash_on_delivery",
                                                      "idempotencyKey": str(uuid.uuid4())})
    assert r.status_code == 201, r.content
    return r.json()


# --- access ------------------------------------------------------------------------------------------------

def test_home_requires_sign_in_and_a_finished_profile(api, restaurant):
    assert api.get("/api/v1/partner/home").status_code == 401
    draft, client = make_partner("restaurant", "draft@click.test")
    draft.partner_code = None
    draft.save()
    assert client.get("/api/v1/partner/home").json()["error"]["code"] == "onboarding_incomplete"


# --- category configuration --------------------------------------------------------------------------------

@pytest.mark.parametrize("slug,kind,on,metrics", [
    ("cab-driver", "rides", "Online", ["trips", "earnings", "distance", "online_time"]),
    ("restaurant", "orders", "Open", ["orders", "sales", "completed", "pending"]),
    ("retail-store", "orders", "Open", ["orders", "sales", "items_sold", "pending"]),
    ("cinema-hall", "venue", "Bookings open", ["shows", "tickets", "occupancy", "revenue"]),
    ("hotel", "hotels", "Accepting bookings", ["arrivals", "in_house", "departures", "revenue"]),
    ("resort", "hotels", "Accepting bookings", ["arrivals", "in_house", "departures", "revenue"]),
    ("sports-venue", "upcoming", "Accepting bookings", []),
    ("parcel-partner", "parcels", "Available", ["deliveries", "completed", "earnings", "pending"]),
    ("electrician", "services", "Available", ["jobs", "completed", "earnings", "rating"]),
    ("delivery-rider", "parcels", "Available", ["deliveries", "completed", "earnings", "pending"]),
])
def test_each_category_gets_its_own_home(slug, kind, on, metrics):
    partner, client = make_partner(slug, f"{slug}@click.test")
    if kind == "orders":
        from conftest import make_store
        PartnerStore.objects.create(partner=partner, store=make_store(f"Store {slug}"))
    if kind == "services":
        from apps.professionals.models import ProviderProfile, ServiceCategory

        cat = ServiceCategory.objects.create(slug=f"cat-{slug}", name="Electrical", profession="Electrician", group="home")
        ProviderProfile.objects.create(partner=partner, category=cat)
    if kind == "hotels":
        from datetime import time
        from decimal import Decimal as D

        from apps.hotels.models import Destination, HotelProperty

        d = Destination.objects.create(slug=f"d-{slug}", name="City", latitude=D("17.4"), longitude=D("78.4"))
        HotelProperty.objects.create(partner=partner, destination=d, address="x", latitude=D("17.4"), longitude=D("78.4"),
                                     check_in_time=time(14), check_out_time=time(11))
    if kind == "venue":
        PartnerVenue.objects.create(partner=partner, venue=Venue.objects.create(name="Hall", slug=f"hall-{slug}", kind="cinema", city="B"))
    home = client.get("/api/v1/partner/home").json()
    assert home["workspace"]["kind"] == kind
    assert home["availability"]["onLabel"] == on
    if kind == "upcoming":
        assert home["workspace"]["state"] == "upcoming" and home["metrics"]["status"] == "unavailable"
        assert not home["availability"]["canChange"] and home["quickActions"] == []
    else:
        assert [m["key"] for m in home["metrics"]["data"]] == metrics
        assert all(q["to"].startswith("/") for q in home["quickActions"])


def test_store_partner_without_a_linked_storefront_is_told_so():
    _, client = make_partner("restaurant", "unlinked@click.test")
    home = client.get("/api/v1/partner/home").json()
    assert home["workspace"]["state"] == "not_connected" and "isn’t listed on Click yet" in home["workspace"]["message"]
    assert client.post("/api/v1/partner/availability", {"available": True}).status_code == 409


# --- availability ------------------------------------------------------------------------------------------

def test_closing_the_restaurant_stops_customer_orders_and_is_audited(restaurant, store, auth_api, products, address):
    partner, client = restaurant
    r = client.post("/api/v1/partner/availability", {"available": False})
    assert r.status_code == 200 and r.json()["availability"]["label"] == "Closed"
    store.refresh_from_db()
    assert store.is_accepting_orders is False
    assert PartnerAvailabilityEvent.objects.filter(partner=partner, is_available=False).count() == 1
    added = auth_api.post("/api/v1/customer/cart/items", {"productId": str(products[0].id), "quantity": 1})
    placed = auth_api.post("/api/v1/customer/orders", {"addressId": str(address.id), "paymentMethod": "cash_on_delivery",
                                                       "idempotencyKey": str(uuid.uuid4())})
    assert placed.status_code >= 400 and Order.objects.count() == 0
    assert added.status_code >= 400  # the closed storefront no longer sells


def test_unverified_partner_cannot_switch_on():
    _, client = make_partner("cab-driver", "new@click.test", status=Partner.Status.VERIFICATION_PENDING)
    r = client.post("/api/v1/partner/availability", {"available": True})
    assert r.status_code == 409 and r.json()["error"]["code"] == "availability_not_allowed"


# --- Customer App → Partner Home → Customer App (orders) ------------------------------------------------------

def test_customer_order_reaches_the_restaurant_and_its_actions_reach_the_customer(restaurant, auth_api, products, address):
    partner, client = restaurant
    order = order_food(auth_api, products, address)

    home = client.get("/api/v1/partner/home").json()
    [item] = [i for i in home["actionRequired"]["data"] if i["kind"] == "order"]
    assert item["ref"] == order["number"] and item["statusLabel"] == "New order"
    assert [a["key"] for a in item["actions"]] == ["accept", "reject"]
    assert home["notifications"]["unread"] == 1
    assert PartnerNotification.objects.get(partner=partner).title == f"New order {order['number']}"

    for action, status in [("accept", "confirmed"), ("preparing", "preparing"), ("ready", "ready"), ("handover", "out_for_delivery")]:
        r = client.post(f"/api/v1/partner/work/order/{order['id']}/{action}")
        assert r.status_code == 200, r.content
        assert auth_api.get(f"/api/v1/customer/orders/{order['id']}").json()["status"] == status

    # A stale or out-of-order action is refused, never shown as done.
    assert client.post(f"/api/v1/partner/work/order/{order['id']}/accept").status_code == 409
    metrics = {m["key"]: m["value"] for m in client.get("/api/v1/partner/home").json()["metrics"]["data"]}
    assert metrics["orders"] == 1 and metrics["completed"] == 1


def test_rejecting_needs_a_reason_and_cancels_the_customer_order(restaurant, auth_api, products, address):
    _, client = restaurant
    order = order_food(auth_api, products, address)
    assert client.post(f"/api/v1/partner/work/order/{order['id']}/reject", {"reason": ""}).status_code == 400
    assert client.post(f"/api/v1/partner/work/order/{order['id']}/reject", {"reason": "Out of paneer"}).status_code == 200
    assert auth_api.get(f"/api/v1/customer/orders/{order['id']}").json()["status"] == "cancelled"


def test_partners_never_see_or_touch_another_partners_orders(restaurant, auth_api, products, address):
    order = order_food(auth_api, products, address)
    from conftest import make_store

    other, other_client = make_partner("restaurant", "other@click.test", available=True)
    PartnerStore.objects.create(partner=other, store=make_store("Other Kitchen"))
    assert other_client.get("/api/v1/partner/work?view=new").json()["items"] == []
    assert other_client.post(f"/api/v1/partner/work/order/{order['id']}/accept").status_code == 404
    assert Order.objects.get(pk=order["id"]).status == "placed"
    assert other_client.get("/api/v1/partner/notifications").json()["unread"] == 0


# --- drivers -----------------------------------------------------------------------------------------------

@pytest.fixture
def cab(db):
    return RideType.objects.create(code="cab", name="Cab", vehicle_types="car", seats=4, base_fare=Decimal("50"), per_km=Decimal("16"),
                                   per_minute=Decimal("2"), minimum_fare=Decimal("90"), booking_fee=Decimal("5"), average_speed_kmh=22)


def make_driver(email, lat=12.9725, lng=77.6420):
    partner, client = make_partner("cab-driver", email, available=True, details={"vehicle_type": "car", "vehicle_number": "KA 01 AB 1"})
    DriverLocation.objects.create(driver=partner, lat=Decimal(str(lat)), lng=Decimal(str(lng)), reported_at=timezone.now())
    return partner, client


def book(auth_api):
    r = auth_api.post("/api/v1/customer/rides", {"pickup": INDIRANAGAR, "drop": KORAMANGALA, "rideType": "cab",
                                                  "paymentMethod": "cash", "idempotencyKey": str(uuid.uuid4())}, format="json")
    assert r.status_code == 201, r.content
    return r.json()


def test_ride_request_flows_to_driver_home_and_trip_steps_reach_the_customer(cab, auth_api):
    driver, client = make_driver("d1@click.test")
    ride = book(auth_api)
    [req] = client.get("/api/v1/partner/home").json()["actionRequired"]["data"]
    assert req["id"] == ride["id"] and {f["label"] for f in req["fields"]} >= {"Pickup", "Drop", "Payment"}

    assert client.post(f"/api/v1/partner/work/ride/{ride['id']}/accept").status_code == 200
    home = client.get("/api/v1/partner/home").json()
    assert home["active"]["data"][0]["navigate"]["label"] == "Home"
    # Can't go offline mid-trip.
    assert client.post("/api/v1/partner/availability", {"available": False}).status_code == 409
    for action, status in [("arrived", "driver_arrived"), ("start", "in_progress"), ("complete", "completed")]:
        assert client.post(f"/api/v1/partner/work/ride/{ride['id']}/{action}").status_code == 200
        assert auth_api.get(f"/api/v1/customer/rides/{ride['id']}").json()["status"] == status
    metrics = {m["key"]: m["value"] for m in client.get("/api/v1/partner/home").json()["metrics"]["data"]}
    assert metrics["trips"] == 1 and Decimal(metrics["earnings"]) == Decimal(ride["fare"]["total"])


def test_declining_passes_the_ride_on_and_ends_as_no_driver_when_nobody_is_left(cab, auth_api):
    _, first = make_driver("d1@click.test")
    second, second_client = make_driver("d2@click.test", lat=12.9800)
    ride = book(auth_api)
    RideDriverOffer.objects.filter(ride_id=ride["id"], driver=second).delete()  # only the first driver was offered it
    assert first.post(f"/api/v1/partner/work/ride/{ride['id']}/decline").status_code == 200
    assert RideDriverOffer.objects.filter(ride_id=ride["id"], driver=second, response="pending").exists()
    assert second_client.post(f"/api/v1/partner/work/ride/{ride['id']}/decline").status_code == 200
    assert Ride.objects.get(pk=ride["id"]).status == "no_driver"


def test_going_offline_withdraws_pending_requests(cab, auth_api):
    driver, client = make_driver("d1@click.test")
    ride = book(auth_api)
    assert client.post("/api/v1/partner/availability", {"available": False}).status_code == 200
    assert RideDriverOffer.objects.get(ride_id=ride["id"], driver=driver).response == "expired"
    assert Ride.objects.get(pk=ride["id"]).status == "no_driver"


def test_delivery_riders_are_not_matched_to_ride_trips(cab, auth_api):
    rider, _ = make_partner("delivery-rider", "rider@click.test", available=True, details={"vehicle_type": "car"})
    DriverLocation.objects.create(driver=rider, lat=Decimal("12.9725"), lng=Decimal("77.6420"), reported_at=timezone.now())
    assert book(auth_api)["status"] == "no_driver"


# --- venues --------------------------------------------------------------------------------------------------

def test_cinema_closing_bookings_stops_new_customer_bookings(auth_api):
    partner, client = make_partner("cinema-hall", "cinema@click.test", available=True)
    venue = Venue.objects.create(name="Hall", slug="hall", kind="cinema", city="Bengaluru")
    PartnerVenue.objects.create(partner=partner, venue=venue)
    event = Event.objects.create(kind="movie", status="now_showing", title="Film", slug="film", duration_minutes=120)
    show = Show.objects.create(event=event, venue=venue, starts_at=timezone.now() + timezone.timedelta(hours=1), rows=5,
                               seats_per_row=10, price=Decimal("200"), premium_price=Decimal("300"))
    body = {"showId": str(show.id), "seats": ["A1"], "paymentMethod": "pay_at_venue", "idempotencyKey": str(uuid.uuid4())}
    assert auth_api.post("/api/v1/customer/bookings", body, format="json").status_code == 201
    home = client.get("/api/v1/partner/home").json()
    assert home["actionRequired"]["data"][0]["title"] == "Film"
    assert {m["key"]: m["value"] for m in home["metrics"]["data"]}["tickets"] == 1
    assert client.post("/api/v1/partner/availability", {"available": False}).status_code == 200
    r = auth_api.post("/api/v1/customer/bookings", {**body, "seats": ["A2"], "idempotencyKey": str(uuid.uuid4())}, format="json")
    assert r.json()["error"]["code"] == "venue_closed"


# --- resilience and notifications ---------------------------------------------------------------------------

def test_one_failing_section_does_not_break_home(restaurant, monkeypatch):
    from apps.orders.partner_workspace import OrdersProvider

    _, client = restaurant
    monkeypatch.setattr(OrdersProvider, "performance", lambda self: 1 / 0)
    home = client.get("/api/v1/partner/home").json()
    assert home["performance"]["status"] == "error" and home["metrics"]["status"] == "ok"


def test_notifications_read_state(restaurant, auth_api, products, address):
    _, client = restaurant
    order_food(auth_api, products, address)
    n = client.get("/api/v1/partner/notifications").json()
    assert n["unread"] == 1
    assert client.post(f"/api/v1/partner/notifications/{n['results'][0]['id']}/read").json()["unread"] == 0
    assert client.post(f"/api/v1/partner/notifications/{uuid.uuid4()}/read").status_code == 404


def test_dev_partner_login_is_absent_without_debug(api, settings):
    settings.DEBUG = False
    assert api.get("/api/v1/partner/dev-login").status_code == 404
