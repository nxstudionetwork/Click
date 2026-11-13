"""
Discovery, availability, pricing and search for Click. Events. What a customer sees as fact comes from records:

  verified        an approved PartnerVerification for the provider's partner
  available       the provider's blocked dates, minimum notice and events-per-day capacity against real bookings
  ratings / counts recomputed from completed bookings and published reviews (lifecycle.recompute)
  response time   the median time to first quote, shown only with 3+ answered enquiries
  distance        straight-line km from the customer's saved address pin, when both have coordinates
  attend events   Click. Showtime's live events with bookable shows (apps.bookings), linked, never copied
"""

from __future__ import annotations

import re
import statistics
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Count, Min, Q
from django.utils import timezone

from apps.partners.models import Partner, PartnerVerification
from apps.rides.pricing import haversine_km

from .models import ACTIVE, Enquiry, EventBooking, EventPackage, EventProvider, EventService, EventType

TWO = Decimal("0.01")
TAX_RATE = Decimal(str(getattr(settings, "CLICK_EVENTS_TAX_RATE", "0.18")))
OPERATING = (Partner.Status.ACTIVE, Partner.Status.VERIFIED)
GUEST_BANDS = [("u20", "Under 20", 1, 19), ("20-50", "20–50", 20, 50), ("50-100", "50–100", 51, 100), ("100-250", "100–250", 101, 250),
               ("250-500", "250–500", 251, 500), ("500+", "500+", 501, 100000)]


def money(x) -> Decimal:
    return Decimal(x).quantize(TWO, rounding=ROUND_HALF_UP)


def today() -> date:
    return timezone.now().astimezone(ZoneInfo(settings.TIME_ZONE)).date()


def listed():
    return (EventProvider.objects.filter(is_listed=True, partner__status__in=OPERATING)
            .select_related("partner__profile", "venue").prefetch_related("services", "event_types", "packages__services"))


def name_of(p: EventProvider) -> str:
    return p.partner.business_name


def verified(p: EventProvider) -> bool:
    if not hasattr(p, "_verified"):
        p._verified = PartnerVerification.objects.filter(partner=p.partner, status=PartnerVerification.Status.APPROVED).exists()
    return p._verified


def distance(p: EventProvider, point) -> float | None:
    if point is None or p.latitude is None:
        return None
    return round(haversine_km((float(p.latitude), float(p.longitude)), point), 1)


def serves(p: EventProvider, point) -> bool:
    km = distance(p, point)
    return km is None or km <= p.service_radius_km


def capacity_ok(p: EventProvider, guests: int | None) -> bool:
    if not guests:
        return True
    if p.kind == EventProvider.Kind.VENUE and hasattr(p, "venue"):
        return guests <= max(p.venue.floating_capacity, p.venue.seated_capacity)
    return (p.min_guests or 0) <= guests <= (p.max_guests or 10 ** 6)


def availability(p: EventProvider, day: date | None) -> dict | None:
    """{"state": "available" | "booked" | "unavailable" | "too_soon", "label"} for a date, from real records only."""
    if day is None:
        return None
    if day < today() + timedelta(days=p.min_notice_days):
        return {"state": "too_soon", "label": f"Needs {p.min_notice_days} days’ notice"}
    if p.blocked_dates.filter(date=day).exists():
        return {"state": "unavailable", "label": "Not available that day"}
    taken = EventBooking.objects.filter(provider=p, event_date=day, status__in=ACTIVE).count()
    if taken >= p.max_events_per_day:
        return {"state": "booked", "label": "Fully booked that day"}
    return {"state": "available", "label": f"Available {day.strftime('%a %d %b').replace(' 0', ' ')}"}


def response_hours(p: EventProvider) -> float | None:
    rows = list(Enquiry.objects.filter(provider=p, first_response_at__isnull=False).values_list("created_at", "first_response_at")[:50])
    if len(rows) < 3:
        return None
    return round(statistics.median((b - a).total_seconds() / 3600 for a, b in rows), 1)


def response_label(hours: float | None) -> str:
    if hours is None:
        return ""
    if hours < 1:
        return "Usually quotes within an hour"
    if hours < 24:
        return f"Usually quotes within {int(hours + 0.99)} hours"
    return f"Usually quotes within {int(hours / 24 + 0.99)} days"


# --- prices ----------------------------------------------------------------------------------------------------------

def package_amount(pkg: EventPackage, guests: int) -> Decimal:
    return money(pkg.price * guests if pkg.basis == EventPackage.Basis.PER_GUEST else pkg.price)


