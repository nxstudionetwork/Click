"""
DEVELOPMENT MOCK DATA: Click. Parcel configuration and delivery partners (all people fictional).

The service area, vehicles (capacities and rates), delivery services (windows and rules), contents categories and
package rules are configuration a Click. operations team would set in the admin / Business OS; the values here are
for development only and are never shown as production availability. Delivery partners are seeded online with a
fresh location, as if their Partner App had just reported it (re-run the seed to refresh).
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal as D

from django.db import connection
from django.utils import timezone

from apps.partners.models import Partner, PartnerAddress, PartnerAvailabilityEvent, PartnerCategory, PartnerMembership, PartnerProfile
from apps.partners.services import PARTNER_CODE_PREFIX, PARTNER_CODE_SEQUENCE
from apps.rides.models import DriverLocation
from apps.users.models import User

from . import locality_point

# code, name, description, icon, partner vehicle types, max kg, L, W, H (cm), base, per km, minimum, per stop, km/h
VEHICLES = [
    ("bike", "Bike", "Documents and small parcels", "bike", "bike,ev_bike", "8", 40, 35, 35, "30", "8", "45", "15", 22),
    ("scooter", "Scooter", "Small to medium parcels", "bike", "scooter", "15", 50, 45, 45, "35", "9", "55", "15", 20),
    ("auto", "3-Wheeler", "Medium goods and cartons", "auto", "auto,e_cargo", "120", 120, 100, 90, "60", "14", "110", "25", 16),
    ("mini_truck", "Mini Truck", "Large or heavy goods", "warehouse", "mini_truck,tempo", "750", 240, 150, 150, "250", "25", "400", "60", 15),
]
# code, name, description, vehicles, multiplier, max km, open, close, cutoff, by hour, deliver days, schedule days, stops, max stops, cash, cancel fee
SERVICES = [
    ("express", "Express", "Fastest: picked up by the nearest free partner", ["bike", "scooter"], "1.35", "20", 8, 22, None, None, 0, 0, True, 2, True, "25"),
    ("same_day", "Same Day", "Picked up today, delivered by evening", ["bike", "scooter", "auto", "mini_truck"], "1.10", "30", 8, 20, 16, 21, 0, 0, True, 3, True, "25"),
    ("standard", "Standard", "Lower cost, delivered by tomorrow", ["bike", "scooter", "auto"], "0.90", "30", 8, 20, None, 20, 1, 0, False, 0, True, "0"),
    ("scheduled", "Scheduled", "Choose a pickup time up to 3 days ahead", ["bike", "scooter", "auto", "mini_truck"], "1.00", "30", 8, 20, None, None, 0, 3, True, 3, True, "25"),
]
# code, label, icon, requires value, allowed, note
CATEGORIES = [
    ("document", "Document", "receipt", False, True, ""),
    ("small_parcel", "Small parcel", "parcel", False, True, ""),
    ("clothing", "Clothing", "shirt", False, True, ""),
    ("electronics", "Electronics", "device", True, True, "Declare the value; pack in the original box or padding."),
    ("food", "Food (non-perishable)", "food", False, True, "Sealed, non-perishable food only."),
    ("gift", "Gift", "gift", False, True, ""),
    ("household", "Household item", "home", False, True, ""),
    ("business", "Business item", "briefcase", False, True, ""),
    ("other", "Other", "parcel", False, True, "Describe it in the notes."),
    ("hazardous", "Flammable or hazardous", "alert", False, False, "Gas cylinders, fuel, chemicals, batteries sold loose."),
    ("valuables", "Cash, jewellery or bullion", "alert", False, False, ""),
    ("alcohol_drugs", "Alcohol, tobacco or drugs", "alert", False, False, ""),
    ("animals", "Live animals or plants", "alert", False, False, ""),
]
RULES = [
    ("rule", "Pack the item securely and seal it before the partner arrives."),
    ("rule", "The package must fit the selected vehicle's size and weight limits."),
    ("rule", "Declare the contents correctly; partners may decline a package that doesn't match."),
    ("rule", "Share the pickup PIN only when you hand over, and the delivery PIN only with the recipient."),
    ("prohibited", "Flammable, explosive or hazardous items"),
    ("prohibited", "Cash, jewellery, bullion or other valuables"),
    ("prohibited", "Alcohol, tobacco, drugs or prescription-only medicines"),
    ("prohibited", "Weapons, live animals or anything illegal to carry"),
]
# name, phone, vehicle type, model, plate, locality
RIDERS = [
    ("Naveen S", "+91 90000 20001", "bike", "Hero Splendor", "KA 01 EP 2201", "Indiranagar"),
    ("Farhan Ali", "+91 90000 20002", "scooter", "TVS Ntorq", "KA 03 EQ 4410", "Koramangala"),
    ("Deepa M", "+91 90000 20003", "scooter", "Honda Dio", "KA 05 ER 8823", "HSR Layout"),
    ("Mahesh Kumar", "+91 90000 20004", "auto", "Piaggio Ape Xtra", "KA 02 F 6650", "Jayanagar"),
    ("Venkatesh R", "+91 90000 20005", "mini_truck", "Tata Ace Gold", "KA 51 G 1144", "Bellandur"),
]


def _code() -> str:
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval(%s)", [PARTNER_CODE_SEQUENCE])
        return f"{PARTNER_CODE_PREFIX}{cursor.fetchone()[0]:06d}"


def _rider(name, phone, vtype, model, plate, locality, category):
    email = f"rider.{plate.replace(' ', '').lower()}@click.local"
    user = User.objects.filter(email=email).first() or User.objects.create_user(email, None, full_name=name, phone=phone, phone_verified=True)
    membership = PartnerMembership.objects.filter(user=user, role="owner").select_related("partner").first()
    partner = membership.partner if membership else Partner.objects.create(partner_type=category.partner_type, category=category, business_name=name)
    if not membership:
        PartnerMembership.objects.create(partner=partner, user=user, role="owner")
    partner.partner_code = partner.partner_code or _code()
    partner.status, partner.is_available = Partner.Status.VERIFIED, True
    partner.profile_completed_at = partner.profile_completed_at or timezone.now()
    partner.save()
    PartnerProfile.objects.update_or_create(partner=partner, defaults={"contact_name": name, "details": {
        "vehicle_type": vtype, "vehicle_model": model, "vehicle_number": plate, "availability": "full_time"}})
    lat, lng = locality_point(locality, plate)
    PartnerAddress.objects.update_or_create(partner=partner, is_primary=True, defaults={
        "line1": f"{locality} hub", "city": "Bengaluru", "state": "Karnataka", "postal_code": "560001", "latitude": lat, "longitude": lng,
        "service_area": locality})
    DriverLocation.objects.update_or_create(driver=partner, defaults={"lat": lat, "lng": lng, "reported_at": timezone.now()})
    if not partner.availability_events.exists():
        PartnerAvailabilityEvent.objects.create(partner=partner, is_available=True, note="Development seed")
    return partner


def seed_parcels(log) -> None:
    from apps.parcels.models import ParcelCategory, ParcelRule, ParcelService, ParcelServiceArea, ParcelVehicle
    from apps.partners.catalog import apply_catalog
    from apps.partners.models import PartnerType

    apply_catalog(PartnerType, PartnerCategory)  # Parcel & Logistics / Delivery Rider homes use the parcels workspace

    ParcelServiceArea.objects.update_or_create(name="Bengaluru", defaults=dict(
        city="Bengaluru", center_lat=D("12.971600"), center_lng=D("77.594600"), radius_km=D("25"), is_active=True))
    vehicles = {}
    for pos, (code, name, desc, icon, vtypes, kg, ln, wd, ht, base, km, minimum, stop, speed) in enumerate(VEHICLES):
        vehicles[code], _ = ParcelVehicle.objects.update_or_create(code=code, defaults=dict(
            name=name, description=desc, icon=icon, partner_vehicle_types=vtypes, max_weight_kg=D(kg), max_length_cm=ln, max_width_cm=wd,
            max_height_cm=ht, base_fare=D(base), per_km=D(km), minimum_fare=D(minimum), per_stop=D(stop), average_speed_kmh=speed,
            is_active=True, position=pos))
    for pos, (code, name, desc, vs, mult, max_km, opens, closes, cutoff, by, days, sched, stops, max_stops, cash, fee) in enumerate(SERVICES):
        s, _ = ParcelService.objects.update_or_create(code=code, defaults=dict(
            name=name, description=desc, price_multiplier=D(mult), max_distance_km=D(max_km), open_hour=opens, close_hour=closes,
            order_cutoff_hour=cutoff, delivered_by_hour=by, deliver_days=days, schedule_days=sched, allow_stops=stops, max_stops=max_stops,
            cash_allowed=cash, cancellation_fee=D(fee), is_active=True, position=pos))
        s.vehicles.set([vehicles[v] for v in vs])
    for pos, (code, label, icon, value, allowed, note) in enumerate(CATEGORIES):
        ParcelCategory.objects.update_or_create(code=code, defaults=dict(label=label, icon=icon, requires_value=value,
                                                                         is_allowed=allowed, note=note, position=pos))
    for pos, (kind, text) in enumerate(RULES):
        ParcelRule.objects.update_or_create(text=text, defaults=dict(kind=kind, position=pos, is_active=True))

    riders = PartnerCategory.objects.select_related("partner_type").get(slug="delivery-rider")
    for r in RIDERS:
        _rider(*r, category=riders)
    # The dev Parcel Partner (devseed/partners.py) delivers by bike from HSR Layout.
    pp = Partner.objects.filter(category__slug="parcel-partner", memberships__user__email__startswith="partner.parcel").first()
    if pp:
        prof = pp.profile
        prof.details = {**(prof.details or {}), "vehicle_type": "bike", "vehicle_number": "KA 05 PP 3030"}
        prof.save(update_fields=["details", "updated_at"])
        lat, lng = locality_point("HSR Layout", "parcel-partner")
        DriverLocation.objects.update_or_create(driver=pp, defaults={"lat": lat, "lng": lng, "reported_at": timezone.now()})
        if pp.status in (Partner.Status.VERIFIED, Partner.Status.ACTIVE) and not pp.is_available:
            pp.is_available = True
            pp.save(update_fields=["is_available", "updated_at"])
    log(f"parcels: 1 service area, {len(VEHICLES)} vehicles, {len(SERVICES)} services, {len(CATEGORIES)} content types, "
        f"{len(RIDERS)} delivery riders online (locations refreshed)")


# --- the test customer's parcel history (real lifecycle events, PIN proofs and payments) -----------------------------

NS = uuid.UUID("5d2b7c3e-0a4e-4f1b-8f55-3a1c0c0de777")


def seed_parcel_history(profile, log) -> None:
    from apps.parcels.models import (
        ParcelCategory, ParcelOrder, ParcelProof, ParcelService, ParcelStatus as S, ParcelStatusEvent, ParcelVehicle, SavedRecipient,
    )
    from apps.payments.models import Payment
    from apps.rides.pricing import estimate_route
    from apps.parcels import pricing

    if ParcelOrder.objects.filter(customer=profile).exists():
        return
    home = profile.addresses.filter(is_default=True).first() or profile.addresses.first()
    work = profile.addresses.filter(label="work").first() or home
    other = profile.addresses.filter(label="other").first() or home
    rider = Partner.objects.filter(memberships__user__email="rider.ka03eq4410@click.local").first()
    rec, _ = SavedRecipient.objects.update_or_create(customer=profile, phone="+91 90000 30001", label="Asha (Mum)", defaults=dict(
        name="Asha Test", address=f"{other.line1}, {other.line2}", lat=other.latitude, lng=other.longitude, times_used=2,
        last_used_at=timezone.now() - timedelta(days=3)))
    SavedRecipient.objects.update_or_create(customer=profile, phone="+91 90000 30002", label="Office reception", defaults=dict(
        name="Front desk", address=f"{work.line1}, {work.line2}", lat=work.latitude, lng=work.longitude, times_used=1,
        last_used_at=timezone.now() - timedelta(days=9)))
    # (key, service, vehicle, from, to, category, size, kg, payment, final status, days ago)
    rows = [
        ("delivered-1", "same_day", "scooter", home, other, "gift", "medium", "3.5", "wallet", S.DELIVERED, 9),
        ("delivered-2", "express", "bike", home, work, "document", "small", "0.5", "cash", S.DELIVERED, 3),
        ("cancelled", "standard", "bike", work, other, "clothing", "small", "1.2", "wallet", S.CANCELLED, 6),
        ("failed", "same_day", "auto", home, other, "household", "large", "18", "wallet", S.FAILED, 12),
        ("active", "express", "scooter", home, other, "electronics", "small", "1.0", "wallet", S.IN_TRANSIT, 0),
    ]
    paths = {S.DELIVERED: [S.SEARCHING, S.ASSIGNED, S.AT_PICKUP, S.PICKED_UP, S.IN_TRANSIT, S.ARRIVING, S.DELIVERED],
             S.CANCELLED: [S.SEARCHING, S.CANCELLED], S.FAILED: [S.SEARCHING, S.ASSIGNED, S.AT_PICKUP, S.PICKED_UP, S.IN_TRANSIT, S.FAILED],
             S.IN_TRANSIT: [S.SEARCHING, S.ASSIGNED, S.AT_PICKUP, S.PICKED_UP, S.IN_TRANSIT]}
    made = 0
    for key, svc, veh, a, b, cat, size, kg, pay, final, days in rows:
        service, vehicle = ParcelService.objects.get(code=svc), ParcelVehicle.objects.get(code=veh)
        route = estimate_route([(float(a.latitude), float(a.longitude)), (float(b.latitude), float(b.longitude))])
        fare = pricing.compute_fare(vehicle, service, route)
        at = timezone.now() - timedelta(days=days, minutes=40 if days == 0 else 0)
        to_rec = b == other
        p = ParcelOrder.objects.create(
            customer=profile, mode="send", service=service, vehicle=vehicle, status=final,
            pickup_label=a.label.title(), pickup_address=f"{a.line1}, {a.line2}", pickup_lat=a.latitude, pickup_lng=a.longitude,
            pickup_name=profile.user.full_name, pickup_phone="+91 00000 00001",
            drop_label=rec.label if to_rec else b.label.title(), drop_address=f"{b.line1}, {b.line2}", drop_lat=b.latitude, drop_lng=b.longitude,
            drop_name=rec.name if to_rec else "Front desk", drop_phone=rec.phone if to_rec else "+91 90000 30002",
            category=ParcelCategory.objects.get(code=cat), size=size, weight_kg=D(kg),
            declared_value=D("4500") if cat == "electronics" else None, contents_declared_at=at,
            distance_km=route.distance_km, duration_minutes=pricing.minutes_for(route, vehicle), fare_base=fare.base, fare_distance=fare.distance,
            fare_service=fare.service, fare_stops=fare.stops, tax=fare.tax, total=fare.total, payment_method=pay,
            deliver_by=at + timedelta(hours=3), partner=rider if final != S.CANCELLED else None,
            assigned_at=at + timedelta(minutes=4) if final != S.CANCELLED else None,
            picked_up_at=at + timedelta(minutes=20) if final in (S.DELIVERED, S.FAILED, S.IN_TRANSIT) else None,
            delivered_at=at + timedelta(minutes=55) if final == S.DELIVERED else None,
            cancelled_at=at + timedelta(minutes=2) if final == S.CANCELLED else None,
            cancel_reason="Plans changed" if final == S.CANCELLED else "",
            failure_reason="Recipient unavailable; parcel kept at the hub" if final == S.FAILED else "",
            idempotency_key=uuid.uuid5(NS, key))
        ParcelOrder.objects.filter(pk=p.pk).update(created_at=at)
        prev = ""
        for i, st in enumerate(paths[final]):
            ev = ParcelStatusEvent.objects.create(parcel=p, from_status=prev, to_status=st, note="Development seed")
            ParcelStatusEvent.objects.filter(pk=ev.pk).update(created_at=at + timedelta(minutes=4 * i + (16 if i >= 3 else 0)))
            prev = st
        if final in (S.DELIVERED, S.FAILED, S.IN_TRANSIT):
            ParcelProof.objects.create(parcel=p, kind="pickup", method="pin", partner=rider)
        if final == S.DELIVERED:
            ParcelProof.objects.create(parcel=p, kind="delivery", method="pin", partner=rider)
        status = {"wallet": Payment.Status.REFUNDED if final == S.CANCELLED else Payment.Status.CAPTURED,
                  "cash": Payment.Status.CAPTURED}[pay]
        Payment.objects.create(parcel=p, method=pay, amount=p.total, currency=p.currency, status=status)
        made += 1
    if rider:  # the active delivery's partner is on it (so they aren't offered other jobs) and online
        DriverLocation.objects.update_or_create(driver=rider, defaults={"lat": home.latitude, "lng": home.longitude, "reported_at": timezone.now()})
    log(f"parcel history: {made} parcels (delivered, cash, cancelled, failed, in transit), 2 saved recipients")
