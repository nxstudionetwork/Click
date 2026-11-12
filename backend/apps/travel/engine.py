"""
Timetables, availability, fares and policies for Click. Travel — always computed on the server from records:

  timetable     a Journey is a dated run of a Service; each Stop has a time and a day offset from the first stop,
                so the departure / arrival of any segment is exact (overnight and multi-day runs included)
  availability  bus: seats in the layout not held by an active booking (each seat is sold once per journey, enforced
                by a unique constraint); train: class capacity → confirmed, then RAC places, then a capped
                waitlist, else not available; flight: cabin capacity − seats sold (infants sit on a lap)
  fares         bus: the end-to-end fare × the share of the distance travelled; train: fare per km (minimum fare) +
                reservation and superfast charges; flight: the published fare × a demand step from the cabin's load
                factor and how close departure is — so fares really move and are re-checked before payment
  tax           GST as the provider applies it on the class (e.g. 5% on AC bus and AC train classes, 5% / 12% on
                economy / premium cabins); offers are computed on the server
  cancellation  the service's tiers: hours before departure → % kept; inside the last tier nothing is refunded;
                non-refundable fares keep everything
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import ACTIVE, FareClass, Journey, Mode, Passenger, Service, Stop, TravelOffer

TWO = Decimal("0.01")
HOLD_MINUTES = 10
MAX_PASSENGERS = {"bus": 6, "train": 6, "flight": 9}
CUTOFF_MINUTES = {"bus": 30, "train": 30, "flight": 120}
CHILD_MIN_AGE = {"bus": 3, "train": 5, "flight": 2}


def money(x) -> Decimal:
    return Decimal(x).quantize(TWO, rounding=ROUND_HALF_UP)


def round_to(x: Decimal, step: int) -> Decimal:
    return (Decimal(x) / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step


def tz() -> ZoneInfo:
    return ZoneInfo(settings.CLICK_LOCAL_TIMEZONE)


def today() -> date:
    return timezone.now().astimezone(tz()).date()


# --- timetable -------------------------------------------------------------------------------------------------------

def at(journey_date: date, stop: Stop, which: str) -> datetime:
    t = (stop.depart or stop.arrive) if which == "depart" else (stop.arrive or stop.depart)
    return datetime.combine(journey_date + timedelta(days=stop.day), t, tzinfo=tz())


def runs_on(service: Service, d: date) -> bool:
    return d.weekday() in (service.running_days or [])


def journey_for(service: Service, d: date) -> Journey | None:
    """The run that leaves the first stop on `d` (created from the timetable inside the booking window)."""
    if not service.is_active or not runs_on(service, d) or d < today() - timedelta(days=3):
        return None
    if d > today() + timedelta(days=service.booking_window_days):
        return None
    j, _ = Journey.objects.get_or_create(service=service, date=d)
    return j


def segment(service: Service, from_place_ids: set, to_place_ids: set) -> tuple[Stop, Stop] | None:
    """The first boarding stop in the origin set followed by a dropping stop in the destination set."""
    stops = list(service.stops.all())
    for i, a in enumerate(stops):
        if a.place_id in from_place_ids and a.boarding and a.depart:
            for b in stops[i + 1:]:
                if b.place_id in to_place_ids and b.dropping and b.arrive:
                    return a, b
    return None


def boarding_points(service: Service, city_ids: set) -> list[Stop]:
    return [s for s in service.stops.all() if s.place_id in city_ids and s.boarding and s.depart]


def dropping_points(service: Service, city_ids: set, after_seq: int) -> list[Stop]:
    return [s for s in service.stops.all() if s.place_id in city_ids and s.dropping and s.arrive and s.seq > after_seq]


def total_km(service: Service) -> int:
    stops = list(service.stops.all())
    return stops[-1].km if stops else 0


# --- availability ----------------------------------------------------------------------------------------------------

def _held(journey: Journey, fc: FareClass):
    return Passenger.objects.filter(journey=journey, fare_class=fc, holds_seat=True, booking__status__in=ACTIVE)


def bus_seats(service: Service, code: str | None = None) -> dict:
    seats = (service.seat_layout or {}).get("seats", {})
    return {k: v for k, v in seats.items() if code is None or v.get("class") == code}


def sold_seats(journey: Journey) -> set[str]:
    return set(Passenger.objects.filter(journey=journey, holds_seat=True, booking__status__in=ACTIVE).exclude(seat="")
               .values_list("seat", flat=True))


@dataclass
class Availability:
    status: str  # available | rac | waitlist | not_available
    count: int
    label: str

    def as_dict(self) -> dict:
        return {"status": self.status, "count": self.count, "label": self.label}


def availability(fc: FareClass, journey: Journey, passengers: int = 1) -> Availability:
    if journey.status == Journey.Status.CANCELLED:
        return Availability("not_available", 0, "Cancelled by operator")
    mode = fc.service.mode
    if mode == Mode.BUS:
        seats = bus_seats(fc.service, fc.code)
        free = len([s for s in seats if s not in sold_seats(journey)])
        return Availability("available" if free else "not_available", free, f"{free} seat{'s' if free != 1 else ''} left" if free else "Sold out")
    held = _held(journey, fc)
    if mode == Mode.FLIGHT:
        free = fc.capacity - held.count()
        if free <= 0:
            return Availability("not_available", 0, "Sold out")
        return Availability("available", free, f"{free} seat{'s' if free != 1 else ''} left" if free <= 9 else "Available")
    cnf = held.filter(seat_status=Passenger.SeatStatus.CONFIRMED).count()
    rac = held.filter(seat_status=Passenger.SeatStatus.RAC).count()
    wl = held.filter(seat_status=Passenger.SeatStatus.WAITLIST).count()
    free = fc.capacity - cnf
    if free > 0:
        return Availability("available", free, f"Available {free}")
    if rac < fc.rac_capacity:
        return Availability("rac", rac + 1, f"RAC {rac + 1}")
    if wl < fc.waitlist_limit:
        return Availability("waitlist", wl + 1, f"WL {wl + 1}")
    return Availability("not_available", 0, "Not available")


# --- fares -----------------------------------------------------------------------------------------------------------

def demand_step(fc: FareClass, journey: Journey, departs: datetime) -> Decimal:
    """Flights: published fare × a step by load factor, and a step close to departure."""
    load = _held(journey, fc).count() / max(1, fc.capacity)
    step = Decimal("1") if load < 0.4 else Decimal("1.15") if load < 0.7 else Decimal("1.35") if load < 0.9 else Decimal("1.6")
    days = (departs - timezone.now()).days
    if days < 3:
        step *= Decimal("1.2")
    elif days < 7:
        step *= Decimal("1.08")
    return step


def unit_fare(fc: FareClass, journey: Journey, a: Stop, b: Stop) -> tuple[Decimal, Decimal]:
    """(fare, fees) for one seat on the segment a → b, before tax."""
    mode = fc.service.mode
    km = b.km - a.km
    if mode == Mode.TRAIN:
        fare = max(fc.min_fare, round_to(fc.per_km * km, 5))
        return money(fare), money(fc.reservation_charge + fc.superfast_charge)
    if mode == Mode.BUS:
        share = Decimal(km) / max(1, total_km(fc.service))
        return money(max(fc.min_fare, round_to(fc.base_fare * share, 10))), Decimal("0.00")
    fare = round_to(fc.base_fare * demand_step(fc, journey, at(journey.date, a, "depart")), 1) - 1  # e.g. 5,499
    return money(max(fc.min_fare, fare)), Decimal("0.00")


def live_offers(mode: str):
    now = timezone.now()
    return TravelOffer.objects.filter(Q(mode=mode) | Q(mode=""), is_active=True, starts_at__lte=now, ends_at__gt=now)


@dataclass
class Quote:
    unit: Decimal
    seats: int
    infants: int
    base: Decimal
    fees: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal
    offer: TravelOffer | None = None
    lines: list = field(default_factory=list)
    coupon_error: str = ""

    def as_dict(self) -> dict:
        return {"unit_fare": f"{self.unit:.2f}", "base_fare": f"{self.base:.2f}", "fees": f"{self.fees:.2f}", "discount": f"{self.discount:.2f}",
                "offer": self.offer.title if self.offer else None, "tax": f"{self.tax:.2f}", "total": f"{self.total:.2f}",
                "lines": self.lines, "coupon_error": self.coupon_error}


def quote(fc: FareClass, journey: Journey, a: Stop, b: Stop, seats: int, infants: int = 0, coupon: str = "", seat_fares: list | None = None) -> Quote:
    """`seat_fares` (bus): each seat's own fare when a coach mixes seat classes."""
    fare, fees_each = unit_fare(fc, journey, a, b)
    fares = seat_fares or [fare] * seats
    base = sum(fares, Decimal("0")) + fc.infant_fare * infants
    fees = fees_each * seats
    lines = [{"label": f"Fare × {seats}", "amount": f"{sum(fares, Decimal('0')):.2f}"}]
    if infants:
        lines.append({"label": f"Infant × {infants}", "amount": f"{fc.infant_fare * infants:.2f}"})
    if fees:
        lines.append({"label": "Reservation & superfast charges", "amount": f"{fees:.2f}"})
    best, discount, coupon_error = None, Decimal("0"), ""
    for o in live_offers(fc.service.mode):
        if o.code and o.code.upper() != (coupon or "").strip().upper():
            continue
        if base < o.min_fare:
            if o.code:
                coupon_error = f"{o.code} needs a fare of ₹{o.min_fare:,.0f} or more."
            continue
        d = money(base * o.percent / 100)
        if o.max_discount is not None:
            d = min(d, o.max_discount)
        if d > discount:
            best, discount = o, d
    if coupon and (best is None or best.code.upper() != coupon.strip().upper()) and not coupon_error:
        coupon_error = "That code isn’t valid for this journey."
    tax = money((base + fees - discount) * fc.tax_percent / 100)
    total = money(base + fees - discount + tax)
    return Quote(fare, seats, infants, money(base), money(fees), money(discount), tax, total, best, lines, coupon_error)


