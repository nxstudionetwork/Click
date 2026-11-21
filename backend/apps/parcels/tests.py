"""Click. Parcel: quotes, booking checks, partner lifecycle with PINs, cancellation/refunds, privacy and support links."""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal as D
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.parcels.models import (
    ParcelCategory, ParcelOrder, ParcelRule, ParcelService, ParcelServiceArea, ParcelVehicle, SavedRecipient,
)
from apps.partners.models import Partner, PartnerCategory, PartnerMembership, PartnerProfile
from apps.payments.models import Payment
from apps.rides.models import DriverLocation
from apps.users.models import User
from apps.wallet.models import WalletTransaction

pytestmark = pytest.mark.django_db
HOME = (12.9719, 77.6412)
WORK = (12.9260, 77.6762)
NOON = datetime(2030, 6, 3, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))


@pytest.fixture
def config(db):
    from apps.partners.catalog import apply_catalog
    from apps.partners.models import PartnerType

    apply_catalog(PartnerType, PartnerCategory)
    ParcelServiceArea.objects.create(name="Bengaluru", city="Bengaluru", center_lat=D("12.9716"), center_lng=D("77.5946"), radius_km=D("25"))
    bike = ParcelVehicle.objects.create(code="bike", name="Bike", partner_vehicle_types="bike", max_weight_kg=D("8"), max_length_cm=40,
                                        max_width_cm=35, max_height_cm=35, base_fare=D("30"), per_km=D("8"), minimum_fare=D("45"), per_stop=D("15"),
                                        average_speed_kmh=22)
    truck = ParcelVehicle.objects.create(code="mini_truck", name="Mini Truck", partner_vehicle_types="mini_truck", max_weight_kg=D("750"),
                                         max_length_cm=240, max_width_cm=150, max_height_cm=150, base_fare=D("250"), per_km=D("25"),
                                         minimum_fare=D("400"), average_speed_kmh=15, position=1)
    express = ParcelService.objects.create(code="express", name="Express", price_multiplier=D("1.35"), allow_stops=True, max_stops=2,
                                           cancellation_fee=D("25"))
    express.vehicles.set([bike])
    sched = ParcelService.objects.create(code="scheduled", name="Scheduled", schedule_days=3, schedule_lead_minutes=60, position=1)
    sched.vehicles.set([bike, truck])
    for code, label, allowed, value in [("document", "Document", True, False), ("electronics", "Electronics", True, True),
                                        ("hazardous", "Hazardous", False, False)]:
        ParcelCategory.objects.create(code=code, label=label, is_allowed=allowed, requires_value=value)
    ParcelRule.objects.create(text="Seal the package.")
    return {"bike": bike, "truck": truck, "express": express, "scheduled": sched}


def rider(email="rider@click.test", vtype="bike", at=(12.9730, 77.6400)):
    cat = PartnerCategory.objects.select_related("partner_type").get(slug="delivery-rider")
    user = User.objects.create_user(email, "S3cure-pass-123", full_name="Naveen S")
    p = Partner.objects.create(partner_type=cat.partner_type, category=cat, business_name="Naveen S", status=Partner.Status.VERIFIED,
                               is_available=True, partner_code=f"CLK-PT-{uuid.uuid4().hex[:6]}")
    PartnerMembership.objects.create(partner=p, user=user, role="owner")
    PartnerProfile.objects.create(partner=p, contact_name="Naveen S", details={"vehicle_type": vtype})
    DriverLocation.objects.create(driver=p, lat=D(str(at[0])), lng=D(str(at[1])), reported_at=timezone.now())
    c = APIClient()
    c.force_authenticate(user)
    return p, c


def body(**over):
    b = {"mode": "send",
         "pickup": {"label": "Home", "lat": HOME[0], "lng": HOME[1], "name": "Asha", "phone": "+91 98765 43210"},
         "drop": {"label": "Office", "lat": WORK[0], "lng": WORK[1], "name": "Ravi", "phone": "+91 98765 11111"},
         "package": {"category": "document", "size": "small", "weight_kg": "0.5"}, "service": "express"}
    b.update(over)
    return b


@pytest.fixture
def at_noon(monkeypatch):
    from apps.parcels import pricing

    real = pricing.now_local
    monkeypatch.setattr(pricing, "now_local", lambda now=None: real(now) if now else NOON)
    return NOON


