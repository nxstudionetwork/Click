"""
Parcel job matching. Eligible = a delivery partner (Parcel & Logistics partners and Delivery Riders) who is verified,
switched to available, reported a location in the last 10 minutes, has a vehicle that can carry this vehicle class,
is within range of the pickup and isn't already on a delivery. No partner is ever invented or auto-assigned: a job is
offered and becomes assigned only when a partner accepts it in the Partner App.
"""

from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

from apps.partners.models import Partner
from apps.rides.matching import LOCATION_FRESH_FOR
from apps.rides.models import DriverLocation
from apps.rides.pricing import ROAD_FACTOR, haversine_km

from .models import ACTIVE_STATUSES, ParcelJobOffer, ParcelOrder, ParcelStatus, ParcelVehicle

MATCH_RADIUS_KM = 8.0
MAX_OFFERS = 5
BUSY = [s for s in ACTIVE_STATUSES if s != ParcelStatus.SEARCHING]


def parcel_categories() -> list[str]:
    from apps.partners.catalog import categories_with_workspace

    return categories_with_workspace("parcels")


def vehicle_type_of(partner: Partner) -> str:
    details = getattr(getattr(partner, "profile", None), "details", {}) or {}
    return str(details.get("vehicle_type") or "")


def _candidates():
    cutoff = timezone.now() - LOCATION_FRESH_FOR
    return (DriverLocation.objects.filter(
        reported_at__gte=cutoff, driver__is_available=True,
        driver__status__in=[Partner.Status.VERIFIED, Partner.Status.ACTIVE],
        driver__category__slug__in=parcel_categories(),
    ).select_related("driver", "driver__profile"))


def eligible_partners(vehicle: ParcelVehicle, point: tuple[float, float], exclude=(), radius_km: float = MATCH_RADIUS_KM):
    """[(partner, km)] nearest first."""
    out = []
    for loc in _candidates().exclude(driver_id__in=exclude):
        if vehicle_type_of(loc.driver) not in vehicle.vehicle_type_list:
            continue
        if ParcelOrder.objects.filter(partner=loc.driver, status__in=BUSY).exists():
            continue
        d = haversine_km(point, (float(loc.lat), float(loc.lng)))
        if d <= radius_km:
            out.append((loc.driver, d))
    return sorted(out, key=lambda x: x[1])


def pickup_eta_minutes(vehicle: ParcelVehicle, point: tuple[float, float]) -> int | None:
    found = eligible_partners(vehicle, point)
    if not found:
        return None
    return max(3, round(found[0][1] * ROAD_FACTOR / vehicle.average_speed_kmh * 60))


def offer_parcel(parcel: ParcelOrder) -> int:
    already = list(parcel.job_offers.values_list("partner_id", flat=True))
    found = eligible_partners(parcel.vehicle, (float(parcel.pickup_lat), float(parcel.pickup_lng)), exclude=already)[:MAX_OFFERS]
    for partner, km in found:
        ParcelJobOffer.objects.get_or_create(parcel=parcel, partner=partner, defaults={"distance_km": Decimal(str(round(km, 2)))})
    return len(found)


def refresh_for(partner: Partner) -> int:
    """Offer this partner the open jobs near them that their vehicle can carry (when they come online or open Home)."""
    if not partner.is_available or partner.status not in (Partner.Status.VERIFIED, Partner.Status.ACTIVE):
        return 0
    loc = DriverLocation.objects.filter(driver=partner, reported_at__gte=timezone.now() - LOCATION_FRESH_FOR).first()
    if loc is None or ParcelOrder.objects.filter(partner=partner, status__in=BUSY).exists():
        return 0
    vtype, n = vehicle_type_of(partner), 0
    for p in ParcelOrder.objects.filter(status=ParcelStatus.SEARCHING).select_related("vehicle").exclude(job_offers__partner=partner)[:50]:
        if vtype not in p.vehicle.vehicle_type_list:
            continue
        d = haversine_km((float(p.pickup_lat), float(p.pickup_lng)), (float(loc.lat), float(loc.lng)))
        if d <= MATCH_RADIUS_KM:
            ParcelJobOffer.objects.get_or_create(parcel=p, partner=partner, defaults={"distance_km": Decimal(str(round(d, 2)))})
            n += 1
    return n
