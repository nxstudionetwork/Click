"""Click. Hotels API. Discovery is public; reviews of a stay, bookings, payments, cancellation and saved hotels belong
to the signed-in customer (queries scoped to them); properties manage inventory through the partner endpoints."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Min, Q
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import DomainError
from apps.core.api.permissions import IsCustomer
from apps.professionals import media

from . import booking, engine
from .models import ACTIVE, Destination, HotelBooking, HotelOffer, HotelProperty, HotelReview, Landmark, RatePlan, RoomInventory, RoomType
from .search import filters_meta, image_url, inventory, properties

COLLECTIONS = [
    ("weekend", "Weekend stays", "Short drives, easy breaks"), ("city", "City stays", "Close to everything"),
    ("beach", "Beach escapes", "Sand, sea and slow mornings"), ("nature", "Nature retreats", "Hills, forests and fresh air"),
    ("family", "Family getaways", "Family rooms and kid-friendly stays"), ("business", "Business stays", "Wi-Fi, workspaces, quick check-in"),
    ("luxury", "Luxury stays", "Five-star and premium stays"), ("budget", "Budget stays", "Clean, simple, under ₹2,500 a night"),
]


def _customer(request):
    u = request.user
    return u.customer_profile if u and u.is_authenticated and hasattr(u, "customer_profile") else None


def _saved(request) -> dict:
    c = _customer(request)
    if c is None:
        return {}
    return {str(h): str(i) for i, h in c.wishlist_items.filter(hotel__isnull=False).values_list("id", "hotel_id")}


def _lowest(p: HotelProperty):
    rates = [r.price for room in p.rooms.all() for r in room.rates.all()]
    return min(rates) if rates else None


def _collection_members(code: str, props: list[HotelProperty]) -> list[HotelProperty]:
    if code in ("family", "business"):
        return [p for p in props if code in p.good_for]
    if code == "luxury":
        return [p for p in props if (p.star_rating or 0) >= 5]
    if code == "budget":
        return [p for p in props if (_lowest(p) or Decimal("1e9")) <= 2500]
    return [p for p in props if code in p.destination.tags or (p.destination.parent and code in p.destination.parent.tags)]


class StayParams(serializers.Serializer):
    check_in = serializers.DateField()
    check_out = serializers.DateField()
    rooms = serializers.IntegerField(min_value=1, max_value=engine.MAX_ROOMS, default=1)
    adults = serializers.IntegerField(min_value=1, max_value=48, default=2)
    children = serializers.IntegerField(min_value=0, max_value=24, default=0)

    def validate(self, attrs):
        problem = engine.validate_stay(attrs["check_in"], attrs["check_out"], attrs["rooms"], attrs["adults"], attrs["children"])
        if problem:
            raise serializers.ValidationError(problem)
        return attrs


class SearchParams(StayParams):
    destination = serializers.CharField(max_length=80)
    type = serializers.ListField(child=serializers.ChoiceField(choices=HotelProperty.Type.values), required=False)
    stars = serializers.ListField(child=serializers.IntegerField(min_value=1, max_value=5), required=False)
    amenities = serializers.ListField(child=serializers.SlugField(), required=False)
    room_class = serializers.ListField(child=serializers.ChoiceField(choices=RoomType.RoomClass.values), required=False)
    min_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, min_value=0)
    max_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, min_value=0)
    min_rating = serializers.DecimalField(max_digits=3, decimal_places=1, required=False, min_value=0, max_value=10)
    breakfast = serializers.BooleanField(required=False, default=False)
    free_cancellation = serializers.BooleanField(required=False, default=False)
    pay_at_property = serializers.BooleanField(required=False, default=False)
    near = serializers.UUIDField(required=False)
    max_km = serializers.FloatField(required=False, min_value=0.5, max_value=100)
    sort = serializers.CharField(required=False, default="recommended")
    page = serializers.IntegerField(required=False, min_value=1, default=1)


def _query_dict(qp) -> dict:
    out = {}
    for k in qp:
        vals = qp.getlist(k)
        out[k] = ",".join(vals).split(",") if k in ("type", "stars", "amenities", "room_class") else vals[-1]
    return out


class HomeView(APIView):
    """GET /hotels/home — destinations, data-backed collections, live offers and the filter vocabulary."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        props = list(properties())
        dests = []
        for d in Destination.objects.filter(is_active=True, parent__isnull=True):
            mine = [p for p in props if p.destination_id == d.id or p.destination.parent_id == d.id]
            if not mine:
                continue
            low = min((x for x in (_lowest(p) for p in mine) if x is not None), default=None)
            dests.append({"slug": d.slug, "name": d.name, "region": d.region, "tagline": d.tagline, "tags": d.tags, "properties": len(mine),
                          "from_price": f"{low:.2f}" if low is not None else None})
        cols = []
        for code, title, sub in COLLECTIONS:
            members = _collection_members(code, props)
            if not members:
                continue
            low = min((x for x in (_lowest(p) for p in members) if x is not None), default=None)
            places = sorted({p.destination.parent.name if p.destination.parent else p.destination.name for p in members})
            cols.append({"code": code, "title": title, "subtitle": sub, "properties": len(members), "destinations": places[:4],
                         "from_price": f"{low:.2f}" if low is not None else None})
        now_offers = HotelOffer.objects.filter(is_active=True, ends_at__gt=timezone.now(), code="").select_related("property__partner")[:6]
        return Response({"destinations": dests, "collections": cols, "filters": filters_meta(),
                         "offers": [{"id": str(o.id), "title": o.title, "kind": o.kind, "kind_label": o.get_kind_display(), "percent": o.percent,
                                     "property": o.property.partner.business_name if o.property_id else None, "min_nights": o.min_nights,
                                     "conditions": _offer_conditions(o)} for o in now_offers],
                         "price_note": "“From” prices are the lowest weekday room rate before tax; the price for your dates is shown in search."})


