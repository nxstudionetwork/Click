"""
Matching engine boundary. Finds eligible drivers for a ride and offers it to them; a driver accepting through the
Partner API assigns the ride. There is no random assignment and no invented driver: eligibility comes from partner
records (transport partner, verified/active, online, vehicle type serving the ride type) and a fresh location.

Later: service areas, acceptance timeouts with re-offer, batching, driver scoring — all behind these functions.
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.partners.models import Partner

from .models import DriverLocation, RideType
from .pricing import ROAD_FACTOR, haversine_km

MATCH_RADIUS_KM = 6.0
LOCATION_FRESH_FOR = timedelta(minutes=10)  # a driver who hasn't reported for this long isn't offered rides
LIVE_FOR = timedelta(seconds=45)  # the app calls a driver's position "live" only within this window
MAX_OFFERS = 5


def eligible_drivers(ride_type: RideType, point: tuple[float, float], radius_km: float = MATCH_RADIUS_KM, exclude=()):
    """[(partner, distance_km)] nearest first: online, verified, right vehicle, recently located, within radius."""
    from apps.partners.catalog import categories_with_workspace

    cutoff = timezone.now() - LOCATION_FRESH_FOR
    locations = (
        DriverLocation.objects.filter(
            reported_at__gte=cutoff,
            driver__is_available=True,
            driver__status__in=[Partner.Status.VERIFIED, Partner.Status.ACTIVE],
            driver__partner_type__slug="transport",
            # Only categories that drive Click. Ride trips (not delivery riders or fleet operators).
            driver__category__slug__in=categories_with_workspace("rides"),
        )
        .exclude(driver_id__in=exclude)
        .select_related("driver", "driver__profile")
    )
    out = []
    for loc in locations:
        details = getattr(getattr(loc.driver, "profile", None), "details", {}) or {}
        if details.get("vehicle_type") not in ride_type.vehicle_type_list:
            continue
        if loc.driver.rides.filter(status__in=["driver_assigned", "driver_arrived", "in_progress"]).exists():
            continue  # already on a trip
        d = haversine_km(point, (float(loc.lat), float(loc.lng)))
        if d <= radius_km:
            out.append((loc.driver, d))
    return sorted(out, key=lambda x: x[1])


def pickup_eta_minutes(ride_type: RideType, point: tuple[float, float]) -> int | None:
    """Minutes for the nearest eligible driver to reach the pickup, or None when no driver is available."""
    drivers = eligible_drivers(ride_type, point)
    if not drivers:
        return None
    km = drivers[0][1] * ROAD_FACTOR
    return max(1, round(km / ride_type.average_speed_kmh * 60))


def offer_ride(ride) -> int:
    """Offer the ride to the nearest eligible drivers it hasn't been offered to yet. Returns how many were offered it."""
    from .models import RideDriverOffer

    already = list(ride.driver_offers.values_list("driver_id", flat=True))
    drivers = eligible_drivers(ride.ride_type, (float(ride.pickup_lat), float(ride.pickup_lng)), exclude=already)[:MAX_OFFERS]
    for partner, km in drivers:
        RideDriverOffer.objects.get_or_create(ride=ride, driver=partner, defaults={"distance_km": Decimal(str(round(km, 2)))})
    return len(drivers)
