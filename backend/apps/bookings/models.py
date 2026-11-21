"""
Unified bookings domain (Click. Showtime): anything with a time, a place and limited capacity.
Cinema titles and live shows today; theatre, concerts, sports and special screenings reuse the same records.

  Event      a title (a film or a live show) with media, credits, reviews and interest
  Venue      a cinema/theatre/arena, with Screens (seat layout + formats) and food & drinks (ConcessionItem)
  Show       one showtime of an Event on a Screen (or a simple rows x seats layout for legacy/live venues)
  SeatHold   seats reserved for a few minutes while the customer checks out (HeldSeat is unique per show seat)
  Booking    the ticket: seats (BookedSeat, unique per show seat while active), food & drinks, offer, payment
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
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    facilities = models.JSONField(default=list, blank=True, help_text='e.g. ["Parking", "Wheelchair access", "Food court"].')
    image_url = models.URLField(blank=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["city"], name="bookings_venue_city_idx")]

    def __str__(self) -> str:
        return self.name


class Screen(BaseModel):
    """
    An auditorium with its real seat layout. `layout` = {"rows": [{"row": "A", "tier": "classic", "seats": 14,
    "gaps": [4, 10], "unavailable": [7], "accessible": [1, 2]}], "tiers": [{"code": "classic", "name": "Classic"}]}.
    Rows are listed front (nearest the screen) to back.
    """

    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name="screens")
    name = models.CharField(max_length=40)
    formats = models.CharField(max_length=80, blank=True, help_text="Comma-separated formats this screen can play, e.g. '2D, 3D, IMAX'.")
    sound = models.CharField(max_length=40, blank=True, help_text="e.g. 'Dolby Atmos'.")
    layout = models.JSONField()

    class Meta:
        ordering = ["venue", "name"]
        constraints = [models.UniqueConstraint(fields=["venue", "name"], name="bookings_screen_name_unique")]

    def __str__(self) -> str:
        return f"{self.venue.name} · {self.name}"

    def seat_index(self) -> dict:
        """label -> {"tier", "accessible", "unavailable"} for every seat position in the layout."""
        out = {}
        for r in self.layout.get("rows", []):
            for n in range(1, int(r["seats"]) + 1):
                out[f"{r['row']}{n}"] = {"tier": r["tier"], "accessible": n in r.get("accessible", []),
                                         "unavailable": n in r.get("unavailable", [])}
        return out

    def tier_names(self) -> dict:
        return {t["code"]: t["name"] for t in self.layout.get("tiers", [])}


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
    backdrop_url = models.URLField(blank=True)
    trailer_url = models.URLField(blank=True, help_text="A legitimately licensed video file (MP4/WebM).")
    media_credit = models.CharField(max_length=200, blank=True, help_text="Attribution/licence for the artwork and trailer.")
    languages = models.CharField(max_length=120, blank=True, help_text="Comma-separated, e.g. 'Hindi, English'.")
    genres = models.CharField(max_length=120, blank=True, help_text="Comma-separated.")
    certification = models.CharField(max_length=8, blank=True, help_text="U, UA, A…")
    duration_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    release_date = models.DateField(null=True, blank=True)
    cast = models.CharField(max_length=300, blank=True)
    # Maintained from published, verified-attendance reviews (apps.bookings.reviews); never edited by hand.
    rating_average = models.DecimalField(max_digits=2, decimal_places=1, default=0)
    rating_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-rating_average", "title"]
        indexes = [models.Index(fields=["kind", "status"], name="bookings_event_kind_status_idx")]
        constraints = [models.CheckConstraint(condition=Q(rating_average__gte=0, rating_average__lte=5), name="bookings_event_rating_range")]

    def __str__(self) -> str:
        return self.title


class Credit(BaseModel):
    """A person in a title's cast or crew (crew: director, producer, music…)."""

    class Role(models.TextChoices):
        CAST = "cast", "Cast"
        CREW = "crew", "Crew"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="credits")
    name = models.CharField(max_length=120)
    role = models.CharField(max_length=4, choices=Role.choices)
    part = models.CharField(max_length=80, blank=True, help_text="Character for cast, job for crew.")
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["role", "position"]
        indexes = [models.Index(fields=["name"], name="bookings_credit_name_idx")]


