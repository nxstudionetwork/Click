"""
Unified bookings domain: anything with a time, a place and limited capacity.
Movies and live events today; appointments and experiences reuse Show
(a bookable time slot) and Booking later.
"""

import secrets
import string

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile


class Venue(BaseModel):
    class Kind(models.TextChoices):
        CINEMA = "cinema", "Cinema"
        THEATRE = "theatre", "Theatre"
        ARENA = "arena", "Arena"
        CLUB = "club", "Club / lounge"

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, unique=True)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    city = models.CharField(max_length=100)
    locality = models.CharField(max_length=120, blank=True)
    address = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["city"], name="bookings_venue_city_idx")]

    def __str__(self) -> str:
        return self.name


class Event(BaseModel):
    class Kind(models.TextChoices):
        MOVIE = "movie", "Movie"
        EVENT = "event", "Live event"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        NOW_SHOWING = "now_showing", "Now showing"
        COMING_SOON = "coming_soon", "Coming soon"
        ENDED = "ended", "Ended"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=170, unique=True)
    tagline = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    poster_url = models.URLField(blank=True)
    languages = models.CharField(max_length=120, blank=True, help_text="Comma-separated, e.g. 'Hindi, English'.")
    genres = models.CharField(max_length=120, blank=True, help_text="Comma-separated.")
    certification = models.CharField(max_length=8, blank=True, help_text="U, UA, A…")
    duration_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    release_date = models.DateField(null=True, blank=True)
    cast = models.CharField(max_length=300, blank=True)
    rating_average = models.DecimalField(max_digits=2, decimal_places=1, default=0)
    rating_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-rating_average", "title"]
        indexes = [models.Index(fields=["kind", "status"], name="bookings_event_kind_status_idx")]
        constraints = [models.CheckConstraint(condition=Q(rating_average__gte=0, rating_average__lte=5), name="bookings_event_rating_range")]

    def __str__(self) -> str:
        return self.title


ROW_LETTERS = string.ascii_uppercase


class Show(BaseModel):
    """A bookable time slot at a venue, with a simple rows × seats layout."""

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        CANCELLED = "cancelled", "Cancelled"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="shows")
    venue = models.ForeignKey(Venue, on_delete=models.PROTECT, related_name="shows")
    starts_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED)
    language = models.CharField(max_length=40, blank=True)
    format = models.CharField(max_length=20, blank=True, help_text="2D, 3D, IMAX, Live…")
    screen = models.CharField(max_length=40, blank=True)
    rows = models.PositiveSmallIntegerField()
    seats_per_row = models.PositiveSmallIntegerField()
    premium_rows = models.PositiveSmallIntegerField(default=0, help_text="Last N rows are premium.")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    premium_price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default=settings.CLICK_DEFAULT_CURRENCY)

    class Meta:
        ordering = ["starts_at"]
        indexes = [models.Index(fields=["event", "starts_at"], name="bookings_show_event_time_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(rows__gte=1, rows__lte=26, seats_per_row__gte=1, seats_per_row__lte=40), name="bookings_show_layout_bounds"),
            models.CheckConstraint(condition=Q(premium_rows__lte=F("rows")), name="bookings_show_premium_rows_le_rows"),
            models.CheckConstraint(condition=Q(price__gte=0, premium_price__gte=0), name="bookings_show_prices_non_negative"),
        ]

    def seat_tier(self, label: str) -> str | None:
        """Validates a seat label like 'C7' and returns its tier, or None if it doesn't exist."""
        if len(label) < 2 or label[0] not in ROW_LETTERS[: self.rows] or not label[1:].isdigit():
            return None
        number = int(label[1:])
        if not 1 <= number <= self.seats_per_row:
            return None
        return "premium" if ROW_LETTERS.index(label[0]) >= self.rows - self.premium_rows else "standard"

    def seat_price(self, label: str):
        return self.premium_price if self.seat_tier(label) == "premium" else self.price


def _reference() -> str:
    return "BKG-" + "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))


class Booking(BaseModel):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"

    reference = models.CharField(max_length=16, unique=True, default=_reference, editable=False)
    customer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT, related_name="bookings")
    show = models.ForeignKey(Show, on_delete=models.PROTECT, related_name="bookings")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CONFIRMED)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    convenience_fee = models.DecimalField(max_digits=10, decimal_places=2)
    tax = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default=settings.CLICK_DEFAULT_CURRENCY)
    idempotency_key = models.UUIDField()
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["customer", "-created_at"], name="bookings_customer_recent_idx")]
        constraints = [
            models.UniqueConstraint(fields=["customer", "idempotency_key"], name="bookings_customer_idempotency_unique"),
            models.CheckConstraint(condition=Q(total__gte=0), name="bookings_total_non_negative"),
        ]


class BookedSeat(BaseModel):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="seats")
    show = models.ForeignKey(Show, on_delete=models.CASCADE, related_name="booked_seats")
    label = models.CharField(max_length=4)
    tier = models.CharField(max_length=10)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["label"]
        constraints = [
            # The database itself guarantees a seat can't be sold twice for the same show.
            models.UniqueConstraint(fields=["show", "label"], condition=Q(is_active=True), name="bookings_seat_sold_once"),
        ]
