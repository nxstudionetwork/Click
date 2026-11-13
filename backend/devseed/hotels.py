"""
DEVELOPMENT MOCK DATA: Click. Hotels (all properties fictional).

* Destinations are real cities with real public landmarks (airports, stations, centres, beaches) and their public
  coordinates, so distances are computed, not typed. Properties, rooms, rates, offers and policies are invented for
  development and live only in this module; customers never see a "mock" label, and production uses partner data.
* No photos: properties show a designed placeholder until the property uploads its own (no generated or borrowed images).
* Star ratings are set only where the fictional property "has" a classification; guest ratings are never typed in —
  `seed_hotel_history` creates completed stays with reviews from dev viewers and the scores are recomputed from them.
"""

from __future__ import annotations

import uuid
from datetime import time, timedelta
from decimal import Decimal as D

from django.utils import timezone

from apps.partners.models import Partner, PartnerAddress, PartnerAvailabilityEvent, PartnerCategory, PartnerMembership, PartnerProfile, PartnerVerification
from apps.users.models import User

from .partners import TEST_PARTNER_EMAIL_DOMAIN
from .professionals import _code

DESTS = [
    # slug, name, region, lat, lng, tagline, tags, synonyms, landmarks [(name, kind, lat, lng)]
    ("hyderabad", "Hyderabad", "Telangana", "17.3850", "78.4867", "Biryani, history and HITEC City", ["city", "business", "weekend"], ["hyd", "secunderabad"],
     [("Charminar", "centre", "17.3616", "78.4747"), ("Rajiv Gandhi International Airport", "airport", "17.2403", "78.4294"),
      ("Secunderabad Railway Station", "station", "17.4337", "78.5016"), ("HITEC City", "business", "17.4474", "78.3762"), ("Hussain Sagar", "landmark", "17.4239", "78.4738")]),
    ("bengaluru", "Bengaluru", "Karnataka", "12.9716", "77.5946", "Gardens, cafés and tech parks", ["city", "business"], ["bangalore", "blr"],
     [("MG Road", "centre", "12.9756", "77.6066"), ("Kempegowda International Airport", "airport", "13.1986", "77.7066"),
      ("KSR Bengaluru City Junction", "station", "12.9781", "77.5695"), ("Whitefield ITPL", "business", "12.9855", "77.7366")]),
    ("goa", "Goa", "Goa", "15.4909", "73.8278", "Beaches, shacks and sunsets", ["beach", "weekend"], ["north goa", "panaji", "panjim"],
     [("Panaji", "centre", "15.4909", "73.8278"), ("Goa International Airport (Dabolim)", "airport", "15.3808", "73.8314"),
      ("Calangute Beach", "beach", "15.5439", "73.7553"), ("Baga Beach", "beach", "15.5553", "73.7517"), ("Madgaon Junction", "station", "15.2668", "73.9696")]),
    ("mysuru", "Mysuru", "Karnataka", "12.2958", "76.6394", "Palaces and silk, a short drive from Bengaluru", ["weekend", "city"], ["mysore"],
     [("Mysore Palace", "centre", "12.3052", "76.6552"), ("Mysuru Junction", "station", "12.3164", "76.6458"), ("Chamundi Hill", "landmark", "12.2724", "76.6702")]),
    ("coorg", "Coorg", "Karnataka", "12.4244", "75.7382", "Coffee estates and misty hills", ["nature", "weekend"], ["kodagu", "madikeri"],
     [("Madikeri town", "centre", "12.4244", "75.7382"), ("Abbey Falls", "landmark", "12.4570", "75.7206")]),
    ("vijayawada", "Vijayawada", "Andhra Pradesh", "16.5062", "80.6480", "On the Krishna, by Kanaka Durga hill", ["city", "business"], ["bezawada"],
     [("Benz Circle", "centre", "16.4999", "80.6560"), ("Vijayawada Junction", "station", "16.5181", "80.6200"),
      ("Vijayawada Airport", "airport", "16.5304", "80.7968"), ("Kanaka Durga Temple", "landmark", "16.5155", "80.6047")]),
]

