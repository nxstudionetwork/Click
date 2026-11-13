"""
Travel tickets. Every step runs on the server, under a lock on the service, with a status event and a notification:

  review    prepare(): the segment, class, seats / passengers and fare re-checked now — availability (seat free, berth
            / RAC / waitlist status per passenger), passenger rules, offer, tax, policy and the points it will earn
  book      must match the total the customer reviewed (`price_changed` → "Fare updated", confirm again), is
            idempotent, and allocates seats / berths in one transaction (a bus seat can't be sold twice: unique
            constraint). Paid from the Click. Wallet in the same transaction; if payment fails, the seats are held for
            10 minutes as "payment pending" for a retry, then released — no ticket is issued without payment
  cancel    by the tiers agreed at booking (hours before departure → % kept), refund to the wallet; a cancelled train
            berth goes to the first RAC passenger, and an RAC place to the first on the waitlist
  operator  a delay, platform / gate notice or a cancellation by the operator notifies every traveller; an operator
            cancellation refunds in full
  complete  after arrival; Click. Rewards points are earned on the fare of completed journeys
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.activity.services import record
from apps.core.api.exceptions import ConflictError, DomainError
from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify

from . import engine
from .models import (ACTIVE, BookingStatus as S, FareClass, Journey, Mode, Operator, Passenger, SavedTraveller, Service, StatusEvent, Stop,
                     TravelBooking, TripRating, pnr)

BERTHS = {"SL": ("S", 72, ["LB", "MB", "UB", "LB", "MB", "UB", "SL", "SU"]), "3A": ("B", 64, ["LB", "MB", "UB", "LB", "MB", "UB", "SL", "SU"]),
          "2A": ("A", 46, ["LB", "UB", "LB", "UB", "SL", "SU"]), "1A": ("H", 24, ["LB", "UB", "LB", "UB"]),
          "CC": ("C", 78, ["W", "M", "A", "A", "M", "W"]), "EC": ("E", 56, ["W", "A", "A", "W"])}
BERTH_NAMES = {"LB": "Lower", "MB": "Middle", "UB": "Upper", "SL": "Side lower", "SU": "Side upper", "W": "Window", "M": "Middle", "A": "Aisle"}
TICKET_WORD = {"bus": "bus ticket", "train": "train ticket", "flight": "flight"}


def _note(b: TravelBooking, title: str, body: str) -> None:
    notify(b.customer, NotificationCategory.BOOKINGS, f"{title} · {b.number}"[:120], body[:300], f"/travel/bookings/{b.id}")


def _event(b: TravelBooking, to: str, note: str = "") -> None:
    StatusEvent.objects.create(booking=b, to=to, note=note[:200])


def _resolve(data) -> tuple[Journey, Stop, Stop, Service]:
    j = Journey.objects.select_related("service__operator").filter(pk=data["journey_id"]).first()
    if j is None or not j.service.is_active or j.service.operator.status != "active":
        raise DomainError("This journey is no longer available. Refresh the results.", code="journey_unavailable", status_code=404)
    stops = {s.id: s for s in j.service.stops.select_related("place__city")}
    a, b = stops.get(data["from_stop_id"]), stops.get(data["to_stop_id"])
    if a is None or b is None or a.seq >= b.seq or not a.boarding or not b.dropping or not a.depart or not b.arrive:
        raise DomainError("Choose a valid boarding and dropping point for this journey.", code="invalid_segment")
    return j, a, b, j.service


def _berth_label(code: str, n: int) -> tuple[str, str]:
    prefix, per_coach, pattern = BERTHS.get(code, ("D", 80, ["W", "A"]))
    coach, berth = n // per_coach + 1, n % per_coach + 1
    return f"{prefix}{coach}-{berth}", pattern[(berth - 1) % len(pattern)]


def _train_plan(fc: FareClass, j: Journey, pax: list) -> list[dict]:
    """Predicts each passenger's status in order: confirmed berth (preference honoured if free), else RAC, else WL."""
    held = list(Passenger.objects.filter(journey=j, fare_class=fc, holds_seat=True, booking__status__in=ACTIVE).values_list("seat_status", "seat"))
    used = {s for st, s in held if st == "CNF"}
    cnf = sum(1 for st, _ in held if st == "CNF")
    rac = sum(1 for st, _ in held if st == "RAC")
    wl = sum(1 for st, _ in held if st == "WL")
    free = [n for n in range(fc.capacity) if _berth_label(fc.code, n)[0] not in used]
    out = []
    for p in pax:
        if cnf < fc.capacity and free:
            pref = p.get("berth_preference") or ""
            pick = next((n for n in free if _berth_label(fc.code, n)[1] == pref), free[0]) if pref else free[0]
            if not pref and p.get("age", 30) >= 60:  # seniors get a lower berth when one is free
                pick = next((n for n in free if _berth_label(fc.code, n)[1] in ("LB", "SL")), pick)
            free.remove(pick)
            seat, kind = _berth_label(fc.code, pick)
            cnf += 1
            out.append({"status": "CNF", "seat": seat, "berth": BERTH_NAMES.get(kind, kind), "queue": 0})
        elif rac < fc.rac_capacity:
            rac += 1
            out.append({"status": "RAC", "seat": "", "berth": "", "queue": rac})
        elif wl < fc.waitlist_limit:
            wl += 1
            out.append({"status": "WL", "seat": "", "berth": "", "queue": wl})
        else:
            out.append({"status": "NA", "seat": "", "berth": "", "queue": 0})
    return out