ROW_LETTERS = string.ascii_uppercase


class Show(BaseModel):
    """
    One showtime of an Event. With a Screen, seats and tiers come from the screen's real layout and prices from
    `tier_prices`; without one (legacy/live venues) a simple rows × seats layout is used.
    """

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        CANCELLED = "cancelled", "Cancelled"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="shows")
    venue = models.ForeignKey(Venue, on_delete=models.PROTECT, related_name="shows")
    screen_ref = models.ForeignKey(Screen, on_delete=models.PROTECT, null=True, blank=True, related_name="shows")
    starts_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED)
    language = models.CharField(max_length=40, blank=True)
    format = models.CharField(max_length=20, blank=True, help_text="2D, 3D, IMAX, 4DX, Live…")
    screen = models.CharField(max_length=40, blank=True)
    rows = models.PositiveSmallIntegerField()
    seats_per_row = models.PositiveSmallIntegerField()
    premium_rows = models.PositiveSmallIntegerField(default=0, help_text="Last N rows are premium.")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    premium_price = models.DecimalField(max_digits=10, decimal_places=2)
    tier_prices = models.JSONField(default=dict, blank=True, help_text='Screen tiers -> price, e.g. {"classic": "180.00"}.')
    currency = models.CharField(max_length=3, default=settings.CLICK_DEFAULT_CURRENCY)

    class Meta:
        ordering = ["starts_at"]
        indexes = [
            models.Index(fields=["event", "starts_at"], name="bookings_show_event_time_idx"),
            models.Index(fields=["venue", "starts_at"], name="bookings_show_venue_time_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(rows__gte=1, rows__lte=26, seats_per_row__gte=1, seats_per_row__lte=40), name="bookings_show_layout_bounds"),
            models.CheckConstraint(condition=Q(premium_rows__lte=F("rows")), name="bookings_show_premium_rows_le_rows"),
            models.CheckConstraint(condition=Q(price__gte=0, premium_price__gte=0), name="bookings_show_prices_non_negative"),
        ]

    def _index(self) -> dict | None:
        if not self.screen_ref_id:
            return None
        if not hasattr(self, "_seat_index"):
            self._seat_index = self.screen_ref.seat_index()
        return self._seat_index

    def seat_tier(self, label: str) -> str | None:
        """Validates a seat label like 'C7' and returns its tier, or None if it doesn't exist or can't be sold."""
        index = self._index()
        if index is not None:
            seat = index.get(label)
            return None if seat is None or seat["unavailable"] else seat["tier"]
        if len(label) < 2 or label[0] not in ROW_LETTERS[: self.rows] or not label[1:].isdigit():
            return None
        number = int(label[1:])
        if not 1 <= number <= self.seats_per_row:
            return None
        return "premium" if ROW_LETTERS.index(label[0]) >= self.rows - self.premium_rows else "standard"

    def seat_price(self, label: str):
        from decimal import Decimal

        tier = self.seat_tier(label)
        if self.screen_ref_id:
            return Decimal(str(self.tier_prices.get(tier, self.price)))
        return self.premium_price if tier == "premium" else self.price

    @property
    def capacity(self) -> int:
        index = self._index()
        if index is not None:
            return sum(1 for s in index.values() if not s["unavailable"])
        return self.rows * self.seats_per_row


def _reference() -> str:
    return "BKG-" + "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))


class ShowOffer(BaseModel):
    """A Showtime offer, validated and applied by the server (optionally for one venue, title or payment method)."""

    class DiscountType(models.TextChoices):
        PERCENT = "percent", "Percent off"
        FLAT = "flat", "Flat amount off"

    title = models.CharField(max_length=80)
    description = models.CharField(max_length=200, blank=True)
    discount_type = models.CharField(max_length=8, choices=DiscountType.choices)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    max_discount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    min_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Minimum ticket value.")
    min_seats = models.PositiveSmallIntegerField(default=1)
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, null=True, blank=True, related_name="offers")
    event = models.ForeignKey(Event, on_delete=models.CASCADE, null=True, blank=True, related_name="offers")
    payment_method = models.CharField(max_length=30, blank=True, help_text="Only for this payment method (e.g. wallet).")
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title