AMENITIES = [("wifi", "Free Wi-Fi", "device", "both"), ("parking", "Parking", "car", "property"), ("pool", "Swimming pool", "drop", "property"),
             ("ac", "Air conditioning", "sparkle", "both"), ("restaurant", "Restaurant", "food", "property"), ("room-service", "Room service", "bell", "property"),
             ("gym", "Gym", "dumbbell", "property"), ("spa", "Spa", "beauty", "property"), ("breakfast", "Breakfast available", "coffee", "property"),
             ("pets", "Pet friendly", "paw", "property"), ("family", "Family friendly", "team", "property"), ("accessible", "Accessible rooms", "user", "property"),
             ("airport-transfer", "Airport transfer", "car", "property"), ("laundry", "Laundry", "shirt", "property"), ("workspace", "Work desk", "briefcase", "room"),
             ("tv", "TV", "play", "room"), ("kitchen", "Kitchenette", "food", "room"), ("bathtub", "Bathtub", "drop", "room"), ("balcony", "Balcony", "leaf", "room")]

# name, destination, area, type, stars, lat, lng, base nightly, amenities, good_for, tagline, pay-at-property allowed, accent, free-cancel days
PROPS = [
    ("The Nizam Courtyard", "hyderabad", "Banjara Hills", "hotel", 5, "17.4126", "78.4482", 9800, ["wifi", "parking", "pool", "ac", "restaurant", "room-service", "gym", "spa", "breakfast", "airport-transfer", "laundry", "accessible"], ["couple", "business", "family"], "Courtyards, fountains and a rooftop grill", False, "#d4b26a", 3),
    ("Orbit Business Hotel", "hyderabad", "HITEC City", "hotel", 4, "17.4485", "78.3790", 5400, ["wifi", "parking", "ac", "restaurant", "room-service", "gym", "breakfast", "laundry"], ["business", "solo"], "Walk to the tech parks", True, "#7dd3fc", 2),
    ("Charminar Heritage Stay", "hyderabad", "Old City", "guest_house", None, "17.3600", "78.4720", 2200, ["wifi", "ac", "breakfast", "family"], ["family", "couple", "solo"], "A restored haveli near the bazaars", True, "#f59e0b", 1),
    ("Hussain Sagar Residency", "hyderabad", "Tank Bund", "hotel", 3, "17.4210", "78.4800", 3600, ["wifi", "parking", "ac", "restaurant", "breakfast", "family"], ["family", "couple"], "Rooms facing Hussain Sagar", True, "#38bdf8", 2),
    ("Airport Transit Inn", "hyderabad", "Shamshabad", "hotel", 3, "17.2520", "78.4300", 3100, ["wifi", "parking", "ac", "restaurant", "airport-transfer", "room-service"], ["business", "solo"], "Ten minutes from the terminal", False, "#94a3b8", 1),
    ("Gachibowli Suites", "hyderabad", "Gachibowli", "apartment", None, "17.4401", "78.3489", 4200, ["wifi", "parking", "ac", "gym", "laundry", "family"], ["family", "business"], "Serviced apartments with kitchens", True, "#a3e635", 3),
    ("Cubbon Grand", "bengaluru", "MG Road", "hotel", 5, "12.9740", "77.6100", 10500, ["wifi", "parking", "pool", "ac", "restaurant", "room-service", "gym", "spa", "breakfast", "accessible"], ["business", "couple"], "Five-star calm on MG Road", False, "#e2c48a", 3),
    ("Indiranagar Boutique", "bengaluru", "Indiranagar", "hotel", 3, "12.9719", "77.6412", 4300, ["wifi", "ac", "restaurant", "breakfast", "pets"], ["couple", "solo"], "Twelve rooms above the café streets", True, "#f472b6", 2),
    ("Lakeview Residency", "bengaluru", "Whitefield", "hotel", 4, "12.9860", "77.7310", 5600, ["wifi", "parking", "ac", "restaurant", "gym", "breakfast", "laundry"], ["business"], "Steps from ITPL", True, "#60a5fa", 2),
    ("Backpacker Nest BLR", "bengaluru", "Koramangala", "hostel", None, "12.9352", "77.6245", 900, ["wifi", "ac", "laundry"], ["solo"], "Dorms, pods and a rooftop common room", True, "#22d3ee", 1),
    ("Sea Breeze Resort", "goa", "Calangute", "resort", 4, "15.5420", "73.7600", 7400, ["wifi", "parking", "pool", "ac", "restaurant", "room-service", "spa", "breakfast", "family", "airport-transfer"], ["family", "couple"], "Two pools, five minutes to the sand", False, "#2dd4bf", 7),
    ("Baga Shack Rooms", "goa", "Baga", "guest_house", None, "15.5560", "73.7540", 2600, ["wifi", "ac", "breakfast"], ["couple", "solo"], "Simple rooms, steps from Baga beach", True, "#fb923c", 1),
    ("Fontainhas Villa", "goa", "Panaji", "villa", None, "15.4980", "73.8330", 12800, ["wifi", "parking", "pool", "ac", "kitchen", "family", "pets"], ["family"], "A Portuguese-era villa with a private pool", False, "#fbbf24", 14),
    ("Candolim Palms", "goa", "Candolim", "resort", 3, "15.5180", "73.7620", 4800, ["wifi", "parking", "pool", "ac", "restaurant", "breakfast", "family"], ["family", "couple"], "Palm gardens and a quiet pool", True, "#4ade80", 3),
    ("Palace Road Inn", "mysuru", "Palace Road", "hotel", 3, "12.3040", "76.6500", 3200, ["wifi", "parking", "ac", "restaurant", "breakfast", "family"], ["family", "couple"], "A walk from the palace lights", True, "#f59e0b", 2),
    ("Chamundi Heritage", "mysuru", "Nazarbad", "hotel", 4, "12.3010", "76.6620", 6200, ["wifi", "parking", "pool", "ac", "restaurant", "spa", "breakfast"], ["couple", "family"], "A 1920s mansion with a lawn", False, "#e879f9", 5),
    ("Misty Estate Homestay", "coorg", "Madikeri", "homestay", None, "12.4300", "75.7300", 3400, ["wifi", "parking", "breakfast", "family", "pets"], ["family", "couple"], "Home-cooked Kodava meals on a coffee estate", True, "#86efac", 3),
    ("Abbey Falls Retreat", "coorg", "Abbey Falls Road", "resort", 4, "12.4520", "75.7250", 8200, ["wifi", "parking", "pool", "restaurant", "spa", "breakfast", "family"], ["couple", "family"], "Cottages above the falls", False, "#34d399", 7),
    ("Krishna Riverside Hotel", "vijayawada", "Benz Circle", "hotel", 4, "16.5010", "80.6550", 4600, ["wifi", "parking", "pool", "ac", "restaurant", "gym", "breakfast", "room-service"], ["business", "family"], "A pool deck by Benz Circle", True, "#38bdf8", 2),
    ("Station Square Lodge", "vijayawada", "Governorpet", "hotel", 2, "16.5160", "80.6250", 1500, ["wifi", "ac", "restaurant"], ["solo", "business"], "Clean, quick, five minutes from the station", True, "#a1a1aa", 1),
]

