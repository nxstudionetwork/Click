"""
Shopping lists and "Find everything": match each list line to real listings at the stores that deliver to the
customer, then show the store that covers the most of the list (and, if no single store has everything, a split
across stores). Ranking weighs coverage first, then total cost including delivery, then delivery time and distance —
never price alone. Nothing is added to the basket until the customer chooses.
"""

from __future__ import annotations

from decimal import Decimal

from apps.catalog.pricing import attach_deals, price_of

from . import catalog as cat
from .search import _singular, matching_categories, text_filter, tokens


def _match(line, store_ids):
    """Per store, the best in-stock listing for one list line (a chosen product, or the words typed)."""
    qs = cat.orderable_listings().filter(store_id__in=store_ids)
    if line.item_id:
        qs = qs.filter(grocery_item_id=line.item_id)
    else:
        words = tokens(line.text)
        if not words:
            return {}
        cats = matching_categories(words)
        named = qs.filter(text_filter(words))
        qs = named if named.exists() or not cats else qs.filter(grocery_item__category__in=cats)
    rows = list(qs[:300])
    attach_deals(rows)
    words = [_singular(w) for w in tokens(line.text)]
    best: dict = {}
    for p in rows:
        name = p.grocery_item.name.lower()
        score = (-sum(w in name for w in words), -p.units_sold, price_of(p).price)
        if p.store_id not in best or score < best[p.store_id][0]:
            best[p.store_id] = (score, p)
    return {sid: p for sid, (_, p) in best.items()}


def find_everything(shopping_list, point) -> dict:
    lines = [li for li in shopping_list.items.all() if not li.is_done]
    stores = cat.deliverable_stores(point)
    usable = {sid: h for sid, h in stores.items() if h["deliverable"]} if point is not None else {}
    ids = list(usable)
    matches = {li.id: _match(li, ids) for li in lines}
    ctx = {"stores": usable}

    per_store = []
    for sid, h in usable.items():
        found = [(li, matches[li.id][sid]) for li in lines if sid in matches[li.id]]
        if not found:
            continue
        subtotal = sum((price_of(p).price * li.quantity for li, p in found), Decimal("0"))
        fee = Decimal(h["delivery_fee"] or "0")
        per_store.append({"h": h, "found": found, "subtotal": subtotal, "fee": fee})

    def rank(s):
        return (-len(s["found"]), s["subtotal"] + s["fee"], s["h"]["eta_min"] or 999, s["h"]["distance_km"] or 99)

    per_store.sort(key=rank)

    def store_out(s, only=None):
        found = [(li, p) for li, p in s["found"] if only is None or li.id in only]
        sub = sum((price_of(p).price * li.quantity for li, p in found), Decimal("0"))
        st = s["h"]["store"]
        return {
            "store": {"id": str(st.id), "slug": st.slug, "name": st.name, "eta_label": s["h"]["eta_label"],
                      "distance_km": s["h"]["distance_km"], "status": s["h"]["status"], "delivery_fee": s["h"]["delivery_fee"],
                      "min_order": f"{st.min_order_amount:.2f}" if st.min_order_amount else None},
            "items": [{"line_id": str(li.id), "text": li.text, "quantity": li.quantity, "listing": card}
                      for (li, _), card in zip(found, cat.cards([p for _, p in found], ctx))],
            "found": len(found), "subtotal": f"{sub:.2f}",
            "estimated_total": f"{sub + s['fee']:.2f}",
        }

    best = store_out(per_store[0]) if per_store else None
    split = []
    if per_store and per_store[0]["found"] and len(per_store[0]["found"]) < len(lines):
        remaining = {li.id for li in lines}
        pool = list(per_store)
        while remaining and pool:
            pool.sort(key=lambda s: (-len({li.id for li, _ in s["found"]} & remaining), s["subtotal"] + s["fee"]))
            top = pool.pop(0)
            covers = {li.id for li, _ in top["found"]} & remaining
            if not covers:
                break
            split.append(store_out(top, covers))
            remaining -= covers
    covered = {li.id for s in per_store for li, _ in s["found"]}
    return {
        "has_location": point is not None, "lines": len(lines),
        "best": best, "complete": bool(best and best["found"] == len(lines)),
        "split": split if len(split) > 1 else [],
        "stores": [store_out(s) for s in per_store[:6]],
        "missing": [{"line_id": str(li.id), "text": li.text} for li in lines if li.id not in covered],
    }
