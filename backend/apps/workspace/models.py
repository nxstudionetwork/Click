"""Business OS workspace records: the central notification inbox for every OS account (and every future module)."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel


class WorkNotification(BaseModel):
    class Type(models.TextChoices):
        APPROVAL_REQUEST = "approval_request", "Approval request"
        APPROVAL_RESULT = "approval_result", "Approval result"
        TASK_ASSIGNED = "task_assigned", "Task assignment"
        DEADLINE = "deadline", "Deadline"
        SECURITY = "security", "Security alert"
        SYSTEM = "system", "System alert"
        BUSINESS = "business", "Business alert"
        PARTNER = "partner", "Partner event"
        WORKFLOW = "workflow", "Workflow event"
        ANNOUNCEMENT = "announcement", "Announcement"

    # Never muted: people must always hear about security and the decisions waiting on them.
    ESSENTIAL = frozenset({Type.SECURITY, Type.APPROVAL_REQUEST})

    class Priority(models.TextChoices):
        NORMAL = "normal", "Normal"
        IMPORTANT = "important", "Important"
        CRITICAL = "critical", "Critical"

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="work_notifications")
    type = models.CharField(max_length=20, choices=Type.choices)
    module = models.CharField(max_length=40, blank=True)
    title = models.CharField(max_length=160)
    body = models.CharField(max_length=500, blank=True)
    link_path = models.CharField(max_length=200, blank=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    read_at = models.DateTimeField(null=True, blank=True)
    channels = models.JSONField(default=list, blank=True, help_text="Channels this was delivered to, e.g. ['in_app','email'].")
    dedupe_key = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "-created_at"], name="worknotif_recipient_recent_idx"),
            models.Index(fields=["recipient"], condition=Q(read_at__isnull=True), name="worknotif_unread_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["recipient", "dedupe_key"], condition=~Q(dedupe_key=""), name="worknotif_dedupe"),
        ]