ROOMS = {
    "hotel": [("Superior Double", "double", "1 Queen bed", 2, 1, 3, 24, "", 1.0, 8, ["ac", "tv", "workspace"]),
              ("Deluxe King", "double", "1 King bed", 2, 1, 3, 30, "City view", 1.3, 6, ["ac", "tv", "workspace", "bathtub"]),
              ("Family Room", "family", "1 King + 1 Single bed", 3, 2, 5, 38, "", 1.6, 3, ["ac", "tv"])],
    "resort": [("Garden Room", "double", "1 King bed", 2, 1, 3, 32, "Garden view", 1.0, 8, ["ac", "tv", "balcony"]),
               ("Pool Villa", "suite", "1 King bed", 2, 2, 4, 55, "Pool access", 1.8, 3, ["ac", "tv", "balcony", "bathtub"]),
               ("Family Cottage", "family", "2 Queen beds", 4, 2, 6, 60, "", 1.7, 3, ["ac", "tv", "balcony"])],
    "guest_house": [("Standard Double", "double", "1 Double bed", 2, 1, 3, 18, "", 1.0, 5, ["ac"]),
                    ("Twin Room", "twin", "2 Single beds", 2, 0, 2, 18, "", 1.0, 3, ["ac"])],
    "apartment": [("One-bedroom Apartment", "double", "1 Queen bed + sofa bed", 2, 2, 4, 50, "", 1.0, 6, ["ac", "kitchen", "tv", "workspace"]),
                  ("Two-bedroom Apartment", "family", "2 Queen beds", 4, 2, 6, 85, "", 1.6, 4, ["ac", "kitchen", "tv", "workspace"])],
    "villa": [("Whole Villa (3 bedrooms)", "family", "3 King beds", 6, 3, 9, 240, "Private pool", 1.0, 1, ["ac", "kitchen", "tv", "balcony"])],
    "hostel": [("Bed in 6-bed Dorm", "dorm", "1 Bunk bed", 1, 0, 1, None, "", 1.0, 18, ["ac"]),
               ("Private Double", "double", "1 Double bed", 2, 0, 2, 14, "", 2.4, 4, ["ac"])],
    "homestay": [("Estate Room", "double", "1 Queen bed", 2, 1, 3, 26, "Coffee estate view", 1.0, 4, ["balcony"]),
                 ("Family Suite", "family", "1 King + 2 Single beds", 4, 2, 5, 40, "", 1.5, 2, ["balcony"])],
}