def _check_passengers(mode: str, pax: list, infants: int) -> str:
    if not pax:
        return "Add at least one passenger."
    if len(pax) > engine.MAX_PASSENGERS[mode]:
        return f"Up to {engine.MAX_PASSENGERS[mode]} passengers per booking."
    adults = [p for p in pax if p["age"] >= 12]
    if not adults:
        return "At least one passenger must be 12 or older."
    if mode == Mode.FLIGHT and infants > len(adults):
        return "Each infant must travel with an adult."
    if mode != Mode.FLIGHT and infants:
        return "Infants aren’t booked separately on this mode."
    for p in pax:
        if p["age"] < engine.CHILD_MIN_AGE[mode]:
            return (f"Children under {engine.CHILD_MIN_AGE[mode]} don’t need a ticket"
                    + (" — add them as an infant." if mode == Mode.FLIGHT else " and travel on an adult’s seat."))
    return ""


def prepare(data: dict) -> dict:
    j, a, b, service = _resolve(data)
    pax = data["passengers"]
    infants = data.get("infants") or 0
    fc = service.classes.filter(code=data["class_code"]).first()
    if fc is None:
        raise DomainError("That class isn’t sold on this journey.", code="invalid_class")
    dep, arr = engine.at(j.date, a, "depart"), engine.at(j.date, b, "arrive")
    problem = _check_passengers(service.mode, pax, infants)
    if j.status == Journey.Status.CANCELLED:
        problem = "The operator cancelled this journey."
    elif dep < timezone.now() + timedelta(minutes=engine.CUTOFF_MINUTES[service.mode]):
        problem = problem or "Booking for this departure has closed."
    plan, seat_fares = [], None
    if service.mode == Mode.BUS:
        seats = data.get("seats") or []
        layout = engine.bus_seats(service)
        sold = engine.sold_seats(j)
        if len(seats) != len(pax) or len(set(seats)) != len(seats):
            problem = problem or "Choose one seat for each passenger."
        seat_fares = []
        for i, s in enumerate(seats):
            info = layout.get(s)
            if info is None:
                problem = problem or f"Seat {s} doesn’t exist on this bus."
                continue
            if s in sold:
                problem = problem or f"Seat {s} was just booked by someone else. Choose another seat."
            if info.get("ladies") and i < len(pax) and pax[i]["gender"] != "female":
                problem = problem or f"Seat {s} is reserved for women."
            if info.get("gents") and i < len(pax) and pax[i]["gender"] != "male":
                problem = problem or f"Seat {s} is reserved for men."
            sfc = service.classes.filter(code=info.get("class")).first() or fc
            seat_fares.append(engine.unit_fare(sfc, j, a, b)[0])
            plan.append({"status": "CNF", "seat": s, "berth": sfc.name, "queue": 0})
        if len(seat_fares) != len(pax):
            seat_fares = None
    elif service.mode == Mode.TRAIN:
        plan = _train_plan(fc, j, pax)
        if any(p["status"] == "NA" for p in plan):
            problem = problem or "Not enough berths, RAC or waitlist places left in this class."
    else:
        av = engine.availability(fc, j)
        if av.status == "not_available" or av.count < len(pax):
            problem = problem or ("Sold out in this cabin." if av.status == "not_available" else f"Only {av.count} seats left in this cabin.")
        plan = [{"status": "CNF", "seat": "", "berth": "Seat at check-in", "queue": 0} for _ in pax]
    q = engine.quote(fc, j, a, b, len(pax), infants, data.get("coupon") or "", seat_fares)
    from apps.rewards.services import points_for_amount

    return {
        "journey": {"journey_id": str(j.id), "mode": service.mode, "operator": service.operator.name, "number": service.number, "name": service.name,
                    "vehicle": service.vehicle, "class_code": fc.code, "class_name": fc.name, "fare_type": fc.fare_type,
                    "from": f"{a.place.name}", "from_city": a.place.city_place.name, "to": f"{b.place.name}", "to_city": b.place.city_place.name,
                    "departs_at": dep.isoformat(), "arrives_at": arr.isoformat(), "duration_minutes": engine.duration_minutes(dep, arr),
                    "baggage": service.baggage or None, "status": j.status, "notice": j.notice},
        "passengers": [{**{k: p.get(k) for k in ("name", "age", "gender", "berth_preference")}, **plan[i]} if i < len(plan) else p
                       for i, p in enumerate(pax)],
        "infants": infants, **q.as_dict(), "refundable": fc.refundable, "policy": engine.policy_text(fc.refundable, service.cancellation),
        "change_fee": f"{fc.change_fee:.2f}" if fc.change_fee is not None else None,
        "points": points_for_amount(q.base) if q.base else 0, "hold_minutes": engine.HOLD_MINUTES,
        "bookable": not problem, "problem": problem,
        "status_note": ("Some passengers are on RAC / waitlist: their status updates if berths free up before the chart is prepared."
                        if any(p["status"] in ("RAC", "WL") for p in plan) else ""),
    }


