"""
Click. Services: local professionals for home, personal, repair and moving work.

A professional is a Partner (apps.partners) in a services category; this app adds what customers need to choose and
book them, and the job lifecycle:

  ServiceCategory / ServiceJob   the data-driven catalog (what we help with, common jobs, pricing model)
  ProviderProfile                the professional's customer-facing profile on top of Partner/PartnerProfile:
                                 photo, experience, skills, languages, about; counters maintained from real jobs
  ProviderService                which categories a professional does, with their own price per job where set
  ProviderAvailability           weekly working hours (slots never fall outside them)
  ProviderCertificate            certificates, shown only once Click verified them
  ProviderPortfolio              work photos the professional uploaded
  ServiceBooking (+ Offer, Quote, StatusEvent, Attachment, Review)
                                 a job: offered to the chosen professional (or the nearest available ones), accepted
                                 in the Partner App, quotes approved by the customer, completed, paid, reviewed
  ServiceOffer                   promotions configured by Click (Business OS)
  ServiceNeed                    "Can't find your service?" requests for Click to review

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


def generate_booking_number() -> str:
    return "SRV-" + "".join(secrets.choice(_ALPHABET) for _ in range(8))


class ServiceCategory(BaseModel):
    class Group(models.TextChoices):
        HOME = "home", "Home care"
        PERSONAL = "personal", "Personal services"
        REPAIR = "repair", "Repair & installation"
        MOVING = "moving", "Moving & assistance"
        OTHER = "other", "Other services"

    slug = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=60)
    profession = models.CharField(max_length=60, help_text="What a professional in this category is called, e.g. 'Plumber'.")
    group = models.CharField(max_length=10, choices=Group.choices)
    icon = models.CharField(max_length=20, default="wrench")
    accent = models.CharField(max_length=7, default="#14b8a6", help_text="Hex accent used on this category's cards.")
    summary = models.CharField(max_length=200, blank=True, help_text="What we can help with.")
    synonyms = models.CharField(max_length=400, blank=True, help_text="Comma-separated search words, e.g. 'leak, tap, pipe'.")
    partner_categories = models.CharField(max_length=200, blank=True,
                                          help_text="Partner category slugs whose professionals do this work (comma-separated).")
    position = models.PositiveSmallIntegerField(default=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "name"]
        verbose_name_plural = "service categories"

    def __str__(self) -> str:
        return self.name


class ServiceJob(BaseModel):
    """A common job in a category, with how it is priced."""

    class Pricing(models.TextChoices):
        FIXED = "fixed", "Fixed price"
        STARTING = "starting", "Starting price (final after inspection)"
        HOURLY = "hourly", "Hourly"
        QUOTE = "quote", "Quote after inspection"

    category = models.ForeignKey(ServiceCategory, on_delete=models.CASCADE, related_name="jobs")
    slug = models.SlugField(max_length=80)
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=300, blank=True)
    includes = models.JSONField(default=list, blank=True)
    excludes = models.JSONField(default=list, blank=True, help_text="Not included / may cost extra (e.g. spare parts).")
    pricing = models.CharField(max_length=10, choices=Pricing.choices)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                help_text="Fixed price, starting price or hourly rate (empty for quote jobs).")
    min_hours = models.PositiveSmallIntegerField(default=1, help_text="Hourly jobs: minimum billed hours.")
    inspection_fee = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"),
                                         help_text="Charged only if the customer declines the quote after an inspection visit.")
    duration_minutes = models.PositiveSmallIntegerField(default=60, help_text="Typical time on site (blocks the schedule).")
    instant = models.BooleanField(default=True, help_text="Can be booked for 'as soon as possible'.")
    schedulable = models.BooleanField(default=True)
    position = models.PositiveSmallIntegerField(default=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category", "position", "name"]
        constraints = [models.UniqueConstraint(fields=["category", "slug"], name="pro_job_slug_unique")]

    def __str__(self) -> str:
        return f"{self.category.name}: {self.name}"


class ProviderProfile(BaseModel):
    partner = models.OneToOneField(Partner, on_delete=models.CASCADE, related_name="pro")
    category = models.ForeignKey(ServiceCategory, on_delete=models.PROTECT, related_name="primary_providers", help_text="Main profession.")
    photo = models.ImageField(upload_to="providers/%Y/%m/", blank=True, help_text="Uploaded by the professional; re-encoded WebP.")
    about = models.CharField(max_length=600, blank=True)
    experience_years = models.PositiveSmallIntegerField(null=True, blank=True)
    skills = models.JSONField(default=list, blank=True)
    languages = models.JSONField(default=list, blank=True)
    instant_enabled = models.BooleanField(default=True, help_text="Accepts 'as soon as possible' jobs while available.")
    quote_jobs = models.BooleanField(default=True, help_text="Accepts jobs priced after inspection.")
    # Maintained from real records (completed jobs, published reviews); never edited by hand.
    rating_average = models.DecimalField(max_digits=2, decimal_places=1, default=Decimal("0"))
    rating_count = models.PositiveIntegerField(default=0)
    jobs_completed = models.PositiveIntegerField(default=0)
    is_listed = models.BooleanField(default=True, help_text="Shown to customers (when the partner can operate).")

    def __str__(self) -> str:
        return f"{self.partner.business_name} ({self.category.profession})"


class ProviderService(BaseModel):
    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name="services")
    category = models.ForeignKey(ServiceCategory, on_delete=models.CASCADE, related_name="providers")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "category"], name="pro_service_unique")]


class ProviderJobPrice(BaseModel):
    """The professional's own price for a job (overrides the catalog price; same pricing model)."""

    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name="prices")
    job = models.ForeignKey(ServiceJob, on_delete=models.CASCADE, related_name="provider_prices")
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "job"], name="pro_price_unique"),
                       models.CheckConstraint(condition=Q(price__gt=0), name="pro_price_positive")]


