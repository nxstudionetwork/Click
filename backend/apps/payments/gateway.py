"""
Online payment (UPI / card / net banking) for checkouts, through the same provider layer as adding money
(apps/wallet/providers.py). One provider intent covers a whole checkout (every seller's order):

  place checkout with an online method
      → orders are created in "awaiting payment" (stock reserved, store NOT notified), one pending Payment per order,
        all sharing the provider reference
  provider confirms with a signed event (/payments/webhooks/<provider>)
      → succeeded: payments captured, orders move to "placed", store and customer notified
      → failed:    payments failed, orders cancelled, stock restored
  nothing confirmed within CLICK_ONLINE_PAYMENT_TTL_MINUTES → expire_unpaid() cancels them the same way

The app never decides that a payment succeeded; it only shows the state these records hold.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.api.exceptions import ConflictError, DomainError

from .models import Payment

ONLINE = ("upi", "card", "netbanking")
LABEL = {"upi": "UPI", "card": "Card", "netbanking": "Net banking"}


def provider():
    from apps.wallet.providers import current

    return current()


def available_methods() -> list[str]:
    p = provider()
    return list(p.methods) if p else []


class _Ref:  # what a provider needs to describe / sign an intent
    def __init__(self, reference: str, amount: Decimal):
        self.provider_reference, self.amount = reference, amount


def start_for_orders(orders, method: str) -> dict:
    p = provider()
    if p is None:
        raise DomainError("Online payment isn’t available right now. Choose another way to pay.", code="online_payment_unavailable", status_code=503)
    if method not in p.methods:
        raise DomainError("This payment method isn’t available.", code="payment_method_unavailable")
    reference = p.create_intent(None)
    for o in orders:
        Payment.objects.create(order=o, method=method, amount=o.total, currency=o.currency, provider=p.name, provider_reference=reference)
    return intent(reference)


def intent(reference: str) -> dict | None:
    """Customer-facing state of one checkout payment (read from the Payment rows)."""
    rows = list(Payment.objects.filter(provider_reference=reference, wallet_topup__isnull=True).select_related("order"))
    if not rows:
        return None
    statuses = {r.status for r in rows}
    state = ("succeeded" if statuses == {Payment.Status.CAPTURED} else "failed" if statuses & {Payment.Status.FAILED} else
             "cancelled" if statuses <= {Payment.Status.CANCELLED, Payment.Status.REFUNDED} else "pending")
    p = provider()
    amount = sum((r.amount for r in rows), Decimal("0"))
    out = {"reference": reference, "status": state, "amount": f"{amount:.2f}", "method": rows[0].method, "method_label": LABEL.get(rows[0].method, rows[0].method),
           "orders": [{"id": str(r.order_id), "number": r.order.number, "status": r.order.status} for r in rows if r.order_id],
           "gift_card_id": next((str(r.gift_card_id) for r in rows if r.gift_card_id), None),
           "expires_at": (min(r.created_at for r in rows) + timedelta(minutes=settings.CLICK_ONLINE_PAYMENT_TTL_MINUTES)).isoformat()}
    if p and state == "pending" and p.name == rows[0].provider:
        out["client"] = p.client_data(_Ref(reference, amount))
    return out


def owned_reference(customer, reference: str) -> bool:
    from django.db.models import Q

    return Payment.objects.filter(Q(order__customer=customer) | Q(gift_card__buyer=customer), provider_reference=reference).exists()


def start_for_gift_card(card, method: str) -> dict:
    p = provider()
    if p is None:
        raise DomainError("Online payment isn’t available right now. Choose another way to pay.", code="online_payment_unavailable", status_code=503)
    if method not in p.methods:
        raise DomainError("This payment method isn’t available.", code="payment_method_unavailable")
    reference = p.create_intent(None)
    Payment.objects.create(gift_card=card, method=method, amount=card.amount, provider=p.name, provider_reference=reference)
    return intent(reference)


@transaction.atomic
def apply_result(reference: str, outcome: str, amount: Decimal, reason: str = "") -> dict:
    """Called only after the provider's signature is verified. Idempotent: replays and late events change nothing."""
    from apps.notifications.models import NotificationCategory
    from apps.notifications.services import notify
    from apps.orders.models import OrderStatus
    from apps.orders.services import transition_order

    rows = list(Payment.objects.select_for_update(of=("self",)).filter(provider_reference=reference, wallet_topup__isnull=True).select_related("order__store", "order__customer", "gift_card__buyer"))
    if not rows:
        raise DomainError("Unknown payment reference.", code="unknown_reference", status_code=404)
    if any(r.status != Payment.Status.PENDING for r in rows):
        return intent(reference)  # already settled (or expired): duplicate / late callback
    if outcome == "pending":
        return intent(reference)
    if outcome == "succeeded":
        if sum((r.amount for r in rows), Decimal("0")) != Decimal(str(amount)).quantize(Decimal("0.01")):
            raise ConflictError("The confirmed amount doesn’t match the checkout.", code="amount_mismatch")
        for r in rows:
            r.status = Payment.Status.CAPTURED
            r.save(update_fields=["status", "updated_at"])
            if r.gift_card_id:
                from apps.giftcards.services import paid

                paid(r.gift_card)
            if r.order and r.order.status == OrderStatus.AWAITING_PAYMENT:
                transition_order(r.order, OrderStatus.PLACED, note=f"Paid by {LABEL.get(r.method, r.method)} · {reference}")
                notify(r.order.customer, NotificationCategory.ORDERS, f"Order placed with {r.order.store.name}",
                       f"{r.order.number} · payment received. We'll update you as it progresses.", f"/orders/{r.order.id}")
        return intent(reference)
    for r in rows:
        r.status = Payment.Status.FAILED
        r.save(update_fields=["status", "updated_at"])
        if r.gift_card_id:
            from apps.giftcards.services import failed

            failed(r.gift_card)
        if r.order and r.order.status == OrderStatus.AWAITING_PAYMENT:
            transition_order(r.order, OrderStatus.CANCELLED, note=f"Payment didn’t go through{': ' + reason[:120] if reason else ''}")
    first = rows[0].order
    if rows[0].gift_card_id:
        notify(rows[0].gift_card.buyer, NotificationCategory.PAYMENTS, "Gift card payment didn’t go through",
               "The gift card wasn’t bought. If money left your account, your bank or payment app returns it.", f"/gift-cards/mine/{rows[0].gift_card_id}")
    if first:
        notify(first.customer, NotificationCategory.PAYMENTS, "Payment didn’t go through",
               f"{LABEL.get(rows[0].method, rows[0].method)} payment for {first.number}{' and more' if len(rows) > 1 else ''} failed, so the order wasn’t placed. "
               "If money left your account, your bank or payment app returns it.", f"/account/payments/{rows[0].id}")
    return intent(reference)


