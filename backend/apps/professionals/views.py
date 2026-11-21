"""Click. Services API. Discovery is public; bookings, photos, needs and favourites belong to the signed-in customer;
the professional's own profile is managed through the partner endpoints (their own partner only)."""

from __future__ import annotations

import uuid

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.activity.services import record
from apps.core.api.exceptions import DomainError
from apps.core.api.permissions import IsCustomer

from . import engine, lifecycle, media
from .models import (
    ACTIVE, BookingStatus, ProviderAvailability, ProviderJobPrice, ProviderPortfolio, ProviderProfile, ServiceAttachment, ServiceBooking,
    ServiceCategory, ServiceJob, ServiceNeed, ServiceReview,
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
    try:
        lat, lng = float(request.query_params["lat"]), float(request.query_params["lng"])
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            return lat, lng
    except (KeyError, ValueError):
        pass
    return None


def _cat(c: ServiceCategory, count: int | None = None) -> dict:
    return {"slug": c.slug, "name": c.name, "profession": c.profession, "group": c.group, "group_label": c.get_group_display(),
            "icon": c.icon, "accent": c.accent, "summary": c.summary, "professionals": count}


def _job(j: ServiceJob, provider=None) -> dict:
    price = engine.price_for(provider, j)
    return {"id": str(j.id), "slug": j.slug, "name": j.name, "description": j.description, "includes": j.includes, "excludes": j.excludes,
            "pricing": j.pricing, "pricing_label": j.get_pricing_display(), "price": f"{price:.2f}" if price is not None else None,
            "price_label": engine.price_label(j.pricing, price), "min_hours": j.min_hours,
            "inspection_fee": f"{j.inspection_fee:.2f}" if j.inspection_fee else None, "duration_minutes": j.duration_minutes,
            "instant": j.instant, "schedulable": j.schedulable}


SORTS = {
    "recommended": lambda c: (c["availability"] != "now", -(float(c["rating"]["average"]) if c["rating"] else 0) * 2 - min(c["jobs_completed"], 500) / 100),
    "nearest": lambda c: (c["distance_km"] is None, c["distance_km"] or 0),
    "rating": lambda c: (-(float(c["rating"]["average"]) if c["rating"] else 0), -(c["rating"]["count"] if c["rating"] else 0)),
    "experience": lambda c: (-(c["experience_years"] or 0),),
    "price": lambda c: (c["price"] is None, float(c["price"] or 0)),
    "available": lambda c: ({"now": 0, "today": 1, "tomorrow": 2, "later": 3, "none": 4}[c["availability"]],),
}


def provider_cards(request, category: ServiceCategory, job: ServiceJob | None = None, params=None) -> list[dict]:
    params = params or {}
    point = _point(request)
    cards = [engine.card(p, point, category, job, request=request) for p in engine.providers_for(category, point)]
    if params.get("available_now") == "true":
        cards = [c for c in cards if c["availability"] == "now"]
    if params.get("verified") == "true":
        cards = [c for c in cards if c["verified"]]
    try:
        if params.get("min_rating"):
            cards = [c for c in cards if c["rating"] and float(c["rating"]["average"]) >= float(params["min_rating"])]
        if params.get("min_experience"):
            cards = [c for c in cards if (c["experience_years"] or 0) >= int(params["min_experience"])]
        if params.get("max_price"):
            cards = [c for c in cards if c["price"] is not None and float(c["price"]) <= float(params["max_price"])]
        if params.get("max_km") and point is not None:
            cards = [c for c in cards if c["distance_km"] is not None and c["distance_km"] <= float(params["max_km"])]
    except ValueError:
        pass
    sort = params.get("sort") if params.get("sort") in SORTS else "recommended"
    return sorted(cards, key=SORTS[sort])


class HomeView(APIView):
    """GET /services/home?address|lat&lng — categories, professionals near you, available now, trusted, offers."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        lifecycle.expire_due()
        point = _point(request)
        cats = list(ServiceCategory.objects.filter(is_active=True).prefetch_related("jobs"))
        everyone, per_cat = {}, {}
        for c in cats:
            ps = engine.providers_for(c, point)
            per_cat[c.slug] = len(ps)
            for p in ps:
                everyone.setdefault(p.id, p)
        cards = [engine.card(p, point, request=request) for p in everyone.values()]
        popular = sorted(cards, key=lambda x: (-x["jobs_completed"], -(float(x["rating"]["average"]) if x["rating"] else 0)))[:10]
        now = [c for c in cards if c["availability"] == "now"]
        trusted = sorted([c for c in cards if c["verified"] and c["rating"] and c["rating"]["count"] >= 3 and float(c["rating"]["average"]) >= 4.5],
                         key=lambda x: -float(x["rating"]["average"]))[:10]
        groups = []
        for code, label in ServiceCategory.Group.choices:
            items = [_cat(c, per_cat[c.slug]) for c in cats if c.group == code and per_cat[c.slug]]
            if items:
                groups.append({"code": code, "label": label, "categories": items})
        return Response({
            "has_location": point is not None,
            "categories": [_cat(c, per_cat[c.slug]) for c in cats if per_cat[c.slug]],
            "groups": groups, "popular": popular, "available_now": sorted(now, key=lambda x: x["eta_minutes"] or 999)[:10], "trusted": trusted,
            "offers": [engine.offer_card(o) for o in engine.live_offers()],
            "unsupported_categories": [c.name for c in cats if not per_cat[c.slug]],
        })


class SearchView(APIView):
    """GET /services/search?q — categories, jobs and professionals matching the words (and synonyms)."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        q = request.query_params.get("q", "")[:80]
        cats = engine.match_categories(q)
        jobs = engine.match_jobs(q)
        ws = engine.words(q)
        pros = []
        if ws:
            pq = Q()
            for w in ws:
                pq |= Q(partner__business_name__icontains=w) | Q(partner__profile__contact_name__icontains=w) | Q(skills__icontains=w)
            point = _point(request)
            pros = [engine.card(p, point, request=request) for p in engine.listed().filter(pq).distinct()[:8] if engine.serves(p, point)]
        return Response({"query": q, "categories": [_cat(c) for c, _ in cats[:5]],
                         "jobs": [{**_job(j), "category": {"slug": j.category.slug, "name": j.category.name}} for j in jobs],
                         "professionals": pros})


class CategoryView(APIView):
    """GET /services/categories/<slug>?address&job&sort&… — what we help with, common jobs, offers, professionals."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        c = get_object_or_404(ServiceCategory.objects.filter(is_active=True), slug=slug)
        job = c.jobs.filter(pk=request.query_params.get("job"), is_active=True).first() if request.query_params.get("job") else None
        return Response({**_cat(c), "jobs": [_job(j) for j in c.jobs.filter(is_active=True)],
                         "offers": [engine.offer_card(o) for o in engine.live_offers(c)],
                         "professionals": provider_cards(request, c, job, request.query_params), "has_location": _point(request) is not None})


class ProviderView(APIView):
    """GET /services/providers/<id> — the full profile (no phone numbers or exact address)."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, pk):
        p = get_object_or_404(engine.listed(), pk=pk)
        point = _point(request)
        _, radius, area = engine.base(p)
        customer = _customer(request)
        if customer is not None:
            record(customer, "service.pro_viewed", obj=p)
        reviews = ServiceReview.objects.filter(provider=p, status=ServiceReview.Status.PUBLISHED).select_related("customer__user", "booking__job")
        cats = [s.category for s in p.services.all()]
        favorite = None
        if customer is not None:
            from apps.wishlists.models import WishlistItem

            favorite = str(WishlistItem.objects.filter(customer=customer, provider=p).values_list("id", flat=True).first() or "") or None
        aspects = {}
        if reviews.exists():
            from django.db.models import Avg

            agg = reviews.aggregate(q=Avg("quality"), b=Avg("behaviour"), t=Avg("timeliness"))
            aspects = {"quality": round(agg["q"], 1), "behaviour": round(agg["b"], 1), "timeliness": round(agg["t"], 1)}
        return Response({
            **engine.card(p, point, request=request), "about": p.about, "skills": p.skills, "service_area": area, "service_radius_km": radius,
            "serves_location": engine.serves(p, point) if point else None, "since": p.partner.created_at.isoformat(),
            "certificates": [{"name": x.name, "issuer": x.issuer} for x in p.certificates.filter(verified_at__isnull=False)],
            "portfolio": [{"id": str(x.id), "caption": x.caption, **media.urls(x, request)} for x in p.portfolio.all()],
            "hours": [{"weekday": h.weekday, "starts": h.starts_at.strftime("%I:%M %p").lstrip("0"), "ends": h.ends_at.strftime("%I:%M %p").lstrip("0")}
                      for h in p.hours.all()],
            "services": [{**_cat(c), "jobs": [_job(j, p) for j in c.jobs.filter(is_active=True)]} for c in cats],
            "reviews": [{"id": str(r.id), "overall": r.overall, "comment": r.comment, "job": r.booking.job.name, "created_at": r.created_at.isoformat(),
                         "author": (r.customer.user.full_name or "Click customer").split(" ")[0]} for r in reviews[:10]],
            "aspects": aspects, "rates": engine.rates(p), "favorite_id": favorite,
            "partner_status": p.partner.get_status_display(),
        })


class SlotsView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, pk):
        p = get_object_or_404(engine.listed(), pk=pk)
        job = get_object_or_404(ServiceJob.objects.filter(is_active=True), pk=request.query_params.get("job"))
        return Response({"available_now": engine.available_now(p), "slots": engine.slots(p, job)})


