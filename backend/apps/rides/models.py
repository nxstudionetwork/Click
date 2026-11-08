"""
Click. Ride: ride types and pricing, ride offers, ride requests/trips (with stops and status history), ratings,
safety events and driver locations. Drivers are Click Partners (apps.partners) in the Transport type; their vehicle
comes from the partner profile (vehicle_type / vehicle_model / vehicle_number / vehicle_color).
"""

import secrets
from decimal import Decimal

from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile
from apps.partners.models import Partner

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_ride_number() -> str:
    return "CLK-R-" + "".join(secrets.choice(_ALPHABET) for _ in range(7))


class RideType(BaseModel):
    """A ride product (Bike, Auto, Cab, XL…) with its pricing and the partner vehicle types that can serve it."""

    code = models.SlugField(max_length=20, unique=True)
    name = models.CharField(max_length=40)
    description = models.CharField(max_length=120, blank=True, help_text="Key benefit, e.g. 'Fastest through traffic'.")
    icon = models.CharField(max_length=20, default="car")
    seats = models.PositiveSmallIntegerField(default=4)
    vehicle_types = models.CharField(max_length=80, help_text="Comma-separated partner vehicle_type values, e.g. 'bike,ev_bike'.")
    base_fare = models.DecimalField(max_digits=8, decimal_places=2)
    per_km = models.DecimalField(max_digits=8, decimal_places=2)
    per_minute = models.DecimalField(max_digits=8, decimal_places=2)
    minimum_fare = models.DecimalField(max_digits=8, decimal_places=2)
    booking_fee = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    per_stop = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    average_speed_kmh = models.PositiveSmallIntegerField(default=20, help_text="City average used for time estimates.")
    is_active = models.BooleanField(default=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "name"]

    def __str__(self) -> str:
        return self.name

    @property
    def vehicle_type_list(self) -> list[str]:
        return [v.strip() for v in self.vehicle_types.split(",") if v.strip()]


class RideOffer(BaseModel):
    """A ride promotion applied by the server at booking (percent with optional cap, or flat)."""

    class DiscountType(models.TextChoices):
        PERCENT = "percent", "Percent off"
        FLAT = "flat", "Flat amount off"

    title = models.CharField(max_length=80)
    description = models.CharField(max_length=200, blank=True)
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices)
    discount_value = models.DecimalField(max_digits=8, decimal_places=2)
    max_discount = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    min_fare = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    ride_types = models.ManyToManyField(RideType, blank=True, related_name="offers", help_text="Empty = every ride type.")
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return self.title


class RideStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    SEARCHING = "searching", "Finding your ride"
    DRIVER_ASSIGNED = "driver_assigned", "Driver on the way"
    DRIVER_ARRIVED = "driver_arrived", "Driver has arrived"
    IN_PROGRESS = "in_progress", "Trip in progress"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
    NO_DRIVER = "no_driver", "No driver found"


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    RideStatus.SCHEDULED: {RideStatus.SEARCHING, RideStatus.CANCELLED},
    RideStatus.SEARCHING: {RideStatus.DRIVER_ASSIGNED, RideStatus.NO_DRIVER, RideStatus.CANCELLED},
    RideStatus.DRIVER_ASSIGNED: {RideStatus.DRIVER_ARRIVED, RideStatus.CANCELLED, RideStatus.SEARCHING},
    RideStatus.DRIVER_ARRIVED: {RideStatus.IN_PROGRESS, RideStatus.CANCELLED},
    RideStatus.IN_PROGRESS: {RideStatus.COMPLETED},
    RideStatus.COMPLETED: set(),
    RideStatus.CANCELLED: set(),
    RideStatus.NO_DRIVER: set(),
}
ACTIVE_STATUSES = {RideStatus.SEARCHING, RideStatus.DRIVER_ASSIGNED, RideStatus.DRIVER_ARRIVED, RideStatus.IN_PROGRESS}
CUSTOMER_CANCELLABLE = {RideStatus.SCHEDULED, RideStatus.SEARCHING, RideStatus.DRIVER_ASSIGNED, RideStatus.DRIVER_ARRIVED}


