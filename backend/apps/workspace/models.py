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
    archived_at = models.DateTimeField(null=True, blank=True, help_text="Cleared from the inbox (essential unread items can't be).")
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


class Alert(BaseModel):
    """
    An exception that needs someone's attention (payment failures, SLA breaches, verification backlogs, security
    signals, system problems, expiring documents …). Raised and auto-resolved by detectors (apps.workspace.alerts),
    each tied to a permission so only people allowed to see the source data see the alert.
    """

    class Severity(models.TextChoices):
        CRITICAL = "critical", "Critical"
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"
        LOW = "low", "Low"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        RESOLVED = "resolved", "Resolved"

    SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    organization = models.ForeignKey("organization.Organization", on_delete=models.CASCADE, related_name="alerts")
    key = models.CharField(max_length=160, help_text="Detector key + subject; one open alert per key.")
    detector = models.CharField(max_length=60, db_index=True)
    category = models.CharField(max_length=20)  # finance | operations | partner | security | technology | people | support | compliance
    severity = models.CharField(max_length=10, choices=Severity.choices)
    title = models.CharField(max_length=200)
    detail = models.CharField(max_length=500, blank=True)
    source = models.CharField(max_length=80, help_text="Where the data comes from, e.g. Payments.")
    link_path = models.CharField(max_length=200, blank=True)
    recommended_action = models.CharField(max_length=240, blank=True)
    permission = models.CharField(max_length=100, blank=True, help_text="Who may see it. Blank = only the subject user.")
    org_wide_only = models.BooleanField(default=True, help_text="Platform-wide data: needs an organization-wide grant.")
    org_unit = models.ForeignKey("organization.OrgUnit", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    subject_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="+",
                                     help_text="Personal alerts (e.g. your account was locked).")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.OPEN)
    is_risk = models.BooleanField(default=False, help_text="Also shown in Risk Watch.")
    due_on = models.DateField(null=True, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    metric = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["status", "severity", "-last_seen_at"]
        indexes = [models.Index(fields=["organization", "status"], name="alert_org_status_idx")]
        constraints = [models.UniqueConstraint(fields=["organization", "key"], condition=~Q(status="resolved"), name="alert_one_open_per_key")]


class Announcement(BaseModel):
    class Category(models.TextChoices):
        COMPANY = "company", "Company"
        POLICY = "policy", "Policy update"
        MAINTENANCE = "maintenance", "System maintenance"
        OPERATIONAL = "operational", "Operational notice"
        SECURITY = "security", "Security"
        FEATURE = "feature", "New in Business OS"

    class Priority(models.TextChoices):
        NORMAL = "normal", "Normal"
        IMPORTANT = "important", "Important"
        CRITICAL = "critical", "Critical"

    organization = models.ForeignKey("organization.Organization", on_delete=models.CASCADE, related_name="announcements")
    title = models.CharField(max_length=160)
    body = models.TextField(max_length=4000)
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.COMPANY)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    audience = models.JSONField(default=dict, blank=True, help_text='{} = everyone; or {"units": [...], "departments": [...], "roles": [...]}')
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    requires_ack = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        ordering = ["-starts_at"]


class AnnouncementAck(BaseModel):
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE, related_name="acks")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    dismissed = models.BooleanField(default=False, help_text="Hidden from Home (only allowed for non-critical announcements).")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["announcement", "user"], name="announcement_ack_unique")]
