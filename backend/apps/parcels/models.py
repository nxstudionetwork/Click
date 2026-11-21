"""
Click. Parcel: local pickup-and-drop delivery. A customer books a ParcelOrder (send, receive or store pickup);
the backend prices it (pricing.py), offers the job to eligible delivery partners near the pickup (matching.py),
and the partner moves it through a validated lifecycle in the Partner App (pickup and delivery are confirmed with
PINs the customer holds, never by a frontend button). Payments, notifications, support and partner records are the
shared Click. ones.

Configuration (managed in the admin / Business OS): ParcelServiceArea (where Click. Parcel operates),
ParcelService (express / same day / standard / scheduled with their windows and rules), ParcelVehicle (capacities
and rates), ParcelCategory (what's inside, including restricted categories) and ParcelRule (package rules).
"""

import secrets
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile
from apps.partners.models import Partner

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_parcel_number() -> str:
    return "PCL-" + "".join(secrets.choice(_ALPHABET) for _ in range(8))


def generate_pin() -> str:
    return f"{secrets.randbelow(10000):04d}"


class ParcelServiceArea(BaseModel):
    name = models.CharField(max_length=80)
    city = models.CharField(max_length=80)
    center_lat = models.DecimalField(max_digits=9, decimal_places=6)
    center_lng = models.DecimalField(max_digits=9, decimal_places=6)
    radius_km = models.DecimalField(max_digits=5, decimal_places=1)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name


class ParcelVehicle(BaseModel):
    code = models.SlugField(max_length=20, unique=True)
    name = models.CharField(max_length=40)
    description = models.CharField(max_length=120, blank=True)
    icon = models.CharField(max_length=20, default="bike")
    partner_vehicle_types = models.CharField(max_length=80, help_text="Comma-separated partner vehicle_type values that can carry this.")
    max_weight_kg = models.DecimalField(max_digits=7, decimal_places=1)
    max_length_cm = models.PositiveSmallIntegerField()
    max_width_cm = models.PositiveSmallIntegerField()
    max_height_cm = models.PositiveSmallIntegerField()
    base_fare = models.DecimalField(max_digits=8, decimal_places=2)
    per_km = models.DecimalField(max_digits=8, decimal_places=2)
    minimum_fare = models.DecimalField(max_digits=8, decimal_places=2)
    per_stop = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    average_speed_kmh = models.PositiveSmallIntegerField(default=20)
    is_active = models.BooleanField(default=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "name"]

    def __str__(self) -> str:
        return self.name

    @property
    def vehicle_type_list(self) -> list[str]:
        return [v.strip() for v in self.partner_vehicle_types.split(",") if v.strip()]


class ParcelService(BaseModel):
    class Kind(models.TextChoices):
        EXPRESS = "express", "Express"
        SAME_DAY = "same_day", "Same Day"
        STANDARD = "standard", "Standard"
        SCHEDULED = "scheduled", "Scheduled"

    code = models.CharField(max_length=12, choices=Kind.choices, unique=True)
    name = models.CharField(max_length=40)
    description = models.CharField(max_length=160, blank=True)
    vehicles = models.ManyToManyField(ParcelVehicle, related_name="services")
    price_multiplier = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("1.00"),
                                           help_text="Applied to the trip fare; the difference shows as the service fee.")
    max_distance_km = models.DecimalField(max_digits=5, decimal_places=1, default=Decimal("25"))
    open_hour = models.PositiveSmallIntegerField(default=8, help_text="Local hour pickups start.")
    close_hour = models.PositiveSmallIntegerField(default=21, help_text="Local hour pickups end.")
    order_cutoff_hour = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Same-day: last local hour to book.")
    delivered_by_hour = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Same-day / standard: deliver by this local hour.")
    deliver_days = models.PositiveSmallIntegerField(default=0, help_text="Standard: days after booking the delivery window ends.")
    schedule_days = models.PositiveSmallIntegerField(default=0, help_text="Scheduled: how many days ahead pickups can be booked.")
    schedule_lead_minutes = models.PositiveSmallIntegerField(default=60)
    allow_stops = models.BooleanField(default=False)
    max_stops = models.PositiveSmallIntegerField(default=0)
    cash_allowed = models.BooleanField(default=True, help_text="Pay the partner in cash at pickup (Send only).")
    cancellation_fee = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"),
                                           help_text="Charged when cancelled after a partner is assigned and before pickup.")
    is_active = models.BooleanField(default=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "name"]

    def __str__(self) -> str:
        return self.name


class ParcelCategory(BaseModel):
    code = models.SlugField(max_length=30, unique=True)
    label = models.CharField(max_length=60)
    icon = models.CharField(max_length=20, default="parcel")
    requires_value = models.BooleanField(default=False, help_text="Declared value required (e.g. electronics).")
    is_allowed = models.BooleanField(default=True, help_text="False = restricted: shown as not accepted, never bookable.")
    note = models.CharField(max_length=200, blank=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "label"]
        verbose_name_plural = "parcel categories"


