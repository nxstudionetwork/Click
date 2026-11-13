"""
Discover feed: organic sections from real Click. data, with a small number of clearly labelled sponsored cards chosen
by an auction.

Organic: near you (your city), trending (most orders this week), new on Click., because you ordered here / similar,
offers near you, this weekend (shows, places), hidden gems (great ratings, fewer orders). Each card says why it's
there in plain words; nothing is invented.

Auction, per sponsored slot:
    ad rank = max bid × relevance^wr × quality^wq × expected engagement^we
  eligible only if: campaign approved and live, partner verified and active, listing open/listed, in its cities / hours,
  under daily and total budget, under the per-customer frequency cap, not hidden by this customer,
  relevance ≥ min_relevance and quality ≥ min_quality. One advertiser at most once per feed.
Pricing: CPC and CPA are second-price (pay just enough to beat the next ad, never above the bid); CPM charges
bid/1000 per counted impression; flat charges its daily bid on the first impression of the day.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from decimal import ROUND_UP, Decimal

from django.conf import settings
from django.core import signing
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q, Sum
from django.utils import timezone

from .models import AdCampaign, AdEvent, AdHide, DiscoverConfig

SALT = "click.discover.serve"
SERVE_MAX_AGE = 24 * 3600
STORE_SERVICE = {"restaurant": "food", "grocery": "groceries", "retail": "shop", "pharmacy": "pharma"}


def viewer_key(request) -> str:
    u = request.user
    if u and u.is_authenticated and hasattr(u, "customer_profile"):
        return f"c:{u.customer_profile.id}"
    raw = f"{request.META.get('REMOTE_ADDR', '')}|{request.META.get('HTTP_USER_AGENT', '')[:120]}|{settings.SECRET_KEY[:16]}"
    return "a:" + hashlib.sha256(raw.encode()).hexdigest()[:40]


# --- cards from real listings ----------------------------------------------------------------------------------------

def _store_card(s, why=""):
    offer = next(iter(getattr(s, "active_offers", []) or []), None)
    retail = s.store_type == "retail"
    return {"type": "store", "id": str(s.id), "service": STORE_SERVICE.get(s.store_type, "shop"), "title": s.name,
            "subtitle": " · ".join(x for x in [", ".join(c.name for c in list(s.categories.all())[:2]), s.locality or s.city] if x),
            "image": s.image_url, "rating": f"{s.rating_average}" if s.rating_count else None, "rating_count": s.rating_count or None,
            "eta": None if retail else f"{s.delivery_time_min}–{s.delivery_time_max} min", "offer": offer.title if offer else None,
            "open": s.is_open, "link": f"/stores/{s.slug}", "cta": "Shop now" if retail else "Order now" if s.store_type == "restaurant" else "Shop groceries",
            "why": why, "city": s.city}


def _hotel_card(h, why=""):
    return {"type": "hotel", "id": str(h.id), "service": "hotels", "title": h.partner.business_name,
            "subtitle": f"{h.get_property_type_display()} · {h.area + ', ' if h.area else ''}{h.destination.name}", "image": "",
            "rating": f"{h.rating_average}" if h.rating_average else None, "rating_count": None, "eta": None, "offer": None, "open": True,
            "link": f"/hotels/{h.id}", "cta": "View stay", "why": why, "city": h.destination.name}


def _attraction_card(a, why=""):
    return {"type": "attraction", "id": str(a.id), "service": "bookings", "title": a.name, "subtitle": f"{a.get_kind_display()} · {a.city}",
            "image": "", "rating": f"{a.rating_average}" if a.rating_average else None, "rating_count": None, "eta": None, "offer": None, "open": True,
            "link": f"/bookings/places/{a.slug}", "cta": "See tickets", "why": why, "city": a.city}


def _event_provider_card(p, why=""):
    return {"type": "event_provider", "id": str(p.id), "service": "events", "title": p.partner.business_name, "subtitle": f"{p.get_kind_display()} · {p.city}",
            "image": "", "rating": f"{p.rating_average}" if p.rating_average else None, "rating_count": None, "eta": None, "offer": None, "open": True,
            "link": f"/events/providers/{p.id}", "cta": "View", "why": why, "city": p.city}


def _pro_card(p, why=""):
    return {"type": "professional", "id": str(p.id), "service": "services", "title": p.partner.business_name,
            "subtitle": f"{p.category.name} · {p.jobs_completed} jobs", "image": "", "rating": f"{p.rating_average}" if p.rating_count else None,
            "rating_count": p.rating_count or None, "eta": None, "offer": None, "open": True, "link": f"/services/pro/{p.id}", "cta": "Book",
            "why": why, "city": ""}


def target_card(c: AdCampaign) -> dict | None:
    """The live card for a campaign's own listing, or None when that listing isn't available to customers now."""
    t, pk = c.target_type, c.target_id
    if t == "store":
        from apps.stores.views import public_stores

        s = public_stores().filter(pk=pk, partner_link__partner=c.partner).first()
        return _store_card(s) if s and s.is_open else None
    if t == "hotel":
        from apps.hotels.models import HotelProperty

        h = HotelProperty.objects.filter(pk=pk, partner=c.partner, is_listed=True).select_related("partner", "destination").first()
        return _hotel_card(h) if h else None
    if t == "attraction":
        from apps.experiences.models import Attraction

        a = Attraction.objects.filter(pk=pk, is_listed=True).first()
        return _attraction_card(a) if a else None
    if t == "event_provider":
        from apps.eventhub.models import EventProvider

        p = EventProvider.objects.filter(pk=pk, partner=c.partner, is_listed=True).select_related("partner").first()
        return _event_provider_card(p) if p else None
    from apps.professionals.models import ProviderProfile

    p = ProviderProfile.objects.filter(pk=pk, partner=c.partner, is_listed=True).select_related("partner", "category").first()
    return _pro_card(p) if p else None


# --- organic sections ------------------------------------------------------------------------------------------------

def _city(customer, requested: str) -> str:
    if requested:
        return requested[:60]
    if customer:
        a = customer.addresses.order_by("-is_default", "-created_at").first()
        if a:
            return a.city
    return ""


def organic(customer, city: str, service: str = "") -> list[dict]:
    from apps.orders.models import Order
    from apps.stores.views import public_stores

    now = timezone.now()
    stores = public_stores().filter(is_accepting_orders=True)
    if city:
        stores = stores.filter(city__iexact=city)
    if service in ("food", "groceries", "shop"):
        stores = stores.filter(store_type={"food": "restaurant", "groceries": "grocery", "shop": "retail"}[service])
    stores = stores.prefetch_related("categories")
    sections = []

    def add(code, title, subtitle, cards):
        cards = [c for c in cards if c]
        if cards:
            sections.append({"code": code, "title": title, "subtitle": subtitle, "cards": cards[:10]})

    week = now - timedelta(days=7)
    trending = list(stores.annotate(n=Count("orders", filter=Q(orders__created_at__gte=week) & ~Q(orders__status="cancelled"))).filter(n__gte=2).order_by("-n")[:10])
    add("trending", "Trending now", "Most ordered this week", [_store_card(s, f"{s.n} orders this week") for s in trending])
    if customer:
        mine = list(Order.objects.filter(customer=customer).exclude(status="cancelled").values_list("store_id", flat=True)[:50])
        again = [s for s in stores.filter(pk__in=mine)][:8]
        add("again", "Because you ordered here", "Places you’ve liked before", [_store_card(s, "You ordered here before") for s in again])
        cats = set(stores.filter(pk__in=mine).values_list("categories__name", flat=True))
        similar = list(stores.filter(categories__name__in=[c for c in cats if c]).exclude(pk__in=mine).distinct().order_by("-rating_average")[:10])
        add("like", "Because you may like", "Similar to what you order", [_store_card(s, "Similar to places you order from") for s in similar])
    add("near", f"Discover near you{' in ' + city if city else ''}", "Highly rated and open now",
        [_store_card(s, "Popular near you") for s in stores.filter(rating_count__gte=3).order_by("-rating_average", "-rating_count")[:10]])
    add("new", "New on Click.", "Joined in the last 60 days",
        [_store_card(s, "New on Click.") for s in stores.filter(created_at__gte=now - timedelta(days=60)).order_by("-created_at")[:10]])
    gems = list(stores.filter(rating_average__gte=Decimal("4.5"), rating_count__gte=3).annotate(n=Count("orders")).filter(n__lte=15).order_by("-rating_average")[:8])
    add("gems", "Hidden gems", "Excellent ratings, fewer people know them yet", [_store_card(s, "Rated highly, still a local secret") for s in gems])
    offers = [s for s in stores.order_by("-rating_average")[:60] if getattr(s, "active_offers", None)][:10]
    add("offers", "Offers near you", "Live deals from places around you", [_store_card(s, "Has a live offer") for s in offers])
    if service in ("", "bookings"):
        from apps.experiences.models import Attraction

        qs = Attraction.objects.filter(is_listed=True)
        if city:
            qs = qs.filter(city__iexact=city)
        add("weekend", "This weekend", "Places and experiences you can book", [_attraction_card(a, "Bookable this weekend") for a in qs.order_by("-rating_average")[:10]])
    if service in ("", "hotels"):
        from apps.hotels.models import HotelProperty

        qs = HotelProperty.objects.filter(is_listed=True).select_related("partner", "destination")
        if city:
            qs = qs.filter(destination__name__iexact=city)
        add("stays", "Stays worth a look", "Top-rated hotels", [_hotel_card(h, "Highly rated stay") for h in qs.order_by("-rating_average")[:8]])
    return sections


# --- auction -----------------------------------------------------------------------------------------------------------

def _quality(card: dict) -> float:
    r = float(card["rating"]) if card.get("rating") else None
    if r is None:
        return 0.8  # new listings: neutral until they have reviews
    scale = 10 if card["type"] == "hotel" else 5
    return max(0.0, min(1.0, r / scale))


def _engagement(c: AdCampaign) -> float:
    agg = c.events.filter(created_at__gte=timezone.now() - timedelta(days=30)).aggregate(
        i=Count("id", filter=Q(kind="impression")), k=Count("id", filter=Q(kind="click")))
    return (agg["k"] + 1) / (agg["i"] + 20) / 0.05  # smoothed CTR relative to a 5% baseline


def _relevance(c: AdCampaign, card: dict, service: str, city: str) -> float:
    r = 1.0
    if service and c.services and service not in c.services:
        return 0.0
    if service and card["service"] != service and not c.services:
        r *= 0.5
    if city and card.get("city"):
        r *= 1.0 if card["city"].lower() == city.lower() else 0.3
    return r


def _spent_today(c: AdCampaign) -> Decimal:
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return c.events.filter(created_at__gte=start).aggregate(s=Sum("cost"))["s"] or Decimal("0")


def auction(customer, viewer: str, *, service: str, city: str, placement: str, slots: int) -> list[dict]:
    cfg = DiscoverConfig.current()
    now = timezone.now()
    hour = timezone.localtime().hour
    hidden = set(AdHide.objects.filter(customer=customer).values_list("campaign_id", flat=True)) if customer else set()
    day = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    qs = (AdCampaign.objects.filter(status=AdCampaign.Status.ACTIVE, starts_at__lte=now, ends_at__gt=now, spent__lt=F("total_budget"))
          .filter(partner__status__in=["verified", "active"], partner__partner_code__isnull=False).exclude(pk__in=hidden).select_related("partner"))
    if placement in ("feed", "top", "category"):
        qs = qs.filter(placement__in=["feed", "top", "category", "launch", "offer"])
    else:
        qs = qs.filter(placement=placement)
    bids = []
    for c in qs[:100]:
        if c.hours and hour not in c.hours:
            continue
        if c.cities and city and city.lower() not in [x.lower() for x in c.cities]:
            continue
        if _spent_today(c) >= c.daily_budget:
            continue
        if c.events.filter(viewer=viewer, kind="impression", created_at__gte=day).count() >= c.frequency_cap:
            continue
        card = target_card(c)
        if card is None:
            continue
        rel, q = _relevance(c, card, service, city), _quality(card)
        if rel < float(cfg.min_relevance) or q < float(cfg.min_quality):
            continue
        eng = _engagement(c)
        factor = (rel ** float(cfg.weight_relevance)) * (q ** float(cfg.weight_quality)) * (eng ** float(cfg.weight_engagement))
        bids.append((float(c.max_bid) * factor, factor, c, card))
    bids.sort(key=lambda b: -b[0])
    out, seen = [], set()
    for i, (rank, factor, c, card) in enumerate(bids):
        if c.partner_id in seen or len(out) >= slots:
            continue
        seen.add(c.partner_id)
        nxt = next((b for b in bids[i + 1:] if b[2].partner_id != c.partner_id), None)
        price = Decimal(str(nxt[0] / factor)).quantize(Decimal("0.01"), rounding=ROUND_UP) + Decimal("0.01") if nxt else Decimal("1.00")
        price = min(price, c.max_bid)
        serve = secrets.token_hex(10)
        token = signing.dumps({"c": str(c.id), "s": serve, "v": viewer, "p": placement, "price": str(price)}, salt=SALT)
        out.append({**card, "sponsored": True, "campaign": str(c.id), "advertiser": c.partner.business_name, "headline": c.headline,
                    "token": token, "why": f"Sponsored by {c.partner.business_name}. Shown because it matches "
                                           f"{(service or 'what’s around you')}{' in ' + city if city else ''}. Ads never use your orders or searches."})
    return out


def feed(customer, viewer: str, *, city: str = "", service: str = "") -> dict:
    city = _city(customer, city)
    sections = organic(customer, city, service)
    cfg = DiscoverConfig.current()
    total = sum(len(s["cards"]) for s in sections)
    slots = min(cfg.max_sponsored, int(total * float(cfg.max_share)) or (1 if total >= cfg.min_gap else 0))
    ads = auction(customer, viewer, service=service, city=city, placement="feed", slots=slots)
    # Interleave: at most one sponsored card per section, never before `min_gap` organic cards, never two in a row.
    for s in sections:
        if not ads:
            break
        if s["code"] in ("again", "like"):  # never inside sections about the customer's own history
            continue
        if len(s["cards"]) >= cfg.min_gap:
            s["cards"].insert(min(cfg.min_gap, len(s["cards"])) - 1 if s["code"] != "trending" else min(2, len(s["cards"])), ads.pop(0))
    return {"city": city, "service": service, "sections": sections}


# --- tracking ----------------------------------------------------------------------------------------------------------

def track(token: str, kind: str, viewer: str) -> bool:
    """Count one impression / click of a served sponsored card and charge the campaign. Invalid, expired, foreign or
    repeated tokens are ignored (no charge)."""
    try:
        d = signing.loads(token, salt=SALT, max_age=SERVE_MAX_AGE)
    except signing.BadSignature:
        return False
    if d.get("v") != viewer or kind not in ("impression", "click"):
        return False
    c = AdCampaign.objects.filter(pk=d["c"]).first()
    if c is None:
        return False
    cost = Decimal("0")
    if kind == "click" and c.pricing == AdCampaign.Pricing.CPC:
        cost = Decimal(d["price"])
    elif kind == "impression" and c.pricing == AdCampaign.Pricing.CPM:
        cost = (c.max_bid / 1000).quantize(Decimal("0.0001"))
    elif kind == "impression" and c.pricing == AdCampaign.Pricing.FLAT:
        start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        cost = c.max_bid if not c.events.filter(kind="impression", created_at__gte=start).exists() else Decimal("0")
    if kind == "click" and not AdEvent.objects.filter(serve_id=d["s"], kind="impression").exists():
        return False  # a click must follow a counted impression of the same serve
    try:
        with transaction.atomic():
            c = AdCampaign.objects.select_for_update().get(pk=c.pk)
            cost = min(cost, max(Decimal("0"), c.total_budget - c.spent))
            AdEvent.objects.create(campaign=c, kind=kind, serve_id=d["s"], viewer=viewer, placement=d.get("p", ""), cost=cost)
            if cost:
                c.spent = c.spent + cost
                if c.spent >= c.total_budget:
                    c.status, c.status_reason = AdCampaign.Status.ENDED, "Budget used"
                c.save(update_fields=["spent", "status", "status_reason", "updated_at"])
    except IntegrityError:
        return False
    return True


def attribute_order(order) -> None:
    """CPA: an order at a store within 7 days of the customer clicking its ad counts as one conversion (charged once)."""
    viewer = f"c:{order.customer_id}"
    since = timezone.now() - timedelta(days=7)
    click = (AdEvent.objects.filter(viewer=viewer, kind="click", created_at__gte=since, campaign__target_type="store", campaign__target_id=order.store_id)
             .select_related("campaign").order_by("-created_at").first())
    if not click:
        return
    c = click.campaign
    cost = c.max_bid if c.pricing == AdCampaign.Pricing.CPA else Decimal("0")
    try:
        with transaction.atomic():
            c = AdCampaign.objects.select_for_update().get(pk=c.pk)
            cost = min(cost, max(Decimal("0"), c.total_budget - c.spent))
            AdEvent.objects.create(campaign=c, kind="conversion", serve_id=click.serve_id, viewer=viewer, placement=click.placement, cost=cost)
            if cost:
                AdCampaign.objects.filter(pk=c.pk).update(spent=F("spent") + cost)
    except IntegrityError:
        pass
