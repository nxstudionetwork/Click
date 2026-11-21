"""
Identity & Access for the Business OS.

    User (apps.users: one identity for every Click actor)
      └── OSAccount     who may use the Business OS, how (employee / partner / external), status, MFA, lockout
      └── OSSession     one signed-in device; access tokens carry its id so revocation is immediate
      └── RoleAssignment(role, anchor unit / department / team, validity)
    Role ──< RolePermission(permission, scope)   module.resource.action @ scope
         ──< RoleApprovalLimit(type, max amount)
    ServiceAccount     non-human API identity (hashed key), never an interactive login

HR (apps.people) says who someone is. This app says what they can do. Never mix the two.
"""

import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import BaseModel
from apps.organization.models import Department, Organization, OrgUnit, Team

from .registry import APPROVAL_TYPES, SCOPES, SCOPE_LABELS


class AccountKind(models.TextChoices):
    EMPLOYEE = "employee", "Employee"
    PARTNER = "partner", "Partner / business"
    EXTERNAL = "external", "Other authorized account"


class IdentityType(models.TextChoices):
    """What the relationship is (independent of `kind`, which is the audience the account signs in as)."""

    EMPLOYEE = "employee", "Employee"
    CONTRACTOR = "contractor", "Contractor"
    CONSULTANT = "consultant", "Consultant"
    INTERN = "intern", "Intern"
    TEMPORARY = "temporary", "Temporary worker"
    PARTNER_USER = "partner_user", "Partner user"
    SUPPORT = "support", "Customer support user"
    EXTERNAL = "external", "Other external user"


class OSAccount(BaseModel):
    class Status(models.TextChoices):
        INVITED = "invited", "Invited"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        DEACTIVATED = "deactivated", "Deactivated"
        EXPIRED = "expired", "Expired"
        ARCHIVED = "archived", "Archived"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="os_account")
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="accounts")
    kind = models.CharField(max_length=12, choices=AccountKind.choices, default=AccountKind.EMPLOYEE)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.INVITED)
    partner = models.ForeignKey("partners.Partner", on_delete=models.PROTECT, null=True, blank=True, related_name="os_accounts",
                                help_text="Partner accounts only: the partner business this login acts for.")
    external_org_name = models.CharField(max_length=150, blank=True)
    identity_type = models.CharField(max_length=16, choices=IdentityType.choices, default=IdentityType.EMPLOYEE)
    expires_at = models.DateTimeField(null=True, blank=True, help_text="Contractors, interns, temporary workers: access ends here.")

    # Security
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    password_changed_at = models.DateTimeField(null=True, blank=True)
    mfa_secret = models.TextField(blank=True, help_text="Encrypted TOTP secret.")
    mfa_pending_secret = models.TextField(blank=True)
    mfa_enabled_at = models.DateTimeField(null=True, blank=True)
    mfa_last_counter = models.BigIntegerField(default=0, help_text="Last accepted TOTP time step (replay protection).")
    recovery_codes = models.JSONField(default=list, blank=True, help_text="SHA-256 hashes of unused recovery codes.")

    # Workspace
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)
    timezone = models.CharField(max_length=64, blank=True)
    language = models.CharField(max_length=10, default="en")
    preferences = models.JSONField(default=dict, blank=True)
    avatar = models.ImageField(upload_to="os/avatars/", null=True, blank=True)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    invited_at = models.DateTimeField(null=True, blank=True)
    access_version = models.PositiveIntegerField(default=1, help_text="Bumped on any role/permission change so clients refetch.")

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "status"], name="osaccount_org_status_idx")]

    def __str__(self) -> str:
        return f"{self.user} [{self.kind}/{self.status}]"

    @property
    def mfa_enabled(self) -> bool:
        return bool(self.mfa_enabled_at and self.mfa_secret)

    @property
    def is_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > timezone.now())

    def bump_access(self) -> None:
        OSAccount.objects.filter(pk=self.pk).update(access_version=models.F("access_version") + 1)


