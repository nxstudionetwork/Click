"""
Click. Gift Cards — a separate stored-value instrument (not Click. Wallet money).

GiftCardDesign   what can be bought: category, artwork colours, amounts, validity, services it can pay for, terms
GiftCard         one card: buyer, recipient, message, delivery, value, balance, holder (who can spend it), expiry, status
GiftCardEntry    append-only balance ledger (issue, spend, refund, expire); the balance is always its sum
"""

from __future__ import annotations

import secrets

from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I


def new_code() -> str:
    raw = "".join(secrets.choice(ALPHABET) for _ in range(16))
    return "-".join(raw[i:i + 4] for i in range(0, 16, 4))


class GiftCardDesign(BaseModel):
    class Category(models.TextChoices):
        CLICK = "click", "Click. Gift Card"
        FOOD = "food", "Food"
        SHOPPING = "shopping", "Shopping"
        GROCERIES = "groceries", "Groceries"
        OCCASION = "occasion", "Special occasions"

    title = models.CharField(max_length=80)
    category = models.CharField(max_length=12, choices=Category.choices)
    occasion = models.CharField(max_length=40, blank=True, help_text="Birthday, Wedding, Thank you…")
    tagline = models.CharField(max_length=120, blank=True)
    colors = models.JSONField(default=list, help_text="Two or three hex colours for the card artwork.")
    min_amount = models.DecimalField(max_digits=8, decimal_places=2, default=100)
    max_amount = models.DecimalField(max_digits=8, decimal_places=2, default=10000)
    presets = models.JSONField(default=list)
    validity_days = models.PositiveSmallIntegerField(default=365)
    services = models.JSONField(default=list, help_text="Where the balance can pay: food, groceries, shop.")
    terms = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "title"]

    @property
    def category_label(self) -> str:
        return self.get_category_display()


class GiftCard(BaseModel):
    class Status(models.TextChoices):
        AWAITING_PAYMENT = "awaiting_payment", "Awaiting payment"
        SCHEDULED = "scheduled", "Scheduled"
        ACTIVE = "active", "Active"
        USED = "used", "Fully used"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"

    class Delivery(models.TextChoices):
        CLICK = "click", "To their Click. account (by phone)"
        SHARE = "share", "I’ll share the code"

    code = models.CharField(max_length=19, unique=True, default=new_code, editable=False)
    design = models.ForeignKey(GiftCardDesign, on_delete=models.PROTECT, related_name="cards")
    buyer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT, related_name="gift_cards_bought")
    holder = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT, null=True, blank=True, related_name="gift_cards",
                               help_text="The customer who can spend it (set when delivered to or redeemed by them).")
    recipient_name = models.CharField(max_length=80)
    recipient_phone = models.CharField(max_length=20, blank=True)
    message = models.CharField(max_length=300, blank=True)
    delivery = models.CharField(max_length=6, choices=Delivery.choices, default=Delivery.CLICK)
    deliver_on = models.DateField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.AWAITING_PAYMENT)
    expires_at = models.DateTimeField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=64)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["buyer", "idempotency_key"], name="giftcard_buyer_idempotency"),
                       models.CheckConstraint(condition=Q(amount__gt=0), name="giftcard_amount_positive")]


class GiftCardEntry(BaseModel):
    class Kind(models.TextChoices):
        ISSUE = "issue", "Issued"
        SPEND = "spend", "Spent"
        REFUND = "refund", "Refunded to card"
        EXPIRE = "expire", "Expired"

    card = models.ForeignKey(GiftCard, on_delete=models.PROTECT, related_name="entries")
    kind = models.CharField(max_length=8, choices=Kind.choices)
    amount = models.DecimalField(max_digits=8, decimal_places=2, help_text="+ credit, − debit")
    payment = models.ForeignKey("payments.Payment", on_delete=models.PROTECT, null=True, blank=True, related_name="gift_card_entries")
    description = models.CharField(max_length=160)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(kind__in=["issue", "refund"], amount__gt=0) | Q(kind__in=["spend", "expire"], amount__lt=0),
                                   name="giftcard_entry_sign"),
            models.UniqueConstraint(fields=["payment", "kind"], condition=Q(payment__isnull=False), name="giftcard_entry_once_per_payment"),
        ]
