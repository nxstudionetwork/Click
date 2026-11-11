import secrets

from django.db import models

from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile


def _reference() -> str:
    return "SUP-" + "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(7))


class SupportTicket(BaseModel):
    """Customer-raised ticket. Agents work these from Business OS (Phase 6)."""

    class Category(models.TextChoices):
        ORDER = "order", "Order"
        PAYMENT = "payment", "Payment"
        DELIVERY = "delivery", "Delivery"
        RIDE = "ride", "Ride"
        ACCOUNT = "account", "Account"
        SERVICE = "service", "Service"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In progress"
        AWAITING_CUSTOMER = "awaiting_customer", "Awaiting your reply"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    reference = models.CharField(max_length=12, unique=True, default=_reference, editable=False)
    customer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT, related_name="support_tickets")
    order = models.ForeignKey("orders.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="support_tickets")
    parcel = models.ForeignKey("parcels.ParcelOrder", on_delete=models.SET_NULL, null=True, blank=True, related_name="support_tickets")
    service_booking = models.ForeignKey("professionals.ServiceBooking", on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name="support_tickets")
    event_booking = models.ForeignKey("eventhub.EventBooking", on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name="support_tickets")
    category = models.CharField(max_length=20, choices=Category.choices)
    subject = models.CharField(max_length=150)
    message = models.TextField(max_length=4000)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["customer", "-created_at"], name="support_customer_recent_idx"),
                   models.Index(fields=["status"], name="support_status_idx")]
