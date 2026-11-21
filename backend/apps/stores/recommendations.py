"""
Store recommendations for a signed-in customer. Transparent rules, not AI: each result says why it was picked.

1. Cuisines/categories the customer has ordered from before (most-ordered first) → open stores in those
   categories, best rated first.
2. Without order history (or to fill up): open, well-rated stores, labelled as such.
Optionally limited to stores near a point (same haversine query as discovery).
"""

from collections import Counter

from apps.orders.models import Order

from .geo import with_distance
from .views import public_stores


def recommend_stores(customer, store_type: str, limit: int = 10, near: dict | None = None) -> list[dict]:
    base = public_stores().filter(store_type=store_type, is_accepting_orders=True)
    if near:
        base = with_distance(base, near["lat"], near["lng"]).filter(distance_km__lte=near["radius"])

    history = Counter()
    ordered_store_ids = set()
    for o in Order.objects.filter(customer=customer, store__store_type=store_type).prefetch_related("store__categories")[:50]:
        ordered_store_ids.add(o.store_id)
        for c in o.store.categories.all():
            history[(c.slug, c.name)] += 1

    picked: list[dict] = []
    seen: set = set()
    for (slug, name), _ in history.most_common(4):
        for s in base.filter(categories__slug=slug).exclude(pk__in=seen).order_by("-rating_average", "-rating_count")[:4]:
            reason = f"Because you ordered {name}" + (" here before" if s.id in ordered_store_ids else "")
            picked.append({"store": s, "reason": reason})
            seen.add(s.id)
            if len(picked) >= limit:
                return picked
    for s in base.exclude(pk__in=seen).filter(rating_count__gt=0).order_by("-rating_average", "-rating_count")[: limit - len(picked)]:
        picked.append({"store": s, "reason": "Highly rated on Click."})
    return picked