class ParcelRule(BaseModel):
    class Kind(models.TextChoices):
        RULE = "rule", "Package rule"
        PROHIBITED = "prohibited", "Not accepted"

    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.RULE)
    text = models.CharField(max_length=200)
    service = models.ForeignKey(ParcelService, on_delete=models.CASCADE, null=True, blank=True, related_name="rules",
                                help_text="Empty = applies to every service.")
    position = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["kind", "position"]


class SavedRecipient(BaseModel):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="parcel_recipients")
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20)
    alt_phone = models.CharField(max_length=20, blank=True)
    label = models.CharField(max_length=120, blank=True, help_text="Place name, e.g. 'Ravi's office'.")
    address = models.CharField(max_length=300, blank=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    instructions = models.CharField(max_length=200, blank=True)
    times_used = models.PositiveIntegerField(default=0)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_used_at", "name"]
        constraints = [models.UniqueConstraint(fields=["customer", "phone", "label"], name="parcels_recipient_unique")]


class ParcelStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    SEARCHING = "searching", "Finding a delivery partner"
    ASSIGNED = "assigned", "Partner assigned"
    AT_PICKUP = "at_pickup", "Partner at pickup"
    PICKED_UP = "picked_up", "Picked up"
    IN_TRANSIT = "in_transit", "In transit"
    ARRIVING = "arriving", "Near destination"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"
    FAILED = "failed", "Delivery failed"
    NO_PARTNER = "no_partner", "No partner available"


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    ParcelStatus.SCHEDULED: {ParcelStatus.SEARCHING, ParcelStatus.CANCELLED},
    ParcelStatus.SEARCHING: {ParcelStatus.ASSIGNED, ParcelStatus.NO_PARTNER, ParcelStatus.CANCELLED},
    ParcelStatus.ASSIGNED: {ParcelStatus.AT_PICKUP, ParcelStatus.SEARCHING, ParcelStatus.CANCELLED},
    ParcelStatus.AT_PICKUP: {ParcelStatus.PICKED_UP, ParcelStatus.CANCELLED, ParcelStatus.FAILED},
    ParcelStatus.PICKED_UP: {ParcelStatus.IN_TRANSIT},
    ParcelStatus.IN_TRANSIT: {ParcelStatus.ARRIVING, ParcelStatus.DELIVERED, ParcelStatus.FAILED},
    ParcelStatus.ARRIVING: {ParcelStatus.DELIVERED, ParcelStatus.FAILED},
    ParcelStatus.DELIVERED: set(),
    ParcelStatus.CANCELLED: set(),
    ParcelStatus.FAILED: set(),
    ParcelStatus.NO_PARTNER: set(),
}
ACTIVE_STATUSES = [ParcelStatus.SEARCHING, ParcelStatus.ASSIGNED, ParcelStatus.AT_PICKUP, ParcelStatus.PICKED_UP,
                   ParcelStatus.IN_TRANSIT, ParcelStatus.ARRIVING]
FREE_CANCEL = {ParcelStatus.SCHEDULED, ParcelStatus.SEARCHING}
FEE_CANCEL = {ParcelStatus.ASSIGNED, ParcelStatus.AT_PICKUP}