# --- customer -----------------------------------------------------------------------------------------------------

class AttachmentView(APIView):
    """POST /customer/services/attachments (multipart `file`) — a problem photo, kept private to the customer's booking."""

    permission_classes = [IsCustomer]
    parser_classes = [MultiPartParser, FormParser]
    throttle_scope = "uploads"

    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            raise DomainError("Choose a photo.", code="file_required")
        c = request.user.customer_profile
        if ServiceAttachment.objects.filter(customer=c, booking__isnull=True, need__isnull=True).count() >= 20:
            raise DomainError("Too many unused photos. Remove some first.", code="limit_reached")
        a = ServiceAttachment(customer=c)
        media.store(a, upload, f"service-photos/{c.id.hex[:8]}")
        a.save()
        return Response({"id": str(a.id), **media.urls(a, request)}, status=status.HTTP_201_CREATED)


class AttachmentDetailView(APIView):
    permission_classes = [IsCustomer]

    def delete(self, request, pk):
        a = get_object_or_404(ServiceAttachment, pk=pk, customer=request.user.customer_profile, booking__isnull=True, need__isnull=True)
        media.delete(a)
        a.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class EstimateInput(serializers.Serializer):
    job_id = serializers.UUIDField()
    provider_id = serializers.UUIDField(required=False, allow_null=True)
    address_id = serializers.UUIDField(required=False, allow_null=True)
    mode = serializers.ChoiceField(choices=ServiceBooking.Mode.choices, default="now")
    scheduled_start = serializers.DateTimeField(required=False, allow_null=True)
    hours = serializers.IntegerField(min_value=1, max_value=12, required=False, allow_null=True)


