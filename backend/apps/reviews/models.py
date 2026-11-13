"""Shared review moderation: customers report a review; the review stays in its own service's table."""

from django.db import models

from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile


class ReviewReport(BaseModel):
    class Reason(models.TextChoices):
        SPAM = "spam", "Spam or advertising"
        ABUSE = "abuse", "Abusive or hateful"
        FALSE = "false", "Misleading or not about this"
        PRIVATE = "private", "Shares personal information"
        OTHER = "other", "Something else"

    kind = models.CharField(max_length=20, help_text="Review type key from apps.reviews.hub.KINDS.")
    review_id = models.UUIDField()
    reporter = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="review_reports")
    reason = models.CharField(max_length=10, choices=Reason.choices)
    note = models.CharField(max_length=300, blank=True)
    resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["kind", "review_id", "reporter"], name="review_report_once_per_reporter")]
