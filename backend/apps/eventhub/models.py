"""
Click. Events: plan an event and book the people who make it happen.

Attending events (concerts, workshops, live shows) is Click. Showtime (apps.bookings: Event kind=event, Show, Venue,
tickets); Events reads those for discovery and links to them. This app is the planning marketplace:

  EventType / EventService      data-driven registries (Birthday, Wedding…; Decoration, Catering…) Business OS manages;
                                an event type suggests services and a checklist
  EventProvider                 a Partner (apps.partners) offering event work: a full event team, a single-service
                                vendor or a venue. Customer-facing profile, services, event types, service area,
                                FAQs, cancellation terms; ratings and counters maintained only from real bookings
  VenueDetails                  capacity, spaces, amenities, rules, parking and catering policy for venue providers
  ProviderBlockedDate           dates a provider marked unavailable; confirmed bookings also use up a provider's
                                events-per-day capacity — together the only source of "available on <date>"
  EventPackage (+ Addon)        packaged offerings with price basis, guest range, duration, inclusions, add-ons, terms
  PortfolioItem                 photos the provider uploaded (none are seeded: no invented portfolio history)
  EventPlan                     the customer's event: type, date (or flexible), place from their saved addresses,
                                guests, budget, services needed, requirements, reference photos, checklist
  Enquiry / Quote / Message     a plan sent to a provider; the provider quotes (itemised, versioned); the customer
                                accepts, rejects or asks for changes; questions go through Click (no phone numbers)
  EventBooking (+ Milestone, StatusEvent, Review)
                                the confirmed booking from an accepted quote or a package: price snapshot, payment
                                through the shared Payment/Wallet, milestones the provider ticks off, reviews from
                                customers with completed bookings only

Payments, notifications, support tickets and favourites (wishlist) are the shared Click. ones.
"""

import secrets
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel
from apps.customers.models import Address, CustomerProfile
from apps.partners.models import Partner

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _number(prefix: str) -> str:
    return prefix + "".join(secrets.choice(_ALPHABET) for _ in range(8))


def plan_number() -> str:
    return _number("EVP-")


def booking_number() -> str:
    return _number("EVB-")


# --- registries ------------------------------------------------------------------------------------------------------

class EventType(BaseModel):
    """Birthday, Wedding, Corporate… `checklist` = [{"key", "label", "service"}] seeds a plan's checklist."""

    slug = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=80)
    group = models.CharField(max_length=20, choices=[("personal", "Celebrations"), ("wedding", "Weddings"), ("work", "Work & learning"),
                                                     ("community", "Community & culture"), ("other", "Other")], default="personal")
    icon = models.CharField(max_length=30, default="gift")
    accent = models.CharField(max_length=9, default="#a855f7")
    summary = models.CharField(max_length=160, blank=True)
    synonyms = models.JSONField(default=list, blank=True)
    suggested_services = models.JSONField(default=list, blank=True, help_text="EventService slugs suggested for this event type.")
    checklist = models.JSONField(default=list, blank=True)
    position = models.PositiveSmallIntegerField(default=0)
    in_planner = models.BooleanField(default=True, help_text="Offered as a choice in Plan an Event.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "name"]

    def __str__(self):
        return self.name


class EventService(BaseModel):
    """Decoration, Catering, Photography… what a provider offers and a plan needs."""

    slug = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=80)
    group = models.CharField(max_length=20, choices=[("planning", "Planning"), ("venue", "Venue"), ("food", "Food"), ("media", "Photo & video"),
                                                     ("entertainment", "Entertainment"), ("decor", "Decor & setup"), ("beauty", "Beauty"),
                                                     ("logistics", "Staff & logistics")], default="planning")
    icon = models.CharField(max_length=30, default="sparkle")
    synonyms = models.JSONField(default=list, blank=True)
    position = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "name"]

    def __str__(self):
        return self.name


# --- providers -------------------------------------------------------------------------------------------------------

