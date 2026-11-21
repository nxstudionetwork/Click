"""Click. Events: discovery and filters, honest availability, planning, quotes through the Partner workspace, booking and
payment through the shared wallet, cancellation refunds, milestones, reviews, favourites, ownership, Buddy and Buzz."""

import uuid
from datetime import timedelta
from decimal import Decimal as D

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.customers.models import Address
from apps.eventhub import engine
from apps.eventhub.models import (
    EventBooking, EventPackage, EventPlan, EventProvider, EventService, EventType, PackageAddon, ProviderBlockedDate, VenueDetails,
)
from apps.partners.models import Partner, PartnerCategory, PartnerMembership, PartnerProfile, PartnerVerification
from apps.users.models import User
from apps.wallet.models import WalletTransaction

pytestmark = pytest.mark.django_db
HOME = (D("12.971900"), D("77.641200"))
CUST = "/api/v1/customer/eventhub"


@pytest.fixture
def registry(db):
    from apps.partners.catalog import apply_catalog
    from apps.partners.models import PartnerType

    apply_catalog(PartnerType, PartnerCategory)
    s = {slug: EventService.objects.create(slug=slug, name=name, synonyms=syn) for slug, name, syn in [
        ("decoration", "Decoration", ["decor", "decorator"]), ("catering", "Catering", ["caterer"]), ("photography", "Photography", ["photographer"]),
        ("venue", "Venue", ["hall", "banquet"]), ("dj", "DJ", [])]}
    t = {slug: EventType.objects.create(slug=slug, name=name, synonyms=syn, checklist=[
        {"key": "decor", "label": "Confirm decoration", "service": "decoration"}, {"key": "venue", "label": "Choose the venue", "service": "venue"},
        {"key": "photo", "label": "Confirm photography", "service": "photography"}]) for slug, name, syn in [
        ("birthday", "Birthday", ["bday"]), ("wedding", "Wedding", ["shaadi"])]}
    return {"s": s, "t": t}


def provider(reg, name, kind="team", services=("decoration", "photography"), types=("birthday",), at=(12.9730, 77.6400), radius=20,
             verified=True, guests=(10, 200), cat="event-planner", listed=True, per_day=1):
    pc = PartnerCategory.objects.select_related("partner_type").get(slug=cat)
    user = User.objects.create_user(f"{uuid.uuid4().hex[:8]}@events.test", "S3cure-pass-123", full_name=name)
    partner = Partner.objects.create(partner_type=pc.partner_type, category=pc, business_name=name, status=Partner.Status.ACTIVE,
                                     is_available=True, partner_code=f"CLK-PT-{uuid.uuid4().hex[:6]}")
    PartnerMembership.objects.create(partner=partner, user=user, role="owner")
    PartnerProfile.objects.create(partner=partner, contact_name=name, details={})
    if verified:
        PartnerVerification.objects.create(partner=partner, status="approved", submitted_at=timezone.now())
    p = EventProvider.objects.create(partner=partner, kind=kind, area="Indiranagar", latitude=D(str(at[0])), longitude=D(str(at[1])),
                                     service_radius_km=radius, min_guests=guests[0], max_guests=guests[1], is_listed=listed,
                                     min_notice_days=2, max_events_per_day=per_day)
    p.services.set([reg["s"][x] for x in services])
    p.event_types.set([reg["t"][x] for x in types])
    c = APIClient()
    c.force_authenticate(user)
    return p, c


def package(p, reg, name="Birthday Basic", price="15000", basis="fixed", guests=(10, 60), services=("decoration",), types=("birthday",)):
    pkg = EventPackage.objects.create(provider=p, name=name, price=D(price), basis=basis, min_guests=guests[0], max_guests=guests[1], duration_hours=D("3"))
    pkg.services.set([reg["s"][x] for x in services])
    pkg.event_types.set([reg["t"][x] for x in types])
    return pkg


@pytest.fixture
def home(customer):
    return Address.objects.create(customer=customer.customer_profile, recipient_name="Asha", phone="+91 98765 43210", line1="1 Test Road",
                                  line2="Indiranagar", city="Bengaluru", postal_code="560038", is_default=True, latitude=HOME[0], longitude=HOME[1])


def fund(customer, amount="100000"):
    WalletTransaction.objects.create(customer=customer.customer_profile, kind="topup", amount=D(amount), description="Test top-up")