def _offer_conditions(o: HotelOffer) -> str:
    bits = []
    if o.min_nights > 1:
        bits.append(f"{o.min_nights}+ nights")
    if o.min_days_ahead:
        bits.append(f"book {o.min_days_ahead}+ days ahead")
    if o.max_days_ahead is not None:
        bits.append(f"check-in within {o.max_days_ahead} days")
    if o.kind == "weekend":
        bits.append("stays including a Fri or Sat night")
    if o.max_discount:
        bits.append(f"up to ₹{o.max_discount:,.0f} off")
    return ", ".join(bits)


class DestinationsView(APIView):
    """GET /hotels/destinations?q= — real destinations, landmarks and properties matching what was typed."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()[:60]
        if len(q) < 2:
            return Response({"results": []})
        out = [{"kind": "destination", "value": d.slug, "label": d.name, "detail": d.region if d.kind == "city" else f"{d.parent.name if d.parent else ''}"}
               for d in Destination.objects.filter(Q(name__icontains=q) | Q(region__icontains=q), is_active=True).select_related("parent")[:5]]
        out += [{"kind": "landmark", "value": lm.name, "label": lm.name, "detail": f"{lm.get_kind_display()} · {lm.destination.name}"}
                for lm in Landmark.objects.filter(name__icontains=q).select_related("destination")[:4]]
        out += [{"kind": "property", "value": str(p.id), "label": p.partner.business_name, "detail": f"{p.get_property_type_display()} · {p.area or p.destination.name}"}
                for p in properties().filter(partner__business_name__icontains=q)[:4]]
        return Response({"results": out})


class SearchView(APIView):
    """GET /hotels/search?destination&check_in&check_out&rooms&adults&children&filters&sort&page"""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        s = SearchParams(data=_query_dict(request.query_params))
        s.is_valid(raise_exception=True)
        res = inventory().search(s.validated_data, request)
        saved = _saved(request)
        for c in res["results"]:
            c["favorite_id"] = saved.get(c["id"])
        if res["destination"]:
            d = Destination.objects.get(slug=res["destination"]["slug"])
            res["landmarks"] = [{"id": str(lm.id), "name": lm.name, "kind": lm.kind, "kind_label": lm.get_kind_display()}
                                for lm in Landmark.objects.filter(Q(destination=d) | Q(destination__parent=d))]
        return Response(res)


def _aspects(p: HotelProperty) -> dict:
    from django.db.models import Avg

    agg = HotelReview.objects.filter(property=p, is_published=True).aggregate(**{a: Avg(a) for a in HotelReview.ASPECTS})
    return {k: round(v, 1) for k, v in agg.items() if v is not None}


def review_out(r: HotelReview) -> dict:
    return {"id": str(r.id), "overall": r.overall, "title": r.title, "comment": r.comment, "traveller": r.get_traveller_display() if r.traveller else "",
            "stayed": r.booking.check_in.strftime("%b %Y"), "nights": r.booking.nights, "room": r.booking.room_name,
            "author": (r.customer.user.full_name or "Guest").split()[0], "created_at": r.created_at.isoformat(), "verified_stay": True}


class PropertyView(APIView):
    """GET /hotels/properties/<id>?check_in&check_out&rooms&adults&children — details; rooms and rates when dates are given."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, pk):
        p = get_object_or_404(properties(), pk=pk)
        rooms = None
        stay = None
        if request.query_params.get("check_in"):
            s = StayParams(data=request.query_params)
            s.is_valid(raise_exception=True)
            stay = s.validated_data
            rooms = inventory().rooms(p, stay["check_in"], stay["check_out"], stay["rooms"], stay["adults"], stay["children"], request)
        from .search import centre_of

        centre = centre_of(p.destination.parent or p.destination)
        lms = Landmark.objects.filter(Q(destination=p.destination) | Q(destination=p.destination.parent_id) | Q(destination__parent=p.destination.parent_id or p.destination_id))
        reviews = p.reviews.filter(is_published=True).select_related("customer__user", "booking")[:6]
        return Response({
            "id": str(p.id), "name": p.partner.business_name, "type": p.property_type, "type_label": p.get_property_type_display(),
            "star_rating": p.star_rating, "tagline": p.tagline, "description": p.description, "highlights": p.highlights,
            "destination": {"slug": (p.destination.parent or p.destination).slug, "name": (p.destination.parent or p.destination).name},
            "area": p.area, "address": p.address, "latitude": float(p.latitude), "longitude": float(p.longitude), "accent": p.accent,
            "rating": {"average": f"{p.rating_average:.1f}", "count": p.rating_count, "label": engine.rating_label(p.rating_average, p.rating_count)} if p.rating_count else None,
            "aspects": _aspects(p) if p.rating_count else {},
            "amenities": [{"slug": a.slug, "name": a.name, "icon": a.icon} for a in p.amenities.all()],
            "check_in_time": p.check_in_time.strftime("%H:%M"), "check_out_time": p.check_out_time.strftime("%H:%M"), "languages": p.languages,
            "policies": p.policies, "accessibility": p.accessibility, "parking": p.parking, "good_for": p.good_for,
            "payment_options": sorted({r.get_payment_display() for room in p.rooms.all() for r in room.rates.all()}),
            "meal_options": sorted({r.get_meal_plan_display() for room in p.rooms.all() for r in room.rates.all()}),
            "distances": sorted([{"name": lm.name, "kind": lm.kind, "kind_label": lm.get_kind_display(),
                                  "km": engine.distance_km(p, (float(lm.latitude), float(lm.longitude)))} for lm in lms], key=lambda x: x["km"] or 0)[:8],
            "distance_from_centre": engine.distance_km(p, centre), "nearby": p.nearby,
            "images": [{"id": str(i.id), "category": i.category, "caption": i.caption, **media.urls(i, request)} for i in p.images.all()],
            "favorite_id": _saved(request).get(str(p.id)),
            "rooms": rooms, "stay": {k: (v.isoformat() if isinstance(v, date) else v) for k, v in stay.items()} if stay else None,
            "offers": [{"title": o.title, "percent": o.percent, "conditions": _offer_conditions(o)} for o in engine.live_offers(p) if not o.code],
            "reviews": [review_out(r) for r in reviews],
        })