class Booking(BaseModel):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"

    reference = models.CharField(max_length=16, unique=True, default=_reference, editable=False)
    customer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT, related_name="bookings")
    show = models.ForeignKey(Show, on_delete=models.PROTECT, related_name="bookings")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CONFIRMED)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, help_text="Tickets.")
    convenience_fee = models.DecimalField(max_digits=10, decimal_places=2)
    concessions_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    offer = models.ForeignKey(ShowOffer, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    offer_title = models.CharField(max_length=80, blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default=settings.CLICK_DEFAULT_CURRENCY)
    idempotency_key = models.UUIDField()
    cancelled_at = models.DateTimeField(null=True, blank=True)
    checked_in_at = models.DateTimeField(null=True, blank=True, help_text="Set when the venue scans the ticket.")

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


class SeatHold(BaseModel):
    """Seats reserved for one customer for a few minutes while they check out. Expired holds are released."""

    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="seat_holds")
    show = models.ForeignKey(Show, on_delete=models.CASCADE, related_name="holds")
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at"]


class HeldSeat(BaseModel):
    hold = models.ForeignKey(SeatHold, on_delete=models.CASCADE, related_name="seats")
    show = models.ForeignKey(Show, on_delete=models.CASCADE, related_name="held_seats")
    label = models.CharField(max_length=4)
    tier = models.CharField(max_length=10)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["label"]
        # One hold per seat per show (expired holds are deleted under the show's row lock before new ones are made).
        constraints = [models.UniqueConstraint(fields=["show", "label"], name="bookings_seat_held_once")]


class ConcessionItem(BaseModel):
    """Food & drinks a venue sells with tickets (only venues with items offer them)."""

    class Category(models.TextChoices):
        COMBO = "combo", "Combos"
        POPCORN = "popcorn", "Popcorn"
        SNACKS = "snacks", "Snacks"
        DRINKS = "drinks", "Drinks"

    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name="concessions")
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=160, blank=True)
    category = models.CharField(max_length=8, choices=Category.choices)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    is_veg = models.BooleanField(default=True)
    is_available = models.BooleanField(default=True)
    image_url = models.URLField(blank=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["category", "position", "name"]
        constraints = [models.CheckConstraint(condition=Q(price__gte=0), name="bookings_concession_price_non_negative")]


class BookingConcession(BaseModel):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="concessions")
    item = models.ForeignKey(ConcessionItem, on_delete=models.SET_NULL, null=True, related_name="+")
    name = models.CharField(max_length=80)
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)
    quantity = models.PositiveSmallIntegerField()
    line_total = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["created_at"]


class ShowReview(BaseModel):
    """A rating from a customer who attended (a confirmed booking whose show has started). One per title."""

    class Status(models.TextChoices):
        PUBLISHED = "published", "Published"
        HIDDEN = "hidden", "Hidden by moderation"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="reviews")
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="show_reviews")
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    rating = models.PositiveSmallIntegerField()
    body = models.CharField(max_length=1500, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PUBLISHED)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["event", "customer"], name="bookings_review_one_per_customer"),
            models.CheckConstraint(condition=Q(rating__gte=1, rating__lte=5), name="bookings_review_rating_range"),
        ]


class ShowInterest(BaseModel):
    """'I'm interested' on an upcoming title; notified once when booking opens."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="interests")
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="show_interests")
    notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["event", "customer"], name="bookings_interest_unique")]


class ShowFeature(BaseModel):
    """Editorial featuring of a title in the Showtime hero, with a priority and date window."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="features")
    headline = models.CharField(max_length=120, blank=True)
    priority = models.PositiveSmallIntegerField(default=0)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-priority", "ends_at"]
        constraints = [models.CheckConstraint(condition=Q(ends_at__gt=F("starts_at")), name="bookings_feature_window")]
