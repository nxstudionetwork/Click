"""
Returns and replacements for delivered Shopping items.

A customer can request one return per item line while its return window (snapshotted from the listing when
ordered) is open. Click staff resolve requests in Django admin today (the seller will in the Partner App):
approving a return refunds the item's share of what was paid to the Click Wallet; approving a replacement marks it
for the seller to send. Nothing is refunded by the customer's request alone.
"""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.api.exceptions import ConflictError, DomainError
from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify

from .models import OrderItem, OrderStatus, ReturnRequest

OPEN = {ReturnRequest.Status.REQUESTED, ReturnRequest.Status.APPROVED}


def return_deadline(item: OrderItem):
    order = item.order
    if item.return_days is None or order.status != OrderStatus.DELIVERED or order.delivered_at is None:
        return None
    return order.delivered_at + timedelta(days=item.return_days)


def return_problem(item: OrderItem) -> str | None:
    """Why this line can't be returned now (None means it can)."""
    if item.return_days is None:
        return "This item isn't returnable."
    if item.order.status != OrderStatus.DELIVERED:
        return "You can return items once they're delivered."
    deadline = return_deadline(item)
    if deadline is None or timezone.now() > deadline:
        return "The return window for this item has closed."
    if item.returns.exclude(status=ReturnRequest.Status.REJECTED).exists():
        return "You've already requested a return for this item."
    return None


@transaction.atomic
def request_return(*, customer, item: OrderItem, kind: str, reason: str, details: str = "", quantity: int = 1) -> ReturnRequest:
    item = OrderItem.objects.select_for_update().select_related("order").get(pk=item.pk)
    if item.order.customer_id != customer.id:
        raise DomainError("Not found.", code="not_found", status_code=404)
    if problem := return_problem(item):
        raise ConflictError(problem, code="return_not_allowed")
    if item.replacement_only and kind == ReturnRequest.Kind.RETURN:
        raise DomainError("This item can be replaced, not returned for a refund.", code="replacement_only")
    if not 1 <= quantity <= item.quantity:
        raise DomainError(f"Choose between 1 and {item.quantity}.", code="invalid_quantity")
    ret = ReturnRequest.objects.create(item=item, customer=customer, kind=kind, reason=reason, details=details.strip(), quantity=quantity)
    notify(customer, NotificationCategory.ORDERS, "Return requested", f"{item.product_name} · {item.order.number}. We'll update you.",
           f"/orders/{item.order_id}")
    return ret


def refund_amount(ret: ReturnRequest) -> Decimal:
    """The item's share of what was actually paid: its line value, minus its share of the discount, plus its tax.
    (Tax is charged on the pre-discount subtotal, so both shares are proportional to the line value.)"""
    item, order = ret.item, ret.item.order
    line = item.unit_price * ret.quantity
    if not order.subtotal:
        return Decimal("0.00")
    share = line / order.subtotal
    return max(line - order.discount * share + order.tax * share, Decimal("0")).quantize(Decimal("0.01"))


@transaction.atomic
def resolve(ret: ReturnRequest, *, approve: bool, note: str = "") -> ReturnRequest:
    ret = ReturnRequest.objects.select_for_update().select_related("item__order", "customer").get(pk=ret.pk)
    if ret.status != ReturnRequest.Status.REQUESTED:
        raise ConflictError("This request has already been resolved.", code="return_resolved")
    ret.resolution_note, ret.resolved_at = note, timezone.now()
    title = ret.item.product_name
    if not approve:
        ret.status = ReturnRequest.Status.REJECTED
        msg = "Return request declined"
    elif ret.kind == ReturnRequest.Kind.REPLACEMENT:
        ret.status = ReturnRequest.Status.APPROVED
        msg = "Replacement approved"
    else:
        from apps.wallet.services import refund_return

        ret.refund_amount = refund_amount(ret)
        payment = ret.item.order.payments.order_by("created_at").first()
        refund_return(ret.customer, ret.refund_amount, payment, f"Return of {title} ({ret.item.order.number})")
        ret.status = ReturnRequest.Status.REFUNDED
        msg = "Return approved and refunded"
    ret.save(update_fields=["status", "refund_amount", "resolution_note", "resolved_at", "updated_at"])
    order = ret.item.order
    if ret.status == ReturnRequest.Status.REFUNDED and not order.items.exclude(returns__status=ReturnRequest.Status.REFUNDED).exists():
        from apps.rewards.services import reverse_for_order

        reverse_for_order(order, f"order {order.number} fully refunded")  # every item came back: its points do too
    notify(ret.customer, NotificationCategory.ORDERS, msg, f"{title} · {ret.item.order.number}", f"/orders/{ret.item.order_id}")
    return ret


@transaction.atomic
def mark_replaced(ret: ReturnRequest) -> ReturnRequest:
    ret = ReturnRequest.objects.select_for_update().get(pk=ret.pk)
    if ret.kind != ReturnRequest.Kind.REPLACEMENT or ret.status != ReturnRequest.Status.APPROVED:
        raise ConflictError("Only approved replacements can be marked as sent.", code="return_resolved")
    ret.status = ReturnRequest.Status.REPLACED
    ret.save(update_fields=["status", "updated_at"])
    return ret
