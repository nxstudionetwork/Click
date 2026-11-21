"""Click. Travel API. Places, search and journey details are public; reviews, bookings, tickets, cancellations,
travellers, recent searches, saved routes, price alerts and preferences belong to the signed-in customer (every query
is scoped to them)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.activity.services import record
from apps.core.api.exceptions import DomainError
from apps.core.api.permissions import IsCustomer
from apps.rewards.services import points_for_amount

from . import booking, engine, search
from .models import (ACTIVE, Journey, Mode, Operator, Passenger, Place, PriceAlert, RecentSearch, Route, SavedTraveller, Service, Stop,
                     TravelBooking, TravelOffer, TravelPreference)


def _customer(request):
    u = request.user
    return u.customer_profile if u and u.is_authenticated and hasattr(u, "customer_profile") else None


def place_out(p: Place) -> dict:
    return {"id": str(p.id), "slug": p.slug, "kind": p.kind, "kind_label": p.get_kind_display(), "name": p.name, "code": p.code,
            "city": p.city_place.name, "city_slug": p.city_place.slug, "state": p.state, "label": p.label}


def _list(qp, key) -> list:
    return [x for x in ",".join(qp.getlist(key)).split(",") if x]


class PlacesView(APIView):
    """GET /travel/places?q=&mode= — cities, stations, airports and boarding points; each labelled with what it is."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()[:60]
        mode = request.query_params.get("mode")
        if len(q) < 2:
            return Response({"results": []})
        kinds = {"bus": ["city", "bus_stop"], "train": ["city", "station"], "flight": ["city", "airport"]}.get(mode, ["city", "station", "airport", "bus_stop"])
        qs = (Place.objects.filter(is_active=True, kind__in=kinds)
              .filter(Q(name__icontains=q) | Q(code__iexact=q) | Q(aliases__icontains=q) | Q(state__icontains=q) | Q(city__name__icontains=q))
              .select_related("city"))
        rows = sorted(qs[:40], key=lambda p: (p.kind != "city", not p.name.lower().startswith(q.lower()), p.code.upper() != q.upper(), p.name))
        return Response({"results": [place_out(p) for p in rows[:10]]})


def _from_price(service: Service) -> Decimal | None:
    stops = list(service.stops.all())
    if len(stops) < 2:
        return None
    vals = []
    for fc in service.classes.all():
        if service.mode == Mode.TRAIN:
            vals.append(max(fc.min_fare, engine.round_to(fc.per_km * stops[-1].km, 5)) + fc.reservation_charge + fc.superfast_charge)
        else:
            vals.append(fc.base_fare)
    return min(vals) if vals else None


def routes_catalog() -> list[dict]:
    """Every end-to-end city pair Click. sells, with the published lowest fare and the services on it."""
    services = (Service.objects.filter(is_active=True, operator__status="active").select_related("operator")
                .prefetch_related(Prefetch("stops", queryset=Stop.objects.select_related("place__city").order_by("seq")), "classes"))
    pairs: dict = {}
    for s in services:
        stops = list(s.stops.all())
        if len(stops) < 2:
            continue
        o, d = stops[0].place.city_place, stops[-1].place.city_place
        key = (s.mode, o.id, d.id)
        row = pairs.setdefault(key, {"mode": s.mode, "from": place_out(o), "to": place_out(d), "km": stops[-1].km, "services": 0,
                                     "from_price": None, "premium": False, "sleeper": False, "minutes": None})
        row["services"] += 1
        fp = _from_price(s)
        if fp is not None and (row["from_price"] is None or fp < row["from_price"]):
            row["from_price"] = fp
        mins = engine.duration_minutes(engine.at(date(2026, 1, 5), stops[0], "depart"), engine.at(date(2026, 1, 5), stops[-1], "arrive"))
        row["minutes"] = mins if row["minutes"] is None else min(row["minutes"], mins)
        row["premium"] |= s.premium or any(c.code in ("business", "1A", "EC", "premium_economy") for c in s.classes.all())
        row["sleeper"] |= s.bus_type in ("sleeper", "seater_sleeper") or any(c.code in ("SL", "3A", "2A", "1A") for c in s.classes.all())
    out = list(pairs.values())
    for r in out:
        r["from_price"] = f"{r['from_price']:.2f}" if r["from_price"] is not None else None
    return out