REVIEW_TEXT = ["Spotless room and very helpful staff at the front desk.", "Great location, breakfast had plenty of choice.", "", "Good value for the price; the room was a bit small.",
               "Check-in was quick and the bed was really comfortable.", "Noisy at night because of the road, otherwise fine.", "Lovely pool and calm gardens."]


def _r(x: float) -> D:
    return D(str(int(round(x / 50.0) * 50)))


def seed_hotels(log) -> None:
    from apps.hotels.models import Amenity, Destination, HotelOffer, HotelProperty, Landmark, RatePlan, RoomInventory, RoomType
    from apps.hotels.engine import today
    from apps.partners.catalog import apply_catalog
    from apps.partners.models import PartnerType

    apply_catalog(PartnerType, PartnerCategory)  # hotel categories use the Hotels workspace
    am = {}
    for pos, (slug, name, icon, scope) in enumerate(AMENITIES):
        am[slug], _ = Amenity.objects.update_or_create(slug=slug, defaults=dict(name=name, icon=icon, scope=scope, position=pos, filterable=scope != "room"))
    dests = {}
    for pos, (slug, name, region, lat, lng, tagline, tags, syn, lms) in enumerate(DESTS):
        d, _ = Destination.objects.update_or_create(slug=slug, defaults=dict(name=name, region=region, latitude=D(lat), longitude=D(lng), tagline=tagline,
                                                                             tags=tags, synonyms=syn, position=pos, is_active=True))
        dests[slug] = d
        for lname, kind, la, lo in lms:
            Landmark.objects.update_or_create(destination=d, name=lname, defaults=dict(kind=kind, latitude=D(la), longitude=D(lo)))
    now = timezone.now()
    d0 = today()
    cat = {t: PartnerCategory.objects.select_related("partner_type").get(slug={"resort": "resort", "homestay": "homestay", "apartment": "serviced-apartment",
                                                                                 "villa": "serviced-apartment"}.get(t, "hotel"))
           for t in ("hotel", "resort", "homestay", "apartment", "villa", "guest_house", "hostel")}
    made = 0
    for i, (name, dslug, area, ptype, stars, lat, lng, base, amen, good, tagline, pay_at, accent, free_days) in enumerate(PROPS):
        # The dev Partner App hotel login (devseed.partners, "Lakeview Residency") owns a real listing; the Hyderabad
        # property keeps the account it was first seeded with.
        email = {"Lakeview Residency": f"partner.hotel{TEST_PARTNER_EMAIL_DOMAIN}",
                 "Hussain Sagar Residency": "hotel.lakeview.residency@click.local"}.get(name) or f"hotel.{name.lower().replace(' ', '.')}@click.local"
        user = User.objects.filter(email=email).first() or User.objects.create_user(email, None, full_name=name, phone_verified=False)
        m = PartnerMembership.objects.filter(user=user, role="owner").select_related("partner").first()
        c = cat[ptype]
        partner = m.partner if m else Partner.objects.create(partner_type=c.partner_type, category=c, business_name=name)
        if not m:
            PartnerMembership.objects.create(partner=partner, user=user, role="owner")
        partner.partner_code = partner.partner_code or _code()
        partner.business_name = name
        partner.status, partner.is_available, partner.profile_completed_at = Partner.Status.ACTIVE, True, partner.profile_completed_at or now
        partner.save()
        PartnerProfile.objects.get_or_create(partner=partner, defaults={"contact_name": f"{name} front desk", "details": {}})
        PartnerAddress.objects.update_or_create(partner=partner, is_primary=True, defaults={
            "line1": f"{area}", "city": dests[dslug].name, "state": dests[dslug].region, "postal_code": "500001", "latitude": D(lat), "longitude": D(lng)})
        if not PartnerVerification.objects.filter(partner=partner, status="approved").exists():
            PartnerVerification.objects.create(partner=partner, status="approved", submitted_at=now - timedelta(days=120), reviewed_at=now - timedelta(days=110),
                                               reviewer_note="Development seed: property documents checked")
        if not partner.availability_events.exists():
            PartnerAvailabilityEvent.objects.create(partner=partner, is_available=True, note="Development seed")
        p, _ = HotelProperty.objects.update_or_create(partner=partner, defaults=dict(
            destination=dests[dslug], property_type=ptype, star_rating=stars, tagline=tagline,
            description=f"{tagline}. {name} is in {area}, {dests[dslug].name}.", highlights=[tagline] + (["Free cancellation on most rooms"] if free_days >= 2 else []),
            address=f"{area}, {dests[dslug].name}, {dests[dslug].region}", area=area, latitude=D(lat), longitude=D(lng),
            check_in_time=time(14 if ptype != "hostel" else 13, 0), check_out_time=time(11 if ptype != "villa" else 10, 0),
            languages=["English", "Hindi"] + (["Telugu"] if dslug in ("hyderabad", "vijayawada") else ["Kannada"] if dslug in ("bengaluru", "mysuru", "coorg") else ["Konkani"]),
            policies=["Government-issued photo ID required at check-in", "Unmarried couples welcome" if ptype != "homestay" else "Quiet hours after 10 PM",
                      "No smoking in rooms"] + (["Pets allowed on request"] if "pets" in amen else []),
            accessibility="Step-free entrance and an accessible room" if "accessible" in amen else "",
            parking="Free on-site parking" if "parking" in amen else "", good_for=good, accent=accent, is_listed=True,
            nearby=[]))
        p.amenities.set([am[a] for a in amen])
        keep = []
        for pos, (rname, rclass, beds, ma, mc, mo, size, view, mult, units, ramen) in enumerate(ROOMS[ptype]):
            room, _ = RoomType.objects.update_or_create(property=p, name=rname, defaults=dict(
                room_class=rclass, beds=beds, max_adults=ma, max_children=mc, max_occupancy=mo, size_sqm=size, view=view, total_units=units,
                description=f"{beds}{f', {size} m²' if size else ''}{f', {view.lower()}' if view else ''}.", position=pos, is_active=True))
            room.amenities.set([am[a] for a in ramen + ["wifi"]])
            keep.append(room.pk)
            price = _r(base * mult)
            weekend = _r(base * mult * (1.25 if dslug in ("goa", "coorg", "mysuru") else 1.0)) if dslug in ("goa", "coorg", "mysuru") else None
            rates = [("Room only", "room_only", True, free_days, 100, "either" if pay_at else "pay_now", price, weekend)]
            if "breakfast" in amen and rclass != "dorm":
                rates.append(("Breakfast included", "breakfast", True, free_days + 1, 100, "either" if pay_at else "pay_now", price + _r(350 * mo / 2), weekend + _r(350 * mo / 2) if weekend else None))
            if stars and stars >= 3:
                rates.append(("Saver (non-refundable)", "room_only", False, None, 100, "pay_now", _r(float(price) * 0.88), _r(float(weekend) * 0.88) if weekend else None))
            names = []
            for rn, meal, refundable, fdays, fee, pay, pr, wk in rates:
                RatePlan.objects.update_or_create(room_type=room, name=rn, defaults=dict(
                    meal_plan=meal, refundable=refundable, free_cancel_days=fdays if refundable else None, cancel_fee_percent=fee, payment=pay, price=pr,
                    weekend_price=wk, min_nights=2 if ptype == "villa" else 1, is_active=True))
                names.append(rn)
            room.rates.exclude(name__in=names).update(is_active=False)
        p.rooms.exclude(pk__in=keep).update(is_active=False)
        # A few nights are already sold out so availability differs between properties.
        if i % 4 == 0:
            r0 = p.rooms.filter(is_active=True).first()
            for k in (6, 7):
                RoomInventory.objects.update_or_create(room_type=r0, date=d0 + timedelta(days=k), defaults={"closed": True})
        made += 1
    end = now + timedelta(days=120)
    for title, kind, pct, cap, min_n, ahead_min, ahead_max, code, prop in [
        ("Early booking: 10% off", "early", 10, None, 1, 21, None, "", None),
        ("Last-minute deal: 8% off", "last_minute", 8, None, 1, None, 3, "", "Orbit Business Hotel"),
        ("Weekend by the sea: 12% off", "weekend", 12, None, 2, None, None, "", "Sea Breeze Resort"),
        ("Stay 3, save 15%", "long_stay", 15, None, 3, None, None, "", "Gachibowli Suites"),
        ("Coupon STAYCLICK: 15% off, up to ₹1,500", "coupon", 15, D("1500"), 2, None, None, "STAYCLICK", None),
    ]:
        HotelOffer.objects.update_or_create(title=title, defaults=dict(
            kind=kind, percent=pct, max_discount=cap, min_nights=min_n, min_days_ahead=ahead_min, max_days_ahead=ahead_max, code=code,
            property=HotelProperty.objects.filter(partner__business_name=prop).first() if prop else None, starts_at=now - timedelta(days=10), ends_at=end, is_active=True))
    log(f"hotels: {len(DESTS)} destinations with real landmarks, {made} fictional properties, "
        f"{RoomType.objects.filter(is_active=True).count()} room types, {RatePlan.objects.filter(is_active=True).count()} rates, 5 offers (no photos)")