class OSSession(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="os_sessions")
    refresh_jti = models.CharField(max_length=64, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    device_label = models.CharField(max_length=120, blank=True)
    mfa_verified = models.BooleanField(default=False)
    last_seen_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(help_text="Absolute end of the session, whatever the activity.")
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoke_reason = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ["-last_seen_at"]
        indexes = [models.Index(fields=["user"], condition=Q(revoked_at__isnull=True), name="ossession_user_live_idx")]

    @property
    def is_live(self) -> bool:
        return self.revoked_at is None and self.expires_at > timezone.now()


class Permission(BaseModel):
    """Mirror of registry.PERMISSIONS (synced after migrate). Never edited by hand."""

    code = models.CharField(max_length=100, unique=True)
    module = models.CharField(max_length=40, db_index=True)
    resource = models.CharField(max_length=40)
    action = models.CharField(max_length=20)
    label = models.CharField(max_length=150)
    sensitive = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code


ScopeChoices = models.TextChoices("ScopeChoices", [(s.upper(), (s, SCOPE_LABELS[s])) for s in SCOPES])
ApprovalTypeChoices = models.TextChoices("ApprovalTypeChoices", [(k.upper(), (k, v)) for k, v in APPROVAL_TYPES.items()])


class Role(BaseModel):
    class Audience(models.TextChoices):
        EMPLOYEE = "employee", "Employees"
        PARTNER = "partner", "Partners"
        EXTERNAL = "external", "External accounts"
        SERVICE = "service", "Service accounts"
        ANY = "any", "Any account"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="roles")
    key = models.SlugField(max_length=60)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=300, blank=True)
    parent = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="children",
                               help_text="Inherits every permission of the parent role.")
    audience = models.CharField(max_length=10, choices=Audience.choices, default=Audience.EMPLOYEE)
    is_system = models.BooleanField(default=False, help_text="Built-in template: read-only, duplicate it to customise.")
    requires_mfa = models.BooleanField(default=False, help_text="Holders must have MFA enabled for this role to take effect.")
    home_widgets = models.JSONField(default=list, blank=True, help_text="Ordered Home widget keys this role brings.")
    home_config = models.JSONField(default=dict, blank=True, help_text='Home defaults, e.g. {"pulse": ["gmv", "orders"]}.')
    priority = models.PositiveSmallIntegerField(default=100, help_text="Lower comes first when composing Home.")
    emergency_eligible = models.BooleanField(default=False, help_text="May be activated as time-boxed break-glass access.")
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["priority", "name"]
        constraints = [models.UniqueConstraint(fields=["organization", "key"], name="role_key_unique_per_org")]

    def __str__(self) -> str:
        return self.name

    def lineage(self) -> list["Role"]:
        """Self then ancestors, cycle-safe."""
        out, seen, role = [], set(), self
        while role is not None and role.pk not in seen:
            out.append(role)
            seen.add(role.pk)
            role = role.parent
        return out


class RolePermission(BaseModel):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="grants")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="+")
    scope = models.CharField(max_length=16, choices=ScopeChoices.choices, default="own")

    class Meta:
        ordering = ["permission__code"]
        constraints = [models.UniqueConstraint(fields=["role", "permission"], name="role_permission_unique")]


class RoleApprovalLimit(BaseModel):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="approval_limits")
    approval_type = models.CharField(max_length=16, choices=ApprovalTypeChoices.choices)
    max_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, help_text="Blank = no upper limit.")
    currency = models.CharField(max_length=3, default="INR")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["role", "approval_type"], name="role_approval_limit_unique")]


class RoleAssignmentQuerySet(models.QuerySet):
    def live(self):
        now = timezone.now()
        return self.filter(is_active=True, role__is_active=True).filter(
            Q(valid_from__isnull=True) | Q(valid_from__lte=now), Q(valid_until__isnull=True) | Q(valid_until__gt=now)
        )


class RoleAssignment(BaseModel):
    """A role given to one person, anchored where it applies. Scopes in the role resolve from this anchor."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="role_assignments")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="assignments")
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.CASCADE, null=True, blank=True, related_name="+",
                                 help_text="Blank = the person's own work location.")
    department = models.ForeignKey(Department, on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    note = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    objects = RoleAssignmentQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "is_active"], name="roleassign_user_active_idx")]


class ServiceAccount(BaseModel):
    """Machine identity for integrations and automation. Authenticates with `Authorization: ClickKey <prefix>.<secret>`."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="service_accounts")
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="service_account")
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=300, blank=True)
    key_prefix = models.CharField(max_length=16, unique=True)
    key_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["name"]

    @staticmethod
    def hash_secret(secret: str) -> str:
        return hashlib.sha256(secret.encode()).hexdigest()

    @classmethod
    def issue(cls, *, organization, name, created_by=None, description="", expires_at=None) -> tuple["ServiceAccount", str]:
        """Create the account and return (account, full key). The key is shown once and never stored."""
        from apps.users.models import User

        user = User(email=None, full_name=f"Service · {name}", is_active=True)
        user.set_unusable_password()
        user.save()
        prefix, secret = secrets.token_hex(6), secrets.token_urlsafe(32)
        account = cls.objects.create(organization=organization, user=user, name=name, description=description,
                                     key_prefix=prefix, key_hash=cls.hash_secret(secret), expires_at=expires_at, created_by=created_by)
        return account, f"{prefix}.{secret}"

    @property
    def is_usable(self) -> bool:
        return self.revoked_at is None and (self.expires_at is None or self.expires_at > timezone.now())


