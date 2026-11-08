"""
Route estimate and upfront fare. Everything here runs on the server; clients never send prices.

Route: no road-routing provider is connected yet, so distance is the straight-line (haversine) path through
pickup → stops → drop multiplied by ROAD_FACTOR, and duration uses each ride type's city average speed. The API
labels this `estimate_basis = "straight_line"` so the app never presents it as a road route or live traffic. A
routing provider plugs in behind `estimate_route` without changing callers.
"""

import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from .models import RideOffer, RideType

ROAD_FACTOR = 1.3  # typical ratio of city road distance to straight-line distance
STOP_WAIT_MINUTES = 2
MIN_TRIP_KM = 0.3
MAX_TRIP_KM = 60  # intercity isn't offered yet
WHOLE = Decimal("1")


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


@dataclass(frozen=True)
class RouteEstimate:
    distance_km: Decimal
    straight_km: float
    stops: int
    basis: str = "straight_line"


def estimate_route(points: list[tuple[float, float]]) -> RouteEstimate:
    straight = sum(haversine_km(points[i], points[i + 1]) for i in range(len(points) - 1))
    return RouteEstimate(Decimal(str(round(straight * ROAD_FACTOR, 2))), straight, max(0, len(points) - 2))


def duration_minutes(route: RouteEstimate, ride_type: RideType) -> int:
    return max(3, math.ceil(float(route.distance_km) / ride_type.average_speed_kmh * 60) + route.stops * STOP_WAIT_MINUTES)


@dataclass(frozen=True)
class Fare:
    base: Decimal
    distance: Decimal
    time: Decimal
    fees: Decimal
    subtotal: Decimal
    discount: Decimal
    total: Decimal


def _money(v) -> Decimal:
    return Decimal(v).quantize(WHOLE, rounding=ROUND_HALF_UP)


def offer_problem(offer: RideOffer | None, ride_type: RideType, subtotal: Decimal) -> str | None:
    if offer is None:
        return None
    now = timezone.now()
    if not offer.is_active or (offer.starts_at and offer.starts_at > now) or (offer.ends_at and offer.ends_at < now):
        return "This offer has ended."
    if offer.ride_types.exists() and not offer.ride_types.filter(pk=ride_type.pk).exists():
        return f"This offer isn't valid on {ride_type.name}."
    if subtotal < offer.min_fare:
        return f"This offer needs a fare of at least ₹{offer.min_fare:.0f}."
    return None


def compute_fare(ride_type: RideType, route: RouteEstimate, minutes: int, offer: RideOffer | None = None) -> Fare:
    distance = _money(ride_type.per_km * route.distance_km)
    time = _money(ride_type.per_minute * minutes)
    fees = _money(ride_type.booking_fee + ride_type.per_stop * route.stops)
    trip = max(ride_type.base_fare + distance + time, ride_type.minimum_fare)
    subtotal = _money(trip + fees)
    discount = Decimal("0")
    if offer is not None and offer_problem(offer, ride_type, subtotal) is None:
        if offer.discount_type == RideOffer.DiscountType.PERCENT:
            discount = _money(subtotal * offer.discount_value / 100)
            if offer.max_discount is not None:
                discount = min(discount, offer.max_discount)
        else:
            discount = min(offer.discount_value, subtotal)
    return Fare(_money(ride_type.base_fare), distance, time, fees, subtotal, _money(discount), _money(subtotal - discount))


def active_offers():
    now = timezone.now()
    from django.db.models import Q

    return RideOffer.objects.filter(is_active=True).filter(
        Q(starts_at__isnull=True) | Q(starts_at__lte=now), Q(ends_at__isnull=True) | Q(ends_at__gte=now)
    ).prefetch_related("ride_types")