@transaction.atomic
def book(customer, data: dict) -> tuple[TravelBooking, bool, str]:
    existing = TravelBooking.objects.filter(customer=customer, idempotency_key=data["idempotency_key"]).first()
    if existing:
        return existing, False, ""
    j, a, b, service = _resolve(data)
    Service.objects.select_for_update().get(pk=service.pk)  # one sale at a time per service: no double-sold seat or berth
    p = prepare(data)
    if not p["bookable"]:
        raise ConflictError(p["problem"], code="not_available", details={"review": p})
    if data.get("expected_total") is not None and Decimal(str(data["expected_total"])) != Decimal(p["total"]):
        raise ConflictError("The fare changed. Review the new total.", code="price_changed", details={"review": p, "previous": f"{Decimal(str(data['expected_total'])):.2f}"})
    fc = service.classes.get(code=data["class_code"])
    pax = data["passengers"]
    bk = TravelBooking.objects.create(
        customer=customer, mode=service.mode, journey=j, fare_class=fc, from_stop=a, to_stop=b,
        departs_at=engine.at(j.date, a, "depart"), arrives_at=engine.at(j.date, b, "arrive"),
        adults=sum(1 for x in pax if x["age"] >= 12), children=sum(1 for x in pax if x["age"] < 12), infants=p["infants"],
        contact_phone=data["contact_phone"].strip(), contact_email=data.get("contact_email") or "",
        operator_name=service.operator.name, service_label=f"{service.number} {service.name}".strip(), class_name=fc.name,
        from_label=a.place.label, to_label=b.place.label, refundable=fc.refundable, cancellation_rules=service.cancellation,
        base_fare=Decimal(p["base_fare"]), fees=Decimal(p["fees"]), discount=Decimal(p["discount"]), offer_title=p["offer"] or "",
        tax=Decimal(p["tax"]), total=Decimal(p["total"]), idempotency_key=data["idempotency_key"], trip_ref=data.get("trip_ref") or "",
        hold_expires_at=timezone.now() + timedelta(minutes=engine.HOLD_MINUTES))
    layout = engine.bus_seats(service)
    classes = {c.code: c for c in service.classes.all()}
    unit = Decimal(p["unit_fare"])
    try:
        with transaction.atomic():
            for i, (x, plan) in enumerate(zip(pax, p["passengers"])):
                seat_fc = classes.get(layout.get(plan["seat"], {}).get("class"), fc) if service.mode == Mode.BUS else fc
                Passenger.objects.create(booking=bk, journey=j, fare_class=seat_fc, position=i + 1, name=x["name"].strip()[:80], age=x["age"],
                                         gender=x["gender"], berth_preference=x.get("berth_preference") or "", seat=plan["seat"],
                                         seat_status=plan["status"], queue=plan["queue"],
                                         fare=engine.unit_fare(seat_fc, j, a, b)[0] if service.mode == Mode.BUS else unit)
    except IntegrityError:
        raise ConflictError("A seat you chose was just booked. Choose another seat.", code="seat_taken", details={"review": prepare(data)})
    if data.get("save_travellers"):
        for x in pax:
            SavedTraveller.objects.update_or_create(customer=customer, name=x["name"].strip()[:80],
                                                    defaults={"age": x["age"], "gender": x["gender"], "berth_preference": x.get("berth_preference") or ""})
    _event(bk, S.PENDING_PAYMENT, "Seats held for payment")
    error = ""
    try:
        with transaction.atomic():
            bk = pay(bk)
    except DomainError as e:  # e.g. wallet balance short: seats stay held for a retry
        error = str(e.detail)
        _note(bk, "Payment wasn’t completed", f"Your seats are held for {engine.HOLD_MINUTES} minutes. Retry the payment to get your ticket.")
    return bk, True, error


