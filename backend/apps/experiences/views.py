"""Click. Bookings API. Discovery (places, temples, attractions, experiences, availability) is public; reviews,
bookings, cancellation and the central list of every reservation belong to the signed-in customer."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import DomainError
from apps.core.api.permissions import IsCustomer
from apps.rides.pricing import haversine_km

from . import booking, hub
from .models import ACTIVE, KINDS, Attraction, ExperienceBooking, Group, Offering, Price

PAGE = 12
GROUP_LINKS = [  # other Click. services that are also booked — linked, never duplicated
    {"code": "shows", "title": "Shows", "subtitle": "Movies and live shows", "link": "/showtime", "theme": "movies"},
    {"code": "events", "title": "Events", "subtitle": "Plan events, find teams", "link": "/events", "theme": "events"},
    {"code": "hotels", "title": "Hotels", "subtitle": "Stays for your trip", "link": "/hotels", "theme": "hotels"},
    {"code": "travel", "title": "Travel", "subtitle": "Bus, train and flight", "link": "/travel", "theme": "travel"},
]


def _customer(request):
    u = request.user
    return u.customer_profile if u and u.is_authenticated and hasattr(u, "customer_profile") else None


def _saved(request) -> dict:
    c = _customer(request)
    if c is None:
        return {}
    return {str(a): str(i) for i, a in c.wishlist_items.filter(attraction__isnull=False).values_list("id", "attraction_id")}


def listed():
    return (Attraction.objects.filter(is_listed=True).prefetch_related("offerings__prices", "images", "closures")
            .annotate(recent=Count("bookings", filter=Q(bookings__status__in=["confirmed", "completed"],
                                                        bookings__created_at__gte=timezone.now() - timedelta(days=90)))))


def _from_price(a: Attraction):
    vals = [p.amount for o in a.offerings.all() if o.is_active for p in o.prices.all() if p.visitor not in ("family", "infant", "child")]
    return min(vals) if vals else None


def next_available(a: Attraction, days: int = 10):
    if not a.bookable:
        return None
    for i in range(days):
        d = booking.today() + timedelta(days=i)
        for o in a.offerings.all():
            if o.is_active and any(s["status"] == "available" for s in booking.slots(o, d)):
                return d
    return None


def card(a: Attraction, request=None, near=None, saved=None, with_next=True) -> dict:
    low = _from_price(a) if a.bookable else None
    km = None
    if near and a.latitude is not None:
        km = round(haversine_km(near, (float(a.latitude), float(a.longitude))), 1)
    nxt = next_available(a) if with_next else None
    img = next(iter(a.images.all()), None)
    return {"id": str(a.id), "slug": a.slug, "name": a.name, "kind": a.kind, "kind_label": a.get_kind_display(), "group": a.group,
            "group_label": a.get_group_display(), "city": a.city, "region": a.region, "area": a.area, "tagline": a.tagline, "deity": a.deity,
            "accent": a.accent, "image_url": img.url if img else None,
            "rating": {"average": f"{a.rating_average:.1f}", "count": a.rating_count} if a.rating_count >= 3 else None,
            "bookable": a.bookable, "verified": a.verified_provider, "instant": a.instant_confirmation and a.bookable,
            "free_cancellation": a.bookable and a.refundable and a.free_cancel_hours > 0,
            "from_price": f"{low:.2f}" if low is not None else None,
            "booking_types": sorted({o.get_kind_display() for o in a.offerings.all() if o.is_active}) if a.bookable else [],
            "next_available": nxt.isoformat() if nxt else None, "official_source": a.official_source if not a.bookable else "",
            "duration_minutes": a.duration_minutes, "family_friendly": a.family_friendly, "kids_friendly": a.kids_friendly, "setting": a.setting,
            "distance_km": km, "favorite_id": (saved if saved is not None else _saved(request) if request else {}).get(str(a.id)),
            "recent_bookings": getattr(a, "recent", 0)}


def _near(request):
    try:
        lat, lng = float(request.query_params["lat"]), float(request.query_params["lng"])
        return (lat, lng) if -90 <= lat <= 90 and -180 <= lng <= 180 else None
    except (KeyError, ValueError):
        return None


class HomeView(APIView):
    """GET /experiences/home?city=&lat=&lng= — categories, destinations and data-rule discovery sections."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        rows = list(listed())
        near = _near(request)
        saved = _saved(request)
        city = (request.query_params.get("city") or "").strip().lower()
        cards = {a.id: card(a, near=near, saved=saved, with_next=False) for a in rows}

        def pick(rule, key=None, n=10):
            out = [cards[a.id] for a in rows if rule(a)]
            return sorted(out, key=key)[:n] if key else out[:n]

        by_bookable = lambda c: (not c["bookable"], c["name"])  # noqa: E731
        cities = {}
        for a in rows:
            cities.setdefault(a.city, {"name": a.city, "region": a.region, "count": 0, "bookable": 0})
            cities[a.city]["count"] += 1
            cities[a.city]["bookable"] += int(a.bookable)
        sections = []
        if city:
            sections.append({"code": "near", "title": f"Featured in {city.title()}", "subtitle": "Places and experiences in your city",
                             "items": pick(lambda a: a.city.lower() == city, by_bookable)})
        if near:
            close = sorted([c for c in cards.values() if c["distance_km"] is not None and c["distance_km"] <= 60], key=lambda c: c["distance_km"])
            sections.append({"code": "nearby", "title": "Near you", "subtitle": "Within 60 km, by straight-line distance", "items": close[:10]})
        sections += [
            {"code": "temples", "title": "Explore temples & spiritual places", "subtitle": "Darshan, seva and visitor information",
             "items": pick(lambda a: a.group == Group.SPIRITUAL, by_bookable)},
            {"code": "tourist", "title": "Explore tourist spots", "subtitle": "Monuments, museums, forts and palaces",
             "items": pick(lambda a: a.group == Group.TOURIST, by_bookable)},
            {"code": "parks", "title": "Parks & family fun", "subtitle": "Water parks, zoos, gardens and adventure parks",
             "items": pick(lambda a: a.group == Group.PARKS, by_bookable)},
            {"code": "experiences", "title": "Experiences", "subtitle": "Tours, boat rides, workshops and activities",
             "items": pick(lambda a: a.group == Group.EXPERIENCES, by_bookable)},
            {"code": "family", "title": "Family fun", "subtitle": "Marked kid-friendly by the provider",
             "items": pick(lambda a: a.kids_friendly and a.bookable, by_bookable)},
            {"code": "popular", "title": "Most booked on Click.", "subtitle": "Confirmed bookings in the last 90 days",
             "items": sorted([c for c in cards.values() if c["recent_bookings"] >= 3], key=lambda c: -c["recent_bookings"])[:10]},
            {"code": "top_rated", "title": "Top rated", "subtitle": "4.0+ from 3 or more verified visits",
             "items": sorted([c for c in cards.values() if c["rating"] and float(c["rating"]["average"]) >= 4.0], key=lambda c: -float(c["rating"]["average"]))[:10]},
        ]
        return Response({
            "groups": [{"code": g.value, "label": g.label, "kinds": [{"code": k, "label": lbl, "count": sum(1 for a in rows if a.kind == k)} for k, lbl in KINDS[g]],
                        "count": sum(1 for a in rows if a.group == g.value)} for g in Group],
            "services": GROUP_LINKS, "cities": sorted(cities.values(), key=lambda c: (-c["count"], c["name"])),
            "sections": [s for s in sections if s["items"]],
            "counts": {"total": len(rows), "bookable": sum(1 for a in rows if a.bookable)},
        })


