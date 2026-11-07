"""
Payments are separate records (not columns on Order) so an order can have
multiple attempts, refunds and providers. Only cash on delivery is enabled
today; online gateways plug in via `providers.py` in Phase 3.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel


class PaymentMethod(models.TextChoices):
    CASH_ON_DELIVERY = "cash_on_delivery", "Cash on delivery"


class Payment(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        AUTHORIZED = "authorized", "Authorized"
        CAPTURED = "captured", "Captured"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="payments")
    method = models.CharField(max_length=30, choices=PaymentMethod.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default=settings.CLICK_DEFAULT_CURRENCY)
    provider = models.CharField(max_length=40, default="internal")
    provider_reference = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["provider", "provider_reference"], name="payments_provider_ref_idx")]
        constraints = [models.CheckConstraint(condition=Q(amount__gte=0), name="payments_amount_non_negative")]
