"""
Click. Shopping read services: home sections, the infinite discovery feed, search (with interpretation, filters,
facets and spelling correction), typeahead suggestions, category pages, product detail and comparison.

Sections are only returned when they have enough real content (`SECTION_MIN`); the app never shows an empty or
padded section.
"""

import base64
import difflib
import json
import re
import uuid
from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.contrib.postgres.search import TrigramWordSimilarity
from django.db.models import Count, Exists, Max, Min, OuterRef, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.activity.models import CustomerActivity
from apps.activity.services import record
from apps.catalog.images import image_urls
from apps.catalog.models import AttributeDefinition, Brand, Product, ProductAttributeValue, ProductVariant, ShopCategory
from apps.catalog.pricing import active_deals, attach_deals, price_of
from apps.core.api.exceptions import DomainError
from apps.orders.models import OrderItem, OrderStatus

from . import serializers as S
from .delivery import estimate
from .listings import affinity_rank, in_category, listings, order_by_sort, trending_scores, with_pricing
from .models import ProductReview, ShopCampaign
from .personal import signals
from .query import interpret

SECTION_MIN = 4
SECTION_SIZE = 12
PAGE_SIZE = 24
FEED_PAGE = 20
SORTS = {"relevance", "popular", "price_asc", "price_desc", "rating", "newest", "discount"}


def customer_of(request):
    user = getattr(request, "user", None)
    return getattr(user, "customer_profile", None) if user is not None and user.is_authenticated else None


# --- home -------------------------------------------------------------------------------------------------

def active_campaigns(category=None):
    now = timezone.now()
    qs = ShopCampaign.objects.filter(is_active=True, starts_at__lte=now, ends_at__gt=now)
    if category is not None:
        qs = qs.filter(category__in=[category.id] + ([category.parent_id] if category.parent_id else []))
    return list(qs.order_by("-priority", "ends_at")[:5])


def category_counts() -> Counter:
    counts: Counter = Counter()
    for row in listings().values("shop_category_id", "shop_category__parent_id").annotate(n=Count("id")):
        counts[row["shop_category_id"]] += row["n"]
        if row["shop_category__parent_id"]:
            counts[row["shop_category__parent_id"]] += row["n"]
    return counts


def top_categories() -> list[dict]:
    counts = category_counts()
    return [S.category(c, counts[c.id]) for c in ShopCategory.objects.filter(parent__isnull=True, is_active=True) if counts[c.id]]


def brand_list(limit=None) -> list[dict]:
    rows = (listings().filter(brand_ref__isnull=False, brand_ref__is_active=True)
            .values("brand_ref_id", "brand_ref__name", "brand_ref__slug", "brand_ref__logo_url").annotate(n=Count("id")).order_by("-n", "brand_ref__name"))
    rows = rows[:limit] if limit else rows
    return [{"id": str(r["brand_ref_id"]), "name": r["brand_ref__name"], "slug": r["brand_ref__slug"], "logo_url": r["brand_ref__logo_url"],
             "product_count": r["n"]} for r in rows]


def _section(out, request, sid, title, subtitle, products, *, reasons=None, minimum=SECTION_MIN, link=None):
    products = list(products)
    if len(products) >= minimum:
        out.append({"id": sid, "kind": "products", "title": title, "subtitle": subtitle, "link": link,
                    "products": S.cards(products[:SECTION_SIZE], request, reasons)})


def _by_ids(ids):
    order = {pid: i for i, pid in enumerate(ids)}
    return sorted(listings().filter(pk__in=ids), key=lambda p: order[p.pk])