class BookInput(EstimateInput):
    address_id = serializers.UUIDField()
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    attachment_ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list, max_length=5)
    expected_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    idempotency_key = serializers.UUIDField()
    rebook_of = serializers.UUIDField(required=False, allow_null=True)


class EstimateView(APIView):
    permission_classes = [IsCustomer]

    def post(self, request):
        s = EstimateInput(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(lifecycle.estimate(request.user.customer_profile, s.validated_data))


def _owned(request):
    return (ServiceBooking.objects.filter(customer=request.user.customer_profile)
            .select_related("job", "category", "provider__partner__profile", "provider__category", "requested_provider__partner__profile")
            .prefetch_related("events", "quotes", "attachments", "payments", "support_tickets"))


def booking_out(b: ServiceBooking, request, full: bool = False) -> dict:
    pro = None
    if b.provider_id:
        p = b.provider
        pro = {"id": str(p.id), "name": engine.name_of(p), "profession": p.category.profession, "photo_url": engine.photo_url(p, request),
               "rating": {"average": f"{p.rating_average:.1f}", "count": p.rating_count} if p.rating_count else None, "verified": engine.verified(p)}
    out = {
        "id": str(b.id), "number": b.number, "status": b.status, "status_label": b.get_status_display(),
        "category": {"slug": b.category.slug, "name": b.category.name, "accent": b.category.accent, "icon": b.category.icon},
        "job": {"id": str(b.job_id), "name": b.job.name}, "mode": b.mode, "scheduled_start": b.scheduled_start.isoformat() if b.scheduled_start else None,
        "address_label": f"{b.address.get('label', '').title()} · {b.address.get('line2') or b.address.get('city', '')}",
        "pricing": b.pricing, "pricing_label": b.get_pricing_display(), "agreed_amount": f"{b.agreed_amount:.2f}" if b.agreed_amount is not None else None,
        "total": f"{b.total:.2f}" if b.total is not None else None, "provider": pro, "created_at": b.created_at.isoformat(),
        "requested_provider": {"id": str(b.requested_provider_id), "name": engine.name_of(b.requested_provider)}
        if b.requested_provider_id and not b.provider_id else None,
        "is_active": b.status in ACTIVE, "reviewed": hasattr(b, "review"),
    }
    if not full:
        return out
    q = b.quotes.all()
    return {**out,
            "address": b.address, "description": b.description, "unit_price": f"{b.unit_price:.2f}" if b.unit_price is not None else None,
            "price_label": engine.price_label(b.pricing, b.unit_price), "hours": b.hours, "billed_hours": f"{b.billed_hours}" if b.billed_hours else None,
            "inspection_fee": f"{b.inspection_fee:.2f}" if b.inspection_fee else None, "excludes": b.job.excludes,
            "discount": f"{b.discount:.2f}", "offer_title": b.offer_title, "tax": f"{b.tax:.2f}", "payment_method": b.payment_method,
            "eta_minutes": b.eta_minutes, "accepted_at": b.accepted_at.isoformat() if b.accepted_at else None,
            "timeline": [{"to": e.to_status, "label": BookingStatus(e.to_status).label, "note": e.note, "at": e.created_at.isoformat()} for e in b.events.all()],
            "quotes": [{"id": str(x.id), "amount": f"{x.amount:.2f}", "note": x.note, "status": x.status, "created_at": x.created_at.isoformat()} for x in q],
            "photos": [{"id": str(a.id), **media.urls(a, request)} for a in b.attachments.all()],
            "payment": next(({"method": p.method, "status": p.status, "amount": f"{p.amount:.2f}"} for p in b.payments.all()), None),
            "cancellation": lifecycle.cancellation(b), "can_pay": b.status == BookingStatus.COMPLETED,
            "awaiting_cash": b.status == BookingStatus.COMPLETED and b.payment_method == "cash",
            "can_review": b.status in (BookingStatus.PAID, BookingStatus.COMPLETED) and not hasattr(b, "review") and b.provider_id is not None,
            "review": ({"overall": b.review.overall, "quality": b.review.quality, "behaviour": b.review.behaviour, "timeliness": b.review.timeliness,
                        "comment": b.review.comment} if hasattr(b, "review") else None),
            "tickets": [{"id": str(t.id), "reference": t.reference, "status": t.status} for t in b.support_tickets.all()],
            "tracking": "status_only"}


class BookingListCreateView(APIView):
    """GET /customer/services/bookings?when=upcoming|active|completed|cancelled ; POST books."""

    permission_classes = [IsCustomer]
    throttle_scope = "order_placement"

    def get(self, request):
        lifecycle.expire_due()
        qs = _owned(request)
        when = request.query_params.get("when")
        if when == "active":
            qs = qs.filter(status__in=[BookingStatus.REQUESTED, BookingStatus.ON_THE_WAY, BookingStatus.ARRIVED, BookingStatus.QUOTE_PENDING,
                                       BookingStatus.IN_PROGRESS, BookingStatus.COMPLETED])
        elif when == "upcoming":
            qs = qs.filter(status=BookingStatus.CONFIRMED)
        elif when == "completed":
            qs = qs.filter(status=BookingStatus.PAID)
        elif when == "cancelled":
            qs = qs.filter(status__in=[BookingStatus.CANCELLED, BookingStatus.UNASSIGNED])
        return Response({"results": [booking_out(b, request) for b in qs[:50]]})

    def post(self, request):
        s = BookInput(data=request.data)
        s.is_valid(raise_exception=True)
        b, created = lifecycle.book(request.user.customer_profile, s.validated_data)
        return Response(booking_out(_owned(request).get(pk=b.pk), request, True), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class BookingDetailView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request, pk):
        lifecycle.expire_due()
        return Response(booking_out(get_object_or_404(_owned(request), pk=pk), request, True))


class BookingActionView(APIView):
    """POST /customer/services/bookings/<id>/<cancel|quote|pay|review>"""

    permission_classes = [IsCustomer]

    def post(self, request, pk, action):
        b = get_object_or_404(_owned(request), pk=pk)
        data = request.data if isinstance(request.data, dict) else {}
        if action == "cancel":
            reason = str(data.get("reason") or "").strip()[:200]
            if len(reason) < 2:
                raise DomainError("Tell us why you're cancelling.", code="validation_error")
            lifecycle.cancel(b, reason)
        elif action == "quote":
            lifecycle.decide_quote(b, bool(data.get("approve")))
        elif action == "pay":
            lifecycle.settle(b, str(data.get("method") or ""))
        elif action == "review":
            s = ReviewInput(data=data)
            s.is_valid(raise_exception=True)
            lifecycle.review(request.user.customer_profile, b, s.validated_data)
        else:
            raise DomainError("Unknown action.", code="unknown_action", status_code=404)
        return Response(booking_out(_owned(request).get(pk=pk), request, True))


class ReviewInput(serializers.Serializer):
    overall = serializers.IntegerField(min_value=1, max_value=5)
    quality = serializers.IntegerField(min_value=1, max_value=5)
    behaviour = serializers.IntegerField(min_value=1, max_value=5)
    timeliness = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class RebookView(APIView):
    """GET /customer/services/bookings/<id>/rebook — same service, professional and address; availability is checked again."""

    permission_classes = [IsCustomer]

    def get(self, request, pk):
        b = get_object_or_404(_owned(request), pk=pk)
        return Response({"category": b.category.slug, "job_id": str(b.job_id), "provider_id": str(b.provider_id) if b.provider_id else None,
                         "address_id": str(b.address_ref_id) if b.address_ref_id else None, "hours": b.hours, "description": b.description,
                         "rebook_of": str(b.id)})


class NeedInput(serializers.Serializer):
    text = serializers.CharField(max_length=600, min_length=5)
    address_id = serializers.UUIDField(required=False, allow_null=True)
    preferred_time = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    attachment_ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list, max_length=5)


