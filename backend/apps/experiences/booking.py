"""
Availability, pricing and reservations for Click. Bookings (temples, attractions, experiences). All on the server:

  availability  per offering and date (and slot): closed if the provider is closed that day or doesn't run it; else
                capacity − places used by confirmed bookings and by pending ones still inside their hold; a slot that
                starts within 15 minutes (or a day ticket after closing time) has expired
  price         the provider's ticket types × quantities, the best live offer that qualifies, then GST as the provider
                applies it (none on darshan / seva; e.g. 18% on amusement parks)
  book          must match the reviewed total (`price_changed`), idempotent, locks the offering so the last places
                can't be sold twice; paid from the Click. Wallet in the same transaction (free darshan registrations
                confirm without payment); if payment fails the places are held 10 minutes for a retry
  entry code    issued on confirmation; the provider verifies it in the Click. Partner App (no QR the provider
                doesn't scan)
  cancel        free until N hours before the visit, then the provider's fee %; refunds to the wallet
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from apps.activity.services import record
from apps.core.api.exceptions import ConflictError, DomainError
from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify

from .models import ACTIVE, Attraction, BookingStatus as S, ExperienceBooking, ExperienceOffer, ExperienceReview, Offering, StatusEvent, entry_code

TWO = Decimal("0.01")
HOLD_MINUTES = 10
SLOT_CUTOFF_MINUTES = 15


def money(x) -> Decimal:
    return Decimal(x).quantize(TWO, rounding=ROUND_HALF_UP)


def tz() -> ZoneInfo:
    return ZoneInfo(settings.CLICK_LOCAL_TIMEZONE)


def today() -> date:
    return timezone.now().astimezone(tz()).date()


def _t(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def starts_at(d: date, slot: time | None, a: Attraction) -> datetime:
    opening = (a.opening or {}).get("open")
    return datetime.combine(d, slot or (_t(opening) if opening else time(0, 0)), tzinfo=tz())


def used_units(o: Offering, d: date, slot: time | None) -> int:
    qs = ExperienceBooking.objects.filter(offering=o, visit_date=d, status__in=ACTIVE).filter(
        Q(status=S.CONFIRMED) | Q(hold_expires_at__gt=timezone.now()))
    qs = qs.filter(slot_time=slot) if slot else qs.filter(slot_time__isnull=True)
    return qs.aggregate(s=Sum("units"))["s"] or 0


def day_state(o: Offering, d: date) -> str:
    """open | closed | not_running | too_far | past"""
    if d < today():
        return "past"
    if d > today() + timedelta(days=o.book_ahead_days):
        return "too_far"
    if o.attraction.closures.filter(date=d).exists():
        return "closed"
    if d.weekday() not in (o.days or []):
        return "not_running"
    return "open"


def slots(o: Offering, d: date) -> list[dict]:
    state = day_state(o, d)
    if state != "open":
        return []
    now = timezone.now() + timedelta(minutes=SLOT_CUTOFF_MINUTES)
    out = []
    if o.booking_model == Offering.Model.SLOT:
        for s in o.slot_times:
            st = _t(s)
            left = max(0, o.capacity - used_units(o, d, st))
            start = datetime.combine(d, st, tzinfo=tz())
            expired = start <= now
            passed = start <= timezone.now()
            out.append({"time": s, "left": left, "status": "expired" if expired else ("sold_out" if left == 0 else "available"),
                        "label": ("Time passed" if passed else "Starting soon · closed") if expired else
                        ("Sold out" if left == 0 else f"{left} left" if left <= 20 else "Available")})
    else:
        left = max(0, o.capacity - used_units(o, d, None))
        close = (o.attraction.opening or {}).get("close")
        expired = bool(close) and datetime.combine(d, _t(close), tzinfo=tz()) <= now
        out.append({"time": None, "left": left, "status": "expired" if expired else ("sold_out" if left == 0 else "available"),
                    "label": "Closed for today" if expired else ("Sold out" if left == 0 else f"{left} left" if left <= 20 else "Available")})
    return out


def calendar(o: Offering, days: int = 14) -> list[dict]:
    out = []
    for i in range(days):
        d = today() + timedelta(days=i)
        state = day_state(o, d)
        if state != "open":
            out.append({"date": d.isoformat(), "status": state, "left": 0})
            continue
        ss = slots(o, d)
        live = [s for s in ss if s["status"] == "available"]
        out.append({"date": d.isoformat(), "status": "available" if live else ("sold_out" if any(s["status"] == "sold_out" for s in ss) else "expired"),
                    "left": sum(s["left"] for s in live)})
    return out


def live_offers(a: Attraction):
    now = timezone.now()
    return ExperienceOffer.objects.filter(Q(attraction=a) | Q(attraction__isnull=True, group=a.group) | Q(attraction__isnull=True, group=""),
                                          is_active=True, starts_at__lte=now, ends_at__gt=now)


@dataclass
class Quote:
    lines: list
    visitors: int
    units: int
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal
    offer: ExperienceOffer | None = None
    coupon_error: str = ""
    problems: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"lines": self.lines, "visitors": self.visitors, "units": self.units, "subtotal": f"{self.subtotal:.2f}",
                "discount": f"{self.discount:.2f}", "offer": self.offer.title if self.offer else None, "tax": f"{self.tax:.2f}",
                "total": f"{self.total:.2f}", "coupon_error": self.coupon_error}


def quote(o: Offering, qty: dict, coupon: str = "") -> Quote:
    prices = {p.visitor: p for p in o.prices.all()}
    lines, visitors, units, subtotal, problems = [], 0, 0, Decimal("0"), []
    for visitor, n in qty.items():
        if not n:
            continue
        p = prices.get(visitor)
        if p is None:
            problems.append(f"{visitor.title()} tickets aren’t sold for {o.name}.")
            continue
        amount = money(p.amount * n)
        lines.append({"visitor": visitor, "label": p.label or p.get_visitor_display(), "qty": n, "unit": f"{p.amount:.2f}", "amount": f"{amount:.2f}", "units": p.units * n})
        visitors += (4 if visitor == "family" else 1) * n
        units += p.units * n
        subtotal += amount
    best, discount, coupon_error = None, Decimal("0"), ""
    if subtotal > 0:
        for off in live_offers(o.attraction):
            if off.code and off.code.upper() != (coupon or "").strip().upper():
                continue
            if subtotal < off.min_amount:
                if off.code:
                    coupon_error = f"{off.code} needs ₹{off.min_amount:,.0f} or more."
                continue
            d = money(subtotal * off.percent / 100)
            if off.max_discount is not None:
                d = min(d, off.max_discount)
            if d > discount:
                best, discount = off, d
    if coupon and (best is None or best.code.upper() != coupon.strip().upper()) and not coupon_error:
        coupon_error = "That code isn’t valid for this booking."
    tax = money((subtotal - discount) * o.tax_percent / 100)
    return Quote(lines, visitors, units, money(subtotal), money(discount), tax, money(subtotal - discount + tax), best, coupon_error, problems)


def free_cancel_until(a: Attraction, start: datetime) -> datetime | None:
    if not a.refundable:
        return None
    until = start - timedelta(hours=a.free_cancel_hours)
    return until if until > timezone.now() else None


def policy_text(refundable: bool, until: datetime | None, fee_percent: int) -> str:
    if not refundable:
        return "Non-refundable: nothing is refunded if you cancel."
    if until:
        after = "no refund after that" if fee_percent >= 100 else f"{fee_percent}% fee after that"
        return f"Free cancellation until {until.astimezone(tz()):%d %b, %I:%M %p}; {after}."
    return "Free cancellation has closed for this date; " + ("no refund if you cancel." if fee_percent >= 100 else f"a {fee_percent}% fee applies.")


def _offering(data) -> Offering:
    o = (Offering.objects.select_related("attraction__provider").prefetch_related("prices")
         .filter(pk=data["offering_id"], is_active=True, attraction__is_listed=True, attraction__bookable=True).first())
    if o is None:
        raise DomainError("This can’t be booked through Click. right now.", code="not_bookable", status_code=404)
    return o


def prepare(data: dict) -> dict:
    o = _offering(data)
    a = o.attraction
    d = data["visit_date"]
    slot = _t(data["slot_time"]) if data.get("slot_time") else None
    q = quote(o, data["tickets"], data.get("coupon") or "")
    problem = q.problems[0] if q.problems else ""
    state = day_state(o, d)
    if not problem and state != "open":
        problem = {"past": "Choose today or a later date.", "too_far": f"Bookings open {o.book_ahead_days} days ahead.",
                   "closed": f"{a.name} is closed on {d:%d %b}.", "not_running": f"{o.name} doesn’t run on {d:%A}s."}[state]
    if not problem and o.booking_model == Offering.Model.SLOT and (slot is None or slot.strftime("%H:%M") not in o.slot_times):
        problem = "Choose a time slot."
    if not problem and q.visitors == 0:
        problem = "Add at least one ticket."
    if not problem and q.units > o.max_per_booking:
        problem = f"Up to {o.max_per_booking} places per booking."
    if not problem and any(ln["visitor"] in ("child", "infant") for ln in q.lines) and not any(ln["visitor"] not in ("child", "infant") for ln in q.lines):
        problem = "Children must be accompanied by an adult ticket."
    if not problem:
        s = next((x for x in slots(o, d) if x["time"] == (slot.strftime("%H:%M") if slot else None)), None)
        if s is None or s["status"] == "expired":
            problem = "That time has passed. Choose another slot or date."
        elif s["left"] < q.units:
            problem = "Sold out for that time." if s["left"] == 0 else f"Only {s['left']} places left for that time."
    if not problem and o.pickup_points and data.get("pickup_point") not in o.pickup_points:
        problem = "Choose a pickup point."
    start = starts_at(d, slot, a)
    until = free_cancel_until(a, start)
    from apps.rewards.services import points_for_amount

    return {"attraction": {"id": str(a.id), "slug": a.slug, "name": a.name, "kind": a.kind, "kind_label": a.get_kind_display(), "city": a.city,
                           "address": a.address, "accent": a.accent},
            "offering": {"id": str(o.id), "name": o.name, "kind": o.kind, "kind_label": o.get_kind_display(), "booking_model": o.booking_model,
                         "requirements": o.requirements, "duration_minutes": o.duration_minutes},
            "visit_date": d.isoformat(), "slot_time": slot.strftime("%H:%M") if slot else None, "pickup_point": data.get("pickup_point") or "",
            **q.as_dict(), "policy": policy_text(a.refundable, until, a.cancel_fee_percent), "refundable": a.refundable,
            "free_cancel_until": until.isoformat() if until else None, "points": points_for_amount(q.subtotal) if q.subtotal else 0,
            "instant_confirmation": a.instant_confirmation, "hold_minutes": HOLD_MINUTES, "bookable": not problem, "problem": problem,
            "dress_code": a.dress_code}


def _note(b: ExperienceBooking, title: str, body: str) -> None:
    notify(b.customer, NotificationCategory.BOOKINGS, f"{title} · {b.number}"[:120], body[:300], f"/bookings/r/{b.id}")


def _event(b: ExperienceBooking, to: str, note: str = "") -> None:
    StatusEvent.objects.create(booking=b, to=to, note=note[:200])


@transaction.atomic
def book(customer, data: dict) -> tuple[ExperienceBooking, bool, str]:
    existing = ExperienceBooking.objects.filter(customer=customer, idempotency_key=data["idempotency_key"]).first()
    if existing:
        return existing, False, ""
    o = _offering(data)
    Offering.objects.select_for_update().get(pk=o.pk)  # one sale at a time per offering: the last places can't be sold twice
    p = prepare(data)
    if not p["bookable"]:
        raise ConflictError(p["problem"], code="not_available", details={"review": p})
    if data.get("expected_total") is not None and Decimal(str(data["expected_total"])) != Decimal(p["total"]):
        raise ConflictError("The price changed. Review the new total.", code="price_changed", details={"review": p})
    a = o.attraction
    slot = _t(p["slot_time"]) if p["slot_time"] else None
    when = f"{data['visit_date']:%a %d %b}" + (f", {slot:%I:%M %p}" if slot else "")
    b = ExperienceBooking.objects.create(
        customer=customer, attraction=a, offering=o, visit_date=data["visit_date"], slot_time=slot, lines=p["lines"], visitors=p["visitors"],
        units=p["units"], lead_name=data["lead_name"].strip(), lead_phone=data["lead_phone"].strip(), lead_email=data.get("lead_email") or "",
        visitor_names=[n.strip()[:80] for n in data.get("visitor_names") or [] if n.strip()][:20], pickup_point=p["pickup_point"],
        title=f"{o.name} · {a.name}"[:200], refundable=a.refundable,
        free_cancel_until=datetime.fromisoformat(p["free_cancel_until"]) if p["free_cancel_until"] else None,
        cancel_fee_percent=a.cancel_fee_percent if a.refundable else 100, subtotal=Decimal(p["subtotal"]), discount=Decimal(p["discount"]),
        offer_title=p["offer"] or "", tax=Decimal(p["tax"]), total=Decimal(p["total"]), idempotency_key=data["idempotency_key"],
        hold_expires_at=timezone.now() + timedelta(minutes=HOLD_MINUTES))
    _event(b, S.PENDING_PAYMENT, "Places held")
    if b.total == 0:
        b.payment_status = ExperienceBooking.PaymentStatus.FREE
        b.save(update_fields=["payment_status", "updated_at"])
        return _confirm(b, f"Confirmed · {when} · no payment needed"), True, ""
    error = ""
    try:
        with transaction.atomic():
            b = pay(b)
    except DomainError as e:
        error = str(e.detail)
        _note(b, "Payment wasn’t completed", f"Your places are held for {HOLD_MINUTES} minutes. Retry the payment to confirm.")
    return b, True, error


def _confirm(b: ExperienceBooking, note: str) -> ExperienceBooking:
    b.status, b.confirmed_at, b.hold_expires_at, b.entry_code = S.CONFIRMED, timezone.now(), None, entry_code()
    b.save(update_fields=["status", "confirmed_at", "hold_expires_at", "entry_code", "updated_at"])
    _event(b, S.CONFIRMED, note)
    when = f"{b.visit_date:%a %d %b}" + (f", {b.slot_time:%I:%M %p}" if b.slot_time else "")
    _note(b, "Booking confirmed", f"{b.title}, {when}. Show entry code {b.entry_code} at the entrance.")
    record(b.customer, "experience.booked", {"title": b.title, "number": b.number, "kind": b.attraction.kind}, obj=b)
    return b


@transaction.atomic
def pay(b: ExperienceBooking) -> ExperienceBooking:
    from apps.payments.models import Payment, PaymentMethod
    from apps.wallet import services as wallet

    b = ExperienceBooking.objects.select_for_update().select_related("customer", "attraction").get(pk=b.pk)
    if b.status != S.PENDING_PAYMENT or b.payment_status != ExperienceBooking.PaymentStatus.PENDING:
        raise ConflictError("There’s nothing to pay on this booking.", code="not_payable")
    if b.hold_expires_at and b.hold_expires_at <= timezone.now():
        raise ConflictError("The hold on these places expired. Choose a slot again.", code="hold_expired")
    payment = Payment.objects.create(experience_booking=b, method=PaymentMethod.WALLET, amount=b.total, currency=b.currency)
    wallet.pay(b.customer, b.total, payment, f"Booking {b.number}")
    payment.status = Payment.Status.CAPTURED
    payment.save(update_fields=["status", "updated_at"])
    b.payment_status = ExperienceBooking.PaymentStatus.PAID
    b.save(update_fields=["payment_status", "updated_at"])
    return _confirm(b, f"Paid ₹{b.total:,.2f} from Click. Wallet")


def expire_holds() -> int:
    n = 0
    for b in ExperienceBooking.objects.filter(status=S.PENDING_PAYMENT, hold_expires_at__lte=timezone.now()):
        b.status, b.payment_status = S.FAILED, ExperienceBooking.PaymentStatus.NOT_CHARGED
        b.save(update_fields=["status", "payment_status", "updated_at"])
        _event(b, S.FAILED, "Payment wasn’t completed in time; places released")
        _note(b, "Booking not completed", "Payment wasn’t completed, so the places were released. Nothing was charged.")
        n += 1
    return n


def complete_past() -> int:
    from apps.rewards.services import award_points

    n = 0
    for b in ExperienceBooking.objects.filter(status=S.CONFIRMED, visit_date__lt=today()).select_related("customer"):
        b.status = S.COMPLETED
        b.save(update_fields=["status", "updated_at"])
        _event(b, S.COMPLETED, "Visit completed")
        if b.subtotal:
            award_points(b.customer, b.subtotal - b.discount, f"experience:{b.id}", f"Booking {b.number}")
        n += 1
    return n


def sweep() -> None:
    expire_holds()
    complete_past()


def cancellation(b: ExperienceBooking) -> dict:
    if b.status not in ACTIVE:
        return {"allowed": False, "fee": None, "refund": None, "note": "This booking can’t be cancelled."}
    start = starts_at(b.visit_date, b.slot_time, b.attraction)
    if timezone.now() >= start:
        return {"allowed": False, "fee": None, "refund": None, "note": "The visit has started. Contact support for help."}
    if b.status == S.PENDING_PAYMENT or b.payment_status == ExperienceBooking.PaymentStatus.FREE:
        return {"allowed": True, "fee": "0.00", "refund": "0.00", "note": "Nothing was charged, so cancelling costs nothing and frees the places."}
    if b.refundable and b.free_cancel_until and timezone.now() < b.free_cancel_until:
        fee = Decimal("0")
    else:
        fee = money(b.total * (b.cancel_fee_percent if b.refundable else 100) / 100)
    refund = money(b.total - fee)
    note = (f"Free cancellation: ₹{refund:,.2f} back to your Click. Wallet." if fee == 0 else
            "No refund under this booking’s policy." if refund == 0 else
            f"₹{fee:,.2f} is kept under the policy; ₹{refund:,.2f} goes back to your Click. Wallet.")
    return {"allowed": True, "fee": f"{fee:.2f}", "refund": f"{refund:.2f}", "note": note, "refund_to": "Click. Wallet"}


@transaction.atomic
def cancel(b: ExperienceBooking, reason: str) -> ExperienceBooking:
    from apps.payments.models import Payment
    from apps.wallet import services as wallet

    b = ExperienceBooking.objects.select_for_update().select_related("customer", "attraction").get(pk=b.pk)
    c = cancellation(b)
    if not c["allowed"]:
        raise ConflictError(c["note"], code="not_cancellable")
    refund = Decimal(c["refund"] or "0")
    if refund > 0:
        payment = b.payments.filter(status=Payment.Status.CAPTURED).first()
        if payment is None:
            raise ConflictError("The payment for this booking wasn’t found. Contact support.", code="payment_missing")
        wallet.refund(b.customer, refund, payment, f"Booking {b.number} cancelled")
        full = refund == b.total
        if full:
            payment.status = Payment.Status.REFUNDED
            payment.save(update_fields=["status", "updated_at"])
        b.refunded = refund
        b.payment_status = ExperienceBooking.PaymentStatus.REFUNDED if full else ExperienceBooking.PaymentStatus.PARTLY_REFUNDED
    elif b.payment_status == ExperienceBooking.PaymentStatus.PENDING:
        b.payment_status = ExperienceBooking.PaymentStatus.NOT_CHARGED
    b.status, b.cancelled_at, b.cancel_reason, b.hold_expires_at = S.CANCELLED, timezone.now(), reason[:200], None
    b.save(update_fields=["status", "cancelled_at", "cancel_reason", "refunded", "payment_status", "hold_expires_at", "updated_at"])
    _event(b, S.CANCELLED, reason)
    _note(b, "Booking cancelled", c["note"])
    record(b.customer, "experience.cancelled", {"title": b.title, "number": b.number, "refund": c["refund"]}, obj=b)
    return b


@transaction.atomic
def check_in(provider, code: str) -> ExperienceBooking:
    """The provider verifies an entry code (Partner App): it must be theirs, for today, confirmed and unused."""
    b = (ExperienceBooking.objects.select_for_update().select_related("attraction", "customer")
         .filter(attraction__provider=provider, entry_code=code.strip().upper()).first())
    if b is None:
        raise DomainError("No booking with that entry code at your place.", code="not_found", status_code=404)
    if b.status != S.CONFIRMED:
        raise ConflictError(f"This booking is {b.get_status_display().lower()}.", code="invalid_state")
    if b.visit_date != today():
        raise ConflictError(f"This booking is for {b.visit_date:%d %b}.", code="wrong_date")
    if b.checked_in_at:
        raise ConflictError(f"Already used at {b.checked_in_at.astimezone(tz()):%I:%M %p}.", code="already_used")
    b.checked_in_at = timezone.now()
    b.save(update_fields=["checked_in_at", "updated_at"])
    _note(b, "Entry verified", f"Enjoy your visit to {b.attraction.name}.")
    return b


@transaction.atomic
def review(customer, b: ExperienceBooking, rating: int, comment: str) -> ExperienceReview:
    if b.customer_id != customer.id:
        raise DomainError("Not found.", code="not_found", status_code=404)
    if b.status != S.COMPLETED:
        raise ConflictError("You can review after your visit.", code="review_not_allowed")
    if ExperienceReview.objects.filter(booking=b).exists():
        raise ConflictError("You’ve already reviewed this visit.", code="review_exists")
    r = ExperienceReview.objects.create(booking=b, customer=customer, attraction=b.attraction, rating=rating, comment=comment.strip()[:2000])
    agg = ExperienceReview.objects.filter(attraction=b.attraction, is_published=True).aggregate(a=Avg("rating"), n=Count("id"))
    Attraction.objects.filter(pk=b.attraction_id).update(rating_average=Decimal(str(round(agg["a"] or 0, 1))), rating_count=agg["n"])
    return r
