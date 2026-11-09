"""
Showtime booking core: seat holds, server-side pricing (tickets, fees, food & drinks, offers, tax), booking creation
and cancellation. Every price and every seat state is decided here, never by the client.

  pick seats -> SeatHold (HOLD_MINUTES, seats unique per show) -> quote -> book (pay) -> BookedSeat (unique while active)

An expired hold is released the next time anyone holds or books seats for that show.
"""

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.activity.services import record
from apps.core.api.exceptions import ConflictError, DomainError
from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify
from apps.payments.services import settle_on_cancel, start_booking_payment

from .models import BookedSeat, Booking, BookingConcession, ConcessionItem, HeldSeat, SeatHold, Show, ShowOffer

audit = logging.getLogger("click.audit")
MAX_SEATS = 10
MAX_CONCESSION_QTY = 10
HOLD_MINUTES = 8
CONVENIENCE_FEE_PER_SEAT = Decimal("20.00")
CANCELLATION_CUTOFF = timedelta(hours=2)
TWO = Decimal("0.01")


def bookable_shows():
    return Show.objects.filter(status=Show.Status.SCHEDULED, starts_at__gt=timezone.now(),
                               event__status__in=["now_showing", "coming_soon"]).select_related("event", "venue", "screen_ref")


def _venue_open(show) -> None:
    # A venue operated through Click Partner can close bookings from Partner Home (unlinked venues are unaffected).
    from apps.partners.models import PartnerVenue

    link = PartnerVenue.objects.select_related("partner").filter(venue_id=show.venue_id).first()
    if link is not None and not link.partner.is_available:
        raise DomainError(f"{show.venue.name} isn’t taking bookings right now.", code="venue_closed", status_code=409)


def _locked_show(show_id) -> Show:
    try:
        return bookable_shows().select_for_update(of=("self",)).get(pk=show_id)
    except Show.DoesNotExist:
        raise DomainError("This showtime is no longer available for booking.", code="show_unavailable", status_code=404)


def release_expired(show) -> None:
    """Return seats from expired holds to sale. Call with the show row locked."""
    SeatHold.objects.filter(show=show, expires_at__lte=timezone.now()).delete()


def unavailable_labels(show, *, exclude_hold=None) -> set:
    booked = set(BookedSeat.objects.filter(show=show, is_active=True).values_list("label", flat=True))
    held = HeldSeat.objects.filter(show=show, hold__expires_at__gt=timezone.now())
    if exclude_hold is not None:
        held = held.exclude(hold=exclude_hold)
    return booked | set(held.values_list("label", flat=True))


def _validate_labels(show, seats) -> list[str]:
    labels = sorted({s.strip().upper() for s in seats})
    if not 1 <= len(labels) <= MAX_SEATS:
        raise DomainError(f"Choose between 1 and {MAX_SEATS} seats.", code="invalid_seat_count")
    invalid = [s for s in labels if show.seat_tier(s) is None]
    if invalid:
        raise DomainError("Some seats don't exist for this showtime.", code="invalid_seats", details={"seats": invalid})
    return labels


# --- holds ---------------------------------------------------------------------------------------------------

@transaction.atomic
def create_hold(*, customer, show_id, seats) -> SeatHold:
    """Reserve seats for HOLD_MINUTES. Replaces the customer's earlier hold for the same showtime."""
    show = _locked_show(show_id)
    _venue_open(show)
    labels = _validate_labels(show, seats)
    release_expired(show)
    SeatHold.objects.filter(show=show, customer=customer).delete()
    taken = sorted(set(labels) & unavailable_labels(show))
    if taken:
        raise ConflictError("Some of these seats were just taken. Choose others.", code="seats_unavailable", details={"seats": taken})
    hold = SeatHold.objects.create(customer=customer, show=show, expires_at=timezone.now() + timedelta(minutes=HOLD_MINUTES))
    try:
        with transaction.atomic():
            HeldSeat.objects.bulk_create(HeldSeat(hold=hold, show=show, label=s, tier=show.seat_tier(s), price=show.seat_price(s)) for s in labels)
    except IntegrityError:
        raise ConflictError("Some of these seats were just taken. Choose others.", code="seats_unavailable")
    record(customer, "showtime.held", {"seats": len(labels)}, obj=show)
    return hold


def active_hold(customer, hold_id) -> SeatHold:
    hold = SeatHold.objects.select_related("show__event", "show__venue", "show__screen_ref").prefetch_related("seats").filter(
        pk=hold_id, customer=customer).first()
    if hold is None:
        raise DomainError("Your seats aren’t held any more. Choose them again.", code="hold_not_found", status_code=404)
    if hold.expires_at <= timezone.now():
        raise ConflictError("Your seat hold has expired. Choose your seats again.", code="hold_expired")
    return hold


