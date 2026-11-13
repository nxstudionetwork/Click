import logging
import uuid
from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.activity.services import record
from apps.carts.models import Cart
from apps.carts.services import add_item, cart_items, clear_cart, get_or_create_cart, offer_problem, seller_groups, unit_price
from apps.catalog.models import Product, ProductDeal, ProductVariant
from apps.catalog.pricing import deal_for
from apps.core.api.exceptions import ConflictError, DomainError
from apps.customers.models import CustomerProfile
from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify
from apps.payments.gateway import ONLINE, available_methods, start_for_orders
from apps.payments.models import PaymentMethod
from apps.payments.services import cancel_pending_payments, start_payment
from apps.stores.models import StoreType

from .models import ALLOWED_TRANSITIONS, CUSTOMER_CANCELLABLE, CheckoutGroup, Order, OrderItem, OrderStatus, OrderStatusEvent

audit = logging.getLogger("click.audit")


def place_order(*, customer: CustomerProfile, address_id, payment_method: str, idempotency_key, customer_note: str = "",
                grocery: dict | None = None, gift_card_id=None) -> tuple[Order, bool]:
    """Single-order view of `place_checkout` (food, groceries; first order of a marketplace checkout)."""
    _, orders, created = place_checkout(customer=customer, address_id=address_id, payment_method=payment_method,
                                        idempotency_key=idempotency_key, customer_note=customer_note, grocery=grocery, gift_card_id=gift_card_id)
    return orders[0], created