@transaction.atomic
def pay(bk: TravelBooking) -> TravelBooking:
    from apps.payments.models import Payment, PaymentMethod
    from apps.wallet import services as wallet

    bk = TravelBooking.objects.select_for_update().select_related("customer").get(pk=bk.pk)
    if bk.status != S.PENDING_PAYMENT or bk.payment_status != TravelBooking.PaymentStatus.PENDING:
        raise ConflictError("There’s nothing to pay on this booking.", code="not_payable")
    if bk.hold_expires_at and bk.hold_expires_at <= timezone.now():
        raise ConflictError("The hold on these seats expired. Search again to book.", code="hold_expired")
    payment = Payment.objects.create(travel_booking=bk, method=PaymentMethod.WALLET, amount=bk.total, currency=bk.currency)
    wallet.pay(bk.customer, bk.total, payment, f"Travel booking {bk.number}")  # raises if the balance is short (rolls back)
    payment.status = Payment.Status.CAPTURED
    payment.save(update_fields=["status", "updated_at"])
    bk.payment_status = TravelBooking.PaymentStatus.PAID
    bk.status, bk.confirmed_at, bk.hold_expires_at, bk.pnr = S.CONFIRMED, timezone.now(), None, pnr()
    bk.save(update_fields=["payment_status", "status", "confirmed_at", "hold_expires_at", "pnr", "updated_at"])
    _event(bk, S.CONFIRMED, f"Paid ₹{bk.total:,.2f} from Click. Wallet · ticket issued")
    title = {"bus": "Your bus booking is confirmed", "train": "Your train ticket is ready", "flight": "Your flight is booked"}[bk.mode]
    _note(bk, title, f"{bk.from_label.split(' — ')[0]} → {bk.to_label.split(' — ')[0]}, {bk.departs_at.astimezone(engine.tz()):%d %b, %H:%M}. PNR {bk.pnr}.")
    record(bk.customer, "travel.booked", {"mode": bk.mode, "number": bk.number, "total": f"{bk.total:.2f}"}, obj=bk)
    return bk


def _release(bk: TravelBooking) -> None:
    bk.passengers.update(holds_seat=False)


def expire_holds() -> int:
    n = 0
    for bk in TravelBooking.objects.filter(status=S.PENDING_PAYMENT, hold_expires_at__lte=timezone.now()):
        with transaction.atomic():
            bk.status, bk.payment_status = S.FAILED, TravelBooking.PaymentStatus.NOT_CHARGED
            bk.save(update_fields=["status", "payment_status", "updated_at"])
            _release(bk)
            _event(bk, S.FAILED, "Payment wasn’t completed in time; seats released")
        _note(bk, "Booking not completed", "Payment wasn’t completed, so the seats were released. Nothing was charged.")
        n += 1
    return n


def complete_past() -> int:
    from apps.rewards.services import award_points

    n = 0
    for bk in TravelBooking.objects.filter(status=S.CONFIRMED, arrives_at__lte=timezone.now()).select_related("customer"):
        bk.status = S.COMPLETED
        bk.save(update_fields=["status", "updated_at"])
        _event(bk, S.COMPLETED, "Journey completed")
        award_points(bk.customer, bk.base_fare, f"travel:{bk.id}", f"Travel {bk.number}", service="travel")
        n += 1
    return n


