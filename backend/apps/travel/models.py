"""
Click. Travel: long-distance transport — bus, train and flight. Separate from Rides (local, on demand), Hotels
(accommodation) and Showtime / Events.

  Place            where journeys start and end: cities, and the stations, airports and bus boarding points inside
                   them (`city`); autocomplete labels say which ("Hyderabad — Airport (HYD)")
  Operator         the transport provider (bus operator, railway, airline): mode, status, contact, verified ratings;
                   `source` says where the inventory comes from (Click. partner inventory today; aggregator / direct
                   APIs plug in behind apps.travel.providers)
  Service          a timetabled service: number, name, vehicle, running days, amenities, bus seat layout, baggage
                   and the cancellation rules; `Stop`s give the route with times, day offsets and distance
  FareClass        what can be sold on a service: bus seat types, train classes, flight cabins / fare types, with
                   capacity, fares and refundability
  Journey          one dated run of a service (status, delay, platform / gate notes) — materialised from the
                   timetable for the booking window
  TravelBooking    a ticket: the journey segment, class, passengers (each with seat / berth / status), price
  (+ Passenger,    snapshot, policy snapshot, payment through the shared Payment / Click. Wallet, PNR; bookings
   StatusEvent)    made together (a return trip) share a `trip_ref`
  SavedTraveller   the customer's frequent travellers: name, age, gender, berth preference — never ID numbers
  RecentSearch, Route, PriceAlert, TravelPreference, TravelOffer
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
    return "TRV-" + "".join(secrets.choice(_ALPHABET) for _ in range(8))


def pnr() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(6))


class Mode(models.TextChoices):
    BUS = "bus", "Bus"
    TRAIN = "train", "Train"
    FLIGHT = "flight", "Flight"


class Place(BaseModel):
    class Kind(models.TextChoices):
        CITY = "city", "City"
        AIRPORT = "airport", "Airport"
        STATION = "station", "Railway station"
        BUS_STOP = "bus_stop", "Bus stop"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    code = models.CharField(max_length=8, blank=True, help_text="IATA airport code or railway station code.")
    city = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="points",
                             help_text="The city a station, airport or boarding point belongs to.")
    state = models.CharField(max_length=60, blank=True)
    aliases = models.CharField(max_length=200, blank=True, help_text="Other names people search for, comma-separated.")
    address = models.CharField(max_length=200, blank=True)
    landmark = models.CharField(max_length=120, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["kind", "name"], name="travel_place_kind_name_idx")]

    def __str__(self) -> str:
        return self.label

    @property
    def city_place(self):
        return self.city if self.city_id else self

    @property
    def label(self) -> str:
        if self.kind == self.Kind.CITY:
            return f"{self.name} — City"
        suffix = f" ({self.code})" if self.code else ""
        return f"{self.name} — {self.get_kind_display()}{suffix}"


class Operator(BaseModel):
    class Source(models.TextChoices):
        CLICK = "click", "Click. partner inventory"
        AGGREGATOR = "aggregator", "Aggregator API"
        DIRECT = "direct", "Provider API"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    mode = models.CharField(max_length=6, choices=Mode.choices)
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=6, blank=True, help_text="Airline designator / short code.")
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.CLICK)
    partner = models.ForeignKey("partners.Partner", on_delete=models.SET_NULL, null=True, blank=True, related_name="travel_operators")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    contact_phone = models.CharField(max_length=20, blank=True)
    contact_email = models.EmailField(blank=True)
    logo_url = models.URLField(blank=True, help_text="The operator's own logo (uploaded by them); none are seeded.")
    accent = models.CharField(max_length=9, default="#2563eb")
    # Maintained from verified-trip ratings only.
    rating_average = models.DecimalField(max_digits=2, decimal_places=1, default=0)
    rating_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Service(BaseModel):
    class BusType(models.TextChoices):
        SEATER = "seater", "Seater"
        SEMI_SLEEPER = "semi_sleeper", "Semi-sleeper"
        SLEEPER = "sleeper", "Sleeper"
        SEATER_SLEEPER = "seater_sleeper", "Seater / sleeper"

    operator = models.ForeignKey(Operator, on_delete=models.PROTECT, related_name="services")
    mode = models.CharField(max_length=6, choices=Mode.choices)
    number = models.CharField(max_length=12, help_text="Train number, flight number or the operator's service code.")
    name = models.CharField(max_length=120, blank=True, help_text="Train name, or a service name.")
    vehicle = models.CharField(max_length=80, blank=True, help_text="Bus model, train type or aircraft, as the operator states it.")
    bus_type = models.CharField(max_length=16, choices=BusType.choices, blank=True)
    ac = models.BooleanField(default=True)
    premium = models.BooleanField(default=False, help_text="Premium coach (multi-axle etc.), as the operator lists it.")
    running_days = models.JSONField(default=list, help_text="Weekdays the service leaves its first stop, 0 = Monday.")
    amenities = models.JSONField(default=list, blank=True)
    seat_layout = models.JSONField(default=dict, blank=True, help_text='Bus: {"decks": [{"name": "Lower", "rows": [["1A","1B",null,"1C"]]}], '
                                                                        '"seats": {"1A": {"class": "seater", "ladies": false}}}')
    baggage = models.JSONField(default=dict, blank=True, help_text='Flights: {"cabin": "7 kg", "check_in": "15 kg"}.')
    cancellation = models.JSONField(default=list, help_text='Tiers, most generous first: [{"hours": 48, "fee_percent": 10}, …]; '
                                                            'cancelling within the last tier\'s hours keeps everything.')
    booking_window_days = models.PositiveSmallIntegerField(default=60)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["number"]
        constraints = [models.UniqueConstraint(fields=["operator", "number"], name="travel_service_number_unique")]

    def __str__(self) -> str:
        return f"{self.number} {self.name}".strip()


class Stop(BaseModel):
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="stops")
    place = models.ForeignKey(Place, on_delete=models.PROTECT, related_name="stops")
    seq = models.PositiveSmallIntegerField()
    arrive = models.TimeField(null=True, blank=True)
    depart = models.TimeField(null=True, blank=True)
    day = models.PositiveSmallIntegerField(default=0, help_text="Days after the service leaves its first stop.")
    km = models.PositiveIntegerField(default=0, help_text="Distance from the first stop.")
    boarding = models.BooleanField(default=True)
    dropping = models.BooleanField(default=True)
    note = models.CharField(max_length=80, blank=True, help_text="Platform, terminal or pickup note when the operator publishes one.")

    class Meta:
        ordering = ["service", "seq"]
        constraints = [models.UniqueConstraint(fields=["service", "seq"], name="travel_stop_seq_unique")]


class FareClass(BaseModel):
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="classes")
    code = models.CharField(max_length=16, help_text="Bus seat class, train class (SL, 3A, 2A, 1A, CC, EC) or cabin.")
    name = models.CharField(max_length=60)
    fare_type = models.CharField(max_length=30, blank=True, help_text="Flights: Saver, Flexi…")
    capacity = models.PositiveSmallIntegerField(help_text="Seats / berths sold in this class per journey.")
    rac_capacity = models.PositiveSmallIntegerField(default=0, help_text="Trains: RAC places (two passengers per side-lower berth).")
    waitlist_limit = models.PositiveSmallIntegerField(default=0, help_text="Trains: how many waitlisted tickets may be sold.")
    base_fare = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"), help_text="Bus / flight: end-to-end fare per seat.")
    per_km = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0"), help_text="Trains: fare per km.")
    min_fare = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    reservation_charge = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    superfast_charge = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    infant_fare = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"), help_text="Flights: per infant on lap.")
    tax_percent = models.DecimalField(max_digits=4, decimal_places=1, default=Decimal("0"), help_text="GST as the provider applies it.")
    refundable = models.BooleanField(default=True)
    change_fee = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text="Flights: date change fee, if allowed.")
    meal = models.CharField(max_length=40, blank=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["service", "position"]
        constraints = [models.UniqueConstraint(fields=["service", "code"], name="travel_class_code_unique")]

    def __str__(self) -> str:
        return f"{self.service.number} {self.code}"


class Journey(BaseModel):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "On schedule"
        DELAYED = "delayed", "Delayed"
        CANCELLED = "cancelled", "Cancelled by operator"

    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="journeys")
    date = models.DateField(help_text="Date the service leaves its first stop.")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED)
    delay_minutes = models.PositiveSmallIntegerField(default=0)
    notice = models.CharField(max_length=160, blank=True, help_text="Platform / gate / boarding update from the operator.")

    class Meta:
        ordering = ["date"]
        constraints = [models.UniqueConstraint(fields=["service", "date"], name="travel_journey_unique")]
        indexes = [models.Index(fields=["date", "status"], name="travel_journey_date_idx")]

    def __str__(self) -> str:
        return f"{self.service} · {self.date}"


class BookingStatus(models.TextChoices):
    PENDING_PAYMENT = "pending_payment", "Payment pending"
    CONFIRMED = "confirmed", "Confirmed"
    CANCELLED = "cancelled", "Cancelled"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Not completed"


ACTIVE = (BookingStatus.PENDING_PAYMENT, BookingStatus.CONFIRMED)


class TravelBooking(BaseModel):
    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Payment pending"
        PAID = "paid", "Paid"
        REFUNDED = "refunded", "Refunded"
        PARTLY_REFUNDED = "partly_refunded", "Partly refunded"
        NOT_CHARGED = "not_charged", "Not charged"

    number = models.CharField(max_length=16, unique=True, default=booking_number, editable=False)
    pnr = models.CharField(max_length=10, blank=True, help_text="Issued when the ticket is confirmed.")
    customer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT, related_name="travel_bookings")
    mode = models.CharField(max_length=6, choices=Mode.choices)
    journey = models.ForeignKey(Journey, on_delete=models.PROTECT, related_name="bookings")
    fare_class = models.ForeignKey(FareClass, on_delete=models.PROTECT, related_name="bookings")
    from_stop = models.ForeignKey(Stop, on_delete=models.PROTECT, related_name="+")
    to_stop = models.ForeignKey(Stop, on_delete=models.PROTECT, related_name="+")
    departs_at = models.DateTimeField()
    arrives_at = models.DateTimeField()
    adults = models.PositiveSmallIntegerField(default=1)
    children = models.PositiveSmallIntegerField(default=0)
    infants = models.PositiveSmallIntegerField(default=0)
    contact_phone = models.CharField(max_length=20)
    contact_email = models.EmailField(blank=True)
    status = models.CharField(max_length=20, choices=BookingStatus.choices, default=BookingStatus.PENDING_PAYMENT)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    # Snapshot of what was agreed.
    operator_name = models.CharField(max_length=120)
    service_label = models.CharField(max_length=140)
    class_name = models.CharField(max_length=60)
    from_label = models.CharField(max_length=140)
    to_label = models.CharField(max_length=140)
    refundable = models.BooleanField()
    cancellation_rules = models.JSONField(default=list)
    base_fare = models.DecimalField(max_digits=12, decimal_places=2)
    fees = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    offer_title = models.CharField(max_length=100, blank=True)
    tax = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    refunded = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=3, default=settings.CLICK_DEFAULT_CURRENCY)
    hold_expires_at = models.DateTimeField(null=True, blank=True)
    trip_ref = models.CharField(max_length=40, blank=True, help_text="Shared by bookings made together (outbound + return).")
    idempotency_key = models.CharField(max_length=64)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=200, blank=True)
    reminded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["customer", "status"], name="travel_booking_customer_idx"),
                   models.Index(fields=["journey", "fare_class", "status"], name="travel_booking_journey_idx")]
        constraints = [
            models.UniqueConstraint(fields=["customer", "idempotency_key"], name="travel_booking_idempotency"),
            models.CheckConstraint(condition=Q(total__gte=0) & Q(refunded__gte=0), name="travel_booking_amounts"),
        ]

    def __str__(self) -> str:
        return self.number


class Passenger(BaseModel):
    class Gender(models.TextChoices):
        FEMALE = "female", "Female"
        MALE = "male", "Male"
        OTHER = "other", "Other"

    class SeatStatus(models.TextChoices):
        CONFIRMED = "CNF", "Confirmed"
        RAC = "RAC", "RAC"
        WAITLIST = "WL", "Waitlist"
        CANCELLED = "CAN", "Cancelled"

    booking = models.ForeignKey(TravelBooking, on_delete=models.CASCADE, related_name="passengers")
    journey = models.ForeignKey(Journey, on_delete=models.PROTECT, related_name="+")
    fare_class = models.ForeignKey(FareClass, on_delete=models.PROTECT, related_name="+")
    position = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=80)
    age = models.PositiveSmallIntegerField()
    gender = models.CharField(max_length=6, choices=Gender.choices)
    berth_preference = models.CharField(max_length=12, blank=True)
    seat = models.CharField(max_length=24, blank=True, help_text="Bus seat, train coach-berth, or empty (flight seats at check-in).")
    seat_status = models.CharField(max_length=3, choices=SeatStatus.choices, default=SeatStatus.CONFIRMED)
    queue = models.PositiveIntegerField(default=0, help_text="RAC / waitlist position when issued.")
    fare = models.DecimalField(max_digits=10, decimal_places=2)
    holds_seat = models.BooleanField(default=True, help_text="False once cancelled or released.")

    class Meta:
        ordering = ["booking", "position"]
        constraints = [models.UniqueConstraint(fields=["journey", "seat"], condition=Q(holds_seat=True) & ~Q(seat=""),
                                               name="travel_seat_sold_once")]
        indexes = [models.Index(fields=["journey", "fare_class", "seat_status"], name="travel_pax_inventory_idx")]


class StatusEvent(BaseModel):
    booking = models.ForeignKey(TravelBooking, on_delete=models.CASCADE, related_name="events")
    to = models.CharField(max_length=20, choices=BookingStatus.choices)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["created_at"]


class TripRating(BaseModel):
    """A traveller's rating of a completed journey; operator ratings are recomputed from these only."""

    booking = models.OneToOneField(TravelBooking, on_delete=models.CASCADE, related_name="rating")
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="trip_ratings")
    operator = models.ForeignKey(Operator, on_delete=models.CASCADE, related_name="ratings")
    rating = models.PositiveSmallIntegerField()
    comment = models.CharField(max_length=1000, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(condition=Q(rating__gte=1, rating__lte=5), name="travel_rating_range")]


