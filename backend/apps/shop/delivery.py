"""
Shopping delivery estimates. No courier/logistics provider is connected yet, so the estimate is a published rule,
always shown as a date *range* and labelled an estimate, never an exact promise:

  window = seller's dispatch days + transit days by distance between the seller and the delivery point
           (same metro <= 40 km: 1-2 days; <= 500 km: 2-4 days; farther: 4-7 days)
  without coordinates, the same city counts as 1-3 days and anything else 3-7 days.

The fee is the seller's delivery fee, free above the seller's threshold. Location therefore changes the estimate,
and cash on delivery depends on the seller and the listing.
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.rides.pricing import haversine_km

TRANSIT = [(40, (1, 2)), (500, (2, 4))]
FAR = (4, 7)


def transit_days(store, *, lat=None, lng=None, city: str = "") -> tuple[tuple[int, int], str]:
    if None not in (lat, lng, store.latitude, store.longitude):
        km = haversine_km((float(store.latitude), float(store.longitude)), (float(lat), float(lng)))
        for limit, days in TRANSIT:
            if km <= limit:
                return days, "distance"
        return FAR, "distance"
    if city and store.city and city.strip().lower() == store.city.strip().lower():
        return (1, 3), "same_city"
    return (3, 7), "region"


def estimate(store, *, address=None, lat=None, lng=None, city: str = "", subtotal: Decimal | None = None) -> dict:
    if address is not None:
        lat, lng, city = address.latitude, address.longitude, address.city
    (lo, hi), basis = transit_days(store, lat=lat, lng=lng, city=city)
    today = timezone.localdate()
    start, end = today + timedelta(days=store.dispatch_days + lo), today + timedelta(days=store.dispatch_days + hi)
    fee = store.delivery_fee
    if subtotal is not None and store.free_delivery_above is not None and subtotal >= store.free_delivery_above:
        fee = Decimal("0")
    return {
        "from_date": start.isoformat(), "to_date": end.isoformat(), "basis": basis,
        "fee": f"{fee:.2f}", "free_above": f"{store.free_delivery_above:.2f}" if store.free_delivery_above is not None else None,
        "is_estimate": True,
    }
