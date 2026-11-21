"""
Hotel search and room offers. `ClickInventory` serves Click.'s own (partner-managed) inventory; an external
hotel-inventory provider would implement the same two methods (`search`, `rooms`) and be selected with
CLICK_HOTEL_INVENTORY — none is connected today, and nothing here pretends one is.

Filters are applied on the server and each one changes the result: price (cheapest bookable stay per night), property
type, star rating, guest rating, amenities (all of them), room class, free cancellation, pay at property, breakfast,
distance from a landmark. Sorts: recommended (documented score), price ↑/↓, guest rating, distance, stars, best value.

Highlights are rules on real data, shown only when they hold:
  Top rated            rating ≥ 8.5 from 5+ verified stays
  Best value           the best rating-per-₹ in this result set (rating from 3+ stays)
  Great for families   lists families and has a family room (or room for the party) free for these dates
  Good for business    lists business travellers and has Wi-Fi
  Free cancellation    the cheapest bookable rate is refundable with a free window
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db.models import Prefetch, Q
from django.utils.module_loading import import_string

from . import engine
from .models import Amenity, Destination, HotelProperty, Landmark, RatePlan, RoomType

PAGE = 10
SORTS = ("recommended", "price_asc", "price_desc", "rating", "distance", "stars", "value")


def properties():
    return (HotelProperty.objects.filter(is_listed=True, partner__status__in=["active", "verified"])
            .select_related("destination", "partner")
            .prefetch_related("amenities", Prefetch("rooms", queryset=RoomType.objects.filter(is_active=True).prefetch_related(
                Prefetch("rates", queryset=RatePlan.objects.filter(is_active=True)), "amenities")), "images"))


def resolve_destination(q: str) -> tuple[Destination | None, Landmark | None]:
    """A typed destination → a real Destination (or a landmark in one). Never a made-up place."""
    q = (q or "").strip().lower()
    if not q:
        return None, None
    for d in Destination.objects.filter(is_active=True):
        if q in (d.slug, d.name.lower()) or q in [s.lower() for s in d.synonyms]:
            return d, None
    lm = Landmark.objects.filter(name__icontains=q).select_related("destination").first()
    if lm:
        return lm.destination, lm
    d = Destination.objects.filter(Q(name__icontains=q) | Q(region__icontains=q), is_active=True).first()
    return d, None


def centre_of(dest: Destination):
    c = dest.landmarks.filter(kind=Landmark.Kind.CENTRE).first()
    return (float(c.latitude), float(c.longitude)) if c else (float(dest.latitude), float(dest.longitude))


def image_url(prop: HotelProperty, request=None, room: RoomType | None = None) -> str:
    from apps.professionals import media

    imgs = [i for i in prop.images.all() if (room is None or i.room_type_id == room.id)]
    if not imgs:
        return ""
    return media.urls(imgs[0], request)["src"]


class ClickInventory:
    """Click.'s own inventory: properties listed by hotel partners on Click."""

    def best_offer_for(self, prop: HotelProperty, ci: date, co: date, rooms: int, adults: int, children: int, need: dict):
        best = None
        family_free = False
        for room in prop.rooms.all():
            if need.get("room_class") and room.room_class not in need["room_class"]:
                continue
            for rate in room.rates.all():
                if need.get("breakfast") and rate.meal_plan == RatePlan.Meal.ROOM_ONLY:
                    continue
                if need.get("free_cancellation") and not (rate.refundable and rate.free_cancel_days is not None):
                    continue
                if need.get("pay_at_property") and rate.payment == RatePlan.Payment.PAY_NOW:
                    continue
                q = engine.quote(rate, ci, co, rooms, adults, children)
                if q.problem:
                    continue
                if room.room_class == RoomType.RoomClass.FAMILY or (children and room.max_children):
                    family_free = True
                if best is None or q.total < best.total:
                    best = q
        return best, family_free

    def search(self, params: dict, request=None) -> dict:
        ci, co = params["check_in"], params["check_out"]
        rooms, adults, children = params["rooms"], params["adults"], params["children"]
        dest, landmark = resolve_destination(params.get("destination") or "")
        if dest is None:
            return {"destination": None, "count": 0, "results": [], "page": 1, "has_more": False}
        qs = properties().filter(Q(destination=dest) | Q(destination__parent=dest))
        if params.get("type"):
            qs = qs.filter(property_type__in=params["type"])
        if params.get("stars"):
            qs = qs.filter(star_rating__in=params["stars"])
        for slug in params.get("amenities") or []:
            qs = qs.filter(amenities__slug=slug)
        if params.get("min_rating"):
            qs = qs.filter(rating_average__gte=params["min_rating"], rating_count__gt=0)
        near = None
        if params.get("near"):
            near = Landmark.objects.filter(pk=params["near"], destination__in=[dest, *dest.areas.all()]).first()
        near = near or landmark
        point = (float(near.latitude), float(near.longitude)) if near else centre_of(dest)
        point_label = near.name if near else f"{dest.name} centre"
        need = {k: params.get(k) for k in ("room_class", "breakfast", "free_cancellation", "pay_at_property")}
        nights = (co - ci).days
        cards = []
        for p in qs.distinct():
            q, family_free = self.best_offer_for(p, ci, co, rooms, adults, children, need)
            if q is None:
                continue
            per_night = q.total / nights / rooms
            if params.get("min_price") is not None and per_night < params["min_price"]:
                continue
            if params.get("max_price") is not None and per_night > params["max_price"]:
                continue
            km = engine.distance_km(p, point)
            if params.get("max_km") is not None and km is not None and km > params["max_km"]:
                continue
            cards.append(self.card(p, q, km, point_label, family_free, request, nights, rooms))
        rated = [c for c in cards if c["rating"] and c["rating"]["count"] >= 3]
        if rated:
            best = max(rated, key=lambda c: float(c["rating"]["average"]) / float(c["price"]["per_night"]))
            best["highlights"].insert(0, "Best value")
            for c in cards:
                c["_value"] = (float(c["rating"]["average"]) / float(c["price"]["per_night"])) if c["rating"] else 0
        sort = params.get("sort") if params.get("sort") in SORTS else "recommended"
        key = {
            # Recommended: verified-stay rating (shrunk towards 7 for few reviews) + small bonuses for flexibility and
            # breakfast, minus a distance penalty. Published here so the label isn't a black box.
            "recommended": lambda c: -(((float(c["rating"]["average"]) * c["rating"]["count"] + 7 * 5) / (c["rating"]["count"] + 5)) if c["rating"] else 6.5)
                                     - (0.4 if c["free_cancellation"] else 0) - (0.2 if c["breakfast"] else 0) + ((c["distance_km"] or 0) / 25),
            "price_asc": lambda c: float(c["price"]["total"]),
            "price_desc": lambda c: -float(c["price"]["total"]),
            "rating": lambda c: (-(float(c["rating"]["average"]) if c["rating"] else 0), -(c["rating"]["count"] if c["rating"] else 0)),
            "distance": lambda c: (c["distance_km"] is None, c["distance_km"] or 0),
            "stars": lambda c: (-(c["star_rating"] or 0), float(c["price"]["total"])),
            "value": lambda c: -c.get("_value", 0),
        }[sort]
        cards.sort(key=key)
        for c in cards:
            c.pop("_value", None)
        page = max(1, int(params.get("page") or 1))
        return {"destination": {"slug": dest.slug, "name": dest.name, "region": dest.region}, "measured_from": point_label,
                "count": len(cards), "page": page, "has_more": page * PAGE < len(cards), "results": cards[(page - 1) * PAGE: page * PAGE]}

    def card(self, p: HotelProperty, q, km, point_label, family_free, request, nights, rooms) -> dict:
        amen = list(p.amenities.all())
        slugs = {a.slug for a in amen}
        highlights = []
        if p.rating_count >= 5 and p.rating_average >= Decimal("8.5"):
            highlights.append("Top rated")
        if "family" in p.good_for and family_free:
            highlights.append("Great for families")
        if "business" in p.good_for and "wifi" in slugs:
            highlights.append("Good for business")
        free_cancel = q.rate.refundable and q.cancel_until is not None
        return {
            "id": str(p.id), "name": p.partner.business_name, "type": p.property_type, "type_label": p.get_property_type_display(),
            "star_rating": p.star_rating, "tagline": p.tagline, "area": p.area, "destination": p.destination.name, "accent": p.accent,
            "image_url": image_url(p, request), "photos": p.images.count(),
            "rating": {"average": f"{p.rating_average:.1f}", "count": p.rating_count, "label": engine.rating_label(p.rating_average, p.rating_count)} if p.rating_count else None,
            "distance_km": km, "distance_from": point_label, "amenities": [{"slug": a.slug, "name": a.name, "icon": a.icon} for a in amen[:5]],
            "room": q.room.name, "rooms_left": q.free if q.free <= 3 else None, "meal_label": q.rate.get_meal_plan_display(),
            "breakfast": q.rate.meal_plan != RatePlan.Meal.ROOM_ONLY, "free_cancellation": free_cancel,
            "cancellation": engine.policy_text(q.rate.refundable, q.cancel_until, q.rate.cancel_fee_percent),
            "pay_at_property": q.rate.payment != RatePlan.Payment.PAY_NOW, "offer": q.offer.title if q.offer else None,
            "price": {"per_night": f"{engine.money((q.room_total - q.discount) / nights / rooms):.2f}", "total": f"{q.total:.2f}",
                      "tax": f"{q.tax:.2f}", "before_discount": f"{q.room_total:.2f}" if q.discount else None, "nights": nights, "rooms": rooms},
            "highlights": highlights + (["Free cancellation"] if free_cancel else []),
        }

    def rooms(self, p: HotelProperty, ci: date, co: date, rooms: int, adults: int, children: int, request=None) -> list[dict]:
        out = []
        for room in p.rooms.all():
            quotes = [engine.quote(rate, ci, co, rooms, adults, children) for rate in room.rates.all()]
            out.append({
                "id": str(room.id), "name": room.name, "room_class": room.room_class, "room_class_label": room.get_room_class_display(),
                "beds": room.beds, "max_adults": room.max_adults, "max_children": room.max_children, "max_occupancy": room.max_occupancy,
                "size_sqm": room.size_sqm, "view": room.view, "description": room.description, "image_url": image_url(p, request, room),
                "amenities": [{"slug": a.slug, "name": a.name, "icon": a.icon} for a in room.amenities.all()],
                "fits": engine.fits(room, rooms, adults, children), "rates": [q.as_dict() for q in sorted(quotes, key=lambda q: q.total)],
            })
        out.sort(key=lambda r: (not r["fits"], min((float(x["total"]) for x in r["rates"] if not x["problem"]), default=1e12)))
        return out


def inventory():
    path = getattr(settings, "CLICK_HOTEL_INVENTORY", "") or "apps.hotels.search.ClickInventory"
    return import_string(path)()


def filters_meta() -> dict:
    return {"types": [{"value": v, "label": l} for v, l in HotelProperty.Type.choices],
            "amenities": [{"slug": a.slug, "name": a.name, "icon": a.icon} for a in Amenity.objects.filter(filterable=True, scope__in=["property", "both"])],
            "room_classes": [{"value": v, "label": l} for v, l in RoomType.RoomClass.choices],
            "sorts": [{"value": "recommended", "label": "Recommended"}, {"value": "price_asc", "label": "Price: low to high"},
                      {"value": "price_desc", "label": "Price: high to low"}, {"value": "rating", "label": "Guest rating"},
                      {"value": "distance", "label": "Distance"}, {"value": "stars", "label": "Star rating"}, {"value": "value", "label": "Best value"}],
            "guest_ratings": [{"value": 9, "label": "Exceptional 9+"}, {"value": 8.5, "label": "Excellent 8.5+"}, {"value": 8, "label": "Very good 8+"},
                              {"value": 7, "label": "Good 7+"}]}
