"""
Click. Events workflow. Every step is validated here (never in the client), under a row lock where it changes a
booking, with a status event and a customer notification:

  plan      create_plan (type, date or flexible, a saved address, guests, budget, services, requirements, photos)
            → a checklist from the event type and the services needed
  enquire   send_enquiries: the plan goes to up to 5 matching providers at a time (their Partner App "events" workspace)
  quote     provider_quote (itemised, versioned; a new version replaces a pending one) / provider_decline;
            the customer rejects, asks for changes (→ the provider re-quotes) or asks questions (messages on Click)
  book      estimate → book: from the customer's chosen quote or a package, re-priced server-side and matched against
            the total the customer saw; the provider must be free that day. Paid now from the Click. Wallet
            (confirmed) or later (payment pending until paid; unpaid bookings close 2 days before the event)
  run       provider: preparing (team assigned), milestones ticked off, event started on the day, completed
  after     cancel (refund by the provider's terms, to the wallet), review (completed bookings only, once)
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Count
from django.utils import timezone

from apps.core.api.exceptions import ConflictError, DomainError
from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify

from . import engine
from .models import (
    ACTIVE, ALLOWED_TRANSITIONS, BookingStatus as S, ChecklistItem, Enquiry, EventAttachment, EventBooking, EventPackage, EventPlan,
    EventProvider, EventReview, EventService, EventType, Message, Milestone, Quote, StatusEvent,
)

MAX_PHOTOS = 6
MAX_ENQUIRIES_AT_ONCE = 5
MAX_OPEN_ENQUIRIES = 10
PAY_BY_DAYS = 2  # unpaid bookings close this many days before the event
SELF_CANCEL_DAYS = 2  # closer than this, cancellation goes through support


def _note(customer, title: str, body: str, path: str) -> None:
    notify(customer, NotificationCategory.BOOKINGS, title[:150], body[:200], path)


def _band(guests: int) -> str:
    return next((code for code, _, lo, hi in engine.GUEST_BANDS if lo <= guests <= hi), "")


# --- plans -----------------------------------------------------------------------------------------------------------

@transaction.atomic
def create_plan(customer, data: dict) -> EventPlan:
    etype = EventType.objects.filter(slug=data["event_type"], is_active=True).first()
    if etype is None:
        raise DomainError("Choose the type of event.", code="validation_error", details={"event_type": ["Unknown event type."]})
    day = data.get("date")
    flexible = bool(data.get("date_flexible"))
    if day is None and not flexible:
        raise DomainError("Choose a date or mark it flexible.", code="validation_error", details={"date": ["Required."]})
    if day is not None and day < engine.today():
        raise DomainError("The event date is in the past.", code="validation_error", details={"date": ["Choose a future date."]})
    address = customer.addresses.filter(pk=data.get("address_id")).first() if data.get("address_id") else None
    if data.get("address_id") and address is None:
        raise DomainError("Choose one of your saved addresses.", code="validation_error", details={"address_id": ["Not your address."]})
    if address is None:
        raise DomainError("Choose where the event is (a saved address, or where you’d like a venue).", code="validation_error",
                          details={"address_id": ["Required."]})
    bmin, bmax = data.get("budget_min"), data.get("budget_max")
    if bmin is not None and bmax is not None and bmin > bmax:
        raise DomainError("The budget range is reversed.", code="validation_error", details={"budget_max": ["Must be at least the minimum."]})
    services = list(EventService.objects.filter(slug__in=data.get("services") or [], is_active=True))
    if not services:
        raise DomainError("Choose at least one service you need.", code="validation_error", details={"services": ["Choose at least one."]})
    plan = EventPlan.objects.create(
        customer=customer, event_type=etype, title=(data.get("title") or "").strip()[:120], date=day, date_flexible=flexible,
        date_note=(data.get("date_note") or "")[:120], start_time=data.get("start_time"), address_ref=address,
        address={"label": address.label, "line1": address.line1, "line2": address.line2, "landmark": address.landmark, "city": address.city,
                 "postal_code": address.postal_code},
        latitude=address.latitude, longitude=address.longitude, needs_venue=any(s.slug == "venue" for s in services),
        guests=data["guests"], guests_band=_band(data["guests"]), budget_min=bmin, budget_max=bmax,
        budget_flexible=bool(data.get("budget_flexible")) or (bmin is None and bmax is None), requirements=(data.get("requirements") or "").strip(),
    )
    plan.services.set(services)
    ids = data.get("attachment_ids") or []
    photos = EventAttachment.objects.filter(customer=customer, pk__in=ids, plan__isnull=True)
    if len(ids) > MAX_PHOTOS or photos.count() != len(ids):
        raise DomainError(f"Attach up to {MAX_PHOTOS} of your own photos.", code="invalid_attachments")
    photos.update(plan=plan)
    _build_checklist(plan, services)
    return plan


def _build_checklist(plan: EventPlan, services: list[EventService]) -> None:
    rows, seen = [], set()
    by_slug = {s.slug: s for s in services}
    for item in plan.event_type.checklist or []:
        svc = item.get("service")
        if svc and svc not in by_slug:
            continue  # only steps for what this event actually needs
        rows.append((item["key"], item["label"], by_slug.get(svc)))
        seen.add(svc)
    for s in services:
        if s.slug not in seen:
            rows.append((f"svc-{s.slug}", f"Confirm {s.name.lower()}", s))
    for key, label in [("guests", "Confirm the final guest count"), ("schedule", "Finalise the day’s schedule"), ("payment", "Complete payments")]:
        if key not in {r[0] for r in rows}:
            rows.append((key, label, None))
    ChecklistItem.objects.bulk_create([ChecklistItem(plan=plan, key=k, label=l, service=s, position=i) for i, (k, l, s) in enumerate(rows)])


def matches(plan: EventPlan, params=None, request=None) -> list[dict]:
    """Providers who could take this event: they offer something it needs, serve its place, handle its guest count and
    event type, and (for a fixed date) aren't blocked or fully booked. Each card says what of the plan it covers."""
    params = params or {}
    point = (float(plan.latitude), float(plan.longitude)) if plan.latitude is not None else None
    needed = {s.slug for s in plan.services.all()}
    contacted = set(plan.enquiries.values_list("provider_id", flat=True))
    out = []
    for p in engine.listed().filter(services__slug__in=needed).distinct():
        if not engine.serves(p, point) or not engine.capacity_ok(p, plan.guests):
            continue
        types = {t.id for t in p.event_types.all()}
        if types and plan.event_type_id not in types:
            continue
        c = engine.card(p, point, plan.date, plan.guests, request)
        if c["availability"] and c["availability"]["state"] in ("booked", "unavailable"):
            continue
        covers = sorted(needed & {s["slug"] for s in c["services"]})
        pkgs = [engine.package_out(x, plan.guests) for x in p.packages.all() if x.is_active and x.min_guests <= plan.guests <= x.max_guests
                and (not x.event_types.exists() or x.event_types.filter(pk=plan.event_type_id).exists())]
        if params.get("kind") and p.kind != params["kind"]:
            continue
        out.append({**c, "covers": covers, "coverage": len(covers), "packages": pkgs, "contacted": p.id in contacted})
    budget = plan.budget_max
    out.sort(key=lambda c: (-c["coverage"], c["kind"] != "team",
                            budget is not None and c["price_from"] is not None and Decimal(c["price_from"]["amount"]) > budget,
                            -(float(c["rating"]["average"]) if c["rating"] else 0)))
    return out


