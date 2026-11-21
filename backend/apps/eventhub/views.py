"""Click. Events API. Discovery is public; plans, photos, quotes, bookings and favourites belong to the signed-in
customer (every query is scoped to them); providers manage their own profile, dates, packages and quotes through
the partner endpoints (their own partner only)."""

from __future__ import annotations

import uuid

from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import DomainError
from apps.core.api.permissions import IsCustomer
from apps.professionals import media

from . import engine, lifecycle
from .models import (
    ACTIVE, ChecklistItem, Enquiry, EventAttachment, EventBooking, EventPackage, EventPlan, EventProvider, EventService, EventType,
    PortfolioItem, ProviderBlockedDate, Quote,
)


def _customer(request):
    u = request.user
    return u.customer_profile if u and u.is_authenticated and hasattr(u, "customer_profile") else None


def _point(request):
    c = _customer(request)
    aid = request.query_params.get("address")
    if aid and c is not None:
        try:
            a = c.addresses.filter(pk=uuid.UUID(aid)).first()
        except ValueError:
            a = None
        if a is not None and a.latitude is not None:
            return float(a.latitude), float(a.longitude)
    return None


def _favs(request) -> tuple[dict, dict]:
    c = _customer(request)
    if c is None:
        return {}, {}
    rows = c.wishlist_items.filter(Q(event_provider__isnull=False) | Q(event_package__isnull=False)).values_list("id", "event_provider_id", "event_package_id")
    return ({str(p): str(i) for i, p, _ in rows if p}, {str(k): str(i) for i, _, k in rows if k})


def _with_favs(cards: list[dict], request) -> list[dict]:
    provs, _ = _favs(request)
    for c in cards:
        c["favorite_id"] = provs.get(c["id"])
    return cards


def _registry():
    return {"event_types": [engine.type_out(t) for t in EventType.objects.filter(is_active=True)],
            "services": [engine.service_out(s) for s in EventService.objects.filter(is_active=True)],
            "guest_bands": [{"code": c, "label": l, "min": lo, "max": hi} for c, l, lo, hi in engine.GUEST_BANDS]}


# --- public ----------------------------------------------------------------------------------------------------------

class RegistryView(APIView):
    """GET /eventhub/registry — event types, services and guest bands (Business OS-managed lists)."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response(_registry())


class HomeView(APIView):
    """GET /eventhub/home?address= — what Events shows: live events to attend, teams, venues, packages, registries."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        point = _point(request)
        cards = _with_favs(engine.search_providers({}, point, request), request)
        teams = [c for c in cards if c["kind"] != "venue"]
        venues = [c for c in cards if c["kind"] == "venue"]
        pkgs = (EventPackage.objects.filter(is_active=True, provider__in=engine.listed()).select_related("provider__partner")
                .prefetch_related("services", "event_types", "addons").order_by("position", "price"))
        _, pfav = _favs(request)
        packages = []
        for x in pkgs:
            if engine.serves(x.provider, point):
                packages.append({**engine.package_out(x, with_provider=True, point=point, request=request), "favorite_id": pfav.get(str(x.id))})
        return Response({
            **_registry(), "has_location": point is not None, "live_events": engine.live_events(point, limit=10),
            "featured": [c for c in teams if c["featured"]][:8], "teams": teams[:12], "venues": venues[:10], "packages": packages,
            "counts": {"teams": len(teams), "venues": len(venues), "packages": len(packages)},
        })


class ProvidersView(APIView):
    """GET /eventhub/providers?kind&type&service&date&guests&max_budget&min_rating&verified&available&max_km&sort&q&address"""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        cards = _with_favs(engine.search_providers(request.query_params, _point(request), request), request)
        page = max(1, int(request.query_params.get("page") or 1)) if str(request.query_params.get("page") or "1").isdigit() else 1
        size = 20
        return Response({"count": len(cards), "page": page, "has_more": page * size < len(cards), "results": cards[(page - 1) * size: page * size]})