def home(request) -> dict:
    customer = customer_of(request)
    sig = signals(customer)
    base = with_pricing(listings())
    sections: list = []

    deal_ids = list(dict.fromkeys(active_deals().filter(product__in=listings().values("id")).order_by("ends_at").values_list("product_id", flat=True)))
    _section(sections, request, "deals", "Deals for You", "Limited-time prices, set by each seller. Each ends when shown.",
             _by_ids(deal_ids[:SECTION_SIZE]), link="/shopping/search?sort=discount&deals=1")

    if not sig.empty and sig.categories:
        picks = (base.filter(Q(shop_category_id__in=sig.categories) | Q(brand_ref_id__in=sig.brands))
                 .exclude(pk__in=sig.bought + sig.wishlist + sig.viewed[:1]).order_by("-rating_average", "-units_sold", "id")[:SECTION_SIZE])
        cat_names = dict(ShopCategory.objects.filter(pk__in=sig.categories).values_list("id", "name"))
        reasons = {p.id: ("From a brand you like" if p.brand_ref_id in sig.brands else f"Because you like {cat_names.get(p.shop_category_id, 'this')}")
                   for p in picks}
        _section(sections, request, "for_you", "Just for You", "Picked from what you've viewed, saved and bought on Click.", picks, reasons=reasons)
    if not any(s["id"] == "for_you" for s in sections):
        popular = base.filter(Q(units_sold__gt=0) | Q(rating_count__gt=0)).order_by("-units_sold", "-rating_average", "id")
        _section(sections, request, "for_you", "Just for You",
                 "Popular on Click. Shopping right now. This gets more personal as you browse and shop.", popular)

    if sig.viewed:
        last = listings().filter(pk__in=sig.viewed[:5]).first()
        if last:
            similar = base.filter(shop_category_id=last.shop_category_id).exclude(pk=last.pk).order_by("-rating_average", "-units_sold")
            _section(sections, request, "because_viewed", f"Because you viewed {last.name}", "Similar picks in the same category.", similar, minimum=3)

    trending = sorted(trending_scores().items(), key=lambda kv: -kv[1])
    _section(sections, request, "trending", "Trending Now", "What customers are viewing, saving and buying this week.",
             _by_ids([pid for pid, _ in trending[:SECTION_SIZE]]))
    _section(sections, request, "best_sellers", "Best Sellers", "Ranked by units ordered on Click.",
             base.filter(units_sold__gt=0).order_by("-units_sold", "id"), link="/shopping/search?sort=popular")

    prev = 0
    names = ["Great Finds", "Smart Picks", "Premium Picks"]
    for i, t in enumerate(settings.CLICK_SHOP_PRICE_BANDS):
        band = base.filter(eff_price__gt=prev, eff_price__lte=t).order_by("-rating_average", "-units_sold", "id")
        _section(sections, request, f"under_{t}", f"{names[i] if i < len(names) else 'Picks'} Under ₹{t:,}", None, band,
                 link=f"/shopping/search?max_price={t}" + (f"&min_price={prev}" if prev else ""))
        prev = t

    _section(sections, request, "new_arrivals", "New Arrivals", "The latest listings from Click. sellers.",
             base.filter(created_at__gte=timezone.now() - timedelta(days=30)).order_by("-created_at", "id"), link="/shopping/search?sort=newest")

    brands = brand_list(12)
    if len(brands) >= 3:
        sections.append({"id": "brands", "kind": "brands", "title": "Popular Brands", "subtitle": "Brands sold by Click. sellers.",
                         "link": "/shopping/brands", "brands": brands})

    if sig.bought:
        _section(sections, request, "buy_again", "Buy Again", "Items from your delivered orders.", _by_ids(sig.bought[:SECTION_SIZE]), minimum=2)
    if sig.wishlist:
        cats = list(Product.objects.filter(pk__in=sig.wishlist).values_list("shop_category_id", flat=True))
        _section(sections, request, "wishlist_similar", "Similar to Your Wishlist", None,
                 base.filter(shop_category_id__in=cats).exclude(pk__in=sig.wishlist).order_by("-rating_average", "-units_sold"))

    return {"campaigns": [S.campaign(c) for c in active_campaigns()], "categories": top_categories(), "sections": sections,
            "personalized": not sig.empty}


