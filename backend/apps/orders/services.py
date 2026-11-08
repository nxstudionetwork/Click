import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.carts.models import Cart
from apps.catalog.models import Product
from apps.carts.services import add_item, clear_cart, compute_totals, get_or_create_cart, offer_problem, unit_price
from apps.core.api.exceptions import ConflictError, DomainError
from apps.customers.models import CustomerProfile
from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify
from apps.payments.services import cancel_pending_payments, start_payment

from .models import ALLOWED_TRANSITIONS, CUSTOMER_CANCELLABLE, Order, OrderItem, OrderStatus, OrderStatusEvent

from apps.activity.services import record

audit = logging.getLogger("click.audit")


@transaction.atomic
def place_order(*, customer: CustomerProfile, address_id, payment_method: str, idempotency_key, customer_note: str = "") -> tuple[Order, bool]:
    """
    Converts the customer's cart into an order. All prices are recomputed
    server-side. Returns (order, created); a repeated idempotency key returns
    the original order instead of creating a duplicate.
    """
    # Lock the cart row: concurrent placements for the same customer serialize here.
    cart, _ = Cart.objects.select_for_update().get_or_create(customer=customer)

    existing = Order.objects.filter(customer=customer, idempotency_key=idempotency_key).first()
    if existing:
        return existing, False

    items = list(cart.items.select_related("product", "product__store").prefetch_related("options"))
    if not items:
        raise DomainError("Your cart is empty.", code="cart_empty")

    store = cart.store
    if store is None or not store.is_open:
        raise DomainError("This store isn't accepting orders right now.", code="store_closed")

    unavailable = [i.product.name for i in items if not i.product.is_orderable or i.product.store_id != store.id
                   or any(not o.is_available for o in i.options.all())]
    if unavailable:
        raise ConflictError("Some items are no longer available.", code="items_unavailable", details={"items": unavailable})

    address = customer.addresses.filter(pk=address_id).first()
    if address is None:
        raise DomainError("Choose a valid delivery address.", code="invalid_address")

    totals = compute_totals(cart, items)
    if totals.subtotal < store.min_order_amount:
        raise DomainError(
            f"Minimum order for {store.name} is {store.min_order_amount} {store.currency}.",
            code="below_minimum_order",
        )
    # An offer chosen earlier must still apply now (dates, store, minimum); otherwise stop and say why.
    if cart.offer_id and (problem := offer_problem(cart.offer, store, totals.subtotal)):
        raise ConflictError(problem, code="offer_not_applicable")

    # Reserve inventory atomically; a concurrent buyer taking the last unit fails here, not later.
    wanted: dict = {}
    for i in items:
        if i.product.stock_quantity is not None:
            wanted[i.product] = wanted.get(i.product, 0) + i.quantity
    for product, qty in wanted.items():
        reserved = Product.objects.filter(pk=product.pk, stock_quantity__gte=qty).update(
            stock_quantity=F("stock_quantity") - qty
        )
        if not reserved:
            raise ConflictError(
                "Some items are no longer available.", code="items_unavailable", details={"items": [product.name]}
            )

    order = Order.objects.create(
        customer=customer,
        store=store,
        delivery_address=address.snapshot(),
        delivery_address_ref=address,
        customer_note=customer_note,
        subtotal=totals.subtotal,
        delivery_fee=totals.delivery_fee,
        tax=totals.tax,
        discount=totals.discount,
        offer_title=cart.offer.title if totals.discount else "",
        total=totals.total,
        currency=store.currency,
        idempotency_key=idempotency_key,
        estimated_delivery_at=timezone.now() + timedelta(minutes=store.delivery_time_max),
    )
    OrderItem.objects.bulk_create(
        OrderItem(
            order=order,
            product=i.product,
            product_name=i.product.name,
            unit_price=unit_price(i),
            quantity=i.quantity,
            line_total=unit_price(i) * i.quantity,
            note=i.note,
            options_summary=" · ".join(o.name for o in i.options.all())[:300],
        )
        for i in items
    )
    OrderStatusEvent.objects.create(order=order, to_status=OrderStatus.PLACED, actor=customer.user)
    start_payment(order, payment_method)
    clear_cart(cart)
    notify(customer, NotificationCategory.ORDERS, f"Order placed at {store.name}",
           f"{order.number} · we'll update you as it progresses.", f"/orders/{order.id}")
    record(customer, "order.placed", {"total": str(order.total), "store": store.slug}, obj=order)
    audit.info("order.placed", extra={"order": order.number, "customer": str(customer.id)})
    return order, True


@transaction.atomic
def transition_order(order: Order, to_status: str, *, actor=None, note: str = "") -> Order:
    order = Order.objects.select_for_update().select_related("store", "customer").get(pk=order.pk)
    if to_status not in ALLOWED_TRANSITIONS[order.status]:
        raise ConflictError(
            f"An order that is {order.get_status_display().lower()} can't move to {to_status}.",
            code="invalid_status_transition",
        )
    previous = order.status
    order.status = to_status
    now = timezone.now()
    if to_status == OrderStatus.CANCELLED:
        order.cancelled_at = now
        cancel_pending_payments(order)
        _restock(order)
    elif to_status == OrderStatus.DELIVERED:
        order.delivered_at = now
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
    for item in order.items.select_related("product"):
        if item.product and item.product.stock_quantity is not None:
            Product.objects.filter(pk=item.product_id).update(stock_quantity=F("stock_quantity") + item.quantity)


@transaction.atomic
def reorder(order: Order, *, customer: CustomerProfile):
    """Rebuild the cart from a past order. Current prices apply; unavailable items are reported, not added."""
    if not order.store.is_open:
        raise DomainError("This store isn't accepting orders right now.", code="store_closed")
    cart = get_or_create_cart(customer)
    clear_cart(cart)
    skipped = []
    for item in order.items.select_related("product"):
        if not item.product:
            skipped.append(item.product_name)
            continue
        # Options are snapshotted by name; map them back to today's options for this product.
        names = {n for n in item.options_summary.split(" · ") if n}
        option_ids = [o.id for g in item.product.option_groups.prefetch_related("options") for o in g.options.all() if o.name in names]
        try:
            add_item(customer, item.product_id, item.quantity, item.note, option_ids)
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
