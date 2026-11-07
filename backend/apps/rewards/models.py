"""
Append-only points ledger. The balance is always derived from the ledger,
never stored as a mutable number, so it is auditable and cannot drift.
"""

from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile


class RewardTransaction(BaseModel):
    class Kind(models.TextChoices):
        EARN = "earn", "Earned"
        REDEEM = "redeem", "Redeemed"
        EXPIRE = "expire", "Expired"
        ADJUST = "adjust", "Adjustment"

    customer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT, related_name="reward_transactions")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    points = models.IntegerField(help_text="Positive for credits, negative for debits.")
    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, null=True, blank=True, related_name="reward_transactions")
    description = models.CharField(max_length=200)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["order"], condition=Q(kind="earn"), name="rewards_one_earn_per_order"),
            models.CheckConstraint(
                condition=(Q(kind="earn", points__gt=0) | Q(kind__in=["redeem", "expire"], points__lt=0) | Q(kind="adjust")),
                name="rewards_points_sign_matches_kind",
            ),
        ]