def make_plan(api, home, days=20, guests=40, services=("decoration", "photography"), event_type="birthday", **extra):
    r = api.post(f"{CUST}/plans", {"eventType": event_type, "date": (engine.today() + timedelta(days=days)).isoformat(), "addressId": str(home.id),
                                   "guests": guests, "services": list(services), "requirements": "Superhero theme", **extra}, format="json")
    assert r.status_code == 201, r.json()
    return r.json()


def book(api, plan_id, **body):
    est = api.post(f"{CUST}/estimate", {"planId": plan_id, **body}, format="json").json()
    return api.post(f"{CUST}/bookings", {"planId": plan_id, "expectedTotal": est.get("total"), "idempotencyKey": str(uuid.uuid4()), **body}, format="json")


def work(client, kind, item, action, reason=""):
    return client.post(f"/api/v1/partner/work/{kind}/{item}/{action}", {"reason": reason}, format="json")


def test_discovery_filters_and_registry_are_real(api, registry, customer, home):
    a, _ = provider(registry, "Confetti Crew")
    package(a, registry)
    provider(registry, "Far Away Events", at=(13.30, 77.90), radius=5)
    provider(registry, "Unlisted Team", listed=False)
    provider(registry, "Wedding Only", types=("wedding",), services=("catering",), verified=False)
    v, _ = provider(registry, "Grand Hall", kind="venue", services=("venue",), types=("birthday", "wedding"), cat="venue", guests=(1, 500))
    VenueDetails.objects.create(provider=v, space_type="Banquet hall", seated_capacity=200, floating_capacity=300, amenities=["Parking"])
    api.force_authenticate(customer)
    h = api.get(f"/api/v1/eventhub/home?address={home.id}").json()
    names = {c["name"] for c in h["teams"]} | {c["name"] for c in h["venues"]}
    assert names == {"Confetti Crew", "Wedding Only", "Grand Hall"}  # unlisted and out-of-area providers never appear
    assert h["counts"]["packages"] == 1 and h["packages"][0]["priceLabel"] == "₹15,000"
    assert {t["slug"] for t in h["eventTypes"]} == {"birthday", "wedding"}
    q = lambda **p: {c["name"] for c in api.get("/api/v1/eventhub/providers", {"address": str(home.id), **p}).json()["results"]}
    assert q(kind="venue") == {"Grand Hall"}
    assert q(type="wedding") == {"Wedding Only", "Grand Hall"}
    assert q(service="catering") == {"Wedding Only"}
    assert q(verified="true") == {"Confetti Crew", "Grand Hall"}
    assert q(guests="400") == set()  # nobody here takes 400 (the hall holds 300)
    assert q(max_budget="10000") == set() and q(max_budget="20000") == {"Confetti Crew"}
    day = engine.today() + timedelta(days=10)
    ProviderBlockedDate.objects.create(provider=a, date=day)
    assert "Confetti Crew" not in q(date=day.isoformat(), available="true")
    card = next(c for c in api.get("/api/v1/eventhub/providers", {"date": day.isoformat()}).json()["results"] if c["name"] == "Confetti Crew")
    assert card["availability"]["state"] == "unavailable" and card["rating"] is None and card["response"] == ""
    s = api.get("/api/v1/eventhub/search?q=decorator").json()
    assert s["services"][0]["slug"] == "decoration" and "Confetti Crew" in {c["name"] for c in s["providers"]}
    prof = api.get(f"/api/v1/eventhub/providers/{v.id}").json()
    assert prof["venue"]["floating"] == 300 and prof["portfolio"] == [] and prof["reviews"] == []


