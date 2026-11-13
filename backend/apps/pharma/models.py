"""
Click. Pharma. Pharmacies are stores (store_type "pharmacy") and medicines are products, so search, cart, checkout,
payments, orders, invoices and reviews are the shared ones. Pharma adds:

Prescription     a customer's uploaded prescription for one pharmacy, reviewed by that pharmacy's pharmacist.
                 Never approved automatically; only "verified" lets prescription-only items be ordered, once.
RefillReminder   "remind me to reorder this every N days" for a product the customer bought.
"""

from __future__ import annotations

import secrets

from django.db import models

from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile


def _ref():
    return "RX-" + secrets.token_hex(4).upper()


class Prescription(BaseModel):
    class Status(models.TextChoices):
        UNDER_REVIEW = "under_review", "Under review"
        CLARIFICATION = "clarification", "More information needed"
        VERIFIED = "verified", "Verified"
        PARTIAL = "partial", "Partially accepted"
        REJECTED = "rejected", "Not valid"
        USED = "used", "Used for an order"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"

    reference = models.CharField(max_length=12, unique=True, default=_ref, editable=False)
    customer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT, related_name="prescriptions")
    pharmacy = models.ForeignKey("stores.Store", on_delete=models.PROTECT, related_name="prescriptions")
    file = models.FileField(upload_to="private/prescriptions/%Y/%m/", help_text="Served only to its owner and the pharmacy.")
    file_name = models.CharField(max_length=120)
    file_type = models.CharField(max_length=40)
    note = models.CharField(max_length=500, blank=True, help_text="What the customer needs (optional).")
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.UNDER_REVIEW)
    pharmacist_note = models.CharField(max_length=500, blank=True)
    approved_items = models.ManyToManyField("catalog.Product", blank=True, related_name="+",
                                            help_text="Prescription items the pharmacist approved (empty = any prescription item of this pharmacy).")
    alternative_note = models.CharField(max_length=300, blank=True, help_text="An alternative the pharmacist proposes; the customer decides.")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey("users.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    valid_until = models.DateField(null=True, blank=True)
    order = models.ForeignKey("orders.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="prescriptions")

    class Meta:
        ordering = ["-created_at"]


class RefillReminder(BaseModel):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="refill_reminders")
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="+")
    every_days = models.PositiveSmallIntegerField()
    next_on = models.DateField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["next_on"]
        constraints = [models.UniqueConstraint(fields=["customer", "product"], name="refill_once_per_product")]
