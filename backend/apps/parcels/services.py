"""Parcel quote, booking, lifecycle, cancellation and tracking. Every state change is validated here, under a row lock."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.core import signing
from django.db import transaction
from django.utils import timezone

from apps.core.api.exceptions import ConflictError, DomainError
from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify
from apps.payments.models import Payment, PaymentMethod
from apps.rides.pricing import estimate_route

from . import matching, pricing
from .models import (
    ALLOWED_TRANSITIONS, FEE_CANCEL, FREE_CANCEL, ParcelCategory, ParcelOrder, ParcelProof, ParcelService, ParcelStatus,
    ParcelStatusEvent, ParcelStop, ParcelVehicle, SavedRecipient,
)

PHONE = re.compile(r"^\+?[0-9][0-9 \-]{7,15}$")
SHARE_SALT = "click.parcel.share"
SHARE_MAX_AGE = 7 * 24 * 3600
DISPATCH_AHEAD = timedelta(minutes=15)

NOTIFY = {
    ParcelStatus.SEARCHING: ("Finding a delivery partner", "We're offering your parcel to partners nearby."),
    ParcelStatus.ASSIGNED: ("Delivery partner assigned", "Your partner is heading to the pickup."),
    ParcelStatus.AT_PICKUP: ("Partner at pickup", "Share the pickup PIN only when you hand over the parcel."),
    ParcelStatus.PICKED_UP: ("Parcel picked up", "The pickup was confirmed with the PIN."),
    ParcelStatus.IN_TRANSIT: ("Parcel in transit", "On its way to the drop."),
    ParcelStatus.ARRIVING: ("Parcel near destination", "The recipient needs the delivery PIN."),
    ParcelStatus.DELIVERED: ("Parcel delivered", "Delivery was confirmed with the PIN."),
    ParcelStatus.CANCELLED: ("Parcel cancelled", ""),
    ParcelStatus.FAILED: ("Delivery couldn't be completed", "Tell us what you'd like us to do in Help."),
    ParcelStatus.NO_PARTNER: ("No delivery partner available", "Nothing was charged; any wallet payment was refunded."),
}


@dataclass
class Place:
    label: str
    address: str
    lat: float
    lng: float
    name: str = ""
    phone: str = ""
    instructions: str = ""


def _place(d: dict | None) -> Place | None:
    if not d:
        return None
    return Place(d["label"], d.get("address", ""), float(d["lat"]), float(d["lng"]), d.get("name", ""), d.get("phone", ""),
                 d.get("instructions", ""))


def _package(d: dict) -> pricing.Package:
    dims = (d["length_cm"], d["width_cm"], d["height_cm"]) if d.get("length_cm") and d.get("width_cm") and d.get("height_cm") else None
    return pricing.Package(ParcelCategory.objects.filter(code=d.get("category")).first(), d.get("size", ""),
                           Decimal(str(d.get("weight_kg") or 0)), dims, d.get("declared_value"))


def apply_store(data: dict):
    """Store pickup: the pickup is the store's own location from Click.'s records (never a client-sent point)."""
    if data.get("mode") != ParcelOrder.Mode.STORE_PICKUP:
        return None
    from apps.stores.models import Store

    store = Store.objects.filter(pk=data.get("store_id"), status=Store.Status.ACTIVE, latitude__isnull=False).first()
    if store is None:
        raise DomainError("Choose a store on Click. to pick up from.", code="store_required")
    pickup = data.get("pickup") or {}
    data["pickup"] = {**pickup, "label": store.name, "address": ", ".join(x for x in (store.locality, store.city) if x),
                      "lat": float(store.latitude), "lng": float(store.longitude), "name": pickup.get("name") or store.name,
                      "phone": pickup.get("phone") or ""}
    return store


def quote(data: dict, now=None) -> dict:
    """Prices for every vehicle under the chosen service (or the first available), with what each service offers."""
    apply_store(data)
    pickup, drop = _place(data.get("pickup")), _place(data.get("drop"))
    if pickup is None or drop is None:
        raise DomainError("Choose a pickup and a drop.", code="locations_required")
    stops = [_place(s) for s in data.get("stops") or []]
    points = [(pickup.lat, pickup.lng), *[(s.lat, s.lng) for s in stops], (drop.lat, drop.lng)]
    if problem := pricing.points_problem(points):
        raise DomainError(problem, code="not_serviceable")
    route = estimate_route(points)
    pkg = _package(data.get("package") or {})
    pkg_problem = pricing.package_problem(pkg)
    services = list(ParcelService.objects.filter(is_active=True).prefetch_related("vehicles"))
    vehicles = list(ParcelVehicle.objects.filter(is_active=True))
    eta_cache: dict = {}

    def eta(v):
        if v.id not in eta_cache:
            eta_cache[v.id] = matching.pickup_eta_minutes(v, (pickup.lat, pickup.lng))
        return eta_cache[v.id]

    svc_out = []
    for s in services:
        fitting = [v for v in s.vehicles.all() if v.is_active and (pkg_problem or not pricing.vehicle_problem(v, pkg))]
        if stops and not (s.allow_stops and len(stops) <= s.max_stops):
            svc_out.append({"code": s.code, "name": s.name, "description": s.description, "available": False,
                            "reason": "Doesn't support extra stops" if not s.allow_stops else f"Up to {s.max_stops} stops"})
            continue
        if not fitting:
            svc_out.append({"code": s.code, "name": s.name, "description": s.description, "available": False,
                            "reason": "No vehicle on this service fits the package"})
            continue
        best = None
        for v in fitting:
            w = pricing.service_window(s, route, pricing.minutes_for(route, v), now,
                                       data.get("scheduled_for") if s.code == "scheduled" else None,
                                       eta(v) if s.code == "express" else None)
            if w["available"]:
                best = w
                break
            best = best or w
        svc_out.append({"code": s.code, "name": s.name, "description": s.description, "available": best["available"],
                        "reason": best.get("reason", ""), "label": best.get("label", ""), "slots": best.get("slots", []),
                        "needs_time": best.get("needs_time", False)})
    chosen = next((s for s in services if s.code == data.get("service")), None)
    if chosen is None or not next(x for x in svc_out if x["code"] == chosen.code)["available"]:
        chosen = next((s for s in services if next(x for x in svc_out if x["code"] == s.code)["available"]), None)

    veh_out = []
    for v in vehicles:
        row = {"code": v.code, "name": v.name, "description": v.description, "icon": v.icon,
               "capacity": {"max_kg": f"{v.max_weight_kg:.0f}", "max_cm": [v.max_length_cm, v.max_width_cm, v.max_height_cm]}}
        if chosen is None or v not in chosen.vehicles.all():
            veh_out.append({**row, "available": False, "reason": "Not on this service"})
            continue
        if not pkg_problem and (vp := pricing.vehicle_problem(v, pkg)):
            veh_out.append({**row, "available": False, "reason": vp})
            continue
        minutes = pricing.minutes_for(route, v)
        w = pricing.service_window(chosen, route, minutes, now, data.get("scheduled_for") if chosen.code == "scheduled" else None,
                                   eta(v) if chosen.code == "express" else None)
        fare = pricing.compute_fare(v, chosen, route)
        veh_out.append({**row, "available": w["available"] or w.get("needs_time", False), "reason": w.get("reason", ""),
                        "fare": fare.as_dict(), "trip_minutes": minutes, "window": w.get("label", ""),
                        "pickup_eta_minutes": eta(v) if chosen.code == "express" else None})
    return {
        "distance_km": f"{route.distance_km:.1f}", "stops": route.stops, "estimate_basis": route.basis,
        "package_problem": pkg_problem, "service": chosen.code if chosen else None, "services": svc_out, "vehicles": veh_out,
        "payment_methods": pricing.mode_payment_methods(data.get("mode", "send"), chosen) if chosen else ["wallet"],
        "cancellation_fee": f"{chosen.cancellation_fee:.2f}" if chosen else None,
    }


def _check_people(data: dict, mode: str) -> None:
    pickup, drop = data["pickup"], data["drop"]
    for who, d in (("sender" if mode != "store_pickup" else "store", pickup), ("recipient", drop)):
        if not (d.get("name") or "").strip():
            raise DomainError(f"Enter the {who}'s name.", code="validation_error", details={who: ["Name is required."]})
        if who == "store":
            continue  # the store's listing on Click. identifies it; the partner contacts it through the order reference
        if not PHONE.match((d.get("phone") or "").strip()):
            raise DomainError(f"Enter a valid phone number for the {who}.", code="validation_error", details={who: ["Phone number is invalid."]})
    if (alt := (drop.get("alt_phone") or "").strip()) and not PHONE.match(alt):
        raise DomainError("The alternate phone number isn't valid.", code="validation_error")


def _record(parcel: ParcelOrder, frm: str, to: str, note: str = "", actor=None) -> None:
    ParcelStatusEvent.objects.create(parcel=parcel, from_status=frm, to_status=to, note=note[:200], actor=actor)


def _notify(parcel: ParcelOrder, status: str, extra: str = "") -> None:
    title, body = NOTIFY.get(status, (parcel.get_status_display(), ""))
    notify(parcel.customer, NotificationCategory.DELIVERIES, f"{title} · {parcel.number}", (extra or body)[:200], f"/parcels/{parcel.id}")


@transaction.atomic
def book(customer, data: dict, now=None) -> tuple[ParcelOrder, bool]:
    existing = ParcelOrder.objects.filter(customer=customer, idempotency_key=data["idempotency_key"]).first()
    if existing:
        return existing, False
    mode = data["mode"]
    if not data.get("contents_confirmed"):
        raise DomainError("Confirm the package follows the rules and the contents are declared correctly.", code="contents_not_confirmed")
    _check_people(data, mode)
    store = apply_store(data)
    q = quote(data, now)
    if q["package_problem"]:
        raise DomainError(q["package_problem"], code="invalid_package")
    service = ParcelService.objects.filter(code=data["service"], is_active=True).first()
    svc = next((s for s in q["services"] if s["code"] == data["service"]), None)
    if service is None or svc is None or not svc["available"]:
        raise ConflictError((svc or {}).get("reason") or "That delivery type isn't available.", code="service_unavailable")
    if service.code == "scheduled" and not data.get("scheduled_for"):
        raise DomainError("Choose a pickup time.", code="schedule_required")
    veh = next((v for v in q["vehicles"] if v["code"] == data["vehicle"]), None)
    if veh is None or not veh["available"] or "fare" not in veh:
        raise ConflictError((veh or {}).get("reason") or "That vehicle can't take this parcel.", code="vehicle_unavailable")
    if data["payment_method"] not in q["payment_methods"]:
        raise DomainError("That payment method isn't available for this parcel.", code="payment_method_unavailable")
    total = Decimal(veh["fare"]["total"])
    if Decimal(str(data["expected_total"])) != total:
        raise ConflictError("The price changed. Review the new estimate.", code="price_changed", details={"quote": q})

    vehicle = ParcelVehicle.objects.get(code=veh["code"])
    pickup, drop = data["pickup"], data["drop"]
    stops = data.get("stops") or []
    points = [(pickup["lat"], pickup["lng"]), *[(s["lat"], s["lng"]) for s in stops], (drop["lat"], drop["lng"])]
    route = estimate_route(points)
    minutes = pricing.minutes_for(route, vehicle)
    window = pricing.service_window(service, route, minutes, now, data.get("scheduled_for"),
                                    matching.pickup_eta_minutes(vehicle, points[0]) if service.code == "express" else None)
    pkg = _package(data["package"])
    fare = pricing.compute_fare(vehicle, service, route)
    scheduled = service.code == "scheduled"
    parcel = ParcelOrder.objects.create(
        customer=customer, mode=mode, service=service, vehicle=vehicle,
        status=ParcelStatus.SCHEDULED if scheduled else ParcelStatus.SEARCHING,
        pickup_label=pickup["label"][:120], pickup_address=pickup.get("address", "")[:300], pickup_lat=_d(pickup["lat"]),
        pickup_lng=_d(pickup["lng"]), pickup_name=pickup["name"].strip()[:120], pickup_phone=pickup["phone"].strip(),
        pickup_instructions=pickup.get("instructions", "")[:200], store=store, store_reference=data.get("store_reference", "")[:80],
        drop_label=drop["label"][:120], drop_address=drop.get("address", "")[:300], drop_lat=_d(drop["lat"]), drop_lng=_d(drop["lng"]),
        drop_name=drop["name"].strip()[:120], drop_phone=drop["phone"].strip(), drop_alt_phone=drop.get("alt_phone", "").strip(),
        drop_instructions=drop.get("instructions", "")[:200],
        category=pkg.category, size=pkg.size, weight_kg=pkg.weight_kg,
        length_cm=pkg.dims[0] if pkg.dims else None, width_cm=pkg.dims[1] if pkg.dims else None, height_cm=pkg.dims[2] if pkg.dims else None,
        declared_value=pkg.declared_value, package_notes=data["package"].get("notes", "")[:300], contents_declared_at=timezone.now(),
        distance_km=route.distance_km, duration_minutes=minutes, estimate_basis=route.basis,
        fare_base=fare.base, fare_distance=fare.distance, fare_service=fare.service, fare_stops=fare.stops, tax=fare.tax,
        discount=fare.discount, total=fare.total, payment_method=data["payment_method"],
        scheduled_for=window.get("pickup_at") if scheduled else None, deliver_by=window.get("deliver_by"),
        repeat_of_id=data.get("repeat_of"), idempotency_key=data["idempotency_key"],
    )
    ParcelStop.objects.bulk_create([ParcelStop(parcel=parcel, position=i + 1, label=s["label"][:120], address=s.get("address", "")[:300],
                                               lat=_d(s["lat"]), lng=_d(s["lng"]), contact_name=s.get("name", "")[:120],
                                               contact_phone=s.get("phone", "")[:20], instructions=s.get("instructions", "")[:200])
                                    for i, s in enumerate(stops)])
    _record(parcel, "", parcel.status, "Booked", customer.user)
    _start_payment(parcel)
    if data.get("save_recipient"):
        save_recipient(customer, drop)
    from apps.activity.services import record

    record(customer, "parcel.booked", {"total": str(parcel.total), "service": service.code}, obj=parcel)
    notify(customer, NotificationCategory.DELIVERIES, f"Parcel booked · {parcel.number}",
           f"{service.name} · {window.get('label', '')}"[:200], f"/parcels/{parcel.id}")
    if not scheduled:
        _dispatch(parcel)
    return parcel, True


def _d(v) -> Decimal:
    return Decimal(str(round(float(v), 6)))


def save_recipient(customer, drop: dict) -> SavedRecipient:
    r, _ = SavedRecipient.objects.update_or_create(
        customer=customer, phone=drop["phone"].strip(), label=drop.get("label", "")[:120],
        defaults=dict(name=drop["name"].strip()[:120], alt_phone=drop.get("alt_phone", "").strip(), address=drop.get("address", "")[:300],
                      lat=_d(drop["lat"]), lng=_d(drop["lng"]), instructions=drop.get("instructions", "")[:200]))
    r.times_used += 1
    r.last_used_at = timezone.now()
    r.save(update_fields=["times_used", "last_used_at", "updated_at"])
    return r


def _start_payment(parcel: ParcelOrder) -> None:
    """Wallet: captured at booking (refunded per the cancellation rules). Cash: the partner collects it at pickup."""
    method = PaymentMethod.WALLET if parcel.payment_method == "wallet" else PaymentMethod.CASH
    payment = Payment.objects.create(parcel=parcel, method=method, amount=parcel.total, currency=parcel.currency)
    if method == PaymentMethod.WALLET:
        from apps.wallet import services as wallet

        wallet.pay(parcel.customer, parcel.total, payment, f"Parcel {parcel.number}")
        payment.status = Payment.Status.CAPTURED
        payment.save(update_fields=["status", "updated_at"])


def _settle(parcel: ParcelOrder, fee: Decimal, why: str) -> Decimal:
    """Refund wallet payments minus `fee`; cancel pending cash. Returns the amount refunded."""
    from apps.wallet import services as wallet

    refunded = Decimal("0")
    for p in parcel.payments.select_for_update():
        if p.method == PaymentMethod.WALLET and p.status == Payment.Status.CAPTURED:
            amount = max(p.amount - fee, Decimal("0"))
            if amount > 0:
                wallet.refund(parcel.customer, amount, p, f"Parcel {parcel.number} {why}")
                refunded += amount
            # Full refund marks the payment refunded; with a fee it stays captured (the wallet ledger shows the refund).
            p.status = Payment.Status.REFUNDED if fee == 0 else Payment.Status.CAPTURED
            p.save(update_fields=["status", "updated_at"])
        elif p.status == Payment.Status.PENDING:
            p.status = Payment.Status.CANCELLED
            p.save(update_fields=["status", "updated_at"])
    return refunded


def _dispatch(parcel: ParcelOrder) -> None:
    if matching.offer_parcel(parcel) == 0 and parcel.service.code == "express":
        # Express was promised because a partner was free; if none is now, end honestly and refund.
        transition(parcel, ParcelStatus.NO_PARTNER, note="No eligible partner nearby")


@transaction.atomic
def transition(parcel: ParcelOrder, to: str, *, note: str = "", actor=None, extra: str = "") -> ParcelOrder:
    parcel = ParcelOrder.objects.select_for_update().select_related("service", "customer").get(pk=parcel.pk)
    if to not in ALLOWED_TRANSITIONS.get(parcel.status, set()):
        raise ConflictError(f"A parcel that is {parcel.get_status_display().lower()} can't move to that step.", code="invalid_transition")
    frm, now = parcel.status, timezone.now()
    parcel.status = to
    fields = ["status", "updated_at"]
    if to == ParcelStatus.PICKED_UP:
        parcel.picked_up_at = now
        fields.append("picked_up_at")
    elif to == ParcelStatus.DELIVERED:
        parcel.delivered_at = now
        fields.append("delivered_at")
    elif to in (ParcelStatus.CANCELLED, ParcelStatus.NO_PARTNER):
        parcel.cancelled_at = now
        fields.append("cancelled_at")
        if to == ParcelStatus.NO_PARTNER:
            _settle(parcel, Decimal("0"), "refund (no partner)")
        parcel.job_offers.filter(response="pending").update(response="expired")
    elif to == ParcelStatus.SEARCHING and frm == ParcelStatus.ASSIGNED:
        parcel.partner, parcel.assigned_at = None, None
        fields += ["partner", "assigned_at"]
    parcel.save(update_fields=fields)
    _record(parcel, frm, to, note, actor)
    _notify(parcel, to, extra)
    return parcel


def cancellation_terms(parcel: ParcelOrder) -> dict:
    if parcel.status in FREE_CANCEL:
        return {"allowed": True, "fee": "0.00", "note": "Free to cancel until a delivery partner is assigned."}
    if parcel.status in FEE_CANCEL:
        fee = min(parcel.service.cancellation_fee, parcel.total) if parcel.payment_method == "wallet" else Decimal("0")
        return {"allowed": True, "fee": f"{fee:.2f}",
                "note": (f"A partner is on the way: a ₹{fee:.0f} cancellation fee applies and the rest is refunded to your wallet."
                         if fee else "A partner is on the way. Please cancel only if you must.")}
    return {"allowed": False, "fee": None, "note": "This parcel can't be cancelled now. Contact support from the parcel page."
            if parcel.status in (ParcelStatus.PICKED_UP, ParcelStatus.IN_TRANSIT, ParcelStatus.ARRIVING) else ""}


@transaction.atomic
def cancel_by_customer(parcel: ParcelOrder, reason: str, user) -> ParcelOrder:
    parcel = ParcelOrder.objects.select_for_update().select_related("service").get(pk=parcel.pk)
    terms = cancellation_terms(parcel)
    if not terms["allowed"]:
        raise ConflictError(terms["note"] or "This parcel can't be cancelled.", code="not_cancellable")
    fee = Decimal(terms["fee"])
    refunded = _settle(parcel, fee, "cancellation refund")
    parcel.cancel_reason, parcel.cancellation_fee = reason[:200], fee
    parcel.save(update_fields=["cancel_reason", "cancellation_fee", "updated_at"])
    extra = (f"₹{refunded:.0f} refunded to your Click Wallet." if refunded else "") + (f" Cancellation fee ₹{fee:.0f}." if fee else "")
    return transition(parcel, ParcelStatus.CANCELLED, note=f"Cancelled by customer: {reason}"[:200], actor=user, extra=extra.strip())


# --- partner side --------------------------------------------------------------------------------------------------

@transaction.atomic
def partner_accept(parcel: ParcelOrder, partner) -> ParcelOrder:
    parcel = ParcelOrder.objects.select_for_update().get(pk=parcel.pk)
    offer = parcel.job_offers.filter(partner=partner, response="pending").first()
    if offer is None or parcel.status != ParcelStatus.SEARCHING:
        raise ConflictError("This delivery is no longer available.", code="job_unavailable")
    if ParcelOrder.objects.filter(partner=partner, status__in=matching.BUSY).exists():
        raise ConflictError("Finish your current delivery first.", code="partner_busy")
    offer.response = "accepted"
    offer.save(update_fields=["response", "updated_at"])
    parcel.job_offers.exclude(pk=offer.pk).filter(response="pending").update(response="expired")
    parcel.partner, parcel.assigned_at = partner, timezone.now()
    parcel.save(update_fields=["partner", "assigned_at", "updated_at"])
    return transition(parcel, ParcelStatus.ASSIGNED, note=f"Accepted by {partner.partner_code or partner.pk}")


@transaction.atomic
def partner_decline(parcel: ParcelOrder, partner) -> None:
    offer = parcel.job_offers.filter(partner=partner, response="pending").first()
    if offer is None:
        raise ConflictError("This delivery is no longer available.", code="job_unavailable")
    offer.response = "declined"
    offer.save(update_fields=["response", "updated_at"])
    if parcel.status == ParcelStatus.SEARCHING and not parcel.job_offers.filter(response="pending").exists():
        matching.offer_parcel(parcel)


def _proof(parcel, partner, kind, method, stop=None):
    from apps.rides.models import DriverLocation

    loc = DriverLocation.objects.filter(driver=partner).first()
    ParcelProof.objects.create(parcel=parcel, kind=kind, method=method, stop=stop, partner=partner,
                               lat=loc.lat if loc else None, lng=loc.lng if loc else None, location_reported_at=loc.reported_at if loc else None)


def partner_step(parcel: ParcelOrder, partner, action: str, payload: dict) -> ParcelOrder:
    """arrived | pickup (PIN) | start | stop (next stop) | near | deliver (PIN) | fail (reason) | release"""
    if parcel.partner_id != partner.id:
        raise DomainError("This isn't your delivery.", code="not_your_job", status_code=404)
    code = str(payload.get("code") or "").strip()
    if action == "arrived":
        return transition(parcel, ParcelStatus.AT_PICKUP, note="Partner at pickup")
    if action == "release":
        return transition(parcel, ParcelStatus.SEARCHING, note="Partner released the job")
    if action == "pickup":
        if parcel.status != ParcelStatus.AT_PICKUP:
            raise ConflictError("Mark that you're at the pickup first.", code="invalid_transition")
        if code != parcel.pickup_pin:
            raise DomainError("That pickup PIN isn't right. Ask the sender for the 4-digit pickup PIN.", code="wrong_pin")
        with transaction.atomic():
            _proof(parcel, partner, ParcelProof.Kind.PICKUP, "pin")
            for p in parcel.payments.filter(method=PaymentMethod.CASH, status=Payment.Status.PENDING):
                p.status = Payment.Status.CAPTURED  # the partner confirmed collecting the cash at pickup
                p.save(update_fields=["status", "updated_at"])
            parcel = transition(parcel, ParcelStatus.PICKED_UP, note="Pickup PIN verified")
            return transition(parcel, ParcelStatus.IN_TRANSIT, note="On the way")
    if action == "stop":
        stop = parcel.stops.filter(completed_at__isnull=True).order_by("position").first()
        if stop is None or parcel.status not in (ParcelStatus.IN_TRANSIT, ParcelStatus.ARRIVING):
            raise ConflictError("There's no stop to complete.", code="invalid_transition")
        stop.completed_at = timezone.now()
        stop.save(update_fields=["completed_at", "updated_at"])
        _proof(parcel, partner, ParcelProof.Kind.STOP, "partner_confirmation", stop)
        _record(parcel, parcel.status, parcel.status, f"Stop {stop.position} completed: {stop.label}")
        _notify(parcel, parcel.status, f"Stop {stop.position} ({stop.label}) completed.")
        return parcel
    if action == "near":
        return transition(parcel, ParcelStatus.ARRIVING, note="Near the drop")
    if action == "deliver":
        if parcel.stops.filter(completed_at__isnull=True).exists():
            raise ConflictError("Complete the stops before the final drop.", code="stops_pending")
        if code != parcel.delivery_pin:
            raise DomainError("That delivery PIN isn't right. Ask the recipient for the 4-digit delivery PIN.", code="wrong_pin")
        with transaction.atomic():
            _proof(parcel, partner, ParcelProof.Kind.DELIVERY, "pin")
            return transition(parcel, ParcelStatus.DELIVERED, note="Delivery PIN verified")
    if action == "fail":
        reason = " ".join(str(payload.get("reason", "")).split())[:200]
        if len(reason) < 3:
            raise DomainError("Say what went wrong.", code="validation_error", details={"reason": ["Enter a reason."]})
        parcel.failure_reason = reason
        parcel.save(update_fields=["failure_reason", "updated_at"])
        return transition(parcel, ParcelStatus.FAILED, note=f"Failed: {reason}", extra=f"Partner reported: {reason}. Tell us what to do in Help.")
    raise DomainError("Unknown step.", code="invalid_step")


def dispatch_due(now=None) -> int:
    """Start matching scheduled parcels whose pickup is within DISPATCH_AHEAD (run by a scheduler; also run when read)."""
    now = now or timezone.now()
    n = 0
    for p in ParcelOrder.objects.filter(status=ParcelStatus.SCHEDULED, scheduled_for__lte=now + DISPATCH_AHEAD).select_related("service")[:50]:
        p = transition(p, ParcelStatus.SEARCHING, note="Pickup time is near")
        _dispatch(p)
        n += 1
    return n


# --- tracking & sharing ----------------------------------------------------------------------------------------------

STEPS = [ParcelStatus.SEARCHING, ParcelStatus.ASSIGNED, ParcelStatus.AT_PICKUP, ParcelStatus.PICKED_UP, ParcelStatus.IN_TRANSIT,
         ParcelStatus.ARRIVING, ParcelStatus.DELIVERED]


def timeline(parcel: ParcelOrder) -> list[dict]:
    reached = {}
    for e in parcel.events.all():
        reached.setdefault(e.to_status, e.created_at)
    steps = ([ParcelStatus.SCHEDULED] if parcel.scheduled_for else []) + STEPS
    out = [{"status": s, "label": ParcelStatus(s).label, "at": reached[s].isoformat() if s in reached else None} for s in steps]
    if parcel.status in (ParcelStatus.CANCELLED, ParcelStatus.FAILED, ParcelStatus.NO_PARTNER):
        out = [x for x in out if x["at"]] + [{"status": parcel.status, "label": parcel.get_status_display(),
                                              "at": reached.get(parcel.status, parcel.updated_at).isoformat()}]
    return out


def partner_position(parcel: ParcelOrder) -> dict | None:
    """The assigned partner's last reported position (from their app). Called live only when it is fresh."""
    from apps.rides.matching import LIVE_FOR, LOCATION_FRESH_FOR
    from apps.rides.models import DriverLocation

    if not parcel.partner_id or parcel.status not in (ParcelStatus.ASSIGNED, ParcelStatus.AT_PICKUP, ParcelStatus.PICKED_UP,
                                                      ParcelStatus.IN_TRANSIT, ParcelStatus.ARRIVING):
        return None
    loc = DriverLocation.objects.filter(driver_id=parcel.partner_id).first()
    if loc is None or timezone.now() - loc.reported_at > LOCATION_FRESH_FOR:
        return None
    return {"lat": float(loc.lat), "lng": float(loc.lng), "reported_at": loc.reported_at.isoformat(),
            "live": timezone.now() - loc.reported_at <= LIVE_FOR}


def share_token(parcel: ParcelOrder) -> str:
    return signing.dumps({"p": str(parcel.id)}, salt=SHARE_SALT, compress=True)


def from_share_token(token: str) -> ParcelOrder | None:
    try:
        data = signing.loads(token, salt=SHARE_SALT, max_age=SHARE_MAX_AGE)
    except signing.BadSignature:
        return None
    return ParcelOrder.objects.filter(pk=data.get("p")).select_related("service", "vehicle").first()


def mask_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    return f"••••• {digits[-4:]}" if len(digits) >= 4 else ""