def expire_unpaid() -> int:
    """Cancel checkouts whose online payment was never confirmed (run on a schedule)."""
    from apps.orders.models import OrderStatus
    from apps.orders.services import transition_order

    cutoff = timezone.now() - timedelta(minutes=settings.CLICK_ONLINE_PAYMENT_TTL_MINUTES)
    n = 0
    for p in Payment.objects.filter(status=Payment.Status.PENDING, method__in=ONLINE, order__status=OrderStatus.AWAITING_PAYMENT,
                                    created_at__lte=cutoff).select_related("order"):
        with transaction.atomic():
            transition_order(p.order, OrderStatus.CANCELLED, note="Payment wasn’t completed in time")
            n += 1
    return n


def refund_online(payment: Payment, customer, label: str) -> None:
    """Refund a captured online payment to the original method through its provider. Without that provider connected
    the refund can't be sent, so the cancellation is stopped and the customer is pointed to support."""
    from apps.notifications.models import NotificationCategory
    from apps.notifications.services import notify

    p = provider()
    if p is None or p.name != payment.provider:
        raise ConflictError("This order was paid online and its refund can’t be sent right now. Please contact support.", code="refund_unavailable")
    p.refund(payment)
    notify(customer, NotificationCategory.PAYMENTS, f"Refund of ₹{payment.amount:,.2f} started",
           f"For {label}, back to your {LABEL.get(payment.method, payment.method)}. Banks usually show it within 5–7 working days.",
           f"/account/payments/{payment.id}")
