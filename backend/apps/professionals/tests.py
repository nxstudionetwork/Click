"""Click. Services: discovery, honest availability, booking, offers to professionals, quotes, billing, payment, reviews,
favourites, uploads and ownership."""

import io
import uuid
from datetime import time, timedelta
from decimal import Decimal as D

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.customers.models import Address
from apps.partners.models import Partner, PartnerAddress, PartnerCategory, PartnerMembership, PartnerProfile, PartnerVerification
from apps.professionals.models import (
    ProviderAvailability, ProviderProfile, ProviderService, ServiceBooking, ServiceCategory, ServiceJob, ServiceOffer,
)
from apps.users.models import User
from apps.wallet.models import WalletTransaction

pytestmark = pytest.mark.django_db
HOME = (D("12.971900"), D("77.641200"))


@pytest.fixture
def catalog(db):
    from apps.partners.catalog import apply_catalog
    from apps.partners.models import PartnerType

    apply_catalog(PartnerType, PartnerCategory)
    plumbing = ServiceCategory.objects.create(slug="plumbing", name="Plumbing", profession="Plumber", group="home", synonyms="leak, tap, pipe")
    cooking = ServiceCategory.objects.create(slug="cook", name="Cook", profession="Cook", group="personal", synonyms="cook, meal")
    jobs = {
        "tap": ServiceJob.objects.create(category=plumbing, slug="tap", name="Tap repair", pricing="fixed", price=D("199"), duration_minutes=60),
        "leak": ServiceJob.objects.create(category=plumbing, slug="leak", name="Pipe leakage", pricing="starting", price=D("299")),
        "other": ServiceJob.objects.create(category=plumbing, slug="other", name="Other plumbing", pricing="quote", inspection_fee=D("99")),
        "meal": ServiceJob.objects.create(category=cooking, slug="meal", name="Cook a meal", pricing="hourly", price=D("300"), min_hours=2),
    }
    return {"plumbing": plumbing, "cook": cooking, **jobs}


def pro(catalog, name, cat="plumbing", at=(12.9730, 77.6400), available=True, verified=True, radius=8, email=None):
    pc = PartnerCategory.objects.select_related("partner_type").get(slug="plumber")
    user = User.objects.create_user(email or f"{name.split()[0].lower()}@pro.test", "S3cure-pass-123", full_name=name)
    partner = Partner.objects.create(partner_type=pc.partner_type, category=pc, business_name=name, status=Partner.Status.ACTIVE,
                                     is_available=available, partner_code=f"CLK-PT-{uuid.uuid4().hex[:6]}")
    PartnerMembership.objects.create(partner=partner, user=user, role="owner")
    PartnerProfile.objects.create(partner=partner, contact_name=name, details={})
    PartnerAddress.objects.create(partner=partner, line1="Base", city="Bengaluru", state="KA", postal_code="560001",
                                  latitude=D(str(at[0])), longitude=D(str(at[1])), service_radius_km=radius)
    if verified:
        PartnerVerification.objects.create(partner=partner, status="approved", submitted_at=timezone.now())
    p = ProviderProfile.objects.create(partner=partner, category=catalog[cat], experience_years=7, languages=["Kannada"])
    ProviderService.objects.create(provider=p, category=catalog[cat])
    ProviderAvailability.objects.bulk_create([ProviderAvailability(provider=p, weekday=d, starts_at=time(0, 0), ends_at=time(23, 59)) for d in range(7)])
    c = APIClient()
    c.force_authenticate(user)
    return p, c


@pytest.fixture
def home(customer):
    return Address.objects.create(customer=customer.customer_profile, recipient_name="Asha", phone="+91 98765 43210", line1="1 Test Road",
                                  line2="Indiranagar", city="Bengaluru", postal_code="560038", is_default=True, latitude=HOME[0], longitude=HOME[1])


def book(api, job, home, provider=None, mode="now", **extra):
    est = api.post("/api/v1/customer/services/estimate", {"jobId": str(job.id), "providerId": str(provider.id) if provider else None,
                                                          "addressId": str(home.id), "mode": mode, **extra}, format="json").json()
    r = api.post("/api/v1/customer/services/bookings", {"jobId": str(job.id), "providerId": str(provider.id) if provider else None,
                                                        "addressId": str(home.id), "mode": mode, "expectedAmount": est.get("agreed"),
                                                        "idempotencyKey": str(uuid.uuid4()), **extra}, format="json")
    return r


