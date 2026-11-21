"""
Product analytics events for Business OS. Only allow-listed event names and properties are stored; no free text,
no contact details, no payment data. Server-side outcomes (orders, bookings, payments) are already recorded by each
service and in the activity log; these are the client-side signals (opens, views, searches, funnel steps).
"""

from django.db import models

from apps.core.models import BaseModel

EVENTS = {
    "app_opened": [], "screen_viewed": ["screen"], "search_performed": ["group", "results"], "category_viewed": ["service", "category"],
    "store_viewed": ["store_id", "service"], "product_viewed": ["product_id", "service"], "cart_created": ["service"],
    "checkout_started": ["service", "method"], "offer_viewed": ["offer_id", "service"], "offer_used": ["offer_id", "service"],
    "support_requested": ["category"], "referral_shared": ["channel"], "buddy_opened": [], "discover_opened": [],
}


class AnalyticsEvent(BaseModel):
    name = models.CharField(max_length=40)
    customer = models.ForeignKey("customers.CustomerProfile", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    session = models.CharField(max_length=40, blank=True, help_text="Random per-app-session id from the client (no device fingerprint).")
    platform = models.CharField(max_length=12, blank=True)
    props = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField()

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [models.Index(fields=["name", "-occurred_at"], name="analytics_name_time_idx")]