# --- feed (cursor pagination) -------------------------------------------------------------------------------

def _encode(values) -> str:
    return base64.urlsafe_b64encode(json.dumps(values).encode()).decode()


def _decode(cursor: str):
    try:
        a, u, i = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return int(a), int(u), uuid.UUID(i)
    except Exception:
        raise DomainError("This list has changed. Pull to refresh.", code="invalid_cursor")


def feed(request, cursor: str | None) -> dict:
    """Endless discovery: listings in the customer's preferred categories/brands first, then by popularity."""
    sig = signals(customer_of(request))
    qs = affinity_rank(listings(), sig.categories, sig.brands).order_by("-affinity", "-units_sold", "id")
    if cursor:
        a, u, i = _decode(cursor)
        qs = qs.filter(Q(affinity__lt=a) | Q(affinity=a, units_sold__lt=u) | Q(affinity=a, units_sold=u, id__gt=i))
    page = list(qs[:FEED_PAGE + 1])
    more = len(page) > FEED_PAGE
    page = page[:FEED_PAGE]
    nxt = _encode([page[-1].affinity, page[-1].units_sold, str(page[-1].id)]) if more and page else None
    return {"results": S.cards(page, request), "next_cursor": nxt, "personalized": not sig.empty}


# --- search ---------------------------------------------------------------------------------------------------

def _int(v):
    try:
        return int(float(v)) if v not in (None, "") else None
    except (TypeError, ValueError):
        raise DomainError("Filters must be numbers.", code="invalid_filter")


def _in_stock(qs):
    variants = ProductVariant.objects.filter(product=OuterRef("pk"), is_active=True)
    return qs.annotate(_has_var=Exists(variants), _var_stock=Exists(variants.filter(Q(stock_quantity__isnull=True) | Q(stock_quantity__gt=0)))).filter(
        is_available=True).filter(Q(_has_var=False, stock_quantity__isnull=True) | Q(_has_var=False, stock_quantity__gt=0) | Q(_has_var=True, _var_stock=True))


def _age_ids(age: int) -> list:
    """Listings whose "Age group" attribute (e.g. "9-12 years", "12+ years", "6-24 months") includes this age."""
    ids = []
    for pid, value in ProductAttributeValue.objects.filter(definition__code="age").values_list("product_id", "value"):
        v = value.lower()
        if m := re.match(r"(\d+)\s*-\s*(\d+)\s*(years|months)", v):
            lo, hi = int(m.group(1)), int(m.group(2))
            if m.group(3) == "months":
                lo, hi = lo / 12, hi / 12
            if lo <= age <= hi:
                ids.append(pid)
        elif (m := re.match(r"(\d+)\s*\+", v)) and age >= int(m.group(1)):
            ids.append(pid)
    return ids


def _colour_ids(colour):
    return (ProductAttributeValue.objects.filter(definition__code="color", value__iexact=colour).values("product_id").union(
        ProductVariant.objects.filter(is_active=True, options__Color=colour).values("product_id")))


