"""
Click. Bookings — places and experiences you can visit or book: temples and spiritual places, tourist attractions,
parks and fun, and experiences (activities, tours, boat rides, workshops). Bookings is also the central hub that lists
every reservation the customer holds across Click. (apps.experiences.hub reads each domain's own records — nothing is
copied).

  Attraction        a place or experience: kind (temple, museum, fort, water park, city tour…), location, verified
                    visitor information, facilities, rules, FAQs. `bookable` = Click. can actually sell it (an onboarded
                    provider manages its tickets); otherwise it is information only and `official_source` says where it
                    is booked — Click. never pretends to sell it
  Offering          what can be booked: an entry ticket, a darshan, a seva / pooja, an activity, a tour package; its
                    booking model (all-day ticket or time slot), days, slot times and capacity, pickup points
  Price             the ticket types the provider sells for an offering (adult, child, senior, student, family…)
  Closure           dates the provider is closed
  ExperienceBooking a reservation with a price snapshot, visitors, the policy as agreed, payment through the shared
  (+ StatusEvent,   Payment / Click. Wallet, and an entry code the provider verifies in the Click. Partner App
   ExperienceReview)
  ExperienceOffer   offers configured by Click. / the provider; always computed on the server
"""

import secrets
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def booking_number() -> str:
    return "BKG-" + "".join(secrets.choice(_ALPHABET) for _ in range(8))


def entry_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(8))


class Group(models.TextChoices):
    SPIRITUAL = "spiritual", "Temples & spiritual"
    TOURIST = "tourist", "Tourist spots"
    PARKS = "parks", "Parks & fun"
    EXPERIENCES = "experiences", "Experiences"


KINDS = {
    Group.SPIRITUAL: [("temple", "Temple"), ("pilgrimage", "Pilgrimage site")],
    Group.TOURIST: [("monument", "Monument"), ("heritage", "Heritage site"), ("museum", "Museum"), ("fort", "Fort"), ("palace", "Palace"),
                    ("gallery", "Art gallery"), ("science_centre", "Science centre"), ("planetarium", "Planetarium"), ("viewpoint", "Viewpoint"),
                    ("beach", "Beach")],
    Group.PARKS: [("theme_park", "Theme park"), ("water_park", "Water park"), ("zoo", "Zoo"), ("aquarium", "Aquarium"), ("garden", "Botanical garden"),
                  ("nature_park", "Nature park"), ("adventure_park", "Adventure park"), ("ropeway", "Ropeway")],
    Group.EXPERIENCES: [("activity", "Activity"), ("adventure", "Adventure"), ("city_tour", "City tour"), ("walking_tour", "Walking tour"),
                        ("tour", "Guided tour"), ("boat_ride", "Boat ride"), ("cruise", "Cruise"), ("workshop", "Workshop"),
                        ("food", "Food experience"), ("cultural", "Cultural experience")],
}
KIND_CHOICES = [k for group in KINDS.values() for k in group]
GROUP_OF = {k: g for g, kinds in KINDS.items() for k, _ in kinds}