def act(client, b, action, **payload):
    return client.post(f"/api/v1/partner/work/service/{b}/{action}", payload, format="json")


def fund(customer, amount="5000"):
    WalletTransaction.objects.create(customer=customer.customer_profile, kind="topup", amount=D(amount), description="Test top-up")


def test_discovery_shows_only_real_nearby_professionals(api, catalog, customer, home):
    near, _ = pro(catalog, "Ramesh Kumar")
    pro(catalog, "Far Away", at=(13.10, 77.59), radius=5, email="far@pro.test")
    pro(catalog, "Not Verified", verified=False, available=False, email="nv@pro.test")
    api.force_authenticate(customer)
    cat = api.get(f"/api/v1/services/categories/plumbing?address={home.id}").json()
    names = {p["name"]: p for p in cat["professionals"]}
    assert set(names) == {"Ramesh Kumar", "Not Verified"}
    r = names["Ramesh Kumar"]
    assert r["verified"] and r["availability"] == "now" and r["etaMinutes"] and r["distanceKm"] < 1 and r["priceLabel"] == "From ₹199"
    assert r["rating"] is None and r["jobsCompleted"] == 0 and r["photoUrl"] == ""  # nothing invented
    assert names["Not Verified"]["verified"] is False and names["Not Verified"]["availability"] != "now"
    assert [c["slug"] for c in api.get(f"/api/v1/services/home?address={home.id}").json()["categories"]] == ["plumbing"]  # cook has nobody
    assert api.get("/api/v1/services/search?q=my tap is leaking").json()["categories"][0]["slug"] == "plumbing"


def test_instant_booking_flow_with_wallet_payment_and_one_review(auth_api, customer, catalog, home):
    p, pc = pro(catalog, "Ramesh Kumar")
    fund(customer)
    r = book(auth_api, catalog["tap"], home, p)
    assert r.status_code == 201, r.json()
    b = r.json()
    assert b["status"] == "requested" and b["agreedAmount"] == "199.00" and not b["payment"]  # nothing charged at booking
    for step in ("accept", "on_the_way", "arrived", "start"):
        assert act(pc, b["id"], step).status_code == 200, step
    assert auth_api.post(f"/api/v1/customer/services/bookings/{b['id']}/pay", {"method": "wallet"}, format="json").status_code == 409
    act(pc, b["id"], "complete")
    d = auth_api.get(f"/api/v1/customer/services/bookings/{b['id']}").json()
    assert d["status"] == "completed" and d["total"] == "234.82"  # 199 + 18% tax
    d = auth_api.post(f"/api/v1/customer/services/bookings/{b['id']}/pay", {"method": "wallet"}, format="json").json()
    assert d["status"] == "paid" and d["payment"]["status"] == "captured"
    review = {"overall": 5, "quality": 5, "behaviour": 4, "timeliness": 5, "comment": "Neat"}
    assert auth_api.post(f"/api/v1/customer/services/bookings/{b['id']}/review", review, format="json").status_code == 200
    assert auth_api.post(f"/api/v1/customer/services/bookings/{b['id']}/review", review, format="json").status_code == 409
    p.refresh_from_db()
    assert (p.rating_average, p.rating_count, p.jobs_completed) == (D("5.0"), 1, 1)


def test_any_available_is_offered_to_several_and_first_accept_wins(auth_api, catalog, home):
    a, ac = pro(catalog, "Ramesh Kumar")
    b_, bc = pro(catalog, "Shabbir Ahmed", at=(12.9650, 77.6380))
    r = book(auth_api, catalog["tap"], home).json()
    assert {o.provider_id for o in ServiceBooking.objects.get(pk=r["id"]).job_offers.all()} == {a.id, b_.id}
    assert act(bc, r["id"], "accept").status_code == 200
    assert act(ac, r["id"], "accept").status_code == 409
    assert act(ac, r["id"], "on_the_way").status_code == 404  # not their job


def test_quote_jobs_need_customer_approval_and_decline_charges_only_the_inspection_fee(auth_api, customer, catalog, home):
    p, pc = pro(catalog, "Ramesh Kumar")
    b = book(auth_api, catalog["other"], home, p).json()
    assert b["agreedAmount"] is None
    for s in ("accept", "on_the_way", "arrived"):
        act(pc, b["id"], s)
    assert act(pc, b["id"], "start").status_code == 409  # no approved quote yet
    act(pc, b["id"], "quote", reason="1450 replace the pipe section")
    assert act(pc, b["id"], "start").status_code == 409  # quote pending
    d = auth_api.post(f"/api/v1/customer/services/bookings/{b['id']}/quote", {"approve": False}, format="json").json()
    assert d["status"] == "completed" and d["total"] == "116.82"  # ₹99 inspection fee + tax
    assert d["quotes"][0]["status"] == "declined"


