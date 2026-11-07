from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile


class NotificationCategory(models.TextChoices):
    ORDERS = "orders", "Orders"
    RIDES = "rides", "Rides"
    DELIVERIES = "deliveries", "Deliveries"
    PAYMENTS = "payments", "Payments"
    WALLET = "wallet", "Wallet"
    BOOKINGS = "bookings", "Bookings"
    OFFERS = "offers", "Offers"
    REWARDS = "rewards", "Rewards"
    SUPPORT = "support", "Support"
    SYSTEM = "system", "System"


class Notification(BaseModel):
    """In-app notification. Push/SMS/email channels fan out from the same record later."""

    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="notifications")
    category = models.CharField(max_length=20, choices=NotificationCategory.choices)
    title = models.CharField(max_length=120)
    body = models.CharField(max_length=300, blank=True)
    link_path = models.CharField(max_length=200, blank=True, help_text="In-app route, e.g. /orders/<id>.")
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "-created_at"], name="notif_customer_recent_idx"),
            models.Index(fields=["customer"], condition=Q(read_at__isnull=True), name="notif_customer_unread_idx"),
        ]
