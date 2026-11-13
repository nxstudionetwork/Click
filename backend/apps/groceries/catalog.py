"""Grocery listings (store-owned products) and how they are shown. Prices always come from apps.catalog.pricing."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.db.models import F, Q
from rest_framework import serializers

from apps.catalog.models import Product
from apps.catalog.pricing import attach_deals, price_of
from apps.stores.models import Store, StoreType

from . import delivery as dl
from .models import GroceryCategory, GroceryItem

LOW_STOCK = 5


def grocery_stores():
    return Store.objects.filter(store_type=StoreType.GROCERY, status=Store.Status.ACTIVE).prefetch_related("hours")


def visible_listings():
    """Every live grocery listing customers may see (including out-of-stock ones, shown as such)."""
    return (Product.objects.filter(store__store_type=StoreType.GROCERY, store__status=Store.Status.ACTIVE, is_active=True,
                                   grocery_item__isnull=False, grocery_item__is_active=True, grocery_item__category__is_active=True)
            .select_related("store", "grocery_item", "grocery_item__category"))


def orderable_listings():
    return visible_listings().filter(is_available=True, store__is_accepting_orders=True).filter(
        Q(stock_quantity__isnull=True) | Q(stock_quantity__gt=0))


def deliverable_stores(point, now=None) -> dict:
    """{store_id: headline} for active grocery stores that can deliver to `point` (any mode, now or by slot).
    Without a point no store is claimed deliverable; callers show stores without delivery promises."""
    out = {}
    for s in grocery_stores().select_related("grocery"):
        h = dl.headline(s, point, now)
        h["store"] = s
        out[s.id] = h
    if point is None:
        return out
    return {k: v for k, v in out.items() if v["deliverable"]}


def per_unit(item: GroceryItem, price: Decimal) -> str | None:
    basis = item.unit_basis()
    if not basis or item.size_unit in ("pc",) and item.size_value == 1:
        return None
    qty, label, per = basis
    if qty <= 0:
        return None
    value = (price / qty * per).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    if label == "pc":
        return f"₹{value:.1f}/pc".replace(".0/", "/")
    return f"₹{value:.0f}/{label}"


class ListingSerializer(serializers.Serializer):
    """A store's listing of a grocery item. Contract: `GroceryListing` in packages/api/src/groceries.ts."""

    def to_representation(self, p: Product) -> dict:
        item, price = p.grocery_item, price_of(p)
        in_stock = p.is_available and p.in_stock
        today = dl.now_local().date()
        ctx = self.context or {}
        headline = (ctx.get("stores") or {}).get(p.store_id)
        return {
            "id": str(p.id), "item_id": str(item.id), "name": item.name, "brand": item.brand, "size": item.size_label,
            "category": {"slug": item.category.slug, "name": item.category.name},
            "price": f"{price.price:.2f}", "mrp": f"{price.reference:.2f}" if price.reference else None,
            "discount_percent": price.discount_percent, "deal_ends_at": price.deal.ends_at.isoformat() if price.deal else None,
            "per_unit": per_unit(item, price.price),
            "in_stock": in_stock, "orderable": in_stock and p.store.is_accepting_orders,
            "stock_left": p.stock_quantity if in_stock and p.stock_quantity is not None and p.stock_quantity <= LOW_STOCK else None,
            "image_url": item.image_url or p.image_url, "image_credit": item.image_credit if item.image_url else "",
            "dietary": item.dietary, "attributes": item.attributes,
            "variable_weight": p.variable_weight,
            "fresh_today": bool(p.received_on and p.received_on == today and in_stock),
            "received_on": p.received_on.isoformat() if p.received_on else None,
            "rating": {"average": f"{p.rating_average:.1f}", "count": p.rating_count} if p.rating_count else None,
            "store": {"id": str(p.store_id), "slug": p.store.slug, "name": p.store.name,
                      "eta_label": headline["eta_label"] if headline else "", "is_open": p.store.is_accepting_orders},
        }


def cards(products, context=None) -> list[dict]:
    products = list(products)
    attach_deals(products)
    return ListingSerializer(products, many=True, context=context or {}).data


def best_per_item(listings, prefer=None) -> list[Product]:
    """One listing per grocery item: in stock first, then cheapest, then the preferred order of stores."""
    rank = {sid: i for i, sid in enumerate(prefer or [])}
    attach_deals(listings)
    best: dict = {}
    for p in listings:
        key = p.grocery_item_id
        score = (0 if p.is_orderable and p.store.is_accepting_orders else 1, price_of(p).price, rank.get(p.store_id, 999))
        if key not in best or score < best[key][0]:
            best[key] = (score, p)
    return [p for _, p in best.values()]


def category_tree():
    return GroceryCategory.objects.filter(is_active=True)


def popular_first(qs):
    return qs.order_by(F("units_sold").desc(), "grocery_item__name")
