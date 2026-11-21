"""
Parcel quotes. Everything here runs on the server from configured records; the app never computes a price.

Route: the same estimate Click. Ride uses (no road-routing provider is connected): straight-line distance through
pickup → stops → drop x a road factor, labelled `estimate_basis = "straight_line"`. Times come from the vehicle's city
average speed and, for Express, the real distance of the nearest eligible delivery partner who is online.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from apps.rides.pricing import MAX_TRIP_KM, MIN_TRIP_KM, RouteEstimate, estimate_route, haversine_km

from .models import ParcelCategory, ParcelOrder, ParcelService, ParcelServiceArea, ParcelVehicle

WHOLE = Decimal("1")
STOP_MINUTES = 5
HANDOVER_MINUTES = 5
# Package size presets: max weight (kg) and the box (cm) they stand for. "custom" uses the customer's own numbers.
SIZES = {
    "small": {"label": "Small", "hint": "Fits in a backpack · documents, phone, small box", "max_kg": 5, "dims": (30, 30, 30)},
    "medium": {"label": "Medium", "hint": "Shoebox to carry-on bag", "max_kg": 12, "dims": (45, 45, 45)},
    "large": {"label": "Large", "hint": "Carton or suitcase", "max_kg": 25, "dims": (70, 60, 60)},
    "custom": {"label": "Custom", "hint": "Enter weight and size", "max_kg": None, "dims": None},
}


def local_tz() -> ZoneInfo:
    return ZoneInfo(getattr(settings, "CLICK_LOCAL_TIMEZONE", "Asia/Kolkata"))


def now_local(now=None) -> datetime:
    return timezone.localtime(now or timezone.now(), local_tz())


def money(v) -> Decimal:
    return Decimal(v).quantize(WHOLE, rounding=ROUND_HALF_UP)


def area_for(point) -> ParcelServiceArea | None:
    for a in ParcelServiceArea.objects.filter(is_active=True):
        if haversine_km((float(a.center_lat), float(a.center_lng)), point) <= float(a.radius_km):
            return a
    return None


@dataclass
class Package:
    category: ParcelCategory | None
    size: str
    weight_kg: Decimal
    dims: tuple[int, int, int] | None
    declared_value: Decimal | None

    def box(self) -> tuple[int, int, int] | None:
        if self.dims:
            return self.dims
        preset = SIZES.get(self.size) or {}
        return preset.get("dims")


def package_problem(p: Package) -> str | None:
    if p.category is None:
        return "Tell us what's inside."
    if not p.category.is_allowed:
        return f"{p.category.label} can't be sent with Click. Parcel."
    if p.size not in SIZES:
        return "Choose a package size."
    if p.weight_kg is None or p.weight_kg <= 0:
        return "Enter an approximate weight."
    preset = SIZES[p.size]
    if preset["max_kg"] is not None and p.weight_kg > preset["max_kg"]:
        return f"A {preset['label'].lower()} package is up to {preset['max_kg']} kg. Choose a bigger size or Custom."
    if p.size == "custom" and not p.dims:
        return "Enter the package's length, width and height for a custom size."
    if p.category.requires_value and not p.declared_value:
        return f"Enter the value of the {p.category.label.lower()} (needed for this kind of item)."
    return None


def vehicle_problem(v: ParcelVehicle, p: Package) -> str | None:
    if p.weight_kg > v.max_weight_kg:
        return f"Over {v.max_weight_kg:.0f} kg"
    box = p.box()
    # The box fits if, side by side from smallest to largest, every side fits the vehicle's limit.
    if box and any(a > b for a, b in zip(sorted(box), sorted((v.max_length_cm, v.max_width_cm, v.max_height_cm)))):
        return "Too big for this vehicle"
    return None


@dataclass(frozen=True)
class Fare:
    base: Decimal
    distance: Decimal
    service: Decimal
    stops: Decimal
    tax: Decimal
    discount: Decimal
    total: Decimal

    def as_dict(self) -> dict:
        return {k: f"{getattr(self, k):.2f}" for k in ("base", "distance", "service", "stops", "tax", "discount", "total")}


def compute_fare(v: ParcelVehicle, s: ParcelService, route: RouteEstimate) -> Fare:
    distance = money(v.per_km * route.distance_km)
    trip = max(v.base_fare + distance, v.minimum_fare)
    base = trip - distance  # minimum fare shows as part of the base
    service = money(trip * (s.price_multiplier - 1))
    stops = money(v.per_stop * route.stops)
    tax = (Decimal(trip + service + stops) * settings.CLICK_SERVICE_FEE_TAX_RATE).quantize(Decimal("0.01"))
    total = (trip + service + stops + tax).quantize(Decimal("0.01"))
    return Fare(base, distance, service, stops, tax, Decimal("0"), total)


def minutes_for(route: RouteEstimate, v: ParcelVehicle) -> int:
    return max(5, math.ceil(float(route.distance_km) / v.average_speed_kmh * 60) + route.stops * STOP_MINUTES + HANDOVER_MINUTES)


def _fmt(dt: datetime, ref: datetime) -> str:
    t = dt.strftime("%I:%M %p").lstrip("0")
    if dt.date() == ref.date():
        return f"today, {t}"
    if dt.date() == (ref + timedelta(days=1)).date():
        return f"tomorrow, {t}"
    return dt.strftime("%a %d %b, ") + t


def schedule_slots(s: ParcelService, now=None, limit: int = 60) -> list[dict]:
    """Pickup slots (30 min) inside the service's hours, from the lead time up to `schedule_days` ahead."""
    if s.code != ParcelService.Kind.SCHEDULED or not s.schedule_days:
        return []
    tz, now = local_tz(), now_local(now)
    earliest = now + timedelta(minutes=s.schedule_lead_minutes)
    out = []
    for d in range(s.schedule_days + 1):
        day = (now + timedelta(days=d)).date()
        t = datetime.combine(day, time(s.open_hour), tz)
        end = datetime.combine(day, time(min(s.close_hour, 23)), tz)
        while t < end:
            if t >= earliest:
                out.append({"start": t.isoformat(), "label": _fmt(t, now)})
            t += timedelta(minutes=30)
    return out[:limit]