class SavedTraveller(BaseModel):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="saved_travellers")
    name = models.CharField(max_length=80)
    age = models.PositiveSmallIntegerField()
    gender = models.CharField(max_length=6, choices=Passenger.Gender.choices)
    berth_preference = models.CharField(max_length=12, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["customer", "name"], name="travel_traveller_unique")]


class Route(BaseModel):
    """A city pair people save and follow (Wishlist, price alerts)."""

    origin = models.ForeignKey(Place, on_delete=models.CASCADE, related_name="+")
    destination = models.ForeignKey(Place, on_delete=models.CASCADE, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["origin", "destination"], name="travel_route_unique")]

    def __str__(self) -> str:
        return f"{self.origin.name} → {self.destination.name}"


class RecentSearch(BaseModel):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="travel_searches")
    mode = models.CharField(max_length=6, choices=Mode.choices)
    origin = models.ForeignKey(Place, on_delete=models.CASCADE, related_name="+")
    destination = models.ForeignKey(Place, on_delete=models.CASCADE, related_name="+")
    date = models.DateField()
    return_date = models.DateField(null=True, blank=True)
    adults = models.PositiveSmallIntegerField(default=1)
    children = models.PositiveSmallIntegerField(default=0)
    infants = models.PositiveSmallIntegerField(default=0)
    travel_class = models.CharField(max_length=16, blank=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [models.UniqueConstraint(fields=["customer", "mode", "origin", "destination"], name="travel_recent_unique")]


class PriceAlert(BaseModel):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="travel_price_alerts")
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="alerts")
    mode = models.CharField(max_length=6, choices=Mode.choices)
    date = models.DateField()
    last_fare = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Lowest fare when last checked.")
    last_checked_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["date"]
        constraints = [models.UniqueConstraint(fields=["customer", "route", "mode", "date"], name="travel_alert_unique")]


class TravelPreference(BaseModel):
    customer = models.OneToOneField(CustomerProfile, on_delete=models.CASCADE, related_name="travel_preference")
    bus_types = models.JSONField(default=list, blank=True, help_text='e.g. ["sleeper", "ac"].')
    bus_departure = models.CharField(max_length=10, blank=True, help_text="morning / afternoon / evening / night")
    train_class = models.CharField(max_length=4, blank=True)
    berth = models.CharField(max_length=12, blank=True)
    flight_cabin = models.CharField(max_length=16, blank=True)
    nonstop = models.BooleanField(default=False)
    airlines = models.JSONField(default=list, blank=True)


class TravelOffer(BaseModel):
    mode = models.CharField(max_length=6, choices=Mode.choices, blank=True, help_text="Blank = every mode.")
    title = models.CharField(max_length=100)
    code = models.CharField(max_length=20, blank=True, help_text="Blank = applied automatically when it qualifies.")
    percent = models.PositiveSmallIntegerField()
    max_discount = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    min_fare = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-percent"]
        constraints = [models.CheckConstraint(condition=Q(percent__gte=1, percent__lte=90), name="travel_offer_percent_range")]

    def __str__(self) -> str:
        return self.title