def send_reminders() -> int:
    now = timezone.now()
    n = 0
    for bk in TravelBooking.objects.filter(status=S.CONFIRMED, reminded_at__isnull=True, departs_at__gt=now, departs_at__lte=now + timedelta(hours=24)):
        word = {"bus": "bus", "train": "train", "flight": "flight"}[bk.mode]
        _note(bk, f"Your {word} leaves soon", f"{bk.service_label} departs {bk.departs_at.astimezone(engine.tz()):%a %d %b, %H:%M} from {bk.from_label}.")
        TravelBooking.objects.filter(pk=bk.pk).update(reminded_at=now)
        n += 1
    return n


def sweep() -> None:
    expire_holds()
    complete_past()
    send_reminders()


def cancellation(bk: TravelBooking) -> dict:
    if bk.status not in ACTIVE:
        return {"allowed": False, "fee": None, "refund": None, "fee_percent": None, "note": "This booking can’t be cancelled."}
    if timezone.now() >= bk.departs_at:
        return {"allowed": False, "fee": None, "refund": None, "fee_percent": None, "note": "Departure time has passed. Contact support."}
    if bk.status == S.PENDING_PAYMENT:
        return {"allowed": True, "fee": "0.00", "refund": "0.00", "fee_percent": 0, "note": "Nothing has been charged, so cancelling costs nothing."}
    if bk.mode == Mode.TRAIN and not bk.passengers.exclude(seat_status__in=["WL", "CAN"]).exists():
        pct = 0  # a fully waitlisted ticket never got a berth
    else:
        pct = engine.cancel_fee_percent(bk.refundable, bk.cancellation_rules, bk.departs_at)
    fee = engine.money(bk.total * pct / 100)
    refund = engine.money(bk.total - fee)
    note = (f"Full refund: ₹{refund:,.2f} back to your Click. Wallet." if fee == 0 else
            "No refund under this fare’s rules." if refund == 0 else
            f"Cancellation fee ₹{fee:,.2f} ({pct}%); ₹{refund:,.2f} goes back to your Click. Wallet.")
    return {"allowed": True, "fee": f"{fee:.2f}", "refund": f"{refund:.2f}", "fee_percent": pct, "note": note, "refund_to": "Click. Wallet"}


def _refund(bk: TravelBooking, amount: Decimal, why: str) -> None:
    from apps.payments.models import Payment
    from apps.wallet import services as wallet

    payment = bk.payments.filter(status=Payment.Status.CAPTURED).first()
    if payment is None:
        raise ConflictError("The payment for this booking wasn’t found. Contact support.", code="payment_missing")
    wallet.refund(bk.customer, amount, payment, why)  # credited to the wallet immediately
    full = amount == bk.total
    if full:
        payment.status = Payment.Status.REFUNDED
        payment.save(update_fields=["status", "updated_at"])
    bk.refunded = amount
    bk.payment_status = TravelBooking.PaymentStatus.REFUNDED if full else TravelBooking.PaymentStatus.PARTLY_REFUNDED


def _promote(j: Journey, fc: FareClass) -> None:
    """Freed berths go to RAC in order; freed RAC places to the waitlist in order."""
    while True:
        held = Passenger.objects.filter(journey=j, fare_class=fc, holds_seat=True, booking__status__in=ACTIVE)
        cnf = held.filter(seat_status="CNF").count()
        nxt = held.filter(seat_status="RAC").order_by("queue", "created_at").first() if cnf < fc.capacity else None
        if nxt is None:
            break
        plan = _train_plan(fc, j, [{"berth_preference": nxt.berth_preference, "age": nxt.age}])[0]
        if plan["status"] != "CNF":
            break
        nxt.seat_status, nxt.seat, nxt.queue = "CNF", plan["seat"], 0
        nxt.save(update_fields=["seat_status", "seat", "queue", "updated_at"])
        _note(nxt.booking, "Your berth is confirmed", f"{nxt.name}: {plan['seat']} ({plan['berth']}).")
    rac = Passenger.objects.filter(journey=j, fare_class=fc, holds_seat=True, booking__status__in=ACTIVE, seat_status="RAC").count()
    for w in Passenger.objects.filter(journey=j, fare_class=fc, holds_seat=True, booking__status__in=ACTIVE, seat_status="WL").order_by("queue", "created_at"):
        if rac >= fc.rac_capacity:
            break
        rac += 1
        w.seat_status, w.queue = "RAC", rac
        w.save(update_fields=["seat_status", "queue", "updated_at"])
        _note(w.booking, "Your ticket moved to RAC", f"{w.name}: RAC {rac}. You can board; a berth may still be confirmed.")