class EventProvider(BaseModel):
    class Kind(models.TextChoices):
        TEAM = "team", "Event team"
        VENDOR = "vendor", "Specialist"
        VENUE = "venue", "Venue"

    partner = models.OneToOneField(Partner, on_delete=models.CASCADE, related_name="event_provider")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.TEAM)
    tagline = models.CharField(max_length=140, blank=True)
    about = models.TextField(blank=True)
    logo = models.ImageField(upload_to="events/logos/", blank=True)
    cover = models.JSONField(default=dict, blank=True, editable=False, help_text="Cover image renditions the provider uploaded.")
    accent = models.CharField(max_length=9, default="#a855f7")
    experience_years = models.PositiveSmallIntegerField(null=True, blank=True)
    team_size = models.PositiveSmallIntegerField(null=True, blank=True)
    services = models.ManyToManyField(EventService, related_name="providers", blank=True)
    event_types = models.ManyToManyField(EventType, related_name="providers", blank=True)
    languages = models.JSONField(default=list, blank=True)
    city = models.CharField(max_length=80, default="Bengaluru")
    area = models.CharField(max_length=120, blank=True, help_text="Base locality shown to customers.")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    service_radius_km = models.PositiveSmallIntegerField(default=25)
    max_events_per_day = models.PositiveSmallIntegerField(default=1)
    min_notice_days = models.PositiveSmallIntegerField(default=2)
    min_guests = models.PositiveIntegerField(null=True, blank=True)
    max_guests = models.PositiveIntegerField(null=True, blank=True)
    faqs = models.JSONField(default=list, blank=True, help_text='[{"q": "...", "a": "..."}]')
    free_cancellation_days = models.PositiveSmallIntegerField(default=7, help_text="Full refund if cancelled at least this many days before.")
    late_cancellation_fee_percent = models.PositiveSmallIntegerField(default=25)
    is_listed = models.BooleanField(default=False, help_text="Shown to customers (Business OS turns this on after review).")
    is_featured = models.BooleanField(default=False)
    # Maintained from bookings and reviews (apps.eventhub.lifecycle.recompute); never edited by hand.
    rating_average = models.DecimalField(max_digits=2, decimal_places=1, default=0)
    rating_count = models.PositiveIntegerField(default=0)
    events_completed = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=["is_listed", "kind"], name="eventhub_provider_listed_idx")]

    def __str__(self):
        return self.partner.business_name


class VenueDetails(BaseModel):
    class Catering(models.TextChoices):
        IN_HOUSE = "in_house", "In-house catering only"
        OUTSIDE = "outside", "Outside caterers allowed"
        BOTH = "both", "In-house or outside caterers"
        NONE = "none", "No food service"

    provider = models.OneToOneField(EventProvider, on_delete=models.CASCADE, related_name="venue")
    space_type = models.CharField(max_length=60, help_text="e.g. Banquet hall, Rooftop, Lawn, Conference room.")
    indoor = models.BooleanField(default=True)
    outdoor = models.BooleanField(default=False)
    seated_capacity = models.PositiveIntegerField()
    floating_capacity = models.PositiveIntegerField()
    address = models.CharField(max_length=255, blank=True)
    amenities = models.JSONField(default=list, blank=True)
    rules = models.JSONField(default=list, blank=True)
    parking = models.CharField(max_length=160, blank=True)
    catering_policy = models.CharField(max_length=10, choices=Catering.choices, default=Catering.BOTH)
    hours = models.CharField(max_length=80, blank=True, help_text="e.g. 9 AM – 11 PM (music until 10 PM).")


class ProviderBlockedDate(BaseModel):
    provider = models.ForeignKey(EventProvider, on_delete=models.CASCADE, related_name="blocked_dates")
    date = models.DateField()
    reason = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["date"]
        constraints = [models.UniqueConstraint(fields=["provider", "date"], name="eventhub_blocked_unique")]


class PortfolioItem(BaseModel):
    provider = models.ForeignKey(EventProvider, on_delete=models.CASCADE, related_name="portfolio")
    event_type = models.ForeignKey(EventType, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    caption = models.CharField(max_length=160, blank=True)
    renditions = models.JSONField(default=dict, blank=True, editable=False)
    width = models.PositiveIntegerField(null=True, blank=True, editable=False)
    height = models.PositiveIntegerField(null=True, blank=True, editable=False)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "-created_at"]


class EventPackage(BaseModel):
    class Basis(models.TextChoices):
        FIXED = "fixed", "Fixed price"
        PER_GUEST = "per_guest", "Per guest"

    provider = models.ForeignKey(EventProvider, on_delete=models.CASCADE, related_name="packages")
    name = models.CharField(max_length=100)
    event_types = models.ManyToManyField(EventType, related_name="packages", blank=True)
    services = models.ManyToManyField(EventService, related_name="packages", blank=True)
    description = models.CharField(max_length=300, blank=True)
    includes = models.JSONField(default=list, blank=True, help_text="Inclusions shown as a list.")
    basis = models.CharField(max_length=10, choices=Basis.choices, default=Basis.FIXED)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    min_guests = models.PositiveIntegerField(default=1)
    max_guests = models.PositiveIntegerField()
    duration_hours = models.DecimalField(max_digits=4, decimal_places=1)
    terms = models.TextField(blank=True)
    position = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "price"]
        constraints = [models.CheckConstraint(condition=Q(price__gte=0) & Q(max_guests__gte=models.F("min_guests")), name="eventhub_package_valid")]

    def __str__(self):
        return f"{self.name} · {self.provider}"