def package_label(pkg: EventPackage) -> str:
    return f"₹{pkg.price:,.0f} per guest" if pkg.basis == EventPackage.Basis.PER_GUEST else f"₹{pkg.price:,.0f}"


def price_from(p: EventProvider) -> dict | None:
    """The lowest active package, as {"amount", "label"} (per-guest packages say so). None: quote only."""
    pkgs = [x for x in p.packages.all() if x.is_active]
    if not pkgs:
        return None
    fixed = [x for x in pkgs if x.basis == EventPackage.Basis.FIXED]
    best = min(fixed, key=lambda x: x.price) if fixed else min(pkgs, key=lambda x: x.price)
    return {"amount": f"{best.price:.2f}", "label": f"From {package_label(best)}"}


def tax_on(amount: Decimal) -> Decimal:
    return money(amount * TAX_RATE)


# --- cards -----------------------------------------------------------------------------------------------------------

def logo_url(p: EventProvider, request=None) -> str:
    if not p.logo:
        return ""
    return request.build_absolute_uri(p.logo.url) if request is not None else p.logo.url


def cover_url(p: EventProvider, request=None) -> str:
    from django.core.files.storage import default_storage

    path = (p.cover or {}).get("960") or (p.cover or {}).get("320")
    if not path:
        return ""
    url = default_storage.url(path)
    return request.build_absolute_uri(url) if request is not None else url


def service_out(s: EventService) -> dict:
    return {"slug": s.slug, "name": s.name, "icon": s.icon, "group": s.group}


def type_out(t: EventType) -> dict:
    return {"slug": t.slug, "name": t.name, "icon": t.icon, "accent": t.accent, "summary": t.summary, "group": t.group,
            "suggested_services": t.suggested_services}


def card(p: EventProvider, point=None, day: date | None = None, guests: int | None = None, request=None) -> dict:
    venue = getattr(p, "venue", None) if p.kind == EventProvider.Kind.VENUE else None
    return {
        "id": str(p.id), "name": name_of(p), "kind": p.kind, "kind_label": p.get_kind_display(), "tagline": p.tagline, "accent": p.accent,
        "logo_url": logo_url(p, request), "cover_url": cover_url(p, request), "verified": verified(p), "featured": p.is_featured,
        "rating": {"average": f"{p.rating_average:.1f}", "count": p.rating_count} if p.rating_count else None,
        "events_completed": p.events_completed, "experience_years": p.experience_years, "team_size": p.team_size,
        "area": p.area, "city": p.city, "service_radius_km": p.service_radius_km, "distance_km": distance(p, point),
        "services": [service_out(s) for s in p.services.all()], "event_types": [t.name for t in p.event_types.all()],
        "price_from": price_from(p), "response": response_label(response_hours(p)),
        "availability": availability(p, day), "capacity_ok": capacity_ok(p, guests) if guests else None,
        "venue": {"space_type": venue.space_type, "seated": venue.seated_capacity, "floating": venue.floating_capacity,
                  "amenities": venue.amenities[:4], "indoor": venue.indoor, "outdoor": venue.outdoor} if venue else None,
    }


def package_out(pkg: EventPackage, guests: int | None = None, with_provider: bool = False, point=None, request=None) -> dict:
    out = {
        "id": str(pkg.id), "name": pkg.name, "description": pkg.description, "includes": pkg.includes, "basis": pkg.basis,
        "price": f"{pkg.price:.2f}", "price_label": package_label(pkg), "min_guests": pkg.min_guests, "max_guests": pkg.max_guests,
        "duration_hours": float(pkg.duration_hours), "terms": pkg.terms, "services": [service_out(s) for s in pkg.services.all()],
        "event_types": [t.slug for t in pkg.event_types.all()],
        "addons": [{"id": str(a.id), "name": a.name, "price": f"{a.price:.2f}", "per_guest": a.per_guest} for a in pkg.addons.all()],
        "estimate": f"{package_amount(pkg, guests):.2f}" if guests and pkg.min_guests <= guests <= pkg.max_guests else None,
    }
    if with_provider:
        p = pkg.provider
        out["provider"] = {"id": str(p.id), "name": name_of(p), "kind": p.kind, "verified": verified(p), "accent": p.accent,
                           "logo_url": logo_url(p, request), "distance_km": distance(p, point),
                           "rating": {"average": f"{p.rating_average:.1f}", "count": p.rating_count} if p.rating_count else None}
    return out


# --- filtering -------------------------------------------------------------------------------------------------------