@transaction.atomic
def cancel(bk: TravelBooking, reason: str) -> TravelBooking:
    bk = TravelBooking.objects.select_for_update().select_related("customer").get(pk=bk.pk)
    c = cancellation(bk)
    if not c["allowed"]:
        raise ConflictError(c["note"], code="not_cancellable")
    Service.objects.select_for_update().get(pk=bk.journey.service_id)
    refund = Decimal(c["refund"] or "0")
    if refund > 0:
        _refund(bk, refund, f"Travel booking {bk.number} cancelled")
    elif bk.payment_status == TravelBooking.PaymentStatus.PENDING:
        bk.payment_status = TravelBooking.PaymentStatus.NOT_CHARGED
    bk.status, bk.cancelled_at, bk.cancel_reason, bk.hold_expires_at = S.CANCELLED, timezone.now(), reason[:200], None
    bk.save(update_fields=["status", "cancelled_at", "cancel_reason", "refunded", "payment_status", "hold_expires_at", "updated_at"])
    bk.passengers.update(holds_seat=False, seat_status="CAN")
    _event(bk, S.CANCELLED, reason)
    _note(bk, "Your booking was cancelled", c["note"])
    record(bk.customer, "travel.cancelled", {"mode": bk.mode, "number": bk.number, "refund": c["refund"]}, obj=bk)
    if bk.mode == Mode.TRAIN:
        _promote(bk.journey, bk.fare_class)
    return bk


@transaction.atomic
def operator_update(j: Journey, status: str, delay_minutes: int = 0, notice: str = "") -> int:
    """An operator's change to a run: every traveller is told; an operator cancellation refunds in full."""
    j = Journey.objects.select_for_update().get(pk=j.pk)
    j.status, j.delay_minutes, j.notice = status, delay_minutes, notice[:160]
    j.save(update_fields=["status", "delay_minutes", "notice", "updated_at"])
    n = 0
    for bk in TravelBooking.objects.select_for_update().filter(journey=j, status__in=ACTIVE).select_related("customer"):
        n += 1
        if status == Journey.Status.CANCELLED:
            if bk.payment_status == TravelBooking.PaymentStatus.PAID:
                _refund(bk, bk.total, f"Travel booking {bk.number}: cancelled by the operator")
            else:
                bk.payment_status = TravelBooking.PaymentStatus.NOT_CHARGED
            bk.status, bk.cancelled_at, bk.cancel_reason, bk.hold_expires_at = S.CANCELLED, timezone.now(), "Cancelled by the operator", None
            bk.save(update_fields=["status", "cancelled_at", "cancel_reason", "refunded", "payment_status", "hold_expires_at", "updated_at"])
            bk.passengers.update(holds_seat=False, seat_status="CAN")
            _event(bk, S.CANCELLED, "Cancelled by the operator")
            _note(bk, "The operator cancelled your journey", f"{bk.service_label}: a full refund of ₹{bk.total:,.2f} is in your Click. Wallet.")
        elif delay_minutes:
            _note(bk, "Your departure time has changed", f"{bk.service_label} is running about {delay_minutes} minutes late." + (f" {notice}" if notice else ""))
        elif notice:
            _note(bk, "Boarding information updated", f"{bk.service_label}: {notice}")
    return n


@transaction.atomic
def rate(customer, bk: TravelBooking, rating: int, comment: str) -> TripRating:
    from django.db.models import Avg, Count

    if bk.customer_id != customer.id:
        raise DomainError("Not found.", code="not_found", status_code=404)
    if bk.status != S.COMPLETED:
        raise ConflictError("You can rate the journey after you travel.", code="rating_not_allowed")
    if TripRating.objects.filter(booking=bk).exists():
        raise ConflictError("You’ve already rated this journey.", code="rating_exists")
    op = bk.journey.service.operator
    r = TripRating.objects.create(booking=bk, customer=customer, operator=op, rating=rating, comment=comment.strip()[:1000])
    agg = TripRating.objects.filter(operator=op).aggregate(a=Avg("rating"), n=Count("id"))
    Operator.objects.filter(pk=op.pk).update(rating_average=Decimal(str(round(agg["a"] or 0, 1))), rating_count=agg["n"])
    return r