def release_hold(customer, hold_id) -> None:
    SeatHold.objects.filter(pk=hold_id, customer=customer).delete()


# --- pricing -------------------------------------------------------------------------------------------------

@dataclass
class Quote:
    seats: list = field(default_factory=list)            # [(label, tier, price)]
    concessions: list = field(default_factory=list)      # [(item, qty, line_total)]
    tickets: Decimal = Decimal("0")
    convenience_fee: Decimal = Decimal("0")
    concessions_total: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    discount: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    offer: ShowOffer | None = None


def active_offers(show=None, *, at=None):
    now = at or timezone.now()
    qs = ShowOffer.objects.filter(is_active=True).filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now)).filter(
        Q(ends_at__isnull=True) | Q(ends_at__gt=now))
    if show is not None:
        qs = qs.filter(Q(venue__isnull=True) | Q(venue_id=show.venue_id)).filter(Q(event__isnull=True) | Q(event_id=show.event_id))
    return qs


def offer_problem(offer: ShowOffer | None, show, tickets: Decimal, seat_count: int, payment_method: str | None) -> str | None:
    if offer is None:
        return "Choose an offer."
    if not active_offers(show).filter(pk=offer.pk).exists():
        return "This offer isn’t valid for this showtime."
    if seat_count < offer.min_seats:
        return f"Book at least {offer.min_seats} seats to use this offer."
    if tickets < offer.min_amount:
        return f"Tickets worth {offer.min_amount - tickets:.2f} more are needed for this offer."
    if offer.payment_method and payment_method and payment_method != offer.payment_method:
        return "Pay with Click. Wallet to use this offer." if offer.payment_method == "wallet" else "Not valid with this payment method."
    return None


def offer_discount(offer: ShowOffer, tickets: Decimal) -> Decimal:
    if offer.discount_type == ShowOffer.DiscountType.PERCENT:
        d = (tickets * offer.discount_value / 100).quantize(TWO, ROUND_HALF_UP)
        return min(d, offer.max_discount) if offer.max_discount is not None else d
    return min(offer.discount_value, tickets)


def resolve_concessions(show, items) -> list:
    """[(ConcessionItem, qty)] from [{"id", "quantity"}], checked against this venue's available items."""
    wanted: dict = {}
    for it in items or []:
        qty = int(it.get("quantity", 0))
        if qty < 0 or qty > MAX_CONCESSION_QTY:
            raise DomainError(f"Choose up to {MAX_CONCESSION_QTY} of each item.", code="invalid_quantity")
        if qty:
            wanted[str(it["id"])] = wanted.get(str(it["id"]), 0) + qty
    if not wanted:
        return []
    found = {str(i.id): i for i in ConcessionItem.objects.filter(pk__in=wanted.keys(), venue_id=show.venue_id)}
    missing = [k for k in wanted if k not in found or not found[k].is_available]
    if missing:
        raise ConflictError("Some food & drinks aren’t available right now.", code="concessions_unavailable",
                            details={"items": [found[k].name for k in missing if k in found]})
    return [(found[k], q) for k, q in wanted.items()]


def quote(show, seats, concessions, *, offer=None, payment_method=None, strict_offer=False) -> Quote:
    q = Quote(seats=seats)
    q.tickets = sum((p for _, _, p in seats), Decimal("0"))
    q.convenience_fee = CONVENIENCE_FEE_PER_SEAT * len(seats)
    q.concessions = [(item, qty, (item.price * qty).quantize(TWO)) for item, qty in concessions]
    q.concessions_total = sum((lt for _, _, lt in q.concessions), Decimal("0"))
    q.tax = (q.convenience_fee * settings.CLICK_SERVICE_FEE_TAX_RATE + q.concessions_total * settings.CLICK_TAX_RATE).quantize(TWO, ROUND_HALF_UP)
    if offer is not None:
        problem = offer_problem(offer, show, q.tickets, len(seats), payment_method)
        if problem and strict_offer:
            raise ConflictError(problem, code="offer_not_applicable")
        if not problem:
            q.offer, q.discount = offer, offer_discount(offer, q.tickets)
    q.total = max(q.tickets + q.convenience_fee + q.concessions_total + q.tax - q.discount, Decimal("0")).quantize(TWO)
    return q


def hold_seats(hold) -> list:
    return [(s.label, s.tier, s.price) for s in hold.seats.all()]


# --- booking -------------------------------------------------------------------------------------------------