class ParcelOrder(BaseModel):
    class Mode(models.TextChoices):
        SEND = "send", "Send"
        RECEIVE = "receive", "Receive"
        STORE_PICKUP = "store_pickup", "Store pickup"

    class Size(models.TextChoices):
        SMALL = "small", "Small"
        MEDIUM = "medium", "Medium"
        LARGE = "large", "Large"
        CUSTOM = "custom", "Custom"

    number = models.CharField(max_length=16, unique=True, default=generate_parcel_number, editable=False)
    customer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT, related_name="parcels")
    mode = models.CharField(max_length=14, choices=Mode.choices)
    service = models.ForeignKey(ParcelService, on_delete=models.PROTECT, related_name="orders")
    vehicle = models.ForeignKey(ParcelVehicle, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=12, choices=ParcelStatus.choices)

    # Pickup (sender, or the store for store pickup)
    pickup_label = models.CharField(max_length=120)
    pickup_address = models.CharField(max_length=300, blank=True)
    pickup_lat = models.DecimalField(max_digits=9, decimal_places=6)
    pickup_lng = models.DecimalField(max_digits=9, decimal_places=6)
    pickup_name = models.CharField(max_length=120)
    pickup_phone = models.CharField(max_length=20)
    pickup_instructions = models.CharField(max_length=200, blank=True)
    store = models.ForeignKey("stores.Store", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    store_reference = models.CharField(max_length=80, blank=True, help_text="Order / bill reference the store will recognise.")
    # Final drop (recipient, or the customer)
    drop_label = models.CharField(max_length=120)
    drop_address = models.CharField(max_length=300, blank=True)
    drop_lat = models.DecimalField(max_digits=9, decimal_places=6)
    drop_lng = models.DecimalField(max_digits=9, decimal_places=6)
    drop_name = models.CharField(max_length=120)
    drop_phone = models.CharField(max_length=20)
    drop_alt_phone = models.CharField(max_length=20, blank=True)
    drop_instructions = models.CharField(max_length=200, blank=True)

    # Package
    category = models.ForeignKey(ParcelCategory, on_delete=models.PROTECT, related_name="+")
    size = models.CharField(max_length=8, choices=Size.choices)
    weight_kg = models.DecimalField(max_digits=7, decimal_places=2)
    length_cm = models.PositiveSmallIntegerField(null=True, blank=True)
    width_cm = models.PositiveSmallIntegerField(null=True, blank=True)
    height_cm = models.PositiveSmallIntegerField(null=True, blank=True)
    declared_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    package_notes = models.CharField(max_length=300, blank=True)
    contents_declared_at = models.DateTimeField(help_text="When the customer confirmed the contents follow the package rules.")

    # Price (server-computed, snapshotted)
    distance_km = models.DecimalField(max_digits=7, decimal_places=2)
    duration_minutes = models.PositiveIntegerField()
    estimate_basis = models.CharField(max_length=20, default="straight_line")
    fare_base = models.DecimalField(max_digits=10, decimal_places=2)
    fare_distance = models.DecimalField(max_digits=10, decimal_places=2)
    fare_service = models.DecimalField(max_digits=10, decimal_places=2)
    fare_stops = models.DecimalField(max_digits=10, decimal_places=2)
    tax = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField(max_digits=10, decimal_places=2)
    cancellation_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=3, default=settings.CLICK_DEFAULT_CURRENCY)
    payment_method = models.CharField(max_length=30)

    # Timing
    scheduled_for = models.DateTimeField(null=True, blank=True, help_text="Scheduled pickup time.")
    deliver_by = models.DateTimeField(null=True, blank=True, help_text="End of the promised delivery window.")
    partner = models.ForeignKey(Partner, on_delete=models.PROTECT, null=True, blank=True, related_name="parcels")
    assigned_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=200, blank=True)
    failure_reason = models.CharField(max_length=200, blank=True)

    # Verification: shown only to the customer; the partner must enter them (never sent to the Partner App).
    pickup_pin = models.CharField(max_length=4, default=generate_pin)
    delivery_pin = models.CharField(max_length=4, default=generate_pin)
    repeat_of = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    idempotency_key = models.UUIDField()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["customer", "-created_at"], name="parcels_customer_recent_idx"),
                   models.Index(fields=["status", "scheduled_for"], name="parcels_status_sched_idx"),
                   models.Index(fields=["partner", "status"], name="parcels_partner_status_idx")]
        constraints = [
            models.UniqueConstraint(fields=["customer", "idempotency_key"], name="parcels_idempotency_unique"),
            models.CheckConstraint(condition=Q(total__gte=0, weight_kg__gt=0), name="parcels_amounts_positive"),
        ]

    def __str__(self) -> str:
        return self.number


class ParcelStop(BaseModel):
    """An intermediate drop between pickup and the final drop (multi-stop deliveries)."""

    parcel = models.ForeignKey(ParcelOrder, on_delete=models.CASCADE, related_name="stops")
    position = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=120)
    address = models.CharField(max_length=300, blank=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lng = models.DecimalField(max_digits=9, decimal_places=6)
    contact_name = models.CharField(max_length=120, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    instructions = models.CharField(max_length=200, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["position"]
        constraints = [models.UniqueConstraint(fields=["parcel", "position"], name="parcels_stop_position_unique")]


class ParcelStatusEvent(BaseModel):
    parcel = models.ForeignKey(ParcelOrder, on_delete=models.CASCADE, related_name="events")
    from_status = models.CharField(max_length=12, blank=True)
    to_status = models.CharField(max_length=12)
    note = models.CharField(max_length=200, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["created_at"]


class ParcelProof(BaseModel):
    """What was actually verified: the PIN check, when, and where the partner's app last reported being."""

    class Kind(models.TextChoices):
        PICKUP = "pickup", "Pickup"
        STOP = "stop", "Stop delivered"
        DELIVERY = "delivery", "Delivery"

    parcel = models.ForeignKey(ParcelOrder, on_delete=models.CASCADE, related_name="proofs")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    method = models.CharField(max_length=20, help_text="pin | partner_confirmation")
    stop = models.ForeignKey(ParcelStop, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    partner = models.ForeignKey(Partner, on_delete=models.SET_NULL, null=True, related_name="+")
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    location_reported_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]


class ParcelJobOffer(BaseModel):
    class Response(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        EXPIRED = "expired", "Expired"

    parcel = models.ForeignKey(ParcelOrder, on_delete=models.CASCADE, related_name="job_offers")
    partner = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name="parcel_offers")
    distance_km = models.DecimalField(max_digits=7, decimal_places=2)
    response = models.CharField(max_length=10, choices=Response.choices, default=Response.PENDING)

    class Meta:
        ordering = ["created_at"]
        constraints = [models.UniqueConstraint(fields=["parcel", "partner"], name="parcels_offer_unique")]
