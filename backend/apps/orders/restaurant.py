"""
Click Partner — Restaurant mode services.

Everything a restaurant runs from Click Partner beyond the shared order queue (apps.orders.partner_workspace):
the menu customers order from, kitchen operations (preparation time, busy, temporary closure), the kitchen board,
order history and search, offers (reviewed by Click before customers see them) and insights.

All of it reads and writes the same records the Customer App uses (Store, MenuCategory, Product, option groups,
Order, StoreOffer), so a change here is what customers see on their next request. The restaurant is always resolved
from the signed-in user; a store id from the client only selects among stores this partner operates.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Avg, Count, F, Max, Q, Sum
from django.db.models.functions import Lower
from django.utils import timezone

from apps.catalog.models import MenuCategory, Product, ProductOption, ProductOptionGroup
from apps.core.api.exceptions import ConflictError, DomainError
from apps.partners.workspace.base import BUSINESS_TZ, day_bounds, local_today, money, pct
from apps.stores.models import Store, StoreOffer, StoreType

from .models import Order, OrderItem, OrderReview, OrderStatus as S, OrderStatusEvent

MODE = "restaurant"
MAX_PRICE = Decimal("100000")
MAX_DELTA = Decimal("10000")
BUSY_CHOICES = (10, 20, 30)
PAUSE_CHOICES = (15, 30, 60, 120, 240)
PAUSE_REASONS = {
    "busy": "Kitchen is very busy", "staff": "Short on staff", "stock": "Running low on ingredients",
    "closing": "Closing soon", "technical": "Technical issue", "other": "Temporarily closed",
}
ORDER_FILTERS = {
    "new": [S.PLACED], "accepted": [S.CONFIRMED], "preparing": [S.PREPARING], "ready": [S.READY],
    "completed": [S.OUT_FOR_DELIVERY, S.DELIVERED], "cancelled": [S.CANCELLED],
}
PAGE_SIZE = 20


# --- access ------------------------------------------------------------------------------------------------------

def _mode_of(partner) -> str:
    from apps.partners.services import configuration_for

    return configuration_for(partner.category)["home"].get("mode", "")


def require_restaurant(user, store_id=None) -> tuple:
    """(partner, store) for the signed-in restaurant partner. Other partner types get 403 whatever the frontend shows."""
    from apps.partners.services import require_owned_partner

    partner = require_owned_partner(user)
    if not partner.is_onboarded:
        raise DomainError("Finish setting up your Partner profile first.", code="onboarding_incomplete", status_code=409)
    if _mode_of(partner) != MODE:
        raise DomainError("Restaurant tools are only for restaurant partners.", code="not_restaurant", status_code=403)
    stores = Store.objects.filter(partner_link__partner=partner, store_type=StoreType.RESTAURANT).order_by("created_at")
    store = stores.filter(pk=store_id).first() if store_id else stores.first()
    if store is None:
        if store_id and stores.exists():
            raise DomainError("Restaurant not found.", code="not_found", status_code=404)
        raise DomainError("Your restaurant isn’t listed on Click yet. Once Click verifies you and connects your restaurant, "
                          "you can manage it here.", code="not_connected", status_code=409)
    release_due(store)
    return partner, store


def store_summary(store: Store, partner) -> dict:
    return {
        "id": str(store.id), "name": store.name, "slug": store.slug, "city": store.city, "locality": store.locality,
        "image_url": store.image_url, "is_accepting_orders": store.is_accepting_orders,
        "operations": operations_state(store),
        "stores": [{"id": str(s.id), "name": s.name} for s in
                   Store.objects.filter(partner_link__partner=partner, store_type=StoreType.RESTAURANT).order_by("created_at")],
    }


# --- operations: preparation time, busy, temporary closure --------------------------------------------------------

def operations_state(store: Store) -> dict:
    now = timezone.now()
    busy = bool(store.busy_until and store.busy_until > now and store.busy_extra_minutes)
    paused = bool(store.paused_until and store.paused_until > now)
    state = "paused" if paused else "closed" if not store.is_accepting_orders else "busy" if busy else "open"
    return {
        "state": state,
        "label": {"paused": "Temporarily closed", "closed": "Closed", "busy": "Busy right now", "open": "Open"}[state],
        "prep_time_minutes": store.prep_time_minutes,
        "busy_extra_minutes": store.busy_extra_minutes if busy else 0,
        "busy_until": store.busy_until.isoformat() if busy else None,
        "paused_until": store.paused_until.isoformat() if paused else None,
        "pause_reason": store.pause_reason if paused else "",
        "delivery_window": f"{store.delivery_time_min}–{store.delivery_time_max} min",
        "busy_choices": list(BUSY_CHOICES), "pause_choices": list(PAUSE_CHOICES),
        "pause_reasons": [{"key": k, "label": v} for k, v in PAUSE_REASONS.items()],
    }


def _set_partner_open(store: Store, is_open: bool, actor, note: str) -> None:
    from apps.partners.models import Partner, PartnerAvailabilityEvent

    link = getattr(store, "partner_link", None)
    if link is None:
        return
    partner = Partner.objects.select_for_update().get(pk=link.partner_id)
    if partner.is_available != is_open:
        partner.is_available = is_open
        partner.save(update_fields=["is_available", "updated_at"])
        PartnerAvailabilityEvent.objects.create(partner=partner, is_available=is_open, actor=actor, note=note[:120])


def _end_busy(store: Store) -> list[str]:
    if not store.busy_extra_minutes:
        store.busy_until = None
        return ["busy_until"]
    extra = store.busy_extra_minutes
    store.delivery_time_min = max(store.delivery_time_min - extra, 1)
    store.delivery_time_max = max(store.delivery_time_max - extra, store.delivery_time_min)
    store.busy_extra_minutes, store.busy_until = 0, None
    return ["delivery_time_min", "delivery_time_max", "busy_extra_minutes", "busy_until"]


def release_due(store: Store | None = None) -> int:
    """End busy periods and temporary closures whose time is up (idempotent). Reopening restores ordering for customers."""
    now = timezone.now()
    qs = Store.objects.filter(Q(busy_until__lte=now) | Q(paused_until__lte=now))
    if store is not None:
        if not ((store.busy_until and store.busy_until <= now) or (store.paused_until and store.paused_until <= now)):
            return 0
        qs = qs.filter(pk=store.pk)
    done = 0
    for sid in list(qs.values_list("pk", flat=True)):
        with transaction.atomic():
            s = Store.objects.select_for_update(of=("self",)).select_related("partner_link").get(pk=sid)
            fields: list[str] = []
            if s.busy_until and s.busy_until <= now:
                fields += _end_busy(s)
            if s.paused_until and s.paused_until <= now:
                s.paused_until, s.pause_reason, s.is_accepting_orders = None, "", True
                fields += ["paused_until", "pause_reason", "is_accepting_orders"]
                _set_partner_open(s, True, None, "Reopened automatically after a temporary closure")
            if fields:
                s.save(update_fields=[*set(fields), "updated_at"])
                done += 1
    if store is not None and done:
        store.refresh_from_db()
    return done


def on_manual_availability(store_ids, is_available: bool) -> None:
    """Open/Close from Partner Home replaces any temporary closure (a manual Close is indefinite)."""
    Store.objects.filter(id__in=store_ids).exclude(paused_until=None).update(paused_until=None, pause_reason="")
    if not is_available:
        for s in Store.objects.filter(id__in=store_ids).exclude(busy_extra_minutes=0):
            with transaction.atomic():
                s = Store.objects.select_for_update().get(pk=s.pk)
                s.save(update_fields=[*_end_busy(s), "updated_at"])


@transaction.atomic
def update_operations(store: Store, data: dict, actor) -> Store:
    store = Store.objects.select_for_update(of=("self",)).select_related("partner_link").get(pk=store.pk)
    action = data.get("action")
    now = timezone.now()
    if action == "prep_time":
        minutes = _int(data.get("minutes"), "minutes")
        if not 5 <= minutes <= 90:
            raise _invalid("minutes", "Preparation time must be between 5 and 90 minutes.")
        store.prep_time_minutes = minutes
        store.save(update_fields=["prep_time_minutes", "updated_at"])
    elif action == "busy":
        extra, hours = _int(data.get("minutes"), "minutes"), _int(data.get("for_minutes", 60), "for_minutes")
        if extra not in BUSY_CHOICES:
            raise _invalid("minutes", "Choose 10, 20 or 30 extra minutes.")
        if hours not in (30, 60, 120):
            raise _invalid("for_minutes", "Choose 30 minutes, 1 hour or 2 hours.")
        if not store.is_accepting_orders:
            raise ConflictError("Open your restaurant first.", code="restaurant_closed")
        _end_busy(store)  # replace, never stack
        store.busy_extra_minutes, store.busy_until = extra, now + timedelta(minutes=hours)
        store.delivery_time_min += extra
        store.delivery_time_max += extra
        store.save(update_fields=["delivery_time_min", "delivery_time_max", "busy_extra_minutes", "busy_until", "updated_at"])
    elif action == "not_busy":
        store.save(update_fields=[*_end_busy(store), "updated_at"])
    elif action == "pause":
        minutes = _int(data.get("for_minutes"), "for_minutes")
        reason = PAUSE_REASONS.get(str(data.get("reason", "other")))
        if minutes not in PAUSE_CHOICES:
            raise _invalid("for_minutes", "Choose how long to close for.")
        if reason is None:
            raise _invalid("reason", "Choose a reason.")
        store.paused_until, store.pause_reason, store.is_accepting_orders = now + timedelta(minutes=minutes), reason, False
        store.save(update_fields=["paused_until", "pause_reason", "is_accepting_orders", "updated_at"])
        _set_partner_open(store, False, actor, f"Temporarily closed: {reason}")
    elif action == "resume":
        store.paused_until, store.pause_reason, store.is_accepting_orders = None, "", True
        store.save(update_fields=["paused_until", "pause_reason", "is_accepting_orders", "updated_at"])
        _set_partner_open(store, True, actor, "Reopened")
    else:
        raise _invalid("action", "Unknown operation.")
    return store


# --- menu --------------------------------------------------------------------------------------------------------

def _option_groups(p: Product) -> list:
    return [{"id": str(g.id), "name": g.name, "min_select": g.min_select, "max_select": g.max_select,
             "options": [{"id": str(o.id), "name": o.name, "price_delta": money(o.price_delta), "is_available": o.is_available}
                         for o in g.options.all()]} for g in p.option_groups.all()]


def item_dict(p: Product) -> dict:
    return {
        "id": str(p.id), "category_id": str(p.category_id) if p.category_id else None, "name": p.name,
        "description": p.description, "image_url": p.image_url, "price": money(p.price), "dietary": p.dietary,
        "is_available": p.is_available, "is_active": p.is_active, "is_featured": p.is_featured, "position": p.position,
        "units_sold": p.units_sold, "rating_average": float(p.rating_average or 0), "rating_count": p.rating_count,
        "option_groups": _option_groups(p),
    }


def menu(store: Store) -> dict:
    products = list(Product.objects.filter(store=store).prefetch_related("option_groups__options")
                    .order_by("position", "name"))
    by_cat: dict = {}
    for p in products:
        by_cat.setdefault(p.category_id, []).append(item_dict(p))
    cats = [{"id": str(c.id), "name": c.name, "position": c.position, "is_active": c.is_active, "items": by_cat.get(c.id, [])}
            for c in MenuCategory.objects.filter(store=store).order_by("position", "name")]
    live = [p for p in products if p.is_active]
    return {
        "categories": cats, "uncategorised": by_cat.get(None, []),
        "counts": {"items": len(live), "available": sum(1 for p in live if p.is_available),
                   "unavailable": sum(1 for p in live if not p.is_available), "hidden": len(products) - len(live)},
        "dietary": [{"key": k, "label": v} for k, v in Product.Dietary.choices],
    }


def _clean_name(value, field="name", max_len=80) -> str:
    name = " ".join(str(value or "").split())
    if len(name) < 2:
        raise _invalid(field, "Enter a name (at least 2 characters).")
    if len(name) > max_len:
        raise _invalid(field, f"Keep it under {max_len} characters.")
    return name


@transaction.atomic
def create_category(store: Store, data: dict) -> MenuCategory:
    name = _clean_name(data.get("name"))
    if MenuCategory.objects.filter(store=store, name__iexact=name).exists():
        raise ConflictError(f"“{name}” is already on your menu.", code="duplicate")
    position = (MenuCategory.objects.filter(store=store).aggregate(m=Max("position"))["m"] or 0) + 1
    return MenuCategory.objects.create(store=store, name=name, position=position)


@transaction.atomic
def update_category(store: Store, category_id, data: dict) -> MenuCategory:
    cat = MenuCategory.objects.select_for_update().filter(store=store, pk=category_id).first()
    if cat is None:
        raise DomainError("Category not found.", code="not_found", status_code=404)
    fields = []
    if "name" in data:
        name = _clean_name(data["name"])
        if MenuCategory.objects.filter(store=store, name__iexact=name).exclude(pk=cat.pk).exists():
            raise ConflictError(f"“{name}” is already on your menu.", code="duplicate")
        cat.name = name
        fields.append("name")
    if "is_active" in data:
        cat.is_active = bool(data["is_active"])
        fields.append("is_active")
    if fields:
        cat.save(update_fields=[*fields, "updated_at"])
    return cat


@transaction.atomic
def delete_category(store: Store, category_id) -> None:
    cat = MenuCategory.objects.filter(store=store, pk=category_id).first()
    if cat is None:
        raise DomainError("Category not found.", code="not_found", status_code=404)
    if Product.objects.filter(category=cat).exists():
        raise ConflictError("Move or remove the items in this category first.", code="category_not_empty")
    cat.delete()


def _reorder(qs, ids) -> None:
    if not isinstance(ids, list) or not ids:
        raise _invalid("ids", "Send the new order.")
    owned = {str(i) for i in qs.values_list("pk", flat=True)}
    ids = [str(i) for i in ids]
    if set(ids) != owned or len(ids) != len(owned):
        raise ConflictError("Your menu changed on another device. Refresh and try again.", code="stale_menu")
    for position, pk in enumerate(ids, start=1):
        qs.filter(pk=pk).update(position=position, updated_at=timezone.now())


@transaction.atomic
def reorder_categories(store: Store, ids) -> None:
    _reorder(MenuCategory.objects.filter(store=store), ids)


@transaction.atomic
def reorder_items(store: Store, category_id, ids) -> None:
    if not MenuCategory.objects.filter(store=store, pk=category_id).exists():
        raise DomainError("Category not found.", code="not_found", status_code=404)
    _reorder(Product.objects.filter(store=store, category_id=category_id), ids)


def _money(value, field, *, minimum=Decimal("0"), maximum=MAX_PRICE, allow_zero=False) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise _invalid(field, "Enter a valid amount.")
    if amount < minimum or amount > maximum or (amount == 0 and not allow_zero):
        raise _invalid(field, f"Enter an amount between ₹{max(minimum, Decimal('1')):,.0f} and ₹{maximum:,.0f}.")
    return amount


def _clean_groups(groups) -> list[dict]:
    if groups in (None, ""):
        return []
    if not isinstance(groups, list) or len(groups) > 6:
        raise _invalid("option_groups", "Add up to 6 option groups.")
    cleaned, seen = [], set()
    for gi, g in enumerate(groups):
        name = _clean_name(g.get("name"), f"option_groups.{gi}.name", 60)
        if name.lower() in seen:
            raise _invalid(f"option_groups.{gi}.name", "Each option group needs a different name.")
        seen.add(name.lower())
        options = g.get("options") or []
        if not isinstance(options, list) or not 1 <= len(options) <= 20:
            raise _invalid(f"option_groups.{gi}.options", "Add between 1 and 20 choices.")
        opts, opt_names = [], set()
        for oi, o in enumerate(options):
            oname = _clean_name(o.get("name"), f"option_groups.{gi}.options.{oi}.name", 60)
            if oname.lower() in opt_names:
                raise _invalid(f"option_groups.{gi}.options.{oi}.name", "Choices in a group need different names.")
            opt_names.add(oname.lower())
            opts.append({"name": oname, "price_delta": _money(o.get("price_delta", 0) or 0, f"option_groups.{gi}.options.{oi}.price_delta",
                                                               maximum=MAX_DELTA, allow_zero=True),
                         "is_available": o.get("is_available", True) is not False})
        min_s, max_s = _int(g.get("min_select", 0), "min_select"), _int(g.get("max_select", 1), "max_select")
        if not (0 <= min_s <= max_s and 1 <= max_s <= len(opts)):
            raise _invalid(f"option_groups.{gi}.max_select", "Choose how many options customers can pick (at least 1, at most the number of choices).")
        cleaned.append({"name": name, "min_select": min_s, "max_select": max_s, "options": opts})
    return cleaned


def _save_groups(product: Product, groups: list[dict]) -> None:
    product.option_groups.all().delete()  # order items keep their own snapshot (options_summary), so history is safe
    for gp, g in enumerate(groups, start=1):
        group = ProductOptionGroup.objects.create(product=product, name=g["name"], min_select=g["min_select"],
                                                  max_select=g["max_select"], position=gp)
        ProductOption.objects.bulk_create([ProductOption(group=group, position=op, **o) for op, o in enumerate(g["options"], start=1)])


def _clean_item(store: Store, data: dict, *, partial: bool, current: Product | None = None) -> dict:
    out: dict = {}
    if not partial or "name" in data:
        out["name"] = _clean_name(data.get("name"), max_len=150)
        dup = Product.objects.filter(store=store).annotate(n=Lower("name")).filter(n=out["name"].lower())
        if current is not None:
            dup = dup.exclude(pk=current.pk)
        if dup.exists():
            raise ConflictError(f"“{out['name']}” is already on your menu.", code="duplicate")
    if not partial or "category_id" in data:
        cat = MenuCategory.objects.filter(store=store, pk=data.get("category_id")).first() if data.get("category_id") else None
        if cat is None:
            raise _invalid("category_id", "Choose a menu category.")
        out["category"] = cat
    if not partial or "price" in data:
        out["price"] = _money(data.get("price"), "price")
        if current is not None and current.compare_at_price is not None and current.compare_at_price <= out["price"]:
            out["compare_at_price"] = None  # keep the "was" price honest
    if "description" in data:
        desc = " ".join(str(data.get("description") or "").split())
        if len(desc) > 300:
            raise _invalid("description", "Keep the description under 300 characters.")
        out["description"] = desc
    if "image_url" in data:
        url = str(data.get("image_url") or "").strip()
        if url and not (url.startswith("https://") and len(url) <= 500):
            raise _invalid("image_url", "Use an https:// image link.")
        out["image_url"] = url
    if "dietary" in data:
        if data["dietary"] not in Product.Dietary.values:
            raise _invalid("dietary", "Choose veg, non-veg, vegan or not specified.")
        out["dietary"] = data["dietary"]
    for flag in ("is_available", "is_featured", "is_active"):
        if flag in data:
            out[flag] = bool(data[flag])
    if "option_groups" in data:
        out["option_groups"] = _clean_groups(data["option_groups"])
    return out


@transaction.atomic
def create_item(store: Store, data: dict) -> Product:
    clean = _clean_item(store, data, partial=False)
    groups = clean.pop("option_groups", [])
    position = (Product.objects.filter(store=store, category=clean["category"]).aggregate(m=Max("position"))["m"] or 0) + 1
    product = Product.objects.create(store=store, position=position, **clean)
    _save_groups(product, groups)
    return product


@transaction.atomic
def update_item(store: Store, item_id, data: dict) -> Product:
    product = Product.objects.select_for_update().filter(store=store, pk=item_id).first()  # ownership check
    if product is None:
        raise DomainError("Menu item not found.", code="not_found", status_code=404)
    clean = _clean_item(store, data, partial=True, current=product)
    groups = clean.pop("option_groups", None)
    if "category" in clean and clean["category"].pk != product.category_id:
        clean["position"] = (Product.objects.filter(store=store, category=clean["category"]).aggregate(m=Max("position"))["m"] or 0) + 1
    for k, v in clean.items():
        setattr(product, k, v)
    if clean:
        product.save()
    if groups is not None:
        _save_groups(product, groups)
    return Product.objects.prefetch_related("option_groups__options").get(pk=product.pk)


# --- orders: history, search, kitchen ----------------------------------------------------------------------------

def _provider(partner):
    from apps.partners.workspace import provider_for

    return provider_for(partner)


def search_orders(partner, store: Store, params) -> dict:
    status = params.get("status", "all")
    qs = (Order.objects.filter(store=store).exclude(status=S.AWAITING_PAYMENT)
          .select_related("store", "customer__user").prefetch_related("items", "payments"))
    if status in ORDER_FILTERS:
        qs = qs.filter(status__in=ORDER_FILTERS[status])
    q = "".join(str(params.get("q", "")).split()).upper()[:20]
    if q:
        qs = qs.filter(number__icontains=q)
    if day := params.get("date"):
        try:
            d = date.fromisoformat(str(day))
        except ValueError:
            raise _invalid("date", "Use a date like 2026-11-17.")
        start, end = day_bounds(d)
        qs = qs.filter(created_at__gte=start, created_at__lt=end)
    try:
        page = max(int(params.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1
    total = qs.count()
    rows = qs.order_by("created_at" if status in ("new", "accepted", "preparing", "ready") else "-created_at")
    rows = rows[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
    provider = _provider(partner)
    counts = dict(Order.objects.filter(store=store).values_list("status").annotate(n=Count("id")).values_list("status", "n"))
    return {
        "items": [provider._item(o).as_dict() for o in rows], "page": page, "page_size": PAGE_SIZE, "total": total,
        "has_more": page * PAGE_SIZE < total,
        "filters": [{"key": "all", "label": "All", "count": None}] + [
            {"key": k, "label": k.capitalize(), "count": sum(counts.get(s, 0) for s in v) if k in ("new", "accepted", "preparing", "ready") else None}
            for k, v in ORDER_FILTERS.items()],
    }


def kitchen(partner, store: Store) -> dict:
    """The kitchen board: one column per stage, oldest first, with a target ready time for each order."""
    provider = _provider(partner)
    orders = list(Order.objects.filter(store=store, status__in=[S.PLACED, S.CONFIRMED, S.PREPARING, S.READY])
                  .select_related("store", "customer__user").prefetch_related("items", "payments").order_by("created_at")[:80])
    accepted_at = dict(OrderStatusEvent.objects.filter(order__in=orders, to_status=S.CONFIRMED)
                       .values_list("order_id").annotate(t=Max("created_at")).values_list("order_id", "t"))
    ready_at = dict(OrderStatusEvent.objects.filter(order__in=orders, to_status=S.READY)
                    .values_list("order_id").annotate(t=Max("created_at")).values_list("order_id", "t"))
    prep = store.prep_time_minutes + (store.busy_extra_minutes or 0)
    now = timezone.now()
    columns: dict[str, list] = {"new": [], "accepted": [], "preparing": [], "ready": []}
    key = {S.PLACED: "new", S.CONFIRMED: "accepted", S.PREPARING: "preparing", S.READY: "ready"}
    for o in orders:
        card = provider._item(o).as_dict()
        target = (accepted_at.get(o.id) + timedelta(minutes=prep)) if accepted_at.get(o.id) else None
        card["kitchen"] = {
            "lines": [{"quantity": i.quantity, "name": i.product_name, "options": i.options_summary, "note": i.note} for i in o.items.all()],
            "note": o.customer_note, "order_type": "Delivery",
            "placed_at": o.created_at.isoformat(),
            "ready_by": target.isoformat() if target and o.status in (S.CONFIRMED, S.PREPARING) else None,
            "late": bool(target and o.status in (S.CONFIRMED, S.PREPARING) and now > target),
            "ready_at": ready_at[o.id].isoformat() if o.id in ready_at else None,
            "handover": "Waiting for the delivery partner" if o.status == S.READY else "",
        }
        columns[key[o.status]].append(card)
    return {"columns": [{"key": k, "label": {"new": "New", "accepted": "Accepted", "preparing": "Preparing", "ready": "Ready"}[k],
                         "items": v} for k, v in columns.items()],
            "prep_time_minutes": prep, "operations": operations_state(store)}


# --- offers ------------------------------------------------------------------------------------------------------

def offer_dict(o: StoreOffer) -> dict:
    now = timezone.now()
    if o.review_status != StoreOffer.Review.APPROVED:
        state = o.review_status
    elif o.paused_by_partner:
        state = "paused"
    elif o.ends_at and o.ends_at < now:
        state = "ended"
    elif o.starts_at and o.starts_at > now:
        state = "scheduled"
    else:
        state = "live" if o.is_active else "inactive"
    labels = {"pending": "Waiting for Click review", "rejected": "Not approved", "paused": "Paused", "ended": "Ended",
              "scheduled": "Scheduled", "live": "Live for customers", "inactive": "Inactive"}
    return {"id": str(o.id), "title": o.title, "description": o.description, "discount_type": o.discount_type,
            "discount_value": money(o.discount_value), "max_discount": money(o.max_discount) if o.max_discount is not None else None,
            "min_order_amount": money(o.min_order_amount), "starts_at": o.starts_at.isoformat() if o.starts_at else None,
            "ends_at": o.ends_at.isoformat() if o.ends_at else None, "state": state, "state_label": labels[state],
            "review_note": o.review_note, "created_by_partner": o.created_by_partner}


def offers(store: Store) -> list:
    return [offer_dict(o) for o in StoreOffer.objects.filter(store=store).order_by("-created_at")]


def _when(value, field):
    if value in (None, ""):
        return None
    try:
        d = datetime.fromisoformat(str(value))
    except ValueError:
        raise _invalid(field, "Enter a valid date and time.")
    return d if d.tzinfo else d.replace(tzinfo=BUSINESS_TZ)


@transaction.atomic
def create_offer(store: Store, data: dict) -> StoreOffer:
    """Every value is validated here; the offer reaches customers only after Click approves it."""
    title = _clean_name(data.get("title"), "title", 80)
    if StoreOffer.objects.filter(store=store, title__iexact=title).exclude(review_status=StoreOffer.Review.REJECTED).exists():
        raise ConflictError(f"You already have an offer called “{title}”.", code="duplicate")
    kind = data.get("discount_type")
    if kind not in ("percent", "flat", "free_delivery"):
        raise _invalid("discount_type", "Choose percent off, flat amount off or free delivery.")
    min_order = _money(data.get("min_order_amount", 0) or 0, "min_order_amount", allow_zero=True, maximum=Decimal("50000"))
    value, cap = Decimal("0"), None
    if kind == "percent":
        value = Decimal(_int(data.get("discount_value"), "discount_value"))
        if not 5 <= value <= 60:
            raise _invalid("discount_value", "Percent offers must be between 5% and 60%.")
        cap = _money(data.get("max_discount"), "max_discount", maximum=Decimal("1000")) if data.get("max_discount") not in (None, "") else None
    elif kind == "flat":
        value = _money(data.get("discount_value"), "discount_value", maximum=Decimal("1000"))
        if value * 2 > min_order:
            raise _invalid("min_order_amount", "For a flat discount, the minimum order must be at least twice the discount.")
    starts, ends = _when(data.get("starts_at"), "starts_at"), _when(data.get("ends_at"), "ends_at")
    now = timezone.now()
    if ends is None:
        raise _invalid("ends_at", "Choose when the offer ends.")
    if ends <= max(starts or now, now) or ends - (starts or now) > timedelta(days=90):
        raise _invalid("ends_at", "The offer must end after it starts, within 90 days.")
    desc = " ".join(str(data.get("description") or "").split())[:200]
    return StoreOffer.objects.create(
        store=store, title=title, description=desc, discount_type=kind, discount_value=value, max_discount=cap,
        min_order_amount=min_order, starts_at=starts, ends_at=ends, is_active=False,
        review_status=StoreOffer.Review.PENDING, created_by_partner=True)


@transaction.atomic
def set_offer_paused(store: Store, offer_id, paused: bool) -> StoreOffer:
    o = StoreOffer.objects.select_for_update().filter(store=store, pk=offer_id).first()
    if o is None:
        raise DomainError("Offer not found.", code="not_found", status_code=404)
    if o.review_status != StoreOffer.Review.APPROVED:
        raise ConflictError("Only approved offers can be paused or resumed.", code="offer_not_approved")
    o.paused_by_partner, o.is_active = paused, not paused
    o.save(update_fields=["paused_by_partner", "is_active", "updated_at"])
    return o


def review_offer(offer: StoreOffer, approve: bool, note: str = "") -> None:
    """Click staff decision (Business OS / admin). Approval makes the offer visible to customers."""
    offer.review_status = StoreOffer.Review.APPROVED if approve else StoreOffer.Review.REJECTED
    offer.is_active = approve and not offer.paused_by_partner
    offer.review_note = note[:200]
    offer.save(update_fields=["review_status", "is_active", "review_note", "updated_at"])
    link = getattr(offer.store, "partner_link", None)
    if link is not None:
        from apps.partners.notifications import notify_partner

        notify_partner(link.partner, "account", f"Offer {'approved' if approve else 'not approved'}: {offer.title}",
                       "Customers can now see it." if approve else (note or "Edit the terms and submit it again."), "/restaurant/offers")


# --- insights ----------------------------------------------------------------------------------------------------

def insights(store: Store, days: int) -> dict:
    today = local_today()
    start, end = day_bounds(today - timedelta(days=days - 1))[0], day_bounds(today)[1]
    placed = Order.objects.filter(store=store, created_at__gte=start, created_at__lt=end).exclude(status=S.AWAITING_PAYMENT)
    valid = placed.exclude(status=S.CANCELLED)
    agg = valid.aggregate(n=Count("id"), gross=Sum("subtotal"), total=Sum("total"), discount=Sum("discount"))
    cancelled = placed.filter(status=S.CANCELLED).count()
    rejected = OrderStatusEvent.objects.filter(order__in=placed, from_status=S.PLACED, to_status=S.CANCELLED).exclude(
        actor_id=F("order__customer__user_id")).count()
    completed = placed.filter(status__in=[S.OUT_FOR_DELIVERY, S.DELIVERED]).count()
    n_all = placed.count()

    def window(d):
        s = day_bounds(today - timedelta(days=d - 1))[0]
        return money(Order.objects.filter(store=store, created_at__gte=s, created_at__lt=end)
                     .exclude(status__in=[S.CANCELLED, S.AWAITING_PAYMENT]).aggregate(t=Sum("total"))["t"] or 0)

    # Preparation: accepted -> ready, from the status log only.
    acc = dict(OrderStatusEvent.objects.filter(order__in=placed, to_status=S.CONFIRMED).values_list("order_id", "created_at"))
    rdy = dict(OrderStatusEvent.objects.filter(order__in=placed, to_status=S.READY).values_list("order_id", "created_at"))
    prep = [(rdy[k] - acc[k]).total_seconds() / 60 for k in rdy if k in acc and rdy[k] > acc[k]]
    on_time = sum(1 for m in prep if m <= store.prep_time_minutes + 5)

    lines = (OrderItem.objects.filter(order__in=valid).values("product_id", "product_name")
             .annotate(qty=Sum("quantity"), revenue=Sum("line_total")).order_by("-qty"))
    best = [{"name": r["product_name"], "quantity": r["qty"], "revenue": money(r["revenue"])} for r in lines[:5]]
    sold_ids = {r["product_id"] for r in lines}
    not_selling = list(Product.objects.filter(store=store, is_active=True).exclude(id__in=sold_ids)
                       .order_by("name").values_list("name", flat=True)[:5])
    unavailable = list(Product.objects.filter(store=store, is_active=True, is_available=False).order_by("name").values_list("name", flat=True)[:10])

    reviews = OrderReview.objects.filter(store=store, created_at__gte=start)
    r_agg = reviews.aggregate(avg=Avg("rating"), n=Count("id"))
    repeat = (valid.values("customer_id").annotate(n=Count("id")).filter(n__gt=1).count())
    customers = valid.values("customer_id").distinct().count()
    return {
        "days": days,
        "sales": {"today": window(1), "week": window(7), "month": window(30)},
        "orders": {"total": n_all, "completed": completed, "cancelled": cancelled, "rejected": rejected,
                   "average_value": money((agg["total"] or 0) / agg["n"]) if agg["n"] else None},
        "money": {"gross_sales": money(agg["gross"] or 0), "discounts": money(agg["discount"] or 0), "order_value": money(agg["total"] or 0)},
        "operations": {"average_prep_minutes": round(sum(prep) / len(prep)) if prep else None,
                       "on_time_rate": pct(on_time, len(prep)), "target_minutes": store.prep_time_minutes,
                       "acceptance_rate": pct(n_all - rejected, n_all) if n_all else None,
                       "cancellation_rate": pct(cancelled, n_all) if n_all else None},
        "menu": {"best_sellers": best, "not_selling": not_selling, "unavailable": unavailable},
        "customers": {"rating": round(float(r_agg["avg"]), 1) if r_agg["n"] else None, "ratings": r_agg["n"],
                      "store_rating": float(store.rating_average) if store.rating_count else None,
                      "repeat_customers": repeat, "customers": customers,
                      "recent_feedback": [{"rating": r.rating, "comment": r.comment, "at": r.created_at.isoformat()}
                                          for r in reviews.exclude(comment="").order_by("-created_at")[:5]]},
        "note": "Sales are order values of orders placed (cancelled orders excluded). Click commission and payouts aren’t set up yet.",
    }


# --- helpers -----------------------------------------------------------------------------------------------------

def _invalid(field: str, message: str) -> DomainError:
    return DomainError(message, code="validation_error", details={field: [message]})


def _int(value, field) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise _invalid(field, "Enter a whole number.")