# =====================================================================================================================
# Governance (Module 3): packages, requests, reviews, segregation of duties, emergency access, role versions.
# All of them resolve through the same Role / RoleAssignment model: nothing here is a second permission system.
# =====================================================================================================================
class RoleVersion(BaseModel):
    """Immutable snapshot after every change to a role's grants, limits or inheritance."""

    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    snapshot = models.JSONField(default=dict)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    reason = models.CharField(max_length=300, blank=True)
    affected_users = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-version"]
        constraints = [models.UniqueConstraint(fields=["role", "version"], name="role_version_unique")]


class AccessPackage(BaseModel):
    """A reusable bundle of roles (e.g. "Finance Executive"), assigned in one step and reviewed as one unit."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="access_packages")
    key = models.SlugField(max_length=60)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=300, blank=True)
    roles = models.ManyToManyField(Role, related_name="packages")
    requestable = models.BooleanField(default=True, help_text="Employees may request it from the Access Request Center.")
    max_days = models.PositiveIntegerField(null=True, blank=True, help_text="If set, grants from this package expire after N days.")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["organization", "key"], name="access_package_key_unique")]


class AccessRequest(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for approval"
        PROVISIONED = "provisioned", "Granted"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Withdrawn"
        BLOCKED = "blocked", "Approved but not granted"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    code = models.CharField(max_length=20, unique=True)
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="access_requests")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    package = models.ForeignKey(AccessPackage, on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    valid_until = models.DateTimeField(null=True, blank=True)
    reason = models.TextField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    approval = models.ForeignKey("workflows.ApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    outcome_note = models.CharField(max_length=300, blank=True)
    assignment_ids = models.JSONField(default=list, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class AccessReview(BaseModel):
    class Kind(models.TextChoices):
        PERIODIC = "periodic", "Periodic certification"
        PRIVILEGED = "privileged", "Privileged access review"
        EVENT = "event", "Event-triggered (join / move / leave)"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.PERIODIC)
    due_on = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.OPEN)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class AccessReviewItem(BaseModel):
    class Decision(models.TextChoices):
        PENDING = "pending", "To review"
        KEEP = "keep", "Keep"
        REMOVE = "remove", "Remove"
        SUSPEND = "suspend", "Suspend account"
        ESCALATE = "escalate", "Escalate"

    review = models.ForeignKey(AccessReview, on_delete=models.CASCADE, related_name="items")
    assignment = models.ForeignKey(RoleAssignment, on_delete=models.CASCADE, related_name="review_items")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="access_reviews_to_do")
    reason = models.CharField(max_length=200, blank=True, help_text="Why it is being reviewed (e.g. transfer, sensitive role).")
    decision = models.CharField(max_length=10, choices=Decision.choices, default=Decision.PENDING)
    comment = models.CharField(max_length=500, blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["decision", "created_at"]


class SoDRule(BaseModel):
    class Severity(models.TextChoices):
        WARNING = "warning", "Warning (allowed, flagged)"
        EXCEPTION = "exception", "Needs an approved exception"
        BLOCK = "block", "Blocked"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="sod_rules")
    key = models.SlugField(max_length=60)
    name = models.CharField(max_length=160)
    description = models.CharField(max_length=300, blank=True)
    first = models.JSONField(default=list, help_text="Permission codes (fnmatch patterns) — side A.")
    second = models.JSONField(default=list, help_text="Permission codes (fnmatch patterns) — side B.")
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.WARNING)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["organization", "key"], name="sod_rule_key_unique")]


class SoDException(BaseModel):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    rule = models.ForeignKey(SoDRule, on_delete=models.CASCADE, related_name="exceptions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sod_exceptions")
    reason = models.CharField(max_length=500)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    valid_until = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_live(self) -> bool:
        return self.revoked_at is None and (self.valid_until is None or self.valid_until > timezone.now())


class EmergencyAccess(BaseModel):
    """Break-glass: a time-boxed role activated by the person themselves, loudly announced, reviewed afterwards."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ENDED = "ended", "Ended"
        REVIEWED = "reviewed", "Reviewed"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="emergency_access")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="+")
    assignment = models.OneToOneField(RoleAssignment, on_delete=models.SET_NULL, null=True, related_name="emergency")
    reason = models.TextField()
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    review_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