@transaction.atomic
def send_enquiries(plan: EventPlan, provider_ids: list, package_id=None, message: str = "") -> list[Enquiry]:
    if plan.status not in (EventPlan.Status.PLANNING, EventPlan.Status.BOOKED):
        raise ConflictError("This plan is closed.", code="plan_closed")
    if not provider_ids or len(provider_ids) > MAX_ENQUIRIES_AT_ONCE:
        raise DomainError(f"Choose 1 to {MAX_ENQUIRIES_AT_ONCE} teams to ask for quotes.", code="validation_error")
    if plan.enquiries.filter(status__in=Enquiry.OPEN).count() + len(provider_ids) > MAX_OPEN_ENQUIRIES:
        raise ConflictError(f"You can have up to {MAX_OPEN_ENQUIRIES} open quote requests for one event.", code="too_many_enquiries")
    eligible = {c["id"]: c for c in matches(plan)}
    pkg = EventPackage.objects.filter(pk=package_id, is_active=True).first() if package_id else None
    out = []
    for pid in provider_ids:
        if str(pid) not in eligible:
            raise ConflictError("One of those teams can’t take this event (area, guests, type or date).", code="provider_not_eligible")
        e, created = Enquiry.objects.get_or_create(plan=plan, provider_id=pid, defaults={
            "message": message[:600], "package": pkg if pkg and str(pkg.provider_id) == str(pid) else None})
        if not created and e.status in (Enquiry.Status.WITHDRAWN, Enquiry.Status.REJECTED):
            e.status, e.message = Enquiry.Status.REQUESTED, message[:600]
            e.save(update_fields=["status", "message", "updated_at"])
        out.append(e)
    _note(plan.customer, f"Quote requests sent · {plan.number}",
          f"Sent to {len(out)} team{'s' if len(out) != 1 else ''}. You’ll be notified when a quote arrives.", f"/events/plans/{plan.id}")
    return out


