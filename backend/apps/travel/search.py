"""
Travel search behind a provider boundary. `ClickInventory` searches Click.'s own timetabled inventory (operators that
manage services through Click.). An aggregator or a direct provider API implements the same `options()` method and
is listed in CLICK_TRAVEL_PROVIDERS; providers run with a timeout, their credentials stay on the server, and a
provider that fails is reported as unavailable — never replaced with invented results.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Prefetch, Q
from django.utils import timezone
from django.utils.module_loading import import_string

from . import engine
from .models import FareClass, Mode, Operator, Place, Service, Stop

PAGE = 15
BUCKETS = {"early": (0, 6), "morning": (6, 12), "afternoon": (12, 17), "evening": (17, 21), "night": (21, 24)}
BUCKET_LABELS = {"early": "Before 6 AM", "morning": "6 AM – 12 PM", "afternoon": "12 – 5 PM", "evening": "5 – 9 PM", "night": "After 9 PM"}
TRAIN_CLASSES = [("1A", "First AC"), ("2A", "AC 2 Tier"), ("3A", "AC 3 Tier"), ("SL", "Sleeper"), ("CC", "AC Chair Car"), ("EC", "Executive Chair Car")]
CABINS = [("economy", "Economy"), ("premium_economy", "Premium Economy"), ("business", "Business"), ("first", "First")]


class TravelUnavailable(Exception):
    pass


def place_ids(p: Place, mode: str) -> set:
    """A city means every station / airport / boarding point in it (of the right kind); a specific point means just it."""
    if p.kind != Place.Kind.CITY:
        return {p.id}
    kind = {"bus": Place.Kind.BUS_STOP, "train": Place.Kind.STATION, "flight": Place.Kind.AIRPORT}[mode]
    return {p.id, *p.points.filter(kind=kind, is_active=True).values_list("id", flat=True)}


def _bucket(dt: datetime) -> str:
    h = dt.astimezone(engine.tz()).hour
    return next(k for k, (a, b) in BUCKETS.items() if a <= h < b)


def _cancel_kind(service: Service, fc_refundable: bool) -> str:
    if not fc_refundable or not service.cancellation:
        return "non_refundable"
    first = max(service.cancellation, key=lambda r: r["hours"])
    return "free" if first["fee_percent"] == 0 else "partial"


def stop_out(s: Stop, jd: date, which: str) -> dict:
    p = s.place
    return {"stop_id": str(s.id), "place_id": str(p.id), "name": p.name, "code": p.code, "kind": p.kind, "city": p.city_place.name,
            "address": p.address, "landmark": p.landmark, "note": s.note, "at": engine.at(jd, s, which).isoformat()}


def class_out(fc: FareClass, j, a: Stop, b: Stop, seats: int) -> dict:
    fare, fees = engine.unit_fare(fc, j, a, b)
    tax = engine.money((fare + fees) * fc.tax_percent / 100)
    av = engine.availability(fc, j, seats)
    return {"code": fc.code, "name": fc.name, "fare_type": fc.fare_type, "fare": f"{fare:.2f}", "fees": f"{fees:.2f}",
            "tax": f"{tax:.2f}", "per_person": f"{fare + fees + tax:.2f}", "availability": av.as_dict(),
            "bookable": av.status != "not_available" and (av.status != "available" or av.count >= seats or fc.service.mode == Mode.TRAIN),
            "refundable": fc.refundable, "meal": fc.meal, "change_fee": f"{fc.change_fee:.2f}" if fc.change_fee is not None else None,
            "infant_fare": f"{fc.infant_fare:.2f}" if fc.infant_fare else None}


def option(service: Service, j, a: Stop, b: Stop, seats: int, cls: str = "", city_from: set | None = None, city_to: set | None = None) -> dict | None:
    dep, arr = engine.at(j.date, a, "depart"), engine.at(j.date, b, "arrive")  # scheduled times; a delay is shown alongside
    classes = [fc for fc in service.classes.all() if not cls or fc.code == cls]
    if not classes:
        return None
    op = service.operator
    stops = [s for s in service.stops.all() if a.seq < s.seq < b.seq]
    out_classes = [class_out(fc, j, a, b, seats) for fc in classes]
    bookable = [c for c in out_classes if c["bookable"]]
    lowest = min((Decimal(c["per_person"]) for c in (bookable or out_classes)), default=None)
    out = {
        "id": f"{j.id}.{a.id}.{b.id}", "mode": service.mode, "journey_id": str(j.id), "from_stop_id": str(a.id), "to_stop_id": str(b.id),
        "operator": {"id": str(op.id), "name": op.name, "code": op.code, "accent": op.accent, "logo_url": op.logo_url or None,
                     "rating": {"average": f"{op.rating_average:.1f}", "count": op.rating_count} if op.rating_count >= 5 else None},
        "service": {"number": service.number, "name": service.name, "vehicle": service.vehicle, "bus_type": service.bus_type,
                    "bus_type_label": service.get_bus_type_display() if service.bus_type else "", "ac": service.ac, "premium": service.premium,
                    "amenities": service.amenities, "running_days": service.running_days, "baggage": service.baggage or None},
        "departs_at": dep.isoformat(), "arrives_at": arr.isoformat(), "duration_minutes": engine.duration_minutes(dep, arr),
        "days_later": (arr.astimezone(engine.tz()).date() - dep.astimezone(engine.tz()).date()).days,
        "from": stop_out(a, j.date, "depart"), "to": stop_out(b, j.date, "arrive"),
        "stops": len(stops), "via": [s.place.city_place.name if service.mode == Mode.FLIGHT else s.place.name for s in stops][:6],
        "distance_km": b.km - a.km, "classes": out_classes, "lowest": f"{lowest:.2f}" if lowest is not None else None,
        "available": bool(bookable), "refundable": any(fc.refundable for fc in classes),
        "cancellation": _cancel_kind(service, any(fc.refundable for fc in classes)),
        "policy": engine.policy_text(any(fc.refundable for fc in classes), service.cancellation),
        "status": j.status, "status_label": j.get_status_display(), "delay_minutes": j.delay_minutes, "notice": j.notice,
        "dep_bucket": _bucket(dep), "arr_bucket": _bucket(arr),
    }
    if service.mode == Mode.BUS:
        out["seats_left"] = sum(c["availability"]["count"] for c in out_classes)
        out["boarding_points"] = [stop_out(s, j.date, "depart") for s in engine.boarding_points(service, city_from or {a.place_id})]
        out["dropping_points"] = [stop_out(s, j.date, "arrive") for s in engine.dropping_points(service, city_to or {b.place_id}, a.seq)]
    return out


class ClickInventory:
    """Click. partner inventory: timetabled services operators manage through Click."""

    name = "click"

    def options(self, mode: str, origin: Place, destination: Place, d: date, seats: int, cls: str = "") -> list[dict]:
        from_ids, to_ids = place_ids(origin, mode), place_ids(destination, mode)
        services = (Service.objects.filter(mode=mode, is_active=True, operator__status=Operator.Status.ACTIVE)
                    .filter(stops__place__in=from_ids).filter(stops__place__in=to_ids).distinct()
                    .select_related("operator")
                    .prefetch_related(Prefetch("stops", queryset=Stop.objects.select_related("place__city").order_by("seq")), "classes"))
        cutoff = timezone.now() + timedelta(minutes=engine.CUTOFF_MINUTES[mode])
        out = []
        for s in services:
            seg = engine.segment(s, from_ids, to_ids)
            if not seg:
                continue
            a, b = seg
            j = engine.journey_for(s, d - timedelta(days=a.day))
            if j is None or engine.at(j.date, a, "depart") < cutoff:
                continue
            o = option(s, j, a, b, seats, cls, from_ids, to_ids)
            if o:
                out.append(o)
        return out


def providers() -> list:
    paths = getattr(settings, "CLICK_TRAVEL_PROVIDERS", None) or ["apps.travel.search.ClickInventory"]
    return [import_string(p)() for p in paths]


def gather(mode, origin, destination, d, seats, cls="") -> list[dict]:
    provs = providers()
    if len(provs) == 1:  # one provider: run inline (same DB connection)
        try:
            return provs[0].options(mode, origin, destination, d, seats, cls)
        except Exception as e:  # pragma: no cover - defensive
            raise TravelUnavailable(str(e)) from e
    results, failures = [], 0
    with ThreadPoolExecutor(max_workers=len(provs)) as pool:
        futures = [pool.submit(p.options, mode, origin, destination, d, seats, cls) for p in provs]
        for f in futures:
            try:
                results += f.result(timeout=getattr(settings, "CLICK_TRAVEL_PROVIDER_TIMEOUT", 8))
            except (FutureTimeout, Exception):
                failures += 1
    if failures == len(provs):
        raise TravelUnavailable("All travel providers failed.")
    seen, unique = set(), []
    for o in results:  # the same service from two sources is listed once
        key = (o["operator"]["name"], o["service"]["number"], o["departs_at"])
        if key not in seen:
            seen.add(key)
            unique.append(o)
    return unique


# --- filters, sorts, highlights --------------------------------------------------------------------------------------

def _num(x) -> float:
    return float(x) if x is not None else float("inf")


def apply_filters(opts: list[dict], f: dict) -> list[dict]:
    out = []
    for o in opts:
        low = _num(o["lowest"])
        if f.get("min_price") is not None and low < float(f["min_price"]):
            continue
        if f.get("max_price") is not None and low > float(f["max_price"]):
            continue
        if f.get("departure") and o["dep_bucket"] not in f["departure"]:
            continue
        if f.get("arrival") and o["arr_bucket"] not in f["arrival"]:
            continue
        if f.get("operators") and o["operator"]["id"] not in f["operators"]:
            continue
        if f.get("min_rating") and not (o["operator"]["rating"] and float(o["operator"]["rating"]["average"]) >= float(f["min_rating"])):
            continue
        if f.get("cancellation") and o["cancellation"] not in f["cancellation"]:
            continue
        if f.get("available_only") and not o["available"]:
            continue
        if f.get("amenities") and not set(f["amenities"]) <= set(o["service"]["amenities"]):
            continue
        if f.get("max_duration") and o["duration_minutes"] > int(f["max_duration"]) * 60:
            continue
        if o["mode"] == Mode.BUS:
            types = set(f.get("bus_type") or [])
            sv = o["service"]
            if types:
                have = {"ac" if sv["ac"] else "non_ac", sv["bus_type"], *(["premium"] if sv["premium"] else [])}
                if sv["bus_type"] == "seater_sleeper":
                    have |= {"seater", "sleeper"}
                ac_wanted = types & {"ac", "non_ac"}
                kind_wanted = types - {"ac", "non_ac"}
                if (ac_wanted and not ac_wanted & have) or (kind_wanted and not kind_wanted & have):
                    continue
            if f.get("boarding") and not {p["place_id"] for p in o["boarding_points"]} & set(f["boarding"]):
                continue
            if f.get("dropping") and not {p["place_id"] for p in o["dropping_points"]} & set(f["dropping"]):
                continue
        if o["mode"] == Mode.TRAIN:
            if f.get("train_type") and o["service"]["vehicle"] not in f["train_type"]:
                continue
            if f.get("weekday") is not None and int(f["weekday"]) not in o["service"]["running_days"]:
                continue
        if o["mode"] == Mode.FLIGHT:
            if f.get("stops"):
                want = {int(x) for x in f["stops"]}
                if min(o["stops"], 2) not in want:
                    continue
            if f.get("refundable") and not o["refundable"]:
                continue
            if f.get("checked_bag") and not (o["service"]["baggage"] or {}).get("check_in"):
                continue
        out.append(o)
    return out


def highlights(opts: list[dict]) -> dict:
    """Labels computed from the result data: cheapest, fastest and best value (price and time, 60/40)."""
    live = [o for o in opts if o["available"] and o["lowest"]]
    if not live:
        return {}
    cheapest = min(live, key=lambda o: (Decimal(o["lowest"]), o["departs_at"]))
    fastest = min(live, key=lambda o: (o["duration_minutes"], Decimal(o["lowest"])))
    out = {"cheapest": cheapest["id"], "fastest": fastest["id"]}
    if len(live) >= 3:
        lo, fa = float(cheapest["lowest"]), max(1, fastest["duration_minutes"])
        best = min(live, key=lambda o: 0.6 * float(o["lowest"]) / lo + 0.4 * o["duration_minutes"] / fa)
        if best["id"] not in (cheapest["id"], fastest["id"]):  # only a label of its own when it's a different option
            out["best_value"] = best["id"]
    return out


def strip(opts: list[dict], hl: dict) -> list[dict]:
    by_id = {o["id"]: o for o in opts}
    names = {"cheapest": "Cheapest", "fastest": "Fastest", "best_value": "Best value"}
    return [{"key": k, "label": names[k], "id": v, "total": by_id[v]["lowest"], "duration_minutes": by_id[v]["duration_minutes"],
             "departs_at": by_id[v]["departs_at"], "operator": by_id[v]["operator"]["name"]} for k, v in hl.items()]


def _recommended_key(o: dict, lo: float, fa: int):
    rating = float(o["operator"]["rating"]["average"]) if o["operator"]["rating"] else 3.5
    return (not o["available"], 0.5 * float(o["lowest"] or 1e9) / lo + 0.3 * o["duration_minutes"] / fa - 0.1 * (rating - 3.5))


def sort(opts: list[dict], how: str) -> list[dict]:
    if not opts:
        return opts
    if how in ("price", "cheapest"):
        return sorted(opts, key=lambda o: (not o["available"], _num(o["lowest"])))
    if how == "departure":
        return sorted(opts, key=lambda o: o["departs_at"])
    if how == "arrival":
        return sorted(opts, key=lambda o: o["arrives_at"])
    if how in ("duration", "fastest"):
        return sorted(opts, key=lambda o: (o["duration_minutes"], _num(o["lowest"])))
    if how == "rating":
        return sorted(opts, key=lambda o: (-(float(o["operator"]["rating"]["average"]) if o["operator"]["rating"] else 0), _num(o["lowest"])))
    live = [o for o in opts if o["lowest"]]
    lo = min((float(o["lowest"]) for o in live), default=1.0) or 1.0
    fa = max(1, min((o["duration_minutes"] for o in opts), default=1))
    return sorted(opts, key=lambda o: _recommended_key(o, lo, fa))


def facets(opts: list[dict]) -> dict:
    ops = {o["operator"]["id"]: o["operator"]["name"] for o in opts}
    out = {"operators": [{"id": k, "name": v} for k, v in sorted(ops.items(), key=lambda x: x[1])],
           "price": {"min": min((o["lowest"] for o in opts if o["lowest"]), key=Decimal, default=None),
                     "max": max((o["lowest"] for o in opts if o["lowest"]), key=Decimal, default=None)},
           "amenities": sorted({a for o in opts for a in o["service"]["amenities"]}),
           "departure": [{"code": k, "label": BUCKET_LABELS[k]} for k in BUCKETS], "cancellation": sorted({o["cancellation"] for o in opts})}
    if opts and opts[0]["mode"] == Mode.BUS:
        bp, dp = {}, {}
        for o in opts:
            bp.update({p["place_id"]: p["name"] for p in o["boarding_points"]})
            dp.update({p["place_id"]: p["name"] for p in o["dropping_points"]})
        out["boarding"] = [{"id": k, "name": v} for k, v in sorted(bp.items(), key=lambda x: x[1])]
        out["dropping"] = [{"id": k, "name": v} for k, v in sorted(dp.items(), key=lambda x: x[1])]
    if opts and opts[0]["mode"] == Mode.TRAIN:
        out["train_types"] = sorted({o["service"]["vehicle"] for o in opts if o["service"]["vehicle"]})
    return out


def cheapest_on(mode, origin, destination, d, seats, cls="") -> Decimal | None:
    opts = [o for o in gather(mode, origin, destination, d, seats, cls) if o["available"] and o["lowest"]]
    return min((Decimal(o["lowest"]) for o in opts), default=None)
