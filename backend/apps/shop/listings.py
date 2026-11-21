"""
Marketplace listing queries shared by every Shopping surface (home sections, feed, search, category pages, Buddy).

Ranking signals are real records only:
  best sellers  Product.units_sold (maintained by order placement/cancellation)
  trending      the last 7 days of product views, wishlist saves and cart adds (CustomerActivity) plus units ordered
  new           listing creation date
  top rated     published, verified-purchase reviews (Product.rating_average / rating_count)
"""

from datetime import timedelta

from django.core.cache import cache
from django.db.models import Case, Count, DecimalField, ExpressionWrapper, F, IntegerField, OuterRef, Q, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.activity.models import CustomerActivity
from apps.catalog.models import Product
from apps.catalog.pricing import active_deals
from apps.orders.models import OrderItem, OrderStatus
from apps.stores.models import Store, StoreType

NEW_FOR_DAYS = 30
TRENDING_DAYS = 7
TRENDING_MIN_SCORE = 4
TOP_RATED_MIN = 4.5
TOP_RATED_MIN_COUNT = 3
SIGNAL_WEIGHTS = {"product.viewed": 1, "wishlist.added": 2, "cart.added": 3}
BADGE_CACHE_SECONDS = 300


def listings():
    """Customer-visible marketplace listings: active retail sellers, active products in the Shopping taxonomy."""
    return (Product.objects.filter(is_active=True, shop_category__isnull=False, shop_category__is_active=True,
                                   store__status=Store.Status.ACTIVE, store__store_type=StoreType.RETAIL)
            .select_related("store", "brand_ref", "shop_category", "shop_category__parent")
            .prefetch_related("images", "variants"))


def with_pricing(qs):
    """Annotate the server's effective price (after an active deal) and discount, for price filters and sorting."""
    deal_pct = Subquery(active_deals().filter(product=OuterRef("pk")).order_by("-percent_off").values("percent_off")[:1],
                        output_field=IntegerField())
    money = DecimalField(max_digits=12, decimal_places=2)
    return qs.annotate(
        deal_pct=Coalesce(deal_pct, Value(0)),
        eff_price=ExpressionWrapper(F("price") * (Value(100) - F("deal_pct")) / Value(100), output_field=money),
        ref_price=Coalesce(F("compare_at_price"), F("price"), output_field=money),
    ).annotate(discount_pct=ExpressionWrapper((F("ref_price") - F("eff_price")) * Value(100) / F("ref_price"), output_field=money))


def in_category(qs, category):
    return qs.filter(Q(shop_category=category) | Q(shop_category__parent=category))


def trending_scores(days: int = TRENDING_DAYS) -> dict:
    """Product id -> trend score from recent real engagement and orders. Cached briefly."""
    key = f"shop:trending:{days}"
    if (cached := cache.get(key)) is not None:
        return cached
    since = timezone.now() - timedelta(days=days)
    scores: dict = {}
    rows = (CustomerActivity.objects.filter(created_at__gte=since, verb__in=SIGNAL_WEIGHTS, object_type="catalog.product")
            .values("verb", "object_id").annotate(n=Count("id")))
    for r in rows:
        scores[r["object_id"]] = scores.get(r["object_id"], 0) + SIGNAL_WEIGHTS[r["verb"]] * r["n"]
    ordered = (OrderItem.objects.filter(order__created_at__gte=since, product__isnull=False)
               .exclude(order__status=OrderStatus.CANCELLED).values("product_id").annotate(q=Sum("quantity")))
    for r in ordered:
        scores[r["product_id"]] = scores.get(r["product_id"], 0) + 4 * r["q"]
    scores = {k: v for k, v in scores.items() if v >= TRENDING_MIN_SCORE}
    cache.set(key, scores, BADGE_CACHE_SECONDS)
    return scores


def best_seller_ids() -> set:
    """The top sellers of each top-level category (at least 3 units sold), so the badge means something per category."""
    key = "shop:bestsellers"
    if (cached := cache.get(key)) is not None:
        return cached
    ids: set = set()
    rows = listings().filter(units_sold__gte=3).values("id", "units_sold", "shop_category_id", "shop_category__parent_id")
    by_top: dict = {}
    for r in rows:
        by_top.setdefault(r["shop_category__parent_id"] or r["shop_category_id"], []).append(r)
    for rs in by_top.values():
        ids |= {r["id"] for r in sorted(rs, key=lambda r: -r["units_sold"])[:3]}
    cache.set(key, ids, BADGE_CACHE_SECONDS)
    return ids


def badges_for(p, *, trending: dict, best: set) -> list[str]:
    """Badges backed by data/rules only: best_seller, trending, new, top_rated, limited_deal."""
    out = []
    if p.pk in best:
        out.append("best_seller")
    if p.pk in trending:
        out.append("trending")
    deal = getattr(p, "_active_deal", None)
    if deal is not None and (deal.kind == "flash" or deal.quantity_limit is not None):
        out.append("limited_deal")
    if float(p.rating_average) >= TOP_RATED_MIN and p.rating_count >= TOP_RATED_MIN_COUNT:
        out.append("top_rated")
    if p.created_at >= timezone.now() - timedelta(days=NEW_FOR_DAYS):
        out.append("new")
    return out[:2]


def order_by_sort(qs, sort: str, *, relevance=None):
    orders = {
        "popular": ["-units_sold", "-rating_count", "id"],
        "price_asc": ["eff_price", "id"],
        "price_desc": ["-eff_price", "id"],
        "rating": ["-rating_average", "-rating_count", "id"],
        "newest": ["-created_at", "id"],
        "discount": ["-discount_pct", "id"],
    }
    if sort == "relevance" and relevance is not None:
        return qs.annotate(_rel=relevance).order_by("-_rel", "-units_sold", "id")
    return qs.order_by(*orders.get(sort, orders["popular"]))


def affinity_rank(qs, category_ids, brand_ids):
    """1 for listings in the customer's preferred categories/brands, else 0 (for a personal feed order)."""
    if not category_ids and not brand_ids:
        return qs.annotate(affinity=Value(0, output_field=IntegerField()))
    return qs.annotate(affinity=Case(
        When(Q(shop_category_id__in=category_ids) | Q(shop_category__parent_id__in=category_ids) | Q(brand_ref_id__in=brand_ids), then=Value(1)),
        default=Value(0), output_field=IntegerField()))