def search(params, request) -> dict:
    q = (params.get("q") or "").strip()[:120]
    it = interpret(q) if q else None
    qs = with_pricing(listings())

    cat_slug = params.get("category") or (it.category.slug if it and it.category else None)
    category = ShopCategory.objects.filter(slug=cat_slug, is_active=True).select_related("parent").first() if cat_slug else None
    if category:
        qs = in_category(qs, category)
        # "shirt" chose Men's Clothing; narrow to shirts when there are any (otherwise keep the whole category).
        if it and it.category and it.category.slug == category.slug and it.category_word:
            narrowed = qs.filter(name__icontains=it.category_word)
            if narrowed.exists():
                qs = narrowed
    elif it and it.categories:
        qs = qs.filter(Q(shop_category__in=it.categories) | Q(shop_category__parent__in=it.categories))
    if it and it.age is not None and (ids := _age_ids(it.age)):
        qs = qs.filter(pk__in=ids)
    brand_slugs = [b for b in (params.get("brand") or "").split(",") if b] or ([it.brand.slug] if it and it.brand else [])
    if brand_slugs:
        qs = qs.filter(brand_ref__slug__in=brand_slugs)
    if it and it.colour:
        qs = qs.filter(pk__in=_colour_ids(it.colour))
    for term in (it.terms if it else []):
        attr_ids = ProductAttributeValue.objects.filter(value__iexact=term).values("product_id")
        qs = qs.filter(Q(name__icontains=term) | Q(brand__icontains=term) | Q(shop_category__name__icontains=term)
                       | Q(shop_category__parent__name__icontains=term) | Q(shop_category__synonyms__icontains=term) | Q(pk__in=attr_ids))
    facet_base = qs

    min_price = _int(params.get("min_price")) if params.get("min_price") else (it.min_price if it else None)
    max_price = _int(params.get("max_price")) if params.get("max_price") else (it.max_price if it else None)
    if min_price is not None:
        qs = qs.filter(eff_price__gte=min_price)
    if max_price is not None:
        qs = qs.filter(eff_price__lte=max_price)
    if rating := _int(params.get("rating")):
        qs = qs.filter(rating_average__gte=rating, rating_count__gt=0)
    if discount := _int(params.get("discount")):
        qs = qs.filter(discount_pct__gte=discount)
    if params.get("deals"):
        qs = qs.filter(deal_pct__gt=0)
    if params.get("in_stock"):
        qs = _in_stock(qs)
    if seller := params.get("seller"):
        qs = qs.filter(store__slug=seller)
    for key, raw in params.items():
        values = [v for v in str(raw).split(",") if v]
        if key.startswith("attr_") and values:
            qs = qs.filter(pk__in=ProductAttributeValue.objects.filter(definition__code=key[5:], value__in=values).values("product_id"))
        elif key.startswith("opt_") and values:
            axis = key[4:].replace("_", " ").title()
            qs = qs.filter(pk__in=ProductVariant.objects.filter(is_active=True, **{f"options__{axis}__in": values}).values("product_id"))

    sort = params.get("sort") or (it.sort if it and it.sort else ("relevance" if q else "popular"))
    if sort not in SORTS:
        raise DomainError("Unknown sort.", code="invalid_sort")
    qs = order_by_sort(qs, sort, relevance=TrigramWordSimilarity(q, "name") if q else None)

    page = max(_int(params.get("page")) or 1, 1)
    count = qs.count()
    results = list(qs[(page - 1) * PAGE_SIZE: page * PAGE_SIZE])
    return {
        "query": q, "interpretation": it.as_dict() if it else None, "sort": sort,
        "category": S.category(category) if category else None,
        "correction": correction(q) if q and count == 0 else None,
        "count": count, "page": page, "has_more": page * PAGE_SIZE < count,
        "results": S.cards(results, request),
        "facets": facets(facet_base, category),
        "applied": {"min_price": min_price, "max_price": max_price, "brands": brand_slugs},
    }