@transaction.atomic
def create_booking(*, customer, payment_method: str, idempotency_key, show_id=None, seats=None, hold_id=None,
                   concessions=None, offer_id=None) -> tuple[Booking, bool]:
    """
    Book from a seat hold (the Showtime flow) or, for older clients, directly from seat labels. Everything is
    re-validated and re-priced here; a repeated idempotency key returns the original booking.
    """
    existing = Booking.objects.filter(customer=customer, idempotency_key=idempotency_key).first()
    if existing:
        return existing, False

    hold = None
    if hold_id:
        hold = SeatHold.objects.select_for_update().filter(pk=hold_id, customer=customer).first()
        if hold is None:
            raise DomainError("Your seats aren’t held any more. Choose them again.", code="hold_not_found", status_code=404)
        show_id = hold.show_id
    show = _locked_show(show_id)
    _venue_open(show)
    release_expired(show)
    if hold is not None:
        if not SeatHold.objects.filter(pk=hold.pk).exists():
            raise ConflictError("Your seat hold has expired. Choose your seats again.", code="hold_expired")
        seat_rows = hold_seats(hold)
    else:
        labels = _validate_labels(show, seats or [])
        taken = sorted(set(labels) & unavailable_labels(show))
        if taken:
            raise ConflictError("Some seats were just booked by someone else.", code="seats_unavailable", details={"seats": taken})
        seat_rows = [(s, show.seat_tier(s), show.seat_price(s)) for s in labels]

    offer = ShowOffer.objects.filter(pk=offer_id).first() if offer_id else None
    if offer_id and offer is None:
        raise ConflictError("This offer isn’t available.", code="offer_not_applicable")
    q = quote(show, seat_rows, resolve_concessions(show, concessions), offer=offer, payment_method=payment_method, strict_offer=True)

    booking = Booking.objects.create(
        customer=customer, show=show, subtotal=q.tickets, convenience_fee=q.convenience_fee, concessions_total=q.concessions_total,
        tax=q.tax, discount=q.discount, offer=q.offer, offer_title=q.offer.title if q.offer else "", total=q.total,
        currency=show.currency, idempotency_key=idempotency_key)
    if hold is not None:
        hold.delete()  # its seats become booked seats below (same transaction)
    try:
        with transaction.atomic():
            BookedSeat.objects.bulk_create(BookedSeat(booking=booking, show=show, label=l, tier=t, price=p) for l, t, p in seat_rows)
    except IntegrityError:
        raise ConflictError("Some seats were just booked by someone else.", code="seats_unavailable")
    BookingConcession.objects.bulk_create(
        BookingConcession(booking=booking, item=item, name=item.name, unit_price=item.price, quantity=qty, line_total=lt)
        for item, qty, lt in q.concessions)
    start_booking_payment(booking, payment_method)  # wallet shortfall raises here and rolls everything back
    labels = ", ".join(l for l, _, _ in seat_rows)
    notify(customer, NotificationCategory.BOOKINGS, f"Booked: {show.event.title}",
           f"{booking.reference} · {labels} · {show.venue.name}", f"/tickets/{booking.id}")
    record(customer, "booking.created", {"show": str(show.id), "seats": len(seat_rows)}, obj=booking)
    audit.info("booking.created", extra={"booking": booking.reference})
    return booking, True


@transaction.atomic
def cancel_booking(booking: Booking) -> Booking:
    booking = Booking.objects.select_for_update().select_related("show__event").get(pk=booking.pk)
    if booking.status != Booking.Status.CONFIRMED:
        raise ConflictError("This booking is already cancelled.", code="booking_not_cancellable")
    if booking.show.starts_at - timezone.now() < CANCELLATION_CUTOFF:
        raise ConflictError("Bookings can be cancelled up to 2 hours before the show.", code="booking_not_cancellable")
    booking.status = Booking.Status.CANCELLED
    booking.cancelled_at = timezone.now()
    booking.save(update_fields=["status", "cancelled_at", "updated_at"])
    booking.seats.update(is_active=False)
    settle_on_cancel(booking.payments.all(), booking.customer, f"booking {booking.reference}")
    notify(booking.customer, NotificationCategory.BOOKINGS, f"Booking cancelled: {booking.show.event.title}",
           booking.reference, f"/tickets/{booking.id}")
    return booking


def can_cancel(booking: Booking) -> bool:
    return booking.status == Booking.Status.CONFIRMED and booking.show.starts_at - timezone.now() >= CANCELLATION_CUTOFF


def cancellation_terms(booking: Booking) -> dict:
    """What cancelling would do, from the same rules cancel_booking applies (shown before the customer confirms)."""
    payment = booking.payments.order_by("created_at").first()
    wallet_paid = payment is not None and payment.method == "wallet" and payment.status == "captured"
    return {
        "allowed": can_cancel(booking),
        "cutoff_hours": int(CANCELLATION_CUTOFF.total_seconds() // 3600),
        "deadline": (booking.show.starts_at - CANCELLATION_CUTOFF).isoformat(),
        "refund_amount": f"{booking.total:.2f}" if wallet_paid else "0.00",
        "refund_method": "Click. Wallet" if wallet_paid else ("Nothing was charged (pay at venue)" if payment else "—"),
        "charges": "0.00",
    }
