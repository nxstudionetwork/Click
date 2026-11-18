"""
Click Partner — Driver mode services beyond the shared work queue (apps.rides.partner_workspace):
request expiry, driver cancellation and rider no-show, rating the rider, driver safety reports, the driver's profile
and vehicle (with exactly what riders see), earnings by period, and trip history.

Everything acts on the same Ride records the Customer App reads, through apps.rides.services.transition, so every
step reaches the rider. The driver is always resolved from the signed-in user.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from apps.core.api.exceptions import ConflictError, DomainError
from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify
from apps.partners.workspace.base import day_bounds, local_today, money, pct

from . import matching, services
from .models import ACTIVE_STATUSES, Ride, RideDriverOffer, RideRating, RideRiderRating, RideSafetyEvent, RideStatus, RideStatusEvent, RideType

MODE = "driver"
OFFER_TTL = timedelta(seconds=40)
NO_SHOW_AFTER = timedelta(minutes=5)
EMERGENCY_NUMBER = "112"
VEHICLE_LABEL = {"car": "Car / Cab", "auto": "Auto rickshaw", "bike": "Bike / Scooter", "ev_bike": "Electric bike", "van": "Van",
                 "mini_truck": "Mini truck"}
PAGE_SIZE = 20


# --- access ------------------------------------------------------------------------------------------------------

def require_driver(user):
    from apps.partners.services import configuration_for, require_owned_partner

    partner = require_owned_partner(user)
    if not partner.is_onboarded:
        raise DomainError("Finish setting up your Partner profile first.", code="onboarding_incomplete", status_code=409)
    if configuration_for(partner.category)["home"].get("mode") != MODE:
        raise DomainError("Driver tools are only for ride partners.", code="not_driver", status_code=403)
    return partner


def _own_ride(driver, ride_id) -> Ride:
    ride = Ride.objects.filter(pk=ride_id, driver=driver).select_related("ride_type", "customer__user").first()
    if ride is None:
        raise DomainError("Ride not found.", code="not_found", status_code=404)
    return ride


# --- requests: expiry --------------------------------------------------------------------------------------------

def offer_expiry():
    return timezone.now() + OFFER_TTL


def expire_stale_offers() -> int:
    """Unanswered requests pass on to the next nearest drivers (or end as no driver found). Idempotent."""
    n = 0
    stale = RideDriverOffer.objects.filter(response="pending", expires_at__lte=timezone.now()).values_list("ride_id", flat=True).distinct()
    for ride_id in list(stale):
        with transaction.atomic():
            ride = Ride.objects.select_for_update().get(pk=ride_id)
            n += ride.driver_offers.filter(response="pending", expires_at__lte=timezone.now()).update(response="expired")
            services._reoffer_if_unanswered(ride)
    return n


# --- cancellation / no-show --------------------------------------------------------------------------------------

def arrived_at(ride: Ride):
    e = RideStatusEvent.objects.filter(ride=ride, to_status=RideStatus.DRIVER_ARRIVED).order_by("-created_at").first()
    return e.created_at if e else None


@transaction.atomic
def driver_cancel(ride: Ride, driver, reason_text: str) -> Ride:
    """Before pickup only. The rider isn't left stranded: the ride goes back to matching with other drivers."""
    ride = Ride.objects.select_for_update().get(pk=ride.pk)
    if ride.driver_id != driver.id:
        raise DomainError("This isn't your ride.", code="not_your_ride", status_code=404)
    reason = " ".join(str(reason_text or "").split())[:120]
    if len(reason) < 3:
        raise DomainError("Tell Click why you’re cancelling.", code="validation_error", details={"reason": ["Enter a reason."]})
    if ride.status != RideStatus.DRIVER_ASSIGNED:
        raise ConflictError("You can cancel only before you reach the pickup. At the pickup, use “Rider didn’t show”.",
                            code="invalid_transition")
    ride = services.transition(ride, RideStatus.SEARCHING, note=f"Driver cancelled ({driver.partner_code}): {reason}")
    notify(ride.customer, NotificationCategory.RIDES, "Finding you another driver",
           f"{ride.number} · your driver couldn’t make it. You won’t be charged extra.", f"/rides/{ride.id}")
    services._reoffer_if_unanswered(ride)  # this driver's accepted offer keeps them out of the next round
    return ride