# --- cancellation ----------------------------------------------------------------------------------------------------

def policy_text(refundable: bool, rules: list) -> str:
    if not refundable:
        return "Non-refundable: nothing is refunded if you cancel."
    if not rules:
        return "Cancellation isn’t available on this fare."
    parts = []
    for i, r in enumerate(sorted(rules, key=lambda x: -x["hours"])):
        parts.append(f"{_hours(r['hours'], '+')}{' before departure' if i == 0 else ''}: {'free' if not r['fee_percent'] else str(r['fee_percent']) + '% fee'}")
    last = min(r["hours"] for r in rules)
    return "Cancellation: " + "; ".join(parts) + f"; under {_hours(last)}: no refund."


def _hours(h: int, plus: str = "") -> str:
    if h >= 24 and h % 24 == 0:
        return f"{h // 24}{plus} day{'s' if h // 24 != 1 or plus else ''}"
    return f"{h}{plus} hour{'s' if h != 1 or plus else ''}"


def cancel_fee_percent(refundable: bool, rules: list, departs: datetime) -> int:
    if not refundable or not rules:
        return 100
    hours = (departs - timezone.now()).total_seconds() / 3600
    for r in sorted(rules, key=lambda x: -x["hours"]):
        if hours >= r["hours"]:
            return int(r["fee_percent"])
    return 100


def duration_minutes(a: datetime, b: datetime) -> int:
    return int((b - a).total_seconds() // 60)
