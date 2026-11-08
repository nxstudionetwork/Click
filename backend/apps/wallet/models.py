"""
Click Wallet: an append-only ledger per customer. The balance is always the
sum of the ledger, never a stored number, so it cannot drift and every rupee
is auditable. Credits come from refunds and staff-issued promotional credit;
top-ups arrive with the payment-gateway integration.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile


class WalletTransaction(BaseModel):
    class Kind(models.TextChoices):
        TOPUP = "topup", "Money added"
        REFUND = "refund", "Refund"
        PROMO = "promo", "Promotional credit"
        PAYMENT = "payment", "Payment"
        ADJUSTMENT = "adjustment", "Adjustment"

    CREDIT_KINDS = {Kind.TOPUP, Kind.REFUND, Kind.PROMO}

    customer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT, related_name="wallet_transactions")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Positive = credit, negative = debit.")
    currency = models.CharField(max_length=3, default=settings.CLICK_DEFAULT_CURRENCY)
    description = models.CharField(max_length=200)
    payment = models.ForeignKey("payments.Payment", on_delete=models.PROTECT, null=True, blank=True, related_name="wallet_transactions")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                   help_text="Staff member who issued a promo/adjustment.")

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["customer", "-created_at"], name="wallet_customer_recent_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(kind__in=["topup", "refund", "promo"], amount__gt=0) | Q(kind="payment", amount__lt=0) | Q(kind="adjustment"),
                name="wallet_amount_sign_matches_kind",
            ),
            models.UniqueConstraint(fields=["payment", "kind"], condition=Q(payment__isnull=False), name="wallet_one_entry_per_payment_kind"),
        ]
