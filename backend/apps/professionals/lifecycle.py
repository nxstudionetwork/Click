"""
Service booking lifecycle. Every step is validated here under a row lock and recorded as a ServiceStatusEvent with a
notification. Money rules:

  * the customer agrees to an amount before any work (fixed price, starting price, hourly rate x booked hours);
  * quote-priced jobs can't start until the customer approves a quote; any increase over the agreed amount needs an
    approved quote — a professional can never raise the price silently;
  * hourly jobs bill the hours worked, never more than booked (more needs an approved quote) and at least the minimum;
  * the final amount is set when the professional completes the job; the customer then pays (Click Wallet, or cash the
    professional confirms receiving). Nothing is charged at booking.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Avg, Count
from django.utils import timezone

from apps.core.api.exceptions import ConflictError, DomainError
from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify
from apps.payments.models import Payment, PaymentMethod

from . import engine
from .models import (
    ALLOWED_TRANSITIONS, BookingStatus as S, ProviderProfile, ServiceAttachment, ServiceBooking, ServiceJob, ServiceJobOffer,
    ServiceQuote, ServiceReview, ServiceStatusEvent,
)

TWO = Decimal("0.01")
MAX_PHOTOS = 5
OFFER_TO = 5
NOW_WINDOW = timedelta(minutes=10)
SCHEDULED_WINDOW = timedelta(hours=2)

NOTIFY = {
    S.CONFIRMED: ("Booking confirmed", "{pro} accepted your {job} booking."),
    S.ON_THE_WAY: ("{pro} is on the way", "Arrival estimate is based on distance; you'll see each step here."),
    S.ARRIVED: ("{pro} has arrived", ""),
    S.QUOTE_PENDING: ("Quote ready for approval", "{pro} sent a quote. Work starts only after you approve it."),
    S.IN_PROGRESS: ("Work started", "{pro} has started the job."),
    S.COMPLETED: ("Work completed", "Check the work, then pay and rate {pro}."),
    S.PAID: ("Payment received", "Thanks! Rate {pro} to help others."),
    S.CANCELLED: ("Booking cancelled", ""),
    S.UNASSIGNED: ("No professional accepted", "Nothing was charged. Try another professional or time."),
}


def money(v) -> Decimal:
    return Decimal(v).quantize(TWO, rounding=ROUND_HALF_UP)


def _point(address):
    if address is None or address.latitude is None:
        return None
    return float(address.latitude), float(address.longitude)


def _agreed(job: ServiceJob, price: Decimal | None, hours: int | None) -> Decimal | None:
    if job.pricing == ServiceJob.Pricing.QUOTE or price is None:
        return None
    if job.pricing == ServiceJob.Pricing.HOURLY:
        return money(price * max(hours or job.min_hours, job.min_hours))
    return money(price)


def _eligible(job: ServiceJob, point, mode: str, start: datetime | None, only: ProviderProfile | None = None):
    """[(provider, km)] who do this category, serve the location, take this kind of job and are free (now / at the slot)."""
    rows = engine.providers_for(job.category, point) if only is None else [only]
    out = []
    for p in rows:
        if not p.services.filter(category=job.category).exists() or not engine.serves(p, point):
            continue
        if job.pricing == ServiceJob.Pricing.QUOTE and not p.quote_jobs:
            continue
        if mode == "any":
            pass  # only who could ever take it; used to offer the union of their free slots
        elif mode == ServiceBooking.Mode.NOW:
            if not engine.available_now(p):
                continue
        else:
            if not any(datetime.fromisoformat(s["start"]) == start for s in engine.slots(p, job, limit=500)):
                continue
        out.append((p, engine.distance(p, point)))
    return sorted(out, key=lambda x: (x[1] is None, x[1] or 0))


def estimate(customer, data: dict) -> dict:
    """What the customer would agree to, who can take it and when — computed, never stored."""
    job = ServiceJob.objects.select_related("category").filter(pk=data["job_id"], is_active=True, category__is_active=True).first()
    if job is None:
        raise DomainError("Choose a service.", code="job_required")
    address = customer.addresses.filter(pk=data.get("address_id")).first() if data.get("address_id") else None
    point = _point(address)
    provider = engine.listed().filter(pk=data.get("provider_id")).first() if data.get("provider_id") else None
    if data.get("provider_id") and provider is None:
        raise DomainError("That professional isn't available on Click.", code="provider_unavailable", status_code=404)
    price = engine.price_for(provider, job)
    hours = data.get("hours") if job.pricing == ServiceJob.Pricing.HOURLY else None
    agreed = _agreed(job, price, hours)
    offer, discount, _ = engine.best_offer(customer, job.category, agreed)
    tax = money((agreed - discount) * settings.CLICK_SERVICE_FEE_TAX_RATE) if agreed is not None else None
    mode = data.get("mode") or ServiceBooking.Mode.NOW
    start = data.get("scheduled_start")
    if mode == ServiceBooking.Mode.NOW and not job.instant:
        problem = "This job is booked for a scheduled time."
        pros = []
    elif mode == ServiceBooking.Mode.SCHEDULED and not job.schedulable:
        problem = "This job can only be booked for as soon as possible."
        pros = []
    elif mode == ServiceBooking.Mode.SCHEDULED and start is None:
        problem = ""
        pros = []
    else:
        pros = _eligible(job, point, mode, start, provider)
        problem = "" if pros else ("This professional isn't free then." if provider else
                                   "No professional is available for this right now." if mode == "now" else "No professional is free at that time.")
    if address is None:
        problem = problem or "Choose the service address."
    if mode == ServiceBooking.Mode.SCHEDULED and job.schedulable:
        owners = [provider] if provider is not None else [p for p, _ in _eligible(job, point, "any", None)]
        seen: dict[str, dict] = {}
        for p in owners:
            for s in engine.slots(p, job):
                seen.setdefault(s["start"], s)
        slots = sorted(seen.values(), key=lambda s: s["start"])[:60]
    else:
        slots = []
    return {
        "job": {"id": str(job.id), "name": job.name, "category": job.category.name, "category_slug": job.category.slug, "pricing": job.pricing, "pricing_label": job.get_pricing_display(),
                "min_hours": job.min_hours, "includes": job.includes, "excludes": job.excludes, "duration_minutes": job.duration_minutes},
        "price": f"{price:.2f}" if price is not None else None, "price_label": engine.price_label(job.pricing, price),
        "hours": hours, "agreed": f"{agreed:.2f}" if agreed is not None else None,
        "offer": {"title": offer.title, "discount": f"{discount:.2f}"} if offer and discount else None,
        "tax": f"{tax:.2f}" if tax is not None else None,
        "estimated_total": f"{agreed - discount + tax:.2f}" if agreed is not None else None,
        "inspection_fee": f"{job.inspection_fee:.2f}" if job.inspection_fee else None,
        "additional_charges": job.excludes,
        "professionals": len(pros), "eta_minutes": engine.eta_minutes(pros[0][1]) if pros and mode == "now" else None,
        "slots": slots,
        "problem": problem, "bookable": not problem and (mode == "now" or start is not None),
        "cancellation": "Free until the professional is on the way. After that, contact support.",
    }


def _event(b: ServiceBooking, frm: str, to: str, note: str = "") -> None:
    ServiceStatusEvent.objects.create(booking=b, from_status=frm, to_status=to, note=note[:200])


def _notify(b: ServiceBooking, status: str, extra: str = "") -> None:
    title, body = NOTIFY.get(status, (b.get_status_display(), ""))
    pro = engine.name_of(b.provider).split(" ")[0] if b.provider_id else "Your professional"
    notify(b.customer, NotificationCategory.BOOKINGS, f"{title.format(pro=pro)} · {b.number}", (extra or body.format(pro=pro, job=b.job.name))[:200], f"/services/bookings/{b.id}")


@transaction.atomic
def book(customer, data: dict) -> tuple[ServiceBooking, bool]:
    existing = ServiceBooking.objects.filter(customer=customer, idempotency_key=data["idempotency_key"]).first()
    if existing:
        return existing, False
    est = estimate(customer, data)
    if not est["bookable"]:
        raise ConflictError(est["problem"] or "This booking can't be made right now.", code="not_available", details={"estimate": est})
    if est["agreed"] is not None and data.get("expected_amount") is not None and Decimal(str(data["expected_amount"])) != Decimal(est["agreed"]):
        raise ConflictError("The price changed. Review the new estimate.", code="price_changed", details={"estimate": est})
    job = ServiceJob.objects.select_related("category").get(pk=data["job_id"])
    address = customer.addresses.get(pk=data["address_id"])
    point = _point(address)
    provider = engine.listed().filter(pk=data.get("provider_id")).first() if data.get("provider_id") else None
    mode = data["mode"]
    start = data.get("scheduled_start")
    price = engine.price_for(provider, job)
    photos = list(ServiceAttachment.objects.filter(customer=customer, pk__in=data.get("attachment_ids") or [], booking__isnull=True, need__isnull=True))
    if len(photos) != len(set(data.get("attachment_ids") or [])) or len(photos) > MAX_PHOTOS:
        raise DomainError(f"Attach up to {MAX_PHOTOS} of your own photos.", code="invalid_attachments")
    now = timezone.now()
    b = ServiceBooking.objects.create(
        customer=customer, requested_provider=provider, category=job.category, job=job, mode=mode,
        scheduled_start=start if mode == "scheduled" else None,
        scheduled_end=start + timedelta(minutes=job.duration_minutes) if mode == "scheduled" else None,
        address=address.snapshot(), address_ref=address, lat=address.latitude, lng=address.longitude,
        description=(data.get("description") or "").strip()[:1000], pricing=job.pricing, unit_price=price,
        hours=est["hours"], inspection_fee=job.inspection_fee, agreed_amount=Decimal(est["agreed"]) if est["agreed"] else None,
        offers_expire_at=now + (NOW_WINDOW if mode == "now" else min(SCHEDULED_WINDOW, max(start - now - timedelta(minutes=30), timedelta(minutes=15)))),
        rebook_of_id=data.get("rebook_of"), idempotency_key=data["idempotency_key"],
    )
    ServiceAttachment.objects.filter(pk__in=[x.pk for x in photos]).update(booking=b)
    _event(b, "", S.REQUESTED, "Requested")
    pros = _eligible(job, point, mode, start, provider)[: (1 if provider else OFFER_TO)]
    for p, km in pros:
        ServiceJobOffer.objects.create(booking=b, provider=p, distance_km=Decimal(str(km)) if km is not None else None)
    from apps.activity.services import record

    record(customer, "service.booked", {"job": job.slug, "mode": mode}, obj=b)
    notify(customer, NotificationCategory.BOOKINGS, f"Request sent · {b.number}",
           f"{job.name}: {'waiting for ' + engine.name_of(provider) if provider else f'offered to {len(pros)} professionals nearby'}."[:200],
           f"/services/bookings/{b.id}")
    return b, True


@transaction.atomic
def transition(b: ServiceBooking, to: str, note: str = "", extra: str = "") -> ServiceBooking:
    b = ServiceBooking.objects.select_for_update(of=("self",)).select_related("job", "provider__partner__profile", "customer").get(pk=b.pk)
    if to not in ALLOWED_TRANSITIONS.get(b.status, set()):
        raise ConflictError(f"A booking that is {b.get_status_display().lower()} can't move to that step.", code="invalid_transition")
    frm, now = b.status, timezone.now()
    b.status = to
    fields = ["status", "updated_at"]
    if to == S.IN_PROGRESS and not b.started_at:
        b.started_at = now
        fields.append("started_at")
    elif to == S.COMPLETED:
        b.completed_at = now
        fields.append("completed_at")
    elif to == S.PAID:
        b.paid_at = now
        fields.append("paid_at")
    elif to in (S.CANCELLED, S.UNASSIGNED):
        b.cancelled_at = now
        fields.append("cancelled_at")
        b.job_offers.filter(response="pending").update(response="expired")
    b.save(update_fields=fields)
    _event(b, frm, to, note)
    _notify(b, to, extra)
    return b


def expire_due(now=None) -> int:
    """Requests nobody accepted in time end as 'no professional accepted' (run on reads and by a scheduler)."""
    now = now or timezone.now()
    n = 0
    for b in ServiceBooking.objects.filter(status=S.REQUESTED, offers_expire_at__lt=now)[:50]:
        transition(b, S.UNASSIGNED, "No professional accepted in time")
        n += 1
    return n


# --- professional side ------------------------------------------------------------------------------------------------

@transaction.atomic
def accept(b: ServiceBooking, p: ProviderProfile) -> ServiceBooking:
    b = ServiceBooking.objects.select_for_update().select_related("job").get(pk=b.pk)
    offer = b.job_offers.filter(provider=p, response="pending").first()
    if offer is None or b.status != S.REQUESTED or (b.offers_expire_at and b.offers_expire_at < timezone.now()):
        raise ConflictError("This job is no longer available.", code="job_unavailable")
    if b.mode == "now" and engine.busy_now(p):
        raise ConflictError("Finish your current job first.", code="provider_busy")
    if b.mode == "scheduled" and ServiceBooking.objects.filter(
            provider=p, status__in=[S.CONFIRMED, *engine.ON_JOB], scheduled_start__lt=b.scheduled_end,
            scheduled_end__gt=b.scheduled_start).exclude(pk=b.pk).exists():
        raise ConflictError("You already have a job at that time.", code="provider_busy")
    offer.response = "accepted"
    offer.save(update_fields=["response", "updated_at"])
    b.job_offers.exclude(pk=offer.pk).filter(response="pending").update(response="expired")
    b.provider, b.accepted_at = p, timezone.now()
    if b.requested_provider_id is None:
        # Offered to several professionals: the accepting one's own price applies only if it is lower than agreed.
        own = engine.price_for(p, b.job)
        if own is not None and b.unit_price is not None and own < b.unit_price:
            b.unit_price = own
            b.agreed_amount = _agreed(b.job, own, b.hours)
    b.eta_minutes = engine.eta_minutes(float(offer.distance_km)) if b.mode == "now" and offer.distance_km is not None else None
    b.save(update_fields=["provider", "accepted_at", "unit_price", "agreed_amount", "eta_minutes", "updated_at"])
    return transition(b, S.CONFIRMED, f"Accepted by {engine.name_of(p)}")


@transaction.atomic
def decline(b: ServiceBooking, p: ProviderProfile) -> None:
    offer = b.job_offers.filter(provider=p, response="pending").first()
    if offer is None:
        raise ConflictError("This job is no longer available.", code="job_unavailable")
    offer.response = "declined"
    offer.save(update_fields=["response", "updated_at"])
    if b.status == S.REQUESTED and not b.job_offers.filter(response="pending").exists():
        transition(b, S.UNASSIGNED, "Declined by the professional" if b.requested_provider_id else "No professional accepted")


def _amount(text) -> Decimal | None:
    import re

    m = re.search(r"\d+(?:\.\d{1,2})?", str(text or "").replace(",", ""))
    return Decimal(m.group(0)) if m else None


def step(b: ServiceBooking, p: ProviderProfile, action: str, payload: dict) -> ServiceBooking:
    """on_the_way | arrived | quote {amount, note} | start | complete {hours?} | cash_received"""
    if b.provider_id != p.id:
        raise DomainError("This isn't your job.", code="not_your_job", status_code=404)
    if action == "on_the_way":
        return transition(b, S.ON_THE_WAY)
    if action == "arrived":
        return transition(b, S.ARRIVED)
    if action == "quote":
        amount = _amount(payload.get("amount") or payload.get("reason"))
        if amount is None or amount <= 0:
            raise DomainError("Enter the quote amount.", code="validation_error", details={"amount": ["Enter an amount."]})
        note = str(payload.get("note") or payload.get("reason") or "")[:500]
        with transaction.atomic():
            if b.status not in (S.ARRIVED, S.IN_PROGRESS):
                raise ConflictError("Send a quote after you've arrived.", code="invalid_transition")
            ServiceQuote.objects.filter(booking=b, status=ServiceQuote.Status.PENDING).update(status=ServiceQuote.Status.DECLINED)
            ServiceQuote.objects.create(booking=b, amount=money(amount), note=note)
            return transition(b, S.QUOTE_PENDING, f"Quote ₹{amount:.0f}", extra=f"Quote ₹{amount:,.0f}. Work continues only after you approve it.")
    if action == "start":
        if b.status == S.QUOTE_PENDING:
            raise ConflictError("Wait for the customer to approve or decline your quote.", code="quote_pending")
        if b.status != S.ARRIVED:
            raise ConflictError("Mark that you've arrived before starting.", code="invalid_transition")
        if b.pricing == ServiceJob.Pricing.QUOTE and b.agreed_amount is None:
            raise ConflictError("The customer must approve your quote before work starts.", code="quote_required")
        return transition(b, S.IN_PROGRESS)
    if action == "complete":
        return complete(b, p, payload)
    if action == "cash_received":
        return settle(b, PaymentMethod.CASH, confirmed_by_provider=True)
    raise DomainError("Unknown step.", code="invalid_step")


@transaction.atomic
def complete(b: ServiceBooking, p: ProviderProfile, payload: dict) -> ServiceBooking:
    b = ServiceBooking.objects.select_for_update().select_related("job", "category").get(pk=b.pk)
    if b.status != S.IN_PROGRESS:
        raise ConflictError("Start the job before completing it.", code="invalid_transition")
    base = b.agreed_amount
    approved = b.quotes.filter(status=ServiceQuote.Status.APPROVED).exists()
    if b.pricing == ServiceJob.Pricing.HOURLY and not approved:
        worked = _amount(payload.get("hours") or payload.get("reason"))
        if worked is None or worked <= 0:
            raise DomainError("Enter the hours worked.", code="validation_error", details={"hours": ["Enter hours."]})
        billed = max(Decimal(b.job.min_hours), Decimal(math.ceil(worked * 2) / 2))  # half-hour steps
        billed = min(billed, Decimal(b.hours or b.job.min_hours))  # never more than booked without an approved quote
        b.billed_hours = billed
        base = money(b.unit_price * billed)
    if base is None:
        raise ConflictError("There's no agreed price for this job yet.", code="quote_required")
    offer, discount, _ = engine.best_offer(b.customer, b.category, base)
    b.offer, b.offer_title, b.discount = offer, offer.title if offer else "", discount
    b.tax = money((base - discount) * settings.CLICK_SERVICE_FEE_TAX_RATE)
    b.total = money(base - discount + b.tax)
    b.save(update_fields=["billed_hours", "offer", "offer_title", "discount", "tax", "total", "updated_at"])
    return transition(b, S.COMPLETED, "Marked complete by the professional", extra=f"Total ₹{b.total:,.2f}. Pay in the app or in cash.")


# --- customer side ----------------------------------------------------------------------------------------------------

@transaction.atomic
def decide_quote(b: ServiceBooking, approve: bool) -> ServiceBooking:
    b = ServiceBooking.objects.select_for_update().get(pk=b.pk)
    q = b.quotes.filter(status=ServiceQuote.Status.PENDING).first()
    if q is None or b.status != S.QUOTE_PENDING:
        raise ConflictError("There's no quote waiting for you.", code="no_quote")
    q.status, q.decided_at = (ServiceQuote.Status.APPROVED if approve else ServiceQuote.Status.DECLINED), timezone.now()
    q.save(update_fields=["status", "decided_at", "updated_at"])
    if approve:
        b.agreed_amount = q.amount
        b.save(update_fields=["agreed_amount", "updated_at"])
        return transition(b, S.IN_PROGRESS, f"Quote ₹{q.amount:.0f} approved")
    if b.started_at:  # an extra-work quote during the job: keep the original agreement and continue
        return transition(b, S.IN_PROGRESS, "Extra-work quote declined; original price applies")
    if b.inspection_fee and b.inspection_fee > 0:
        # Declined after an inspection visit: only the inspection fee the customer saw before booking is due.
        b.agreed_amount, b.discount = b.inspection_fee, Decimal("0")
        b.tax = money(b.inspection_fee * settings.CLICK_SERVICE_FEE_TAX_RATE)
        b.total = money(b.inspection_fee + b.tax)
        b.save(update_fields=["agreed_amount", "tax", "discount", "total", "updated_at"])
        return transition(b, S.COMPLETED, "Quote declined: inspection fee only",
                          extra=f"You declined the quote. Only the inspection fee (₹{b.total:,.2f} incl. tax) is due.")
    return transition(b, S.ARRIVED, "Quote declined")


@transaction.atomic
def settle(b: ServiceBooking, method: str, confirmed_by_provider: bool = False) -> ServiceBooking:
    """Wallet: charged now (customer action). Cash: only the professional can confirm receiving it."""
    b = ServiceBooking.objects.select_for_update().get(pk=b.pk)
    if b.status != S.COMPLETED or b.total is None:
        raise ConflictError("There's nothing to pay yet.", code="not_payable")
    if method == PaymentMethod.WALLET:
        from apps.wallet import services as wallet

        payment = Payment.objects.create(service_booking=b, method=PaymentMethod.WALLET, amount=b.total, currency=b.currency)
        wallet.pay(b.customer, b.total, payment, f"Service {b.number}")
        payment.status = Payment.Status.CAPTURED
        payment.save(update_fields=["status", "updated_at"])
    elif method == PaymentMethod.CASH:
        if not confirmed_by_provider:
            b.payment_method = PaymentMethod.CASH
            b.save(update_fields=["payment_method", "updated_at"])
            return b  # waiting for the professional to confirm the cash
        Payment.objects.create(service_booking=b, method=PaymentMethod.CASH, amount=b.total, currency=b.currency, status=Payment.Status.CAPTURED)
    else:
        raise DomainError("That payment method isn't available.", code="payment_method_unavailable")
    b.payment_method = method
    b.save(update_fields=["payment_method", "updated_at"])
    b = transition(b, S.PAID, f"Paid ({method})")
    ProviderProfile.objects.filter(pk=b.provider_id).update(
        jobs_completed=ServiceBooking.objects.filter(provider_id=b.provider_id, status=S.PAID).count())
    return b


def cancellation(b: ServiceBooking) -> dict:
    if b.status in (S.REQUESTED, S.CONFIRMED):
        return {"allowed": True, "note": "Free to cancel until the professional is on the way."}
    if b.status in (S.ON_THE_WAY, S.ARRIVED, S.QUOTE_PENDING, S.IN_PROGRESS):
        return {"allowed": False, "note": "The professional is on the job. Contact support from this page to cancel."}
    return {"allowed": False, "note": ""}


def cancel(b: ServiceBooking, reason: str) -> ServiceBooking:
    if not cancellation(b)["allowed"]:
        raise ConflictError(cancellation(b)["note"] or "This booking can't be cancelled.", code="not_cancellable")
    return transition(b, S.CANCELLED, f"Cancelled by customer: {reason}"[:200])


@transaction.atomic
def review(customer, b: ServiceBooking, data: dict) -> ServiceReview:
    if b.customer_id != customer.id:
        raise DomainError("Not found.", code="not_found", status_code=404)
    if b.status not in (S.PAID, S.COMPLETED) or not b.provider_id:
        raise DomainError("You can rate a professional after the job is completed.", code="review_not_allowed")
    if ServiceReview.objects.filter(booking=b).exists():
        raise ConflictError("You've already rated this job.", code="review_exists")
    r = ServiceReview.objects.create(booking=b, customer=customer, provider_id=b.provider_id, overall=data["overall"],
                                     quality=data["quality"], behaviour=data["behaviour"], timeliness=data["timeliness"],
                                     comment=(data.get("comment") or "").strip()[:1000])
    recompute(b.provider_id)
    return r


def recompute(provider_id) -> None:
    agg = ServiceReview.objects.filter(provider_id=provider_id, status=ServiceReview.Status.PUBLISHED).aggregate(a=Avg("overall"), n=Count("id"))
    ProviderProfile.objects.filter(pk=provider_id).update(
        rating_average=Decimal(agg["a"] or 0).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), rating_count=agg["n"],
        jobs_completed=ServiceBooking.objects.filter(provider_id=provider_id, status=S.PAID).count())