def test_starting_price_increase_needs_approval_and_hourly_never_bills_more_than_booked(auth_api, catalog, home):
    p, pc = pro(catalog, "Ramesh Kumar")
    b = book(auth_api, catalog["leak"], home, p).json()
    for s in ("accept", "on_the_way", "arrived", "start"):
        act(pc, b["id"], s)
    act(pc, b["id"], "quote", amount="900", note="Joint needs replacing")
    d = auth_api.post(f"/api/v1/customer/services/bookings/{b['id']}/quote", {"approve": True}, format="json").json()
    assert d["status"] == "in_progress" and d["agreedAmount"] == "900.00"
    cook, cc = pro(catalog, "Selvi M", cat="cook", email="selvi@pro.test")
    h = book(auth_api, catalog["meal"], home, cook, hours=3).json()
    assert h["agreedAmount"] == "900.00"  # 3 h x 300
    for s in ("accept", "on_the_way", "arrived", "start"):
        act(cc, h["id"], s)
    assert act(cc, h["id"], "complete").status_code == 400  # hours required
    act(cc, h["id"], "complete", reason="5")  # worked 5 h, booked 3: bills 3 without an approved quote
    d = auth_api.get(f"/api/v1/customer/services/bookings/{h['id']}").json()
    assert d["billedHours"] == "3.00" and d["total"] == "1062.00"


def test_scheduled_slots_exclude_booked_times_and_cash_is_confirmed_by_the_professional(auth_api, catalog, home, other_customer):
    p, pc = pro(catalog, "Ramesh Kumar")
    slots = APIClient().get(f"/api/v1/services/providers/{p.id}/slots?job={catalog['tap'].id}").json()["slots"]
    first = slots[0]["start"]
    b = book(auth_api, catalog["tap"], home, p, mode="scheduled", scheduledStart=first)
    assert b.status_code == 201 and b.json()["status"] == "requested"
    act(pc, b.json()["id"], "accept")
    after = APIClient().get(f"/api/v1/services/providers/{p.id}/slots?job={catalog['tap'].id}").json()["slots"]
    assert first not in [s["start"] for s in after]
    for s in ("on_the_way", "arrived", "start", "complete"):
        act(pc, b.json()["id"], s)
    d = auth_api.post(f"/api/v1/customer/services/bookings/{b.json()['id']}/pay", {"method": "cash"}, format="json").json()
    assert d["status"] == "completed" and d["awaitingCash"]
    assert act(pc, b.json()["id"], "cash_received").json()["item"]["status"] == "paid"


def test_any_available_scheduling_offers_every_eligible_professionals_slots_and_shows_who_was_asked(auth_api, catalog, home):
    p, pc = pro(catalog, "Ramesh Kumar")
    q, _ = pro(catalog, "Imran Shaikh", at=(12.9740, 77.6410))
    est = auth_api.post("/api/v1/customer/services/estimate", {"jobId": str(catalog["tap"].id), "addressId": str(home.id), "mode": "scheduled"},
                        format="json").json()
    union = {s["start"] for s in est["slots"]}
    assert est["slots"] and est["job"]["categorySlug"] == "plumbing"
    assert {s["start"] for s in APIClient().get(f"/api/v1/services/providers/{q.id}/slots?job={catalog['tap'].id}").json()["slots"]} <= union | set()
    b = book(auth_api, catalog["tap"], home, p).json()
    assert b["provider"] is None and b["requestedProvider"]["name"] == "Ramesh Kumar"
    d = act(pc, b["id"], "accept")
    after = auth_api.get(f"/api/v1/customer/services/bookings/{b['id']}").json()
    assert after["provider"]["name"] == "Ramesh Kumar" and after["requestedProvider"] is None
    assert after["timeline"][-1]["note"] == "Accepted by Ramesh Kumar"  # never an internal partner code


