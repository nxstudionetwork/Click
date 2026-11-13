"""
Grocery basket pricing and checkout checks. A basket can hold items from several local stores; each store's part is
priced and delivered on its own (its minimum order, its delivery mode and slot, its distance-based fee) and becomes its
own order. `prepare_basket` runs inside `orders.services.place_checkout`'s transaction, so a failure in any store's
part creates nothing and charges nothing.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.carts.services import offer_discount, seller_groups
from apps.catalog.models import Product
from apps.catalog.pricing import price_of
from apps.core.api.exceptions import ConflictError, DomainError
from apps.stores.models import Store

from . import delivery as dl
from .models import GroceryOrderDetails

TWO = Decimal("0.01")
SUBSTITUTIONS = {c for c, _ in GroceryOrderDetails.Substitution.choices}


def price_changes(items) -> list[dict]:
    out = []
    for i in items:
        now = price_of(i.product, i.variant).price
        if i.price_seen is not None and now != i.price_seen:
            out.append({"item_id": str(i.id), "name": i.product.name, "from": f"{i.price_seen:.2f}", "to": f"{now:.2f}"})
    return out


def _apply(g, opt: dl.Option, slot: dict | None, dist):
    g.delivery_fee = opt.fee
    if g.offer is not None:
        g.discount = offer_discount(g.offer, g.subtotal, g.delivery_fee)
    g.total = max(g.subtotal + g.delivery_fee + g.tax - g.discount, Decimal("0")).quantize(TWO)
    now = timezone.now()
    start = datetime.fromisoformat(slot["start"]) if slot else None
    end = datetime.fromisoformat(slot["end"]) if slot else None
    g.grocery = {"mode": opt.mode, "slot_start": start, "slot_end": end, "distance_km": dist,
                 "eta_min": opt.eta_min, "eta_max": opt.eta_max}
    g.estimated_at = end if end else now + timedelta(minutes=opt.eta_max or 60)


def _choose(res: dict, choice: dict | None):
    """The option the customer chose, validated; or (None, reason)."""
    objs = {o.mode: o for o in res["_objects"]}
    mode = (choice or {}).get("mode")
    if mode not in objs:
        return None, None, "Choose how you'd like this delivered."
    opt = objs[mode]
    if not opt.available:
        return None, None, opt.reason or "This delivery option isn't available."
    slot = None
    if mode == "scheduled":
        wanted = (choice or {}).get("slot_start")
        try:
            wanted_dt = datetime.fromisoformat(str(wanted)) if wanted else None
        except ValueError:
            wanted_dt = None
        slot = next((s for s in opt.slots if wanted_dt and datetime.fromisoformat(s["start"]) == wanted_dt), None)
        if slot is None:
            return None, None, "That delivery slot is no longer available. Choose another."
    return opt, slot, ""


def prepare_basket(cart, groups, address, grocery: dict) -> None:
    items = [i for g in groups for i in g.items]
    if changes := price_changes(items):
        raise ConflictError("Some prices changed since you added them. Review your basket to continue.",
                            code="price_changed", details={"items": changes})
    substitution = grocery.get("substitution") or GroceryOrderDetails.Substitution.NONE
    if substitution not in SUBSTITUTIONS:
        raise DomainError("Choose what the store should do if an item is unavailable.", code="invalid_substitution")
    choices = grocery.get("delivery") or {}
    point = dl.address_point(address)
    for g in groups:
        store = Store.objects.select_for_update().get(pk=g.store.pk)  # serialises slot capacity per store
        store._prefetched_objects_cache = {"hours": list(store.hours.all())}
        res = dl.options(store, point, g.subtotal)
        if res["status"]["state"] == "unavailable":
            raise ConflictError(f"{store.name} is currently unavailable.", code="store_unavailable",
                                details={"store_id": str(store.id), "store": store.name})
        opt, slot, problem = _choose(res, choices.get(str(store.id)))
        if opt is None:
            raise ConflictError(f"{store.name}: {problem}", code="delivery_unavailable",
                                details={"store_id": str(store.id), "store": store.name})
        _apply(g, opt, slot, res["distance_km"])
        g.grocery.update(substitution=substitution, substitution_note=(grocery.get("substitution_note") or "")[:200])


def record_details(order, g) -> None:
    info = g.grocery
    GroceryOrderDetails.objects.create(
        order=order, delivery_mode=info["mode"], slot_start=info["slot_start"], slot_end=info["slot_end"],
        substitution=info.get("substitution", "none"), substitution_note=info.get("substitution_note", ""),
        distance_km=Decimal(str(info["distance_km"])) if info["distance_km"] is not None else None,
        eta_min=info["eta_min"], eta_max=info["eta_max"],
    )


def alternatives(item, point, limit: int = 3) -> list[Product]:
    """For an unavailable line: the same product (same item and size) at other stores, else similar items here."""
    from .catalog import orderable_listings

    p = item.product
    out = []
    if p.grocery_item_id:
        out = list(orderable_listings().filter(grocery_item_id=p.grocery_item_id).exclude(store_id=p.store_id)
                   .select_related("store", "grocery_item")[:limit])
    if len(out) < limit and p.grocery_item_id:
        out += list(orderable_listings().filter(store_id=p.store_id, grocery_item__category_id=p.grocery_item.category_id)
                    .exclude(pk=p.pk).select_related("store", "grocery_item").order_by("-units_sold")[: limit - len(out)])
    return out


def basket(cart, address, choices: dict | None = None) -> dict:
    """The basket priced for an address: per store its status, delivery options (default: the first available),
    the chosen option's fee, minimum-order gap and total; plus price changes and unavailable lines."""
    from apps.carts.services import cart_items

    items = cart_items(cart)
    groups = seller_groups(cart, items) if items else []
    point = dl.address_point(address)
    choices = choices or {}
    stores = []
    grand = Decimal("0")
    ready = bool(groups)
    for g in groups:
        res = dl.options(g.store, point, g.subtotal)
        choice = choices.get(str(g.store.id))
        if not choice:
            first = next((o for o in res["_objects"] if o.available and o.mode != "scheduled"), None) or \
                next((o for o in res["_objects"] if o.available), None)
            choice = {"mode": first.mode, "slot_start": first.slots[0]["start"] if first and first.slots else None} if first else None
        opt, slot, problem = _choose(res, choice)
        if opt is not None:
            _apply(g, opt, slot, res["distance_km"])
        else:
            ready = False
        below = max(g.store.min_order_amount - g.subtotal, Decimal("0"))
        if below > 0:
            ready = False
        grand += g.total
        stores.append({
            "store_id": str(g.store.id), "status": res["status"], "distance_km": res["distance_km"],
            "options": res["options"], "choice": choice, "problem": problem,
            "subtotal": f"{g.subtotal:.2f}", "delivery_fee": f"{g.delivery_fee:.2f}", "tax": f"{g.tax:.2f}",
            "discount": f"{g.discount:.2f}", "total": f"{g.total:.2f}", "offer_title": g.offer.title if g.offer and g.discount else "",
            "minimum_remaining": f"{below:.2f}" if below > 0 else None,
            "free_delivery_remaining": (f"{g.store.free_delivery_above - g.subtotal:.2f}"
                                        if g.store.free_delivery_above is not None and g.subtotal < g.store.free_delivery_above else None),
        })
    unavailable = []
    for i in items:
        ok = (i.product.is_orderable and i.product.store.is_open)
        if not ok:
            ready = False
            unavailable.append({"item_id": str(i.id), "name": i.product.name,
                                "reason": "Out of stock" if not i.product.in_stock else "No longer available from this store",
                                "alternatives": [str(p.id) for p in alternatives(i, point)]})
    changes = price_changes(items)
    if changes:
        ready = False
    return {"stores": stores, "price_changes": changes, "unavailable": unavailable, "total": f"{grand:.2f}",
            "ready": ready and address is not None, "has_location": point is not None}