def test_plan_quote_book_pay_run_review(auth_api, registry, customer, home):
    p, pc = provider(registry, "Confetti Crew")
    other, _ = provider(registry, "Snapshots", services=("photography",))
    plan = make_plan(auth_api, home)
    assert [c["label"] for c in plan["checklist"]][:2] == ["Confirm decoration", "Confirm photography"]  # venue step dropped: not needed
    matches = auth_api.get(f"{CUST}/plans/{plan['id']}/matches").json()["results"]
    assert [m["name"] for m in matches][0] == "Confetti Crew" and matches[0]["covers"] == ["decoration", "photography"]
    r = auth_api.post(f"{CUST}/plans/{plan['id']}/enquiries", {"providerIds": [str(p.id), str(other.id)], "message": "Hi"}, format="json")
    assert r.status_code == 201 and len(r.json()["enquiries"]) == 2
    # The provider sees it in the Partner App workspace and quotes from the text action.
    home_items = pc.get("/api/v1/partner/home").json()
    assert home_items["workspace"]["kind"] == "events", home_items["workspace"]
    req = next(i for i in home_items["actionRequired"]["data"] if i["kind"] == "event_enquiry")
    assert work(pc, "event_enquiry", req["id"], "quote", "abc").status_code == 400  # needs an amount
    assert work(pc, "event_enquiry", req["id"], "quote", "30000 decoration and photos").status_code == 200
    e = next(x for x in auth_api.get(f"{CUST}/plans/{plan['id']}").json()["enquiries"] if x["provider"]["name"] == "Confetti Crew")
    q = e["quotes"][0]
    assert q["amount"] == "30000.00" and q["total"] == "35400.00" and q["status"] == "pending"
    # Ask for changes -> the provider re-quotes (itemised, with an optional item) -> version 2.
    assert auth_api.post(f"{CUST}/enquiries/{e['id']}/changes", {"note": "Add a cake please"}, format="json").json()["status"] == "revision"
    r = pc.post(f"/api/v1/partner/eventhub/enquiries/{e['id']}/quote", {"items": [
        {"label": "Decoration", "amount": "22000"}, {"label": "Photography", "amount": "10000"}, {"label": "Cake (2 kg)", "amount": "3000", "optional": True}],
        "terms": "Venue not included"}, format="json")
    assert r.status_code == 200 and r.json()["quotes"][0]["version"] == 2
    q2 = r.json()["quotes"][0]["id"]
    # Book from the quote, with the optional cake; nothing is charged until the customer confirms with enough balance.
    est = auth_api.post(f"{CUST}/estimate", {"planId": plan["id"], "quoteId": q2, "optionalItems": ["2"]}, format="json").json()
    assert est["subtotal"] == "35000.00" and est["tax"] == "6300.00" and est["total"] == "41300.00" and est["bookable"]
    r = book(auth_api, plan["id"], quoteId=q2, optionalItems=["2"])
    assert r.status_code == 400 and r.json()["error"]["code"] == "insufficient_wallet_balance"
    assert not EventBooking.objects.exists()
    fund(customer)
    r = book(auth_api, plan["id"], quoteId=q2, optionalItems=["2"])
    b = r.json()
    assert r.status_code == 201 and b["status"] == "confirmed" and b["paymentStatus"] == "paid" and b["payment"]["amount"] == "41300.00"
    assert {m["label"] for m in b["milestones"]} >= {"Booking made", "Decoration confirmed", "Event day"}
    detail = auth_api.get(f"{CUST}/plans/{plan['id']}").json()
    assert detail["status"] == "booked" and all(c["done"] for c in detail["checklist"] if c["service"] in ("Decoration", "Photography"))
    assert book(auth_api, plan["id"], quoteId=q2).status_code == 409  # the quote is used
    # The provider runs the event: team, a milestone, can't start early, then start and complete on the day.
    assert work(pc, "event_booking", b["id"], "preparing", "Lead: Priya").status_code == 200
    assert work(pc, "event_booking", b["id"], "milestone", "Theme confirmed").status_code == 200
    assert work(pc, "event_booking", b["id"], "start").json()["error"]["code"] == "too_early"
    EventBooking.objects.filter(pk=b["id"]).update(event_date=engine.today())
    assert auth_api.post(f"{CUST}/bookings/{b['id']}/review", {"overall": 5, "quality": 5, "communication": 5, "value": 5}, format="json").status_code == 409
    work(pc, "event_booking", b["id"], "start")
    work(pc, "event_booking", b["id"], "complete")
    r = auth_api.post(f"{CUST}/bookings/{b['id']}/review", {"overall": 4, "quality": 5, "communication": 4, "value": 3, "comment": "Lovely"}, format="json")
    assert r.status_code == 200 and r.json()["review"]["overall"] == 4
    assert auth_api.post(f"{CUST}/bookings/{b['id']}/review", {"overall": 5, "quality": 5, "communication": 5, "value": 5}, format="json").status_code == 409
    p.refresh_from_db()
    assert p.rating_count == 1 and p.rating_average == D("4.0") and p.events_completed == 1
    assert EventPlan.objects.get(pk=plan["id"]).status == "done"