@transaction.atomic
def place_checkout(*, customer: CustomerProfile, address_id, payment_method: str, idempotency_key,
                   customer_note: str = "", grocery: dict | None = None, gift_card_id=None) -> tuple[CheckoutGroup | None, list[Order], bool]:
    """
    Converts the customer's cart into orders, recomputing every price server-side. A single-store cart becomes one
    order; a marketplace cart becomes one order per seller under a CheckoutGroup. Everything happens in one
    transaction: if any seller's part fails (stock, deal ended, wallet balance), nothing is created or charged.
    A repeated idempotency key returns the original result instead of creating duplicates.
    """
    # Lock the cart row: concurrent placements for the same customer serialize here.
    cart, _ = Cart.objects.select_for_update().get_or_create(customer=customer)

    group = CheckoutGroup.objects.filter(customer=customer, idempotency_key=idempotency_key).first()
    if group:
        return group, list(group.orders.order_by("created_at")), False
    existing = Order.objects.filter(customer=customer, idempotency_key=idempotency_key).first()
    if existing:
        return existing.checkout, [existing], False

    items = cart_items(cart)
    if not items:
        raise DomainError("Your cart is empty.", code="cart_empty")
    address = customer.addresses.filter(pk=address_id).first()
    if address is None:
        raise DomainError("Choose a valid delivery address.", code="invalid_address")

    marketplace = cart.mode in (Cart.Mode.MARKETPLACE, Cart.Mode.BASKET)
    if not marketplace and (cart.store is None or not cart.store.is_open):
        raise DomainError("This store isn't accepting orders right now.", code="store_closed")

    unavailable = [i.product.name for i in items if not _line_orderable(i, cart)]
    if unavailable:
        raise ConflictError("Some items are no longer available.", code="items_unavailable", details={"items": unavailable})

    groups = seller_groups(cart, items)
    if cart.mode == Cart.Mode.BASKET:
        # Groceries: each store's delivery mode/slot, distance-based fee, live prices and opening hours are checked
        # (and the fee, ETA and slot attached to its group) before anything is created.
        from apps.groceries.checkout import prepare_basket

        prepare_basket(cart, groups, address, grocery or {})
    for g in groups:
        if g.subtotal < g.store.min_order_amount:
            raise DomainError(f"Minimum order for {g.store.name} is {g.store.min_order_amount} {g.store.currency}.",
                              code="below_minimum_order")
    # An offer chosen earlier must still apply now (dates, seller, minimum); otherwise stop and say why.
    if cart.offer_id:
        g = next((g for g in groups if g.store.id == cart.offer.store_id), None)
        if problem := offer_problem(cart.offer, g.store if g else None, g.subtotal if g else 0):
            raise ConflictError(problem, code="offer_not_applicable")
    rx_items = [i for i in items if i.product.requires_prescription]
    if rx_items:
        from apps.pharma.models import Prescription

        rx = cart.prescription
        ok = (rx is not None and rx.customer_id == customer.id and rx.pharmacy_id == cart.store_id
              and rx.status in (Prescription.Status.VERIFIED, Prescription.Status.PARTIAL)
              and (rx.valid_until is None or rx.valid_until >= timezone.localdate()))
        approved = set(rx.approved_items.values_list("id", flat=True)) if ok else set()
        if not ok or (approved and any(i.product_id not in approved for i in rx_items)):
            raise ConflictError("Prescription items need a prescription this pharmacy has verified.", code="prescription_required",
                                details={"items": [i.product.name for i in rx_items]})
    online = payment_method in ONLINE
    if online and payment_method not in available_methods():
        raise DomainError("Online payment isn’t available right now. Choose another way to pay.", code="online_payment_unavailable", status_code=503)
    if payment_method == PaymentMethod.CASH_ON_DELIVERY:
        no_cod = [i.product.name for g in groups for i in g.items if not (g.store.cod_enabled and i.product.is_cod_available)]
        if no_cod:
            raise DomainError("Cash on delivery isn't available for some items. Choose another way to pay.",
                              code="cod_unavailable", details={"items": no_cod})

    _reserve_stock(items)
    _claim_deals(items)

    checkout = None
    if marketplace:
        checkout = CheckoutGroup.objects.create(customer=customer, idempotency_key=idempotency_key,
                                                total=sum((g.total for g in groups)), currency=groups[0].store.currency)
    orders = []
    for g in groups:
        key = idempotency_key if not marketplace else uuid.uuid5(uuid.UUID(str(idempotency_key)), str(g.store.id))
        orders.append(_create_order(customer, g, address, key, customer_note, payment_method, checkout, gift_card_id))
    if online:  # one provider intent for the whole checkout; orders wait for its verified confirmation
        start_for_orders(orders, payment_method)
    if rx_items:
        from apps.pharma.models import Prescription

        Prescription.objects.filter(pk=cart.prescription_id).update(status=Prescription.Status.USED, order=orders[0])
    clear_cart(cart)
    if checkout:
        record(customer, "checkout.placed", {"total": str(checkout.total), "orders": len(orders)}, obj=checkout)
    return checkout, orders, True


def _line_orderable(item, cart) -> bool:
    p = item.product
    if not p.store.is_open or (cart.mode == Cart.Mode.STORE and p.store_id != cart.store_id):
        return False
    if item.variant is not None:
        if not item.variant.is_orderable:
            return False
    elif not p.is_orderable or p.variants.filter(is_active=True).exists():
        return False
    return all(o.is_available for o in item.options.all())


def _reserve_stock(items) -> None:
    """Reserve inventory atomically; a concurrent buyer taking the last unit fails here, not later."""
    wanted: dict = {}
    for i in items:
        target = i.variant if i.variant is not None else i.product
        if target.stock_quantity is not None:
            wanted[(type(target), target.pk, i.product.name)] = wanted.get((type(target), target.pk, i.product.name), 0) + i.quantity
    for (model, pk, name), qty in wanted.items():
        model = ProductVariant if model is ProductVariant else Product
        if not model.objects.filter(pk=pk, stock_quantity__gte=qty).update(stock_quantity=F("stock_quantity") - qty):
            raise ConflictError("Some items are no longer available.", code="items_unavailable", details={"items": [name]})