class NeedsView(APIView):
    """POST /customer/services/needs — 'Can't find your service?' (reviewed by Click); GET lists the customer's own."""

    permission_classes = [IsCustomer]

    def get(self, request):
        rows = ServiceNeed.objects.filter(customer=request.user.customer_profile)[:20]
        return Response({"results": [{"id": str(n.id), "text": n.text, "status": n.status, "status_label": n.get_status_display(),
                                      "created_at": n.created_at.isoformat()} for n in rows]})

    def post(self, request):
        s = NeedInput(data=request.data)
        s.is_valid(raise_exception=True)
        c = request.user.customer_profile
        a = c.addresses.filter(pk=s.validated_data.get("address_id")).first() if s.validated_data.get("address_id") else None
        n = ServiceNeed.objects.create(customer=c, text=s.validated_data["text"].strip(), address=a.snapshot() if a else {},
                                       preferred_time=s.validated_data["preferred_time"])
        ServiceAttachment.objects.filter(customer=c, pk__in=s.validated_data["attachment_ids"], booking__isnull=True, need__isnull=True).update(need=n)
        from apps.notifications.models import NotificationCategory
        from apps.notifications.services import notify

        notify(c, NotificationCategory.SUPPORT, "We received your service request", "Click will review it and contact you.", "/services")
        return Response({"id": str(n.id), "status": n.status}, status=status.HTTP_201_CREATED)