# --- quotes ----------------------------------------------------------------------------------------------------------

def parse_amount(text: str) -> tuple[Decimal | None, str]:
    """'45000 decoration, stage and lights' -> (45000, 'decoration, stage and lights') — the Partner App's text action."""
    import re

    m = re.search(r"(\d[\d,]*(?:\.\d{1,2})?)", text or "")
    if not m:
        return None, (text or "").strip()
    return Decimal(m.group(1).replace(",", "")), (text[:m.start()] + text[m.end():]).strip(" -–:·,")


@transaction.atomic
def provider_quote(enquiry: Enquiry, provider: EventProvider, data: dict) -> Quote:
    e = Enquiry.objects.select_for_update().select_related("plan__customer").get(pk=enquiry.pk)
    if e.provider_id != provider.id:
        raise DomainError("Not found.", code="not_found", status_code=404)
    if e.status not in (Enquiry.Status.REQUESTED, Enquiry.Status.REVISION, Enquiry.Status.QUOTED):
        raise ConflictError("This request is closed.", code="enquiry_closed")
    items = [i for i in (data.get("items") or []) if i.get("label")]
    if not items:
        raise DomainError("Add at least one item to the quote.", code="validation_error", details={"items": ["Required."]})
    for i in items:
        i["amount"] = f"{engine.money(Decimal(str(i['amount']))):.2f}"
        i["optional"] = bool(i.get("optional"))
        if Decimal(i["amount"]) < 0:
            raise DomainError("Amounts can’t be negative.", code="validation_error")
    required = sum((Decimal(i["amount"]) for i in items if not i["optional"]), Decimal("0"))
    if required <= 0:
        raise DomainError("The quote needs a price for the required items.", code="validation_error")
    last = e.quotes.first()
    e.quotes.filter(status=Quote.Status.PENDING).update(status=Quote.Status.SUPERSEDED)
    q = Quote.objects.create(
        enquiry=e, version=(last.version + 1) if last else 1, items=items, amount=engine.money(required),
        duration_hours=data.get("duration_hours"), team_size=data.get("team_size"), terms=(data.get("terms") or "")[:2000],
        notes=(data.get("notes") or "")[:2000], valid_until=data.get("valid_until") or (engine.today() + timedelta(days=7)))
    updated = e.status == Enquiry.Status.REVISION or last is not None
    e.status = Enquiry.Status.QUOTED
    e.first_response_at = e.first_response_at or timezone.now()
    e.save(update_fields=["status", "first_response_at", "updated_at"])
    _note(e.plan.customer, f"{'Quote updated' if updated else 'Quote received'} · {engine.name_of(provider)}",
          f"₹{q.amount:,.0f} + tax for your {e.plan.event_type.name.lower()}. Review it before you book.", f"/events/plans/{e.plan_id}?enquiry={e.id}")
    return q