def quote(api, **over):
    r = api.post("/api/v1/customer/parcels/quote", body(**over), format="json")
    assert r.status_code == 200, r.json()
    return r.json()


def book(api, q, vehicle="bike", payment="wallet", **over):
    v = next(x for x in q["vehicles"] if x["code"] == vehicle)
    return api.post("/api/v1/customer/parcels", {**body(**over), "service": q["service"], "vehicle": vehicle, "paymentMethod": payment,
                                                 "expectedTotal": v["fare"]["total"], "idempotencyKey": str(uuid.uuid4()),
                                                 "contentsConfirmed": True}, format="json")


def test_quote_is_backend_priced_and_express_needs_a_real_partner(auth_api, config, at_noon):
    q = quote(auth_api)
    express = next(s for s in q["services"] if s["code"] == "express")
    assert express["available"] is False and "No delivery partner" in express["reason"]
    rider()
    q = quote(auth_api)
    assert q["service"] == "express" and q["estimateBasis"] == "straight_line"
    bike = next(v for v in q["vehicles"] if v["code"] == "bike")
    fare = {k: D(v) for k, v in bike["fare"].items()}
    assert fare["total"] == fare["base"] + fare["distance"] + fare["service"] + fare["stops"] + fare["tax"]
    assert fare["service"] > 0 and "estimated" in bike["window"]
    assert next(v for v in q["vehicles"] if v["code"] == "mini_truck")["reason"] == "Not on this service"


def test_package_rules_and_vehicle_capacity(auth_api, config, at_noon):
    rider()
    assert quote(auth_api, package={"category": "hazardous", "size": "small", "weight_kg": "1"})["packageProblem"].endswith("can't be sent with Click. Parcel.")
    assert "value" in quote(auth_api, package={"category": "electronics", "size": "small", "weight_kg": "1"})["packageProblem"]
    q = quote(auth_api, package={"category": "document", "size": "custom", "weight_kg": "40", "length_cm": 100, "width_cm": 60, "height_cm": 50},
              service="scheduled")
    assert next(v for v in q["vehicles"] if v["code"] == "bike")["reason"] == "Over 8 kg"
    assert next(v for v in q["vehicles"] if v["code"] == "mini_truck")["available"]


def test_outside_service_area_is_not_offered(auth_api, config):
    r = auth_api.post("/api/v1/customer/parcels/quote", body(drop={"label": "Mysuru", "lat": 12.2958, "lng": 76.6394, "name": "R", "phone": "+91 98765 11111"}),
                      format="json")
    assert r.status_code == 400 and r.json()["error"]["code"] == "not_serviceable"


def test_full_send_flow_with_pins_proof_and_partner_isolation(auth_api, customer, config, at_noon, django_capture_on_commit_callbacks):
    p1, c1 = rider()
    _, c2 = rider("other@click.test", at=(12.9740, 77.6390))
    q = quote(auth_api)
    r = book(auth_api, q, payment="cash")
    assert r.status_code == 201, r.json()
    d = r.json()
    assert d["status"] == "searching" and len(d["pins"]["pickup"]) == 4 and d["drop"]["phoneMasked"].endswith("1111")
    parcel = ParcelOrder.objects.get(pk=d["id"])
    assert parcel.job_offers.count() == 2
    # Partner work items never include the PINs.
    home = c1.get("/api/v1/partner/home").json()
    assert parcel.pickup_pin not in str(home) and parcel.delivery_pin not in str(home)
    assert c1.post(f"/api/v1/partner/work/parcel/{parcel.id}/accept", {}, format="json").status_code == 200
    assert c2.post(f"/api/v1/partner/work/parcel/{parcel.id}/accept", {}, format="json").status_code == 409
    assert c2.post(f"/api/v1/partner/work/parcel/{parcel.id}/arrived", {}, format="json").status_code == 404
    c1.post(f"/api/v1/partner/work/parcel/{parcel.id}/arrived", {}, format="json")
    wrong = "0000" if parcel.pickup_pin != "0000" else "1111"
    assert c1.post(f"/api/v1/partner/work/parcel/{parcel.id}/pickup", {"reason": wrong}, format="json").status_code == 400
    assert c1.post(f"/api/v1/partner/work/parcel/{parcel.id}/deliver", {"reason": parcel.delivery_pin}, format="json").status_code == 409
    assert c1.post(f"/api/v1/partner/work/parcel/{parcel.id}/pickup", {"reason": parcel.pickup_pin}, format="json").status_code == 200
    assert Payment.objects.get(parcel=parcel).status == "captured"  # cash collected at pickup
    c1.post(f"/api/v1/partner/work/parcel/{parcel.id}/near", {}, format="json")
    assert c1.post(f"/api/v1/partner/work/parcel/{parcel.id}/deliver", {"reason": parcel.delivery_pin}, format="json").status_code == 200
    d = auth_api.get(f"/api/v1/customer/parcels/{parcel.id}").json()
    assert d["status"] == "delivered" and [p["kind"] for p in d["proofs"]] == ["pickup", "delivery"]
    assert d["pins"] == {"pickup": None, "delivery": None}
    assert [t["status"] for t in d["timeline"] if t["at"]][-1] == "delivered"


