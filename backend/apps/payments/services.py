"""
Payment orchestration for orders and bookings. Status always comes from here
(trusted backend), never from the client.

  cash_on_delivery / pay_at_venue -> pending until collected
  wallet                          -> captured immediately from the wallet ledger
  (online gateways)               -> later: pending -> authorized -> captured via signed webhooks
"""

from apps.core.api.exceptions import DomainError

from .models import Payment, PaymentMethod

ORDER_METHODS = {PaymentMethod.CASH_ON_DELIVERY, PaymentMethod.WALLET}
BOOKING_METHODS = {PaymentMethod.PAY_AT_VENUE, PaymentMethod.WALLET}


def _start(*, customer, method: str, amount, currency, allowed, description: str, **target) -> Payment:
    if method not in allowed:
        raise DomainError("This payment method isn't available here.", code="payment_method_unavailable")
    payment = Payment.objects.create(method=method, amount=amount, currency=currency,
                                     provider="click_wallet" if method == PaymentMethod.WALLET else "internal", **target)
    if method == PaymentMethod.WALLET:
        from apps.wallet.services import pay

        pay(customer, amount, payment, description)
        payment.status = Payment.Status.CAPTURED
        payment.save(update_fields=["status", "updated_at"])
    return payment


def start_payment(order, method: str) -> Payment:
    return _start(customer=order.customer, method=method, amount=order.total, currency=order.currency,
                  allowed=ORDER_METHODS, description=f"Order {order.number}", order=order)


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
        else:
            continue
        p.save(update_fields=["status", "updated_at"])


def cancel_pending_payments(order) -> None:
    settle_on_cancel(order.payments.all(), order.customer, f"order {order.number}")
