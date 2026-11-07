import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.api.exceptions import ConflictError, DomainError
from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify
from apps.payments.services import settle_on_cancel, start_booking_payment

from .models import BookedSeat, Booking, Show

from apps.activity.services import record

audit = logging.getLogger("click.audit")
MAX_SEATS = 10
CONVENIENCE_FEE_PER_SEAT = Decimal("20.00")
CANCELLATION_CUTOFF = timedelta(hours=2)


def bookable_shows():
    return Show.objects.filter(status=Show.Status.SCHEDULED, starts_at__gt=timezone.now(),
                               event__status__in=["now_showing", "coming_soon"]).select_related("event", "venue")


@transaction.atomic
def create_booking(*, customer, show_id, seats: list[str], payment_method: str, idempotency_key) -> tuple[Booking, bool]:
    existing = Booking.objects.filter(customer=customer, idempotency_key=idempotency_key).first()
    if existing:
        return existing, False
    try:
        show = bookable_shows().select_for_update(of=("self",)).get(pk=show_id)
    except Show.DoesNotExist:
        raise DomainError("This show is no longer available for booking.", code="show_unavailable", status_code=404)

    labels = sorted({s.strip().upper() for s in seats})
    if not 1 <= len(labels) <= MAX_SEATS:
        raise DomainError(f"Choose between 1 and {MAX_SEATS} seats.", code="invalid_seat_count")
    invalid = [s for s in labels if show.seat_tier(s) is None]
    if invalid:
        raise DomainError("Some seats don't exist for this show.", code="invalid_seats", details={"seats": invalid})
    taken = list(BookedSeat.objects.filter(show=show, label__in=labels, is_active=True).values_list("label", flat=True))
    if taken:
        raise ConflictError("Some seats were just booked by someone else.", code="seats_unavailable", details={"seats": taken})

    subtotal = sum((show.seat_price(s) for s in labels), Decimal("0"))
    fee = CONVENIENCE_FEE_PER_SEAT * len(labels)
    tax = (fee * settings.CLICK_SERVICE_FEE_TAX_RATE).quantize(Decimal("0.01"))
    booking = Booking.objects.create(customer=customer, show=show, subtotal=subtotal, convenience_fee=fee, tax=tax,
                                     total=subtotal + fee + tax, currency=show.currency, idempotency_key=idempotency_key)
    try:
        with transaction.atomic():
            BookedSeat.objects.bulk_create(
                BookedSeat(booking=booking, show=show, label=s, tier=show.seat_tier(s), price=show.seat_price(s)) for s in labels
            )
    except IntegrityError:
        raise ConflictError("Some seats were just booked by someone else.", code="seats_unavailable")
    start_booking_payment(booking, payment_method)
    notify(customer, NotificationCategory.BOOKINGS, f"Booked: {show.event.title}",
           f"{booking.reference} · {', '.join(labels)} · {show.venue.name}", f"/bookings/{booking.id}")
    record(customer, "booking.created", {"show": str(show.id), "seats": len(labels)}, obj=booking)
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
           booking.reference, f"/bookings/{booking.id}")
    return booking


def can_cancel(booking: Booking) -> bool:
    return booking.status == Booking.Status.CONFIRMED and booking.show.starts_at - timezone.now() >= CANCELLATION_CUTOFF
