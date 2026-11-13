"""
Discovery, availability and pricing for Click. Services. Everything a customer sees as fact comes from records:
the professional's partner status and verification, base address and service radius, working hours, live
availability toggle, bookings (busy / free slots), prices, and counters maintained from completed jobs and reviews.
Arrival times are estimates from distance (no live tracking of professionals exists) and are labelled as such.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.partners.models import Partner, PartnerVerification
from apps.rides.pricing import haversine_km

from .models import (
    ACTIVE, ON_JOB, BookingStatus, ProviderProfile, ServiceBooking, ServiceCategory, ServiceJob, ServiceJobOffer,
    ServiceOffer,
)

DEFAULT_RADIUS_KM = 8
SLOT_LEAD = timedelta(minutes=90)
SLOT_DAYS = 7
PREP_MINUTES = 10
CITY_KMH = 18
ROAD = 1.3
TWO = Decimal("0.01")


def tz() -> ZoneInfo:
    return ZoneInfo(getattr(settings, "CLICK_LOCAL_TIMEZONE", "Asia/Kolkata"))


def local(now=None) -> datetime:
    return timezone.localtime(now or timezone.now(), tz())


def listed():
    return (ProviderProfile.objects.filter(is_listed=True, partner__status__in=[Partner.Status.VERIFIED, Partner.Status.ACTIVE])
            .select_related("partner", "partner__profile", "category").prefetch_related("services__category", "hours", "partner__addresses", "prices"))


def base(p: ProviderProfile):
    a = next((x for x in p.partner.addresses.all() if x.is_primary), None)
    if a is None or a.latitude is None:
        return None, DEFAULT_RADIUS_KM, ""
    return (float(a.latitude), float(a.longitude)), (a.service_radius_km or DEFAULT_RADIUS_KM), a.service_area or a.line2 or a.city


def distance(p: ProviderProfile, point) -> float | None:
    b, _, _ = base(p)
    if b is None or point is None:
        return None
    return round(haversine_km(b, point), 1)


def serves(p: ProviderProfile, point) -> bool:
    """Within the professional's service radius (unknown location = not claimed as serving)."""
    b, radius, _ = base(p)
    if point is None:
        return True
    return b is not None and haversine_km(b, point) <= radius


def verified(p: ProviderProfile) -> bool:
    return PartnerVerification.objects.filter(partner=p.partner, status=PartnerVerification.Status.APPROVED).exists()


def _windows(p: ProviderProfile, start: datetime, days: int):
    out = []
    for d in range(days + 1):
        day = (start + timedelta(days=d)).date()
        for h in p.hours.all():
            if h.weekday == day.weekday():
                out.append((datetime.combine(day, h.starts_at, tz()), datetime.combine(day, h.ends_at, tz())))
    return sorted(out)


def busy_now(p: ProviderProfile) -> bool:
    return ServiceBooking.objects.filter(provider=p, status__in=ON_JOB).exists()


def available_now(p: ProviderProfile, now=None) -> bool:
    now = local(now)
    if not (p.partner.is_available and p.instant_enabled):
        return False
    if not any(o <= now < c for o, c in _windows(p, now - timedelta(days=1), 1)):
        return False
    return not busy_now(p)