def test_package_booking_addons_capacity_and_double_booking(auth_api, registry, customer, home, other_customer):
    p, _ = provider(registry, "Confetti Crew")
    pkg = package(p, registry, price="500", basis="per_guest", guests=(20, 80))
    addon = PackageAddon.objects.create(package=pkg, name="Return gifts", price=D("100"), per_guest=True)
    fund(customer)
    plan = make_plan(auth_api, home, guests=40)
    est = auth_api.post(f"{CUST}/estimate", {"planId": plan["id"], "packageId": str(pkg.id), "addonIds": [str(addon.id)]}, format="json").json()
    assert est["subtotal"] == "24000.00" and est["total"] == "28320.00"
    assert auth_api.post(f"{CUST}/estimate", {"planId": plan["id"], "packageId": str(pkg.id), "guests": 100}, format="json").status_code == 409
    stale = auth_api.post(f"{CUST}/bookings", {"planId": plan["id"], "packageId": str(pkg.id), "expectedTotal": "1.00", "idempotencyKey": "k1"}, format="json")
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "price_changed"
    r = book(auth_api, plan["id"], packageId=str(pkg.id), addonIds=[str(addon.id)])
    assert r.status_code == 201
    # The provider takes 1 event a day: the same date is now unavailable to anyone else.
    other = APIClient()
    other.force_authenticate(other_customer)
    oh = Address.objects.create(customer=other_customer.customer_profile, recipient_name="Ravi", phone="+91 90000 11111", line1="2 Road", city="Bengaluru",
                                postal_code="560038", latitude=HOME[0], longitude=HOME[1])
    plan2 = make_plan(other, oh, guests=40)
    fund(other_customer)
    est2 = other.post(f"{CUST}/estimate", {"planId": plan2["id"], "packageId": str(pkg.id)}, format="json").json()
    assert not est2["bookable"] and "booked" in est2["problem"]
    assert all(m["name"] != "Confetti Crew" for m in other.get(f"{CUST}/plans/{plan2['id']}/matches").json()["results"])


def test_cancellation_refunds_pay_later_and_ownership(auth_api, registry, customer, home, other_customer):
    p, _ = provider(registry, "Confetti Crew")
    p.free_cancellation_days, p.late_cancellation_fee_percent = 10, 25
    p.save()
    pkg = package(p, registry, price="10000")
    fund(customer, "50000")
    plan = make_plan(auth_api, home, days=5)
    b = book(auth_api, plan["id"], packageId=str(pkg.id)).json()
    assert b["cancellation"]["allowed"] and b["cancellation"]["refund"] == "8850.00"  # 25% of 11,800 kept inside 10 days
    other = APIClient()
    other.force_authenticate(other_customer)
    assert other.get(f"{CUST}/bookings/{b['id']}").status_code == 404
    assert other.post(f"{CUST}/bookings/{b['id']}/cancel", {"reason": "x y"}, format="json").status_code == 404
    assert other.get(f"{CUST}/plans/{plan['id']}").status_code == 404
    r = auth_api.post(f"{CUST}/bookings/{b['id']}/cancel", {"reason": "Plans changed"}, format="json").json()
    assert r["status"] == "cancelled" and r["paymentStatus"] == "partly_refunded" and r["refunded"] == "8850.00"
    from apps.wallet.services import balance

    assert balance(customer.customer_profile) == D("50000") - D("11800") + D("8850")
    # Pay later: held, then paid; unpaid ones close 2 days before the event.
    plan2 = make_plan(auth_api, home, days=30)
    held = book(auth_api, plan2["id"], packageId=str(pkg.id), paymentMethod="pay_later").json()
    assert held["status"] == "payment_pending" and held["canPay"]
    assert auth_api.post(f"{CUST}/bookings/{held['id']}/pay", {}, format="json").json()["status"] == "confirmed"
    plan3 = make_plan(auth_api, home, days=25)
    held3 = book(auth_api, plan3["id"], packageId=str(pkg.id), paymentMethod="pay_later").json()
    EventBooking.objects.filter(pk=held3["id"]).update(event_date=engine.today() + timedelta(days=1))
    assert auth_api.get(f"{CUST}/bookings/{held3['id']}").json()["status"] == "cancelled"
    plan4 = make_plan(auth_api, home, days=2)
    assert book(auth_api, plan4["id"], packageId=str(pkg.id), paymentMethod="pay_later").status_code == 400  # too close for pay later


