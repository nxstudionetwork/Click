"""
Store status, delivery options, fees, ETAs and slots. Everything a customer sees about "when" and "how much" for a
grocery delivery is computed here from the vendor's own configuration (GroceryStoreSettings, StoreHours), the
customer's saved location and the store's current workload. Nothing is a live rider ETA: the app labels these as
estimates, and a store without coordinates or a customer address without a map pin never gets a distance claim.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_CEILING, Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from apps.orders.models import OrderStatus
from apps.stores.models import Store

from .models import GroceryOrderDetails, GroceryStoreSettings

CLOSING_SOON_MINUTES = 30
ACTIVE_STATES = [OrderStatus.PLACED, OrderStatus.CONFIRMED, OrderStatus.PREPARING]
MAX_SLOTS = 16


def local_tz() -> ZoneInfo:
    return ZoneInfo(getattr(settings, "CLICK_LOCAL_TIMEZONE", "Asia/Kolkata"))


def now_local(now=None) -> datetime:
    return timezone.localtime(now or timezone.now(), local_tz())


def config(store: Store) -> GroceryStoreSettings:
    """The vendor's settings, or defaults (unsaved) for a grocery store that hasn't configured delivery yet."""
    try:
        return store.grocery
    except GroceryStoreSettings.DoesNotExist:
        return GroceryStoreSettings(store=store)


def _hours(store: Store):
    cached = getattr(store, "_prefetched_objects_cache", {}).get("hours")
    return list(cached) if cached is not None else list(store.hours.all())


def _time_label(dt: datetime, ref: datetime) -> str:
    t = dt.strftime("%I:%M %p").lstrip("0")
    if dt.date() == ref.date():
        return t
    if dt.date() == (ref + timedelta(days=1)).date():
        return f"tomorrow {t}"
    return f"{dt.strftime('%a')} {t}"


def windows(store: Store, start: datetime, days: int):
    """Opening windows (local datetimes) from the start of `start`'s day for `days` days."""
    tz = local_tz()
    hours = _hours(store)
    out = []
    for d in range(days + 1):
        day = (start + timedelta(days=d)).date()
        for h in hours:
            if h.weekday == day.weekday():
                out.append((datetime.combine(day, h.opens_at, tz), datetime.combine(day, h.closes_at, tz)))
    return sorted(out)


def store_status(store: Store, now=None) -> dict:
    """open | closing_soon | closed | unavailable, with the times that explain it."""
    now = now_local(now)
    if store.status != Store.Status.ACTIVE or not store.is_accepting_orders:
        return {"state": "unavailable", "label": "Temporarily unavailable", "closes_at": None, "opens_at": None,
                "detail": "This store isn't taking orders right now."}
    if not _hours(store):
        return {"state": "open", "label": "Open", "closes_at": None, "opens_at": None, "detail": ""}
    wins = windows(store, now - timedelta(days=1), 8)
    current = next(((o, c) for o, c in wins if o <= now < c), None)
    if current:
        closes = current[1]
        soon = closes - now <= timedelta(minutes=CLOSING_SOON_MINUTES)
        return {"state": "closing_soon" if soon else "open", "label": "Closing soon" if soon else "Open",
                "closes_at": closes.isoformat(), "opens_at": None, "detail": f"Closes {_time_label(closes, now)}"}
    nxt = next((o for o, _ in wins if o > now), None)
    return {"state": "closed", "label": "Closed", "closes_at": None, "opens_at": nxt.isoformat() if nxt else None,
            "detail": f"Opens {_time_label(nxt, now)}" if nxt else "Opening hours not set"}


def distance_km(store: Store, point) -> float | None:
    """Great-circle distance, only when both the store and the customer's point have coordinates."""
    if not point or store.latitude is None or store.longitude is None or point[0] is None or point[1] is None:
        return None
    lat1, lng1, lat2, lng2 = map(math.radians, (float(store.latitude), float(store.longitude), float(point[0]), float(point[1])))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return round(2 * 6371.0 * math.asin(math.sqrt(a)), 2)


def address_point(address):
    if address is None or address.latitude is None or address.longitude is None:
        return None
    return float(address.latitude), float(address.longitude)