class Ride(BaseModel):
    """One ride request and its trip. Fare is computed and locked by the server at booking (upfront pricing)."""

    number = models.CharField(max_length=16, unique=True, default=generate_ride_number, editable=False)
    customer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT, related_name="rides")
    ride_type = models.ForeignKey(RideType, on_delete=models.PROTECT, related_name="rides")
    status = models.CharField(max_length=20, choices=RideStatus.choices, default=RideStatus.SEARCHING)
    # Passenger (when booked for someone else). Only name and phone, never another customer's account data.
    passenger_name = models.CharField(max_length=120, blank=True)
    passenger_phone = models.CharField(max_length=20, blank=True)

    pickup_label = models.CharField(max_length=120)
    pickup_address = models.CharField(max_length=300, blank=True)
    pickup_lat = models.DecimalField(max_digits=9, decimal_places=6)
    pickup_lng = models.DecimalField(max_digits=9, decimal_places=6)
    drop_label = models.CharField(max_length=120)
    drop_address = models.CharField(max_length=300, blank=True)
    drop_lat = models.DecimalField(max_digits=9, decimal_places=6)
    drop_lng = models.DecimalField(max_digits=9, decimal_places=6)

    distance_km = models.DecimalField(max_digits=7, decimal_places=2)
    duration_minutes = models.PositiveIntegerField()
    fare_base = models.DecimalField(max_digits=10, decimal_places=2)
    fare_distance = models.DecimalField(max_digits=10, decimal_places=2)
    fare_time = models.DecimalField(max_digits=10, decimal_places=2)
    fare_fees = models.DecimalField(max_digits=10, decimal_places=2, help_text="Booking fee + stop fees.")
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    offer = models.ForeignKey(RideOffer, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    offer_title = models.CharField(max_length=80, blank=True)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    payment_method = models.CharField(max_length=30)

    scheduled_for = models.DateTimeField(null=True, blank=True)
    driver = models.ForeignKey(Partner, on_delete=models.PROTECT, null=True, blank=True, related_name="rides")
    driver_assigned_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=200, blank=True)
    idempotency_key = models.UUIDField()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["customer", "-created_at"], name="rides_customer_recent_idx"),
                   models.Index(fields=["status"], name="rides_status_idx")]
        constraints = [
            models.UniqueConstraint(fields=["customer", "idempotency_key"], name="rides_customer_idempotency_unique"),
            models.CheckConstraint(condition=Q(total__gte=0), name="rides_total_non_negative"),
        ]

    def __str__(self) -> str:
        return self.number


class RideStop(BaseModel):
    ride = models.ForeignKey(Ride, on_delete=models.CASCADE, related_name="stops")
    position = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=120)
    address = models.CharField(max_length=300, blank=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lng = models.DecimalField(max_digits=9, decimal_places=6)

    class Meta:
        ordering = ["position"]
        constraints = [models.UniqueConstraint(fields=["ride", "position"], name="rides_stop_position_unique")]


class RideStatusEvent(BaseModel):
    ride = models.ForeignKey(Ride, on_delete=models.CASCADE, related_name="events")
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["created_at"]


class RideDriverOffer(BaseModel):
    """A ride offered to a nearby eligible driver by the matching engine (the driver accepts or declines)."""

    class Response(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        EXPIRED = "expired", "Expired"

    ride = models.ForeignKey(Ride, on_delete=models.CASCADE, related_name="driver_offers")
    driver = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name="ride_offers")
    distance_km = models.DecimalField(max_digits=7, decimal_places=2)
    response = models.CharField(max_length=10, choices=Response.choices, default=Response.PENDING)

    class Meta:
        ordering = ["distance_km"]
        constraints = [models.UniqueConstraint(fields=["ride", "driver"], name="rides_driver_offer_unique")]


class DriverLocation(BaseModel):
    """Last location reported by a driver's Partner App. Customers only see it as live when it is fresh."""

    driver = models.OneToOneField(Partner, on_delete=models.CASCADE, related_name="ride_location")
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lng = models.DecimalField(max_digits=9, decimal_places=6)
    reported_at = models.DateTimeField()


class RideRating(BaseModel):
    ride = models.OneToOneField(Ride, on_delete=models.CASCADE, related_name="rating")
    driver = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name="ride_ratings")
    stars = models.PositiveSmallIntegerField()
    comment = models.CharField(max_length=500, blank=True)
    compliment = models.CharField(max_length=40, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(stars__gte=1, stars__lte=5), name="rides_rating_range")]


class RideSafetyEvent(BaseModel):
    """Safety actions taken during a ride (SOS pressed, trip shared, issue reported) for follow-up by Click."""

    class Kind(models.TextChoices):
        SOS = "sos", "Emergency"
        SHARE = "share", "Trip shared"
        REPORT = "report", "Issue reported"

    ride = models.ForeignKey(Ride, on_delete=models.CASCADE, related_name="safety_events")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    note = models.CharField(max_length=500, blank=True)
