"""
Buddy's action layer. The AI (or Buddy basic mode) never touches the database: it can only *propose* one of these typed
actions; the customer's app sends it here; this module validates every argument on the server (types, ownership,
listing/stock/state), checks the permission tier and runs it through the same Click services the app itself uses.

  safe      runs immediately            open_page, wishlist_add, cart_add, cart_remove
  confirm   needs the customer's tap    book_service (a request; paid only after the work), cancel_order
            on a summary the server
            built; expires in 10 min
  high      never through Buddy         account/security/payment-method changes — Buddy opens the page instead

Payments are never an action: Buddy opens the normal checkout, where the customer pays. Every run is recorded in
ActionExecution (args, tier, outcome) for audit.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.core.api.exceptions import ConflictError, DomainError

from .models import ActionExecution, Conversation

CONFIRM_TTL = timedelta(minutes=10)

# In-app routes Buddy may open (anything else is refused). Dynamic segments are UUIDs or slugs.
ROUTES = [r"/", r"/explore", r"/food", r"/rides", r"/shopping", r"/groceries", r"/groceries/lists", r"/groceries/buy-again", r"/groceries/basket",
          r"/parcels", r"/parcels/history", r"/services", r"/services/bookings", r"/events", r"/events/mine", r"/events/plan", r"/hotels",
          r"/hotels/bookings", r"/showtime", r"/buzz", r"/offers", r"/orders", r"/wishlist", r"/rewards", r"/wallet", r"/notifications",
          r"/account", r"/account/addresses", r"/account/payments", r"/account/card", r"/settings", r"/help", r"/help/new", r"/activity", r"/cart",
          r"/checkout", r"/bookings", r"/tickets", r"/search",
          r"/(orders|rides|parcels|tickets|bookings|services/bookings|services/pro|events/providers|events/plans|events/bookings|hotels|hotels/bookings|products)/[0-9a-fA-F-]{36}",
          r"/(stores|showtime|services|groceries/store)/[a-z0-9-]+"]
_ROUTE_RE = re.compile(r"^(?:" + "|".join(ROUTES) + r")$")


def allowed_path(path: str) -> bool:
    base = (path or "").split("?")[0].split("#")[0]
    return bool(_ROUTE_RE.match(base)) and len(path) < 500


@dataclass
class Spec:
    key: str
    tier: str
    schema: type[serializers.Serializer]
    run: Callable
    describe: Callable | None = None  # builds the server-side confirmation summary


# --- schemas & handlers ----------------------------------------------------------------------------------------------

class OpenPage(serializers.Serializer):
    path = serializers.CharField(max_length=500)

    def validate_path(self, v):
        if not allowed_path(v):
            raise serializers.ValidationError("Buddy can’t open that page.")
        return v


def _open_page(customer, a):
    return {"navigate": a["path"], "message": "Opening it for you."}


class WishlistAdd(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["product", "store", "provider", "event_provider", "hotel"])
    id = serializers.UUIDField()


def _wishlist_add(customer, a):
    from apps.wishlists.models import WishlistItem

    kind, pk = a["kind"], a["id"]
    if kind == "product":
        from apps.catalog.views import public_products
        obj = public_products().filter(pk=pk).first()
    elif kind == "store":
        from apps.stores.views import public_stores
        obj = public_stores().filter(pk=pk).first()
    elif kind == "provider":
        from apps.professionals.engine import listed
        obj = listed().filter(pk=pk).first()
    elif kind == "event_provider":
        from apps.eventhub.engine import listed as ev
        obj = ev().filter(pk=pk).first()
    else:
        from apps.hotels.models import HotelProperty
        obj = HotelProperty.objects.filter(pk=pk, is_listed=True).first()
    if obj is None:
        raise DomainError("That isn’t available on Click any more.", code="not_found", status_code=404)
    item, created = WishlistItem.objects.get_or_create(customer=customer, **{kind: obj})
    name = getattr(obj, "name", None) or getattr(getattr(obj, "partner", None), "business_name", "it")
    return {"message": f"Saved {name} to your wishlist." if created else f"{name} is already in your wishlist.", "wishlist_id": str(item.id)}


class CartAdd(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, max_value=20, default=1)


def _cart_add(customer, a):
    from apps.carts import services as carts

    with transaction.atomic():
        item = carts.add_item(customer, a["product_id"], a["quantity"])
    p = item.product
    return {"message": f"Added {a['quantity']} × {p.name} ({p.store.name}) to your cart. Nothing is ordered until you check out.",
            "cart_item_id": str(item.id), "undo": {"action": "cart_remove", "args": {"item_id": str(item.id)}},
            "next": {"label": "View cart", "path": "/groceries/basket" if item.cart.mode == "basket" else "/cart"}}


class CartRemove(serializers.Serializer):
    item_id = serializers.UUIDField()


def _cart_remove(customer, a):
    from apps.carts import services as carts
    from apps.carts.models import CartItem

    item = CartItem.objects.filter(pk=a["item_id"], cart__customer=customer).select_related("product").first()
    if item is None:
        raise DomainError("That item isn’t in your cart.", code="not_found", status_code=404)
    name = item.product.name
    with transaction.atomic():
        carts.remove_item(item)
    return {"message": f"Removed {name} from your cart."}


class BookService(serializers.Serializer):
    provider_id = serializers.UUIDField()
    job_id = serializers.UUIDField()
    address_id = serializers.UUIDField(required=False, allow_null=True)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


def _service_args(customer, a) -> dict:
    addr = (customer.addresses.filter(pk=a["address_id"]).first() if a.get("address_id")
            else customer.addresses.filter(is_default=True).first() or customer.addresses.first())
    if addr is None:
        raise DomainError("Add an address in Profile → Addresses first.", code="address_required")
    return {"job_id": a["job_id"], "provider_id": a["provider_id"], "address_id": addr.id, "mode": "now", "scheduled_start": None, "hours": None}


def _describe_service(customer, a) -> str:
    from apps.professionals import lifecycle

    est = lifecycle.estimate(customer, _service_args(customer, a))
    if not est["bookable"]:
        raise ConflictError(est["problem"] or "This can’t be booked right now.", code="not_bookable")
    price = f"estimated ₹{est['estimated_total']} incl. tax" if est["estimated_total"] else "quoted after inspection"
    return (f"Request {est['job']['name']} now ({price}). You pay only after the work is done; free to cancel until "
            f"the professional is on the way.")


def _book_service(customer, a):
    from apps.professionals import lifecycle

    data = _service_args(customer, a)
    est = lifecycle.estimate(customer, data)
    b, _ = lifecycle.book(customer, {**data, "description": a.get("description") or "Requested through Buddy", "attachment_ids": [],
                                     "expected_amount": est["agreed"], "idempotency_key": str(uuid.uuid4()), "rebook_of": None})
    return {"message": f"Request {b.number} sent. You’ll be notified when the professional accepts.", "navigate": f"/services/bookings/{b.id}"}


class CancelOrder(serializers.Serializer):
    order_id = serializers.UUIDField()
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True, default="Cancelled through Buddy")


def _order(customer, a):
    o = customer.orders.filter(pk=a["order_id"]).select_related("store").first()
    if o is None:
        raise DomainError("Order not found.", code="not_found", status_code=404)
    return o


def _describe_cancel(customer, a) -> str:
    from apps.orders.models import CUSTOMER_CANCELLABLE

    o = _order(customer, a)
    if o.status not in CUSTOMER_CANCELLABLE:
        raise ConflictError("This order can no longer be cancelled.", code="order_not_cancellable")
    return f"Cancel order {o.number} from {o.store.name} (₹{o.total})? Wallet payments are refunded to your Click. Wallet."


def _cancel_order(customer, a):
    from apps.orders.services import cancel_by_customer

    o = _order(customer, a)
    cancel_by_customer(o, user=customer.user, reason=a.get("reason") or "Cancelled through Buddy")
    return {"message": f"Order {o.number} cancelled.", "navigate": f"/orders/{o.id}"}


REGISTRY: dict[str, Spec] = {s.key: s for s in [
    Spec("open_page", "safe", OpenPage, _open_page),
    Spec("wishlist_add", "safe", WishlistAdd, _wishlist_add),
    Spec("cart_add", "safe", CartAdd, _cart_add),
    Spec("cart_remove", "safe", CartRemove, _cart_remove),
    Spec("book_service", "confirm", BookService, _book_service, _describe_service),
    Spec("cancel_order", "confirm", CancelOrder, _cancel_order, _describe_cancel),
]}
HIGH_RISK = {"change_phone", "delete_account", "change_payment_method", "change_security"}


def request(customer, key: str, args: dict, conversation: Conversation | None = None) -> ActionExecution:
    """Validate and run a safe action, or prepare a confirmation-required one."""
    if key in HIGH_RISK:
        raise DomainError("Buddy can’t do account or security changes. Open Profile → Settings to do it yourself.", code="action_not_allowed",
                          status_code=403)
    spec = REGISTRY.get(key)
    if spec is None:
        raise DomainError("Buddy can’t do that.", code="unknown_action", status_code=400)
    s = spec.schema(data=args or {})
    s.is_valid(raise_exception=True)
    clean = {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in s.validated_data.items()}
    if spec.tier == "confirm":
        summary = spec.describe(customer, clean)
        return ActionExecution.objects.create(customer=customer, conversation=conversation, action=key, tier="confirm", args=clean,
                                              status=ActionExecution.Status.AWAITING, summary=summary[:300], expires_at=timezone.now() + CONFIRM_TTL)
    return _execute(customer, spec, clean, ActionExecution(customer=customer, conversation=conversation, action=key, tier=spec.tier, args=clean))


def _execute(customer, spec: Spec, args: dict, run: ActionExecution) -> ActionExecution:
    try:
        result = spec.run(customer, args)
        run.status = ActionExecution.Status.CONFIRMED if run.tier == "confirm" else ActionExecution.Status.DONE
        run.result, run.summary = result, (result.get("message") or run.summary)[:300]
    except DomainError as e:
        run.status, run.error = ActionExecution.Status.FAILED, str(e.detail)[:300]
        run.result = {"message": str(e.detail), "code": e.error_code}
    run.save()
    return run


def confirm(customer, run_id) -> ActionExecution:
    with transaction.atomic():
        run = ActionExecution.objects.select_for_update().filter(pk=run_id, customer=customer).first()
        if run is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        if run.status != ActionExecution.Status.AWAITING:
            raise ConflictError("This was already handled.", code="action_closed")
        if run.expires_at and run.expires_at <= timezone.now():
            run.status = ActionExecution.Status.EXPIRED
            run.save(update_fields=["status", "updated_at"])
            raise ConflictError("This confirmation expired. Ask Buddy again.", code="action_expired")
        return _execute(customer, REGISTRY[run.action], run.args, run)


def cancel(customer, run_id) -> ActionExecution:
    run = ActionExecution.objects.filter(pk=run_id, customer=customer, status=ActionExecution.Status.AWAITING).first()
    if run is None:
        raise DomainError("Not found.", code="not_found", status_code=404)
    run.status = ActionExecution.Status.CANCELLED
    run.save(update_fields=["status", "updated_at"])
    return run


def out(run: ActionExecution) -> dict:
    return {"id": str(run.id), "action": run.action, "tier": run.tier, "status": run.status, "summary": run.summary, "result": run.result,
            "error": run.error, "expires_at": run.expires_at.isoformat() if run.expires_at else None}