class FavoritesView(APIView):
    """GET /customer/services/favorites — My Professionals (saved via the shared wishlist)."""

    permission_classes = [IsCustomer]

    def get(self, request):
        from apps.wishlists.models import WishlistItem

        rows = WishlistItem.objects.filter(customer=request.user.customer_profile, provider__isnull=False).values_list("id", "provider_id")
        ids = {pid: wid for wid, pid in rows}
        point = _point(request)
        out = []
        for p in engine.listed().filter(pk__in=list(ids)):
            last = ServiceBooking.objects.filter(customer=request.user.customer_profile, provider=p, status=BookingStatus.PAID).first()
            out.append({**engine.card(p, point, request=request), "favorite_id": str(ids[p.id]),
                        "last_booking": {"id": str(last.id), "job": last.job.name} if last else None})
        return Response({"results": out})


# --- partner: the professional's own profile ---------------------------------------------------------------------

def _own_pro(request) -> ProviderProfile:
    from apps.partners.views import _onboarded_partner

    partner = _onboarded_partner(request)
    pro = ProviderProfile.objects.filter(partner=partner).first()
    if pro is None:
        raise DomainError("Your Services profile isn't set up yet.", code="not_a_professional", status_code=404)
    return pro


class ProProfileInput(serializers.Serializer):
    about = serializers.CharField(max_length=600, required=False, allow_blank=True)
    experience_years = serializers.IntegerField(min_value=0, max_value=60, required=False, allow_null=True)
    skills = serializers.ListField(child=serializers.CharField(max_length=40), max_length=20, required=False)
    languages = serializers.ListField(child=serializers.CharField(max_length=30), max_length=10, required=False)
    instant_enabled = serializers.BooleanField(required=False)
    quote_jobs = serializers.BooleanField(required=False)


