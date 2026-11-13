import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.partners.models import Partner, PartnerCategory, PartnerMembership, PartnerProfile, PartnerType
from apps.rides.models import DriverLocation, Ride, RideOffer, RideType
from apps.users.models import User
from apps.wallet.models import WalletTransaction
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db
INDIRANAGAR = {"label": "Home", "address": "12th Cross, Indiranagar", "lat": 12.9719, "lng": 77.6412}
KORAMANGALA = {"label": "Office", "address": "Koramangala 5th Block", "lat": 12.9352, "lng": 77.6245}
YELAHANKA = {"label": "Far away", "address": "Yelahanka", "lat": 13.1005, "lng": 77.5963}


@pytest.fixture
def cab(db):
    return RideType.objects.create(code="cab", name="Cab", vehicle_types="car", seats=4, base_fare=Decimal("50"), per_km=Decimal("16"),
                                   per_minute=Decimal("2"), minimum_fare=Decimal("90"), booking_fee=Decimal("5"), per_stop=Decimal("20"), average_speed_kmh=22)


def make_driver(email="driver@click.local", vehicle="car", lat=12.9725, lng=77.6420, status=Partner.Status.VERIFIED, online=True):
    ptype, _ = PartnerType.objects.get_or_create(slug="transport", defaults={"name": "Transport"})
    cat, _ = PartnerCategory.objects.get_or_create(partner_type=ptype, slug="cab-driver", defaults={"name": "Cab Driver"})
    user = User.objects.create_user(email, "S3cure-pass-123", full_name="Ravi Kumar")
    partner = Partner.objects.create(partner_type=ptype, category=cat, business_name="Ravi Kumar", status=status, is_available=online)
    PartnerMembership.objects.create(partner=partner, user=user, role="owner")
    PartnerProfile.objects.create(partner=partner, contact_name="Ravi Kumar", details={"vehicle_type": vehicle, "vehicle_model": "Maruti Dzire",
                                                                                        "vehicle_color": "White", "vehicle_number": "KA 01 AB 4521"})
    DriverLocation.objects.create(driver=partner, lat=Decimal(str(lat)), lng=Decimal(str(lng)), reported_at=timezone.now())
    return partner, user


def book(api, **over):
    body = {"pickup": INDIRANAGAR, "drop": KORAMANGALA, "rideType": "cab", "paymentMethod": "cash", "idempotencyKey": str(uuid.uuid4()), **over}
    return api.post("/api/v1/customer/rides", body, format="json")


def fund(customer, amount):
    WalletTransaction.objects.create(customer=customer.customer_profile, kind=WalletTransaction.Kind.TOPUP, amount=Decimal(amount), description="test")


def test_quote_prices_on_the_server_and_eta_needs_a_real_driver(auth_api, cab):
    r = auth_api.post("/api/v1/customer/rides/quote", {"pickup": INDIRANAGAR, "drop": KORAMANGALA}, format="json")
    assert r.status_code == 200
    body = r.json()
    assert body["estimateBasis"] == "straight_line"
    opt = body["options"][0]
    assert opt["available"] is False and opt["pickupEtaMinutes"] is None  # no driver online: no ETA is invented
    km = Decimal(body["distanceKm"])
    assert Decimal("5") < km < Decimal("7")
    fare = opt["fare"]
    assert Decimal(fare["total"]) == Decimal(fare["subtotal"]) and Decimal(fare["total"]) >= Decimal("95")
    make_driver()
    opt = auth_api.post("/api/v1/customer/rides/quote", {"pickup": INDIRANAGAR, "drop": KORAMANGALA}, format="json").json()["options"][0]
    assert opt["available"] is True and opt["pickupEtaMinutes"] >= 1


