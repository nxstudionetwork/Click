"""Ride lifecycle. The server owns pricing, matching and every status change; clients only ask."""

import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.activity.services import record
from apps.core.api.exceptions import ConflictError, DomainError
from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify
from apps.payments.models import Payment, PaymentMethod

from . import matching
from .models import (
    ALLOWED_TRANSITIONS, CUSTOMER_CANCELLABLE, Ride, RideOffer, RideRating, RideSafetyEvent, RideStatus,
    RideStatusEvent, RideStop, RideType,
)
from .pricing import MAX_TRIP_KM, MIN_TRIP_KM, compute_fare, duration_minutes, estimate_route, offer_problem

audit = logging.getLogger("click.audit")
MAX_STOPS = 2
PAYMENT_METHODS = {PaymentMethod.CASH, PaymentMethod.WALLET}
SCHEDULE_MIN_AHEAD = timedelta(minutes=30)
SCHEDULE_MAX_AHEAD = timedelta(days=7)


@dataclass
class Place:
    label: str
    address: str
    lat: float
    lng: float


def _points(pickup: Place, stops: list[Place], drop: Place):
    return [(pickup.lat, pickup.lng), *[(s.lat, s.lng) for s in stops], (drop.lat, drop.lng)]


def validate_trip(pickup: Place, stops: list[Place], drop: Place):
    if len(stops) > MAX_STOPS:
        raise DomainError(f"You can add up to {MAX_STOPS} stops.", code="too_many_stops")
    route = estimate_route(_points(pickup, stops, drop))
    if route.straight_km < MIN_TRIP_KM:
        raise DomainError("Pickup and drop are too close. Choose another drop point.", code="trip_too_short")
    if route.straight_km > MAX_TRIP_KM:
        raise DomainError("This trip is outside the city. Intercity rides aren't available yet.", code="trip_too_long")
    return route


def quote(pickup: Place, stops: list[Place], drop: Place, offer: RideOffer | None = None) -> dict:
    """Upfront fare and pickup ETA for every active ride type (ETA is None when no driver is nearby)."""
    route = validate_trip(pickup, stops, drop)
    options = []
    for rt in RideType.objects.filter(is_active=True):
        minutes = duration_minutes(route, rt)
        fare = compute_fare(rt, route, minutes, offer)
        eta = matching.pickup_eta_minutes(rt, (pickup.lat, pickup.lng))
        options.append({
            "ride_type": rt, "duration_minutes": minutes, "fare": fare, "pickup_eta_minutes": eta, "available": eta is not None,
            "offer_problem": offer_problem(offer, rt, fare.subtotal) if offer else None,
        })
    return {"route": route, "options": options}


@transaction.atomic
def request_ride(*, customer, ride_type_code: str, pickup: Place, drop: Place, stops: list[Place], payment_method: str,
                 idempotency_key, offer_id=None, scheduled_for=None, passenger_name: str = "", passenger_phone: str = "") -> tuple[Ride, bool]:
    existing = Ride.objects.filter(customer=customer, idempotency_key=idempotency_key).first()
    if existing:
        return existing, False
    ride_type = RideType.objects.filter(code=ride_type_code, is_active=True).first()
    if ride_type is None:
        raise DomainError("That ride type isn't available.", code="invalid_ride_type")
    if payment_method not in PAYMENT_METHODS:
        raise DomainError("Choose cash or Click. Wallet for rides.", code="invalid_payment_method")
    if scheduled_for is not None:
        now = timezone.now()
        if not (now + SCHEDULE_MIN_AHEAD <= scheduled_for <= now + SCHEDULE_MAX_AHEAD):
            raise DomainError("Schedule between 30 minutes and 7 days from now.", code="invalid_schedule_time")
    if bool(passenger_name.strip()) != bool(passenger_phone.strip()):
        raise DomainError("Add both the passenger's name and phone.", code="passenger_incomplete")

    route = validate_trip(pickup, stops, drop)
    minutes = duration_minutes(route, ride_type)
    offer = None
    if offer_id:
        offer = RideOffer.objects.filter(pk=offer_id).first()
        subtotal = compute_fare(ride_type, route, minutes).subtotal
        if offer is None or (problem := offer_problem(offer, ride_type, subtotal)):
            raise DomainError(problem if offer else "That offer isn't available.", code="offer_not_applicable")
    fare = compute_fare(ride_type, route, minutes, offer)

    ride = Ride.objects.create(
        customer=customer, ride_type=ride_type,
        status=RideStatus.SCHEDULED if scheduled_for else RideStatus.SEARCHING,
        passenger_name=passenger_name.strip(), passenger_phone=passenger_phone.strip(),
        pickup_label=pickup.label[:120], pickup_address=pickup.address[:300], pickup_lat=_d(pickup.lat), pickup_lng=_d(pickup.lng),
        drop_label=drop.label[:120], drop_address=drop.address[:300], drop_lat=_d(drop.lat), drop_lng=_d(drop.lng),
        distance_km=route.distance_km, duration_minutes=minutes,
        fare_base=fare.base, fare_distance=fare.distance, fare_time=fare.time, fare_fees=fare.fees,
        discount=fare.discount, offer=offer if fare.discount else None, offer_title=offer.title if fare.discount else "",
        total=fare.total, payment_method=payment_method, scheduled_for=scheduled_for, idempotency_key=idempotency_key,
    )
    RideStop.objects.bulk_create(
        RideStop(ride=ride, position=i, label=s.label[:120], address=s.address[:300], lat=_d(s.lat), lng=_d(s.lng)) for i, s in enumerate(stops)
    )
    RideStatusEvent.objects.create(ride=ride, to_status=ride.status)
    _start_payment(ride)
    record(customer, "ride.requested", {"total": str(ride.total), "type": ride_type.code}, obj=ride)
    if scheduled_for:
        notify(customer, NotificationCategory.RIDES, f"{ride_type.name} scheduled", f"{ride.number} · pickup {timezone.localtime(scheduled_for):%d %b, %I:%M %p}", f"/rides/{ride.id}")
    else:
        _dispatch(ride)
    audit.info("ride.requested", extra={"ride": ride.number, "customer": str(customer.id)})
    return ride, True