def load(store: Store) -> int:
    cached = getattr(store, "_active_orders", None)
    if cached is not None:
        return cached
    store._active_orders = store.orders.filter(status__in=ACTIVE_STATES).count()
    return store._active_orders


def _round5(minutes: float) -> int:
    return int(math.ceil(minutes / 5) * 5)


def eta_minutes(store: Store, cfg: GroceryStoreSettings, dist: float | None) -> tuple[int, int]:
    """Prep + travel at the vendor's configured pace + a queue allowance when the store is busy."""
    travel = float(cfg.minutes_per_km) * (dist if dist is not None else float(cfg.delivery_radius_km) / 2)
    busy = max(load(store) - cfg.max_active_orders, 0)
    low = _round5(cfg.prep_minutes + travel + min(busy * 3, 30))
    return max(low, 10), max(low, 10) + 10


def delivery_fee(store: Store, cfg: GroceryStoreSettings, dist: float | None, subtotal: Decimal, mode: str) -> Decimal:
    base = store.delivery_fee
    if store.free_delivery_above is not None and subtotal >= store.free_delivery_above:
        base = Decimal("0")
    extra_km = max(Decimal(str(dist)) - cfg.base_km, Decimal("0")) if dist is not None else Decimal("0")
    fee = base + (extra_km * cfg.per_km_fee).quantize(Decimal("1"), rounding=ROUND_CEILING)
    if mode == GroceryOrderDetails.Mode.FAST:
        fee += cfg.fast_surcharge
    return fee.quantize(Decimal("0.01"))


@dataclass
class Option:
    mode: str
    label: str
    available: bool
    reason: str = ""
    fee: Decimal | None = None
    eta_min: int | None = None
    eta_max: int | None = None
    summary: str = ""
    slots: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"mode": self.mode, "label": self.label, "available": self.available, "reason": self.reason,
                "fee": f"{self.fee:.2f}" if self.fee is not None else None, "eta_min": self.eta_min, "eta_max": self.eta_max,
                "summary": self.summary, "slots": self.slots}


def booked(store: Store, starts) -> dict:
    rows = (GroceryOrderDetails.objects.filter(order__store=store, slot_start__in=starts)
            .exclude(order__status=OrderStatus.CANCELLED).values_list("slot_start", flat=True))
    out: dict = {}
    for s in rows:
        out[s] = out.get(s, 0) + 1
    return out


def slots(store: Store, cfg: GroceryStoreSettings, now=None) -> list[dict]:
    """Real delivery slots: inside opening hours, after the lead time, with capacity left."""
    if not cfg.scheduled_enabled or not _hours(store):
        return []
    now = now_local(now)
    earliest = now + timedelta(minutes=cfg.slot_lead_minutes)
    step = timedelta(minutes=cfg.slot_minutes)
    candidates = []
    for opens, closes in windows(store, now, cfg.slot_days):
        start = opens
        while start + step <= closes:
            if start >= earliest:
                candidates.append((start, start + step))
            start += step
    candidates = candidates[: MAX_SLOTS * 2]
    taken = booked(store, [s for s, _ in candidates])
    out = []
    for s, e in candidates:
        left = cfg.slot_capacity - taken.get(s, 0)
        if left <= 0:
            continue
        day = "Today" if s.date() == now.date() else "Tomorrow" if s.date() == (now + timedelta(days=1)).date() else s.strftime("%a %d %b")
        out.append({"start": s.isoformat(), "end": e.isoformat(), "day": day,
                    "label": f"{s.strftime('%I:%M %p').lstrip('0')} – {e.strftime('%I:%M %p').lstrip('0')}", "remaining": left})
        if len(out) >= MAX_SLOTS:
            break
    return out