def _taken(p: ProviderProfile, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    rows = ServiceBooking.objects.filter(
        Q(provider=p) | Q(provider__isnull=True, job_offers__provider=p, job_offers__response="pending"),
        status__in=ACTIVE, scheduled_start__lt=end, scheduled_end__gt=start).values_list("scheduled_start", "scheduled_end")
    return [(a, b) for a, b in rows if a and b]


def slots(p: ProviderProfile, job: ServiceJob, now=None, days: int = SLOT_DAYS, limit: int = 60) -> list[dict]:
    """Start times inside working hours, from 90 minutes ahead, where the job fits and nothing else is booked."""
    now = local(now)
    dur = timedelta(minutes=job.duration_minutes)
    earliest = now + SLOT_LEAD
    taken = _taken(p, now, now + timedelta(days=days + 1))
    out = []
    for o, c in _windows(p, now, days):
        t = o
        while t + dur <= c:
            if t >= earliest and not any(a < t + dur and b > t for a, b in taken):
                day = "Today" if t.date() == now.date() else "Tomorrow" if t.date() == (now + timedelta(days=1)).date() else t.strftime("%a %d %b")
                out.append({"start": t.isoformat(), "end": (t + dur).isoformat(), "day": day, "label": t.strftime("%I:%M %p").lstrip("0")})
            t += timedelta(minutes=60)
        if len(out) >= limit:
            break
    return out[:limit]


def availability_label(p: ProviderProfile, job: ServiceJob | None, now=None) -> tuple[str, str]:
    """("now" | "today" | "tomorrow" | "later" | "none", label) from the real toggle, hours and bookings."""
    if available_now(p, now):
        return "now", "Available now"
    if job is None:
        job = ServiceJob(duration_minutes=60)
    s = slots(p, job, now, days=SLOT_DAYS, limit=1)
    if not s:
        return "none", "No free slots this week"
    first = s[0]
    if first["day"] == "Today":
        return "today", f"Available today, {first['label']}"
    if first["day"] == "Tomorrow":
        return "tomorrow", f"Available tomorrow, {first['label']}"
    return "later", f"Next: {first['day']}, {first['label']}"


def eta_minutes(km: float | None) -> int | None:
    if km is None:
        return None
    return int(math.ceil((km * ROAD / CITY_KMH * 60 + PREP_MINUTES) / 5) * 5)


def price_for(p: ProviderProfile | None, job: ServiceJob) -> Decimal | None:
    if job.pricing == ServiceJob.Pricing.QUOTE:
        return None
    if p is not None:
        own = next((x.price for x in p.prices.all() if x.job_id == job.id), None)  # prefetched by listed()
        if own:
            return own
    return job.price


def price_label(pricing: str, price: Decimal | None) -> str:
    if pricing == ServiceJob.Pricing.QUOTE or price is None:
        return "Quote after inspection"
    v = f"₹{price:,.0f}"
    return {ServiceJob.Pricing.FIXED: v, ServiceJob.Pricing.STARTING: f"From {v}", ServiceJob.Pricing.HOURLY: f"{v}/hour"}[pricing]


def from_price(p: ProviderProfile, category: ServiceCategory) -> Decimal | None:
    prices = [price_for(p, j) for j in category.jobs.all() if j.is_active and j.pricing != ServiceJob.Pricing.QUOTE]
    prices = [x for x in prices if x]
    return min(prices) if prices else None


def rates(p: ProviderProfile) -> dict:
    """Response and completion rates, only once there is enough history to mean something (5+)."""
    since = timezone.now() - timedelta(days=90)
    offers = ServiceJobOffer.objects.filter(provider=p, created_at__gte=since).exclude(response="pending")
    answered = offers.count()
    out = {}
    if answered >= 5:
        out["response_rate"] = round(100 * offers.filter(response="accepted").count() / answered)
    accepted = ServiceBooking.objects.filter(provider=p, accepted_at__gte=since)
    n = accepted.count()
    if n >= 5:
        out["completion_rate"] = round(100 * accepted.filter(status__in=[BookingStatus.COMPLETED, BookingStatus.PAID]).count() / n)
    return out


def photo_url(p: ProviderProfile, request=None) -> str:
    if not p.photo:
        return ""
    url = p.photo.url
    return request.build_absolute_uri(url) if request is not None else url


def name_of(p: ProviderProfile) -> str:
    return (getattr(p.partner.profile, "contact_name", "") if hasattr(p.partner, "profile") else "") or p.partner.business_name


def card(p: ProviderProfile, point=None, category: ServiceCategory | None = None, job: ServiceJob | None = None, now=None, request=None) -> dict:
    cat = category or p.category
    km = distance(p, point)
    avail, label = availability_label(p, job, now)
    if job is not None:
        price, pricing = price_for(p, job), job.pricing
    else:
        price, pricing = from_price(p, cat), ServiceJob.Pricing.STARTING
    return {
        "id": str(p.id), "name": name_of(p), "profession": p.category.profession, "photo_url": photo_url(p, request),
        "categories": [s.category.name for s in p.services.all()], "experience_years": p.experience_years,
        "rating": {"average": f"{p.rating_average:.1f}", "count": p.rating_count} if p.rating_count else None,
        "jobs_completed": p.jobs_completed, "verified": verified(p),
        "availability": avail, "availability_label": label,
        "distance_km": km, "eta_minutes": eta_minutes(km) if avail == "now" else None,
        "price": f"{price:.2f}" if price is not None else None, "pricing": pricing,
        "price_label": price_label(pricing, price) if job is not None or price is not None else "Quote after inspection",
        "languages": p.languages, "accent": cat.accent,
    }


def providers_for(category: ServiceCategory, point=None):
    """Listed professionals doing this category who serve the location (when one is given)."""
    rows = listed().filter(services__category=category).distinct()
    return [p for p in rows if serves(p, point)]


# --- offers -----------------------------------------------------------------------------------------------------------

def live_offers(category: ServiceCategory | None = None):
    now = timezone.now()
    qs = ServiceOffer.objects.filter(is_active=True).filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now),
                                                            Q(ends_at__isnull=True) | Q(ends_at__gte=now))
    if category is not None:
        qs = qs.filter(Q(category__isnull=True) | Q(category=category))
    return qs.select_related("category")