class ProviderAvailability(BaseModel):
    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name="hours")
    weekday = models.PositiveSmallIntegerField(help_text="0 = Monday … 6 = Sunday")
    starts_at = models.TimeField()
    ends_at = models.TimeField()

    class Meta:
        ordering = ["weekday", "starts_at"]
        constraints = [models.CheckConstraint(condition=Q(ends_at__gt=models.F("starts_at")), name="pro_hours_window"),
                       models.CheckConstraint(condition=Q(weekday__lte=6), name="pro_hours_weekday")]


class ProviderCertificate(BaseModel):
    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name="certificates")
    name = models.CharField(max_length=120)
    issuer = models.CharField(max_length=120, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True, help_text="Set by Click after checking the document.")


class ProviderPortfolio(BaseModel):
    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name="portfolio")
    category = models.ForeignKey(ServiceCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    renditions = models.JSONField(default=dict, blank=True, editable=False)
    width = models.PositiveIntegerField(null=True, blank=True, editable=False)
    height = models.PositiveIntegerField(null=True, blank=True, editable=False)
    caption = models.CharField(max_length=160, blank=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "-created_at"]


class ServiceOffer(BaseModel):
    class Kind(models.TextChoices):
        PERCENT = "percent", "Percent off"
        FLAT = "flat", "Flat amount off"

    title = models.CharField(max_length=80)
    description = models.CharField(max_length=200, blank=True)
    category = models.ForeignKey(ServiceCategory, on_delete=models.CASCADE, null=True, blank=True, related_name="offers",
                                 help_text="Empty = every service.")
    kind = models.CharField(max_length=8, choices=Kind.choices)
    value = models.DecimalField(max_digits=8, decimal_places=2)
    max_discount = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    min_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    first_booking_only = models.BooleanField(default=False)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]