def test_trip_validation(auth_api, cab):
    same = auth_api.post("/api/v1/customer/rides/quote", {"pickup": INDIRANAGAR, "drop": INDIRANAGAR}, format="json")
    assert same.json()["error"]["code"] == "trip_too_short"
    far = auth_api.post("/api/v1/customer/rides/quote", {"pickup": INDIRANAGAR, "drop": {**KORAMANGALA, "lat": 13.9}}, format="json")
    assert far.json()["error"]["code"] == "trip_too_long"
    bad = auth_api.post("/api/v1/customer/rides/quote", {"pickup": {**INDIRANAGAR, "lat": 123}, "drop": KORAMANGALA}, format="json")
    assert bad.status_code == 400
    many = auth_api.post("/api/v1/customer/rides/quote", {"pickup": INDIRANAGAR, "drop": KORAMANGALA, "stops": [YELAHANKA] * 3}, format="json")
    assert many.status_code == 400


def test_booking_is_idempotent_ignores_client_prices_and_offers_to_nearby_drivers(auth_api, cab):
    driver, _ = make_driver()
    key = str(uuid.uuid4())
    first = book(auth_api, idempotencyKey=key, fare={"total": "1.00"})
    second = book(auth_api, idempotencyKey=key)
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"] and Ride.objects.count() == 1
    ride = Ride.objects.get()
    assert ride.status == "searching" and ride.total > Decimal("90")
    assert list(ride.driver_offers.values_list("driver_id", flat=True)) == [driver.id]
    assert first.json()["driver"] is None  # nobody is shown until a driver actually accepts


def test_no_driver_nearby_ends_immediately_and_refunds_wallet(auth_api, cab, customer):
    make_driver()  # in Indiranagar; pickup is ~14 km away in Yelahanka
    fund(customer, "1000")
    r = book(auth_api, pickup=YELAHANKA, drop=INDIRANAGAR, paymentMethod="wallet")
    assert r.status_code == 201 and r.json()["status"] == "no_driver"
    assert r.json()["payment"]["status"] == "refunded"
    assert sum(WalletTransaction.objects.filter(customer=customer.customer_profile).values_list("amount", flat=True)) == Decimal("1000")


def test_wallet_needs_enough_balance_and_nothing_is_created_on_failure(auth_api, cab, customer):
    make_driver()
    r = book(auth_api, paymentMethod="wallet")
    assert r.json()["error"]["code"] == "insufficient_wallet_balance"
    assert Ride.objects.count() == 0
    assert book(auth_api, paymentMethod="cash").status_code == 201  # change payment and retry


def test_driver_flow_status_is_server_controlled_and_driver_only(auth_api, cab, customer):
    api = APIClient()  # the driver's own client
    driver, driver_user = make_driver()
    other, other_user = make_driver("other@click.local")
    ride_id = book(auth_api).json()["id"]
    api.force_authenticate(other_user)
    assert api.post(f"/api/v1/partner/rides/{ride_id}/status", {"status": "driver_arrived"}, format="json").status_code == 404
    api.force_authenticate(driver_user)
    assert api.get("/api/v1/partner/rides/offers").json()["results"][0]["id"] == ride_id
    assert api.post(f"/api/v1/partner/rides/{ride_id}/accept").status_code == 200
    detail = auth_api.get(f"/api/v1/customer/rides/{ride_id}").json()
    assert detail["status"] == "driver_assigned"
    assert detail["driver"]["plate"] == "KA 01 AB 4521" and detail["driver"]["vehicleColor"] == "White" and detail["driver"]["name"] == "Ravi"
    assert detail["driver"]["location"]["live"] is True
    # Can't skip steps.
    assert api.post(f"/api/v1/partner/rides/{ride_id}/status", {"status": "completed"}, format="json").status_code == 409
    for step in ("driver_arrived", "in_progress", "completed"):
        assert api.post(f"/api/v1/partner/rides/{ride_id}/status", {"status": step}, format="json").status_code == 200
    done = auth_api.get(f"/api/v1/customer/rides/{ride_id}").json()
    assert done["status"] == "completed" and done["payment"] == {"method": "cash", "status": "captured"}
    assert done["canCancel"] is False and done["driver"]["location"] is None  # location isn't shared after the trip
    r = auth_api.post(f"/api/v1/customer/rides/{ride_id}/rating", {"stars": 5, "compliment": "safe_driving"}, format="json")
    assert r.status_code == 201 and r.json()["rating"]["stars"] == 5
    assert auth_api.post(f"/api/v1/customer/rides/{ride_id}/rating", {"stars": 4}, format="json").status_code == 409
    assert auth_api.get(f"/api/v1/customer/rides/{ride_id}").json()["driver"]["rating"] == 5.0


