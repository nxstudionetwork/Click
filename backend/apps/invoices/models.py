"""
Invoices: one per payment where money was actually taken (captured, or later refunded). Built from that payment and
the order / booking it paid for, numbered once and kept, so the document a customer downloads never changes behind
their back except to record refunds (shown as refund documents, numbered separately).
"""

from django.db import models

from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile


def _number():
    import secrets

    return "INV-" + secrets.token_hex(4).upper()


class Invoice(BaseModel):
    class Status(models.TextChoices):
        GENERATED = "generated", "Generated"
        UPDATED = "updated", "Updated"
        REFUND = "refund_document", "Refund document available"
        CANCELLED = "cancelled", "Cancelled"

    number = models.CharField(max_length=16, unique=True, default=_number, editable=False)
    customer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT, related_name="invoices")
    payment = models.OneToOneField("payments.Payment", on_delete=models.PROTECT, related_name="invoice")
    service = models.CharField(max_length=20)
    title = models.CharField(max_length=40, default="Invoice", help_text="Legal document title appropriate to the seller's registration.")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.GENERATED)
    reference = models.CharField(max_length=40, help_text="Order / booking number.")
    seller = models.JSONField(default=dict)
    buyer = models.JSONField(default=dict)
    lines = models.JSONField(default=list)
    totals = models.JSONField(default=dict)
    refunds = models.JSONField(default=list, blank=True)
    issued_at = models.DateTimeField()

    class Meta:
        ordering = ["-issued_at"]
        indexes = [models.Index(fields=["customer", "-issued_at"], name="invoice_customer_recent_idx")]