def _elsewhere(q: str) -> list[dict]:
    """Matches in other Click. services for the same words (links into their own pages)."""
    out = []
    from apps.bookings.models import Event
    from apps.hotels.models import Destination
    from apps.travel.models import Place

    for d in Destination.objects.filter(Q(name__icontains=q) | Q(synonyms__icontains=q), is_active=True, parent__isnull=True)[:2]:
        out.append({"kind": "hotels", "title": f"Hotels in {d.name}", "link": f"/hotels/search?destination={d.slug}"})
    for p in Place.objects.filter(Q(name__icontains=q) | Q(aliases__icontains=q), kind="city", is_active=True)[:2]:
        out.append({"kind": "travel", "title": f"Travel to {p.name}", "link": f"/travel?to={p.slug}"})
    for e in Event.objects.filter(title__icontains=q, status__in=["now_showing", "coming_soon"])[:2]:
        out.append({"kind": "shows", "title": e.title, "link": f"/showtime/{e.slug}"})
    return out


SORTS = {"recommended", "popular", "rating", "price_asc", "price_desc", "nearest", "soonest"}


class SearchView(APIView):
    """GET /experiences/search?q&group&kind&city&date&<filters>&sort&page"""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        qp = request.query_params
        q = (qp.get("q") or "").strip()[:80]
        qs = listed()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(city__icontains=q) | Q(area__icontains=q) | Q(region__icontains=q) | Q(tagline__icontains=q)
                           | Q(deity__icontains=q) | Q(kind__icontains=q.replace(" ", "_")) | Q(offerings__name__icontains=q)).distinct()
        if qp.get("group") in Group.values:
            qs = qs.filter(group=qp["group"])
        kinds = [k for k in (qp.get("kind") or "").split(",") if k]
        if kinds:
            qs = qs.filter(kind__in=kinds)
        if qp.get("city"):
            qs = qs.filter(city__iexact=qp["city"])
        for flag, field in (("family", "family_friendly"), ("kids", "kids_friendly"), ("bookable", "bookable"), ("verified", "verified_provider")):
            if qp.get(flag) in ("1", "true"):
                qs = qs.filter(**{field: True})
        if qp.get("instant") in ("1", "true"):
            qs = qs.filter(bookable=True, instant_confirmation=True)
        if qp.get("free_cancellation") in ("1", "true"):
            qs = qs.filter(bookable=True, refundable=True, free_cancel_hours__gt=0)
        if qp.get("setting") in ("indoor", "outdoor"):
            qs = qs.filter(setting__in=[qp["setting"], "both"])
        if qp.get("min_rating"):
            try:
                qs = qs.filter(rating_count__gte=3, rating_average__gte=Decimal(qp["min_rating"]))
            except Exception:
                raise DomainError("Choose a valid rating.", code="validation_error")
        rows = list(qs)
        visit = None
        if qp.get("date"):
            try:
                visit = date.fromisoformat(qp["date"])
            except ValueError:
                raise DomainError("Choose a valid date.", code="validation_error")
            if visit < booking.today():
                raise DomainError("Choose today or a later date.", code="validation_error")
            rows = [a for a in rows if a.bookable and any(o.is_active and any(s["status"] == "available" for s in booking.slots(o, visit)) for o in a.offerings.all())]
        near = _near(request)
        saved = _saved(request)
        cards = [card(a, near=near, saved=saved, with_next=False) for a in rows]
        lo, hi = qp.get("min_price"), qp.get("max_price")
        if lo or hi:
            try:
                cards = [c for c in cards if c["from_price"] is not None and (not lo or Decimal(c["from_price"]) >= Decimal(lo)) and (not hi or Decimal(c["from_price"]) <= Decimal(hi))]
            except Exception:
                raise DomainError("Choose a valid price.", code="validation_error")
        if near and qp.get("max_km"):
            cards = [c for c in cards if c["distance_km"] is not None and c["distance_km"] <= float(qp["max_km"])]
        how = qp.get("sort") if qp.get("sort") in SORTS else "recommended"
        inf = Decimal("1e9")
        key = {
            "popular": lambda c: (-c["recent_bookings"], c["name"]),
            "rating": lambda c: (-(float(c["rating"]["average"]) if c["rating"] else 0), c["name"]),
            "price_asc": lambda c: (Decimal(c["from_price"]) if c["from_price"] else inf, c["name"]),
            "price_desc": lambda c: (-(Decimal(c["from_price"]) if c["from_price"] else Decimal(-1)), c["name"]),
            "nearest": lambda c: (c["distance_km"] if c["distance_km"] is not None else 1e9, c["name"]),
            "recommended": lambda c: (not c["bookable"], -(float(c["rating"]["average"]) if c["rating"] else 3.5), -c["recent_bookings"], c["name"]),
        }.get(how)
        page = max(1, int(qp.get("page") or 1)) if str(qp.get("page") or "1").isdigit() else 1
        if how == "soonest":
            by_id = {str(a.id): a for a in rows}
            for c in cards:
                n = next_available(by_id[c["id"]]) if c["bookable"] else None
                c["next_available"] = n.isoformat() if n else None
            cards.sort(key=lambda c: (c["next_available"] or "9999", c["name"]))
        else:
            cards.sort(key=key)
            by_id = {str(a.id): a for a in rows}
            for c in cards[(page - 1) * PAGE: page * PAGE]:
                n = next_available(by_id[c["id"]]) if c["bookable"] else None
                c["next_available"] = n.isoformat() if n else None
        return Response({"count": len(cards), "results": cards[(page - 1) * PAGE: page * PAGE], "has_more": page * PAGE < len(cards),
                         "elsewhere": _elsewhere(q) if q and page == 1 else [],
                         "filters": {"sorts": sorted(SORTS - ({"nearest"} if not near else set())), "near": bool(near)}})