class ProProfileView(APIView):
    """GET/PATCH /partner/services/profile ; POST (multipart `photo`) sets the profile photo."""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        p = _own_pro(request)
        return Response({**engine.card(p, None, request=request), "about": p.about, "skills": p.skills, "instant_enabled": p.instant_enabled,
                         "quote_jobs": p.quote_jobs, "hours": [{"weekday": h.weekday, "starts": h.starts_at.isoformat(), "ends": h.ends_at.isoformat()} for h in p.hours.all()],
                         "prices": [{"job_id": str(x.job_id), "price": f"{x.price:.2f}"} for x in p.prices.all()],
                         "portfolio": [{"id": str(x.id), "caption": x.caption, **media.urls(x, request)} for x in p.portfolio.all()]})

    def patch(self, request):
        p = _own_pro(request)
        s = ProProfileInput(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        for k, v in s.validated_data.items():
            setattr(p, k, v)
        p.save()
        return self.get(request)

    def post(self, request):
        p = _own_pro(request)
        upload = request.FILES.get("photo")
        if upload is None:
            raise DomainError("Choose a photo.", code="file_required")
        if p.photo:
            p.photo.delete(save=False)
        p.photo.save("photo.webp", media.profile_photo(upload), save=True)
        return self.get(request)


class ProPortfolioView(APIView):
    """POST /partner/services/portfolio (multipart `file`, `caption`) ; DELETE /partner/services/portfolio/<id>"""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        p = _own_pro(request)
        upload = request.FILES.get("file")
        if upload is None:
            raise DomainError("Choose a photo.", code="file_required")
        if p.portfolio.count() >= 24:
            raise DomainError("You can show up to 24 work photos.", code="limit_reached")
        x = ProviderPortfolio(provider=p, caption=str(request.data.get("caption", ""))[:160], category=p.category)
        media.store(x, upload, f"portfolio/{p.id.hex[:8]}")
        x.save()
        return Response({"id": str(x.id), "caption": x.caption, **media.urls(x, request)}, status=status.HTTP_201_CREATED)

    def delete(self, request, pk):
        x = get_object_or_404(ProviderPortfolio, pk=pk, provider=_own_pro(request))
        media.delete(x)
        x.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProHoursView(APIView):
    """PUT /partner/services/hours [{weekday, starts, ends}] ; PUT /partner/services/prices [{jobId, price}]"""

    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, what):
        from datetime import time

        p = _own_pro(request)
        rows = request.data if isinstance(request.data, list) else []
        if what == "hours":
            new = []
            for r in rows[:21]:
                try:
                    wd, a, b = int(r["weekday"]), time.fromisoformat(r["starts"]), time.fromisoformat(r["ends"])
                except (KeyError, ValueError, TypeError):
                    raise DomainError("Each entry needs weekday, starts and ends.", code="validation_error")
                if not (0 <= wd <= 6 and b > a):
                    raise DomainError("Check the days and times.", code="validation_error")
                new.append(ProviderAvailability(provider=p, weekday=wd, starts_at=a, ends_at=b))
            p.hours.all().delete()
            ProviderAvailability.objects.bulk_create(new)
        elif what == "prices":
            jobs = {str(j.id): j for j in ServiceJob.objects.filter(category__in=[s.category for s in p.services.all()])}
            for r in rows[:100]:
                j = jobs.get(str(r.get("job_id")))
                if j is None or j.pricing == ServiceJob.Pricing.QUOTE:
                    raise DomainError("You can price only your own services' fixed, starting or hourly jobs.", code="validation_error")
                ProviderJobPrice.objects.update_or_create(provider=p, job=j, defaults={"price": r["price"]})
        else:
            raise DomainError("Unknown setting.", code="not_found", status_code=404)
        return Response({"ok": True})