class ProviderView(APIView):
    """GET /eventhub/providers/<id>?date&guests&address — the full profile (venue details for venues)."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, pk):
        p = get_object_or_404(engine.listed(), pk=pk)
        point = _point(request)
        try:
            from datetime import date as _d
            day = _d.fromisoformat(request.query_params["date"]) if request.query_params.get("date") else None
            guests = int(request.query_params["guests"]) if request.query_params.get("guests") else None
        except ValueError:
            day, guests = None, None
        provs, pfav = _favs(request)
        reviews = p.reviews.filter(is_published=True).select_related("customer__user", "booking__plan__event_type")[:20]
        aspects = {}
        if p.rating_count:
            from django.db.models import Avg
            agg = p.reviews.filter(is_published=True).aggregate(q=Avg("quality"), c=Avg("communication"), v=Avg("value"))
            aspects = {k: round(v, 1) for k, v in (("quality", agg["q"]), ("communication", agg["c"]), ("value", agg["v"])) if v is not None}
        venue = getattr(p, "venue", None) if p.kind == "venue" else None
        upcoming_blocked = [d.isoformat() for d in p.blocked_dates.filter(date__gte=engine.today()).values_list("date", flat=True)[:60]]
        busy = list(EventBooking.objects.filter(provider=p, status__in=ACTIVE, event_date__gte=engine.today())
                    .values_list("event_date", flat=True))
        full = sorted({d.isoformat() for d in busy if busy.count(d) >= p.max_events_per_day} | set(upcoming_blocked))
        return Response({
            **engine.card(p, point, day, guests, request), "favorite_id": provs.get(str(p.id)), "about": p.about, "languages": p.languages,
            "since": p.partner.created_at.isoformat(), "faqs": p.faqs, "min_notice_days": p.min_notice_days, "max_events_per_day": p.max_events_per_day,
            "guests_range": [p.min_guests, p.max_guests], "unavailable_dates": full,
            "cancellation": {"free_days": p.free_cancellation_days, "fee_percent": p.late_cancellation_fee_percent},
            "packages": [{**engine.package_out(x, guests), "favorite_id": pfav.get(str(x.id))} for x in p.packages.filter(is_active=True).prefetch_related("services", "addons", "event_types")],
            "portfolio": [{"id": str(x.id), "caption": x.caption, "event_type": x.event_type.name if x.event_type else "", **media.urls(x, request)}
                          for x in p.portfolio.select_related("event_type")[:24]],
            "reviews": [{"id": str(r.id), "overall": r.overall, "comment": r.comment, "created_at": r.created_at.isoformat(), "verified_booking": True,
                         "event_type": r.booking.plan.event_type.name, "author": (r.customer.user.full_name or "Customer").split()[0]} for r in reviews],
            "aspects": aspects,
            "venue": {"space_type": venue.space_type, "indoor": venue.indoor, "outdoor": venue.outdoor, "seated": venue.seated_capacity,
                      "floating": venue.floating_capacity, "address": venue.address, "amenities": venue.amenities, "rules": venue.rules,
                      "parking": venue.parking, "catering_policy": venue.get_catering_policy_display(), "hours": venue.hours} if venue else None,
        })


class SearchView(APIView):
    """GET /eventhub/search?q= — event types, services, teams, venues, packages and live events (debounced by the client)."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()[:80]
        if len(q) < 2:
            return Response({"query": q, "event_types": [], "services": [], "providers": [], "packages": [], "live_events": []})
        point = _point(request)
        types = engine.match_types(q) or list(EventType.objects.filter(is_active=True, name__icontains=q))
        services = engine.match_services(q) or list(EventService.objects.filter(is_active=True, name__icontains=q))
        sq = Q(partner__business_name__icontains=q) | Q(tagline__icontains=q) | Q(area__icontains=q)
        if services:
            sq |= Q(services__in=services)
        if types:
            sq |= Q(event_types__in=types)
        svc_slugs = {x.slug for x in services}
        type_names = {t.name for t in types}
        provs = [engine.card(p, point, request=request) for p in engine.listed().filter(sq).distinct()[:40] if engine.serves(p, point)]

        def relevance(c):  # the service asked for beats the event type; a name hit beats both; then the usual order
            score = (3 if q.lower() in c["name"].lower() else 0) + 2 * len(svc_slugs & {s["slug"] for s in c["services"]}) + len(type_names & set(c["event_types"]))
            return (-score, *engine.SORTS["recommended"](c))

        provs.sort(key=relevance)
        pq = Q(name__icontains=q) | Q(description__icontains=q)
        if types:
            pq |= Q(event_types__in=types)
        pkgs = EventPackage.objects.filter(pq, is_active=True, provider__in=engine.listed()).distinct().select_related("provider__partner")[:8]
        return Response({"query": q, "event_types": [engine.type_out(t) for t in types[:6]], "services": [engine.service_out(s) for s in services[:6]],
                         "providers": provs[:10], "packages": [engine.package_out(x, with_provider=True, point=point, request=request) for x in pkgs],
                         "live_events": engine.live_events(point, limit=6, q=q)})