NS = uuid.UUID("5f0c2a71-1b9e-4a6b-9d2e-0b70e1d0c0de")


def _stay(customer, prop, days_ago, nights, key, review=None, status="completed", future=False):
    from apps.hotels import engine
    from apps.hotels.models import HotelBooking, HotelReview, StatusEvent
    from apps.payments.models import Payment

    if HotelBooking.objects.filter(customer=customer, idempotency_key=str(key)).exists():
        return 0
    rate = prop.rooms.filter(is_active=True).first().rates.filter(is_active=True, refundable=True).first()
    ci = engine.today() + timedelta(days=days_ago) if future else engine.today() - timedelta(days=days_ago)
    co = ci + timedelta(days=nights)
    nightly = [(d, rate.weekend_price if rate.weekend_price and d.weekday() in (4, 5) else rate.price) for d in engine.nights_of(ci, co)]
    room_total = sum(p for _, p in nightly)
    tax = engine.money(sum(p * engine.gst_rate(p) for _, p in nightly))
    until = engine.free_cancel_until(rate, prop, ci)
    b = HotelBooking.objects.create(
        customer=customer, property=prop, room_type=rate.room_type, rate_plan=rate, check_in=ci, check_out=co, nights=nights, rooms=1, adults=2,
        guest_name=customer.user.full_name or "Guest", guest_phone="+91 90000 00000", status=status, payment_status="paid", payment_mode="pay_now",
        room_name=rate.room_type.name, rate_name=rate.name, meal_plan=rate.meal_plan, refundable=True, free_cancel_until=until,
        cancel_fee_percent=rate.cancel_fee_percent, nightly=[{"date": d.isoformat(), "price": f"{p:.2f}"} for d, p in nightly], room_total=room_total,
        tax=tax, total=room_total + tax, idempotency_key=str(key), confirmed_at=timezone.now() - timedelta(days=days_ago + 10 if not future else 2),
        checked_in_at=timezone.now() - timedelta(days=days_ago) if status == "completed" else None)
    Payment.objects.create(hotel_booking=b, method="wallet", amount=b.total, currency=b.currency, status=Payment.Status.CAPTURED)
    for st in (["pending_payment", "confirmed", "completed"] if status == "completed" else ["pending_payment", "confirmed"]):
        StatusEvent.objects.create(booking=b, to=st, note="Development seed")
    if review:
        score, text, trav = review
        HotelReview.objects.create(booking=b, customer=customer, property=prop, overall=score, cleanliness=min(10, score + (days_ago % 2)),
                                   location=min(10, score + 1), comfort=score, facilities=max(1, score - 1), staff=min(10, score + (days_ago % 3 == 0)),
                                   value=max(1, score - (days_ago % 2)), title="", comment=text, traveller=trav)
    return 1


