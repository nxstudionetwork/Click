"""
Click. Rewards: an append-only points ledger. The balance is always derived from the ledger, never stored as a mutable
number, so it is auditable and cannot drift. Earned points are lots with an expiry; redemptions and expiries use the
oldest-expiring points first.

  RewardTransaction   earn (orders, completed bookings, missions), redeem, expire, adjust (reversals, linked to the
                      entry they reverse)
  RewardCatalogItem   what points can be redeemed for (today: Click. Wallet credit) — the conversion is the item's own
                      points cost and value, set by Click.
  RewardRedemption    a redemption: points deducted and the reward issued in one transaction, idempotent
  RewardMission       a goal measured from real Click. records (completed orders, distinct restaurants, services used…),
                      rewarded once
  RewardCampaign      a time-boxed earning multiplier for a service, applied by the server when points are earned
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
    reference = models.CharField(max_length=60, blank=True, help_text="What earned the points when it isn't an order, e.g. 'travel:<id>'.")
    description = models.CharField(max_length=200)
    reverses = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="reversals",
                                 help_text="Adjustments: the entry this reverses.")
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["order"], condition=Q(kind="earn"), name="rewards_one_earn_per_order"),
            models.UniqueConstraint(fields=["reference"], condition=Q(kind="earn") & ~Q(reference=""), name="rewards_one_earn_per_reference"),
            models.CheckConstraint(
                condition=(Q(kind="earn", points__gt=0) | Q(kind__in=["redeem", "expire"], points__lt=0) | Q(kind="adjust")),
                name="rewards_points_sign_matches_kind",
            ),
        ]


class RewardCatalogItem(BaseModel):
    class Kind(models.TextChoices):
        WALLET_CREDIT = "wallet_credit", "Click. Wallet credit"

    title = models.CharField(max_length=100)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.WALLET_CREDIT)
    description = models.CharField(max_length=200, blank=True)
    points_cost = models.PositiveIntegerField()
    value = models.DecimalField(max_digits=10, decimal_places=2, help_text="Wallet credit issued.")
    credit_valid_days = models.PositiveSmallIntegerField(default=90)
    min_tier = models.CharField(max_length=12, blank=True, help_text="Tier code needed, blank = everyone.")
    terms = models.TextField(blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "points_cost"]
        constraints = [models.CheckConstraint(condition=Q(points_cost__gt=0, value__gt=0), name="rewards_catalog_positive")]

    def __str__(self) -> str:
        return self.title


class RewardRedemption(BaseModel):
    class Status(models.TextChoices):
        COMPLETED = "completed", "Reward issued"
        FAILED = "failed", "Failed"

    customer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT, related_name="reward_redemptions")
    item = models.ForeignKey(RewardCatalogItem, on_delete=models.PROTECT, related_name="redemptions")
    points = models.PositiveIntegerField()
    value = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.COMPLETED)
    reward_transaction = models.OneToOneField(RewardTransaction, on_delete=models.PROTECT, null=True, blank=True, related_name="redemption")
    wallet_transaction = models.OneToOneField("wallet.WalletTransaction", on_delete=models.PROTECT, null=True, blank=True, related_name="reward_redemption")
    idempotency_key = models.CharField(max_length=64)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["customer", "idempotency_key"], name="rewards_redemption_idempotency")]


class RewardMission(BaseModel):
    class Metric(models.TextChoices):
        ORDERS = "orders", "Completed orders"
        RESTAURANTS = "restaurants", "Different restaurants"
        RIDES = "rides", "Completed rides"
        SERVICES_USED = "services_used", "Different Click. services used"
        TRAVEL = "travel", "Completed journeys"
        STAYS = "stays", "Completed hotel stays"
        VISITS = "visits", "Completed visits (Bookings)"
        PROFILE = "profile", "Profile completed"

    code = models.SlugField(max_length=40, unique=True)
    title = models.CharField(max_length=80)
    description = models.CharField(max_length=200)
    metric = models.CharField(max_length=16, choices=Metric.choices)
    target = models.PositiveSmallIntegerField(default=1)
    points = models.PositiveIntegerField()
    service = models.CharField(max_length=20, blank=True, help_text="Where to go to make progress (route key).")
    starts_at = models.DateTimeField(null=True, blank=True, help_text="Only activity from here counts; blank = all time.")
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "points"]

    def __str__(self) -> str:
        return self.title


class RewardCampaign(BaseModel):
    title = models.CharField(max_length=100)
    description = models.CharField(max_length=200, blank=True)
    service = models.CharField(max_length=20, help_text="food / groceries / shop / travel / bookings / any")
    multiplier = models.DecimalField(max_digits=3, decimal_places=1)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-starts_at"]
        constraints = [models.CheckConstraint(condition=Q(multiplier__gt=1, multiplier__lte=5), name="rewards_campaign_multiplier_range")]

    def __str__(self) -> str:
        return self.title
