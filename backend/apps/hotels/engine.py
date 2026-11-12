"""
Availability, pricing, offers and policies for Click. Hotels — computed on the server from records, never stored as
claims:

  free rooms   per night: the room type's units (or that night's override, 0 if closed) minus rooms held by
               pending-payment (until their hold expires) and confirmed bookings; a stay is bookable when every
               night has enough
  price        per night per room: the night's override, else the weekend price on Fri/Sat nights, else the
               rate's price; × rooms
  tax          GST on hotel accommodation by the nightly tariff (after discount): below ₹1,000 none, up to ₹7,500
               12%, above 18%
  offers       the best live offer whose conditions (nights, days before check-in, code) the stay meets
  cancellation from the rate plan: free until N days before check-in at the check-in time, then a fee %;
               non-refundable plans keep everything
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.rides.pricing import haversine_km

from .models import ACTIVE, BookingStatus, HotelBooking, HotelOffer, HotelProperty, RatePlan, RoomInventory, RoomType

TWO = Decimal("0.01")
MAX_NIGHTS = 30
MAX_ROOMS = 8
HOLD_MINUTES = 15


def money(x) -> Decimal:
    return Decimal(x).quantize(TWO, rounding=ROUND_HALF_UP)


def tz() -> ZoneInfo:
    return ZoneInfo(settings.TIME_ZONE)


def today() -> date:
    return timezone.now().astimezone(tz()).date()


def nights_of(check_in: date, check_out: date) -> list[date]:
    return [check_in + timedelta(days=i) for i in range((check_out - check_in).days)]


def gst_rate(nightly: Decimal) -> Decimal:
    if nightly < 1000:
        return Decimal("0")
    return Decimal("0.12") if nightly <= 7500 else Decimal("0.18")


def _live_holds(qs):
    now = timezone.now()
    return qs.filter(Q(status=BookingStatus.CONFIRMED) | Q(status=BookingStatus.PENDING_PAYMENT, hold_expires_at__gt=now))


def free_units(room: RoomType, dates: list[date], exclude_booking=None) -> int:
    """The fewest rooms of this type free on any of the nights (0 if any night is closed)."""
    if not dates:
        return 0
    inv = {i.date: i for i in RoomInventory.objects.filter(room_type=room, date__in=dates)}
    used = {d: 0 for d in dates}
    qs = _live_holds(HotelBooking.objects.filter(room_type=room, check_in__lt=dates[-1] + timedelta(days=1), check_out__gt=dates[0]))
    if exclude_booking is not None:
        qs = qs.exclude(pk=exclude_booking.pk)
    for b in qs.only("check_in", "check_out", "rooms"):
        for d in dates:
            if b.check_in <= d < b.check_out:
                used[d] += b.rooms
    free = []
    for d in dates:
        i = inv.get(d)
        if i is not None and i.closed:
            return 0
        units = i.units if i is not None and i.units is not None else room.total_units
        free.append(max(0, units - used[d]))
    return min(free)


def fits(room: RoomType, rooms: int, adults: int, children: int) -> bool:
    a, c = math.ceil(adults / rooms), math.ceil(children / rooms) if children else 0
    return a <= room.max_adults and c <= room.max_children and a + c <= room.max_occupancy and adults >= rooms


def nightly_prices(rate: RatePlan, dates: list[date]) -> list[tuple[date, Decimal]]:
    inv = {i.date: i for i in RoomInventory.objects.filter(room_type_id=rate.room_type_id, date__in=dates, price_override__isnull=False)}
    out = []
    for d in dates:
        if d in inv:
            p = inv[d].price_override
        elif rate.weekend_price is not None and d.weekday() in (4, 5):
            p = rate.weekend_price
        else:
            p = rate.price
        out.append((d, money(p)))
    return out


def live_offers(prop: HotelProperty):
    now = timezone.now()
    return HotelOffer.objects.filter(Q(property=prop) | Q(property__isnull=True), is_active=True, starts_at__lte=now, ends_at__gt=now)


def offer_applies(o: HotelOffer, check_in: date, nights: int, code: str = "") -> bool:
    ahead = (check_in - today()).days
    if nights < o.min_nights:
        return False
    if o.min_days_ahead is not None and ahead < o.min_days_ahead:
        return False
    if o.max_days_ahead is not None and ahead > o.max_days_ahead:
        return False
    if o.kind == HotelOffer.Kind.WEEKEND and not any(d.weekday() in (4, 5) for d in nights_of(check_in, check_in + timedelta(days=nights))):
        return False
    if o.code and o.code.lower() != (code or "").strip().lower():
        return False
    return True


def best_offer(prop: HotelProperty, check_in: date, nights: int, amount: Decimal, code: str = ""):
    best, best_amt = None, Decimal("0")
    for o in live_offers(prop):
        if not offer_applies(o, check_in, nights, code):
            continue
        amt = money(amount * o.percent / 100)
        if o.max_discount is not None:
            amt = min(amt, o.max_discount)
        if amt > best_amt:
            best, best_amt = o, amt
    return best, best_amt


def free_cancel_until(rate: RatePlan, prop: HotelProperty, check_in: date) -> datetime | None:
    if not rate.refundable or rate.free_cancel_days is None:
        return None
    until = datetime.combine(check_in - timedelta(days=rate.free_cancel_days), prop.check_in_time, tzinfo=tz())
    return until if until > timezone.now() else None  # a window that has already closed is never offered


def policy_text(refundable: bool, until: datetime | None, fee: int) -> str:
    if not refundable:
        return "Non-refundable: cancelling keeps the full amount."
    if until is None:
        return ("No free cancellation for these dates: cancelling keeps the full amount." if fee >= 100
                else f"No free cancellation for these dates: cancelling keeps {fee}% of the total.")
    when = until.astimezone(tz()).strftime("%d %b %Y, %I:%M %p").lstrip("0")
    after = "the full amount" if fee >= 100 else f"{fee}% of the total"
    return f"Free cancellation until {when}. After that, {after} is kept."


@dataclass
class Quote:
    rate: RatePlan
    room: RoomType
    free: int
    nightly: list[tuple[date, Decimal]]
    room_total: Decimal
    offer: HotelOffer | None
    discount: Decimal
    tax: Decimal
    total: Decimal
    cancel_until: datetime | None
    problem: str = ""
    rooms: int = 1

    def as_dict(self) -> dict:
        n = len(self.nightly)
        return {
            "rate_id": str(self.rate.id), "rate_name": self.rate.name, "meal_plan": self.rate.meal_plan, "meal_label": self.rate.get_meal_plan_display(),
            "refundable": self.rate.refundable, "free_cancel_until": self.cancel_until.isoformat() if self.cancel_until else None,
            "cancel_fee_percent": self.rate.cancel_fee_percent,
            "policy": policy_text(self.rate.refundable, self.cancel_until, self.rate.cancel_fee_percent),
            "payment": self.rate.payment, "payment_label": self.rate.get_payment_display(),
            "per_night": f"{money(self.room_total / max(1, n) / max(1, self.rooms)):.2f}" if n else None,
            "nightly": [{"date": d.isoformat(), "price": f"{p:.2f}"} for d, p in self.nightly],
            "room_total": f"{self.room_total:.2f}", "discount": f"{self.discount:.2f}", "offer": self.offer.title if self.offer else None,
            "tax": f"{self.tax:.2f}", "total": f"{self.total:.2f}", "rooms_left": self.free, "problem": self.problem,
        }


def quote(rate: RatePlan, check_in: date, check_out: date, rooms: int, adults: int, children: int, code: str = "", exclude_booking=None) -> Quote:
    room = rate.room_type
    dates = nights_of(check_in, check_out)
    free = free_units(room, dates, exclude_booking)
    nightly = nightly_prices(rate, dates)
    room_total = money(sum((p for _, p in nightly), Decimal("0")) * rooms)
    offer, discount = best_offer(room.property, check_in, len(dates), room_total, code)
    ratio = (room_total - discount) / room_total if room_total else Decimal("1")
    tax = money(sum((p * ratio * gst_rate(p * ratio) for _, p in nightly), Decimal("0")) * rooms)
    problem = ""
    if not room.property.partner.is_available:
        problem = "This property isn’t taking new bookings right now."
    elif not fits(room, rooms, adults, children):
        problem = f"{room.name} sleeps up to {room.max_adults} adults{f' and {room.max_children} children' if room.max_children else ''} per room."
    elif len(dates) < rate.min_nights:
        problem = f"This rate needs at least {rate.min_nights} nights."
    elif free < rooms:
        problem = "Sold out for these dates." if free == 0 else f"Only {free} room{'s' if free > 1 else ''} left for these dates."
    q = Quote(rate, room, free, nightly, room_total, offer, discount, tax, money(room_total - discount + tax),
              free_cancel_until(rate, room.property, check_in), problem, rooms)
    return q


def validate_stay(check_in: date, check_out: date, rooms: int, adults: int, children: int) -> str:
    if check_in < today():
        return "Check-in can’t be in the past."
    if check_out <= check_in:
        return "Check-out must be after check-in."
    if (check_out - check_in).days > MAX_NIGHTS:
        return f"Stays can be up to {MAX_NIGHTS} nights."
    if check_in > today() + timedelta(days=365):
        return "Bookings open up to a year ahead."
    if not 1 <= rooms <= MAX_ROOMS:
        return f"Book 1 to {MAX_ROOMS} rooms."
    if adults < rooms:
        return "Each room needs at least one adult."
    if adults + children > rooms * 6:
        return "That’s more guests than these rooms hold. Add rooms."
    return ""


def distance_km(prop: HotelProperty, point) -> float | None:
    if point is None:
        return None
    return round(haversine_km((float(prop.latitude), float(prop.longitude)), point), 1)


def rating_label(avg: Decimal, count: int) -> str:
    if not count:
        return ""
    a = float(avg)
    return "Exceptional" if a >= 9 else "Excellent" if a >= 8.5 else "Very good" if a >= 8 else "Good" if a >= 7 else "Pleasant" if a >= 6 else "Okay"
