"""
Showtime engagement: reviews (only from customers who attended), "I'm interested" (with one notification when
booking opens) and digital tickets that venues can actually verify.

Ticket codes are signed by the server (django.core.signing, salted). A venue verifies a code through the Partner
API (`POST /partner/tickets/verify`): the signature must be valid, the booking confirmed, the show at that partner's
venue and close in time; the first scan checks the ticket in and later scans say when it was used.
"""

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core import signing
from django.db import transaction
from django.db.models import Avg, Count
from django.utils import timezone

from apps.activity.services import record
from apps.core.api.exceptions import ConflictError, DomainError
from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify

from .models import Booking, Event, ShowInterest, ShowReview

TICKET_SALT = "click.showtime.ticket"
TICKET_PREFIX = "CLICKTKT:"


# --- reviews -------------------------------------------------------------------------------------------------

def attended_booking(customer, event):
    """The customer's confirmed booking for this title whose show has started (attendance), if any."""
    return (Booking.objects.filter(customer=customer, show__event=event, status=Booking.Status.CONFIRMED,
                                   show__starts_at__lte=timezone.now()).order_by("-show__starts_at").first())


def recompute_rating(event_id) -> None:
    agg = ShowReview.objects.filter(event_id=event_id, status=ShowReview.Status.PUBLISHED).aggregate(a=Avg("rating"), n=Count("id"))
    Event.objects.filter(pk=event_id).update(rating_average=Decimal(agg["a"] or 0).quantize(Decimal("0.1"), ROUND_HALF_UP),
                                             rating_count=agg["n"])


@transaction.atomic
def save_review(customer, event, *, rating: int, body: str = "", create: bool) -> ShowReview:
    existing = ShowReview.objects.filter(event=event, customer=customer).first()
    if create:
        if existing:
            raise ConflictError("You’ve already reviewed this show. Edit your review instead.", code="review_exists")
        booking = attended_booking(customer, event)
        if booking is None:
            raise DomainError("You can review a show after you’ve watched it with a Click. booking.", code="review_not_allowed", status_code=403)
        review = ShowReview.objects.create(event=event, customer=customer, booking=booking, rating=rating, body=body.strip())
        record(customer, "show.reviewed", {"rating": rating}, obj=event)
    else:
        if existing is None:
            raise DomainError("You haven’t reviewed this show yet.", code="review_not_found", status_code=404)
        existing.rating, existing.body = rating, body.strip()
        existing.save(update_fields=["rating", "body", "updated_at"])
        review = existing
    recompute_rating(event.pk)
    return review


@transaction.atomic
def delete_review(customer, event) -> None:
    if not ShowReview.objects.filter(event=event, customer=customer).delete()[0]:
        raise DomainError("You haven’t reviewed this show.", code="review_not_found", status_code=404)
    recompute_rating(event.pk)


# --- interest ------------------------------------------------------------------------------------------------

def set_interest(customer, event, interested: bool) -> bool:
    if interested:
        ShowInterest.objects.get_or_create(event=event, customer=customer)
        record(customer, "show.interested", obj=event)
    else:
        ShowInterest.objects.filter(event=event, customer=customer).delete()
    return interested


def notify_booking_open(event) -> int:
    """Tell interested customers (once each) that a title they follow can now be booked."""
    from .services import bookable_shows

    if not bookable_shows().filter(event=event).exists():
        return 0
    pending = list(ShowInterest.objects.filter(event=event, notified_at__isnull=True).select_related("customer"))
    for i in pending:
        notify(i.customer, NotificationCategory.BOOKINGS, f"Booking is open: {event.title}",
               "Choose a cinema, date and seats before they go.", f"/showtime/{event.slug}")
    ShowInterest.objects.filter(pk__in=[i.pk for i in pending]).update(notified_at=timezone.now())
    return len(pending)


# --- tickets -------------------------------------------------------------------------------------------------

def ticket_code(booking: Booking) -> str:
    return TICKET_PREFIX + signing.dumps({"b": str(booking.pk), "r": booking.reference}, salt=TICKET_SALT, compress=True)


@transaction.atomic
def verify_ticket(code: str, partner) -> dict:
    """Venue check-in. Only the partner operating the show's venue can verify; returns what the door staff see."""
    from apps.partners.models import PartnerVenue

    raw = code.strip()
    if raw.startswith(TICKET_PREFIX):
        raw = raw[len(TICKET_PREFIX):]
    try:
        data = signing.loads(raw, salt=TICKET_SALT)
    except signing.BadSignature:
        raise DomainError("This isn’t a valid Click. ticket.", code="ticket_invalid")
    booking = Booking.objects.select_for_update().select_related("show__event", "show__venue", "customer__user").filter(
        pk=data.get("b"), reference=data.get("r")).first()
    if booking is None:
        raise DomainError("This isn’t a valid Click. ticket.", code="ticket_invalid")
    if not PartnerVenue.objects.filter(partner=partner, venue_id=booking.show.venue_id).exists():
        raise DomainError("This ticket is for another venue.", code="ticket_other_venue", status_code=403)
    if booking.status != Booking.Status.CONFIRMED:
        raise ConflictError("This booking was cancelled.", code="ticket_cancelled")
    now = timezone.now()
    show = booking.show
    if now < show.starts_at - timedelta(hours=3) or now > show.starts_at + timedelta(minutes=(show.event.duration_minutes or 180)):
        raise ConflictError("This ticket isn’t for a show happening now.", code="ticket_not_now")
    first = booking.checked_in_at is None
    if first:
        booking.checked_in_at = now
        booking.save(update_fields=["checked_in_at", "updated_at"])
    return {"reference": booking.reference, "title": show.event.title, "starts_at": show.starts_at.isoformat(),
            "seats": [s.label for s in booking.seats.filter(is_active=True)], "first_scan": first,
            "checked_in_at": booking.checked_in_at.isoformat(), "customer": booking.customer.user.full_name.split()[0] if booking.customer.user.full_name else ""}