class BookingStatus(models.TextChoices):
    REQUESTED = "requested", "Finding your professional"
    CONFIRMED = "confirmed", "Booking confirmed"
    ON_THE_WAY = "on_the_way", "Professional on the way"
    ARRIVED = "arrived", "Professional arrived"
    QUOTE_PENDING = "quote_pending", "Quote waiting for your approval"
    IN_PROGRESS = "in_progress", "Work in progress"
    COMPLETED = "completed", "Work completed · payment due"
    PAID = "paid", "Paid"
    CANCELLED = "cancelled", "Cancelled"
    UNASSIGNED = "unassigned", "No professional accepted"


ALLOWED_TRANSITIONS = {
    BookingStatus.REQUESTED: {BookingStatus.CONFIRMED, BookingStatus.CANCELLED, BookingStatus.UNASSIGNED},
    BookingStatus.CONFIRMED: {BookingStatus.ON_THE_WAY, BookingStatus.CANCELLED},
    BookingStatus.ON_THE_WAY: {BookingStatus.ARRIVED, BookingStatus.CANCELLED},
    BookingStatus.ARRIVED: {BookingStatus.QUOTE_PENDING, BookingStatus.IN_PROGRESS, BookingStatus.CANCELLED},
    BookingStatus.QUOTE_PENDING: {BookingStatus.IN_PROGRESS, BookingStatus.ARRIVED, BookingStatus.COMPLETED, BookingStatus.CANCELLED},
    BookingStatus.IN_PROGRESS: {BookingStatus.QUOTE_PENDING, BookingStatus.COMPLETED},
    BookingStatus.COMPLETED: {BookingStatus.PAID},
    BookingStatus.PAID: set(),
    BookingStatus.CANCELLED: set(),
    BookingStatus.UNASSIGNED: set(),
}
ACTIVE = [BookingStatus.REQUESTED, BookingStatus.CONFIRMED, BookingStatus.ON_THE_WAY, BookingStatus.ARRIVED,
          BookingStatus.QUOTE_PENDING, BookingStatus.IN_PROGRESS]
ON_JOB = [BookingStatus.ON_THE_WAY, BookingStatus.ARRIVED, BookingStatus.QUOTE_PENDING, BookingStatus.IN_PROGRESS]


class ServiceBooking(BaseModel):
    class Mode(models.TextChoices):
        NOW = "now", "As soon as possible"
        SCHEDULED = "scheduled", "Scheduled"

    number = models.CharField(max_length=16, unique=True, default=generate_booking_number, editable=False)
    customer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT, related_name="service_bookings")
    provider = models.ForeignKey(ProviderProfile, on_delete=models.PROTECT, null=True, blank=True, related_name="bookings")
    requested_provider = models.ForeignKey(ProviderProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                           help_text="The professional the customer chose (empty = nearest available).")
    category = models.ForeignKey(ServiceCategory, on_delete=models.PROTECT, related_name="bookings")
    job = models.ForeignKey(ServiceJob, on_delete=models.PROTECT, related_name="bookings")
    mode = models.CharField(max_length=10, choices=Mode.choices)
    status = models.CharField(max_length=14, choices=BookingStatus.choices, default=BookingStatus.REQUESTED)
    scheduled_start = models.DateTimeField(null=True, blank=True)
    scheduled_end = models.DateTimeField(null=True, blank=True)

    address = models.JSONField(help_text="Snapshot of the service address.")
    address_ref = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lng = models.DecimalField(max_digits=9, decimal_places=6)
    description = models.CharField(max_length=1000, blank=True)

    pricing = models.CharField(max_length=10, choices=ServiceJob.Pricing.choices)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Price / starting price / hourly rate.")
    hours = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Hourly jobs: hours booked (the most billed without approval).")
    inspection_fee = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    agreed_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                        help_text="What the customer has agreed to pay so far (estimate, or an approved quote).")
    billed_hours = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    offer = models.ForeignKey(ServiceOffer, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    offer_title = models.CharField(max_length=80, blank=True)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Final amount, set at completion.")
    currency = models.CharField(max_length=3, default=settings.CLICK_DEFAULT_CURRENCY)
    payment_method = models.CharField(max_length=30, blank=True)

    eta_minutes = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Estimate at acceptance (distance-based).")
    accepted_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=200, blank=True)
    offers_expire_at = models.DateTimeField(null=True, blank=True)
    rebook_of = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    idempotency_key = models.UUIDField()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["customer", "-created_at"], name="pro_booking_customer_idx"),
                   models.Index(fields=["provider", "status"], name="pro_booking_provider_idx"),
                   models.Index(fields=["status", "offers_expire_at"], name="pro_booking_expiry_idx")]
        constraints = [models.UniqueConstraint(fields=["customer", "idempotency_key"], name="pro_booking_idempotency")]

    def __str__(self) -> str:
        return self.number


