"""
Groceries home, store pages, product pages and personal sections. Every section is computed from real records
(listings, stock, orders, offers) for the customer's location; a section with nothing real to show is left out.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from apps.catalog.pricing import price_of
from apps.orders.models import Order, OrderItem, OrderStatus
from apps.stores.models import StoreType
from apps.stores.views import active_offers

from . import catalog as cat
from . import delivery as dl
from .models import GroceryCategory, GroceryItem

SECTION_LIMIT = 12
POPULAR_MIN_ORDERS = 5
TOGETHER_MIN_ORDERS = 3
RUNNING_LOW_MIN_ORDERS = 3


def _ordered_stores(stores: dict) -> list:
    rank = {"open": 0, "closing_soon": 1, "closed": 2, "unavailable": 3}
    return sorted(stores.values(), key=lambda h: (rank[h["status"]["state"]], h["distance_km"] if h["distance_km"] is not None else 99,
                                                  -float(h["store"].rating_average)))


def badges(store, popular_ids: set, fresh_ids: set) -> list[dict]:
    cfg = dl.config(store)
    out = []
    if cfg.is_independent:
        out.append({"code": "local", "label": "Local Store"})
    if store.verified_at:
        out.append({"code": "verified", "label": "Verified Vendor"})
    if store.id in popular_ids:
        out.append({"code": "popular", "label": "Popular Near You"})
    if store.id in fresh_ids:
        out.append({"code": "fresh", "label": "Fresh Today"})
    return out


def popular_store_ids(store_ids) -> set:
    """Stores with at least POPULAR_MIN_ORDERS delivered/active orders in 30 days, top three by orders."""
    since = timezone.now() - timedelta(days=30)
    rows = (Order.objects.filter(store_id__in=store_ids, created_at__gte=since).exclude(status=OrderStatus.CANCELLED)
            .values("store_id").annotate(n=Count("id")).filter(n__gte=POPULAR_MIN_ORDERS).order_by("-n")[:3])
    return {r["store_id"] for r in rows}


def fresh_store_ids(store_ids) -> set:
    today = dl.now_local().date()
    return set(cat.orderable_listings().filter(store_id__in=store_ids, received_on=today).values_list("store_id", flat=True))


def store_card(h: dict, popular: set, fresh: set, offers_by_store: dict) -> dict:
    s = h["store"]
    return {
        "id": str(s.id), "slug": s.slug, "name": s.name, "image_url": s.image_url, "locality": s.locality,
        "categories": [c.name for c in s.categories.all()],
        "rating": {"average": f"{s.rating_average:.1f}", "count": s.rating_count} if s.rating_count else None,
        "status": h["status"], "distance_km": h["distance_km"], "eta_label": h["eta_label"], "fast": h["fast"],
        "eta_min": h["eta_min"], "eta_max": h["eta_max"],
        "delivery_fee": h["delivery_fee"], "free_delivery_above": f"{s.free_delivery_above:.2f}" if s.free_delivery_above is not None else None,
        "min_order": f"{s.min_order_amount:.2f}" if s.min_order_amount else None,
        "deliverable": h["deliverable"], "can_schedule": h["can_schedule"], "reason": h["reason"],
        "offer": offers_by_store.get(s.id), "badges": badges(s, popular, fresh), "currency": s.currency,
    }


def _offers_by_store(store_ids) -> dict:
    out = {}
    for o in active_offers().filter(store_id__in=store_ids).order_by("created_at"):
        out.setdefault(o.store_id, o.title)
    return out


def offer_cards(stores: dict) -> list[dict]:
    rows = active_offers().filter(store_id__in=list(stores)).select_related("store").order_by("-discount_type", "created_at")
    return [{"id": str(o.id), "title": o.title, "description": o.description, "redeemable": o.is_redeemable,
             "min_order": f"{o.min_order_amount:.2f}" if o.min_order_amount else None,
             "ends_at": o.ends_at.isoformat() if o.ends_at else None,
             "store": {"id": str(o.store_id), "slug": o.store.slug, "name": o.store.name}} for o in rows]


def _section_listings(store_ids, filt: Q, ctx, limit=SECTION_LIMIT, prefer=None):
    rows = list(cat.popular_first(cat.visible_listings().filter(store_id__in=store_ids).filter(filt))[:200])
    best = cat.best_per_item(rows, prefer)
    best.sort(key=lambda p: (not (p.is_orderable and p.store.is_accepting_orders), -p.units_sold, p.grocery_item.name))
    return cat.cards(best[:limit], ctx)


def home(customer, point) -> dict:
    stores = cat.deliverable_stores(point)
    ids = list(stores)
    ordered = _ordered_stores(stores)
    prefer = [h["store"].id for h in ordered]
    ctx = {"stores": stores}
    popular, fresh, offers = popular_store_ids(ids), fresh_store_ids(ids), _offers_by_store(ids)
    store_cards = [store_card(h, popular, fresh, offers) for h in ordered]

    counts = dict(cat.orderable_listings().filter(store_id__in=ids).values("grocery_item__category_id")
                  .annotate(n=Count("grocery_item", distinct=True)).values_list("grocery_item__category_id", "n"))
    categories = [{"slug": c.slug, "name": c.name, "icon": c.icon, "image_url": c.image_url, "section": c.section,
                   "count": counts[c.id]} for c in cat.category_tree() if counts.get(c.id)]

    sections = []
    for code, title in GroceryCategory.Section.choices:
        cards = _section_listings(ids, Q(grocery_item__category__section=code), ctx, prefer=prefer)
        if cards:
            sections.append({"code": code, "title": title, "items": cards})

    deals_listings = _section_listings(ids, Q(compare_at_price__isnull=False) | Q(deals__is_active=True), ctx, prefer=prefer)
    deals_listings = [c for c in deals_listings if c["discount_percent"]]
    fast = sorted([store_card(h, popular, fresh, offers) for h in ordered if h["fast"]], key=lambda c: (c["eta_min"] or 999))
    local = [c for c in store_cards if any(b["code"] == "local" for b in c["badges"])]

    out = {
        "has_location": point is not None, "stores": store_cards, "categories": categories, "sections": sections,
        "offers": offer_cards(stores), "deals": deals_listings, "fast": fast[:6], "local": local,
        "fresh_today": len(fresh), "buy_again": [], "running_low": [],
    }
    if customer is not None:
        out["buy_again"] = buy_again(customer, point, limit=10, stores=stores)
        out["running_low"] = running_low(customer, point, stores=stores)
    return out


# --- personal: buy again / running low --------------------------------------------------------------------------

def _grocery_history(customer):
    return (OrderItem.objects.filter(order__customer=customer, order__store__store_type=StoreType.GROCERY,
                                     order__status=OrderStatus.DELIVERED, product__grocery_item__isnull=False)
            .select_related("order", "product").order_by("-order__delivered_at"))


def _current_listing(item_id, store_id, stores: dict):
    """Today's listing of an item: the same store's if it can still be ordered, else the best nearby one."""
    qs = list(cat.visible_listings().filter(grocery_item_id=item_id, store_id__in=list(stores)))
    same = next((p for p in qs if p.store_id == store_id and p.is_orderable and p.store.is_accepting_orders), None)
    if same:
        return same
    best = cat.best_per_item(qs, [store_id])
    return best[0] if best else None


def buy_again(customer, point, limit=20, stores=None) -> list[dict]:
    stores = stores if stores is not None else cat.deliverable_stores(point)
    seen: dict = {}
    for oi in _grocery_history(customer)[:300]:
        key = oi.product.grocery_item_id
        s = seen.setdefault(key, {"times": 0, "last": oi.order.delivered_at, "store_id": oi.order.store_id,
                                  "last_price": oi.unit_price, "orders": set()})
        if oi.order_id not in s["orders"]:
            s["orders"].add(oi.order_id)
            s["times"] += 1
    rows = sorted(seen.items(), key=lambda kv: (-kv[1]["times"], -(kv[1]["last"].timestamp() if kv[1]["last"] else 0)))
    out = []
    for item_id, s in rows:
        listing = _current_listing(item_id, s["store_id"], stores)
        if listing is None:
            continue
        card = cat.cards([listing], {"stores": stores})[0]
        out.append({"listing": card, "times": s["times"], "last_bought": s["last"].isoformat() if s["last"] else None,
                    "last_price": f"{s['last_price']:.2f}", "same_store": listing.store_id == s["store_id"]})
        if len(out) >= limit:
            break
    return out


def running_low(customer, point, stores=None) -> list[dict]:
    """Items bought in 3+ orders whose usual gap has (nearly) passed. Purchase patterns only, never consumption."""
    stores = stores if stores is not None else cat.deliverable_stores(point)
    dates: dict = defaultdict(set)
    last_store = {}
    for oi in _grocery_history(customer)[:500]:
        if oi.order.delivered_at:
            dates[oi.product.grocery_item_id].add(dl.now_local(oi.order.delivered_at).date())
            last_store.setdefault(oi.product.grocery_item_id, oi.order.store_id)
    today = dl.now_local().date()
    out = []
    for item_id, days in dates.items():
        if len(days) < RUNNING_LOW_MIN_ORDERS:
            continue
        ds = sorted(days)
        gaps = [(b - a).days for a, b in zip(ds, ds[1:]) if (b - a).days > 0]
        if len(gaps) < 2:
            continue
        usual = round(statistics.median(gaps))
        since = (today - ds[-1]).days
        if usual >= 1 and since >= usual * 0.8:
            listing = _current_listing(item_id, last_store[item_id], stores)
            if listing is None:
                continue
            out.append({"listing": cat.cards([listing], {"stores": stores})[0], "usual_days": usual, "days_since": since})
    return sorted(out, key=lambda r: -(r["days_since"] / r["usual_days"]))[:8]


# --- product and store pages --------------------------------------------------------------------------------------

def together(item_id, stores: dict, limit=6) -> list[dict]:
    """Items that appear in the same orders as this one in at least TOGETHER_MIN_ORDERS orders."""
    order_ids = (OrderItem.objects.filter(product__grocery_item_id=item_id).exclude(order__status=OrderStatus.CANCELLED)
                 .values_list("order_id", flat=True).distinct()[:2000])
    rows = (OrderItem.objects.filter(order_id__in=list(order_ids), product__grocery_item__isnull=False)
            .exclude(product__grocery_item_id=item_id).values("product__grocery_item_id")
            .annotate(n=Count("order_id", distinct=True)).filter(n__gte=TOGETHER_MIN_ORDERS).order_by("-n")[:limit])
    out = []
    for r in rows:
        best = cat.best_per_item(list(cat.visible_listings().filter(grocery_item_id=r["product__grocery_item_id"], store_id__in=list(stores))))
        if best:
            out.append({**cat.cards(best, {"stores": stores})[0], "together_orders": r["n"]})
    return out


def compare(item: GroceryItem, stores: dict) -> list[dict]:
    """The same item and pack size at each nearby store (never a different size or brand)."""
    listings = list(cat.visible_listings().filter(grocery_item=item, store_id__in=list(stores)))
    rows = cat.cards(listings, {"stores": stores})
    for r in rows:
        r["distance_km"] = stores[next(p.store_id for p in listings if str(p.id) == r["id"])]["distance_km"]
    return sorted(rows, key=lambda r: (not r["orderable"], float(r["price"])))


def product_detail(product, point, customer=None) -> dict:
    stores = cat.deliverable_stores(point)
    stores.setdefault(product.store_id, dl.headline(product.store, point) | {"store": product.store})
    card = cat.cards([product], {"stores": stores})[0]
    item = product.grocery_item
    similar = cat.best_per_item(list(cat.visible_listings().filter(store_id__in=list(stores), grocery_item__category=item.category)
                                     .exclude(grocery_item=item)[:80]), [product.store_id])
    similar.sort(key=lambda p: (not p.is_orderable, -p.units_sold))
    from apps.shop.models import ProductReview

    reviews = [{"id": str(r.id), "rating": r.rating, "title": r.title, "body": r.body, "created_at": r.created_at.isoformat(),
                "author": (r.customer.user.full_name or "Click customer").split(" ")[0]}
               for r in ProductReview.objects.filter(product=product, status=ProductReview.Status.PUBLISHED).select_related("customer__user")[:5]]
    alert = False
    if customer is not None and not card["in_stock"]:
        alert = product.stock_alerts.filter(customer=customer, notified_at__isnull=True).exists()
    h = stores[product.store_id]
    return {
        **card, "description": item.description, "ingredients": item.ingredients, "nutrition": item.nutrition,
        "image_source": item.image_source, "pricing_note": (
            "Weighed when packed. You pay the price shown, never more; if it's lighter, the store adjusts down."
            if product.variable_weight else ""),
        "delivery": {"status": h["status"], "eta_label": h["eta_label"], "deliverable": h["deliverable"], "reason": h["reason"],
                     "distance_km": h["distance_km"]},
        "compare": compare(item, stores), "together": together(item.id, stores), "similar": cat.cards(similar[:8], {"stores": stores}),
        "reviews": reviews, "alert_set": alert,
    }


def store_page(store, point, customer=None) -> dict:
    h = dl.headline(store, point)
    h["store"] = store
    ids = [store.id]
    card = store_card(h, popular_store_ids(ids), fresh_store_ids(ids), _offers_by_store(ids))
    cfg = dl.config(store)
    listings = cat.visible_listings().filter(store=store)
    counts = dict(listings.values("grocery_item__category_id").annotate(n=Count("id")).values_list("grocery_item__category_id", "n"))
    categories = [{"slug": c.slug, "name": c.name, "icon": c.icon, "count": counts[c.id], "section": c.section}
                  for c in cat.category_tree() if counts.get(c.id)]
    ctx = {"stores": {store.id: h}}
    popular = cat.cards(cat.popular_first(listings.filter(units_sold__gt=0))[:10], ctx)
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    hours = [{"day": days[x.weekday], "weekday": x.weekday, "opens": x.opens_at.strftime("%I:%M %p").lstrip("0"),
              "closes": x.closes_at.strftime("%I:%M %p").lstrip("0")} for x in dl._hours(store)]
    from apps.orders.models import OrderReview

    reviews = [{"rating": r.rating, "comment": r.comment, "created_at": r.created_at.isoformat(),
                "author": (r.customer.user.full_name or "Click customer").split(" ")[0]}
               for r in OrderReview.objects.filter(store=store).exclude(comment="").select_related("customer__user")[:5]]
    alert = False
    if customer is not None and card["status"]["state"] == "unavailable":
        alert = store.stock_alerts.filter(customer=customer, notified_at__isnull=True).exists()
    return {
        **card, "description": store.description, "cover_url": cfg.cover_url, "about": cfg.about,
        "address": cfg.address_line or ", ".join(x for x in (store.locality, store.city) if x),
        "support_phone": cfg.support_phone, "policies": cfg.policies, "freshness_note": cfg.freshness_note,
        "hours": hours, "delivery_options": dl.options(store, point, with_slots=False)["options"],
        "categories": categories, "popular": popular, "offers": offer_cards({store.id: h}),
        "reviews": reviews, "alert_set": alert, "verified": store.verified_at is not None,
        "product_count": listings.count(),
    }


def popular_terms(stores: dict, limit=8) -> list[str]:
    """Most-sold items at nearby stores (actual sales), as search suggestions."""
    sold = Counter()
    for p in cat.visible_listings().filter(store_id__in=list(stores), units_sold__gt=0).values("grocery_item__name", "units_sold"):
        sold[p["grocery_item__name"]] += p["units_sold"]
    return [name for name, _ in sold.most_common(limit)]
