from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from apps.core.api.exceptions import DomainError
from apps.customers.models import CustomerProfile
from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify

from .models import WalletTransaction


def balance(customer) -> Decimal:
    return WalletTransaction.objects.filter(customer=customer).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")


def _lock(customer) -> None:
    # Serialize all wallet writes per customer so concurrent payments can't overspend.
    CustomerProfile.objects.select_for_update().get(pk=customer.pk)


@transaction.atomic
def pay(customer, amount: Decimal, payment, description: str) -> WalletTransaction:
    _lock(customer)
    if balance(customer) < amount:
        raise DomainError("Not enough balance in your Click Wallet.", code="insufficient_wallet_balance",
                          details={"balance": str(balance(customer)), "required": str(amount)})
    return WalletTransaction.objects.create(customer=customer, kind=WalletTransaction.Kind.PAYMENT, amount=-amount,
                                            payment=payment, description=description)


@transaction.atomic
def refund(customer, amount: Decimal, payment, description: str) -> WalletTransaction | None:
    _lock(customer)
    if WalletTransaction.objects.filter(payment=payment, kind=WalletTransaction.Kind.REFUND).exists():
        return None
    txn = WalletTransaction.objects.create(customer=customer, kind=WalletTransaction.Kind.REFUND, amount=amount,
                                           payment=payment, description=description)
    notify(customer, NotificationCategory.WALLET, f"₹{amount} refunded to your Click Wallet", description, "/wallet")
    return txn
