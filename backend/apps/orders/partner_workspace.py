"""
Partner Home workspace for restaurants, grocery/retail stores and local businesses: the orders customers place at the
storefronts this partner operates (apps.partners.PartnerStore), using the same Order records and the same status
machine (services.transition_order) as the Customer App, so every partner action reaches the customer's order page.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, F, Sum
from django.utils import timezone

from apps.catalog.models import Product
from apps.core.api.exceptions import DomainError
from apps.partners.workspace.base import (
    BUSINESS_TZ, Action, Metric, Provider, QuickAction, WorkItem, day_bounds, money, pct,
)
from apps.stores.models import Store, StoreType

from . import services
from .models import Order, OrderStatus as S, OrderStatusEvent

LOW_STOCK = 5
# Shopping's packed/shipped steps exist only where the marketplace order flow is installed; without them retail
# orders follow the confirmed -> preparing -> ready flow like groceries.
PACKED = getattr(S, "PACKED", None)
SHIPPED = getattr(S, "SHIPPED", None)
PREPARING_STATES = [s for s in (S.CONFIRMED, S.PREPARING, PACKED) if s]
READY_STATES = [s for s in (S.READY, SHIPPED) if s]
IN_PROGRESS = PREPARING_STATES + READY_STATES
HANDED_OVER = [S.OUT_FOR_DELIVERY, S.DELIVERED]


def _flow(store_type: str) -> dict[str, tuple[str, Action]]:
    """Next partner step per status: {current status: (target status, action)}. Delivery itself isn't the store's step."""
    common = {S.PLACED: (S.CONFIRMED, Action("accept", "Accept order", "primary"))}
    if store_type == StoreType.RETAIL and PACKED and SHIPPED:
        return {**common,
                S.CONFIRMED: (PACKED, Action("packed", "Mark packed", "primary")),
                PACKED: (SHIPPED, Action("shipped", "Mark shipped", "primary")),
                SHIPPED: (S.OUT_FOR_DELIVERY, Action("handover", "Handed to delivery", "primary",
                                                       confirm="Confirm the parcel is with the delivery partner."))}
    prepare = "Start preparing" if store_type == StoreType.RESTAURANT else "Start packing"
    return {**common,
            S.CONFIRMED: (S.PREPARING, Action("preparing", prepare, "primary")),
            S.PREPARING: (S.READY, Action("ready", "Mark ready", "primary")),
            S.READY: (S.OUT_FOR_DELIVERY, Action("handover", "Handed to delivery", "primary",
                                                 confirm="Confirm the order has been picked up for delivery."))}


def _status_label(order: Order) -> str:
    if order.status == S.PREPARING and order.store.store_type != StoreType.RESTAURANT:
        return "Packing"
    return {S.PLACED: "New order", S.CONFIRMED: "Accepted", S.OUT_FOR_DELIVERY: "With delivery"}.get(
        order.status, order.get_status_display())


class OrdersProvider(Provider):
    kind = "orders"

    def _store_ids(self) -> list:
        if not hasattr(self, "_ids"):
            self._ids = list(Store.objects.filter(partner_link__partner=self.partner).values_list("id", flat=True))
        return self._ids

    def _orders(self):
        return (Order.objects.filter(store_id__in=self._store_ids())
                .select_related("store", "customer__user").prefetch_related("items", "payments"))

    def connection(self):
        if self._store_ids():
            return "live", ""
        noun = {"food": "restaurant", "retail": "store"}.get(self.partner.partner_type.slug, "business")
        return "not_connected", (f"Your {noun} isn’t listed on Click yet. Once Click verifies you and connects your "
                                 f"storefront, customer orders will appear here.")

    # --- availability ------------------------------------------------------------------------------
    def on_availability_changed(self, is_available: bool) -> None:
        # This is what customers see: the storefront stops (or starts) accepting orders right away.
        Store.objects.filter(id__in=self._store_ids()).update(is_accepting_orders=is_available, updated_at=timezone.now())

    # --- items ------------------------------------------------------------------------------------
    def _item(self, o: Order) -> WorkItem:
        items = list(o.items.all())
        count = sum(i.quantity for i in items)
        lines = ", ".join(f"{i.quantity} × {i.product_name}" + (f" ({i.options_summary})" if i.options_summary else "")
                          for i in items[:6]) + (" …" if len(items) > 6 else "")
        pay = next(iter(o.payments.all()), None)
        addr = o.delivery_address or {}
        name = (o.customer.user.full_name or "").split()
        flow = _flow(o.store.store_type)
        actions = []
        if o.status in flow:
            actions.append(flow[o.status][1])
        if o.status == S.PLACED:
            actions.append(Action("reject", "Reject", "danger", needs_reason=True,
                                  confirm="The customer will be told the order was declined and won’t be charged."))
        tone = ("urgent" if o.status == S.PLACED else "success" if o.status in HANDED_OVER
                else "muted" if o.status == S.CANCELLED else "active")
        multi = len(self._store_ids()) > 1
        return WorkItem(
            kind="order", id=str(o.id), ref=o.number, title=f"Order {o.number}",
            subtitle=f"{count} item{'s' if count != 1 else ''}" + (f" · {o.store.name}" if multi else ""),
            status=o.status, status_label=_status_label(o), tone=tone, at=o.created_at, amount=o.total, currency=o.currency,
            fields=[("Items", lines), ("Customer", name[0] if name else ""),
                    ("Deliver to", ", ".join(x for x in [addr.get("line2") or addr.get("line1"), addr.get("city")] if x)),
                    ("Note", o.customer_note), ("Payment", (pay.get_method_display() if pay else "")),
                    ("Placed", timezone.localtime(o.created_at, BUSINESS_TZ).strftime("%I:%M %p").lstrip("0"))],
            actions=actions,
        )

    def _low_stock(self):
        return (Product.objects.filter(store_id__in=self._store_ids(), is_active=True, stock_quantity__isnull=False,
                                       stock_quantity__lte=LOW_STOCK).select_related("store").order_by("stock_quantity", "name"))

    def _stock_item(self, p: Product) -> WorkItem:
        out = p.stock_quantity == 0
        return WorkItem(kind="stock", id=str(p.id), ref=p.name, title=p.name,
                        subtitle="Out of stock" if out else f"Only {p.stock_quantity} left",
                        status="out_of_stock" if out else "low_stock", status_label="Out of stock" if out else "Low stock",
                        tone="urgent" if out else "info", fields=[("Price", f"₹{p.price:.0f}"), ("Unit", p.unit_label)],
                        link="/work?view=inventory")

    # --- Home sections ----------------------------------------------------------------------------
    def action_required(self):
        new = [self._item(o) for o in self._orders().filter(status=S.PLACED).order_by("created_at")[:10]]
        stock = [self._stock_item(p) for p in self._low_stock().filter(stock_quantity=0)[:3]]
        return new + stock

    def active(self):
        return [self._item(o) for o in self._orders().filter(status__in=IN_PROGRESS).order_by("created_at")[:10]]

    def _placed_between(self, start, end):
        return self._orders().filter(created_at__gte=start, created_at__lt=end).exclude(status=S.CANCELLED)

    def metrics(self, day):
        start, end = day_bounds(day)
        today = self._placed_between(start, end)
        agg = today.aggregate(n=Count("id"), total=Sum("total"))
        items = today.aggregate(q=Sum("items__quantity"))["q"] or 0
        completed = self._orders().filter(status__in=HANDED_OVER, events__to_status=S.OUT_FOR_DELIVERY,
                                          events__created_at__gte=start, events__created_at__lt=end).distinct().count()
        pending = self._orders().filter(status__in=[S.PLACED, *IN_PROGRESS]).count()
        return {
            "orders": Metric("orders", "Orders", agg["n"], str(agg["n"]), "Placed today"),
            "sales": Metric("sales", "Sales", money(agg["total"]), f"₹{(agg['total'] or 0):,.0f}", "Order value today"),
            "items_sold": Metric("items_sold", "Items sold", items, str(items), "Today"),
            "completed": Metric("completed", "Completed", completed, str(completed), "Handed over today"),
            "pending": Metric("pending", "Pending", pending, str(pending), "Waiting or in progress"),
        }

    def earnings(self, start, end):
        agg = self._placed_between(start, end).aggregate(total=Sum("total"), n=Count("id"))
        return agg["total"] or Decimal("0"), agg["n"]

    def earnings_note(self):
        return ("Order value of orders placed (cancelled orders excluded), including delivery fee and tax. "
                "Click commission and payouts aren’t set up yet.")

    def earnings_count_label(self):
        return "orders"

    def earnings_recent(self, start, end, limit=20):
        return [{"ref": o.number, "title": f"Order {o.number}", "amount": money(o.total), "at": o.created_at.isoformat(),
                 "detail": _status_label(o)} for o in self._placed_between(start, end).order_by("-created_at")[:limit]]

    def performance(self):
        since = timezone.now() - timedelta(days=30)
        rating = Store.objects.filter(id__in=self._store_ids()).aggregate(avg=Avg("rating_average"), n=Sum("rating_count"))
        events = OrderStatusEvent.objects.filter(order__store_id__in=self._store_ids(), created_at__gte=since)
        accepted = events.filter(to_status=S.CONFIRMED).count()
        rejected = events.filter(from_status=S.PLACED, to_status=S.CANCELLED).exclude(actor_id=F("order__customer__user_id")).count()
        # Fulfilment: of the orders accepted in the period that are finished, how many were handed over (in-progress
        # orders don't count either way).
        accepted_orders = Order.objects.filter(store_id__in=self._store_ids(), events__to_status=S.CONFIRMED,
                                               events__created_at__gte=since).distinct()
        handed = accepted_orders.filter(status__in=HANDED_OVER).count()
        failed = accepted_orders.filter(status=S.CANCELLED).count()
        acc = pct(accepted, accepted + rejected)
        ful = pct(handed, handed + failed)
        has_rating = bool(rating["n"])
        return {
            "rating": Metric("rating", "Rating", float(rating["avg"]) if has_rating else None,
                             f"{rating['avg']:.1f}★" if has_rating else "No ratings yet", f"{rating['n'] or 0} ratings"),
            "acceptance_rate": Metric("acceptance_rate", "Acceptance", acc, f"{acc}%" if acc is not None else "—",
                                      "Orders accepted, last 30 days"),
            "fulfilment_rate": Metric("fulfilment_rate", "Fulfilment", ful, f"{ful}%" if ful is not None else "—",
                                      "Accepted orders handed over (finished orders, last 30 days)"),
        }

    def activity(self, limit=8):
        events = (OrderStatusEvent.objects.filter(order__store_id__in=self._store_ids())
                  .select_related("order").order_by("-created_at")[:limit])
        return [{"id": str(e.id), "title": f"{e.order.number} · {e.get_to_status_display()}",
                 "body": e.note if e.note and len(e.note) < 120 else "", "at": e.created_at.isoformat(),
                 "amount": money(e.order.total) if e.to_status == S.PLACED else None,
                 "tone": "muted" if e.to_status == S.CANCELLED else "success" if e.to_status in HANDED_OVER else "active"}
                for e in events]

    def _counts(self) -> dict:
        qs = self._orders()
        return {
            "new": qs.filter(status=S.PLACED).count(),
            "preparing": qs.filter(status__in=PREPARING_STATES).count(),
            "ready": qs.filter(status__in=READY_STATES).count(),
            "inventory": self._low_stock().count(),
        }

    def quick_actions(self):
        c = self._counts()
        food = Store.objects.filter(id__in=self._store_ids(), store_type=StoreType.RESTAURANT).exists()
        return {
            "new": QuickAction("new", "New orders", "bell", "/work?view=new", c["new"]),
            "preparing": QuickAction("preparing", "Kitchen" if food else "In progress", "food" if food else "parcel",
                                     "/work?view=preparing", c["preparing"]),
            "packing": QuickAction("packing", "Packing", "parcel", "/work?view=preparing", c["preparing"]),
            "ready": QuickAction("ready", "Ready", "check", "/work?view=ready", c["ready"]),
            "active": QuickAction("active", "In progress", "clock", "/work?view=preparing", c["preparing"] + c["ready"]),
            "inventory": QuickAction("inventory", "Inventory", "grocery", "/work?view=inventory", c["inventory"] or None),
            "earnings": QuickAction("earnings", "Sales", "chart", "/earnings"),
        }

    def context_line(self, action_items, active, is_available):
        new = sum(1 for i in action_items if i.kind == "order")
        if new:
            return f"You have {new} new order{'s' if new != 1 else ''} waiting for you to accept."
        if active:
            return f"{len(active)} order{'s' if len(active) != 1 else ''} in progress."
        return "You’re open. New orders will appear here." if is_available else "You’re closed. Open to start receiving orders."

    # --- Work page / actions ------------------------------------------------------------------------
    def views(self):
        c = self._counts()
        prep = "Kitchen" if Store.objects.filter(id__in=self._store_ids(), store_type=StoreType.RESTAURANT).exists() else "In progress"
        views = [{"key": "new", "label": "New", "count": c["new"]},
                 {"key": "preparing", "label": prep, "count": c["preparing"]},
                 {"key": "ready", "label": "Ready", "count": c["ready"]},
                 {"key": "all", "label": "All orders", "count": None}]
        if Product.objects.filter(store_id__in=self._store_ids(), stock_quantity__isnull=False).exists():
            views.append({"key": "inventory", "label": "Inventory alerts", "count": c["inventory"]})
        return views

    def work(self, view, limit=50):
        qs = self._orders()
        if view == "inventory":
            return [self._stock_item(p) for p in self._low_stock()[:limit]]
        if view == "new":
            qs = qs.filter(status=S.PLACED).order_by("created_at")
        elif view == "preparing":
            qs = qs.filter(status__in=PREPARING_STATES).order_by("created_at")
        elif view == "ready":
            qs = qs.filter(status__in=READY_STATES).order_by("created_at")
        else:
            qs = qs.order_by("-created_at")
        return [self._item(o) for o in qs[:limit]]

    def perform(self, kind, item_id, action, payload, actor):
        if kind != "order":
            raise DomainError("Unknown work item.", code="unknown_item", status_code=404)
        order = self._orders().filter(pk=item_id).first()  # ownership: only this partner's storefronts
        if order is None:
            raise DomainError("Order not found.", code="not_found", status_code=404)
        if action == "reject":
            reason = " ".join(str(payload.get("reason", "")).split())[:200]
            if order.status != S.PLACED:
                raise DomainError("Only new orders can be rejected.", code="invalid_status_transition", status_code=409)
            if len(reason) < 3:
                raise DomainError("Tell the customer why you can’t take this order.", code="validation_error",
                                  details={"reason": ["Enter a reason."]})
            services.transition_order(order, S.CANCELLED, actor=actor, note=f"Declined by store: {reason}")
        else:
            step = _flow(order.store.store_type).get(order.status)
            if step is None or step[1].key != action:
                raise DomainError("This order has already moved on. Refresh to see its current status.",
                                  code="invalid_status_transition", status_code=409)
            services.transition_order(order, step[0], actor=actor, note="Updated by store")
        return self._item(self._orders().get(pk=order.pk))