COLLECTIONS = [
    ("weekend", "Weekend escapes", "Under 8 hours: leave Friday night, back Sunday", lambda r: r["minutes"] and r["minutes"] <= 480 and r["mode"] != "flight"),
    ("long", "Long journeys", "1,000 km and more", lambda r: r["km"] >= 1000),
    ("business", "Business travel", "Flights and fast premium trains", lambda r: r["mode"] == "flight" or (r["mode"] == "train" and r["premium"])),
    ("family", "Family travel", "Sleeper berths and AC coaches to stretch out", lambda r: r["sleeper"]),
    ("budget", "Budget travel", "Fares from under ₹800", lambda r: r["from_price"] and Decimal(r["from_price"]) < 800),
    ("premium", "Premium travel", "Business cabins, First AC and premium coaches", lambda r: r["premium"]),
]


class HomeView(APIView):
    """GET /travel/home?city= — routes Click. sells (per mode), data-rule collections, live offers, the vocabulary."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        routes = routes_catalog()
        city = (request.query_params.get("city") or "").strip().lower()
        by_mode = {m: sorted([r for r in routes if r["mode"] == m], key=lambda r: (-r["services"], r["from"]["name"]))[:8] for m in Mode.values}
        near = [r for r in routes if city and (r["from"]["name"].lower() == city or r["from"]["slug"] == city)][:8]
        cols = []
        for code, title, sub, rule in COLLECTIONS:
            members = [r for r in routes if rule(r)]
            if members:
                cols.append({"code": code, "title": title, "subtitle": sub, "routes": sorted(members, key=lambda r: Decimal(r["from_price"] or "1e9"))[:6]})
        now = timezone.now()
        offers = TravelOffer.objects.filter(is_active=True, starts_at__lte=now, ends_at__gt=now)
        return Response({
            "routes": by_mode, "from_city": near, "collections": cols,
            "offers": [{"id": str(o.id), "title": o.title, "mode": o.mode or None, "code": o.code or None, "percent": o.percent,
                        "max_discount": f"{o.max_discount:.0f}" if o.max_discount else None, "min_fare": f"{o.min_fare:.0f}" if o.min_fare else None,
                        "ends_at": o.ends_at.isoformat()} for o in offers],
            "train_classes": [{"code": c, "name": n} for c, n in search.TRAIN_CLASSES],
            "cabins": [{"code": c, "name": n} for c, n in search.CABINS],
            "max_passengers": engine.MAX_PASSENGERS,
            "price_note": "“From” fares are the lowest published fare on the route before tax; your fare is shown in search.",
        })


class SearchParams(serializers.Serializer):
    mode = serializers.ChoiceField(choices=Mode.values)
    origin = serializers.SlugField(max_length=140)
    destination = serializers.SlugField(max_length=140)
    date = serializers.DateField()
    return_date = serializers.DateField(required=False, allow_null=True)
    adults = serializers.IntegerField(min_value=1, max_value=9, default=1)
    children = serializers.IntegerField(min_value=0, max_value=8, default=0)
    infants = serializers.IntegerField(min_value=0, max_value=4, default=0)
    travel_class = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")

    def validate(self, a):
        places = {p.slug: p for p in Place.objects.filter(slug__in=[a["origin"], a["destination"]], is_active=True).select_related("city")}
        if a["origin"] not in places:
            raise serializers.ValidationError({"origin": "Choose a city, station or airport from the list."})
        if a["destination"] not in places:
            raise serializers.ValidationError({"destination": "Choose a city, station or airport from the list."})
        o, d = places[a["origin"]], places[a["destination"]]
        if o.city_place.id == d.city_place.id:
            raise serializers.ValidationError({"destination": "From and To can’t be the same city."})
        if a["date"] < engine.today():
            raise serializers.ValidationError({"date": "Choose today or a later date."})
        if a["date"] > engine.today() + timedelta(days=330):
            raise serializers.ValidationError({"date": "Bookings open up to 330 days ahead."})
        if a.get("return_date") and a["return_date"] < a["date"]:
            raise serializers.ValidationError({"return_date": "The return date can’t be before departure."})
        total = a["adults"] + a["children"]
        if total > engine.MAX_PASSENGERS[a["mode"]]:
            raise serializers.ValidationError({"adults": f"Up to {engine.MAX_PASSENGERS[a['mode']]} passengers per booking."})
        if a["infants"] and a["mode"] != Mode.FLIGHT:
            raise serializers.ValidationError({"infants": "Infants are added on flights only."})
        if a["infants"] > a["adults"]:
            raise serializers.ValidationError({"infants": "Each infant must travel with an adult."})
        a["origin_place"], a["destination_place"] = o, d
        return a


def _filters(qp) -> dict:
    f = {k: _list(qp, k) for k in ("departure", "arrival", "operators", "cancellation", "amenities", "bus_type", "boarding", "dropping", "train_type", "stops")}
    for k in ("min_price", "max_price", "min_rating", "max_duration", "weekday"):
        v = qp.get(k)
        f[k] = v if v not in (None, "") and str(v).replace(".", "", 1).isdigit() else None
    for k in ("available_only", "refundable", "checked_bag"):
        f[k] = qp.get(k) in ("1", "true")
    return f


def _options(v: dict) -> list[dict]:
    try:
        return search.gather(v["mode"], v["origin_place"], v["destination_place"], v["date"], v["adults"] + v["children"], v["travel_class"])
    except search.TravelUnavailable:
        raise DomainError("Travel options are temporarily unavailable. Try again.", code="travel_unavailable", status_code=503)


class SearchView(APIView):
    """GET /travel/search?mode&origin&destination&date&adults&children&infants&travel_class&<filters>&sort&page"""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        s = SearchParams(data=request.query_params)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        opts = _options(v)
        filtered = search.apply_filters(opts, _filters(request.query_params))
        hl = search.highlights(filtered)
        rows = search.sort(filtered, request.query_params.get("sort") or "recommended")
        page = max(1, int(request.query_params.get("page") or 1)) if str(request.query_params.get("page") or "1").isdigit() else 1
        labels = {}
        for k, oid in hl.items():
            labels.setdefault(oid, []).append(k)
        for o in rows:
            o["highlights"] = labels.get(o["id"], [])
        c = _customer(request)
        if c is not None:
            RecentSearch.objects.update_or_create(customer=c, mode=v["mode"], origin=v["origin_place"], destination=v["destination_place"], defaults={
                "date": v["date"], "return_date": v.get("return_date"), "adults": v["adults"], "children": v["children"], "infants": v["infants"],
                "travel_class": v["travel_class"]})
            for old in RecentSearch.objects.filter(customer=c)[10:]:
                old.delete()
        alternatives = []
        if not opts:  # what else really exists for this trip
            for m in Mode.values:
                if m == v["mode"]:
                    continue
                alt = search.gather(m, v["origin_place"], v["destination_place"], v["date"], v["adults"] + v["children"]) if v["infants"] == 0 or m == "flight" else []
                if alt:
                    alternatives.append({"mode": m, "count": len(alt), "lowest": min((o["lowest"] for o in alt if o["lowest"]), key=Decimal, default=None)})
        return Response({
            "query": {"mode": v["mode"], "origin": place_out(v["origin_place"]), "destination": place_out(v["destination_place"]),
                      "date": v["date"].isoformat(), "return_date": v["return_date"].isoformat() if v.get("return_date") else None,
                      "adults": v["adults"], "children": v["children"], "infants": v["infants"], "travel_class": v["travel_class"]},
            "count": len(rows), "total": len(opts), "results": rows[(page - 1) * search.PAGE: page * search.PAGE],
            "has_more": page * search.PAGE < len(rows), "strip": search.strip(filtered, hl), "facets": search.facets(opts),
            "alternatives": alternatives,
            "saved_route_id": _saved_route_id(c, v["origin_place"], v["destination_place"]),
            "fare_note": "Fares are per person including GST, checked again before you pay.",
        })


class DatesView(APIView):
    """GET /travel/dates?… same query — the lowest available fare on the 3 days either side (computed, never estimated)."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        s = SearchParams(data=request.query_params)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        out = []
        for i in range(-3, 4):
            d = v["date"] + timedelta(days=i)
            if d < engine.today():
                continue
            try:
                low = search.cheapest_on(v["mode"], v["origin_place"], v["destination_place"], d, v["adults"] + v["children"], v["travel_class"])
            except search.TravelUnavailable:
                low = None
            out.append({"date": d.isoformat(), "lowest": f"{low:.2f}" if low is not None else None})
        return Response({"results": out})