def offering_out(o: Offering, d: date | None = None) -> dict:
    return {"id": str(o.id), "kind": o.kind, "kind_label": o.get_kind_display(), "booking_model": o.booking_model, "name": o.name,
            "description": o.description, "includes": o.includes, "duration_minutes": o.duration_minutes, "days": o.days, "slot_times": o.slot_times,
            "max_per_booking": o.max_per_booking, "min_age": o.min_age, "pickup_points": o.pickup_points, "requirements": o.requirements,
            "tax_percent": f"{o.tax_percent:.1f}", "book_ahead_days": o.book_ahead_days,
            "prices": [{"visitor": p.visitor, "label": p.label or p.get_visitor_display(), "note": p.note, "amount": f"{p.amount:.2f}", "units": p.units}
                       for p in o.prices.all()],
            "calendar": booking.calendar(o, 14)}


class AttractionView(APIView):
    """GET /experiences/attractions/<slug> — full details; offerings with prices and a 14-day availability calendar."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        a = get_object_or_404(listed(), slug=slug)
        reviews = a.reviews.filter(is_published=True).select_related("customer__user", "booking__offering")[:6]
        until = a.free_cancel_hours
        return Response({
            **card(a, request, near=_near(request)), "description": a.description, "highlights": a.highlights, "facilities": a.facilities,
            "accessibility": a.accessibility, "rules": a.rules, "dress_code": a.dress_code, "prohibited": a.prohibited, "age_note": a.age_note,
            "opening": a.opening or None, "address": a.address, "latitude": float(a.latitude) if a.latitude is not None else None,
            "longitude": float(a.longitude) if a.longitude is not None else None, "faqs": a.faqs, "official_url": a.official_url or None,
            "official_source": a.official_source, "provider": a.provider.business_name if a.provider_id and a.bookable else None,
            "images": [{"url": i.url, "caption": i.caption, "credit": i.credit} for i in a.images.all()],
            "policy": ("Non-refundable." if not a.refundable else
                       f"Free cancellation until {until} hours before your visit; " + ("no refund after that." if a.cancel_fee_percent >= 100 else f"{a.cancel_fee_percent}% fee after that.")),
            "offerings": [offering_out(o) for o in a.offerings.all() if o.is_active] if a.bookable else [],
            "reviews": [{"rating": r.rating, "comment": r.comment, "author": (r.customer.user.full_name or "Visitor").split()[0], "visited": r.booking.visit_date.strftime("%b %Y"),
                         "offering": r.booking.offering.name, "verified": True} for r in reviews],
            "related": [card(x, saved={}, with_next=False) for x in listed().filter(city=a.city).exclude(pk=a.pk)[:6]],
        })


class AvailabilityView(APIView):
    """GET /experiences/offerings/<id>/availability?date= — slots with places left, sold out or expired."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, pk):
        o = get_object_or_404(Offering.objects.select_related("attraction"), pk=pk, is_active=True, attraction__is_listed=True, attraction__bookable=True)
        try:
            d = date.fromisoformat(request.query_params.get("date") or "")
        except ValueError:
            raise DomainError("Choose a date.", code="validation_error")
        state = booking.day_state(o, d)
        reason = {"open": "", "past": "That date has passed.", "too_far": f"Bookings open {o.book_ahead_days} days ahead.",
                  "closed": next((c.reason for c in o.attraction.closures.filter(date=d)), "") or f"{o.attraction.name} is closed that day.",
                  "not_running": f"{o.name} doesn’t run on {d:%A}s."}[state]
        return Response({"date": d.isoformat(), "state": state, "reason": reason, "slots": booking.slots(o, d)})