def _d(v: float) -> Decimal:
    return Decimal(str(round(float(v), 6)))


def _start_payment(ride: Ride) -> None:
    """Wallet rides are charged at booking (refunded if the ride doesn't happen); cash is collected by the driver."""
    from apps.wallet import services as wallet

    payment = Payment.objects.create(ride=ride, method=ride.payment_method, amount=ride.total, currency=ride.currency)
    if ride.payment_method == PaymentMethod.WALLET:
        wallet.pay(ride.customer, ride.total, payment, f"Ride {ride.number}")  # raises insufficient_wallet_balance (rolls back)
        payment.status = Payment.Status.CAPTURED
        payment.save(update_fields=["status", "updated_at"])


def _refund(ride: Ride, why: str) -> None:
    from apps.wallet import services as wallet

    for p in ride.payments.all():
        if p.method == PaymentMethod.WALLET and p.status == Payment.Status.CAPTURED:
            wallet.refund(ride.customer, p.amount, p, f"Ride {ride.number} {why}")
            p.status = Payment.Status.REFUNDED
        elif p.status == Payment.Status.PENDING:
            p.status = Payment.Status.CANCELLED
        p.save(update_fields=["status", "updated_at"])


def _dispatch(ride: Ride) -> None:
    """Offer the ride to nearby drivers; with none available it ends as no_driver right away (and is refunded)."""
    if matching.offer_ride(ride) == 0:
        transition(ride, RideStatus.NO_DRIVER, note="No eligible driver nearby")


@transaction.atomic
def transition(ride: Ride, to_status: str, *, note: str = "") -> Ride:
    ride = Ride.objects.select_for_update().get(pk=ride.pk)
    if to_status not in ALLOWED_TRANSITIONS.get(ride.status, set()):
        raise ConflictError(f"A ride that is {ride.get_status_display().lower()} can't move to {to_status}.", code="invalid_transition")
    previous = ride.status
    ride.status = to_status
    now = timezone.now()
    fields = ["status", "updated_at"]
    if to_status == RideStatus.IN_PROGRESS:
        ride.started_at = now; fields.append("started_at")
    if to_status == RideStatus.COMPLETED:
        ride.completed_at = now; fields.append("completed_at")
    if to_status in (RideStatus.CANCELLED, RideStatus.NO_DRIVER):
        ride.cancelled_at = now; fields.append("cancelled_at")
    if to_status == RideStatus.SEARCHING and previous == RideStatus.DRIVER_ASSIGNED:
        ride.driver = None; ride.driver_assigned_at = None; fields += ["driver", "driver_assigned_at"]
    ride.save(update_fields=fields)
    RideStatusEvent.objects.create(ride=ride, from_status=previous, to_status=to_status, note=note[:200])

    c, link = ride.customer, f"/rides/{ride.id}"
    if to_status == RideStatus.DRIVER_ARRIVED:
        notify(c, NotificationCategory.RIDES, "Your driver has arrived", f"{ride.number} · check the vehicle and plate before you get in.", link)
    elif to_status == RideStatus.COMPLETED:
        for p in ride.payments.filter(method=PaymentMethod.CASH, status=Payment.Status.PENDING):
            p.status = Payment.Status.CAPTURED  # the driver confirmed cash collected by completing the trip
            p.save(update_fields=["status", "updated_at"])
        notify(c, NotificationCategory.RIDES, "Ride completed", f"{ride.number} · ₹{ride.total:.0f}. Rate your ride.", link)
        record(c, "ride.completed", {"total": str(ride.total)}, obj=ride)
    elif to_status == RideStatus.NO_DRIVER:
        _refund(ride, "not matched")
        notify(c, NotificationCategory.RIDES, "No ride available", "No driver was available near your pickup. You haven’t been charged.", link)
    elif to_status == RideStatus.CANCELLED:
        _refund(ride, "cancelled")
    return ride