class PackageAddon(BaseModel):
    package = models.ForeignKey(EventPackage, on_delete=models.CASCADE, related_name="addons")
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    per_guest = models.BooleanField(default=False)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "name"]


# --- the customer's event -------------------------------------------------------------------------------------------

class EventPlan(BaseModel):
    class Status(models.TextChoices):
        PLANNING = "planning", "Planning"
        BOOKED = "booked", "Booked"
        DONE = "done", "Done"
        CANCELLED = "cancelled", "Cancelled"

    number = models.CharField(max_length=16, unique=True, default=plan_number, editable=False)
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="event_plans")
    event_type = models.ForeignKey(EventType, on_delete=models.PROTECT, related_name="plans")
    title = models.CharField(max_length=120, blank=True)
    date = models.DateField(null=True, blank=True)
    date_flexible = models.BooleanField(default=False)
    date_note = models.CharField(max_length=120, blank=True, help_text="e.g. 'Any Saturday in March'.")
    start_time = models.TimeField(null=True, blank=True)
    address_ref = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    address = models.JSONField(default=dict, blank=True, help_text="Snapshot of the chosen saved address.")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    needs_venue = models.BooleanField(default=False)
    guests = models.PositiveIntegerField()
    guests_band = models.CharField(max_length=12, blank=True)
    budget_min = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    budget_max = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    budget_flexible = models.BooleanField(default=False)
    services = models.ManyToManyField(EventService, related_name="plans", blank=True)
    requirements = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PLANNING)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["customer", "status"], name="eventhub_plan_customer_idx")]

    def __str__(self):
        return self.number


class ChecklistItem(BaseModel):
    plan = models.ForeignKey(EventPlan, on_delete=models.CASCADE, related_name="checklist")
    key = models.CharField(max_length=40, blank=True)
    label = models.CharField(max_length=120)
    service = models.ForeignKey(EventService, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    done = models.BooleanField(default=False)
    done_at = models.DateTimeField(null=True, blank=True)
    auto = models.BooleanField(default=False, help_text="Ticked by Click when a booking covers it (the customer can still untick).")
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "created_at"]


class EventAttachment(BaseModel):
    """A customer's reference photo, uploaded before or while planning; visible to providers they send the plan to."""

    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="event_attachments")
    plan = models.ForeignKey(EventPlan, on_delete=models.CASCADE, null=True, blank=True, related_name="attachments")
    renditions = models.JSONField(default=dict, blank=True, editable=False)
    width = models.PositiveIntegerField(null=True, blank=True, editable=False)
    height = models.PositiveIntegerField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["created_at"]


# --- quotes ----------------------------------------------------------------------------------------------------------

class Enquiry(BaseModel):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Waiting for a quote"
        QUOTED = "quoted", "Quote received"
        REVISION = "revision", "Changes requested"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Declined by you"
        PROVIDER_DECLINED = "provider_declined", "Not available"
        WITHDRAWN = "withdrawn", "Withdrawn"

    OPEN = (Status.REQUESTED, Status.QUOTED, Status.REVISION)

    plan = models.ForeignKey(EventPlan, on_delete=models.CASCADE, related_name="enquiries")
    provider = models.ForeignKey(EventProvider, on_delete=models.CASCADE, related_name="enquiries")
    package = models.ForeignKey(EventPackage, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED)
    message = models.CharField(max_length=600, blank=True)
    first_response_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["plan", "provider"], name="eventhub_enquiry_unique")]