def test_price_must_match_and_booking_is_idempotent(auth_api, config, at_noon):
    rider()
    q = quote(auth_api)
    v = next(x for x in q["vehicles"] if x["code"] == "bike")
    key = str(uuid.uuid4())
    payload = {**body(), "service": "express", "vehicle": "bike", "paymentMethod": "cash", "expectedTotal": "1.00", "idempotencyKey": key,
               "contentsConfirmed": True}
    r = auth_api.post("/api/v1/customer/parcels", payload, format="json")
    assert r.status_code == 409 and r.json()["error"]["code"] == "price_changed"
    payload["expectedTotal"] = v["fare"]["total"]
    assert auth_api.post("/api/v1/customer/parcels", {**payload, "contentsConfirmed": False}, format="json").status_code == 400
    a = auth_api.post("/api/v1/customer/parcels", payload, format="json")
    b = auth_api.post("/api/v1/customer/parcels", payload, format="json")
    assert a.status_code == 201 and b.status_code == 200 and a.json()["id"] == b.json()["id"]


def test_cash_only_for_send_and_phone_validation(auth_api, config, at_noon):
    rider()
    q = quote(auth_api, mode="receive")
    assert q["paymentMethods"] == ["wallet"]
    r = book(auth_api, quote(auth_api), payment="cash", drop={"label": "Office", "lat": WORK[0], "lng": WORK[1], "name": "Ravi", "phone": "12"})
    assert r.status_code == 400 and "phone" in r.json()["error"]["message"]


def test_cancellation_free_before_assignment_and_fee_after(auth_api, customer, config, at_noon):
    from apps.wallet.services import balance

    WalletTransaction.objects.create(customer=customer.customer_profile, kind="topup", amount=D("1000"), description="Test top-up")
    p1, c1 = rider()
    q = quote(auth_api)
    first = book(auth_api, q).json()
    assert first["payment"]["status"] == "captured" and first["cancellation"]["fee"] == "0.00"
    r = auth_api.post(f"/api/v1/customer/parcels/{first['id']}/cancel", {"reason": "Changed plans"}, format="json").json()
    assert r["status"] == "cancelled" and r["payment"]["refunded"]
    second = book(auth_api, quote(auth_api)).json()
    c1.post(f"/api/v1/partner/work/parcel/{second['id']}/accept", {}, format="json")
    terms = auth_api.get(f"/api/v1/customer/parcels/{second['id']}").json()["cancellation"]
    assert terms["fee"] == "25.00"
    before = balance(customer.customer_profile)
    auth_api.post(f"/api/v1/customer/parcels/{second['id']}/cancel", {"reason": "No longer needed"}, format="json")
    assert balance(customer.customer_profile) == before + D(second["fare"]["total"]) - D("25")
    assert balance(customer.customer_profile) == D("1000") - D("25")  # first booking fully refunded, second kept only the fee


def test_cannot_cancel_after_pickup(auth_api, config, at_noon):
    _, c1 = rider()
    d = book(auth_api, quote(auth_api), payment="cash").json()
    p = ParcelOrder.objects.get(pk=d["id"])
    for action, payload in (("accept", {}), ("arrived", {}), ("pickup", {"code": p.pickup_pin})):
        c1.post(f"/api/v1/partner/work/parcel/{p.id}/{action}", payload, format="json")
    r = auth_api.post(f"/api/v1/customer/parcels/{p.id}/cancel", {"reason": "x"}, format="json")
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_cancellable"


