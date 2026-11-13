"""
Payment orchestration for orders and bookings. Status always comes from here
(trusted backend), never from the client.

  cash_on_delivery / pay_at_venue -> pending until collected
  wallet                          -> captured immediately from the wallet ledger
  (online gateways)               -> later: pending -> authorized -> captured via signed webhooks
"""

from apps.core.api.exceptions import DomainError

from .models import Payment, PaymentMethod

ORDER_METHODS = {PaymentMethod.CASH_ON_DELIVERY, PaymentMethod.WALLET, PaymentMethod.GIFT_CARD}
BOOKING_METHODS = {PaymentMethod.PAY_AT_VENUE, PaymentMethod.WALLET}


def _start(*, customer, method: str, amount, currency, allowed, description: str, gift_card_id=None, service: str = "", **target) -> Payment:
    if method not in allowed:
        raise DomainError("This payment method isn't available here.", code="payment_method_unavailable")
    payment = Payment.objects.create(method=method, amount=amount, currency=currency,
                                     provider="click_wallet" if method == PaymentMethod.WALLET else "internal", **target)
    if method == PaymentMethod.WALLET:
        from apps.wallet.services import pay

        pay(customer, amount, payment, description)
        payment.status = Payment.Status.CAPTURED
        payment.save(update_fields=["status", "updated_at"])
    elif method == PaymentMethod.GIFT_CARD:
        from apps.giftcards.services import pay as gift_pay

        payment.provider = "click_gift_card"
        gift_pay(customer, gift_card_id, amount, payment, service, description)
        payment.status = Payment.Status.CAPTURED
        payment.save(update_fields=["status", "provider", "updated_at"])
    return payment


def start_payment(order, method: str, gift_card_id=None) -> Payment:
    service = {"restaurant": "food", "grocery": "groceries", "retail": "shop"}.get(order.store.store_type, "shop")
    return _start(customer=order.customer, method=method, amount=order.total, currency=order.currency, allowed=ORDER_METHODS,
                  description=f"Order {order.number}", gift_card_id=gift_card_id, service=service, order=order)


def start_booking_payment(booking, method: str) -> Payment:
    return _start(customer=booking.customer, method=method, amount=booking.total, currency=booking.currency,
                  allowed=BOOKING_METHODS, description=f"Booking {booking.reference}", booking=booking)


def settle_on_cancel(payments, customer, label: str) -> None:
    """Pending payments are cancelled; wallet-captured payments are refunded to the wallet."""
    from apps.wallet.services import refund

    for p in payments.select_for_update():
        if p.status == Payment.Status.PENDING:
            p.status = Payment.Status.CANCELLED
        elif p.status == Payment.Status.CAPTURED and p.method == PaymentMethod.WALLET:
            refund(customer, p.amount, p, f"Refund for {label}")
            p.status = Payment.Status.REFUNDED
        elif p.status == Payment.Status.CAPTURED and p.method == PaymentMethod.GIFT_CARD:
            from apps.giftcards.services import refund as gift_refund

            gift_refund(p, label)
            p.status = Payment.Status.REFUNDED
        elif p.status == Payment.Status.CAPTURED and p.method in ("upi", "card", "netbanking"):
            from .gateway import refund_online

            refund_online(p, customer, label)
            p.status = Payment.Status.REFUNDED
        else:
            continue
        p.save(update_fields=["status", "updated_at"])


def collect_on_delivery(order) -> int:
    """Delivered means the partner collected the cash: a pending cash-on-delivery payment becomes captured."""
    return order.payments.filter(method=PaymentMethod.CASH_ON_DELIVERY, status=Payment.Status.PENDING).update(status=Payment.Status.CAPTURED)


def cancel_pending_payments(order) -> None:
    settle_on_cancel(order.payments.all(), order.customer, f"order {order.number}")