@transaction.atomic
def provider_decline(enquiry: Enquiry, provider: EventProvider, reason: str = "") -> None:
    e = Enquiry.objects.select_for_update().select_related("plan__customer").get(pk=enquiry.pk)
    if e.provider_id != provider.id or e.status not in Enquiry.OPEN:
        raise ConflictError("This request is closed.", code="enquiry_closed")
    e.status = Enquiry.Status.PROVIDER_DECLINED
    e.first_response_at = e.first_response_at or timezone.now()
    e.save(update_fields=["status", "first_response_at", "updated_at"])
    e.quotes.filter(status=Quote.Status.PENDING).update(status=Quote.Status.SUPERSEDED)
    _note(e.plan.customer, f"{engine.name_of(provider)} can’t take this event", (reason or "Try another team from your matches.")[:200],
          f"/events/plans/{e.plan_id}")


@transaction.atomic
def customer_quote_decision(quote: Quote, decision: str, note: str = "") -> Quote:
    q = Quote.objects.select_for_update().select_related("enquiry").get(pk=quote.pk)
    if q.status != Quote.Status.PENDING:
        raise ConflictError("This quote can’t be changed now.", code="quote_closed")
    e = q.enquiry
    if decision == "reject":
        q.status, e.status = Quote.Status.REJECTED, Enquiry.Status.REJECTED
    elif decision == "changes":
        if len(note.strip()) < 3:
            raise DomainError("Tell the team what to change.", code="validation_error", details={"note": ["Required."]})
        q.status, e.status = Quote.Status.CHANGES, Enquiry.Status.REVISION
    else:
        raise DomainError("Unknown decision.", code="validation_error")
    q.customer_note = note.strip()[:600]
    q.save(update_fields=["status", "customer_note", "updated_at"])
    e.save(update_fields=["status", "updated_at"])
    if note.strip():
        Message.objects.create(enquiry=e, from_customer=True, body=f"{'Changes requested' if decision == 'changes' else 'Declined'}: {note.strip()}"[:1000])
    return q


def post_message(enquiry: Enquiry, from_customer: bool, body: str) -> Message:
    body = (body or "").strip()
    if len(body) < 2:
        raise DomainError("Type a message.", code="validation_error")
    if enquiry.status in (Enquiry.Status.WITHDRAWN,):
        raise ConflictError("This request is closed.", code="enquiry_closed")
    m = Message.objects.create(enquiry=enquiry, from_customer=from_customer, body=body[:1000])
    if not from_customer:
        _note(enquiry.plan.customer, f"Message from {engine.name_of(enquiry.provider)}", body[:200], f"/events/plans/{enquiry.plan_id}?enquiry={enquiry.id}")
    return m


# --- booking ---------------------------------------------------------------------------------------------------------

def _source(customer, data: dict):
    """(plan, provider, quote, package, guests) from the customer's own quote or a package + their plan."""
    plan = EventPlan.objects.filter(customer=customer, pk=data.get("plan_id")).select_related("event_type").first()
    if plan is None:
        raise DomainError("Choose your event plan.", code="plan_required", status_code=404)
    if data.get("quote_id"):
        q = Quote.objects.select_related("enquiry__provider__partner", "enquiry__plan").filter(pk=data["quote_id"], enquiry__plan=plan).first()
        if q is None:
            raise DomainError("Quote not found.", code="not_found", status_code=404)
        return plan, q.enquiry.provider, q, None, plan.guests
    pkg = EventPackage.objects.select_related("provider__partner").filter(pk=data.get("package_id"), is_active=True).first()
    if pkg is None or not pkg.provider.is_listed:
        raise DomainError("That package isn’t available.", code="package_unavailable", status_code=404)
    guests = int(data.get("guests") or plan.guests)
    if not pkg.min_guests <= guests <= pkg.max_guests:
        raise ConflictError(f"This package is for {pkg.min_guests}–{pkg.max_guests} guests.", code="guests_out_of_range")
    return plan, pkg.provider, None, pkg, guests