class LiveEventsView(APIView):
    """GET /eventhub/live?address&q — Click. Showtime live events with bookable shows."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({"results": engine.live_events(_point(request), limit=40, q=(request.query_params.get("q") or "")[:80])})


# --- customer --------------------------------------------------------------------------------------------------------

def _own_plans(request):
    return EventPlan.objects.filter(customer=request.user.customer_profile).select_related("event_type")


def _att(a, request):
    return {"id": str(a.id), **{k: v for k, v in media.urls(a, request).items() if k in ("src", "thumb")}}


def _quote_out(q: Quote) -> dict:
    return {"id": str(q.id), "version": q.version, "items": q.items, "amount": f"{q.amount:.2f}", "tax": f"{engine.tax_on(q.amount):.2f}",
            "total": f"{engine.money(q.amount + engine.tax_on(q.amount)):.2f}",
            "duration_hours": float(q.duration_hours) if q.duration_hours is not None else None, "team_size": q.team_size,
            "terms": q.terms, "notes": q.notes, "valid_until": q.valid_until.isoformat() if q.valid_until else None,
            "expired": bool(q.valid_until and q.valid_until < engine.today()), "status": q.status, "status_label": q.get_status_display(),
            "customer_note": q.customer_note, "created_at": q.created_at.isoformat()}


def enquiry_out(e: Enquiry, request) -> dict:
    p = e.provider
    return {"id": str(e.id), "status": e.status, "status_label": e.get_status_display(), "message": e.message, "created_at": e.created_at.isoformat(),
            "provider": {"id": str(p.id), "name": engine.name_of(p), "kind": p.kind, "accent": p.accent, "logo_url": engine.logo_url(p, request),
                         "verified": engine.verified(p), "rating": {"average": f"{p.rating_average:.1f}", "count": p.rating_count} if p.rating_count else None},
            "package": {"id": str(e.package.id), "name": e.package.name} if e.package_id else None,
            "quotes": [_quote_out(q) for q in e.quotes.all()],
            "messages": [{"id": str(m.id), "from_customer": m.from_customer, "body": m.body, "at": m.created_at.isoformat()} for m in e.messages.all()],
            "booking_id": str(b.id) if (b := EventBooking.objects.filter(quote__enquiry=e).exclude(status="cancelled").first()) else None}


def plan_out(plan: EventPlan, request, full: bool = False) -> dict:
    out = {"id": str(plan.id), "number": plan.number, "title": plan.title or f"{plan.event_type.name}", "status": plan.status,
           "status_label": plan.get_status_display(), "event_type": engine.type_out(plan.event_type),
           "date": plan.date.isoformat() if plan.date else None, "date_flexible": plan.date_flexible, "date_note": plan.date_note,
           "start_time": plan.start_time.strftime("%H:%M") if plan.start_time else None, "guests": plan.guests,
           "address": plan.address, "created_at": plan.created_at.isoformat(),
           "quotes_waiting": sum(1 for e in plan.enquiries.all() for q in e.quotes.all() if q.status == "pending"),
           "bookings": plan.bookings.exclude(status="cancelled").count()}
    if not full:
        return out
    done = plan.checklist.filter(done=True).count()
    return {**out, "budget": {"min": f"{plan.budget_min:.2f}" if plan.budget_min is not None else None,
                              "max": f"{plan.budget_max:.2f}" if plan.budget_max is not None else None, "flexible": plan.budget_flexible},
            "services": [engine.service_out(s) for s in plan.services.all()], "requirements": plan.requirements, "needs_venue": plan.needs_venue,
            "attachments": [_att(a, request) for a in plan.attachments.all()],
            "checklist": [{"id": str(c.id), "label": c.label, "done": c.done, "auto": c.auto, "service": c.service.name if c.service_id else None,
                           "custom": not c.key} for c in plan.checklist.select_related("service")],
            "progress": {"done": done, "total": plan.checklist.count()},
            "enquiries": [enquiry_out(e, request) for e in plan.enquiries.select_related("provider__partner", "package").prefetch_related("quotes", "messages")],
            "booking_list": [booking_out(b, request) for b in plan.bookings.select_related("provider__partner")]}


def booking_out(b: EventBooking, request, full: bool = False) -> dict:
    p = b.provider
    out = {"id": str(b.id), "number": b.number, "title": b.title, "status": b.status, "status_label": b.get_status_display(),
           "payment_status": b.payment_status, "payment_status_label": b.get_payment_status_display(), "event_date": b.event_date.isoformat(),
           "start_time": b.start_time.strftime("%H:%M") if b.start_time else None, "guests": b.guests, "total": f"{b.total:.2f}",
           "created_at": b.created_at.isoformat(), "is_active": b.status in ACTIVE, "plan_id": str(b.plan_id),
           "provider": {"id": str(p.id), "name": engine.name_of(p), "kind": p.kind, "accent": p.accent, "logo_url": engine.logo_url(p, request),
                        "verified": engine.verified(p)}, "reviewed": hasattr(b, "review")}
    if not full:
        return out
    from apps.payments.models import Payment

    pay = b.payments.order_by("-created_at").first()
    return {**out, "address": b.address, "lines": b.lines, "services": b.services, "subtotal": f"{b.subtotal:.2f}", "discount": f"{b.discount:.2f}",
            "tax": f"{b.tax:.2f}", "refunded": f"{b.refunded:.2f}", "package": b.package.name if b.package_id else None,
            "quote_version": b.quote.version if b.quote_id else None, "team_note": b.team_note, "cancel_reason": b.cancel_reason,
            "plan": {"id": str(b.plan_id), "number": b.plan.number, "event_type": b.plan.event_type.name, "requirements": b.plan.requirements,
                     "attachments": [_att(a, request) for a in b.plan.attachments.all()]},
            "milestones": [{"key": m.key, "label": m.label, "due_date": m.due_date.isoformat() if m.due_date else None,
                            "done_at": m.done_at.isoformat() if m.done_at else None, "note": m.note} for m in b.milestones.all()],
            "timeline": [{"to": e.to, "label": e.get_to_display(), "note": e.note, "at": e.created_at.isoformat()} for e in b.events.all()],
            "payment": {"method": pay.method, "status": pay.status, "amount": f"{pay.amount:.2f}"} if pay else None,
            "can_pay": b.status == "payment_pending" and b.payment_status == "pending",
            "pay_by": (b.event_date - __import__("datetime").timedelta(days=lifecycle.PAY_BY_DAYS)).isoformat(),
            "cancellation": lifecycle.cancellation(b), "can_review": b.status == "completed" and not hasattr(b, "review"),
            "review": {"overall": b.review.overall, "quality": b.review.quality, "communication": b.review.communication, "value": b.review.value,
                       "comment": b.review.comment} if hasattr(b, "review") else None,
            "tickets": [{"id": str(t.id), "reference": t.reference, "status": t.status} for t in b.support_tickets.all()],
            "terms": (b.quote.terms if b.quote_id else b.package.terms if b.package_id else "")}


class AttachmentView(APIView):
    """POST /customer/eventhub/attachments (multipart `file`) — a reference photo for a plan (EXIF stripped)."""

    permission_classes = [IsCustomer]
    parser_classes = [MultiPartParser, FormParser]
    throttle_scope = "uploads"

    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            raise DomainError("Choose a photo.", code="validation_error")
        c = request.user.customer_profile
        if EventAttachment.objects.filter(customer=c, plan__isnull=True).count() >= 20:
            raise DomainError("Too many unused photos. Remove some first.", code="too_many_uploads")
        a = EventAttachment(customer=c)
        media.store(a, upload, "events/requests")
        a.save()
        return Response(_att(a, request), status=status.HTTP_201_CREATED)


class AttachmentDetailView(APIView):
    permission_classes = [IsCustomer]

    def delete(self, request, pk):
        a = get_object_or_404(EventAttachment, pk=pk, customer=request.user.customer_profile, plan__isnull=True)
        media.delete(a)
        a.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PlanInput(serializers.Serializer):
    event_type = serializers.SlugField()
    title = serializers.CharField(max_length=120, required=False, allow_blank=True)
    date = serializers.DateField(required=False, allow_null=True)
    date_flexible = serializers.BooleanField(required=False, default=False)
    date_note = serializers.CharField(max_length=120, required=False, allow_blank=True)
    start_time = serializers.TimeField(required=False, allow_null=True)
    address_id = serializers.UUIDField(required=False, allow_null=True)
    guests = serializers.IntegerField(min_value=1, max_value=100000)
    budget_min = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False, allow_null=True)
    budget_max = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False, allow_null=True)
    budget_flexible = serializers.BooleanField(required=False, default=False)
    services = serializers.ListField(child=serializers.SlugField(), max_length=20)
    requirements = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    attachment_ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list, max_length=6)


class PlansView(APIView):
    """GET /customer/eventhub/plans ; POST creates a plan (the 'Plan an Event' flow)."""

    permission_classes = [IsCustomer]

    def get(self, request):
        plans = _own_plans(request).prefetch_related("enquiries__quotes")
        return Response({"results": [plan_out(p, request) for p in plans[:50]]})

    def post(self, request):
        s = PlanInput(data=request.data)
        s.is_valid(raise_exception=True)
        plan = lifecycle.create_plan(request.user.customer_profile, s.validated_data)
        return Response(plan_out(_own_plans(request).get(pk=plan.pk), request, True), status=status.HTTP_201_CREATED)


class PlanDetailView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request, pk):
        return Response(plan_out(get_object_or_404(_own_plans(request), pk=pk), request, True))

    def delete(self, request, pk):
        """Cancel a plan that has no active bookings (open quote requests are withdrawn)."""
        plan = get_object_or_404(_own_plans(request), pk=pk)
        if plan.bookings.filter(status__in=ACTIVE).exists():
            raise DomainError("Cancel the plan’s bookings first.", code="plan_has_bookings", status_code=409)
        plan.enquiries.filter(status__in=Enquiry.OPEN).update(status=Enquiry.Status.WITHDRAWN)
        plan.status = EventPlan.Status.CANCELLED
        plan.save(update_fields=["status", "updated_at"])
        return Response(plan_out(plan, request, True))


class PlanMatchesView(APIView):
    """GET /customer/eventhub/plans/<id>/matches?kind — teams, specialists and venues that fit this plan."""

    permission_classes = [IsCustomer]

    def get(self, request, pk):
        plan = get_object_or_404(_own_plans(request), pk=pk)
        return Response({"results": _with_favs(lifecycle.matches(plan, request.query_params, request), request)})


class EnquireInput(serializers.Serializer):
    provider_ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=lifecycle.MAX_ENQUIRIES_AT_ONCE)
    package_id = serializers.UUIDField(required=False, allow_null=True)
    message = serializers.CharField(max_length=600, required=False, allow_blank=True, default="")


class PlanEnquireView(APIView):
    """POST /customer/eventhub/plans/<id>/enquiries — ask up to 5 matching providers for quotes."""

    permission_classes = [IsCustomer]

    def post(self, request, pk):
        plan = get_object_or_404(_own_plans(request), pk=pk)
        s = EnquireInput(data=request.data)
        s.is_valid(raise_exception=True)
        lifecycle.send_enquiries(plan, [str(x) for x in s.validated_data["provider_ids"]], s.validated_data.get("package_id"), s.validated_data["message"])
        return Response(plan_out(_own_plans(request).get(pk=pk), request, True), status=status.HTTP_201_CREATED)


class ChecklistView(APIView):
    """POST /customer/eventhub/plans/<id>/checklist {label} ; PATCH/DELETE .../checklist/<item> {done}."""

    permission_classes = [IsCustomer]

    def post(self, request, pk):
        plan = get_object_or_404(_own_plans(request), pk=pk)
        label = str(request.data.get("label") or "").strip()[:120]
        if len(label) < 2:
            raise DomainError("Type the task.", code="validation_error")
        if plan.checklist.count() >= 40:
            raise DomainError("The checklist is full.", code="checklist_full")
        ChecklistItem.objects.create(plan=plan, label=label, position=plan.checklist.count() + 100)
        return Response(plan_out(plan, request, True), status=status.HTTP_201_CREATED)

    def patch(self, request, pk, item):
        plan = get_object_or_404(_own_plans(request), pk=pk)
        c = get_object_or_404(plan.checklist, pk=item)
        from django.utils import timezone

        c.done = bool(request.data.get("done"))
        c.done_at = timezone.now() if c.done else None
        c.auto = False
        c.save(update_fields=["done", "done_at", "auto", "updated_at"])
        return Response(plan_out(plan, request, True))

    def delete(self, request, pk, item):
        plan = get_object_or_404(_own_plans(request), pk=pk)
        c = get_object_or_404(plan.checklist, pk=item, key="")
        c.delete()
        return Response(plan_out(plan, request, True))


def _own_enquiry(request, pk) -> Enquiry:
    return get_object_or_404(Enquiry.objects.select_related("plan", "provider__partner"), pk=pk, plan__customer=request.user.customer_profile)


class EnquiryActionView(APIView):
    """POST /customer/eventhub/enquiries/<id>/<reject|changes|message|withdraw>"""

    permission_classes = [IsCustomer]

    def post(self, request, pk, action):
        e = _own_enquiry(request, pk)
        note = str(request.data.get("note") or request.data.get("body") or "")
        if action in ("reject", "changes"):
            q = e.quotes.filter(status=Quote.Status.PENDING).first()
            if q is None:
                raise DomainError("There’s no quote waiting for you.", code="no_quote", status_code=409)
            lifecycle.customer_quote_decision(q, action, note)
        elif action == "message":
            lifecycle.post_message(e, True, note)
        elif action == "withdraw":
            if e.status not in Enquiry.OPEN:
                raise DomainError("This request is closed.", code="enquiry_closed", status_code=409)
            e.status = Enquiry.Status.WITHDRAWN
            e.save(update_fields=["status", "updated_at"])
            e.quotes.filter(status=Quote.Status.PENDING).update(status=Quote.Status.SUPERSEDED)
        else:
            raise DomainError("Unknown action.", code="unknown_action", status_code=404)
        e = Enquiry.objects.select_related("provider__partner", "package").prefetch_related("quotes", "messages").get(pk=e.pk)
        return Response(enquiry_out(e, request))


class BookInput(serializers.Serializer):
    plan_id = serializers.UUIDField()
    quote_id = serializers.UUIDField(required=False, allow_null=True)
    package_id = serializers.UUIDField(required=False, allow_null=True)
    guests = serializers.IntegerField(min_value=1, max_value=100000, required=False, allow_null=True)
    addon_ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list, max_length=20)
    optional_items = serializers.ListField(child=serializers.CharField(max_length=10), required=False, default=list, max_length=30)
    payment_method = serializers.ChoiceField(choices=["wallet", "pay_later"], required=False, default="wallet")
    expected_total = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    idempotency_key = serializers.CharField(max_length=64, required=False)

    def validate(self, attrs):
        if bool(attrs.get("quote_id")) == bool(attrs.get("package_id")):
            raise serializers.ValidationError("Book from either a quote or a package.")
        return attrs


class EstimateView(APIView):
    permission_classes = [IsCustomer]

    def post(self, request):
        s = BookInput(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(lifecycle.estimate(request.user.customer_profile, s.validated_data))


def _own_bookings(request):
    return (EventBooking.objects.filter(customer=request.user.customer_profile)
            .select_related("provider__partner", "plan__event_type", "quote", "package").prefetch_related("milestones", "events", "payments", "support_tickets"))


class BookingsView(APIView):
    """GET /customer/eventhub/bookings?when=active|past ; POST books (Confirm Booking)."""

    permission_classes = [IsCustomer]

    def get(self, request):
        lifecycle.expire_unpaid()
        qs = _own_bookings(request)
        when = request.query_params.get("when")
        if when == "active":
            qs = qs.filter(status__in=ACTIVE).order_by("event_date")
        elif when == "past":
            qs = qs.exclude(status__in=ACTIVE)
        return Response({"results": [booking_out(b, request) for b in qs[:50]]})

    def post(self, request):
        s = BookInput(data=request.data)
        s.is_valid(raise_exception=True)
        if not s.validated_data.get("idempotency_key"):
            raise DomainError("Missing idempotency key.", code="validation_error")
        b, created = lifecycle.book(request.user.customer_profile, s.validated_data)
        return Response(booking_out(_own_bookings(request).get(pk=b.pk), request, True), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class ReviewInput(serializers.Serializer):
    overall = serializers.IntegerField(min_value=1, max_value=5)
    quality = serializers.IntegerField(min_value=1, max_value=5)
    communication = serializers.IntegerField(min_value=1, max_value=5)
    value = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(max_length=1500, required=False, allow_blank=True, default="")


class BookingDetailView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request, pk):
        lifecycle.expire_unpaid()
        return Response(booking_out(get_object_or_404(_own_bookings(request), pk=pk), request, True))


class BookingActionView(APIView):
    """POST /customer/eventhub/bookings/<id>/<pay|cancel|review>"""

    permission_classes = [IsCustomer]

    def post(self, request, pk, action):
        b = get_object_or_404(_own_bookings(request), pk=pk)
        if action == "pay":
            lifecycle.pay(b)
        elif action == "cancel":
            reason = str(request.data.get("reason") or "").strip()
            if len(reason) < 2:
                raise DomainError("Tell us why you’re cancelling.", code="validation_error")
            lifecycle.cancel(b, reason)
        elif action == "review":
            s = ReviewInput(data=request.data)
            s.is_valid(raise_exception=True)
            lifecycle.review(request.user.customer_profile, b, s.validated_data)
        else:
            raise DomainError("Unknown action.", code="unknown_action", status_code=404)
        return Response(booking_out(_own_bookings(request).get(pk=pk), request, True))


class FavoritesView(APIView):
    """GET /customer/eventhub/favorites — saved teams/venues and packages (shared Wishlist rows)."""

    permission_classes = [IsCustomer]

    def get(self, request):
        c = request.user.customer_profile
        point = _point(request)
        rows = c.wishlist_items.filter(Q(event_provider__isnull=False) | Q(event_package__isnull=False)).select_related("event_provider__partner", "event_package__provider__partner")
        provs, pkgs = [], []
        for r in rows:
            if r.event_provider_id and r.event_provider.is_listed:
                provs.append({**engine.card(r.event_provider, point, request=request), "favorite_id": str(r.id)})
            elif r.event_package_id and r.event_package.is_active:
                pkgs.append({**engine.package_out(r.event_package, with_provider=True, point=point, request=request), "favorite_id": str(r.id)})
        return Response({"providers": provs, "packages": pkgs})


# --- partner ---------------------------------------------------------------------------------------------------------

def own_provider(request) -> EventProvider:
    from apps.partners.views import _onboarded_partner

    p = EventProvider.objects.filter(partner=_onboarded_partner(request)).first()
    if p is None:
        raise DomainError("Your Click. Events profile isn’t set up yet.", code="not_an_event_provider", status_code=404)
    return p


class QuoteItemInput(serializers.Serializer):
    label = serializers.CharField(max_length=120)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    optional = serializers.BooleanField(required=False, default=False)


class QuoteInput(serializers.Serializer):
    items = QuoteItemInput(many=True, min_length=1, max_length=30)
    duration_hours = serializers.DecimalField(max_digits=4, decimal_places=1, required=False, allow_null=True)
    team_size = serializers.IntegerField(min_value=1, max_value=1000, required=False, allow_null=True)
    terms = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    notes = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    valid_until = serializers.DateField(required=False, allow_null=True)


class PartnerEnquiryView(APIView):
    """GET /partner/eventhub/enquiries/<id> (the request, photos, messages) ; POST .../quote (itemised) | .../message | .../decline"""

    permission_classes = [permissions.IsAuthenticated]

    def _get(self, request, pk) -> Enquiry:
        return get_object_or_404(Enquiry.objects.select_related("plan__event_type", "provider__partner"), pk=pk, provider=own_provider(request))

    def get(self, request, pk, action=None):
        e = self._get(request, pk)
        plan = e.plan
        return Response({**enquiry_out(e, request), "plan": {
            "number": plan.number, "event_type": plan.event_type.name, "date": plan.date.isoformat() if plan.date else None,
            "date_note": plan.date_note, "guests": plan.guests, "area": plan.address.get("line2") or plan.address.get("city", ""),
            "services": [s.name for s in plan.services.all()], "requirements": plan.requirements,
            "budget": {"min": str(plan.budget_min) if plan.budget_min is not None else None, "max": str(plan.budget_max) if plan.budget_max is not None else None,
                       "flexible": plan.budget_flexible},
            "attachments": [_att(a, request) for a in plan.attachments.all()]}})

    def post(self, request, pk, action):
        e = self._get(request, pk)
        if action == "quote":
            s = QuoteInput(data=request.data)
            s.is_valid(raise_exception=True)
            lifecycle.provider_quote(e, e.provider, {**s.validated_data, "items": [dict(i) for i in s.validated_data["items"]]})
        elif action == "message":
            lifecycle.post_message(e, False, str(request.data.get("body") or ""))
        elif action == "decline":
            lifecycle.provider_decline(e, e.provider, str(request.data.get("reason") or ""))
        else:
            raise DomainError("Unknown action.", code="unknown_action", status_code=404)
        return self.get(request, pk)


class PartnerProfileView(APIView):
    """GET/PATCH /partner/eventhub/profile ; POST multipart `logo` or `cover`."""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    FIELDS = ("tagline", "about", "experience_years", "team_size", "languages", "service_radius_km", "max_events_per_day", "min_notice_days",
              "min_guests", "max_guests", "faqs", "free_cancellation_days", "late_cancellation_fee_percent")

    class Input(serializers.Serializer):
        tagline = serializers.CharField(max_length=140, required=False, allow_blank=True)
        about = serializers.CharField(max_length=3000, required=False, allow_blank=True)
        experience_years = serializers.IntegerField(min_value=0, max_value=80, required=False, allow_null=True)
        team_size = serializers.IntegerField(min_value=1, max_value=5000, required=False, allow_null=True)
        languages = serializers.ListField(child=serializers.CharField(max_length=30), max_length=10, required=False)
        service_radius_km = serializers.IntegerField(min_value=1, max_value=500, required=False)
        max_events_per_day = serializers.IntegerField(min_value=1, max_value=50, required=False)
        min_notice_days = serializers.IntegerField(min_value=0, max_value=365, required=False)
        min_guests = serializers.IntegerField(min_value=1, required=False, allow_null=True)
        max_guests = serializers.IntegerField(min_value=1, required=False, allow_null=True)
        faqs = serializers.ListField(child=serializers.DictField(child=serializers.CharField(max_length=600)), max_length=20, required=False)
        free_cancellation_days = serializers.IntegerField(min_value=0, max_value=365, required=False)
        late_cancellation_fee_percent = serializers.IntegerField(min_value=0, max_value=100, required=False)
        services = serializers.ListField(child=serializers.SlugField(), max_length=20, required=False)
        event_types = serializers.ListField(child=serializers.SlugField(), max_length=30, required=False)

    def get(self, request):
        p = own_provider(request)
        return Response({**engine.card(p, request=request), "about": p.about, "faqs": p.faqs, "listed": p.is_listed,
                         **{k: getattr(p, k) for k in self.FIELDS if k not in ("about", "faqs")},
                         "blocked_dates": [d.isoformat() for d in p.blocked_dates.filter(date__gte=engine.today()).values_list("date", flat=True)],
                         "packages": [engine.package_out(x) for x in p.packages.all()],
                         "portfolio": [{"id": str(x.id), "caption": x.caption, **media.urls(x, request)} for x in p.portfolio.all()]})

    def patch(self, request):
        p = own_provider(request)
        s = self.Input(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        d = dict(s.validated_data)
        if "services" in d:
            p.services.set(EventService.objects.filter(slug__in=d.pop("services"), is_active=True))
        if "event_types" in d:
            p.event_types.set(EventType.objects.filter(slug__in=d.pop("event_types"), is_active=True))
        for k, v in d.items():
            setattr(p, k, v)
        p.save()
        return self.get(request)

    def post(self, request):
        p = own_provider(request)
        if request.FILES.get("logo"):
            p.logo.save("logo.webp", media.profile_photo(request.FILES["logo"]), save=True)
        elif request.FILES.get("cover"):
            holder = PortfolioItem()
            media.store(holder, request.FILES["cover"], "events/covers")
            p.cover = holder.renditions
            p.save(update_fields=["cover", "updated_at"])
        else:
            raise DomainError("Choose a logo or cover photo.", code="validation_error")
        return self.get(request)


class PartnerDatesView(APIView):
    """PUT /partner/eventhub/dates {"blocked": ["2026-12-24", ...]} replaces upcoming blocked dates."""

    permission_classes = [permissions.IsAuthenticated]

    def put(self, request):
        p = own_provider(request)
        s = serializers.ListField(child=serializers.DateField(), max_length=366).run_validation(request.data.get("blocked") or [])
        p.blocked_dates.filter(date__gte=engine.today()).delete()
        ProviderBlockedDate.objects.bulk_create([ProviderBlockedDate(provider=p, date=d) for d in sorted(set(s)) if d >= engine.today()])
        return Response({"blocked": [d.isoformat() for d in p.blocked_dates.filter(date__gte=engine.today()).values_list("date", flat=True)]})


class PartnerPortfolioView(APIView):
    """POST /partner/eventhub/portfolio (multipart `file`, `caption`) ; DELETE .../portfolio/<id>."""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        p = own_provider(request)
        if p.portfolio.count() >= 60:
            raise DomainError("Your portfolio is full.", code="portfolio_full")
        upload = request.FILES.get("file")
        if upload is None:
            raise DomainError("Choose a photo.", code="validation_error")
        x = PortfolioItem(provider=p, caption=str(request.data.get("caption", ""))[:160])
        media.store(x, upload, "events/portfolio")
        x.save()
        return Response({"id": str(x.id), "caption": x.caption, **media.urls(x, request)}, status=status.HTTP_201_CREATED)

    def delete(self, request, pk):
        x = get_object_or_404(PortfolioItem, pk=pk, provider=own_provider(request))
        media.delete(x)
        x.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