class Attraction(BaseModel):
    class Setting(models.TextChoices):
        INDOOR = "indoor", "Indoor"
        OUTDOOR = "outdoor", "Outdoor"
        BOTH = "both", "Indoor & outdoor"

    slug = models.SlugField(max_length=140, unique=True)
    name = models.CharField(max_length=140)
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    group = models.CharField(max_length=12, choices=Group.choices, editable=False)
    city = models.CharField(max_length=80)
    region = models.CharField(max_length=80, blank=True, help_text="State.")
    area = models.CharField(max_length=120, blank=True)
    address = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    tagline = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    deity = models.CharField(max_length=80, blank=True, help_text="Temples: the presiding deity, as the temple states it.")
    highlights = models.JSONField(default=list, blank=True)
    facilities = models.JSONField(default=list, blank=True)
    accessibility = models.JSONField(default=list, blank=True)
    rules = models.JSONField(default=list, blank=True, help_text="Visitor rules the provider publishes.")
    dress_code = models.CharField(max_length=200, blank=True)
    prohibited = models.JSONField(default=list, blank=True)
    age_note = models.CharField(max_length=160, blank=True)
    opening = models.JSONField(default=dict, blank=True, help_text='Verified hours only: {"days": [0..6], "open": "09:00", "close": "18:00", "note": ""}.')
    duration_minutes = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Typical visit length.")
    setting = models.CharField(max_length=8, choices=Setting.choices, default=Setting.OUTDOOR)
    family_friendly = models.BooleanField(default=False)
    kids_friendly = models.BooleanField(default=False)
    faqs = models.JSONField(default=list, blank=True, help_text='[{"q": "", "a": ""}]')
    provider = models.ForeignKey("partners.Partner", on_delete=models.SET_NULL, null=True, blank=True, related_name="attractions",
                                 help_text="The onboarded operator who sells and verifies tickets through Click.")
    bookable = models.BooleanField(default=False, help_text="Click. sells this (needs a provider and live offerings).")
    verified_provider = models.BooleanField(default=False)
    instant_confirmation = models.BooleanField(default=True)
    official_source = models.CharField(max_length=200, blank=True, help_text="Information-only places: where bookings are actually made.")
    official_url = models.URLField(blank=True)
    refundable = models.BooleanField(default=True)
    free_cancel_hours = models.PositiveSmallIntegerField(default=24, help_text="Free cancellation until this many hours before the visit.")
    cancel_fee_percent = models.PositiveSmallIntegerField(default=100, help_text="Kept when cancelling after the free window.")
    accent = models.CharField(max_length=9, default="#b45309")
    is_listed = models.BooleanField(default=True)
    # Maintained from verified-visit reviews only.
    rating_average = models.DecimalField(max_digits=2, decimal_places=1, default=0)
    rating_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["group", "city"], name="exp_attraction_group_city_idx"),
                   models.Index(fields=["kind"], name="exp_attraction_kind_idx")]
        constraints = [models.CheckConstraint(condition=Q(rating_average__gte=0, rating_average__lte=5), name="exp_attraction_rating_range"),
                       models.CheckConstraint(condition=Q(cancel_fee_percent__lte=100), name="exp_attraction_fee_range")]

    def save(self, *args, **kwargs):
        self.group = GROUP_OF.get(self.kind, Group.TOURIST)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class AttractionImage(BaseModel):
    """Photos the provider uploaded (none are seeded: no generated imagery)."""

    attraction = models.ForeignKey(Attraction, on_delete=models.CASCADE, related_name="images")
    url = models.URLField()
    caption = models.CharField(max_length=140, blank=True)
    credit = models.CharField(max_length=140, blank=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["attraction", "position"]


class Offering(BaseModel):
    class Kind(models.TextChoices):
        ENTRY = "entry", "Entry ticket"
        DARSHAN = "darshan", "Darshan"
        SEVA = "seva", "Seva"
        POOJA = "pooja", "Pooja"
        ACTIVITY = "activity", "Activity"
        TOUR = "tour", "Tour"
        PACKAGE = "package", "Package"

    class Model(models.TextChoices):
        TICKET = "ticket", "Any time that day"
        SLOT = "slot", "Time slot"

    attraction = models.ForeignKey(Attraction, on_delete=models.CASCADE, related_name="offerings")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    booking_model = models.CharField(max_length=6, choices=Model.choices)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=400, blank=True)
    includes = models.JSONField(default=list, blank=True)
    duration_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    days = models.JSONField(default=list, help_text="Weekdays it runs, 0 = Monday.")
    slot_times = models.JSONField(default=list, blank=True, help_text='Slot model: ["06:00", "09:30"].')
    capacity = models.PositiveIntegerField(help_text="Visitors per slot (slot model) or per day (ticket model).")
    max_per_booking = models.PositiveSmallIntegerField(default=10)
    min_age = models.PositiveSmallIntegerField(null=True, blank=True)
    pickup_points = models.JSONField(default=list, blank=True, help_text="Tours: where the provider picks up.")
    requirements = models.CharField(max_length=200, blank=True, help_text="e.g. photo ID of each devotee at entry.")
    tax_percent = models.DecimalField(max_digits=4, decimal_places=1, default=Decimal("0"), help_text="GST as the provider applies it.")
    book_ahead_days = models.PositiveSmallIntegerField(default=30)
    is_active = models.BooleanField(default=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["attraction", "position"]

    def __str__(self) -> str:
        return f"{self.attraction.name} · {self.name}"


class Price(BaseModel):
    class Visitor(models.TextChoices):
        ADULT = "adult", "Adult"
        CHILD = "child", "Child"
        SENIOR = "senior", "Senior"
        STUDENT = "student", "Student"
        INFANT = "infant", "Infant"
        FAMILY = "family", "Family"
        DEVOTEE = "devotee", "Devotee"
        PARTICIPANT = "participant", "Participant"

    offering = models.ForeignKey(Offering, on_delete=models.CASCADE, related_name="prices")
    visitor = models.CharField(max_length=12, choices=Visitor.choices)
    label = models.CharField(max_length=60, blank=True)
    note = models.CharField(max_length=100, blank=True, help_text="e.g. '3–12 years', 'student ID at entry'.")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    units = models.PositiveSmallIntegerField(default=1, help_text="Places it uses (family = 4, infant = 0).")
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["offering", "position"]
        constraints = [models.UniqueConstraint(fields=["offering", "visitor"], name="exp_price_visitor_unique"),
                       models.CheckConstraint(condition=Q(amount__gte=0), name="exp_price_non_negative")]


class Closure(BaseModel):
    attraction = models.ForeignKey(Attraction, on_delete=models.CASCADE, related_name="closures")
    date = models.DateField()
    reason = models.CharField(max_length=120, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["attraction", "date"], name="exp_closure_unique")]