def estimate(customer, data: dict) -> dict:
    plan, provider, quote, pkg, guests = _source(customer, data)
    lines, services = [], []
    if quote is not None:
        chosen = set(data.get("optional_items") or [])
        for i, item in enumerate(quote.items):
            if not item["optional"] or str(i) in chosen or item["label"] in chosen:
                lines.append({"label": item["label"] + (" (optional)" if item["optional"] else ""), "amount": item["amount"]})
        services = [s.name for s in plan.services.filter(pk__in=provider.services.all())]
        title = f"{plan.event_type.name} · {engine.name_of(provider)}"
    else:
        lines.append({"label": f"{pkg.name} ({engine.package_label(pkg)}{f' × {guests} guests' if pkg.basis == 'per_guest' else ''})",
                      "amount": f"{engine.package_amount(pkg, guests):.2f}"})
        for a in pkg.addons.filter(pk__in=data.get("addon_ids") or []):
            amt = engine.money(a.price * guests if a.per_guest else a.price)
            lines.append({"label": f"{a.name}{f' × {guests}' if a.per_guest else ''}", "amount": f"{amt:.2f}"})
        services = [s.name for s in pkg.services.all()]
        title = f"{pkg.name} · {engine.name_of(provider)}"
    subtotal = engine.money(sum((Decimal(x["amount"]) for x in lines), Decimal("0")))
    discount = Decimal("0.00")
    tax = engine.tax_on(subtotal - discount)
    total = engine.money(subtotal - discount + tax)
    problem = ""
    if plan.date is None:
        problem = "Set a fixed date on your plan before booking."
    else:
        a = engine.availability(provider, plan.date)
        if a["state"] != "available":
            problem = f"{engine.name_of(provider)}: {a['label'].lower()}."
    if quote is not None and quote.status != Quote.Status.PENDING:
        problem = problem or "This quote isn’t open any more."
    if quote is not None and quote.valid_until and quote.valid_until < engine.today():
        problem = problem or "This quote has expired. Ask the team for a new one."
    if plan.status in (EventPlan.Status.CANCELLED, EventPlan.Status.DONE):
        problem = problem or "This plan is closed."
    days = (plan.date - engine.today()).days if plan.date else None
    return {
        "title": title, "provider": {"id": str(provider.id), "name": engine.name_of(provider), "kind": provider.kind},
        "plan": {"id": str(plan.id), "number": plan.number, "event_type": plan.event_type.name, "date": plan.date.isoformat() if plan.date else None,
                 "start_time": plan.start_time.strftime("%H:%M") if plan.start_time else None, "address": plan.address},
        "guests": guests, "lines": lines, "services": services, "subtotal": f"{subtotal:.2f}", "discount": f"{discount:.2f}",
        "tax": f"{tax:.2f}", "total": f"{total:.2f}", "problem": problem, "bookable": not problem,
        "pay_later_allowed": days is not None and days > PAY_BY_DAYS,
        "cancellation": (f"Free cancellation until {provider.free_cancellation_days} days before the event; after that "
                         f"{provider.late_cancellation_fee_percent}% is kept. Within {SELF_CANCEL_DAYS} days of the event, contact support."),
        "terms": quote.terms if quote is not None else pkg.terms,
    }