def test_plan_validation_favourites_support_and_partner_scoping(auth_api, registry, customer, home, other_customer):
    p, pc = provider(registry, "Confetti Crew")
    pkg = package(p, registry)
    bad = auth_api.post(f"{CUST}/plans", {"eventType": "birthday", "date": (engine.today() - timedelta(days=1)).isoformat(), "addressId": str(home.id),
                                          "guests": 10, "services": ["decoration"]}, format="json")
    assert bad.status_code == 400
    other_addr = Address.objects.create(customer=other_customer.customer_profile, recipient_name="R", phone="+91 9", line1="x", city="B", postal_code="1")
    assert auth_api.post(f"{CUST}/plans", {"eventType": "birthday", "dateFlexible": True, "addressId": str(other_addr.id), "guests": 10,
                                           "services": ["decoration"]}, format="json").status_code == 400
    flex = auth_api.post(f"{CUST}/plans", {"eventType": "birthday", "dateFlexible": True, "dateNote": "Any Saturday", "addressId": str(home.id),
                                           "guests": 10, "services": ["decoration"]}, format="json").json()
    assert flex["date"] is None
    est = auth_api.post(f"{CUST}/estimate", {"planId": flex["id"], "packageId": str(pkg.id)}, format="json").json()
    assert not est["bookable"] and "fixed date" in est["problem"]
    # Favourites use the shared wishlist.
    assert auth_api.post("/api/v1/customer/wishlist", {"eventProviderId": str(p.id)}, format="json").status_code == 201
    assert auth_api.post("/api/v1/customer/wishlist", {"eventPackageId": str(pkg.id)}, format="json").status_code == 201
    fav = auth_api.get(f"{CUST}/favorites").json()
    assert fav["providers"][0]["name"] == "Confetti Crew" and fav["packages"][0]["name"] == "Birthday Basic"
    kinds = {i["kind"] for i in auth_api.get("/api/v1/customer/wishlist").json()}
    assert {"event_provider", "event_package"} <= kinds
    # A provider only sees and acts on enquiries sent to them.
    q, qc = provider(registry, "Someone Else")
    plan = make_plan(auth_api, home)
    auth_api.post(f"{CUST}/plans/{plan['id']}/enquiries", {"providerIds": [str(p.id)]}, format="json")
    e = auth_api.get(f"{CUST}/plans/{plan['id']}").json()["enquiries"][0]
    assert qc.get(f"/api/v1/partner/eventhub/enquiries/{e['id']}").status_code == 404
    assert pc.get(f"/api/v1/partner/eventhub/enquiries/{e['id']}").json()["plan"]["requirements"] == "Superhero theme"
    # Support tickets can reference the customer's own event booking only.
    fund(customer)
    plan_b = make_plan(auth_api, home, days=40)
    b = book(auth_api, plan_b["id"], packageId=str(pkg.id)).json()
    t = auth_api.post("/api/v1/customer/support/tickets", {"category": "other", "subject": "Decor", "message": "Question", "eventBookingId": b["id"]}, format="json")
    assert t.status_code == 201 and t.json()["eventBookingNumber"] == b["number"]


def test_buddy_plans_from_real_data_and_buzz_links_to_teams(auth_api, registry, home):
    p, _ = provider(registry, "Confetti Crew")
    package(p, registry)
    r = auth_api.post("/api/v1/customer/assistant/messages", {"messages": [{"role": "user", "content": "Plan a birthday party for 30 people next Saturday"}]},
                      format="json").json()
    text = r["message"]["content"]
    assert "Confetti Crew" in text and "don’t send requests, book or pay" in text
    paths = [a["path"] for a in r["actions"]]
    assert any(x.startswith("/events/plan?") and "guests=30" in x and "type=birthday" in x for x in paths)
    assert not EventBooking.objects.exists() and not EventPlan.objects.exists()
    from apps.buzz.services import build_feed

    items = [i for i in build_feed(30) if i["kind"] == "event_team"]
    assert items and items[0]["action"]["path"] == f"/events/providers/{p.id}" and items[0]["media_url"] == ""