class ReviewsView(APIView):
    """GET /hotels/properties/<id>/reviews?sort=relevant|recent|highest|lowest&page"""

    permission_classes = [permissions.AllowAny]

    def get(self, request, pk):
        p = get_object_or_404(properties(), pk=pk)
        order = {"recent": ["-created_at"], "highest": ["-overall", "-created_at"], "lowest": ["overall", "-created_at"]}.get(
            request.query_params.get("sort"), ["-created_at"])
        qs = p.reviews.filter(is_published=True).select_related("customer__user", "booking")
        if request.query_params.get("sort") in (None, "", "relevant"):
            from django.db.models.functions import Length

            qs = qs.annotate(n=Length("comment")).order_by("-n", "-created_at")  # written reviews first, newest next
        else:
            qs = qs.order_by(*order)
        page = max(1, int(request.query_params.get("page") or 1)) if str(request.query_params.get("page") or "1").isdigit() else 1
        rows = list(qs[(page - 1) * 10: page * 10 + 1])
        return Response({"count": p.rating_count, "aspects": _aspects(p), "results": [review_out(r) for r in rows[:10]], "has_more": len(rows) > 10})


class CompareView(APIView):
    """GET /hotels/compare?ids=a,b,c&check_in&check_out&rooms&adults&children — 2–4 properties side by side."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        ids = [x for x in (request.query_params.get("ids") or "").split(",") if x][:4]
        if len(ids) < 2:
            raise DomainError("Choose 2 to 4 stays to compare.", code="validation_error")
        s = StayParams(data=request.query_params)
        s.is_valid(raise_exception=True)
        st = s.validated_data
        inv = inventory()
        out = []
        for p in properties().filter(pk__in=ids):
            q, _ = inv.best_offer_for(p, st["check_in"], st["check_out"], st["rooms"], st["adults"], st["children"], {})
            out.append({"id": str(p.id), "name": p.partner.business_name, "type_label": p.get_property_type_display(), "star_rating": p.star_rating,
                        "area": p.area, "image_url": image_url(p, request),
                        "rating": {"average": f"{p.rating_average:.1f}", "count": p.rating_count} if p.rating_count else None,
                        "amenities": [a.name for a in p.amenities.all()], "check_in_time": p.check_in_time.strftime("%H:%M"),
                        "cheapest": ({"room": q.room.name, "meal": q.rate.get_meal_plan_display(), "total": f"{q.total:.2f}",
                                      "policy": engine.policy_text(q.rate.refundable, q.cancel_until, q.rate.cancel_fee_percent),
                                      "payment": q.rate.get_payment_display()} if q else None)})
        return Response({"results": out})


# --- customer --------------------------------------------------------------------------------------------------------

class GuestInput(serializers.Serializer):
    guest_name = serializers.CharField(max_length=120, min_length=2)
    guest_email = serializers.EmailField(required=False, allow_blank=True)
    guest_phone = serializers.RegexField(r"^\+?[0-9 ]{8,16}$", max_length=20)
    other_guests = serializers.ListField(child=serializers.CharField(max_length=80, allow_blank=True), required=False, default=list, max_length=10)
    special_requests = serializers.CharField(max_length=500, required=False, allow_blank=True)


class ReviewInput(StayParams):
    rate_id = serializers.UUIDField()
    coupon = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")


class BookInput(ReviewInput, GuestInput):
    payment_mode = serializers.ChoiceField(choices=["pay_now", "at_property"], required=False)
    expected_total = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    idempotency_key = serializers.CharField(max_length=64)


class PrepareView(APIView):
    """POST /customer/hotels/review — the Review Booking numbers for a room, rate, stay and party."""

    permission_classes = [IsCustomer]

    def post(self, request):
        s = ReviewInput(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(booking.prepare(s.validated_data))


def _own(request):
    return (HotelBooking.objects.filter(customer=request.user.customer_profile)
            .select_related("property__partner", "property__destination", "room_type").prefetch_related("events", "payments", "support_tickets"))


def booking_out(b: HotelBooking, request, full: bool = False) -> dict:
    p = b.property
    out = {"id": str(b.id), "number": b.number, "kind": "hotel", "status": b.status, "status_label": b.get_status_display(),
           "payment_status": b.payment_status, "payment_status_label": b.get_payment_status_display(),
           "property": {"id": str(p.id), "name": p.partner.business_name, "area": p.area, "destination": (p.destination.parent or p.destination).name,
                        "image_url": image_url(p, request), "accent": p.accent},
           "room_name": b.room_name, "check_in": b.check_in.isoformat(), "check_out": b.check_out.isoformat(), "nights": b.nights, "rooms": b.rooms,
           "adults": b.adults, "children": b.children, "total": f"{b.total:.2f}", "created_at": b.created_at.isoformat(),
           "is_active": b.status in ACTIVE, "reviewed": hasattr(b, "review")}
    if not full:
        return out
    pay = b.payments.order_by("-created_at").first()
    return {**out, "guest": {"name": b.guest_name, "email": b.guest_email, "phone": b.guest_phone, "others": b.other_guests},
            "special_requests": b.special_requests, "rate_name": b.rate_name, "meal_plan": b.meal_plan, "meal_label": b.get_meal_plan_display(),
            "payment_mode": b.payment_mode, "payment_mode_label": b.get_payment_mode_display(),
            "policy": engine.policy_text(b.refundable, b.free_cancel_until, b.cancel_fee_percent), "refundable": b.refundable,
            "free_cancel_until": b.free_cancel_until.isoformat() if b.free_cancel_until else None,
            "nightly": b.nightly, "room_total": f"{b.room_total:.2f}", "discount": f"{b.discount:.2f}", "offer_title": b.offer_title,
            "tax": f"{b.tax:.2f}", "refunded": f"{b.refunded:.2f}", "address": p.address, "latitude": float(p.latitude), "longitude": float(p.longitude),
            "check_in_time": p.check_in_time.strftime("%H:%M"), "check_out_time": p.check_out_time.strftime("%H:%M"), "policies": p.policies,
            "hold_expires_at": b.hold_expires_at.isoformat() if b.hold_expires_at and b.status == "pending_payment" else None,
            "timeline": [{"to": e.to, "label": e.get_to_display(), "note": e.note, "at": e.created_at.isoformat()} for e in b.events.all()],
            "payment": {"method": pay.method, "status": pay.status, "amount": f"{pay.amount:.2f}", "reference": str(pay.id)[:8].upper()} if pay else None,
            "cancellation": booking.cancellation(b), "can_pay": b.status == "pending_payment" and b.payment_status == "pending",
            "can_review": b.status == "completed" and not hasattr(b, "review"),
            "review": {"overall": b.review.overall, "comment": b.review.comment} if hasattr(b, "review") else None,
            "cancel_reason": b.cancel_reason, "tickets": [{"id": str(t.id), "reference": t.reference, "status": t.status} for t in b.support_tickets.all()],
            "modification": "Changing dates, room or guests isn’t supported online yet: cancel (under the policy above) and book again, or contact support."}


def _sweep():
    booking.expire_holds()
    booking.complete_past()


class BookingsView(APIView):
    """GET /customer/hotels/bookings?when=upcoming|past ; POST books (Confirm & pay)."""

    permission_classes = [IsCustomer]

    def get(self, request):
        _sweep()
        qs = _own(request)
        when = request.query_params.get("when")
        if when == "upcoming":
            qs = qs.filter(status__in=ACTIVE).order_by("check_in")
        elif when == "past":
            qs = qs.exclude(status__in=ACTIVE)
        return Response({"results": [booking_out(b, request) for b in qs[:50]]})

    def post(self, request):
        s = BookInput(data=request.data)
        s.is_valid(raise_exception=True)
        b, created, error = booking.book(request.user.customer_profile, s.validated_data)
        out = booking_out(_own(request).get(pk=b.pk), request, True)
        out["payment_error"] = error
        return Response(out, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class BookingDetailView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request, pk):
        _sweep()
        return Response(booking_out(get_object_or_404(_own(request), pk=pk), request, True))


class StayReviewInput(serializers.Serializer):
    overall = serializers.IntegerField(min_value=1, max_value=10)
    cleanliness = serializers.IntegerField(min_value=1, max_value=10)
    location = serializers.IntegerField(min_value=1, max_value=10)
    comfort = serializers.IntegerField(min_value=1, max_value=10)
    facilities = serializers.IntegerField(min_value=1, max_value=10)
    staff = serializers.IntegerField(min_value=1, max_value=10)
    value = serializers.IntegerField(min_value=1, max_value=10)
    title = serializers.CharField(max_length=120, required=False, allow_blank=True)
    comment = serializers.CharField(max_length=3000, required=False, allow_blank=True)
    traveller = serializers.ChoiceField(choices=["family", "couple", "solo", "business", "friends", ""], required=False, default="")


class BookingActionView(APIView):
    """POST /customer/hotels/bookings/<id>/<pay|cancel|review>"""

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
            s = StayReviewInput(data=request.data)
            s.is_valid(raise_exception=True)
            booking.review(request.user.customer_profile, b, s.validated_data)
        else:
            raise DomainError("Unknown action.", code="unknown_action", status_code=404)
        return Response(booking_out(_own(request).get(pk=pk), request, True))


class SavedView(APIView):
    """GET /customer/hotels/saved — saved hotels (shared Wishlist rows)."""

    permission_classes = [IsCustomer]

    def get(self, request):
        rows = request.user.customer_profile.wishlist_items.filter(hotel__isnull=False, hotel__is_listed=True).select_related("hotel__partner", "hotel__destination")
        return Response({"results": [{**property_card(r.hotel, request), "favorite_id": str(r.id)} for r in rows]})


def property_card(p: HotelProperty, request=None) -> dict:
    low = RatePlan.objects.filter(room_type__property=p, is_active=True).aggregate(m=Min("price"))["m"]
    return {"id": str(p.id), "name": p.partner.business_name, "type_label": p.get_property_type_display(), "star_rating": p.star_rating,
            "area": p.area, "destination": (p.destination.parent or p.destination).name, "image_url": image_url(p, request), "accent": p.accent,
            "rating": {"average": f"{p.rating_average:.1f}", "count": p.rating_count, "label": engine.rating_label(p.rating_average, p.rating_count)} if p.rating_count else None,
            "from_price": f"{low:.2f}" if low is not None else None}


# --- partner ---------------------------------------------------------------------------------------------------------

def own_property(request) -> HotelProperty:
    from apps.partners.views import _onboarded_partner

    p = HotelProperty.objects.filter(partner=_onboarded_partner(request)).first()
    if p is None:
        raise DomainError("Your Click. Hotels property isn’t set up yet.", code="not_a_hotel", status_code=404)
    return p


class InventoryInput(serializers.Serializer):
    room_id = serializers.UUIDField()
    start = serializers.DateField()
    end = serializers.DateField()
    units = serializers.IntegerField(min_value=0, max_value=500, required=False, allow_null=True)
    closed = serializers.BooleanField(required=False)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=1, required=False, allow_null=True)


class PartnerInventoryView(APIView):
    """GET /partner/hotels/inventory?start&days — rooms × nights: units, booked, closed, price ; PUT sets a date range."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        p = own_property(request)
        start = engine.today()
        days = min(60, int(request.query_params.get("days") or 14))
        dates = [start + timedelta(days=i) for i in range(days)]
        out = []
        for room in p.rooms.filter(is_active=True):
            inv = {i.date: i for i in room.inventory.filter(date__in=dates)}
            out.append({"room_id": str(room.id), "name": room.name, "total_units": room.total_units, "nights": [
                {"date": d.isoformat(), "free": engine.free_units(room, [d]), "closed": bool(inv.get(d) and inv[d].closed),
                 "units": inv[d].units if d in inv and inv[d].units is not None else room.total_units,
                 "price": f"{inv[d].price_override:.2f}" if d in inv and inv[d].price_override else None} for d in dates]})
        return Response({"property": p.partner.business_name, "rooms": out})

    def put(self, request):
        p = own_property(request)
        s = InventoryInput(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        room = get_object_or_404(RoomType, pk=d["room_id"], property=p)
        if d["end"] < d["start"] or (d["end"] - d["start"]).days > 366:
            raise DomainError("Choose a date range up to a year.", code="validation_error")
        day = d["start"]
        while day <= d["end"]:
            inv, _ = RoomInventory.objects.get_or_create(room_type=room, date=day)
            if "units" in d:
                inv.units = d["units"]
            if "closed" in d:
                inv.closed = d["closed"]
            if "price" in d:
                inv.price_override = d["price"]
            inv.save()
            day += timedelta(days=1)
        return self.get(request)