@transaction.atomic
def book(customer, data: dict) -> tuple[EventBooking, bool]:
    existing = EventBooking.objects.filter(customer=customer, idempotency_key=data["idempotency_key"]).first()
    if existing:
        return existing, False
    est = estimate(customer, data)
    if not est["bookable"]:
        raise ConflictError(est["problem"], code="not_bookable", details={"estimate": est})
    if data.get("expected_total") is not None and Decimal(str(data["expected_total"])) != Decimal(est["total"]):
        raise ConflictError("The price changed. Review the new total.", code="price_changed", details={"estimate": est})
    method = data.get("payment_method") or "wallet"
    if method not in ("wallet", "pay_later") or (method == "pay_later" and not est["pay_later_allowed"]):
        raise DomainError("That payment option isn’t available for this booking.", code="payment_method_unavailable")
    plan, provider, quote, pkg, guests = _source(customer, data)
    EventProvider.objects.select_for_update().get(pk=provider.pk)  # one booking at a time per provider: no double-booking a day
    if engine.availability(provider, plan.date)["state"] != "available":
        raise ConflictError(f"{engine.name_of(provider)} was just booked for that day.", code="not_bookable")
    if quote is not None:
        q = Quote.objects.select_for_update().get(pk=quote.pk)
        if q.status != Quote.Status.PENDING:
            raise ConflictError("This quote isn’t open any more.", code="quote_closed")
    b = EventBooking.objects.create(
        customer=customer, plan=plan, provider=provider, quote=quote, package=pkg, event_date=plan.date, start_time=plan.start_time,
        guests=guests, address=plan.address, title=est["title"], lines=est["lines"], services=est["services"], subtotal=Decimal(est["subtotal"]),
        discount=Decimal(est["discount"]), tax=Decimal(est["tax"]), total=Decimal(est["total"]), idempotency_key=data["idempotency_key"])
    StatusEvent.objects.create(booking=b, to=S.PAYMENT_PENDING, note="Booking created")
    if quote is not None:
        Quote.objects.filter(pk=quote.pk).update(status=Quote.Status.ACCEPTED)
        Enquiry.objects.filter(pk=quote.enquiry_id).update(status=Enquiry.Status.ACCEPTED)
    if plan.status == EventPlan.Status.PLANNING:
        EventPlan.objects.filter(pk=plan.pk).update(status=EventPlan.Status.BOOKED)
    _milestones(b, plan)
    _tick_checklist(plan, provider, est["services"])
    if method == "wallet":
        b = pay(b)
    else:
        b.payment_method = "pay_later"
        b.save(update_fields=["payment_method", "updated_at"])
        _note(customer, f"Booking held · {b.number}", f"{b.title}. Pay from your Click. Wallet at least {PAY_BY_DAYS} days before the event to keep it.",
              f"/events/bookings/{b.id}")
    return b, True


def _milestones(b: EventBooking, plan: EventPlan) -> None:
    d = b.event_date
    rows = [("booked", "Booking made", None)]
    rows += [(f"svc-{i}", f"{name} confirmed", d - timedelta(days=7)) for i, name in enumerate(b.services[:6])]
    rows += [("guests", "Final guest count shared", d - timedelta(days=3)), ("payment", "Payment completed", d - timedelta(days=PAY_BY_DAYS)),
             ("event_day", "Event day", d), ("completed", "Event completed", d)]
    Milestone.objects.bulk_create([Milestone(booking=b, key=k, label=l, due_date=due, position=i,
                                             done_at=timezone.now() if k == "booked" else None) for i, (k, l, due) in enumerate(rows)])


def _tick_checklist(plan: EventPlan, provider: EventProvider, names: list[str]) -> None:
    slugs = set(EventService.objects.filter(name__in=names).values_list("slug", flat=True))
    plan.checklist.filter(service__slug__in=slugs, done=False).update(done=True, done_at=timezone.now(), auto=True)
    plan.checklist.filter(key="team", done=False).update(done=True, done_at=timezone.now(), auto=True)


@transaction.atomic
def pay(b: EventBooking) -> EventBooking:
    from apps.payments.models import Payment, PaymentMethod
    from apps.wallet import services as wallet

    b = EventBooking.objects.select_for_update().get(pk=b.pk)
    if b.payment_status != EventBooking.PaymentStatus.PENDING or b.status != S.PAYMENT_PENDING:
        raise ConflictError("There’s nothing to pay on this booking.", code="not_payable")
    payment = Payment.objects.create(event_booking=b, method=PaymentMethod.WALLET, amount=b.total, currency=b.currency)
    wallet.pay(b.customer, b.total, payment, f"Event booking {b.number}")
    payment.status = Payment.Status.CAPTURED
    payment.save(update_fields=["status", "updated_at"])
    b.payment_status, b.payment_method = EventBooking.PaymentStatus.PAID, "wallet"
    b.save(update_fields=["payment_status", "payment_method", "updated_at"])
    b.milestones.filter(key="payment", done_at__isnull=True).update(done_at=timezone.now())
    b.plan.checklist.filter(key="payment", done=False).update(done=True, done_at=timezone.now(), auto=True)
    return transition(b, S.CONFIRMED, "Paid from Click. Wallet",
                      notify_text=(f"Booking confirmed · {b.number}", f"{b.title} on {b.event_date:%d %b}. Paid ₹{b.total:,.2f}."))