class ServiceJobOffer(BaseModel):
    class Response(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        EXPIRED = "expired", "Expired"

    booking = models.ForeignKey(ServiceBooking, on_delete=models.CASCADE, related_name="job_offers")
    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name="job_offers")
    distance_km = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    response = models.CharField(max_length=10, choices=Response.choices, default=Response.PENDING)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["booking", "provider"], name="pro_offer_unique")]


class ServiceQuote(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for approval"
        APPROVED = "approved", "Approved"
        DECLINED = "declined", "Declined"

    booking = models.ForeignKey(ServiceBooking, on_delete=models.CASCADE, related_name="quotes")
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="New total for the job (before tax).")
    note = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="pro_quote_positive"),
                       models.UniqueConstraint(fields=["booking"], condition=Q(status="pending"), name="pro_one_pending_quote")]


class ServiceStatusEvent(BaseModel):
    booking = models.ForeignKey(ServiceBooking, on_delete=models.CASCADE, related_name="events")
    from_status = models.CharField(max_length=14, blank=True)
    to_status = models.CharField(max_length=14)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["created_at"]


class ServiceAttachment(BaseModel):
    """A customer's photo of the problem (or of a ServiceNeed). Uploaded before booking, then attached to it."""

    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="service_attachments")
    booking = models.ForeignKey(ServiceBooking, on_delete=models.CASCADE, null=True, blank=True, related_name="attachments")
    need = models.ForeignKey("ServiceNeed", on_delete=models.CASCADE, null=True, blank=True, related_name="attachments")
    renditions = models.JSONField(default=dict, blank=True, editable=False)
    width = models.PositiveIntegerField(null=True, blank=True, editable=False)
    height = models.PositiveIntegerField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["created_at"]


class ServiceReview(BaseModel):
    class Status(models.TextChoices):
        PUBLISHED = "published", "Published"
        HIDDEN = "hidden", "Hidden by moderation"

    booking = models.OneToOneField(ServiceBooking, on_delete=models.CASCADE, related_name="review")
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="service_reviews")
    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name="reviews")
    overall = models.PositiveSmallIntegerField()
    quality = models.PositiveSmallIntegerField()
    behaviour = models.PositiveSmallIntegerField()
    timeliness = models.PositiveSmallIntegerField()
    comment = models.CharField(max_length=1000, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PUBLISHED)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(
            condition=Q(overall__gte=1, overall__lte=5, quality__gte=1, quality__lte=5, behaviour__gte=1, behaviour__lte=5,
                        timeliness__gte=1, timeliness__lte=5), name="pro_review_ranges")]


class ServiceNeed(BaseModel):
    """'Can't find your service?' — reviewed by Click (Business OS) to decide whether to onboard a partner."""

    class Status(models.TextChoices):
        NEW = "new", "Received"
        REVIEWING = "reviewing", "Being reviewed"
        CONTACTED = "contacted", "We contacted you"
        CLOSED = "closed", "Closed"

    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="service_needs")
    text = models.CharField(max_length=600)
    address = models.JSONField(default=dict, blank=True)
    preferred_time = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW)

    class Meta:
        ordering = ["-created_at"]