def facets(qs, category) -> dict:
    """Filters that make sense for this result set: category-specific attributes and variant options only once a
    category is known, plus brands, sellers, price range, rating and discount."""
    ids = qs.values("id")
    plain = listings().filter(pk__in=ids)
    price = qs.aggregate(min=Min("eff_price"), max=Max("eff_price"))
    if category:
        # A top category offers its subcategories; a subcategory offers its siblings.
        children = list(category.children.filter(is_active=True))
        if not children and category.parent_id:
            children = list(ShopCategory.objects.filter(parent_id=category.parent_id, is_active=True))
    else:
        children = list(ShopCategory.objects.filter(parent__isnull=True, is_active=True))
    leaf_counts = Counter()
    for row in plain.values("shop_category_id", "shop_category__parent_id").annotate(n=Count("id")):
        leaf_counts[row["shop_category_id"]] += row["n"]
        if row["shop_category__parent_id"]:
            leaf_counts[row["shop_category__parent_id"]] += row["n"]
    out = {
        "categories": [{"slug": c.slug, "name": c.name, "count": leaf_counts[c.id]} for c in children if leaf_counts[c.id]],
        "brands": [{"slug": r["brand_ref__slug"], "name": r["brand_ref__name"], "count": r["n"]}
                   for r in plain.filter(brand_ref__isnull=False).values("brand_ref__slug", "brand_ref__name").annotate(n=Count("id")).order_by("-n")[:20]],
        "sellers": [{"slug": r["store__slug"], "name": r["store__name"], "count": r["n"]}
                    for r in plain.values("store__slug", "store__name").annotate(n=Count("id")).order_by("-n")[:12]],
        "price": {"min": S.money(price["min"]), "max": S.money(price["max"])},
        "ratings": [{"value": v, "count": plain.filter(rating_average__gte=v, rating_count__gt=0).count()} for v in (4, 3)],
        "discounts": [{"value": v, "count": qs.filter(discount_pct__gte=v).count()} for v in (10, 25, 40)],
        "attributes": [], "options": [],
    }
    if category:
        defs = AttributeDefinition.objects.filter(category_id__in=category.lineage_ids(), is_filterable=True,
                                                  kind__in=[AttributeDefinition.Kind.CHOICE, AttributeDefinition.Kind.BOOLEAN])
        for d in defs:
            vals = list(ProductAttributeValue.objects.filter(definition=d, product__in=ids).values("value").annotate(n=Count("id")).order_by("value"))
            if len(vals) > 1:
                out["attributes"].append({"code": d.code, "name": d.name, "values": [{"value": v["value"], "count": v["n"]} for v in vals]})
        axes: dict = {}
        for opts in ProductVariant.objects.filter(product__in=ids, is_active=True).values_list("options", flat=True)[:5000]:
            for k, v in (opts or {}).items():
                axes.setdefault(k, Counter())[v] += 1
        for name, counter in axes.items():
            if len(counter) > 1:
                out["options"].append({"code": name.lower().replace(" ", "_"), "name": name,
                                       "values": [{"value": v, "count": n} for v, n in counter.most_common(24)]})
    return out


def correction(q: str) -> str | None:
    """'Did you mean…' for a search with no results, from words that really exist in the catalogue."""
    words = re.findall(r"[a-z0-9&']+", q.lower())
    if not words:
        return None
    vocab = set()
    for c in ShopCategory.objects.filter(is_active=True).values_list("name", "synonyms"):
        vocab |= set(re.findall(r"[a-z0-9&']+", " ".join(c).lower()))
    vocab |= set(re.findall(r"[a-z0-9&']+", " ".join(Brand.objects.filter(is_active=True).values_list("name", flat=True)).lower()))
    names = (listings().annotate(sim=TrigramWordSimilarity(q, "name")).filter(sim__gt=0.25).order_by("-sim").values_list("name", flat=True)[:20])
    vocab |= set(re.findall(r"[a-z0-9&']+", " ".join(names).lower()))
    vocab = {w for w in vocab if len(w) > 2}
    fixed = [(difflib.get_close_matches(w, vocab, 1, 0.75) or [w])[0] if w not in vocab and len(w) > 2 else w for w in words]
    return " ".join(fixed) if fixed != words else None


def record_search(customer, q: str) -> None:
    if customer is not None and len(q) >= 2:
        record(customer, "shop.searched", {"q": q.lower()[:60]})