def seed_hotel_history(profile, log) -> None:
    from apps.customers.models import Address
    from apps.hotels import booking
    from apps.hotels.models import HotelProperty
    from apps.wishlists.models import WishlistItem

    from . import locality_point
    from .showtime import VIEWERS, _viewer

    props = list(HotelProperty.objects.select_related("partner").order_by("partner__business_name"))
    if not props:
        return
    viewers = [_viewer(n, loc) for n, loc in VIEWERS]
    for v, (n, loc) in zip(viewers, VIEWERS):
        if not v.addresses.exists():
            lat, lng = locality_point(loc, f"viewer-{n}")
            Address.objects.create(customer=v, label="home", recipient_name=n, phone="+91 90000 00000", line1=f"{n}’s home (dev)", line2=loc,
                                   city="Bengaluru", postal_code="560001", latitude=lat, longitude=lng)
    made = 0
    travellers = ["couple", "family", "business", "solo", "friends"]
    for k, p in enumerate(props):
        for i in range(2 + (k * 3) % 7):  # 2..8 past stays each
            v = viewers[(k + i) % len(viewers)]
            score = max(4, min(10, [9, 8, 10, 7, 9, 8, 6, 9][(k + i) % 8] + [-2, 0, 1, -1, 0, 1, -3, 0][k % 8]))  # properties differ
            review = (score, REVIEW_TEXT[(k + i) % len(REVIEW_TEXT)], travellers[(k + i) % len(travellers)]) if i % 4 != 3 else None
            made += _stay(v, p, 12 + i * 17 + k % 6, 1 + (i % 3), uuid.uuid5(NS, f"{p.partner.business_name}-{i}"), review)
    by = {p.partner.business_name: p for p in props}
    if (h := by.get("Orbit Business Hotel")):
        made += _stay(profile, h, 35, 2, uuid.uuid5(NS, "test-past"), (9, "Easy walk to the office and a quick breakfast.", "business"))
    if (g := by.get("Sea Breeze Resort")):
        made += _stay(profile, g, 30, 3, uuid.uuid5(NS, "test-upcoming"), status="confirmed", future=True)
    if (n := by.get("The Nizam Courtyard")):
        WishlistItem.objects.get_or_create(customer=profile, hotel=n)
    for p in props:
        booking.recompute(p)
    log(f"hotel history: {made} stays (completed with verified reviews; 1 past and 1 upcoming for the test customer, 1 saved hotel); ratings recomputed")
