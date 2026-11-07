from apps.core.api.exceptions import DomainError

from .models import Payment, PaymentMethod

ENABLED_METHODS = {PaymentMethod.CASH_ON_DELIVERY}


def start_payment(order, method: str) -> Payment:
    if method not in ENABLED_METHODS:
        raise DomainError("This payment method isn't available yet.", code="payment_method_unavailable")
    # Cash on delivery: nothing to authorize now; captured when the order is delivered.
    return Payment.objects.create(order=order, method=method, amount=order.total, currency=order.currency)


def cancel_pending_payments(order) -> None:
    order.payments.filter(status=Payment.Status.PENDING).update(status=Payment.Status.CANCELLED)
