"""
Click. Hotels: find, compare and book accommodation. Separate from Travel (transport) and Showtime (entertainment).

  Destination / Landmark      where people search (city, area) and the real points distances are measured from
                              (city centre, airport, station, beach, landmarks); `tags` drive discovery collections
  Amenity                     a registry for property and room amenities (filters map to these slugs)
  HotelProperty               a Partner (apps.partners, Hotels & Venues type) listed on Click.: type, legitimate star
                              rating (only when set), address/pin, policies, check-in/out, payment options; ratings
                              are recomputed from verified-stay reviews only
  HotelImage                  photos the property uploaded (renditions; none are seeded)
  RoomType / RatePlan         sellable rooms (beds, occupancy, size, units) and their rate plans (meal plan,
                              refundability, free-cancellation window, pay now / at property, nightly price)
  RoomInventory               per-date overrides: units, closures, price — availability = units − active bookings
  HotelOffer                  offers Click / the property configured (early booking, last minute, weekend, member,
                              coupon); discounts are always computed on the server
  HotelBooking (+ StatusEvent, Review)
                              a reservation with a full price snapshot, guest details, the cancellation policy as
                              agreed, payment through the shared Payment/Click. Wallet or at the property

Inventory providers: today the inventory is Click.'s own (partners manage it). `apps.hotels.inventory` is the boundary
an external hotel-inventory provider would implement; it is not faked.
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


def booking_number() -> str:
    return "HTL-" + "".join(secrets.choice(_ALPHABET) for _ in range(8))


class Destination(BaseModel):
    slug = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=100)
    region = models.CharField(max_length=100, blank=True, help_text="State / region shown under the name.")
    kind = models.CharField(max_length=10, choices=[("city", "City"), ("area", "Area"), ("region", "Region")], default="city")
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="areas")
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    tagline = models.CharField(max_length=140, blank=True)
    tags = models.JSONField(default=list, blank=True, help_text='Discovery tags, e.g. ["weekend", "beach", "nature", "business"].')
    synonyms = models.JSONField(default=list, blank=True)
    position = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "name"]

    def __str__(self):
        return self.name


class Landmark(BaseModel):
    class Kind(models.TextChoices):
        CENTRE = "centre", "City centre"
        AIRPORT = "airport", "Airport"
        STATION = "station", "Railway station"
        BEACH = "beach", "Beach"
        LANDMARK = "landmark", "Landmark"
        BUSINESS = "business", "Business district"

    destination = models.ForeignKey(Destination, on_delete=models.CASCADE, related_name="landmarks")
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)

    class Meta:
        ordering = ["destination", "kind", "name"]


class Amenity(BaseModel):
    slug = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=60)
    icon = models.CharField(max_length=30, default="check")
    scope = models.CharField(max_length=10, choices=[("property", "Property"), ("room", "Room"), ("both", "Both")], default="property")
    filterable = models.BooleanField(default=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "name"]

    def __str__(self):
        return self.name


class HotelProperty(BaseModel):
    class Type(models.TextChoices):
        HOTEL = "hotel", "Hotel"
        RESORT = "resort", "Resort"
        APARTMENT = "apartment", "Serviced apartment"
        VILLA = "villa", "Villa"
        HOSTEL = "hostel", "Hostel"
        HOMESTAY = "homestay", "Homestay"
        GUEST_HOUSE = "guest_house", "Guest house"

    partner = models.OneToOneField(Partner, on_delete=models.CASCADE, related_name="hotel")
    destination = models.ForeignKey(Destination, on_delete=models.PROTECT, related_name="properties")
    property_type = models.CharField(max_length=12, choices=Type.choices, default=Type.HOTEL)
    star_rating = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Official classification only; leave empty if none.")
    tagline = models.CharField(max_length=140, blank=True)
    description = models.TextField(blank=True)
    highlights = models.JSONField(default=list, blank=True)
    address = models.CharField(max_length=255)
    area = models.CharField(max_length=100, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    amenities = models.ManyToManyField(Amenity, related_name="properties", blank=True)
    check_in_time = models.TimeField()
    check_out_time = models.TimeField()
    languages = models.JSONField(default=list, blank=True)
    policies = models.JSONField(default=list, blank=True, help_text="House rules / important conditions shown before payment.")
    accessibility = models.CharField(max_length=300, blank=True)
    parking = models.CharField(max_length=160, blank=True)
    nearby = models.JSONField(default=list, blank=True, help_text='[{"name", "km"}] places the property lists nearby.')
    good_for = models.JSONField(default=list, blank=True, help_text='Traveller types the property caters for: "family", "couple", "solo", "business".')
    accent = models.CharField(max_length=9, default="#d4b26a")
    is_listed = models.BooleanField(default=False, help_text="Shown to customers (Business OS approval).")
    # Maintained from verified-stay reviews (apps.hotels.booking.recompute); never edited by hand.
    rating_average = models.DecimalField(max_digits=3, decimal_places=1, default=0)
    rating_count = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=["destination", "is_listed"], name="hotels_property_dest_idx")]
        constraints = [models.CheckConstraint(condition=Q(star_rating__isnull=True) | Q(star_rating__gte=1, star_rating__lte=5), name="hotels_star_range")]

    def __str__(self):
        return self.partner.business_name


class HotelImage(BaseModel):
    property = models.ForeignKey(HotelProperty, on_delete=models.CASCADE, related_name="images")
    room_type = models.ForeignKey("RoomType", on_delete=models.CASCADE, null=True, blank=True, related_name="images")
    category = models.CharField(max_length=20, choices=[("exterior", "Exterior"), ("lobby", "Lobby"), ("room", "Rooms"), ("dining", "Dining"),
                                                        ("pool", "Pool & leisure"), ("other", "Other")], default="other")
    caption = models.CharField(max_length=160, blank=True)
    renditions = models.JSONField(default=dict, blank=True, editable=False)
    width = models.PositiveIntegerField(null=True, blank=True, editable=False)
    height = models.PositiveIntegerField(null=True, blank=True, editable=False)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "created_at"]


class RoomType(BaseModel):
    class RoomClass(models.TextChoices):
        SINGLE = "single", "Single"
        DOUBLE = "double", "Double"
        TWIN = "twin", "Twin"
        FAMILY = "family", "Family"
        SUITE = "suite", "Suite"
        DORM = "dorm", "Dorm bed"

    property = models.ForeignKey(HotelProperty, on_delete=models.CASCADE, related_name="rooms")
    name = models.CharField(max_length=100)
    room_class = models.CharField(max_length=8, choices=RoomClass.choices)
    beds = models.CharField(max_length=80, help_text="e.g. 1 King bed, 2 Single beds.")
    max_adults = models.PositiveSmallIntegerField()
    max_children = models.PositiveSmallIntegerField(default=0)
    max_occupancy = models.PositiveSmallIntegerField()
    size_sqm = models.PositiveSmallIntegerField(null=True, blank=True)
    view = models.CharField(max_length=60, blank=True)
    description = models.CharField(max_length=400, blank=True)
    amenities = models.ManyToManyField(Amenity, related_name="rooms", blank=True)
    total_units = models.PositiveSmallIntegerField()
    position = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "name"]

    def __str__(self):
        return f"{self.name} · {self.property}"


class RatePlan(BaseModel):
    class Meal(models.TextChoices):
        ROOM_ONLY = "room_only", "Room only"
        BREAKFAST = "breakfast", "Breakfast included"
        HALF_BOARD = "half_board", "Breakfast and dinner"
        FULL_BOARD = "full_board", "All meals"

    class Payment(models.TextChoices):
        PAY_NOW = "pay_now", "Pay now"
        AT_PROPERTY = "at_property", "Pay at the property"
        EITHER = "either", "Pay now or at the property"

    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, related_name="rates")
    name = models.CharField(max_length=80)
    meal_plan = models.CharField(max_length=12, choices=Meal.choices, default=Meal.ROOM_ONLY)
    refundable = models.BooleanField(default=True)
    free_cancel_days = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Free cancellation until N days before check-in (refundable plans).")
    cancel_fee_percent = models.PositiveSmallIntegerField(default=100, help_text="Kept after the free window (100 = non-refundable after it).")
    payment = models.CharField(max_length=12, choices=Payment.choices, default=Payment.PAY_NOW)
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Nightly price per room, weekdays.")
    weekend_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Fri/Sat nights, if different.")
    extra_adult_price = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    min_nights = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["price"]
        constraints = [models.CheckConstraint(condition=Q(price__gt=0), name="hotels_rate_price_positive")]


class RoomInventory(BaseModel):
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, related_name="inventory")
    date = models.DateField()
    units = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Override total units for this night.")
    closed = models.BooleanField(default=False)
    price_override = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["room_type", "date"], name="hotels_inventory_unique")]
        indexes = [models.Index(fields=["room_type", "date"], name="hotels_inventory_idx")]


class HotelOffer(BaseModel):
    class Kind(models.TextChoices):
        EARLY = "early", "Early booking"
        LAST_MINUTE = "last_minute", "Last-minute deal"
        WEEKEND = "weekend", "Weekend offer"
        LONG_STAY = "long_stay", "Long stay"
        COUPON = "coupon", "Coupon"

    property = models.ForeignKey(HotelProperty, on_delete=models.CASCADE, null=True, blank=True, related_name="offers",
                                 help_text="Empty = applies to every property.")
    title = models.CharField(max_length=100)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    percent = models.PositiveSmallIntegerField()
    max_discount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    min_nights = models.PositiveSmallIntegerField(default=1)
    min_days_ahead = models.PositiveSmallIntegerField(null=True, blank=True)
    max_days_ahead = models.PositiveSmallIntegerField(null=True, blank=True)
    code = models.CharField(max_length=20, blank=True, help_text="Required coupon code (kind=coupon).")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-percent"]
        constraints = [models.CheckConstraint(condition=Q(percent__gte=1, percent__lte=90), name="hotels_offer_percent")]


class BookingStatus(models.TextChoices):
    PENDING_PAYMENT = "pending_payment", "Pending payment"
    CONFIRMED = "confirmed", "Confirmed"
    CANCELLED = "cancelled", "Cancelled"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Payment not completed"


ACTIVE = (BookingStatus.PENDING_PAYMENT, BookingStatus.CONFIRMED)  # hold inventory


class HotelBooking(BaseModel):
    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Payment pending"
        PAID = "paid", "Paid"
        AT_PROPERTY = "at_property", "Pay at the property"
        REFUNDED = "refunded", "Refunded"
        PARTLY_REFUNDED = "partly_refunded", "Partly refunded"
        NOT_CHARGED = "not_charged", "Not charged"

    number = models.CharField(max_length=16, unique=True, default=booking_number, editable=False)
    customer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT, related_name="hotel_bookings")
    property = models.ForeignKey(HotelProperty, on_delete=models.PROTECT, related_name="bookings")
    room_type = models.ForeignKey(RoomType, on_delete=models.PROTECT, related_name="bookings")
    rate_plan = models.ForeignKey(RatePlan, on_delete=models.PROTECT, related_name="bookings")
    check_in = models.DateField()
    check_out = models.DateField()
    nights = models.PositiveSmallIntegerField()
    rooms = models.PositiveSmallIntegerField(default=1)
    adults = models.PositiveSmallIntegerField()
    children = models.PositiveSmallIntegerField(default=0)
    guest_name = models.CharField(max_length=120)
    guest_email = models.EmailField(blank=True)
    guest_phone = models.CharField(max_length=20)
    other_guests = models.JSONField(default=list, blank=True, help_text="Names only.")
    special_requests = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=20, choices=BookingStatus.choices, default=BookingStatus.PENDING_PAYMENT)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    payment_mode = models.CharField(max_length=12, choices=RatePlan.Payment.choices)
    # Snapshot of what was agreed (the property's later changes never alter a booking).
    room_name = models.CharField(max_length=100)
    rate_name = models.CharField(max_length=80)
    meal_plan = models.CharField(max_length=12, choices=RatePlan.Meal.choices)
    refundable = models.BooleanField()
    free_cancel_until = models.DateTimeField(null=True, blank=True)
    cancel_fee_percent = models.PositiveSmallIntegerField()
    nightly = models.JSONField(default=list, help_text='[{"date", "price"}] per room.')
    room_total = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    offer_title = models.CharField(max_length=100, blank=True)
    tax = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    refunded = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=3, default=settings.CLICK_DEFAULT_CURRENCY)
    hold_expires_at = models.DateTimeField(null=True, blank=True, help_text="Pending-payment bookings release the room after this.")
    trip_ref = models.CharField(max_length=40, blank=True, help_text="Reserved for a future Click. Trip / itinerary.")
    idempotency_key = models.CharField(max_length=64)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["room_type", "check_in", "check_out"], name="hotels_booking_dates_idx"),
                   models.Index(fields=["customer", "status"], name="hotels_booking_customer_idx")]
        constraints = [
            models.UniqueConstraint(fields=["customer", "idempotency_key"], name="hotels_booking_idempotency"),
            models.CheckConstraint(condition=Q(check_out__gt=models.F("check_in")), name="hotels_booking_dates"),
            models.CheckConstraint(condition=Q(total__gte=0) & Q(refunded__gte=0), name="hotels_booking_amounts"),
        ]

    def __str__(self):
        return self.number


class StatusEvent(BaseModel):
    booking = models.ForeignKey(HotelBooking, on_delete=models.CASCADE, related_name="events")
    to = models.CharField(max_length=20, choices=BookingStatus.choices)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["created_at"]


class HotelReview(BaseModel):
    ASPECTS = ("cleanliness", "location", "comfort", "facilities", "staff", "value")

    booking = models.OneToOneField(HotelBooking, on_delete=models.CASCADE, related_name="review")
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="hotel_reviews")
    property = models.ForeignKey(HotelProperty, on_delete=models.CASCADE, related_name="reviews")
    overall = models.PositiveSmallIntegerField(help_text="1–10")
    cleanliness = models.PositiveSmallIntegerField()
    location = models.PositiveSmallIntegerField()
    comfort = models.PositiveSmallIntegerField()
    facilities = models.PositiveSmallIntegerField()
    staff = models.PositiveSmallIntegerField()
    value = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=120, blank=True)
    comment = models.TextField(blank=True)
    traveller = models.CharField(max_length=10, choices=[("family", "Family"), ("couple", "Couple"), ("solo", "Solo"), ("business", "Business"),
                                                         ("friends", "Friends")], blank=True)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(condition=Q(overall__gte=1, overall__lte=10), name="hotels_review_range")]
