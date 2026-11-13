"""
Grocery search: products, brands, stores and categories from the database, for the stores that deliver to the
customer. Matching uses the item name, brand and the category registry's names and synonyms ("veggies",
"sabzi"); results are grouped one card per product (the best listing nearby) with how many stores have it.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from django.db.models import Q

from apps.catalog.pricing import attach_deals, price_of

from . import catalog as cat
from .models import GroceryCategory

SORTS = {"relevance", "price_low", "price_high", "rating", "fastest", "popular", "new"}
PAGE_SIZE = 24
STOP = {"the", "a", "an", "and", "for", "of", "some", "near", "me", "nearby", "store", "stores", "shop", "buy", "get", "i", "need", "want",
        "fresh", "from", "local", "my", "please", "show", "find", "cheapest", "cheap", "best", "grocery", "groceries", "open", "now"}


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if t not in STOP and len(t) > 1]


def _singular(t: str) -> str:
    if t.endswith("ies") and len(t) > 4:
        return t[:-3] + "y"
    if t.endswith("oes") and len(t) > 4:
        return t[:-2]
    if t.endswith("s") and not t.endswith("ss") and len(t) > 3:
        return t[:-1]
    return t


def matching_categories(words) -> list[GroceryCategory]:
    out = []
    for c in cat.category_tree():
        names = {c.name.lower(), c.slug.replace("-", " ")} | {s.strip().lower() for s in c.synonyms.split(",") if s.strip()}
        vocab = {w for n in names for w in re.findall(r"[a-z0-9]+", n)} | names
        if any(w in vocab or _singular(w) in vocab for w in words):
            out.append(c)
    return out


def text_filter(words) -> Q:
    q = Q()
    for w in words:
        s = _singular(w)
        q &= (Q(grocery_item__name__icontains=s) | Q(grocery_item__brand__icontains=s) | Q(store__name__icontains=s)
              | Q(grocery_item__category__name__icontains=s) | Q(grocery_item__category__synonyms__icontains=s)
              | Q(grocery_item__attributes__icontains=s))
    return q


def _dec(raw):
    try:
        return Decimal(str(raw)) if raw not in (None, "") else None
    except InvalidOperation:
        return None


def search(params, point) -> dict:
    q = (params.get("q") or "")[:100]
    words = tokens(q)
    stores = cat.deliverable_stores(point)
    qs = cat.visible_listings().filter(store_id__in=list(stores))
    cats = matching_categories(words) if words else []
    if words:
        qs = qs.filter(text_filter(words) | Q(grocery_item__category__in=cats))
    if c := params.get("category"):
        qs = qs.filter(grocery_item__category__slug=c)
    if sec := params.get("section"):
        qs = qs.filter(grocery_item__category__section=sec)
    if brands := [b for b in (params.get("brand") or "").split(",") if b]:
        qs = qs.filter(grocery_item__brand__in=brands)
    if s := params.get("store"):
        qs = qs.filter(store__slug=s)
    if params.get("in_stock") == "true":
        qs = qs.filter(is_available=True).filter(Q(stock_quantity__isnull=True) | Q(stock_quantity__gt=0))
    if params.get("offers") == "true":
        qs = qs.filter(Q(compare_at_price__isnull=False) | Q(deals__is_active=True))
    if (d := params.get("dietary")) in ("veg", "vegan"):
        qs = qs.filter(grocery_item__dietary__in=["veg", "vegan"] if d == "veg" else ["vegan"])
    if (r := _dec(params.get("min_rating"))) is not None:
        qs = qs.filter(store__rating_average__gte=r)
    listings = list(qs.distinct()[:600])
    if words:
        # "rice" means rice: when products are named for the words, category-only matches (atta in "Rice & Atta") drop out.
        named = [p for p in listings if all(_singular(w) in f"{p.grocery_item.brand} {p.grocery_item.name}".lower() for w in words)]
        if named:
            listings = named
    attach_deals(listings)
    lo, hi = _dec(params.get("min_price")), _dec(params.get("max_price"))
    if lo is not None:
        listings = [p for p in listings if price_of(p).price >= lo]
    if hi is not None:
        listings = [p for p in listings if price_of(p).price <= hi]
    if (eta := _dec(params.get("max_eta"))) is not None:
        listings = [p for p in listings if stores[p.store_id]["eta_max"] is not None and stores[p.store_id]["eta_max"] <= eta]

    # facets from what matched (before grouping), so filters never offer an empty choice
    brands_facet = sorted({p.grocery_item.brand for p in listings if p.grocery_item.brand})
    cats_facet = {}
    for p in listings:
        cats_facet.setdefault(p.grocery_item.category.slug, p.grocery_item.category.name)
    store_count: dict = {}
    for p in listings:
        store_count.setdefault(p.grocery_item_id, set()).add(p.store_id)

    best = cat.best_per_item(listings, [h["store"].id for h in sorted(stores.values(), key=lambda h: h["distance_km"] or 99)])
    sort = params.get("sort") if params.get("sort") in SORTS else "relevance"

    def relevance(p):
        name = f"{p.grocery_item.brand} {p.grocery_item.name}".lower()
        score = sum(3 if re.search(rf"\b{re.escape(_singular(w))}", name) else 0 for w in words)
        return (-score, not p.is_orderable, -p.units_sold)

    keys = {
        "relevance": relevance,
        "price_low": lambda p: (not p.is_orderable, price_of(p).price),
        "price_high": lambda p: (not p.is_orderable, -price_of(p).price),
        "rating": lambda p: (not p.is_orderable, -float(p.rating_average), -float(p.store.rating_average)),
        "fastest": lambda p: (not p.is_orderable, stores[p.store_id]["eta_min"] or 999),
        "popular": lambda p: (not p.is_orderable, -p.units_sold),
        "new": lambda p: (not p.is_orderable, -p.created_at.timestamp()),
    }
    best.sort(key=keys[sort])
    try:
        page = max(int(params.get("page", 1)), 1)
    except ValueError:
        page = 1
    chunk = best[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
    ctx = {"stores": stores}
    results = []
    for card, p in zip(cat.cards(chunk, ctx), chunk):
        others = len(store_count.get(p.grocery_item_id, ())) - 1
        results.append({**card, "other_stores": max(others, 0)})

    matched_stores = []
    if words:
        for h in stores.values():
            s = h["store"]
            text = f"{s.name} {' '.join(c.name for c in s.categories.all())} {s.locality}".lower()
            if all(_singular(w) in text for w in words) or any(w in s.name.lower() for w in words if len(w) > 3):
                matched_stores.append(h)
    from .discovery import store_card

    return {
        "query": q, "count": len(best), "page": page, "page_size": PAGE_SIZE, "has_more": page * PAGE_SIZE < len(best),
        "results": results, "sort": sort, "has_location": point is not None,
        "stores": [store_card(h, set(), set(), {}) for h in matched_stores[:6]],
        "categories": [{"slug": c.slug, "name": c.name, "icon": c.icon} for c in cats][:4],
        "facets": {"brands": brands_facet[:30], "categories": [{"slug": k, "name": v} for k, v in cats_facet.items()]},
    }


def suggest(q: str, point) -> dict:
    words = tokens(q)
    if not words:
        return {"products": [], "stores": [], "brands": [], "categories": []}
    stores = cat.deliverable_stores(point)
    qs = cat.visible_listings().filter(store_id__in=list(stores)).filter(text_filter(words))
    best = cat.best_per_item(list(qs[:200]))
    best.sort(key=lambda p: (not p.is_orderable, -p.units_sold))
    brands = sorted({p.grocery_item.brand for p in qs[:200] if p.grocery_item.brand and any(_singular(w) in p.grocery_item.brand.lower() for w in words)})
    store_hits = [h for h in stores.values() if any(w in h["store"].name.lower() for w in words)]
    from .discovery import store_card

    return {
        "products": cat.cards(best[:6], {"stores": stores}),
        "stores": [store_card(h, set(), set(), {}) for h in store_hits[:4]],
        "brands": brands[:5],
        "categories": [{"slug": c.slug, "name": c.name, "icon": c.icon} for c in matching_categories(words)][:4],
    }