def service_window(s: ParcelService, route: RouteEstimate, v_minutes: int, now=None, scheduled_for: datetime | None = None,
                   pickup_eta: int | None = None) -> dict:
    """Whether a service can take this booking now and what it promises (only what it can actually keep)."""
    tz, now = local_tz(), now_local(now)
    if route.distance_km > s.max_distance_km:
        return {"available": False, "reason": f"Up to {s.max_distance_km:.0f} km for {s.name}"}
    open_now = s.open_hour <= now.hour < s.close_hour
    if s.code == ParcelService.Kind.EXPRESS:
        if not open_now:
            return {"available": False, "reason": f"Express runs {s.open_hour}:00–{s.close_hour}:00"}
        if pickup_eta is None:
            return {"available": False, "reason": "No delivery partner is free nearby right now"}
        total = pickup_eta + v_minutes
        return {"available": True, "pickup_at": now, "deliver_by": now + timedelta(minutes=total),
                "label": f"Pickup in about {pickup_eta} min · delivered about {total} min from now (estimated)"}
    if s.code == ParcelService.Kind.SAME_DAY:
        cutoff = s.order_cutoff_hour or s.close_hour
        if now.hour >= cutoff:
            return {"available": False, "reason": f"Book same-day before {cutoff}:00"}
        by = datetime.combine(now.date(), time(s.delivered_by_hour or s.close_hour), tz)
        return {"available": True, "pickup_at": max(now, datetime.combine(now.date(), time(s.open_hour), tz)), "deliver_by": by,
                "label": f"Delivered by {_fmt(by, now)}"}
    if s.code == ParcelService.Kind.STANDARD:
        by = datetime.combine((now + timedelta(days=s.deliver_days)).date(), time(s.delivered_by_hour or s.close_hour), tz)
        if by <= now + timedelta(minutes=v_minutes):
            by += timedelta(days=1)
        return {"available": True, "pickup_at": now if open_now else None, "deliver_by": by, "label": f"Delivered by {_fmt(by, now)}"}
    # scheduled
    slots = schedule_slots(s, now)
    if not slots:
        return {"available": False, "reason": "No pickup times available"}
    if scheduled_for is None:
        return {"available": True, "needs_time": True, "label": "Choose a pickup time", "slots": slots}
    chosen = timezone.localtime(scheduled_for, tz)
    if not any(datetime.fromisoformat(x["start"]) == chosen for x in slots):
        return {"available": False, "reason": "That pickup time isn't available. Choose another.", "slots": slots}
    by = chosen + timedelta(minutes=v_minutes + 30)
    return {"available": True, "pickup_at": chosen, "deliver_by": by, "slots": slots,
            "label": f"Pickup {_fmt(chosen, now)} · delivered by about {_fmt(by, now)} (estimated)"}


def points_problem(points: list[tuple[float, float]]) -> str | None:
    for p in points:
        if area_for(p) is None:
            return "Click. Parcel doesn't deliver to this location yet."
    route = estimate_route(points)
    if route.straight_km < MIN_TRIP_KM:
        return "Pickup and drop are too close together."
    if float(route.distance_km) > MAX_TRIP_KM:
        return f"Parcel deliveries are up to {MAX_TRIP_KM} km within the city."
    return None


def mode_payment_methods(mode: str, s: ParcelService) -> list[str]:
    methods = ["wallet"]
    if mode == ParcelOrder.Mode.SEND and s.cash_allowed:
        methods.append("cash")
    return methods
