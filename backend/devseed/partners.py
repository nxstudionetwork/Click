"""
DEVELOPMENT MOCK DATA: one verified test Click Partner per Home configuration, so every category's Partner Home can
be reviewed locally ("Login as test partner" in the Partner App, DEBUG only).

Where Click already has the customer service, the partner is linked to a real seeded record (a restaurant, grocery
store and shop through PartnerStore, a cinema through PartnerVenue), so orders and bookings customers make in the
Customer App reach that partner's Home. Hotels, parcel and home services have no customer service yet; those
partners show the honest "not live yet" Home. Nothing here creates orders, bookings or earnings.
"""

from django.db import connection

from apps.bookings.models import Venue
from apps.partners.models import (
    Partner, PartnerAddress, PartnerAvailabilityEvent, PartnerCategory, PartnerMembership, PartnerProfile, PartnerStore,
    PartnerVenue,
)
from apps.partners.services import PARTNER_CODE_PREFIX, PARTNER_CODE_SEQUENCE
from apps.stores.models import Store
from apps.users.models import User

from . import locality_point

TEST_PARTNER_EMAIL_DOMAIN = "@click.local"

# email slug, category, contact, details, locality, link kind, linked slug, status
PARTNERS = [
    ("restaurant", "restaurant", "Meera Nair", {"cuisines": ["continental"], "food_type": "both", "opens_at": "09:00", "closes_at": "23:00"},
     "Indiranagar", "store", "basil-lime-thai-kitchen", Partner.Status.ACTIVE),
    ("grocery", "grocery-store", "Prakash Rao", {"opens_at": "07:00", "closes_at": "22:00", "fulfilment": ["delivery"]},
     "Jayanagar", "store", "freshcart-daily", Partner.Status.ACTIVE),
    ("shop", "retail-store", "Farah Khan", {"opens_at": "10:00", "closes_at": "21:00", "fulfilment": ["delivery", "pickup"]},
     "Koramangala", "store", "stride-sports-co", Partner.Status.ACTIVE),
    ("cinema", "cinema-hall", "Vikram Shetty", {"screens": 4, "seating_capacity": 800, "opens_at": "09:00", "closes_at": "23:59"},
     "Indiranagar", "venue", "click-cineplex-indiranagar", Partner.Status.ACTIVE),
    ("hotel", "hotel", "Anita Desai", {"property_type": "hotel", "capacity": 40}, "Whitefield", None, None, Partner.Status.ACTIVE),
    ("parcel", "parcel-partner", "Rahul Verma", {"services": ["same_day", "express"], "daily_capacity": 40}, "HSR Layout", None, None,
     Partner.Status.ACTIVE),
    ("electrician", "electrician", "Sanjay Patil", {"service_types": ["electrical"], "availability": "all_days", "experience_years": 8},
     "Malleshwaram", None, None, Partner.Status.VERIFICATION_PENDING),
]


def _code() -> str:
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval(%s)", [PARTNER_CODE_SEQUENCE])
        return f"{PARTNER_CODE_PREFIX}{cursor.fetchone()[0]:06d}"


def seed_partners(log) -> None:
    for i, (slug, category_slug, contact, details, locality, link_kind, link_slug, status) in enumerate(PARTNERS):
        category = PartnerCategory.objects.select_related("partner_type").get(slug=category_slug)
        email = f"partner.{slug}{TEST_PARTNER_EMAIL_DOMAIN}"
        user = User.objects.filter(email=email).first() or User.objects.create_user(
            email, None, full_name=contact, phone=f"+1 650 555 01{20 + i:02d}", phone_verified=True)
        membership = PartnerMembership.objects.filter(user=user, role="owner").select_related("partner").first()
        linked = None
        if link_kind == "store":
            linked = Store.objects.filter(slug=link_slug).first()
        elif link_kind == "venue":
            linked = Venue.objects.filter(slug=link_slug).first()
        individual = category_slug in ("electrician", "parcel-partner")
        name = contact if individual else (linked.name if linked else {"hotel": "Lakeview Residency"}.get(slug, f"{contact}"))

        partner = membership.partner if membership else Partner.objects.create(
            partner_type=category.partner_type, category=category, business_name=name)
        if not membership:
            PartnerMembership.objects.create(partner=partner, user=user, role="owner")
        partner.partner_code = partner.partner_code or _code()
        partner.business_name = name
        partner.status = status
        partner.profile_completed_at = partner.profile_completed_at or partner.created_at
        if link_kind == "store" and linked:
            partner.is_available = linked.is_accepting_orders
        partner.save()
        PartnerProfile.objects.update_or_create(partner=partner, defaults={"contact_name": contact, "details": details})
        lat, lng = locality_point(locality, slug)
        PartnerAddress.objects.update_or_create(partner=partner, is_primary=True, defaults={
            "line1": f"{locality} main road", "city": "Bengaluru", "state": "Karnataka", "postal_code": "560038",
            "latitude": lat, "longitude": lng, "service_area": locality})
        if link_kind == "store" and linked:
            PartnerStore.objects.get_or_create(store=linked, defaults={"partner": partner})
        elif link_kind == "venue" and linked:
            PartnerVenue.objects.get_or_create(venue=linked, defaults={"partner": partner})
            if not partner.availability_events.exists():
                partner.is_available = True
                partner.save(update_fields=["is_available", "updated_at"])
        if partner.is_available and not partner.availability_events.exists():
            PartnerAvailabilityEvent.objects.create(partner=partner, is_available=True, note="Development seed")
        log(f"partner {partner.partner_code} · {category.name} · {name}" + (f" -> {link_slug}" if linked else ""))

    # The seeded drivers (devseed/rides.py) are online: start their availability log so online time is measurable.
    for driver in Partner.objects.filter(partner_type__slug="transport", is_available=True, availability_events__isnull=True):
        PartnerAvailabilityEvent.objects.create(partner=driver, is_available=True, note="Development seed")
    from .parcels import seed_parcels

    seed_parcels(log)  # Click. Parcel configuration and delivery riders (after the partner catalogue exists)
    from .professionals import seed_professionals

    seed_professionals(log)  # Click. Services catalog and professionals
    from .eventhub import seed_eventhub

    seed_eventhub(log)  # Click. Events registries, event teams, specialists and venues
    from .hotels import seed_hotels

    seed_hotels(log)  # Click. Hotels destinations, properties, rooms, rates and offers
