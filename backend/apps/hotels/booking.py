"""
Hotel reservations. Every step is validated here under a row lock, with a status event and a notification:

  review    prepare(): the room and rate re-priced on the server for the stay and party, with tax, offer and the
            cancellation policy that will apply — what the Review page shows
  book      the booking must match the total the customer reviewed (`price_changed`), is idempotent, and locks
            the room type so the last room can't be sold twice. Pay now: the room is held for 15 minutes as
            "pending payment" and paid from the Click. Wallet (verified on the server, in the same transaction);
            if payment fails the booking stays pending and can be retried until the hold expires, then it fails and
            the room is released. Pay at the property: confirmed straight away, nothing charged online.
  cancel    by the policy agreed at booking: free before the deadline (full refund to the wallet), a % kept after,
            non-refundable keeps all; pay-at-property bookings are never charged on cancellation
  complete  confirmed stays become completed after check-out (on reads and by the partner's check-out)
  review    only the guest of a completed stay, once; property ratings are recomputed from published reviews
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Count
from django.utils import timezone

from apps.core.api.exceptions import ConflictError, DomainError
from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify

from . import engine
from .models import BookingStatus as S, HotelBooking, HotelProperty, HotelReview, RatePlan, RoomType, StatusEvent


def _note(b: HotelBooking, title: str, body: str) -> None:
    notify(b.customer, NotificationCategory.BOOKINGS, f"{title} · {b.number}"[:150], body[:200], f"/hotels/bookings/{b.id}")


def _event(b: HotelBooking, to: str, note: str = "") -> None:
    StatusEvent.objects.create(booking=b, to=to, note=note[:200])


def _rate(data) -> RatePlan:
    rate = (RatePlan.objects.select_related("room_type__property__partner", "room_type__property__destination")
            .filter(pk=data["rate_id"], is_active=True, room_type__is_active=True, room_type__property__is_listed=True).first())
    if rate is None:
        raise DomainError("That room isn’t available any more.", code="room_unavailable", status_code=404)
    return rate


def prepare(data: dict) -> dict:
    rate = _rate(data)
    prop, room = rate.room_type.property, rate.room_type
    ci, co = data["check_in"], data["check_out"]
    problem = engine.validate_stay(ci, co, data["rooms"], data["adults"], data["children"])
    q = engine.quote(rate, ci, co, data["rooms"], data["adults"], data["children"], data.get("coupon", ""))
    problem = problem or q.problem
    return {
        "property": {"id": str(prop.id), "name": prop.partner.business_name, "address": prop.address, "type_label": prop.get_property_type_display(),
                     "check_in_time": prop.check_in_time.strftime("%H:%M"), "check_out_time": prop.check_out_time.strftime("%H:%M"),
                     "policies": prop.policies, "star_rating": prop.star_rating},
        "room": {"id": str(room.id), "name": room.name, "beds": room.beds, "max_adults": room.max_adults, "max_children": room.max_children},
        "stay": {"check_in": ci.isoformat(), "check_out": co.isoformat(), "nights": (co - ci).days, "rooms": data["rooms"],
                 "adults": data["adults"], "children": data["children"]},
        **q.as_dict(), "bookable": not problem, "problem": problem, "hold_minutes": engine.HOLD_MINUTES,
        "tax_note": "GST on hotel stays: 12% for nightly tariffs up to ₹7,500, 18% above, none below ₹1,000.",
    }


@transaction.atomic
def book(customer, data: dict) -> tuple[HotelBooking, bool, str]:
    existing = HotelBooking.objects.filter(customer=customer, idempotency_key=data["idempotency_key"]).first()
    if existing:
        return existing, False, ""
    rate = _rate(data)
    RoomType.objects.select_for_update().get(pk=rate.room_type_id)  # one sale at a time per room type
    p = prepare(data)
    if not p["bookable"]:
        raise ConflictError(p["problem"], code="room_unavailable" if "left" in p["problem"] or "Sold out" in p["problem"] else "not_bookable",
                            details={"review": p})
    if data.get("expected_total") is not None and Decimal(str(data["expected_total"])) != Decimal(p["total"]):
        raise ConflictError("The price changed. Review the new total.", code="price_changed", details={"review": p})
    mode = data.get("payment_mode") or ("at_property" if rate.payment == RatePlan.Payment.AT_PROPERTY else "pay_now")
    allowed = {"pay_now": rate.payment in ("pay_now", "either"), "at_property": rate.payment in ("at_property", "either")}
    if not allowed.get(mode):
        raise DomainError("That payment option isn’t available for this rate.", code="payment_method_unavailable")
    prop = rate.room_type.property
    until = engine.free_cancel_until(rate, prop, data["check_in"])
    b = HotelBooking.objects.create(
        customer=customer, property=prop, room_type=rate.room_type, rate_plan=rate, check_in=data["check_in"], check_out=data["check_out"],
        nights=p["stay"]["nights"], rooms=data["rooms"], adults=data["adults"], children=data["children"],
        guest_name=data["guest_name"].strip(), guest_email=data.get("guest_email") or "", guest_phone=data["guest_phone"].strip(),
        other_guests=[n.strip()[:80] for n in data.get("other_guests") or [] if n.strip()][:10], special_requests=(data.get("special_requests") or "")[:500],
        payment_mode=mode, room_name=rate.room_type.name, rate_name=rate.name, meal_plan=rate.meal_plan, refundable=rate.refundable,
        free_cancel_until=until, cancel_fee_percent=rate.cancel_fee_percent if rate.refundable else 100, nightly=p["nightly"],
        room_total=Decimal(p["room_total"]), discount=Decimal(p["discount"]), offer_title=p["offer"] or "", tax=Decimal(p["tax"]),
        total=Decimal(p["total"]), idempotency_key=data["idempotency_key"], hold_expires_at=timezone.now() + timedelta(minutes=engine.HOLD_MINUTES))
    _event(b, S.PENDING_PAYMENT, "Room held")
    if mode == "at_property":
        b.payment_status = HotelBooking.PaymentStatus.AT_PROPERTY
        b.save(update_fields=["payment_status", "updated_at"])
        b = _confirm(b, "Confirmed · pay at the property")
        return b, True, ""
    error = ""
    try:
        with transaction.atomic():
            b = pay(b)
    except DomainError as e:  # e.g. not enough wallet balance: the booking stays held for a retry
        error = str(e.detail)
        _note(b, "Payment not completed", f"Your room is held for {engine.HOLD_MINUTES} minutes. Retry the payment to confirm.")
    return b, True, error


def _confirm(b: HotelBooking, note: str) -> HotelBooking:
    b.status, b.confirmed_at, b.hold_expires_at = S.CONFIRMED, timezone.now(), None
    b.save(update_fields=["status", "confirmed_at", "hold_expires_at", "updated_at"])
    _event(b, S.CONFIRMED, note)
    _note(b, "Hotel booked", f"{b.property.partner.business_name}, {b.check_in:%d %b} – {b.check_out:%d %b} ({b.nights} night{'s' if b.nights > 1 else ''}).")
    return b


@transaction.atomic
def pay(b: HotelBooking) -> HotelBooking:
    from apps.payments.models import Payment, PaymentMethod
    from apps.wallet import services as wallet

    b = HotelBooking.objects.select_for_update().select_related("property__partner", "customer").get(pk=b.pk)
    if b.status != S.PENDING_PAYMENT or b.payment_status != HotelBooking.PaymentStatus.PENDING:
        raise ConflictError("There’s nothing to pay on this booking.", code="not_payable")
    if b.hold_expires_at and b.hold_expires_at <= timezone.now():
        raise ConflictError("The hold on this room expired. Search again to book.", code="hold_expired")
    payment = Payment.objects.create(hotel_booking=b, method=PaymentMethod.WALLET, amount=b.total, currency=b.currency)
    wallet.pay(b.customer, b.total, payment, f"Hotel booking {b.number}")  # raises if the balance is short (rolls back)
    payment.status = Payment.Status.CAPTURED
    payment.save(update_fields=["status", "updated_at"])
    b.payment_status = HotelBooking.PaymentStatus.PAID
    b.save(update_fields=["payment_status", "updated_at"])
    return _confirm(b, f"Paid ₹{b.total:,.2f} from Click. Wallet")


def expire_holds() -> int:
    n = 0
    for b in HotelBooking.objects.filter(status=S.PENDING_PAYMENT, hold_expires_at__lte=timezone.now()):
        b.status, b.payment_status = S.FAILED, HotelBooking.PaymentStatus.NOT_CHARGED
        b.save(update_fields=["status", "payment_status", "updated_at"])
        _event(b, S.FAILED, "Payment wasn’t completed in time; room released")
        _note(b, "Booking not completed", "Payment wasn’t completed, so the room was released. Nothing was charged.")
        n += 1
    return n


def complete_past() -> int:
    n = 0
    for b in HotelBooking.objects.filter(status=S.CONFIRMED, check_out__lte=engine.today()).select_related("property__partner", "customer"):
        check_out(b, "Stay completed")
        n += 1
    return n


def check_out(b: HotelBooking, note: str = "Checked out") -> HotelBooking:
    with transaction.atomic():
        b = HotelBooking.objects.select_for_update().select_related("property__partner", "customer").get(pk=b.pk)
        if b.status != S.CONFIRMED:
            raise ConflictError("Only confirmed stays can be checked out.", code="invalid_transition")
        b.status = S.COMPLETED
        b.save(update_fields=["status", "updated_at"])
        _event(b, S.COMPLETED, note)
    _note(b, "Thanks for staying", f"How was {b.property.partner.business_name}? Leave a review for other travellers.")
    return b


def cancellation(b: HotelBooking) -> dict:
    """What cancelling now costs, from the policy agreed at booking."""
    if b.status not in (S.CONFIRMED, S.PENDING_PAYMENT):
        return {"allowed": False, "fee": None, "refund": None, "note": "This booking can’t be cancelled."}
    check_in_at = engine.datetime.combine(b.check_in, b.property.check_in_time, tzinfo=engine.tz())
    if timezone.now() >= check_in_at:
        return {"allowed": False, "fee": None, "refund": None, "note": "Check-in time has passed. Contact support for changes."}
    if b.status == S.PENDING_PAYMENT or b.payment_status == HotelBooking.PaymentStatus.AT_PROPERTY:
        return {"allowed": True, "fee": "0.00", "refund": None, "note": "Nothing has been charged online, so cancelling costs nothing on Click."
                + (" The property’s own no-show rules don’t apply once cancelled here." if b.payment_status == "at_property" else "")}
    if b.refundable and b.free_cancel_until and timezone.now() < b.free_cancel_until:
        fee = Decimal("0")
    else:
        fee = engine.money(b.total * (b.cancel_fee_percent if b.refundable else 100) / 100)
    refund = engine.money(b.total - fee)
    note = (f"Free cancellation: ₹{refund:,.2f} back to your Click. Wallet." if fee == 0 else
            "Non-refundable: nothing is refunded." if refund == 0 else
            f"₹{fee:,.2f} is kept under the policy; ₹{refund:,.2f} goes back to your Click. Wallet.")
    return {"allowed": True, "fee": f"{fee:.2f}", "refund": f"{refund:.2f}", "note": note}


@transaction.atomic
def cancel(b: HotelBooking, reason: str) -> HotelBooking:
    from apps.payments.models import Payment
    from apps.wallet import services as wallet

    b = HotelBooking.objects.select_for_update().select_related("property__partner", "customer").get(pk=b.pk)
    c = cancellation(b)
    if not c["allowed"]:
        raise ConflictError(c["note"], code="not_cancellable")
    refund = Decimal(c["refund"] or "0")
    if refund > 0:
        payment = b.payments.filter(status=Payment.Status.CAPTURED).first()
        if payment is None:
            raise ConflictError("The payment for this booking wasn’t found. Contact support.", code="payment_missing")
        wallet.refund(b.customer, refund, payment, f"Hotel booking {b.number} cancelled")  # credited immediately
        full = refund == b.total
        if full:
            payment.status = Payment.Status.REFUNDED
            payment.save(update_fields=["status", "updated_at"])
        b.refunded = refund
        b.payment_status = HotelBooking.PaymentStatus.REFUNDED if full else HotelBooking.PaymentStatus.PARTLY_REFUNDED
    elif b.payment_status == HotelBooking.PaymentStatus.PENDING:
        b.payment_status = HotelBooking.PaymentStatus.NOT_CHARGED
    b.status, b.cancelled_at, b.cancel_reason, b.hold_expires_at = S.CANCELLED, timezone.now(), reason[:200], None
    b.save(update_fields=["status", "cancelled_at", "cancel_reason", "refunded", "payment_status", "hold_expires_at", "updated_at"])
    _event(b, S.CANCELLED, reason)
    _note(b, "Booking cancelled", c["note"])
    return b


@transaction.atomic
def review(customer, b: HotelBooking, data: dict) -> HotelReview:
    if b.customer_id != customer.id:
        raise DomainError("Not found.", code="not_found", status_code=404)
    if b.status != S.COMPLETED:
        raise ConflictError("You can review after your stay.", code="review_not_allowed")
    if HotelReview.objects.filter(booking=b).exists():
        raise ConflictError("You’ve already reviewed this stay.", code="review_exists")
    r = HotelReview.objects.create(booking=b, customer=customer, property=b.property, **{k: data[k] for k in ("overall", *HotelReview.ASPECTS)},
                                   title=(data.get("title") or "").strip()[:120], comment=(data.get("comment") or "").strip(),
                                   traveller=data.get("traveller") or "")
    recompute(b.property)
    return r


def recompute(p: HotelProperty) -> None:
    agg = HotelReview.objects.filter(property=p, is_published=True).aggregate(a=Avg("overall"), n=Count("id"))
    HotelProperty.objects.filter(pk=p.pk).update(rating_average=Decimal(str(round(agg["a"] or 0, 1))), rating_count=agg["n"])