def cancel_by_customer(ride: Ride, reason: str = "") -> Ride:
    if ride.status not in CUSTOMER_CANCELLABLE:
        raise ConflictError("This ride can't be cancelled now.", code="not_cancellable")
    ride.cancel_reason = reason[:200]
    ride.save(update_fields=["cancel_reason", "updated_at"])
    ride.driver_offers.filter(response="pending").update(response="expired")
    return transition(ride, RideStatus.CANCELLED, note="Cancelled by customer")


# --- Driver actions (Partner API) ---------------------------------------------------------------

@transaction.atomic
def driver_accept(ride: Ride, driver) -> Ride:
    ride = Ride.objects.select_for_update().get(pk=ride.pk)
    offer = ride.driver_offers.filter(driver=driver, response="pending").first()
    if offer is None or ride.status != RideStatus.SEARCHING:
        raise ConflictError("This ride is no longer available.", code="ride_unavailable")
    offer.response = "accepted"
    offer.save(update_fields=["response", "updated_at"])
    ride.driver_offers.exclude(pk=offer.pk).filter(response="pending").update(response="expired")
    ride.driver = driver
    ride.driver_assigned_at = timezone.now()
    ride.save(update_fields=["driver", "driver_assigned_at", "updated_at"])
    ride = transition(ride, RideStatus.DRIVER_ASSIGNED, note=f"Accepted by {driver.partner_code or driver.pk}")
    notify(ride.customer, NotificationCategory.RIDES, "Driver assigned", f"{ride.number} · your driver is on the way.", f"/rides/{ride.id}")
    return ride


def driver_step(ride: Ride, driver, to_status: str) -> Ride:
    if ride.driver_id != driver.id:
        raise DomainError("This isn't your ride.", code="not_your_ride", status_code=404)
    if to_status not in {RideStatus.DRIVER_ARRIVED, RideStatus.IN_PROGRESS, RideStatus.COMPLETED}:
        raise DomainError("Unknown step.", code="invalid_step")
    return transition(ride, to_status)


def dispatch_due_scheduled(now=None) -> int:
    """Start matching for scheduled rides whose pickup is within 15 minutes (run every minute by a scheduler)."""
    now = now or timezone.now()
    due = Ride.objects.filter(status=RideStatus.SCHEDULED, scheduled_for__lte=now + timedelta(minutes=15))
    n = 0
    for ride in due:
        transition(ride, RideStatus.SEARCHING, note="Scheduled pickup approaching")
        _dispatch(ride)
        n += 1
    return n


# --- After the ride -----------------------------------------------------------------------------

@transaction.atomic
def rate(ride: Ride, *, stars: int, comment: str = "", compliment: str = "") -> RideRating:
    if ride.status != RideStatus.COMPLETED or ride.driver_id is None:
        raise DomainError("You can rate a ride once it's completed.", code="rating_not_allowed")
    if RideRating.objects.filter(ride=ride).exists():
        raise ConflictError("You've already rated this ride.", code="rating_exists")
    return RideRating.objects.create(ride=ride, driver_id=ride.driver_id, stars=stars, comment=comment.strip(), compliment=compliment)


def safety_event(ride: Ride, kind: str, note: str = "") -> RideSafetyEvent:
    event = RideSafetyEvent.objects.create(ride=ride, kind=kind, note=note[:500])
    audit.warning("ride.safety", extra={"ride": ride.number, "kind": kind})
    return event


def search_places(customer, q: str, limit: int = 12) -> list[dict]:
    """Places the customer can pick: saved addresses, places from their past rides, and Click places with coordinates.
    No external geocoder is called; every result has real coordinates from Click's database."""
    from apps.stores.models import Store

    q = q.strip()[:80]
    out: list[dict] = []
    seen = set()

    def add(kind, label, address, lat, lng):
        key = (round(float(lat), 4), round(float(lng), 4))
        if key in seen or lat is None:
            return
        seen.add(key)
        out.append({"kind": kind, "label": label, "address": address, "lat": float(lat), "lng": float(lng)})

    addresses = customer.addresses.filter(latitude__isnull=False)
    if q:
        addresses = addresses.filter(Q(line1__icontains=q) | Q(line2__icontains=q) | Q(landmark__icontains=q) | Q(city__icontains=q) | Q(label__icontains=q))
    for a in addresses:
        add("saved", a.label.title(), ", ".join(filter(None, [a.line1, a.line2, a.city])), a.latitude, a.longitude)
    rides = customer.rides.order_by("-created_at")
    if q:
        rides = rides.filter(Q(drop_label__icontains=q) | Q(drop_address__icontains=q) | Q(pickup_label__icontains=q))
    for r in rides[:20]:
        add("recent", r.drop_label, r.drop_address, r.drop_lat, r.drop_lng)
    if q and len(q) >= 2:
        stores = Store.objects.filter(status=Store.Status.ACTIVE, latitude__isnull=False).filter(Q(name__icontains=q) | Q(locality__icontains=q))
        for s in stores[:10]:
            add("place", s.name, ", ".join(filter(None, [s.locality, s.city])), s.latitude, s.longitude)
    return out[:limit]
