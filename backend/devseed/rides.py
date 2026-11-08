"""DEVELOPMENT MOCK DATA: ride types and rates, ride offers, and verified test drivers (Click Partners) with vehicles."""

from decimal import Decimal as D

from django.db import connection
from django.utils import timezone

from apps.partners.models import Partner, PartnerAddress, PartnerCategory, PartnerMembership, PartnerProfile, PartnerType
from apps.partners.services import PARTNER_CODE_PREFIX, PARTNER_CODE_SEQUENCE
from apps.rides.models import DriverLocation, RideOffer, RideType
from apps.users.models import User

from . import locality_point

# code, name, description, icon, seats, vehicle types, base, per km, per min, minimum, booking fee, per stop, avg speed
RIDE_TYPES = [
    ("bike", "Bike", "Quickest through traffic", "bike", 1, "bike,ev_bike", "20", "7", "1", "35", "2", "10", 24),
    ("auto", "Auto", "Affordable city travel", "auto", 3, "auto", "30", "12", "1.5", "45", "3", "15", 20),
    ("cab", "Cab", "Comfortable everyday rides", "car", 4, "car", "50", "16", "2", "90", "5", "20", 22),
    ("xl", "XL", "Room for 6 and luggage", "car", 6, "van", "80", "22", "2.5", "150", "5", "25", 20),
]

OFFERS = [
    ("20% off your ride", "Up to ₹60 off on Auto and Cab", "percent", "20", "60", "100", ["auto", "cab"]),
    ("₹25 off bike rides", "On bike rides above ₹80", "flat", "25", None, "80", ["bike"]),
]

# name, phone, vehicle type, model, colour, plate, locality (seeded online near these Bengaluru localities)
DRIVERS = [
    ("Ravi Kumar", "+91 90000 10001", "car", "Maruti Dzire", "White", "KA 01 AB 4521", "Indiranagar"),
    ("Suresh Gowda", "+91 90000 10002", "auto", "Bajaj RE", "Green & yellow", "KA 03 C 7788", "Indiranagar"),
    ("Imran Pasha", "+91 90000 10003", "bike", "Honda Activa", "Grey", "KA 05 HX 1290", "Koramangala"),
    ("Lakshmi Devi", "+91 90000 10004", "car", "Hyundai Aura", "Silver", "KA 51 MN 3310", "Koramangala"),
    ("Arjun Rao", "+91 90000 10005", "auto", "Piaggio Ape", "Green & yellow", "KA 02 D 5521", "Jayanagar"),
    ("Kiran Shetty", "+91 90000 10006", "bike", "TVS Jupiter", "Blue", "KA 04 JK 8812", "HSR Layout"),
    ("Manjunath B", "+91 90000 10007", "van", "Toyota Innova", "White", "KA 53 P 6604", "Whitefield"),
]


def _driver(name, phone, vtype, model, colour, plate, locality, transport, categories):
    email = f"driver.{plate.replace(' ', '').lower()}@click.local"
    user = User.objects.filter(email=email).first() or User.objects.create_user(email, None, full_name=name, phone=phone, phone_verified=True)
    membership = PartnerMembership.objects.filter(user=user, role="owner").select_related("partner").first()
    category = categories["bike-rider" if vtype == "bike" else "auto-driver" if vtype == "auto" else "cab-driver"]
    if membership:
        partner = membership.partner
    else:
        partner = Partner.objects.create(partner_type=transport, category=category, business_name=name)
        PartnerMembership.objects.create(partner=partner, user=user, role="owner")
    if not partner.partner_code:
        with connection.cursor() as cursor:
            cursor.execute("SELECT nextval(%s)", [PARTNER_CODE_SEQUENCE])
            partner.partner_code = f"{PARTNER_CODE_PREFIX}{cursor.fetchone()[0]:06d}"
    partner.status, partner.is_available, partner.profile_completed_at = Partner.Status.VERIFIED, True, partner.profile_completed_at or timezone.now()
    partner.save()
    PartnerProfile.objects.update_or_create(partner=partner, defaults={"contact_name": name, "details": {
        "vehicle_type": vtype, "vehicle_model": model, "vehicle_color": colour, "vehicle_number": plate, "availability": "full_time"}})
    lat, lng = locality_point(locality, plate)
    PartnerAddress.objects.update_or_create(partner=partner, is_primary=True, defaults={
        "line1": f"{locality} base", "city": "Bengaluru", "state": "Karnataka", "postal_code": "560001", "latitude": lat, "longitude": lng,
        "service_area": locality})
    # Online now, as if the Partner App had just reported its location (re-run the seed to refresh).
    DriverLocation.objects.update_or_create(driver=partner, defaults={"lat": lat, "lng": lng, "reported_at": timezone.now()})
    return partner


def seed_rides(log) -> None:
    types = {}
    for pos, (code, name, desc, icon, seats, vtypes, base, km, minute, minimum, fee, stop, speed) in enumerate(RIDE_TYPES):
        types[code], _ = RideType.objects.update_or_create(code=code, defaults=dict(
            name=name, description=desc, icon=icon, seats=seats, vehicle_types=vtypes, base_fare=D(base), per_km=D(km),
            per_minute=D(minute), minimum_fare=D(minimum), booking_fee=D(fee), per_stop=D(stop), average_speed_kmh=speed, position=pos, is_active=True))
    for title, desc, kind, value, cap, min_fare, codes in OFFERS:
        offer, _ = RideOffer.objects.update_or_create(title=title, defaults=dict(
            description=desc, discount_type=kind, discount_value=D(value), max_discount=D(cap) if cap else None, min_fare=D(min_fare), is_active=True))
        offer.ride_types.set([types[c] for c in codes])
    if not PartnerType.objects.filter(slug="transport").exists():
        from apps.partners.catalog import apply_catalog

        apply_catalog(PartnerType, PartnerCategory)  # the same catalogue sync_partner_catalog applies
    transport = PartnerType.objects.get(slug="transport")
    categories = {c.slug: c for c in PartnerCategory.objects.filter(partner_type=transport)}
    for d in DRIVERS:
        _driver(*d, transport=transport, categories=categories)
    log(f"rides: {len(RIDE_TYPES)} ride types, {len(OFFERS)} ride offers, {len(DRIVERS)} verified drivers online (locations refreshed)")
