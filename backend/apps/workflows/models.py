"""
Reusable approvals and tasks. Every module that needs sign-off (expenses, purchase orders, refunds, hiring, stock
adjustments, partner verification …) creates an ApprovalRequest against a policy instead of building its own.

    ApprovalPolicy  "finance.expense"   approval_type=expense   submit_permission=finance.expense.create
      └── levels: 1 Manager  (finance.expense.approve, from ₹0)
                  2 Head     (finance.expense.approve, from ₹50,000)   ← only applies at/above the threshold
    ApprovalRequest → ApprovalStep per applicable level → approved / rejected / cancelled

Who may decide a step: holders of the level's permission whose scope covers the request's unit/department, whose
approval limit (RoleApprovalLimit for the policy's type) covers the amount, who did not raise the request
(segregation of duties) — or an active delegate of such a person. No amounts are hard-coded: they're data.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel
from apps.organization.models import Department, Organization, OrgUnit


class ApprovalPolicy(BaseModel):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="approval_policies")
    key = models.CharField(max_length=60, help_text="module.thing, e.g. finance.expense")
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=300, blank=True)
    module = models.CharField(max_length=40)
    approval_type = models.CharField(max_length=16, default="general", help_text="Matches RoleApprovalLimit.approval_type.")
    submit_permission = models.CharField(max_length=100, help_text="Permission needed to raise a request.")
    currency = models.CharField(max_length=3, default="INR")
    requires_amount = models.BooleanField(default=False)
    amount_unit = models.CharField(max_length=10, default="currency",
                                   help_text="What `amount` measures: currency (money), days (leave) or count.")
    high_value_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True,
                                            help_text="Requests at or above this are flagged high value.")
    allow_request_changes = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["module", "name"]
        constraints = [models.UniqueConstraint(fields=["organization", "key"], name="approval_policy_key_unique")]

    def __str__(self) -> str:
        return self.name


class ApprovalLevel(BaseModel):
    policy = models.ForeignKey(ApprovalPolicy, on_delete=models.CASCADE, related_name="levels")
    sequence = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=80)
    approver_permission = models.CharField(max_length=100)
    min_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                     help_text="This level applies only when the amount is at least this much.")
    enforce_limit = models.BooleanField(default=True, help_text="Approver's approval limit must cover the amount.")
    escalate_after_hours = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [models.UniqueConstraint(fields=["policy", "sequence"], name="approval_level_sequence_unique")]


class ApprovalRequest(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"
        CHANGES_REQUESTED = "changes_requested", "Changes requested"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    policy = models.ForeignKey(ApprovalPolicy, on_delete=models.PROTECT, related_name="requests")
    reference = models.CharField(max_length=24, unique=True)
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True, max_length=4000)
    amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="INR")
    resource_type = models.CharField(max_length=60, blank=True, help_text="The module record this request is about, if any.")
    resource_id = models.CharField(max_length=64, blank=True)
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="approval_requests")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    blocking = models.BooleanField(default=False, help_text="Other work waits on this decision (set by the module).")
    current_sequence = models.PositiveSmallIntegerField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "status"], name="approvalreq_org_status_idx")]

    def __str__(self) -> str:
        return f"{self.reference} · {self.title}"


class ApprovalStep(BaseModel):
    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting"
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        SKIPPED = "skipped", "Skipped"

    request = models.ForeignKey(ApprovalRequest, on_delete=models.CASCADE, related_name="steps")
    sequence = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=80)
    approver_permission = models.CharField(max_length=100)
    enforce_limit = models.BooleanField(default=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.WAITING)
    activated_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    on_behalf_of = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                     help_text="Set when a delegate decided for someone else.")
    decided_at = models.DateTimeField(null=True, blank=True)
    comment = models.TextField(blank=True, max_length=2000)

    class Meta:
        ordering = ["sequence"]
        constraints = [models.UniqueConstraint(fields=["request", "sequence"], name="approval_step_unique")]


class ApprovalComment(BaseModel):
    """History entries that aren't decisions (comments, escalations, submissions, cancellations)."""

    request = models.ForeignKey(ApprovalRequest, on_delete=models.CASCADE, related_name="history")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    kind = models.CharField(max_length=24)  # submitted | approved | rejected | changes_requested | resubmitted | cancelled | comment | escalated
    body = models.TextField(blank=True, max_length=2000)

    class Meta:
        ordering = ["created_at"]


class ApprovalDelegation(BaseModel):
    delegator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="delegations_given")
    delegate = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="delegations_received")
    policy = models.ForeignKey(ApprovalPolicy, on_delete=models.CASCADE, null=True, blank=True, related_name="+",
                               help_text="Blank = every policy.")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    reason = models.CharField(max_length=200, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-starts_at"]
        constraints = [models.CheckConstraint(condition=~Q(delegator=models.F("delegate")), name="delegation_not_self"),
                       models.CheckConstraint(condition=Q(ends_at__gt=models.F("starts_at")), name="delegation_ends_after_start")]


class Task(BaseModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In progress"
        DONE = "done", "Done"
        CANCELLED = "cancelled", "Cancelled"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Medium"
        HIGH = "high", "High"
        URGENT = "urgent", "Critical"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True, max_length=4000)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="os_tasks")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="os_tasks_created")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    priority = models.CharField(max_length=8, choices=Priority.choices, default=Priority.NORMAL)
    due_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    module = models.CharField(max_length=40, blank=True)
    link_path = models.CharField(max_length=200, blank=True)
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    source_type = models.CharField(max_length=60, blank=True, help_text="Module record this task belongs to, e.g. people.onboarding.")
    source_id = models.CharField(max_length=64, blank=True)
    snoozed_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["status", "due_at", "-created_at"]
        indexes = [models.Index(fields=["assignee", "status"], name="task_assignee_status_idx")]

    def __str__(self) -> str:
        return self.title


class TaskComment(BaseModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    body = models.TextField(max_length=2000)

    class Meta:
        ordering = ["created_at"]