def suggest(q: str) -> dict:
    q = q.strip()[:60]
    out = []
    if len(q) >= 2:
        for c in ShopCategory.objects.filter(is_active=True).filter(Q(name__icontains=q) | Q(synonyms__icontains=q))[:3]:
            out.append({"text": c.name, "kind": "category", "path": f"/shopping/c/{c.slug}"})
        for b in Brand.objects.filter(is_active=True, name__istartswith=q)[:3]:
            out.append({"text": b.name, "kind": "brand", "path": f"/shopping/brands/{b.slug}"})
        seen = set()
        for name in listings().filter(name__icontains=q).order_by("-units_sold", "name").values_list("name", flat=True)[:12]:
            if name.lower() not in seen:
                seen.add(name.lower())
                out.append({"text": name, "kind": "product", "path": None})
            if len(seen) >= 6:
                break
    since = timezone.now() - timedelta(days=14)
    counts: dict = {}
    for meta, cust in CustomerActivity.objects.filter(verb="shop.searched", created_at__gte=since).values_list("metadata", "customer_id")[:5000]:
        term = (meta or {}).get("q")
        if term:
            counts.setdefault(term, set()).add(cust)
    trending = [t for t, custs in sorted(counts.items(), key=lambda kv: -len(kv[1])) if len(custs) >= 2][:8]
    return {"query": q, "suggestions": out[:10], "trending": trending, "categories": top_categories()[:8]}


# --- category -------------------------------------------------------------------------------------------------

def category_page(slug: str, request) -> dict:
    c = get_object_or_404(ShopCategory.objects.select_related("parent"), slug=slug, is_active=True)
    counts = category_counts()
    children = [S.category(x, counts[x.id]) for x in c.children.filter(is_active=True) if counts[x.id]]
    in_cat = in_category(listings(), c)
    scores = trending_scores()
    trend_ids = [pid for pid, _ in sorted(scores.items(), key=lambda kv: -kv[1]) if pid in set(in_cat.values_list("id", flat=True))]
    trending = _by_ids(trend_ids[:SECTION_SIZE])
    trending_title = "Trending in " + c.name
    if len(trending) < SECTION_MIN:
        trending, trending_title = list(in_cat.filter(units_sold__gt=0).order_by("-units_sold")[:SECTION_SIZE]), "Best sellers in " + c.name
    return {
        "category": S.category(c, counts[c.id]), "parent": S.category(c.parent) if c.parent_id else None, "children": children,
        "siblings": [S.category(x, counts[x.id]) for x in ShopCategory.objects.filter(parent_id=c.parent_id, is_active=True)] if c.parent_id else [],
        "campaigns": [S.campaign(x) for x in active_campaigns(c)],
        "highlight": {"title": trending_title, "products": S.cards(trending, request)} if len(trending) >= SECTION_MIN else None,
    }


# --- product --------------------------------------------------------------------------------------------------