def _claim_deals(items) -> None:
    """Deals with a unit limit are claimed atomically, so the deal price is never sold beyond its limit."""
    wanted: dict = {}
    for i in items:
        deal = deal_for(i.product)
        if deal is not None and deal.quantity_limit is not None:
            wanted[deal] = wanted.get(deal, 0) + i.quantity
    for deal, qty in wanted.items():
        claimed = ProductDeal.objects.filter(pk=deal.pk, units_sold__lte=F("quantity_limit") - qty).update(units_sold=F("units_sold") + qty)
        if not claimed:
            raise ConflictError(f"The deal on {deal.product.name} has sold out. Your cart shows the current price.",
                                code="deal_ended", details={"items": [deal.product.name]})


def _create_order(customer, g, address, key, customer_note, payment_method, checkout, gift_card_id=None) -> Order:
    store = g.store
    retail = store.store_type == StoreType.RETAIL
    est_from = est_to = None
    if retail:
        from apps.shop.delivery import estimate

        est = estimate(store, address=address)
        tz = timezone.get_current_timezone()
        # Midday on both days, so the dates read the same in any customer time zone.
        est_from = timezone.make_aware(datetime.combine(datetime.fromisoformat(est["from_date"]), time(12)), tz)
        est_to = timezone.make_aware(datetime.combine(datetime.fromisoformat(est["to_date"]), time(12)), tz)
    online = payment_method in ONLINE
    order = Order.objects.create(
        customer=customer, store=store, checkout=checkout, status=OrderStatus.AWAITING_PAYMENT if online else OrderStatus.PLACED,
        delivery_address=address.snapshot(), delivery_address_ref=address, customer_note=customer_note,
        subtotal=g.subtotal, delivery_fee=g.delivery_fee, tax=g.tax, discount=g.discount,
        offer_title=g.offer.title if g.offer and g.discount else "", total=g.total, currency=store.currency,
        idempotency_key=key,
        estimated_delivery_from=est_from,
        estimated_delivery_at=est_to or getattr(g, "estimated_at", None) or (timezone.now() + timedelta(minutes=store.delivery_time_max)),
    )
    if getattr(g, "grocery", None):
        from apps.groceries.checkout import record_details

        record_details(order, g)
    lines = []
    for i in g.items:
        price, deal = unit_price(i), deal_for(i.product)
        summary = i.variant.label if i.variant else " · ".join(o.name for o in i.options.all())
        lines.append(OrderItem(
            order=order, product=i.product, variant=i.variant, product_name=i.product.name, unit_price=price,
            quantity=i.quantity, line_total=price * i.quantity, note=i.note, options_summary=summary[:300],
            return_days=i.product.return_days, replacement_only=i.product.replacement_only,
            deal_percent=deal.percent_off if deal else None,
        ))
        Product.objects.filter(pk=i.product_id).update(units_sold=F("units_sold") + i.quantity)
    OrderItem.objects.bulk_create(lines)
    OrderStatusEvent.objects.create(order=order, to_status=order.status, actor=customer.user)
    if not online:  # online orders are paid (and announced) by payments.gateway once the provider confirms
        start_payment(order, payment_method, gift_card_id)
        notify(customer, NotificationCategory.ORDERS, f"Order placed with {store.name}",
               f"{order.number} · we'll update you as it progresses.", f"/orders/{order.id}")
        from apps.discover.engine import attribute_order

        attribute_order(order)
    record(customer, "order.placed", {"total": str(order.total), "store": store.slug}, obj=order)
    audit.info("order.placed", extra={"order": order.number, "customer": str(customer.id)})
    return order