def best_offer(customer, category: ServiceCategory, amount: Decimal | None):
    """(offer, discount, problem) for the best live offer that applies to this customer and amount."""
    if amount is None:
        return None, Decimal("0"), ""
    first = customer is not None and not ServiceBooking.objects.filter(customer=customer, status=BookingStatus.PAID).exists()
    best, best_d = None, Decimal("0")
    for o in live_offers(category):
        if o.first_booking_only and not first:
            continue
        if amount < o.min_amount:
            continue
        d = (amount * o.value / 100).quantize(TWO, rounding=ROUND_HALF_UP) if o.kind == ServiceOffer.Kind.PERCENT else min(o.value, amount)
        if o.max_discount is not None:
            d = min(d, o.max_discount)
        if d > best_d:
            best, best_d = o, d
    return best, best_d, ""


def offer_card(o: ServiceOffer) -> dict:
    return {"id": str(o.id), "title": o.title, "description": o.description, "category": o.category.slug if o.category_id else None,
            "category_name": o.category.name if o.category_id else None, "first_booking_only": o.first_booking_only,
            "min_amount": f"{o.min_amount:.2f}" if o.min_amount else None, "ends_at": o.ends_at.isoformat() if o.ends_at else None}


# --- search -----------------------------------------------------------------------------------------------------------

def words(text: str) -> list[str]:
    stop = {"a", "an", "the", "my", "i", "need", "want", "get", "some", "someone", "please", "help", "with", "for", "to", "fix", "is",
            "are", "it", "me", "near", "find", "book", "service", "services", "at", "home", "in", "of", "and", "do", "can", "you"}
    return [w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in stop and len(w) > 1]


def _stem(w: str) -> str:
    return w[:-1] if w.endswith("s") and len(w) > 3 else w


def match_categories(text: str) -> list[tuple[ServiceCategory, int]]:
    ws = [_stem(w) for w in words(text)]
    out = []
    for c in ServiceCategory.objects.filter(is_active=True).prefetch_related("jobs"):
        vocab = " ".join([c.name, c.profession, c.slug.replace("-", " "), c.synonyms, *[j.name for j in c.jobs.all() if j.is_active]]).lower()
        score = sum(3 if re.search(rf"\b{re.escape(w)}", c.name.lower() + " " + c.profession.lower()) else 1 if w in vocab else 0 for w in ws)
        if score:
            out.append((c, score))
    return sorted(out, key=lambda x: (-x[1], x[0].position))


def match_jobs(text: str, limit: int = 8) -> list[ServiceJob]:
    ws = [_stem(w) for w in words(text)]
    jobs = ServiceJob.objects.filter(is_active=True, category__is_active=True).select_related("category")
    scored = []
    for j in jobs:
        hay = f"{j.name} {j.description} {j.category.synonyms}".lower()
        s = sum(2 if w in j.name.lower() else 1 if w in hay else 0 for w in ws)
        if s:
            scored.append((s, j))
    return [j for _, j in sorted(scored, key=lambda x: (-x[0], x[1].position))[:limit]]