class OptionView(APIView):
    """GET /travel/options/<journey>/<from_stop>/<to_stop>?seats= — full details: route timeline, classes, seat map."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, journey, a, b):
        j = get_object_or_404(Journey.objects.select_related("service__operator"), pk=journey, service__is_active=True)
        service = j.service
        stops = list(service.stops.select_related("place__city").order_by("seq"))
        sa = next((s for s in stops if s.id == a), None)
        sb = next((s for s in stops if s.id == b), None)
        if sa is None or sb is None or sa.seq >= sb.seq:
            raise DomainError("This journey is no longer available. Refresh the results.", code="journey_unavailable", status_code=404)
        seats = max(1, min(9, int(request.query_params.get("seats") or 1))) if str(request.query_params.get("seats") or "1").isdigit() else 1
        city_from = {p.id for p in Place.objects.filter(Q(pk=sa.place.city_place.id) | Q(city=sa.place.city_place))}
        city_to = {p.id for p in Place.objects.filter(Q(pk=sb.place.city_place.id) | Q(city=sb.place.city_place))}
        o = search.option(service, j, sa, sb, seats, "", city_from, city_to)
        o["route"] = [{"name": s.place.name, "code": s.place.code, "city": s.place.city_place.name, "arrive": engine.at(j.date, s, "arrive").isoformat() if s.arrive else None,
                       "depart": engine.at(j.date, s, "depart").isoformat() if s.depart else None, "km": s.km, "day": s.day + 1, "note": s.note,
                       "in_segment": sa.seq <= s.seq <= sb.seq} for s in stops]
        o["bookable_now"] = engine.at(j.date, sa, "depart") > timezone.now() + timedelta(minutes=engine.CUTOFF_MINUTES[service.mode])
        if service.mode == Mode.BUS:
            sold = engine.sold_seats(j)
            fares = {c.code: engine.unit_fare(c, j, sa, sb)[0] for c in service.classes.all()}
            taxp = {c.code: c.tax_percent for c in service.classes.all()}
            layout = service.seat_layout or {}
            o["seat_map"] = {"decks": layout.get("decks", []), "seats": {
                k: {"class": info.get("class"), "kind": "sleeper" if info.get("class") == "sleeper" else "seater",
                    "status": "sold" if k in sold else ("blocked" if info.get("blocked") else "available"),
                    "ladies": bool(info.get("ladies")), "gents": bool(info.get("gents")),
                    "fare": f"{engine.money(fares.get(info.get('class'), 0) * (1 + taxp.get(info.get('class'), 0) / 100)):.2f}"}
                for k, info in layout.get("seats", {}).items()}, "max": engine.MAX_PASSENGERS["bus"]}
        o["policy_rules"] = service.cancellation
        o["source"] = service.operator.get_source_display()
        o["saved_route_id"] = _saved_route_id(_customer(request), sa.place.city_place, sb.place.city_place)
        return Response(o)


# --- customer --------------------------------------------------------------------------------------------------------

class PassengerInput(serializers.Serializer):
    name = serializers.RegexField(r"^[A-Za-z][A-Za-z .'-]{1,79}$", error_messages={"invalid": "Enter the name as on a government ID (letters only)."})
    age = serializers.IntegerField(min_value=0, max_value=110)
    gender = serializers.ChoiceField(choices=Passenger.Gender.values)
    berth_preference = serializers.ChoiceField(choices=["", "LB", "MB", "UB", "SL", "SU", "W", "A"], required=False, default="")


class ReviewInput(serializers.Serializer):
    journey_id = serializers.UUIDField()
    from_stop_id = serializers.UUIDField()
    to_stop_id = serializers.UUIDField()
    class_code = serializers.CharField(max_length=16)
    passengers = PassengerInput(many=True)
    infants = serializers.IntegerField(min_value=0, max_value=4, default=0)
    seats = serializers.ListField(child=serializers.CharField(max_length=8), required=False, default=list, max_length=9)
    coupon = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")


class BookInput(ReviewInput):
    contact_phone = serializers.RegexField(r"^\+?[0-9 ]{8,16}$", max_length=20)
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    expected_total = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    idempotency_key = serializers.CharField(max_length=64)
    trip_ref = serializers.CharField(max_length=40, required=False, allow_blank=True)
    save_travellers = serializers.BooleanField(required=False, default=False)


class PrepareView(APIView):
    """POST /customer/travel/review — the Review Journey numbers, availability and passenger status, re-checked now."""

    permission_classes = [IsCustomer]

    def post(self, request):
        s = ReviewInput(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(booking.prepare(s.validated_data))


def _own(request):
    return (TravelBooking.objects.filter(customer=request.user.customer_profile)
            .select_related("journey__service__operator", "from_stop__place__city", "to_stop__place__city", "fare_class")
            .prefetch_related("passengers", "events", "payments", "support_tickets"))


def booking_out(b: TravelBooking, full: bool = False) -> dict:
    j = b.journey
    out = {"id": str(b.id), "number": b.number, "kind": "travel", "mode": b.mode, "mode_label": b.get_mode_display(), "pnr": b.pnr,
           "status": b.status, "status_label": b.get_status_display(), "payment_status": b.payment_status,
           "payment_status_label": b.get_payment_status_display(), "operator": b.operator_name, "service": b.service_label,
           "class_name": b.class_name, "from": {"name": b.from_stop.place.name, "city": b.from_stop.place.city_place.name, "code": b.from_stop.place.code},
           "to": {"name": b.to_stop.place.name, "city": b.to_stop.place.city_place.name, "code": b.to_stop.place.code},
           "departs_at": b.departs_at.isoformat(), "arrives_at": b.arrives_at.isoformat(), "passengers_count": b.adults + b.children,
           "total": f"{b.total:.2f}", "created_at": b.created_at.isoformat(), "is_active": b.status in ACTIVE,
           "journey_status": j.status, "journey_status_label": j.get_status_display(), "delay_minutes": j.delay_minutes, "notice": j.notice}
    if not full:
        return out
    pay = b.payments.order_by("-created_at").first()
    return {**out, "trip_ref": b.trip_ref, "contact": {"phone": b.contact_phone, "email": b.contact_email},
            "passengers": [{"position": p.position, "name": p.name, "age": p.age, "gender": p.gender, "gender_label": p.get_gender_display(),
                            "seat": p.seat, "status": p.seat_status, "status_label": p.get_seat_status_display(), "queue": p.queue,
                            "berth_preference": p.berth_preference, "fare": f"{p.fare:.2f}"} for p in b.passengers.all()],
            "infants": b.infants, "from_full": {"label": b.from_label, "address": b.from_stop.place.address, "landmark": b.from_stop.place.landmark, "note": b.from_stop.note},
            "to_full": {"label": b.to_label, "address": b.to_stop.place.address, "landmark": b.to_stop.place.landmark, "note": b.to_stop.note},
            "duration_minutes": engine.duration_minutes(b.departs_at, b.arrives_at), "vehicle": j.service.vehicle, "baggage": j.service.baggage or None,
            "base_fare": f"{b.base_fare:.2f}", "fees": f"{b.fees:.2f}", "discount": f"{b.discount:.2f}", "offer_title": b.offer_title,
            "tax": f"{b.tax:.2f}", "refunded": f"{b.refunded:.2f}", "refundable": b.refundable,
            "policy": engine.policy_text(b.refundable, b.cancellation_rules),
            "hold_expires_at": b.hold_expires_at.isoformat() if b.hold_expires_at and b.status == "pending_payment" else None,
            "timeline": [{"to": e.to, "label": e.get_to_display(), "note": e.note, "at": e.created_at.isoformat()} for e in b.events.all()],
            "payment": {"method": pay.method, "status": pay.status, "status_label": pay.get_status_display(), "amount": f"{pay.amount:.2f}",
                        "reference": str(pay.id)[:8].upper()} if pay else None,
            "refund": ({"amount": f"{b.refunded:.2f}", "status": "completed", "label": "Refund completed · credited to Click. Wallet",
                        "to": "Click. Wallet"} if b.refunded > 0 else None),
            "cancellation": booking.cancellation(b), "can_pay": b.status == "pending_payment" and b.payment_status == "pending",
            "has_ticket": b.status in ("confirmed", "completed") and bool(b.pnr), "cancel_reason": b.cancel_reason,
            "can_rate": b.status == "completed" and not hasattr(b, "rating"),
            "rating": {"rating": b.rating.rating, "comment": b.rating.comment} if hasattr(b, "rating") else None,
            "tickets": [{"id": str(t.id), "reference": t.reference, "status": t.status} for t in b.support_tickets.all()],
            "points": points_for_amount(b.base_fare) if b.status in ACTIVE else 0,
            "modification": "Date or name changes aren’t available online yet: cancel under the rules above and book again, or contact support."}


class BookingsView(APIView):
    """GET /customer/travel/bookings?when=upcoming|past|cancelled ; POST books (Pay & book)."""

    permission_classes = [IsCustomer]

    def get(self, request):
        booking.sweep()
        qs = _own(request)
        when = request.query_params.get("when")
        if when == "upcoming":
            qs = qs.filter(status__in=ACTIVE).order_by("departs_at")
        elif when == "past":
            qs = qs.filter(status="completed")
        elif when == "cancelled":
            qs = qs.filter(status__in=["cancelled", "failed"])
        return Response({"results": [booking_out(b) for b in qs[:50]]})

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


class BookingActionView(APIView):
    """POST /customer/travel/bookings/<id>/<pay|cancel|rate>"""

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
        elif action == "rate":
            try:
                rating = int(request.data.get("rating"))
            except (TypeError, ValueError):
                rating = 0
            if not 1 <= rating <= 5:
                raise DomainError("Choose 1 to 5 stars.", code="validation_error")
            booking.rate(request.user.customer_profile, b, rating, str(request.data.get("comment") or ""))
        else:
            raise DomainError("Unknown action.", code="unknown_action", status_code=404)
        return Response(booking_out(_own(request).get(pk=pk), True))


class TicketView(APIView):
    """GET /customer/travel/bookings/<id>/ticket — only for an issued (paid, confirmed) ticket."""

    permission_classes = [IsCustomer]

    def get(self, request, pk):
        b = get_object_or_404(_own(request), pk=pk)
        if b.status not in ("confirmed", "completed") or not b.pnr:
            raise DomainError("A ticket is issued once the booking is paid and confirmed.", code="no_ticket", status_code=409)
        record(b.customer, "travel.ticket_viewed", {"number": b.number}, obj=b)
        d = booking_out(b, True)
        instructions = {
            "bus": ["Reach the boarding point 15 minutes before departure.", "Show this ticket and a photo ID to the bus staff."],
            "train": ["Carry the original photo ID of one passenger.", "RAC passengers share a side-lower berth; waitlisted passengers can’t board unless confirmed."],
            "flight": ["Web check-in and seat selection are with the airline, using this PNR.", "Reach the airport 2 hours before departure with a photo ID."],
        }[b.mode]
        return Response({**{k: d[k] for k in ("number", "pnr", "mode", "mode_label", "operator", "service", "class_name", "vehicle", "from", "to",
                                               "from_full", "to_full", "departs_at", "arrives_at", "duration_minutes", "passengers", "infants",
                                               "baggage", "total", "status", "status_label", "journey_status", "notice")},
                         "issued_at": b.confirmed_at.isoformat() if b.confirmed_at else None, "instructions": instructions,
                         "issuer": f"Issued by Click. for {b.operator_name}", "code": None,
                         "code_note": "Your PNR is the reference the operator checks; Click. doesn’t print a barcode the operator hasn’t issued."})


def _saved_route_id(c, o: Place, d: Place):
    if c is None:
        return None
    w = c.wishlist_items.filter(travel_route__origin=o.city_place, travel_route__destination=d.city_place).first()
    return str(w.id) if w else None


class RecentView(APIView):
    """GET /customer/travel/recent ; DELETE clears search history."""

    permission_classes = [IsCustomer]

    def get(self, request):
        rows = RecentSearch.objects.filter(customer=request.user.customer_profile).select_related("origin__city", "destination__city")[:8]
        return Response({"results": [{"id": str(r.id), "mode": r.mode, "origin": place_out(r.origin), "destination": place_out(r.destination),
                                      "date": r.date.isoformat() if r.date >= engine.today() else engine.today().isoformat(),
                                      "return_date": r.return_date.isoformat() if r.return_date and r.return_date >= engine.today() else None,
                                      "adults": r.adults, "children": r.children, "infants": r.infants, "travel_class": r.travel_class} for r in rows]})

    def delete(self, request):
        RecentSearch.objects.filter(customer=request.user.customer_profile).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RouteInput(serializers.Serializer):
    origin = serializers.SlugField()
    destination = serializers.SlugField()


def _route(data) -> Route:
    o = Place.objects.filter(slug=data["origin"]).first()
    d = Place.objects.filter(slug=data["destination"]).first()
    if o is None or d is None or o.city_place.id == d.city_place.id:
        raise DomainError("Choose two different places.", code="validation_error")
    r, _ = Route.objects.get_or_create(origin=o.city_place, destination=d.city_place)
    return r


class SavedRoutesView(APIView):
    """GET /customer/travel/routes ; POST {origin, destination} saves a route to the shared Wishlist."""

    permission_classes = [IsCustomer]

    def get(self, request):
        rows = request.user.customer_profile.wishlist_items.filter(travel_route__isnull=False).select_related("travel_route__origin", "travel_route__destination")
        return Response({"results": [{"favorite_id": str(w.id), "origin": place_out(w.travel_route.origin), "destination": place_out(w.travel_route.destination)} for w in rows]})

    def post(self, request):
        from apps.wishlists.models import WishlistItem

        s = RouteInput(data=request.data)
        s.is_valid(raise_exception=True)
        r = _route(s.validated_data)
        w, _ = WishlistItem.objects.get_or_create(customer=request.user.customer_profile, travel_route=r)
        record(request.user.customer_profile, "wishlist.added", {"route": str(r)}, obj=w)
        return Response({"favorite_id": str(w.id)}, status=status.HTTP_201_CREATED)


class TravellerInput(serializers.Serializer):
    name = PassengerInput().fields["name"]
    age = serializers.IntegerField(min_value=0, max_value=110)
    gender = serializers.ChoiceField(choices=Passenger.Gender.values)
    berth_preference = serializers.ChoiceField(choices=["", "LB", "MB", "UB", "SL", "SU", "W", "A"], required=False, default="")


def traveller_out(t: SavedTraveller) -> dict:
    return {"id": str(t.id), "name": t.name, "age": t.age, "gender": t.gender, "berth_preference": t.berth_preference}


class TravellersView(APIView):
    """GET / POST /customer/travel/travellers — saved passengers (name, age, gender, berth preference only)."""

    permission_classes = [IsCustomer]

    def get(self, request):
        return Response({"results": [traveller_out(t) for t in SavedTraveller.objects.filter(customer=request.user.customer_profile)]})

    def post(self, request):
        s = TravellerInput(data=request.data)
        s.is_valid(raise_exception=True)
        c = request.user.customer_profile
        if SavedTraveller.objects.filter(customer=c).count() >= 20:
            raise DomainError("You can save up to 20 travellers.", code="limit_reached")
        t, _ = SavedTraveller.objects.update_or_create(customer=c, name=s.validated_data["name"].strip(), defaults={k: s.validated_data[k] for k in ("age", "gender", "berth_preference")})
        return Response(traveller_out(t), status=status.HTTP_201_CREATED)


class TravellerDetailView(APIView):
    permission_classes = [IsCustomer]

    def patch(self, request, pk):
        t = get_object_or_404(SavedTraveller, pk=pk, customer=request.user.customer_profile)
        s = TravellerInput(t, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        for k, v in s.validated_data.items():
            setattr(t, k, v.strip() if isinstance(v, str) and k == "name" else v)
        t.save()
        return Response(traveller_out(t))

    def delete(self, request, pk):
        get_object_or_404(SavedTraveller, pk=pk, customer=request.user.customer_profile).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AlertInput(RouteInput):
    mode = serializers.ChoiceField(choices=Mode.values)
    date = serializers.DateField()


def _alert_out(a: PriceAlert) -> dict:
    return {"id": str(a.id), "mode": a.mode, "origin": place_out(a.route.origin), "destination": place_out(a.route.destination),
            "date": a.date.isoformat(), "last_fare": f"{a.last_fare:.2f}" if a.last_fare is not None else None,
            "last_checked_at": a.last_checked_at.isoformat() if a.last_checked_at else None, "is_active": a.is_active}


def check_alerts(qs) -> int:
    """Re-checks each followed journey's lowest fare with the same search the app uses; notifies on a change."""
    from apps.notifications.models import NotificationCategory
    from apps.notifications.services import notify

    n = 0
    for a in qs.filter(is_active=True).select_related("route__origin", "route__destination", "customer"):
        if a.date < engine.today():
            a.is_active = False
            a.save(update_fields=["is_active", "updated_at"])
            continue
        try:
            low = search.cheapest_on(a.mode, a.route.origin, a.route.destination, a.date, 1)
        except search.TravelUnavailable:
            continue
        if a.last_fare is not None and low is not None and low != a.last_fare:
            word = "dropped" if low < a.last_fare else "went up"
            notify(a.customer, NotificationCategory.OFFERS, f"Fare {word}: {a.route}"[:120],
                   f"Lowest {a.get_mode_display().lower()} fare on {a.date:%d %b}: ₹{low:,.0f} (was ₹{a.last_fare:,.0f}).",
                   f"/travel/search?mode={a.mode}&origin={a.route.origin.slug}&destination={a.route.destination.slug}&date={a.date.isoformat()}")
            n += 1
        a.last_fare, a.last_checked_at = low, timezone.now()
        a.save(update_fields=["last_fare", "last_checked_at", "updated_at"])
    return n