# --- customer --------------------------------------------------------------------------------------------------------

class ReviewInput(serializers.Serializer):
    offering_id = serializers.UUIDField()
    visit_date = serializers.DateField()
    slot_time = serializers.RegexField(r"^\d{2}:\d{2}$", required=False, allow_blank=True, allow_null=True)
    tickets = serializers.DictField(child=serializers.IntegerField(min_value=0, max_value=50))
    pickup_point = serializers.CharField(max_length=120, required=False, allow_blank=True)
    coupon = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")

    def validate_tickets(self, v):
        bad = [k for k in v if k not in Price.Visitor.values]
        if bad:
            raise serializers.ValidationError(f"Unknown ticket type: {bad[0]}.")
        return v


class BookInput(ReviewInput):
    lead_name = serializers.CharField(max_length=120, min_length=2)
    lead_phone = serializers.RegexField(r"^\+?[0-9 ]{8,16}$", max_length=20)
    lead_email = serializers.EmailField(required=False, allow_blank=True)
    visitor_names = serializers.ListField(child=serializers.CharField(max_length=80, allow_blank=True), required=False, default=list, max_length=20)
    expected_total = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    idempotency_key = serializers.CharField(max_length=64)


class PrepareView(APIView):
    """POST /customer/experiences/review — the Booking Summary numbers, re-checked now."""

    permission_classes = [IsCustomer]

    def post(self, request):
        s = ReviewInput(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(booking.prepare(s.validated_data))


def _own(request):
    return (ExperienceBooking.objects.filter(customer=request.user.customer_profile)
            .select_related("attraction__provider", "offering").prefetch_related("events", "payments", "support_tickets"))


def booking_out(b: ExperienceBooking, full: bool = False) -> dict:
    a = b.attraction
    out = {"id": str(b.id), "number": b.number, "kind": "experience", "status": b.status, "status_label": b.get_status_display(),
           "payment_status": b.payment_status, "payment_status_label": b.get_payment_status_display(), "title": b.title,
           "attraction": {"slug": a.slug, "name": a.name, "kind": a.kind, "kind_label": a.get_kind_display(), "group": a.group, "city": a.city, "accent": a.accent},
           "offering": {"name": b.offering.name, "kind": b.offering.kind, "kind_label": b.offering.get_kind_display()},
           "visit_date": b.visit_date.isoformat(), "slot_time": b.slot_time.strftime("%H:%M") if b.slot_time else None, "visitors": b.visitors,
           "total": f"{b.total:.2f}", "created_at": b.created_at.isoformat(), "is_active": b.status in ACTIVE}
    if not full:
        return out
    pay = b.payments.order_by("-created_at").first()
    return {**out, "lines": b.lines, "lead": {"name": b.lead_name, "phone": b.lead_phone, "email": b.lead_email}, "visitor_names": b.visitor_names,
            "pickup_point": b.pickup_point, "subtotal": f"{b.subtotal:.2f}", "discount": f"{b.discount:.2f}", "offer_title": b.offer_title,
            "tax": f"{b.tax:.2f}", "refunded": f"{b.refunded:.2f}", "entry_code": b.entry_code if b.status in ("confirmed", "completed") else None,
            "checked_in_at": b.checked_in_at.isoformat() if b.checked_in_at else None,
            "policy": booking.policy_text(b.refundable, b.free_cancel_until if b.free_cancel_until and b.free_cancel_until > timezone.now() else None, b.cancel_fee_percent),
            "address": a.address, "latitude": float(a.latitude) if a.latitude is not None else None, "longitude": float(a.longitude) if a.longitude is not None else None,
            "provider": a.provider.business_name if a.provider_id else None, "requirements": b.offering.requirements, "dress_code": a.dress_code,
            "rules": a.rules, "prohibited": a.prohibited,
            "hold_expires_at": b.hold_expires_at.isoformat() if b.hold_expires_at and b.status == "pending_payment" else None,
            "timeline": [{"to": e.to, "label": e.get_to_display(), "note": e.note, "at": e.created_at.isoformat()} for e in b.events.all()],
            "payment": {"method": pay.method, "status": pay.status, "status_label": pay.get_status_display(), "amount": f"{pay.amount:.2f}",
                        "reference": str(pay.id)[:8].upper()} if pay else None,
            "refund": {"amount": f"{b.refunded:.2f}", "status": "completed", "label": "Refund completed · credited to Click. Wallet"} if b.refunded > 0 else None,
            "cancellation": booking.cancellation(b), "can_pay": b.status == "pending_payment" and b.payment_status == "pending",
            "can_review": b.status == "completed" and not hasattr(b, "review"),
            "review": {"rating": b.review.rating, "comment": b.review.comment} if hasattr(b, "review") else None,
            "cancel_reason": b.cancel_reason, "tickets": [{"id": str(t.id), "reference": t.reference, "status": t.status} for t in b.support_tickets.all()],
            "entry_note": "Show this entry code at the entrance; the provider verifies it in the Click. Partner App."}


class BookingsView(APIView):
    """GET /customer/experiences/bookings ; POST books (Pay & book)."""

    permission_classes = [IsCustomer]

    def get(self, request):
        booking.sweep()
        return Response({"results": [booking_out(b) for b in _own(request)[:50]]})

    def post(self, request):
        s = BookInput(data=request.data)
        s.is_valid(raise_exception=True)
        b, created, error = booking.book(request.user.customer_profile, s.validated_data)
        out = booking_out(_own(request).get(pk=b.pk), True)
        out["payment_error"] = error
        return Response(out, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class BookingDetailView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request, pk):
        booking.sweep()
        return Response(booking_out(get_object_or_404(_own(request), pk=pk), True))


class VisitReviewInput(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class BookingActionView(APIView):
    """POST /customer/experiences/bookings/<id>/<pay|cancel|review>"""

    permission_classes = [IsCustomer]

    def post(self, request, pk, action):
        b = get_object_or_404(_own(request), pk=pk)
        if action == "pay":
            booking.pay(b)
        elif action == "cancel":
            reason = str(request.data.get("reason") or "").strip()
            if len(reason) < 2:
                raise DomainError("Tell us why you’re cancelling.", code="validation_error")
            booking.cancel(b, reason)
        elif action == "review":
            s = VisitReviewInput(data=request.data)
            s.is_valid(raise_exception=True)
            booking.review(request.user.customer_profile, b, s.validated_data["rating"], s.validated_data["comment"])
        else:
            raise DomainError("Unknown action.", code="unknown_action", status_code=404)
        return Response(booking_out(_own(request).get(pk=pk), True))


class SavedView(APIView):
    """GET /customer/experiences/saved — saved places (shared Wishlist rows)."""

    permission_classes = [IsCustomer]

    def get(self, request):
        rows = request.user.customer_profile.wishlist_items.filter(attraction__isnull=False, attraction__is_listed=True).values_list("id", "attraction_id")
        by = {a: str(i) for i, a in rows}
        return Response({"results": [card(a, saved={str(k): v for k, v in by.items()}, with_next=False) for a in listed().filter(pk__in=by)]})


class HubView(APIView):
    """GET /customer/reservations?group=upcoming|completed|cancelled|all&kind= — every booking across Click., one list."""

    permission_classes = [IsCustomer]

    def get(self, request):
        group = request.query_params.get("group") or "upcoming"
        if group not in ("upcoming", "completed", "cancelled", "all"):
            group = "upcoming"
        return Response(hub.my_bookings(request.user.customer_profile, group, request.query_params.get("kind") or ""))


# --- partner (provider verification) ---------------------------------------------------------------------------------

class PartnerCheckInView(APIView):
    """POST /partner/experiences/check-in {code} — the provider verifies an entry code at the gate."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from apps.partners.views import _onboarded_partner

        partner = _onboarded_partner(request)
        code = str(request.data.get("code") or "")
        if len(code.strip()) < 6:
            raise DomainError("Enter the 8-character entry code.", code="validation_error")
        b = booking.check_in(partner, code)
        return Response({"number": b.number, "title": b.title, "visit_date": b.visit_date.isoformat(),
                         "slot_time": b.slot_time.strftime("%H:%M") if b.slot_time else None, "visitors": b.visitors, "lines": b.lines,
                         "lead_name": b.lead_name, "checked_in_at": b.checked_in_at.isoformat()})