def options(store: Store, point, subtotal: Decimal = Decimal("0"), now=None, with_slots: bool = True) -> dict:
    """Every delivery mode for this store and location, each available or with the reason it isn't."""
    cfg = config(store)
    now_l = now_local(now)
    status = store_status(store, now)
    dist = distance_km(store, point)
    eta = eta_minutes(store, cfg, dist)
    out = []
    blocked = ""
    if status["state"] == "unavailable":
        blocked = status["detail"]
    elif dist is not None and dist > float(cfg.delivery_radius_km):
        blocked = f"Outside this store's {cfg.delivery_radius_km:.0f} km delivery area"
    open_now = status["state"] in ("open", "closing_soon")
    packs_in_time = True
    if status.get("closes_at"):
        packs_in_time = now_l + timedelta(minutes=cfg.prep_minutes) < datetime.fromisoformat(status["closes_at"])

    fast = Option("fast", "Fast delivery", False)
    if not cfg.fast_enabled:
        fast.reason = "Not offered by this store"
    elif blocked:
        fast.reason = blocked
    elif not open_now or not packs_in_time:
        fast.reason = f"Store closed · {status['detail']}" if status["state"] == "closed" else "Store is about to close"
    elif dist is None:
        fast.reason = "Add a map pin to your address to check fast delivery"
    elif dist > float(cfg.fast_radius_km):
        fast.reason = f"Only within {cfg.fast_radius_km:.0f} km of the store"
    else:
        fast.available, fast.eta_min, fast.eta_max = True, eta[0], eta[1]
        fast.fee = delivery_fee(store, cfg, dist, subtotal, "fast")
        fast.summary = f"{eta[0]}–{eta[1]} min (estimated)"
    out.append(fast)

    std = Option("standard", "Standard delivery", False)
    if not cfg.standard_enabled:
        std.reason = "Not offered by this store"
    elif blocked:
        std.reason = blocked
    elif not open_now or not packs_in_time:
        std.reason = f"Store closed · {status['detail']}" if status["state"] == "closed" else "Store is about to close"
    elif dist is None:
        # No map pin: the store can still deliver, but no time is promised (and only the base fee applies).
        std.available = True
        std.fee = delivery_fee(store, cfg, None, subtotal, "standard")
        std.summary = "Estimated time shown once your address has a map pin"
    else:
        window = max(cfg.standard_window_minutes, eta[1])
        std.available, std.eta_min, std.eta_max = True, eta[0], window
        std.fee = delivery_fee(store, cfg, dist, subtotal, "standard")
        std.summary = f"Within {window // 60} hours" if window % 60 == 0 and window >= 120 else f"Within {window} min"
    out.append(std)

    sch = Option("scheduled", "Scheduled delivery", False)
    if not cfg.scheduled_enabled:
        sch.reason = "Not offered by this store"
    elif blocked:
        sch.reason = blocked
    else:
        sch.slots = slots(store, cfg, now) if with_slots else []
        if with_slots and not sch.slots:
            sch.reason = "No slots left in the next days"
        else:
            sch.available = True
            sch.fee = delivery_fee(store, cfg, dist, subtotal, "scheduled")
            sch.summary = "Choose a time slot"
    out.append(sch)

    return {"status": status, "distance_km": dist, "options": [o.as_dict() for o in out], "_objects": out}


def headline(store: Store, point, now=None) -> dict:
    """What a store card shows: status, distance, the quickest available estimate and the starting fee."""
    res = options(store, point, now=now, with_slots=False)
    avail = [o for o in res["_objects"] if o.available and o.mode != "scheduled"]
    best = avail[0] if avail else None
    sched = next((o for o in res["_objects"] if o.mode == "scheduled" and o.available), None)
    cfg = config(store)
    return {
        "status": res["status"], "distance_km": res["distance_km"],
        "eta_min": best.eta_min if best else None, "eta_max": best.eta_max if best else None,
        "eta_label": (f"{best.eta_min}–{best.eta_max} min" if best and best.mode == "fast"
                      else best.summary if best and best.eta_min is not None else ""),
        "fast": bool(best and best.mode == "fast"),
        "delivery_fee": f"{min(o.fee for o in avail):.2f}" if avail else (f"{sched.fee:.2f}" if sched else None),
        "can_schedule": bool(sched),
        "deliverable": bool(avail or sched),
        "reason": "" if (avail or sched) else next((o.reason for o in res["_objects"] if o.reason), ""),
        "radius_km": f"{cfg.delivery_radius_km:.1f}",
    }