class AlertsView(APIView):
    """GET / POST /customer/travel/alerts — follow a journey's lowest fare; checked when you open Travel (and by the scheduler)."""

    permission_classes = [IsCustomer]

    def get(self, request):
        qs = PriceAlert.objects.filter(customer=request.user.customer_profile)
        stale = qs.filter(Q(last_checked_at__isnull=True) | Q(last_checked_at__lt=timezone.now() - timedelta(minutes=30)))
        check_alerts(stale)
        return Response({"results": [_alert_out(a) for a in qs.select_related("route__origin__city", "route__destination__city")]})

    def post(self, request):
        s = AlertInput(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        if v["date"] < engine.today():
            raise DomainError("Choose a future date.", code="validation_error")
        c = request.user.customer_profile
        if PriceAlert.objects.filter(customer=c, is_active=True).count() >= 10:
            raise DomainError("You can follow up to 10 journeys.", code="limit_reached")
        r = _route(v)
        a, _ = PriceAlert.objects.update_or_create(customer=c, route=r, mode=v["mode"], date=v["date"], defaults={"is_active": True})
        try:
            a.last_fare = search.cheapest_on(v["mode"], r.origin, r.destination, v["date"], 1)
        except search.TravelUnavailable:
            a.last_fare = None
        a.last_checked_at = timezone.now()
        a.save()
        return Response(_alert_out(a), status=status.HTTP_201_CREATED)


class AlertDetailView(APIView):
    permission_classes = [IsCustomer]

    def delete(self, request, pk):
        get_object_or_404(PriceAlert, pk=pk, customer=request.user.customer_profile).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PreferenceInput(serializers.Serializer):
    bus_types = serializers.ListField(child=serializers.ChoiceField(choices=["ac", "non_ac", "sleeper", "seater", "semi_sleeper", "premium"]), required=False)
    bus_departure = serializers.ChoiceField(choices=["", *search.BUCKETS], required=False)
    train_class = serializers.ChoiceField(choices=["", *[c for c, _ in search.TRAIN_CLASSES]], required=False)
    berth = serializers.ChoiceField(choices=["", "LB", "MB", "UB", "SL", "SU", "W", "A"], required=False)
    flight_cabin = serializers.ChoiceField(choices=["", *[c for c, _ in search.CABINS]], required=False)
    nonstop = serializers.BooleanField(required=False)
    airlines = serializers.ListField(child=serializers.UUIDField(), required=False, max_length=10)


class PreferencesView(APIView):
    """GET / PATCH /customer/travel/preferences — defaults for search filters (never a promise of availability)."""

    permission_classes = [IsCustomer]

    def _out(self, p: TravelPreference) -> dict:
        airlines = Operator.objects.filter(mode="flight", status="active")
        return {"bus_types": p.bus_types, "bus_departure": p.bus_departure, "train_class": p.train_class, "berth": p.berth,
                "flight_cabin": p.flight_cabin, "nonstop": p.nonstop, "airlines": [str(x) for x in p.airlines],
                "airline_options": [{"id": str(a.id), "name": a.name} for a in airlines]}

    def get(self, request):
        p, _ = TravelPreference.objects.get_or_create(customer=request.user.customer_profile)
        return Response(self._out(p))

    def patch(self, request):
        p, _ = TravelPreference.objects.get_or_create(customer=request.user.customer_profile)
        s = PreferenceInput(data=request.data)
        s.is_valid(raise_exception=True)
        for k, v in s.validated_data.items():
            setattr(p, k, [str(x) for x in v] if k == "airlines" else v)
        p.save()
        return Response(self._out(p))


class NextJourneyView(APIView):
    """GET /customer/travel/next — the customer's next confirmed or pending journey (none → null)."""

    permission_classes = [IsCustomer]

    def get(self, request):
        booking.sweep()
        b = _own(request).filter(status__in=ACTIVE, departs_at__gt=timezone.now()).order_by("departs_at").first()
        return Response({"booking": booking_out(b) if b else None})