@transaction.atomic
def transition_order(order: Order, to_status: str, *, actor=None, note: str = "") -> Order:
    order = Order.objects.select_for_update().select_related("store", "customer").get(pk=order.pk)
    if to_status not in ALLOWED_TRANSITIONS[order.status]:
        raise ConflictError(
            f"An order that is {order.get_status_display().lower()} can't move to {to_status}.",
            code="invalid_status_transition",
        )
    retail = order.store.store_type == StoreType.RETAIL
    if (retail and to_status in (OrderStatus.PREPARING, OrderStatus.READY)) or (not retail and to_status in (OrderStatus.PACKED, OrderStatus.SHIPPED)):
        raise ConflictError("That step doesn't apply to this kind of order.", code="invalid_status_transition")
    previous = order.status
    order.status = to_status
    now = timezone.now()
    if to_status == OrderStatus.CANCELLED:
        order.cancelled_at = now
        cancel_pending_payments(order)
        _restock(order)
    elif to_status == OrderStatus.DELIVERED:
        order.delivered_at = now
        from apps.payments.services import collect_on_delivery

        collect_on_delivery(order)
    order.save(update_fields=["status", "cancelled_at", "delivered_at", "updated_at"])
    OrderStatusEvent.objects.create(order=order, from_status=previous, to_status=to_status, actor=actor, note=note)
    notify(order.customer, NotificationCategory.ORDERS, f"{order.store.name}: {order.get_status_display()}",
           order.number, f"/orders/{order.id}")
    record(order.customer, f"order.{to_status}", obj=order)
    if to_status == OrderStatus.DELIVERED:
        from apps.rewards.services import award_for_delivered_order

        award_for_delivered_order(order)
    return order


def cancel_by_customer(order: Order, *, user, reason: str = "") -> Order:
    if order.status not in CUSTOMER_CANCELLABLE:
        raise ConflictError("This order can no longer be cancelled.", code="order_not_cancellable")
    return transition_order(order, OrderStatus.CANCELLED, actor=user, note=reason or "Cancelled by customer")


def _restock(order: Order) -> None:
    for item in order.items.select_related("product", "variant"):
        if item.variant_id and item.variant and item.variant.stock_quantity is not None:
            ProductVariant.objects.filter(pk=item.variant_id).update(stock_quantity=F("stock_quantity") + item.quantity)
        elif item.product and item.product.stock_quantity is not None:
            Product.objects.filter(pk=item.product_id).update(stock_quantity=F("stock_quantity") + item.quantity)
        if item.product_id:
            Product.objects.filter(pk=item.product_id, units_sold__gte=item.quantity).update(units_sold=F("units_sold") - item.quantity)


@transaction.atomic
def reorder(order: Order, *, customer: CustomerProfile):
    """Rebuild the cart from a past order. Current prices apply; unavailable items are reported, not added."""
    if not order.store.is_open:
        raise DomainError("This store isn't accepting orders right now.", code="store_closed")
    cart = get_or_create_cart(customer)
    clear_cart(cart)
    skipped = []
    for item in order.items.select_related("product", "variant"):
        if not item.product:
            skipped.append(item.product_name)
            continue
        # Options are snapshotted by name; map them back to today's options for this product.
        names = {n for n in item.options_summary.split(" · ") if n}
        option_ids = [] if item.variant_id else [
            o.id for g in item.product.option_groups.prefetch_related("options") for o in g.options.all() if o.name in names]
        try:
            add_item(customer, item.product_id, item.quantity, item.note, option_ids, variant_id=item.variant_id)
        except DomainError:
            skipped.append(item.product_name)
    cart.refresh_from_db()
    return cart, skipped


@transaction.atomic
def submit_review(order: Order, *, customer: CustomerProfile, rating: int, comment: str = "") -> "OrderReview":
    """Rate a delivered order once; the store's average rating and count update in the same transaction."""
    from decimal import ROUND_HALF_UP, Decimal

    from apps.stores.models import Store

    from .models import OrderReview

    if order.status != OrderStatus.DELIVERED:
        raise DomainError("You can rate an order once it's delivered.", code="review_not_allowed")
    if OrderReview.objects.filter(order=order).exists():
        raise ConflictError("You've already rated this order.", code="review_exists")
    review = OrderReview.objects.create(order=order, customer=customer, store=order.store, rating=rating, comment=comment.strip())
    store = Store.objects.select_for_update().get(pk=order.store_id)
    total = store.rating_average * store.rating_count + rating
    store.rating_count += 1
    store.rating_average = (Decimal(total) / store.rating_count).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    store.save(update_fields=["rating_average", "rating_count", "updated_at"])
    record(customer, "order.reviewed", {"rating": rating}, obj=order)
    return review
