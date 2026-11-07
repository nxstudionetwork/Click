"""
Append-only customer activity events (one row per event, never a giant JSON
history). Feeds history, personalisation and Buddy later. Domain tables
(orders, bookings…) stay the source of truth; this records what happened.
"""

from django.db import models

from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile


class CustomerActivity(BaseModel):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="activities")
    verb = models.CharField(max_length=40, help_text="Dotted event name, e.g. 'order.placed', 'wishlist.added'.")
    object_type = models.CharField(max_length=40, blank=True)
    object_id = models.UUIDField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True, help_text="Small, event-specific attributes only.")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "-created_at"], name="activity_customer_recent_idx"),
            models.Index(fields=["verb", "-created_at"], name="activity_verb_recent_idx"),
        ]