@transaction.atomic
def transition(b: EventBooking, to: str, note: str = "", notify_text: tuple[str, str] | None = None) -> EventBooking:
    b = EventBooking.objects.select_for_update().select_related("provider__partner", "customer").get(pk=b.pk)
    if to not in ALLOWED_TRANSITIONS[b.status]:
        raise ConflictError(f"A booking that is {b.get_status_display().lower()} can’t move to that step.", code="invalid_transition")
    b.status = to
    now = timezone.now()
    fields = ["status", "updated_at"]
    for flag, attr in ((S.CONFIRMED, "confirmed_at"), (S.COMPLETED, "completed_at"), (S.CANCELLED, "cancelled_at")):
        if to == flag:
            setattr(b, attr, now)
            fields.append(attr)
    b.save(update_fields=fields)
    StatusEvent.objects.create(booking=b, to=to, note=note[:200])
    title, body = notify_text or {
        S.PREPARING: (f"Your event team is preparing · {b.number}", note or f"{engine.name_of(b.provider)} has started preparing."),
        S.IN_PROGRESS: (f"Your event has started · {b.number}", f"{engine.name_of(b.provider)} is on site."),
        S.COMPLETED: (f"Event completed · {b.number}", f"How did {engine.name_of(b.provider)} do? Leave a review."),
        S.CANCELLED: (f"Booking cancelled · {b.number}", note or b.title),
    }.get(to, (f"{b.get_status_display()} · {b.number}", b.title))
    _note(b.customer, title, body, f"/events/bookings/{b.id}")
    return b


def expire_unpaid(now=None) -> int:
    """Pay-later bookings not paid by PAY_BY_DAYS before the event close (run on reads and by a scheduler)."""
    cutoff = engine.today() + timedelta(days=PAY_BY_DAYS)
    n = 0
    for b in EventBooking.objects.filter(status=S.PAYMENT_PENDING, event_date__lte=cutoff):
        transition(b, S.CANCELLED, "Payment wasn’t completed in time",
                   notify_text=(f"Booking released · {b.number}", "It wasn’t paid in time, so the date was released. Nothing was charged."))
        n += 1
    return n


# --- provider steps --------------------------------------------------------------------------------------------------

def provider_step(b: EventBooking, provider: EventProvider, action: str, payload: dict) -> EventBooking:
    if b.provider_id != provider.id:
        raise DomainError("Not found.", code="not_found", status_code=404)
    note = str(payload.get("reason") or payload.get("note") or "").strip()[:200]
    if action == "preparing":
        if b.payment_status != EventBooking.PaymentStatus.PAID:
            raise ConflictError("Wait until the customer has paid.", code="not_paid")
        if note:
            EventBooking.objects.filter(pk=b.pk).update(team_note=note)
        return transition(b, S.PREPARING, note or "Team assigned")
    if action == "milestone":
        m = b.milestones.filter(done_at__isnull=True).exclude(key__in=["event_day", "completed", "payment"]).first()
        if m is None:
            raise ConflictError("All planning milestones are done.", code="no_milestone")
        m.done_at, m.note = timezone.now(), note
        m.save(update_fields=["done_at", "note", "updated_at"])
        _note(b.customer, f"{m.label} · {b.number}", note or f"{engine.name_of(provider)} ticked this off.", f"/events/bookings/{b.id}")
        return b
    if action == "start":
        if b.payment_status != EventBooking.PaymentStatus.PAID:
            raise ConflictError("The booking isn’t paid.", code="not_paid")
        if engine.today() < b.event_date:
            raise ConflictError("You can start on the event day.", code="too_early")
        b.milestones.filter(key="event_day", done_at__isnull=True).update(done_at=timezone.now())
        return transition(b, S.IN_PROGRESS, note or "Event started")
    if action == "complete":
        b.milestones.filter(done_at__isnull=True).update(done_at=timezone.now())
        b = transition(b, S.COMPLETED, note or "Event completed")
        recompute(provider)
        plan = b.plan
        if not plan.bookings.filter(status__in=ACTIVE).exists():
            EventPlan.objects.filter(pk=plan.pk).update(status=EventPlan.Status.DONE)
        return b
    raise DomainError("Unknown step.", code="invalid_step")