def test_customer_cancel_refunds_and_ownership(auth_api, cab, customer, other_customer):
    api = APIClient()  # another customer's client
    make_driver()
    fund(customer, "500")
    ride_id = book(auth_api, paymentMethod="wallet").json()["id"]
    api.force_authenticate(other_customer)
    assert api.get(f"/api/v1/customer/rides/{ride_id}").status_code == 404
    assert api.post(f"/api/v1/customer/rides/{ride_id}/cancel").status_code == 404
    r = auth_api.post(f"/api/v1/customer/rides/{ride_id}/cancel", {"reason": "Changed plans"}, format="json")
    assert r.json()["status"] == "cancelled" and r.json()["payment"]["status"] == "refunded"
    assert auth_api.post(f"/api/v1/customer/rides/{ride_id}/cancel").status_code == 409


def test_offers_schedule_passenger_and_safety(auth_api, cab):
    make_driver()
    offer = RideOffer.objects.create(title="20% off", discount_type="percent", discount_value=20, max_discount=Decimal("30"))
    offer.ride_types.set([cab])
    q = auth_api.post("/api/v1/customer/rides/quote", {"pickup": INDIRANAGAR, "drop": KORAMANGALA, "offerId": str(offer.id)}, format="json").json()
    fare = q["options"][0]["fare"]
    assert Decimal(fare["discount"]) == min(Decimal(fare["subtotal"]) * Decimal("0.2"), Decimal("30")).quantize(Decimal("1"))
    ended = RideOffer.objects.create(title="Old", discount_type="flat", discount_value=10, ends_at=timezone.now() - timedelta(days=1))
    assert book(auth_api, offerId=str(ended.id)).json()["error"]["code"] == "offer_not_applicable"

    soon = book(auth_api, scheduledFor=(timezone.now() + timedelta(minutes=5)).isoformat())
    assert soon.json()["error"]["code"] == "invalid_schedule_time"
    later = book(auth_api, scheduledFor=(timezone.now() + timedelta(hours=3)).isoformat(), passengerName="Amma", passengerPhone="+91 98765 43210")
    assert later.status_code == 201 and later.json()["status"] == "scheduled" and later.json()["passengerName"] == "Amma"
    assert book(auth_api, passengerName="Only name").json()["error"]["code"] == "passenger_incomplete"

    ride_id = later.json()["id"]
    assert auth_api.post(f"/api/v1/customer/rides/{ride_id}/safety", {"kind": "share"}, format="json").status_code == 201
    assert auth_api.post(f"/api/v1/customer/rides/{ride_id}/safety", {"kind": "teleport"}, format="json").status_code == 400


def test_places_come_from_click_data_only(auth_api, customer, address):
    address.latitude, address.longitude = Decimal("12.971900"), Decimal("77.641200")
    address.save()
    results = auth_api.get("/api/v1/customer/rides/places?q=MG").json()["results"]
    assert results[0]["kind"] == "saved" and results[0]["lat"] == 12.9719
    assert auth_api.get("/api/v1/customer/rides/places?q=zzzz").json()["results"] == []


def test_ride_endpoints_require_a_customer(api):
    assert api.post("/api/v1/customer/rides/quote", {}, format="json").status_code == 401
    assert api.get("/api/v1/customer/rides").status_code == 401