class BookingStatus(models.TextChoices):
    PENDING_PAYMENT = "pending_payment", "Payment pending"
    CONFIRMED = "confirmed", "Confirmed"
    CANCELLED = "cancelled", "Cancelled"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Payment failed"


ACTIVE = (BookingStatus.PENDING_PAYMENT, BookingStatus.CONFIRMED)


class ExperienceBooking(BaseModel):
    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Payment pending"
        PAID = "paid", "Paid"
        FREE = "free", "No payment needed"
        REFUNDED = "refunded", "Refunded"
        PARTLY_REFUNDED = "partly_refunded", "Partly refunded"
        NOT_CHARGED = "not_charged", "Not charged"

    number = models.CharField(max_length=16, unique=True, default=booking_number, editable=False)
    customer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT, related_name="experience_bookings")
    attraction = models.ForeignKey(Attraction, on_delete=models.PROTECT, related_name="bookings")
    offering = models.ForeignKey(Offering, on_delete=models.PROTECT, related_name="bookings")
    visit_date = models.DateField()
    slot_time = models.TimeField(null=True, blank=True)
    lines = models.JSONField(help_text='[{"visitor", "label", "qty", "unit", "amount", "units"}]')
    visitors = models.PositiveSmallIntegerField(help_text="People on the booking.")
    units = models.PositiveSmallIntegerField(help_text="Capacity used.")
    lead_name = models.CharField(max_length=120)
    lead_phone = models.CharField(max_length=20)
    lead_email = models.EmailField(blank=True)
    visitor_names = models.JSONField(default=list, blank=True, help_text="Names only, when the provider requires them.")
    pickup_point = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=BookingStatus.choices, default=BookingStatus.PENDING_PAYMENT)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    # Snapshot of what was agreed.
    title = models.CharField(max_length=200)
    refundable = models.BooleanField()
    free_cancel_until = models.DateTimeField(null=True, blank=True)
    cancel_fee_percent = models.PositiveSmallIntegerField()
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    offer_title = models.CharField(max_length=100, blank=True)
    tax = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    refunded = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=3, default=settings.CLICK_DEFAULT_CURRENCY)
    hold_expires_at = models.DateTimeField(null=True, blank=True)
    entry_code = models.CharField(max_length=10, blank=True, help_text="Issued on confirmation; the provider verifies it in the Partner App.")
    idempotency_key = models.CharField(max_length=64)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=200, blank=True)
    cancelled_by_provider = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["offering", "visit_date", "slot_time", "status"], name="exp_booking_capacity_idx"),
                   models.Index(fields=["customer", "status"], name="exp_booking_customer_idx")]
        constraints = [
            models.UniqueConstraint(fields=["customer", "idempotency_key"], name="exp_booking_idempotency"),
            models.CheckConstraint(condition=Q(total__gte=0) & Q(refunded__gte=0), name="exp_booking_amounts"),
        ]

    def __str__(self) -> str:
        return self.number


class StatusEvent(BaseModel):
    booking = models.ForeignKey(ExperienceBooking, on_delete=models.CASCADE, related_name="events")
    to = models.CharField(max_length=20, choices=BookingStatus.choices)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["created_at"]


class ExperienceReview(BaseModel):
    booking = models.OneToOneField(ExperienceBooking, on_delete=models.CASCADE, related_name="review")
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="experience_reviews")
    attraction = models.ForeignKey(Attraction, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(condition=Q(rating__gte=1, rating__lte=5), name="exp_review_rating_range")]


class ExperienceOffer(BaseModel):
    attraction = models.ForeignKey(Attraction, on_delete=models.CASCADE, null=True, blank=True, related_name="offers",
                                   help_text="Blank = any bookable place in `group` (or everywhere).")
    group = models.CharField(max_length=12, choices=Group.choices, blank=True)
    title = models.CharField(max_length=100)
    code = models.CharField(max_length=20, blank=True, help_text="Blank = applied automatically when it qualifies.")
    percent = models.PositiveSmallIntegerField()
    max_discount = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    min_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-percent"]
        constraints = [models.CheckConstraint(condition=Q(percent__gte=1, percent__lte=90), name="exp_offer_percent_range")]