def test_cancellation_rules_expiry_and_ownership(auth_api, catalog, home, other_customer):
    p, pc = pro(catalog, "Ramesh Kumar")
    b = book(auth_api, catalog["tap"], home, p).json()
    other = APIClient()
    other.force_authenticate(other_customer)
    assert other.get(f"/api/v1/customer/services/bookings/{b['id']}").status_code == 404
    assert other.post(f"/api/v1/customer/services/bookings/{b['id']}/cancel", {"reason": "x y"}, format="json").status_code == 404
    act(pc, b["id"], "accept")
    act(pc, b["id"], "on_the_way")
    r = auth_api.post(f"/api/v1/customer/services/bookings/{b['id']}/cancel", {"reason": "Changed plans"}, format="json")
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_cancellable"
    c = book(auth_api, catalog["leak"], home, p, mode="now")
    assert c.status_code == 409  # the professional is busy on the first job: not offered
    ServiceBooking.objects.filter(pk=b["id"]).update(status="paid")
    d = book(auth_api, catalog["leak"], home, p).json()
    ServiceBooking.objects.filter(pk=d["id"]).update(offers_expire_at=timezone.now() - timedelta(minutes=1))
    assert auth_api.get(f"/api/v1/customer/services/bookings/{d['id']}").json()["status"] == "unassigned"


def test_offers_apply_to_the_final_amount(auth_api, customer, catalog, home):
    ServiceOffer.objects.create(title="First service: 15% off", kind="percent", value=D("15"), max_discount=D("150"), first_booking_only=True)
    p, pc = pro(catalog, "Ramesh Kumar")
    est = auth_api.post("/api/v1/customer/services/estimate", {"jobId": str(catalog["tap"].id), "providerId": str(p.id),
                                                               "addressId": str(home.id), "mode": "now"}, format="json").json()
    assert est["offer"] == {"title": "First service: 15% off", "discount": "29.85"}
    b = book(auth_api, catalog["tap"], home, p).json()
    for s in ("accept", "on_the_way", "arrived", "start", "complete"):
        act(pc, b["id"], s)
    d = auth_api.get(f"/api/v1/customer/services/bookings/{b['id']}").json()
    assert d["discount"] == "29.85" and d["total"] == f"{(D('199') - D('29.85')) * D('1.18'):.2f}"


def test_favorites_photos_and_needs(auth_api, customer, other_customer, catalog, home):
    from PIL import Image

    p, pc = pro(catalog, "Ramesh Kumar")
    assert auth_api.post("/api/v1/customer/wishlist", {"providerId": str(p.id)}, format="json").status_code == 201
    favs = auth_api.get("/api/v1/customer/services/favorites").json()["results"]
    assert [f["name"] for f in favs] == ["Ramesh Kumar"]
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), "red").save(buf, "JPEG")
    buf.seek(0)
    buf.name = "leak.jpg"
    up = auth_api.post("/api/v1/customer/services/attachments", {"file": buf}, format="multipart")
    assert up.status_code == 201 and up.json()["src"].endswith(".webp")
    bad = io.BytesIO(b"not an image")
    bad.name = "x.jpg"
    assert auth_api.post("/api/v1/customer/services/attachments", {"file": bad}, format="multipart").status_code == 400
    other = APIClient()
    other.force_authenticate(other_customer)
    r = other.post("/api/v1/customer/services/needs", {"text": "Need a piano tuner", "attachmentIds": [up.json()["id"]]}, format="json")
    assert r.status_code == 201  # someone else's photo is silently not attached
    b = book(auth_api, catalog["tap"], home, p, description="Kitchen tap", attachmentIds=[up.json()["id"]]).json()
    assert len(b["photos"]) == 1
    # The professional manages only their own profile.
    assert pc.patch("/api/v1/partner/services/profile", {"about": "Leak expert", "experienceYears": 9}, format="json").json()["about"] == "Leak expert"
    img = io.BytesIO()
    Image.new("RGB", (900, 900), "blue").save(img, "PNG")
    img.seek(0)
    img.name = "me.png"
    assert pc.post("/api/v1/partner/services/profile", {"photo": img}, format="multipart").json()["photoUrl"].endswith(".webp")


def test_buddy_finds_services_but_never_books(auth_api, catalog, home):
    pro(catalog, "Ramesh Kumar")
    r = auth_api.post("/api/v1/customer/assistant/messages", {"messages": [{"role": "user", "content": "My kitchen tap is leaking"}]}, format="json").json()
    assert "plumbing" in r["message"]["content"].lower() and any(a.get("path", "").startswith("/services") for a in r["actions"])
    assert not ServiceBooking.objects.exists()

