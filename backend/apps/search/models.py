"""A signed-in customer's own search history (for "Recent searches" and anonymous counts for "Trending")."""

from django.db import models

from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile


class SearchHistory(BaseModel):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="search_history")
    query = models.CharField(max_length=100)
    normalized = models.CharField(max_length=100, db_index=True)
    results = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["customer", "-created_at"], name="search_hist_customer_idx"),
                   models.Index(fields=["normalized", "-created_at"], name="search_hist_trend_idx")]
