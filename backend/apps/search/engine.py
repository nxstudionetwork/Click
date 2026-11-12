"""
Click. Global Search: one engine, one provider per domain, one result shape.

Every provider reads that domain's own public records (only what customers may see) with indexed PostgreSQL
queries. Results are ranked by a simple, explainable relevance score (exact > prefix > word > contains, plus small
boosts for rating / availability) and grouped. The same engine serves the search page, suggestions, Discover and
Buddy, so there is no second search system. A dedicated search engine can replace `_match` later without changing
the API.

Result: {type, id, title, subtitle, image, link, service, group, rating, price, badge, score}
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from django.db.models import Q

GROUPS = [("food", "Food"), ("groceries", "Groceries"), ("products", "Products"), ("stores", "Stores"), ("hotels", "Hotels"),
          ("travel", "Travel"), ("bookings", "Places & experiences"), ("shows", "Shows"), ("events", "Events"),
          ("services", "Services"), ("pharma", "Pharma"), ("offers", "Offers"), ("gift_cards", "Gift Cards"), ("help", "Help")]
GROUP_LABEL = dict(GROUPS)


@dataclass
class Hit:
    type: str
    id: str
    title: str
    subtitle: str
    link: str
    group: str
    service: str
    image: str = ""
    rating: str | None = None
    price: str | None = None
    badge: str = ""
    score: float = 0.0
    meta: dict = field(default_factory=dict)

    def out(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def normalize(q: str) -> str:
    return re.sub(r"\s+", " ", (q or "").strip().lower())[:100]


def _score(q: str, text: str, boost: float = 0) -> float:
    t = (text or "").lower()
    if not t:
        return 0
    if t == q:
        s = 100
    elif t.startswith(q):
        s = 80
    elif re.search(rf"\b{re.escape(q)}", t):
        s = 60
    elif q in t:
        s = 40
    else:
        words = [w for w in q.split() if len(w) > 1]
        s = 25 * sum(1 for w in words if w in t) / max(1, len(words))
    return s + boost


def _icontains(fields: list[str], q: str) -> Q:
    """Every word must appear in at least one of the fields (so "biryani hyderabad" works across name and city)."""
    cond = Q()
    for w in [w for w in q.split() if len(w) > 1][:5] or [q]:
        part = Q()
        for f in fields:
            part |= Q(**{f"{f}__icontains": w})
        cond &= part
    return cond


# --- providers -----------------------------------------------------------------------------------------------------

def _stores(q, limit):
    from apps.stores.views import public_stores

    group_of = {"restaurant": "food", "grocery": "groceries", "retail": "stores", "pharmacy": "pharma"}
    out = []
    for s in public_stores().filter(_icontains(["name", "categories__name", "description", "city"], q)).distinct()[:limit]:
        g = group_of.get(s.store_type, "stores")
        out.append(Hit("store", str(s.id), s.name, f"{s.get_store_type_display()} · {s.city}", f"/stores/{s.slug}", g, g, s.image_url,
                       f"{s.rating_average}" if s.rating_count else None, badge="" if s.is_accepting_orders else "Closed now",
                       score=_score(q, s.name, float(s.rating_average or 0) + (3 if s.is_accepting_orders else 0))))
    return out


def _products(q, limit):
    from apps.catalog.views import public_products

    out = []
    qs = public_products().filter(store__is_accepting_orders=True).filter(_icontains(["name", "brand", "category__name", "shop_category__name"], q))
    for p in qs[: limit * 2]:
        t = p.store.store_type
        g = {"restaurant": "food", "grocery": "groceries", "pharmacy": "pharma"}.get(t, "products")
        link = f"/groceries/p/{p.id}" if t == "grocery" else f"/stores/{p.store.slug}" if t == "restaurant" else f"/products/{p.id}"
        out.append(Hit("product" if t != "restaurant" else "dish", str(p.id), p.name, f"{p.brand + ' · ' if p.brand else ''}{p.store.name}", link, g, g,
                       p.image_url, price=f"{p.price:.2f}", score=_score(q, p.name, 2 if t == "retail" else 0)))
    return out


def _hotels(q, limit):
    from apps.hotels.models import Destination, HotelProperty

    out = []
    for d in Destination.objects.filter(is_active=True).filter(name__icontains=q)[:3]:
        out.append(Hit("destination", str(d.id), f"Hotels in {d.name}", "Stays · compare and book", f"/hotels/search?destination={d.slug}", "hotels", "hotels",
                       score=_score(q, d.name, 5)))
    qs = HotelProperty.objects.filter(is_listed=True).select_related("partner", "destination").filter(
        _icontains(["partner__business_name", "destination__name", "area", "tagline"], q))
    for h in qs[:limit]:
        out.append(Hit("hotel", str(h.id), h.partner.business_name, f"{h.get_property_type_display()} · {h.area + ', ' if h.area else ''}{h.destination.name}",
                       f"/hotels/{h.id}", "hotels", "hotels", rating=f"{h.rating_average}" if h.rating_average else None,
                       score=_score(q, h.partner.business_name, float(h.rating_average or 0))))
    return out


def _travel(q, limit):
    from apps.travel.models import Place

    out = []
    for p in Place.objects.filter(is_active=True, kind="city").filter(Q(name__icontains=q) | Q(aliases__icontains=q) | Q(code__iexact=q))[:limit]:
        out.append(Hit("destination", str(p.id), f"Travel to {p.name}", f"Bus, train and flight{' · ' + p.state if p.state else ''}", f"/travel?to={p.slug}",
                       "travel", "travel", score=_score(q, p.name, 4)))
    return out


def _attractions(q, limit):
    from apps.experiences.models import Attraction

    out = []
    for a in Attraction.objects.filter(is_listed=True).filter(_icontains(["name", "city", "kind", "tagline", "deity"], q))[:limit]:
        out.append(Hit("attraction", str(a.id), a.name, f"{a.get_kind_display()} · {a.city}", f"/bookings/places/{a.slug}", "bookings", "bookings",
                       rating=f"{a.rating_average}" if a.rating_average else None, score=_score(q, a.name, float(a.rating_average or 0) + 2)))
    cities = {a.city for a in Attraction.objects.filter(is_listed=True, city__icontains=q)[:20]}
    for c in list(cities)[:2]:
        out.append(Hit("collection", f"places:{c}", f"Places to visit in {c}", "Temples, attractions and experiences", f"/bookings/search?city={c}",
                       "bookings", "bookings", score=_score(q, c, 3)))
    return out


def _shows(q, limit):
    from apps.bookings.views import public_events

    out = []
    for e in public_events().filter(Q(title__icontains=q) | Q(genres__icontains=q) | Q(cast__icontains=q))[:limit]:
        out.append(Hit("show", str(e.id), e.title, f"{e.get_kind_display()} · {e.get_status_display()}", f"/showtime/{e.slug}", "shows", "shows",
                       getattr(e, "poster_url", ""), score=_score(q, e.title, 3 if e.status == "now_showing" else 0)))
    return out


def _events(q, limit):
    from apps.eventhub.models import EventProvider, EventType

    out = []
    for t in EventType.objects.filter(is_active=True, name__icontains=q)[:3]:
        out.append(Hit("event_type", str(t.id), f"Plan a {t.name.lower()}", "Teams, venues and quotes", f"/events/plan?type={t.slug}", "events", "events",
                       score=_score(q, t.name, 3)))
    for p in EventProvider.objects.filter(is_listed=True).select_related("partner").filter(_icontains(["partner__business_name", "tagline", "city"], q))[:limit]:
        out.append(Hit("event_provider", str(p.id), p.partner.business_name, f"{p.get_kind_display()} · {p.city}", f"/events/providers/{p.id}", "events", "events",
                       rating=f"{p.rating_average}" if p.rating_average else None, score=_score(q, p.partner.business_name, float(p.rating_average or 0))))
    return out


def _services(q, limit):
    from apps.professionals.models import ProviderProfile, ServiceCategory, ServiceJob

    out = []
    for c in ServiceCategory.objects.filter(is_active=True).filter(Q(name__icontains=q) | Q(profession__icontains=q))[:3]:
        out.append(Hit("service_category", str(c.id), c.name, f"Book a {c.profession.lower()}", f"/services/{c.slug}", "services", "services", score=_score(q, c.name, 6)))
    for j in ServiceJob.objects.filter(is_active=True, name__icontains=q).select_related("category")[:4]:
        out.append(Hit("service_job", str(j.id), j.name, j.category.name, f"/services/{j.category.slug}", "services", "services", score=_score(q, j.name, 3)))
    for p in ProviderProfile.objects.filter(is_listed=True).select_related("partner", "category").filter(_icontains(["partner__business_name", "category__name"], q))[:limit]:
        out.append(Hit("professional", str(p.id), p.partner.business_name, f"{p.category.name} · {p.jobs_completed} jobs", f"/services/pro/{p.id}", "services", "services",
                       rating=f"{p.rating_average}" if p.rating_count else None, score=_score(q, p.partner.business_name, float(p.rating_average or 0))))
    return out


def _offers(q, limit, customer=None):
    from apps.offers import catalog

    out = []
    for o in catalog.all_offers(customer):
        text = f"{o['title']} {o['benefit']} {o['service_label']} {o['code'] or ''} {(o['partner'] or {}).get('name', '')}"
        if all(w in text.lower() for w in q.split() if len(w) > 1):
            out.append(Hit("offer", o["id"], o["benefit"], o["title"], f"/offers?q={o['code'] or o['benefit']}", "offers", o["service"], badge=o["code"] or "",
                           score=_score(q, o["title"]) + 1))
    return sorted(out, key=lambda h: -h.score)[:limit]


def _help(q, limit):
    from apps.support.models import HelpArticle

    return [Hit("article", a.slug, a.title, a.summary, f"/help/articles/{a.slug}", "help", "support", score=_score(q, a.title, -5))
            for a in HelpArticle.objects.filter(is_published=True).filter(Q(title__icontains=q) | Q(summary__icontains=q))[:limit]]


def _gift_cards(q, limit):
    try:
        from apps.giftcards.models import GiftCardDesign
    except ImportError:
        return []
    return [Hit("gift_card", str(d.id), d.title, d.category_label, f"/gift-cards?design={d.id}", "gift_cards", "gift_cards", score=_score(q, d.title, 1))
            for d in GiftCardDesign.objects.filter(is_active=True).filter(Q(title__icontains=q) | Q(category__icontains=q) | Q(occasion__icontains=q))[:limit]]


PROVIDERS = [_stores, _products, _hotels, _travel, _attractions, _shows, _events, _services, _offers, _help, _gift_cards]


def search(q: str, customer=None, *, group: str = "", limit: int = 6) -> dict:
    q = normalize(q)
    if len(q) < 2:
        return {"query": q, "top": [], "groups": [], "count": 0}
    hits: list[Hit] = []
    for p in PROVIDERS:
        try:
            hits += p(q, limit * 2, customer) if p is _offers else p(q, limit * 2)
        except Exception:  # noqa: BLE001 — one domain failing never breaks search for the rest
            import logging

            logging.getLogger(__name__).exception("search provider %s failed", p.__name__)
    if group:
        hits = [h for h in hits if h.group == group]
    hits.sort(key=lambda h: -h.score)
    by_group: dict[str, list[Hit]] = {}
    for h in hits:
        by_group.setdefault(h.group, []).append(h)
    order = sorted(by_group, key=lambda g: -max(h.score for h in by_group[g]))
    top = [h for h in hits[:4]] if not group else []
    per = 30 if group else limit
    return {"query": q, "count": len(hits), "top": [h.out() for h in top],
            "groups": [{"code": g, "label": GROUP_LABEL.get(g, g.title()), "count": len(by_group[g]), "results": [h.out() for h in by_group[g][:per]]} for g in order]}


# --- the customer's own records by ID ------------------------------------------------------------------------------

ID_RX = re.compile(r"^[A-Z]{2,4}-[A-Z0-9]{5,12}$")


def lookup_id(customer, raw: str) -> list[dict]:
    """Orders, bookings, parcels, rides, payments, invoices and support requests the customer owns, by reference.
    Another customer's records are never matched."""
    ref = (raw or "").strip().upper()
    if customer is None or not ID_RX.match(ref):
        return []
    out = []

    def add(kind, label, link, subtitle=""):
        out.append({"type": kind, "id": ref, "title": f"{label} {ref}", "subtitle": subtitle, "link": link, "group": "mine", "service": kind})

    for o in customer.orders.filter(number=ref).select_related("store")[:1]:
        add("order", "Order", f"/orders/{o.id}", f"{o.store.name} · {o.get_status_display()}")
    for b in customer.hotel_bookings.filter(number=ref)[:1]:
        add("hotel_booking", "Hotel booking", f"/hotels/bookings/{b.id}", b.get_status_display())
    for b in customer.travel_bookings.filter(Q(number=ref) | Q(pnr=ref))[:1]:
        add("travel_booking", "Travel booking", f"/travel/bookings/{b.id}", b.get_status_display())
    for b in customer.experience_bookings.filter(number=ref)[:1]:
        add("experience_booking", "Booking", f"/bookings/r/{b.id}", b.get_status_display())
    for b in customer.event_bookings.filter(number=ref)[:1]:
        add("event_booking", "Event booking", f"/events/bookings/{b.id}", b.get_status_display())
    for b in customer.service_bookings.filter(number=ref)[:1]:
        add("service_booking", "Service booking", f"/services/bookings/{b.id}", b.get_status_display())
    for p in customer.parcels.filter(number=ref)[:1]:
        add("parcel", "Parcel", f"/parcels/{p.id}", p.get_status_display())
    for r in customer.rides.filter(number=ref)[:1]:
        add("ride", "Ride", f"/rides/{r.id}", r.get_status_display())
    for b in customer.bookings.filter(reference=ref)[:1]:
        add("show_booking", "Ticket", f"/tickets/{b.id}", b.get_status_display())
    for t in customer.support_tickets.filter(reference=ref)[:1]:
        add("support", "Support request", f"/help/tickets/{t.id}", t.get_status_display())
    if ref.startswith("PAY-"):
        from apps.payments.records import owned

        for p in owned(customer):
            if f"PAY-{str(p.id)[:8].upper()}" == ref:
                add("payment", "Payment", f"/account/payments/{p.id}")
                break
    try:
        from apps.invoices.models import Invoice

        for i in Invoice.objects.filter(customer=customer, number=ref)[:1]:
            add("invoice", "Invoice", f"/account/invoices/{i.id}", i.get_status_display())
    except ImportError:
        pass
    return out