def test_scheduled_booking_uses_real_slots(auth_api, config, at_noon):
    q = quote(auth_api, service="scheduled")
    s = next(x for x in q["services"] if x["code"] == "scheduled")
    assert s["needsTime"] and s["slots"]
    slot = s["slots"][2]["start"]
    q = quote(auth_api, service="scheduled", scheduled_for=slot)
    r = book(auth_api, q, service="scheduled", scheduled_for=slot, payment="cash")
    assert r.status_code == 201 and r.json()["status"] == "scheduled" and r.json()["scheduledFor"]
    bad = quote(auth_api, service="scheduled", scheduled_for="2030-06-03T12:07:00+05:30")
    assert next(x for x in bad["services"] if x["code"] == "scheduled")["available"] is False


def test_tracking_lookup_share_link_and_support_are_private(auth_api, customer, other_customer, config, at_noon):
    rider()
    d = book(auth_api, quote(auth_api), payment="cash").json()
    other = APIClient()
    other.force_authenticate(other_customer)
    assert other.get(f"/api/v1/customer/parcels/{d['id']}").status_code == 404
    assert other.get(f"/api/v1/customer/parcels/track?ref={d['number']}").status_code == 404
    assert auth_api.get(f"/api/v1/customer/parcels/track?ref={d['number'].lower()}").json()["id"] == d["id"]
    token = auth_api.post(f"/api/v1/customer/parcels/{d['id']}/share", {}, format="json").json()["token"]
    shared = APIClient().get(f"/api/v1/parcels/shared/{token}").json()
    assert shared["number"] == d["number"] and "pins" not in shared and "drop" not in shared and "total" not in shared
    assert APIClient().get("/api/v1/parcels/shared/bad-token").status_code == 404
    t = auth_api.post("/api/v1/customer/support/tickets", {"category": "delivery", "subject": "Delayed parcel", "message": "Where is it?",
                                                           "parcelId": d["id"]}, format="json")
    assert t.status_code == 201 and t.json()["parcelNumber"] == d["number"]
    t = other.post("/api/v1/customer/support/tickets", {"category": "delivery", "subject": "x", "message": "y", "parcelId": d["id"]}, format="json")
    assert t.status_code == 400


def test_repeat_and_saved_recipients(auth_api, config, at_noon):
    rider()
    q = quote(auth_api)
    v = next(x for x in q["vehicles"] if x["code"] == "bike")
    d = auth_api.post("/api/v1/customer/parcels", {**body(), "service": "express", "vehicle": "bike", "paymentMethod": "cash",
                                                   "expectedTotal": v["fare"]["total"], "idempotencyKey": str(uuid.uuid4()),
                                                   "contentsConfirmed": True, "saveRecipient": True}, format="json").json()
    assert SavedRecipient.objects.get().name == "Ravi"
    draft = auth_api.get(f"/api/v1/customer/parcels/{d['id']}/repeat").json()
    assert draft["drop"]["phone"] == "+91 98765 11111" and draft["package"]["category"] == "document" and draft["repeatOf"] == d["id"]
    assert len(auth_api.get("/api/v1/customer/parcels/recipients").json()) == 1


def test_options_are_public_and_report_coverage(api, config):
    r = api.get(f"/api/v1/parcels/options?lat={HOME[0]}&lng={HOME[1]}").json()
    assert r["coverage"] == {"checked": True, "available": True, "area": "Bengaluru"}
    assert {c["code"]: c["allowed"] for c in r["categories"]}["hazardous"] is False
    assert api.get("/api/v1/parcels/options?lat=19.07&lng=72.87").json()["coverage"]["available"] is False


def test_express_without_partner_at_booking_ends_honestly(auth_api, customer, config, at_noon):
    p, _ = rider()
    q = quote(auth_api)
    DriverLocation.objects.filter(driver=p).update(reported_at=timezone.now() - timedelta(hours=1))
    r = book(auth_api, q, payment="cash")
    assert r.status_code == 409  # Express no longer available: nothing is booked or charged
    assert not ParcelOrder.objects.exists()