SORTS = {
    "recommended": lambda c: (not c["featured"], -(float(c["rating"]["average"]) if c["rating"] else 0) - min(c["events_completed"], 200) / 100),
    "rating": lambda c: (-(float(c["rating"]["average"]) if c["rating"] else 0), -(c["rating"]["count"] if c["rating"] else 0)),
    "nearest": lambda c: (c["distance_km"] is None, c["distance_km"] or 0),
    "price": lambda c: (c["price_from"] is None, float(c["price_from"]["amount"]) if c["price_from"] else 0),
    "experience": lambda c: (-(c["experience_years"] or 0),),
}


def search_providers(params, point=None, request=None) -> list[dict]:
    """Every filter here changes the result: kind, event type, service, date availability, guests (capacity), budget
    (lowest package within it), rating, verified, distance; then a sort."""
    qs = listed()
    kind = params.get("kind")
    if kind in EventProvider.Kind.values:
        qs = qs.filter(kind=kind)
    if params.get("type"):
        qs = qs.filter(Q(event_types__slug=params["type"]) | Q(event_types__isnull=True))
    if params.get("service"):
        qs = qs.filter(services__slug__in=params["service"].split(","))
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(partner__business_name__icontains=q) | Q(tagline__icontains=q) | Q(services__name__icontains=q) | Q(area__icontains=q))
    try:
        day = date.fromisoformat(params["date"]) if params.get("date") else None
    except ValueError:
        day = None
    try:
        guests = int(params["guests"]) if params.get("guests") else None
    except ValueError:
        guests = None
    out = []
    for p in qs.distinct():
        if not serves(p, point):
            continue
        c = card(p, point, day, guests, request)
        if guests and not c["capacity_ok"]:
            continue
        if day and params.get("available") == "true" and c["availability"]["state"] != "available":
            continue
        if params.get("verified") == "true" and not c["verified"]:
            continue
        try:
            if params.get("min_rating") and not (c["rating"] and float(c["rating"]["average"]) >= float(params["min_rating"])):
                continue
            if params.get("max_budget") and not (c["price_from"] and float(c["price_from"]["amount"]) <= float(params["max_budget"])):
                continue
            if params.get("max_km") and point is not None and (c["distance_km"] is None or c["distance_km"] > float(params["max_km"])):
                continue
        except ValueError:
            pass
        out.append(c)
    sort = params.get("sort") if params.get("sort") in SORTS else "recommended"
    return sorted(out, key=SORTS[sort])


# --- attend: Click. Showtime live events -----------------------------------------------------------------------------

def live_events(point=None, limit: int = 12, q: str = "") -> list[dict]:
    from apps.bookings import services as showtime
    from apps.bookings.models import Event
    from apps.bookings.views import public_events

    qs = public_events().filter(kind=Event.Kind.EVENT, next_show_at__isnull=False)
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(genres__icontains=q) | Q(tagline__icontains=q))
    out = []
    for e in qs.order_by("next_show_at")[:limit]:
        shows = showtime.bookable_shows().filter(event=e).select_related("venue").order_by("starts_at")
        first = shows.first()
        if first is None:
            continue
        price = shows.aggregate(m=Min("price"))["m"]
        v = first.venue
        km = round(haversine_km((float(v.latitude), float(v.longitude)), point), 1) if point and v.latitude is not None else None
        out.append({"slug": e.slug, "title": e.title, "tagline": e.tagline, "category": (e.genres.split(",")[0].strip() if e.genres else "Live event"),
                    "image_url": e.poster_url, "starts_at": first.starts_at.isoformat(), "shows": shows.count(),
                    "venue": v.name, "area": v.locality or v.city, "distance_km": km,
                    "price_from": f"{price:.2f}" if price is not None else None, "path": f"/showtime/{e.slug}",
                    "rating": {"average": f"{e.rating_average:.1f}", "count": e.rating_count} if e.rating_count else None})
    return out


# --- words -----------------------------------------------------------------------------------------------------------

def words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 1]


def _hit(text: str, names: list[str]) -> bool:
    t = f" {' '.join(words(text))} "
    return any(f" {' '.join(words(n))} " in t or (len(n) > 4 and n.lower()[:-1] in t) for n in names if n)


def match_types(text: str) -> list[EventType]:
    return [t for t in EventType.objects.filter(is_active=True) if _hit(text, [t.name, t.slug.replace("-", " "), *t.synonyms])]


def match_services(text: str) -> list[EventService]:
    return [s for s in EventService.objects.filter(is_active=True) if _hit(text, [s.name, s.slug.replace("-", " "), *s.synonyms])]


def popular_types(limit: int = 12):
    return EventType.objects.filter(is_active=True).annotate(n=Count("plans")).order_by("position")[:limit]
