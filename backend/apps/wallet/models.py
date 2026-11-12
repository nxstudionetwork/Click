"""
Click. Wallet: the customer's stored value and Click. credits, kept as an append-only ledger. The balance is always the
sum of the ledger (never a stored number), so it cannot drift and every rupee is auditable.

  WalletTransaction   one ledger line. `bucket` says which money it is:
                        cash   — money added (top-ups), refunds of cash spend, adjustments
                        promo  — promotional credit, cashback and rewards conversions; may expire and is spent first
                      Credits in the promo bucket are *lots* (`expires_at`); every promo debit points at the lot it used
                      (`lot`), so the unspent part of each lot is exact and expires on its own.
  WalletAccount       wallet status (active / restricted / locked / suspended / closed) with the reason shown to the
                      customer; created on first use
  WalletTopUp         "add money": an intent with the payment provider; the wallet is credited only after the
                      provider's signed confirmation is verified (once — replays are ignored)
  CashbackOffer       cashback Click. funds on eligible completed purchases, credited as promo credit
"""

from decimal import Decimal

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
        CASHBACK = "cashback", "Cashback"
        REWARD = "reward", "Rewards conversion"
        PAYMENT = "payment", "Payment"
        EXPIRY = "expiry", "Credit expired"
        ADJUSTMENT = "adjustment", "Adjustment"

    class Bucket(models.TextChoices):
        CASH = "cash", "Wallet balance"
        PROMO = "promo", "Promotional credit"

    CREDIT_KINDS = {Kind.TOPUP, Kind.REFUND, Kind.PROMO, Kind.CASHBACK, Kind.REWARD}

    customer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT, related_name="wallet_transactions")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    bucket = models.CharField(max_length=6, choices=Bucket.choices, default=Bucket.CASH)
    amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Positive = credit, negative = debit.")
    currency = models.CharField(max_length=3, default=settings.CLICK_DEFAULT_CURRENCY)
    description = models.CharField(max_length=200)
    payment = models.ForeignKey("payments.Payment", on_delete=models.PROTECT, null=True, blank=True, related_name="wallet_transactions")
    lot = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="consumptions",
                            help_text="Promo debits / expiry: the promo credit lot used.")
    expires_at = models.DateTimeField(null=True, blank=True, help_text="Promo credit lots only.")
    reference = models.CharField(max_length=80, blank=True, help_text="Idempotency key of the source (cashback:<order>, reward:<redemption>…).")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                   help_text="Staff member who issued a promo/adjustment.")

    PROMO_KINDS = {Kind.PROMO, Kind.CASHBACK, Kind.REWARD}

    def save(self, *args, **kwargs):
        if self.kind in self.PROMO_KINDS:  # promotional credit always lives in the promo bucket
            self.bucket = self.Bucket.PROMO
        super().save(*args, **kwargs)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["customer", "-created_at"], name="wallet_customer_recent_idx"),
                   models.Index(fields=["customer", "bucket", "expires_at"], name="wallet_customer_lots_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(kind__in=["topup", "refund", "promo", "cashback", "reward"], amount__gt=0)
                | Q(kind__in=["payment", "expiry"], amount__lt=0) | Q(kind="adjustment"),
                name="wallet_amount_sign_matches_kind_v2",
            ),
            models.CheckConstraint(condition=Q(kind__in=["promo", "cashback", "reward"], bucket="promo") | ~Q(kind__in=["promo", "cashback", "reward"]),
                                   name="wallet_promo_kinds_in_promo_bucket"),
            # A payment debits each lot / the cash bucket once; a top-up credits once.
            models.UniqueConstraint(fields=["payment", "lot"], condition=Q(kind="payment", lot__isnull=False), name="wallet_one_debit_per_payment_lot"),
            models.UniqueConstraint(fields=["payment", "bucket"], condition=Q(kind="payment", lot__isnull=True, payment__isnull=False),
                                    name="wallet_one_debit_per_payment_bucket"),
            models.UniqueConstraint(fields=["payment"], condition=Q(kind="topup", payment__isnull=False), name="wallet_one_topup_per_payment"),
            models.UniqueConstraint(fields=["reference"], condition=~Q(reference=""), name="wallet_unique_reference"),
        ]


class WalletAccount(BaseModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        RESTRICTED = "restricted", "Restricted"
        LOCKED = "locked", "Temporarily locked"
        SUSPENDED = "suspended", "Suspended"
        CLOSED = "closed", "Closed"

    customer = models.OneToOneField(CustomerProfile, on_delete=models.CASCADE, related_name="wallet_account")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    status_reason = models.CharField(max_length=200, blank=True, help_text="Shown to the customer.")
    status_changed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Wallet {self.customer_id} ({self.status})"


class WalletTopUp(BaseModel):
    class Status(models.TextChoices):
        CREATED = "created", "Waiting for payment"
        PENDING = "pending", "Confirming with the payment provider"
        SUCCEEDED = "succeeded", "Money added"
        FAILED = "failed", "Payment failed"
        EXPIRED = "expired", "Expired"

    customer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT, related_name="wallet_topups")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default=settings.CLICK_DEFAULT_CURRENCY)
    method = models.CharField(max_length=20, help_text="How the customer pays the provider (upi, card…).")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CREATED)
    provider = models.CharField(max_length=30)
    provider_reference = models.CharField(max_length=120, blank=True)
    failure_reason = models.CharField(max_length=200, blank=True)
    idempotency_key = models.CharField(max_length=64)
    payment = models.OneToOneField("payments.Payment", on_delete=models.PROTECT, null=True, blank=True, related_name="wallet_topup_record")
    wallet_transaction = models.OneToOneField(WalletTransaction, on_delete=models.PROTECT, null=True, blank=True, related_name="topup")
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["customer", "idempotency_key"], name="wallet_topup_idempotency"),
                       models.CheckConstraint(condition=Q(amount__gt=0), name="wallet_topup_amount_positive")]


class CashbackOffer(BaseModel):
    """Cashback Click. funds on eligible completed purchases; credited as promotional credit after completion."""

    SERVICES = [("food", "Food"), ("groceries", "Groceries"), ("shop", "Shop"), ("travel", "Travel"), ("bookings", "Bookings"),
                ("hotels", "Hotels"), ("any", "Any eligible service")]

    title = models.CharField(max_length=100)
    service = models.CharField(max_length=12, choices=SERVICES)
    percent = models.PositiveSmallIntegerField()
    max_cashback = models.DecimalField(max_digits=10, decimal_places=2)
    min_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    wallet_payment_only = models.BooleanField(default=True, help_text="Only when the purchase was paid with Click. Wallet.")
    credit_valid_days = models.PositiveSmallIntegerField(default=60)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-percent"]
        constraints = [models.CheckConstraint(condition=Q(percent__gte=1, percent__lte=50), name="wallet_cashback_percent_range")]

    def __str__(self) -> str:
        return self.title
