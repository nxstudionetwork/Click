"""
Shopping personalisation from the customer's own Click. records only: products they viewed (last 60 days),
saved to their wishlist, or bought. No sensitive data, nothing inferred about the person; with no history the
sections say so and fall back to popular listings.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta

from django.utils import timezone

from apps.activity.models import CustomerActivity
from apps.catalog.models import Product
from apps.orders.models import OrderItem, OrderStatus
from apps.stores.models import StoreType
from apps.wishlists.models import WishlistItem

VIEW_WINDOW_DAYS = 60


@dataclass
class Signals:
    viewed: list = field(default_factory=list)     # product ids, most recent first
    wishlist: list = field(default_factory=list)
    bought: list = field(default_factory=list)     # delivered retail purchases, most recent first
    categories: list = field(default_factory=list) # leaf category ids by weight
    brands: list = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.viewed or self.wishlist or self.bought)


def signals(customer) -> Signals:
    if customer is None:
        return Signals()
    since = timezone.now() - timedelta(days=VIEW_WINDOW_DAYS)
    viewed = list(dict.fromkeys(CustomerActivity.objects.filter(
        customer=customer, verb="product.viewed", object_type="catalog.product", created_at__gte=since)
        .order_by("-created_at").values_list("object_id", flat=True)[:50]))
    wishlist = list(WishlistItem.objects.filter(customer=customer, product__isnull=False).order_by("-created_at").values_list("product_id", flat=True)[:50])
    bought = list(dict.fromkeys(OrderItem.objects.filter(
        order__customer=customer, order__status=OrderStatus.DELIVERED, order__store__store_type=StoreType.RETAIL, product__isnull=False)
        .order_by("-order__created_at").values_list("product_id", flat=True)[:50]))
    weights: Counter = Counter()
    brand_weights: Counter = Counter()
    rows = Product.objects.filter(pk__in=set(viewed) | set(wishlist) | set(bought), shop_category__isnull=False).values_list(
        "id", "shop_category_id", "brand_ref_id")
    for pid, cat, brand in rows:
        w = (3 if pid in bought else 0) + (2 if pid in wishlist else 0) + (1 if pid in viewed else 0)
        weights[cat] += w
        if brand:
            brand_weights[brand] += w
    return Signals(viewed, wishlist, bought, [c for c, _ in weights.most_common(4)], [b for b, _ in brand_weights.most_common(3)])