@transaction.atomic
def rider_no_show(ride: Ride, driver) -> Ride:
    ride = Ride.objects.select_for_update().get(pk=ride.pk)
    if ride.driver_id != driver.id:
        raise DomainError("This isn't your ride.", code="not_your_ride", status_code=404)
    if ride.status != RideStatus.DRIVER_ARRIVED:
        raise ConflictError("Mark that you’ve arrived first.", code="invalid_transition")
    since = arrived_at(ride)
    if since and timezone.now() - since < NO_SHOW_AFTER:
        wait = int((NO_SHOW_AFTER - (timezone.now() - since)).total_seconds() // 60) + 1
        raise ConflictError(f"Please wait for the rider for {wait} more min before cancelling.", code="too_early")
    ride.cancel_reason = "Rider didn’t show up at the pickup"
    ride.save(update_fields=["cancel_reason", "updated_at"])
    ride = services.transition(ride, RideStatus.CANCELLED, note="Rider no-show reported by driver")
    notify(ride.customer, NotificationCategory.RIDES, "Ride cancelled",
           f"{ride.number} · your driver waited at the pickup but couldn’t find you.", f"/rides/{ride.id}")
    return ride


# --- after the trip / safety -------------------------------------------------------------------------------------

def rate_rider(driver, ride_id, stars, note: str = "") -> RideRiderRating:
    ride = _own_ride(driver, ride_id)
    if ride.status != RideStatus.COMPLETED:
        raise ConflictError("You can rate the rider once the trip is completed.", code="rating_not_allowed")
    try:
        stars = int(stars)
    except (TypeError, ValueError):
        stars = 0
    if not 1 <= stars <= 5:
        raise DomainError("Choose 1 to 5 stars.", code="validation_error", details={"stars": ["Choose 1 to 5 stars."]})
    rating, created = RideRiderRating.objects.get_or_create(ride=ride, defaults={"driver": driver, "stars": stars, "note": " ".join(note.split())[:300]})
    if not created:
        raise ConflictError("You’ve already rated this rider.", code="rating_exists")
    return rating


def safety_report(driver, ride_id, kind: str, note: str = "") -> dict:
    """SOS or an issue report from the driver; Click's safety team follows up. Emergencies also go to 112."""
    ride = _own_ride(driver, ride_id)
    if kind not in ("sos", "report"):
        raise DomainError("Choose emergency or report.", code="validation_error", details={"kind": ["Choose a type."]})
    if kind == "report" and len(note.strip()) < 5:
        raise DomainError("Tell Click what happened.", code="validation_error", details={"note": ["Describe the issue."]})
    event = RideSafetyEvent.objects.create(ride=ride, kind=kind, note=" ".join(note.split())[:500], reported_by="driver")
    services.audit.warning("ride.safety.driver", extra={"ride": ride.number, "kind": kind, "driver": driver.partner_code})
    return {"id": str(event.id), "kind": kind, "emergency_number": EMERGENCY_NUMBER,
            "message": ("Call 112 if you are in danger. Click’s safety team has your trip details and will contact you."
                        if kind == "sos" else "Thanks. Click’s safety team will review this trip and contact you if needed.")}


# --- profile / vehicle -------------------------------------------------------------------------------------------

def public_identity(partner) -> dict:
    """Exactly what riders see about this driver (shared with apps.rides.serializers.driver_card)."""
    details = getattr(getattr(partner, "profile", None), "details", {}) or {}
    stats = partner.ride_ratings.aggregate(avg=Avg("stars"), n=Count("id"))
    profile = getattr(partner, "profile", None)
    name = (getattr(profile, "contact_name", "") or "") or partner.business_name or "Your driver"
    return {
        "name": name.split()[0] if name else "Your driver",
        "rating": round(stats["avg"], 1) if stats["avg"] else None, "rating_count": stats["n"],
        "vehicle_type": details.get("vehicle_type", ""), "vehicle_model": details.get("vehicle_model", ""),
        "vehicle_color": details.get("vehicle_color", ""), "plate": details.get("vehicle_number", ""),
    }


def profile(partner) -> dict:
    from apps.partners.documents import blocking_reason, documents_state
    from apps.partners.services import capabilities_of

    details = getattr(getattr(partner, "profile", None), "details", {}) or {}
    vt = details.get("vehicle_type", "")
    ride_types = [t.name for t in RideType.objects.filter(is_active=True).order_by("position") if vt in t.vehicle_type_list]
    rides = Ride.objects.filter(driver=partner)
    done = rides.filter(status=RideStatus.COMPLETED).aggregate(n=Count("id"), km=Sum("distance_km"))
    since = timezone.now() - timedelta(days=30)
    offers = partner.ride_offers.filter(created_at__gte=since).aggregate(
        a=Count("id", filter=Q(response="accepted")), d=Count("id", filter=Q(response="declined")), e=Count("id", filter=Q(response="expired")))
    assigned = rides.filter(driver_assigned_at__gte=since).aggregate(
        c=Count("id", filter=Q(status=RideStatus.COMPLETED)), x=Count("id", filter=Q(status=RideStatus.CANCELLED)))
    cancelled_by_me = RideStatusEvent.objects.filter(note__startswith=f"Driver cancelled ({partner.partner_code})",
                                                     created_at__gte=since).count()
    docs = documents_state(partner)
    profile_row = getattr(partner, "profile", None)
    return {
        "partner_code": partner.partner_code, "name": getattr(profile_row, "contact_name", "") or partner.business_name,
        "status": partner.status, "status_label": partner.get_status_display(), "is_verified": partner.status in ("verified", "active"),
        "category": partner.category.name, "joined": partner.created_at.isoformat(),
        "vehicle": {"type": vt, "type_label": VEHICLE_LABEL.get(vt, vt or "Not set"), "model": details.get("vehicle_model", ""),
                    "color": details.get("vehicle_color", ""), "number": details.get("vehicle_number", ""),
                    "ride_types": ride_types},
        "availability_preference": details.get("availability", ""),
        "capabilities": capabilities_of(partner),
        "documents": docs, "blocked_reason": blocking_reason(partner),
        "public": public_identity(partner),
        "stats": {
            "completed_trips": done["n"], "distance_km": float(done["km"] or 0),
            "acceptance_rate": pct(offers["a"], offers["a"] + offers["d"] + offers["e"]),
            "completion_rate": pct(assigned["c"], assigned["c"] + assigned["x"] + cancelled_by_me),
            "cancelled_by_you": cancelled_by_me, "missed_requests": offers["e"],
        },
        "recent_feedback": [{"stars": r.stars, "comment": r.comment, "compliment": r.compliment, "at": r.created_at.isoformat()}
                            for r in partner.ride_ratings.order_by("-created_at")[:5]],
    }


# --- earnings / trips --------------------------------------------------------------------------------------------

def _period(partner, start, end) -> dict:
    from apps.partners.workspace import online_seconds

    qs = Ride.objects.filter(driver=partner, status=RideStatus.COMPLETED, completed_at__gte=start, completed_at__lt=end)
    agg = qs.aggregate(n=Count("id"), amount=Sum("total"), km=Sum("distance_km"),
                       cash=Sum("total", filter=Q(payment_method="cash")), online=Sum("total", filter=~Q(payment_method="cash")))
    secs = online_seconds(partner, start, end)
    h, m = divmod(secs // 60, 60)
    return {"total": money(agg["amount"] or 0), "trips": agg["n"], "distance_km": float(agg["km"] or 0),
            "cash_collected": money(agg["cash"] or 0), "paid_via_click": money(agg["online"] or 0),
            "online_seconds": secs, "online_label": f"{h}h {m:02d}m" if h else f"{m}m",
            "per_trip": money((agg["amount"] or 0) / agg["n"]) if agg["n"] else None}


def earnings(partner) -> dict:
    today = local_today()
    t0, t1 = day_bounds(today)
    y0, _ = day_bounds(today - timedelta(days=1))
    w0, _ = day_bounds(today - timedelta(days=today.weekday()))
    m0, _ = day_bounds(today.replace(day=1))
    days = []
    for offset in range(6, -1, -1):
        d = today - timedelta(days=offset)
        s, e = day_bounds(d)
        days.append({"date": d.isoformat(), **{k: v for k, v in _period(partner, s, e).items() if k in ("total", "trips")}})
    return {
        "periods": [{"key": "today", "label": "Today", **_period(partner, t0, t1)},
                    {"key": "yesterday", "label": "Yesterday", **_period(partner, y0, t0)},
                    {"key": "week", "label": "This week", **_period(partner, w0, t1)},
                    {"key": "month", "label": "This month", **_period(partner, m0, t1)}],
        "last_7_days": days, "currency": "INR",
        "note": ("Gross fares from completed trips. Cash is what you collected from riders; the rest was paid to Click and "
                 "will be settled to you. Click commission, incentives and payouts aren’t set up yet, so nothing is deducted."),
    }


def trips(partner, params) -> dict:
    qs = Ride.objects.filter(driver=partner).exclude(status__in=ACTIVE_STATUSES).select_related("ride_type", "customer__user")
    status = params.get("status", "all")
    if status in ("completed", "cancelled"):
        qs = qs.filter(status=status)
    try:
        page = max(int(params.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1
    total = qs.count()
    rows = list(qs.order_by("-updated_at")[(page - 1) * PAGE_SIZE: page * PAGE_SIZE])
    out = []
    for r in rows:
        rating = RideRating.objects.filter(ride=r).first()
        given = RideRiderRating.objects.filter(ride=r).first()
        out.append({
            "id": str(r.id), "number": r.number, "status": r.status, "status_label": r.get_status_display(),
            "ride_type": r.ride_type.name, "pickup": r.pickup_label, "drop": r.drop_label, "distance_km": float(r.distance_km),
            "fare": money(r.total), "payment": "Cash" if r.payment_method == "cash" else "Click. Wallet",
            "at": (r.completed_at or r.cancelled_at or r.updated_at).isoformat(), "cancel_reason": r.cancel_reason,
            "rating_received": {"stars": rating.stars, "comment": rating.comment} if rating else None,
            "rider_rated": given.stars if given else None, "can_rate_rider": r.status == RideStatus.COMPLETED and given is None,
        })
    return {"results": out, "page": page, "total": total, "has_more": page * PAGE_SIZE < total}