def product_detail(pk, request, *, lat=None, lng=None, city="") -> dict:
    p = get_object_or_404(listings().prefetch_related("attribute_values__definition"), pk=pk)
    customer = customer_of(request)
    attach_deals([p])
    card = S.cards([p], request)[0]
    variants = [v for v in p.variants.all() if v.is_active]
    gallery = [image_urls(i, request) for i in p.images.all()] or ([card["image"]] if card["image"] else [])
    specs = [{"name": a.definition.name, "value": f"{a.value} {a.definition.unit}".strip(), "code": a.definition.code}
             for a in sorted(p.attribute_values.all(), key=lambda a: a.definition.position)]
    store = p.store
    published = ProductReview.objects.filter(product=p, status=ProductReview.Status.PUBLISHED)
    dist = {r["rating"]: r["n"] for r in published.values("rating").annotate(n=Count("id"))}
    co_orders = OrderItem.objects.filter(product=p).exclude(order__status=OrderStatus.CANCELLED).values("order_id")
    together = [r["product_id"] for r in OrderItem.objects.filter(order_id__in=co_orders).exclude(product=p).exclude(product__isnull=True)
                .values("product_id").annotate(n=Count("id")).filter(n__gte=2).order_by("-n")[:4]]
    similar = in_category(listings(), p.shop_category).filter(shop_category=p.shop_category).exclude(pk=p.pk).order_by("-rating_average", "-units_sold")[:12]
    has_location = lat is not None and lng is not None or bool(city)
    mine = published.filter(customer=customer).first() if customer else None
    if customer:
        record(customer, "product.viewed", obj=p)
    from apps.stores.views import active_offers

    from .reviews import review_problem

    offers = [{"id": str(o.id), "title": o.title, "description": o.description, "min_order_amount": S.money(o.min_order_amount),
               "redeemable": o.is_redeemable} for o in active_offers().filter(store=store)[:4]]
    return {
        "offers": offers,
        **card,
        "description": p.description, "highlights": p.highlights or [], "unit_label": p.unit_label,
        "gallery": gallery, "variants": [S.variant(v, p) for v in variants], "axes": S.variant_axes(variants), "specs": specs,
        "seller": {**S.seller_brief(store), "dispatch_days": store.dispatch_days, "return_policy": store.return_policy,
                   "delivery_fee": S.money(store.delivery_fee), "free_delivery_above": S.money(store.free_delivery_above)},
        "policies": {"return_days": p.return_days, "replacement_only": p.replacement_only, "warranty": p.warranty,
                     "cod_available": p.is_cod_available and store.cod_enabled, "secure_payment": True},
        "delivery": estimate(store, lat=lat, lng=lng, city=city, subtotal=price_of(p).price) if has_location else None,
        "rating_summary": {"average": card["rating"], "count": p.rating_count, "distribution": {str(s): dist.get(s, 0) for s in range(5, 0, -1)}},
        "reviews": [S.review(r) for r in published.select_related("customer__user")[:5]],
        "my_review": S.review(mine) if mine else None,
        "can_review": customer is not None and mine is None and review_problem(customer, p) is None,
        "similar": S.cards(similar, request),
        "bought_together": S.cards(_by_ids(together), request) if len(together) >= 1 else [],
        "low_stock": p.stock_quantity is not None and 0 < p.stock_quantity <= 5,
    }


def compare(ids, request) -> dict:
    ids = list(dict.fromkeys(ids))
    if not 2 <= len(ids) <= 4:
        raise DomainError("Choose 2 to 4 products to compare.", code="compare_count")
    products = list(listings().filter(pk__in=ids).prefetch_related("attribute_values__definition"))
    if len(products) != len(ids):
        raise DomainError("Some of these products are no longer available.", code="compare_unavailable", status_code=404)
    order = {str(i): n for n, i in enumerate(ids)}
    products.sort(key=lambda p: order[str(p.id)])
    tops = {p.shop_category.parent_id or p.shop_category_id for p in products}
    if len(tops) > 1:
        raise DomainError("These products are from different categories, so there's nothing useful to compare.", code="compare_incompatible")
    lineage = {cid for p in products for cid in p.shop_category.lineage_ids()}
    defs = list(AttributeDefinition.objects.filter(category_id__in=lineage, is_comparable=True).order_by("position", "name"))
    values = {(a.product_id, a.definition_id): f"{a.value} {a.definition.unit}".strip() for p in products for a in p.attribute_values.all()}
    rows = []
    for d in defs:
        row = [values.get((p.id, d.id)) for p in products]
        if any(row):
            rows.append({"label": d.name, "values": row, "differs": len(set(row)) > 1})
    policy = [
        {"label": "Returns", "values": [f"{p.return_days}-day {'replacement' if p.replacement_only else 'return'}" if p.return_days else "Not returnable" for p in products]},
        {"label": "Warranty", "values": [p.warranty or None for p in products]},
        {"label": "Sold by", "values": [p.store.name for p in products]},
        {"label": "Cash on delivery", "values": ["Available" if p.is_cod_available and p.store.cod_enabled else "Not available" for p in products]},
    ]
    for r in policy:
        r["differs"] = len(set(r["values"])) > 1
    return {"products": S.cards(products, request), "rows": rows + policy}