class Quote(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for you"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Declined"
        CHANGES = "changes", "Changes requested"
        SUPERSEDED = "superseded", "Replaced by a newer quote"

    enquiry = models.ForeignKey(Enquiry, on_delete=models.CASCADE, related_name="quotes")
    version = models.PositiveSmallIntegerField(default=1)
    items = models.JSONField(default=list, help_text='[{"label", "amount", "optional": bool}] — optional items are add-ons the customer may pick.')
    amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Total of the required items, before tax.")
    duration_hours = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    team_size = models.PositiveSmallIntegerField(null=True, blank=True)
    terms = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    valid_until = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    customer_note = models.CharField(max_length=600, blank=True)

    class Meta:
        ordering = ["-version"]


class Message(BaseModel):
    """Questions between the customer and a provider about an enquiry, kept on Click (no personal numbers shared)."""

    enquiry = models.ForeignKey(Enquiry, on_delete=models.CASCADE, related_name="messages")
    from_customer = models.BooleanField()
    body = models.CharField(max_length=1000)

    class Meta:
        ordering = ["created_at"]


# --- bookings --------------------------------------------------------------------------------------------------------

class BookingStatus(models.TextChoices):
    PAYMENT_PENDING = "payment_pending", "Payment pending"
    CONFIRMED = "confirmed", "Confirmed"
    PREPARING = "preparing", "Team preparing"
    IN_PROGRESS = "in_progress", "Event in progress"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


ALLOWED_TRANSITIONS = {
    BookingStatus.PAYMENT_PENDING: {BookingStatus.CONFIRMED, BookingStatus.CANCELLED},
    BookingStatus.CONFIRMED: {BookingStatus.PREPARING, BookingStatus.IN_PROGRESS, BookingStatus.CANCELLED},
    BookingStatus.PREPARING: {BookingStatus.IN_PROGRESS, BookingStatus.CANCELLED},
    BookingStatus.IN_PROGRESS: {BookingStatus.COMPLETED},
    BookingStatus.COMPLETED: set(),
    BookingStatus.CANCELLED: set(),
}
ACTIVE = (BookingStatus.PAYMENT_PENDING, BookingStatus.CONFIRMED, BookingStatus.PREPARING, BookingStatus.IN_PROGRESS)


class EventBooking(BaseModel):
    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Payment pending"
        PAID = "paid", "Paid"
        CASH_DUE = "cash_due", "Pay the team at the event"
        REFUNDED = "refunded", "Refunded"
        PARTLY_REFUNDED = "partly_refunded", "Partly refunded"

    number = models.CharField(max_length=16, unique=True, default=booking_number, editable=False)
    customer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT, related_name="event_bookings")
    plan = models.ForeignKey(EventPlan, on_delete=models.PROTECT, related_name="bookings")
    provider = models.ForeignKey(EventProvider, on_delete=models.PROTECT, related_name="bookings")
    quote = models.OneToOneField(Quote, on_delete=models.PROTECT, null=True, blank=True, related_name="booking")
    package = models.ForeignKey(EventPackage, on_delete=models.PROTECT, null=True, blank=True, related_name="bookings")
    status = models.CharField(max_length=20, choices=BookingStatus.choices, default=BookingStatus.PAYMENT_PENDING)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    payment_method = models.CharField(max_length=20, blank=True)
    event_date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    guests = models.PositiveIntegerField()
    address = models.JSONField(default=dict, blank=True)
    title = models.CharField(max_length=160)
    lines = models.JSONField(default=list, help_text='Price snapshot: [{"label", "amount"}].')
    services = models.JSONField(default=list, help_text="Service names covered (snapshot).")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    tax = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    refunded = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=3, default=settings.CLICK_DEFAULT_CURRENCY)
    team_note = models.CharField(max_length=300, blank=True, help_text="Team lead / team assigned, from the provider.")
    cancel_reason = models.CharField(max_length=200, blank=True)
    idempotency_key = models.CharField(max_length=64)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["provider", "event_date"], name="eventhub_booking_day_idx"),
                   models.Index(fields=["customer", "status"], name="eventhub_booking_customer_idx")]
        constraints = [
            models.UniqueConstraint(fields=["customer", "idempotency_key"], name="eventhub_booking_idempotency"),
            models.CheckConstraint(condition=Q(total__gte=0) & Q(refunded__gte=0), name="eventhub_booking_amounts"),
        ]

    def __str__(self):
        return self.number


class Milestone(BaseModel):
    booking = models.ForeignKey(EventBooking, on_delete=models.CASCADE, related_name="milestones")
    key = models.CharField(max_length=40)
    label = models.CharField(max_length=120)
    due_date = models.DateField(null=True, blank=True)
    done_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position"]


class StatusEvent(BaseModel):
    booking = models.ForeignKey(EventBooking, on_delete=models.CASCADE, related_name="events")
    to = models.CharField(max_length=20, choices=BookingStatus.choices)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["created_at"]


class EventReview(BaseModel):
    booking = models.OneToOneField(EventBooking, on_delete=models.CASCADE, related_name="review")
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="event_reviews")
    provider = models.ForeignKey(EventProvider, on_delete=models.CASCADE, related_name="reviews")
    overall = models.PositiveSmallIntegerField()
    quality = models.PositiveSmallIntegerField()
    communication = models.PositiveSmallIntegerField()
    value = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(condition=Q(overall__gte=1, overall__lte=5), name="eventhub_review_range")]