# --- customer after-booking ------------------------------------------------------------------------------------------

def cancellation(b: EventBooking) -> dict:
    if b.status not in (S.PAYMENT_PENDING, S.CONFIRMED, S.PREPARING):
        return {"allowed": False, "refund": None, "note": "This booking can’t be cancelled now."}
    days = (b.event_date - engine.today()).days
    if days < SELF_CANCEL_DAYS:
        return {"allowed": False, "refund": None, "note": f"The event is less than {SELF_CANCEL_DAYS} days away. Contact support to cancel."}
    if b.payment_status != EventBooking.PaymentStatus.PAID:
        return {"allowed": True, "refund": None, "note": "Nothing has been paid, so nothing is charged."}
    p = b.provider
    keep = Decimal("0") if days >= p.free_cancellation_days else engine.money(b.total * p.late_cancellation_fee_percent / 100)
    refund = engine.money(b.total - keep)
    note = (f"Full refund of ₹{refund:,.2f} to your Click. Wallet." if keep == 0 else
            f"Less than {p.free_cancellation_days} days before the event: ₹{keep:,.2f} ({p.late_cancellation_fee_percent}%) is kept, ₹{refund:,.2f} is refunded to your wallet.")
    return {"allowed": True, "refund": f"{refund:.2f}", "note": note}


@transaction.atomic
def cancel(b: EventBooking, reason: str) -> EventBooking:
    from apps.payments.models import Payment
    from apps.wallet import services as wallet

    c = cancellation(b)
    if not c["allowed"]:
        raise ConflictError(c["note"], code="not_cancellable")
    b = transition(b, S.CANCELLED, reason, notify_text=(f"Booking cancelled · {b.number}", c["note"]))
    if c["refund"] is not None and Decimal(c["refund"]) > 0:
        payment = b.payments.filter(status=Payment.Status.CAPTURED).first()
        if payment is not None:
            wallet.refund(b.customer, Decimal(c["refund"]), payment, f"Event booking {b.number} cancelled")
            full = Decimal(c["refund"]) == b.total
            payment.status = Payment.Status.REFUNDED if full else payment.status
            payment.save(update_fields=["status", "updated_at"])
            b.refunded = Decimal(c["refund"])
            b.payment_status = EventBooking.PaymentStatus.REFUNDED if full else EventBooking.PaymentStatus.PARTLY_REFUNDED
    b.cancel_reason = reason[:200]
    b.save(update_fields=["refunded", "payment_status", "cancel_reason", "updated_at"])
    if b.quote_id:
        Enquiry.objects.filter(pk=b.quote.enquiry_id).update(status=Enquiry.Status.WITHDRAWN)
    plan = b.plan
    if plan.status == EventPlan.Status.BOOKED and not plan.bookings.filter(status__in=ACTIVE).exists():
        EventPlan.objects.filter(pk=plan.pk).update(status=EventPlan.Status.PLANNING)
    return b


@transaction.atomic
def review(customer, b: EventBooking, data: dict) -> EventReview:
    if b.customer_id != customer.id:
        raise DomainError("Not found.", code="not_found", status_code=404)
    if b.status != S.COMPLETED:
        raise ConflictError("You can review the team after the event is completed.", code="review_not_allowed")
    if EventReview.objects.filter(booking=b).exists():
        raise ConflictError("You’ve already reviewed this booking.", code="review_exists")
    r = EventReview.objects.create(booking=b, customer=customer, provider=b.provider, overall=data["overall"], quality=data["quality"],
                                   communication=data["communication"], value=data["value"], comment=(data.get("comment") or "").strip())
    recompute(b.provider)
    return r


def recompute(p: EventProvider) -> None:
    agg = EventReview.objects.filter(provider=p, is_published=True).aggregate(a=Avg("overall"), n=Count("id"))
    EventProvider.objects.filter(pk=p.pk).update(
        rating_average=Decimal(str(round(agg["a"] or 0, 1))), rating_count=agg["n"],
        events_completed=EventBooking.objects.filter(provider=p, status=S.COMPLETED).count())
