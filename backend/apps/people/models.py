"""
People & HR — the authoritative record of who works for Click, across the whole lifecycle:

    workforce plan → position → opening → candidate → application → interviews → offer → onboarding → employee
    → attendance / leave → goals & reviews → learning → promotion / transfer → compensation → engagement → offboarding

What this app never does: decide access (apps.access), store files (apps.documents), run approvals (apps.workflows),
send notifications (apps.workspace.notify) or keep its own audit (apps.audit). It plugs into all of them.

Sensitive data lives in separate tables (EmployeePrivate, CompensationRecord, HRCase, exit interview fields) so it is
only ever loaded by code paths that checked the sensitive permission first.

IDs use the Business OS namespace (EMP-, POS-, JOB-, CAN-, OFF-, HRQ-, HRC-) — distinct from the Click apps'
customer (CL-CU-), partner (CLK-PT-) and order (CLK-) identifiers.
"""

from django.conf import settings
from django.db import models, transaction
from django.db.models import F, Q

from apps.core.models import BaseModel
from apps.organization.models import Department, Organization, OrgUnit, Team


# --- IDs -----------------------------------------------------------------------------------------------------
class IdSequence(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    name = models.CharField(max_length=20)
    value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "name"], name="people_idseq_unique")]


def next_id(organization, prefix: str, width: int = 6, *, model=None, field: str = "code") -> str:
    """Next number in the organization's sequence for `prefix`, skipping any value already taken (records created
    with an explicit ID, imports, older data)."""
    with transaction.atomic():
        seq, _ = IdSequence.objects.select_for_update().get_or_create(organization=organization, name=prefix)
        while True:
            seq.value = F("value") + 1
            seq.save(update_fields=["value"])
            seq.refresh_from_db()
            candidate = f"{prefix}-{seq.value:0{width}d}"
            if model is None or not model.objects.filter(organization=organization, **{field: candidate}).exists():
                return candidate


def employee_id_prefix() -> str:
    return getattr(settings, "CLICK_OS_EMPLOYEE_ID_PREFIX", "EMP")


# --- Organization structure (HR side) ------------------------------------------------------------------------
class JobLevel(BaseModel):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="job_levels")
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=80)
    rank = models.PositiveSmallIntegerField(default=1, help_text="Higher is more senior.")

    class Meta:
        ordering = ["-rank"]
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="joblevel_code_unique")]

    def __str__(self) -> str:
        return self.name


class Designation(BaseModel):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="designations")
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=40)
    grade = models.PositiveSmallIntegerField(default=1, help_text="Seniority level; higher is more senior.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-grade", "name"]
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="designation_code_unique_per_org")]

    def __str__(self) -> str:
        return self.name


class WorkSchedule(BaseModel):
    class Kind(models.TextChoices):
        STANDARD = "standard", "Standard"
        SHIFT = "shift", "Shift"
        FLEXIBLE = "flexible", "Flexible"
        REMOTE = "remote", "Remote"
        HYBRID = "hybrid", "Hybrid"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="work_schedules")
    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.STANDARD)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    grace_minutes = models.PositiveSmallIntegerField(default=15)
    working_days = models.JSONField(default=list, help_text="ISO weekdays 1–7 (1 = Monday).")
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class HolidayCalendar(BaseModel):
    """Corporate (no unit), or for a location / department. Employees get every calendar that applies to them."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="holiday_calendars")
    name = models.CharField(max_length=80)
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    department = models.ForeignKey(Department, on_delete=models.CASCADE, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["name"]


class Holiday(BaseModel):
    calendar = models.ForeignKey(HolidayCalendar, on_delete=models.CASCADE, related_name="holidays")
    date = models.DateField()
    name = models.CharField(max_length=80)
    optional = models.BooleanField(default=False)

    class Meta:
        ordering = ["date"]
        constraints = [models.UniqueConstraint(fields=["calendar", "date", "name"], name="holiday_unique")]


# --- Employee ------------------------------------------------------------------------------------------------
class Employee(BaseModel):
    class Status(models.TextChoices):
        PRE_ONBOARDING = "pre_onboarding", "Pre-onboarding"
        ACTIVE = "active", "Active"
        PROBATION = "probation", "Probation"
        CONFIRMED = "confirmed", "Confirmed"
        ON_LEAVE = "on_leave", "On leave"
        SUSPENDED = "suspended", "Suspended"
        NOTICE = "notice", "Notice period"
        RESIGNED = "resigned", "Resigned"
        TERMINATED = "terminated", "Terminated"
        RETIRED = "retired", "Retired"
        FORMER = "former", "Former employee"

    # Working = counted in headcount and can sign in; the rest are kept as history, never deleted.
    WORKING = ("active", "probation", "confirmed", "on_leave", "notice", "suspended")
    EXITED = ("resigned", "terminated", "retired", "former")

    class WorkerType(models.TextChoices):
        EMPLOYEE = "employee", "Employee"
        CONTRACTOR = "contractor", "Contractor"
        TEMPORARY = "temporary", "Temporary worker"
        INTERN = "intern", "Intern"
        CONSULTANT = "consultant", "Consultant"
        FIELD_WORKER = "field_worker", "Field worker"
        OTHER = "other", "Other approved workforce"

    class EmploymentType(models.TextChoices):
        FULL_TIME = "full_time", "Full-time"
        PART_TIME = "part_time", "Part-time"
        CONTRACT = "contract", "Fixed-term contract"
        INTERN = "intern", "Internship"

    class WorkMode(models.TextChoices):
        OFFICE = "office", "Office"
        REMOTE = "remote", "Remote"
        HYBRID = "hybrid", "Hybrid"
        FIELD = "field", "Field"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="employees")
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="employee",
                                help_text="The Click identity this person signs in with. A record can exist before an account.")
    employee_id = models.CharField(max_length=30, help_text="Business OS employee number, e.g. EMP-000001.")
    full_name = models.CharField(max_length=150)
    preferred_name = models.CharField(max_length=80, blank=True)
    work_email = models.EmailField(blank=True)
    work_phone = models.CharField(max_length=20, blank=True)
    designation = models.ForeignKey(Designation, on_delete=models.SET_NULL, null=True, blank=True, related_name="employees")
    job_level = models.ForeignKey(JobLevel, on_delete=models.SET_NULL, null=True, blank=True, related_name="employees")
    position = models.ForeignKey("Position", on_delete=models.SET_NULL, null=True, blank=True, related_name="holders")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="employees")
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, related_name="employees")
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name="employees",
                                 help_text="Work location (branch, office, warehouse …).")
    manager = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="reports")
    secondary_managers = models.ManyToManyField("self", blank=True, symmetrical=False, related_name="matrix_reports",
                                                help_text="Matrix / dotted-line managers.")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    worker_type = models.CharField(max_length=14, choices=WorkerType.choices, default=WorkerType.EMPLOYEE)
    employment_type = models.CharField(max_length=16, choices=EmploymentType.choices, default=EmploymentType.FULL_TIME)
    work_mode = models.CharField(max_length=8, choices=WorkMode.choices, default=WorkMode.OFFICE)
    schedule = models.ForeignKey(WorkSchedule, on_delete=models.SET_NULL, null=True, blank=True, related_name="employees")
    joined_on = models.DateField(null=True, blank=True)
    probation_end_on = models.DateField(null=True, blank=True)
    confirmed_on = models.DateField(null=True, blank=True)
    contract_end_on = models.DateField(null=True, blank=True)
    exit_date = models.DateField(null=True, blank=True)
    exit_reason = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ["full_name"]
        constraints = [models.UniqueConstraint(fields=["organization", "employee_id"], name="employee_id_unique_per_org")]
        indexes = [models.Index(fields=["organization", "status"], name="employee_org_status_idx")]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.employee_id})"

    @property
    def display_name(self) -> str:
        return self.preferred_name or self.full_name

    @property
    def is_working(self) -> bool:
        return self.status in self.WORKING

    def save(self, *args, **kwargs):
        if not self.employee_id:
            self.employee_id = next_id(self.organization, employee_id_prefix(), model=Employee, field="employee_id")
        super().save(*args, **kwargs)


class EmployeePrivate(BaseModel):
    """Personal data. Only loaded after people.personal.view (scope-checked) or by the person themself."""

    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, related_name="private")
    date_of_birth = models.DateField(null=True, blank=True)
    personal_email = models.EmailField(blank=True)
    personal_phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True, max_length=500)
    emergency_contact_name = models.CharField(max_length=120, blank=True)
    emergency_contact_relation = models.CharField(max_length=40, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)
    share_birthday = models.BooleanField(default=False, help_text="The employee chose to show their birthday (day and month) to colleagues.")


class EmploymentEvent(BaseModel):
    """Lifecycle history: never edited, only appended."""

    class Kind(models.TextChoices):
        HIRED = "hired", "Hired"
        CONFIRMED = "confirmed", "Confirmed"
        PROMOTED = "promoted", "Promoted"
        TRANSFERRED = "transferred", "Transferred"
        STATUS = "status_changed", "Status changed"
        COMPENSATION = "compensation_changed", "Compensation changed"
        ROLE = "role_changed", "Role changed"
        EXITED = "exited", "Exited"
        REHIRED = "rehired", "Rehired"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=24, choices=Kind.choices)
    effective_date = models.DateField()
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    reason = models.CharField(max_length=300, blank=True)
    sensitive = models.BooleanField(default=False, help_text="Compensation details — payroll permission only.")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    approval = models.ForeignKey("workflows.ApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-effective_date", "-created_at"]


# --- Positions & workforce ------------------------------------------------------------------------------------
class Position(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending_approval", "Waiting for approval"
        APPROVED = "approved", "Approved"
        OPEN = "open", "Open (hiring)"
        FILLED = "filled", "Filled"
        FROZEN = "frozen", "Frozen"
        CLOSED = "closed", "Closed"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="positions")
    code = models.CharField(max_length=20, editable=False)
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True, max_length=4000)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="positions")
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    job_level = models.ForeignKey(JobLevel, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    designation = models.ForeignKey(Designation, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    worker_type = models.CharField(max_length=14, choices=Employee.WorkerType.choices, default=Employee.WorkerType.EMPLOYEE)
    employment_type = models.CharField(max_length=16, choices=Employee.EmploymentType.choices, default=Employee.EmploymentType.FULL_TIME)
    reporting_manager = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    headcount = models.PositiveSmallIntegerField(default=1, help_text="Approved headcount for this position.")
    salary_min = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    salary_max = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="INR")
    status = models.CharField(max_length=18, choices=Status.choices, default=Status.DRAFT)
    approval = models.ForeignKey("workflows.ApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="position_code_unique")]

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = next_id(self.organization, "POS", model=Position)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.code} {self.title}"


class HeadcountPlan(BaseModel):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="headcount_plans")
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="headcount_plans")
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    period = models.CharField(max_length=20, help_text="e.g. FY2027 or 2027-H1")
    approved = models.PositiveSmallIntegerField(default=0)
    planned = models.PositiveSmallIntegerField(default=0)
    budget = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["period", "department__name"]
        constraints = [models.UniqueConstraint(fields=["department", "org_unit", "period"], name="headcount_plan_unique")]


# --- Recruitment ----------------------------------------------------------------------------------------------
class JobOpening(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        OPEN = "open", "Open"
        ON_HOLD = "on_hold", "On hold"
        CLOSED = "closed", "Closed"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="job_openings")
    code = models.CharField(max_length=20, editable=False)
    position = models.ForeignKey(Position, on_delete=models.PROTECT, related_name="openings")
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True, max_length=8000)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    openings = models.PositiveSmallIntegerField(default=1)
    recruiter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    hiring_manager = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    internal = models.BooleanField(default=True, help_text="Visible to employees as an internal opportunity.")
    external = models.BooleanField(default=True)
    opened_on = models.DateField(null=True, blank=True)
    closed_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = next_id(self.organization, "JOB", model=JobOpening)
        super().save(*args, **kwargs)


class Candidate(BaseModel):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="candidates")
    code = models.CharField(max_length=20, editable=False)
    full_name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    current_company = models.CharField(max_length=120, blank=True)
    current_title = models.CharField(max_length=120, blank=True)
    experience_years = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    skills = models.JSONField(default=list, blank=True)
    education = models.CharField(max_length=300, blank=True)
    location = models.CharField(max_length=80, blank=True)
    source = models.CharField(max_length=40, blank=True, help_text="Referral, job board, careers page, agency …")
    expected_compensation = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    notice_days = models.PositiveSmallIntegerField(null=True, blank=True)
    talent_pool = models.BooleanField(default=False)
    internal_employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    consent_on = models.DateField(null=True, blank=True, help_text="Candidate consented to processing their data.")
    notes = models.TextField(blank=True, max_length=4000)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = next_id(self.organization, "CAN", model=Candidate)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.full_name


class Application(BaseModel):
    class Stage(models.TextChoices):
        APPLIED = "applied", "Applied"
        SCREENING = "screening", "Screening"
        SHORTLISTED = "shortlisted", "Shortlisted"
        INTERVIEW = "interview", "Interview"
        ASSESSMENT = "assessment", "Assessment"
        SELECTED = "selected", "Selected"
        OFFER = "offer", "Offer"
        ACCEPTED = "accepted", "Accepted"
        ONBOARDING = "onboarding", "Onboarding"
        REJECTED = "rejected", "Rejected"
        WITHDRAWN = "withdrawn", "Withdrawn"

    PIPELINE = ["applied", "screening", "shortlisted", "interview", "assessment", "selected", "offer", "accepted", "onboarding"]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="applications")
    opening = models.ForeignKey(JobOpening, on_delete=models.CASCADE, related_name="applications")
    stage = models.CharField(max_length=12, choices=Stage.choices, default=Stage.APPLIED)
    stage_changed_at = models.DateTimeField(auto_now_add=True)
    rejection_reason = models.CharField(max_length=200, blank=True)
    hired_employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["candidate", "opening"], name="application_unique")]


class ApplicationEvent(BaseModel):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="events")
    from_stage = models.CharField(max_length=12, blank=True)
    to_stage = models.CharField(max_length=12)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["created_at"]


class Interview(BaseModel):
    class Kind(models.TextChoices):
        PHONE = "phone", "Phone screen"
        VIDEO = "video", "Video"
        ONSITE = "onsite", "On-site"
        TECHNICAL = "technical", "Technical"
        HR = "hr", "HR"
        PANEL = "panel", "Panel"

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="interviews")
    round_name = models.CharField(max_length=80)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.VIDEO)
    scheduled_at = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=45)
    location = models.CharField(max_length=200, blank=True, help_text="Room or meeting link.")
    panel = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="interview_panels")
    criteria = models.JSONField(default=list, blank=True, help_text="Evaluation criteria names.")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED)

    class Meta:
        ordering = ["scheduled_at"]


class InterviewFeedback(BaseModel):
    class Recommendation(models.TextChoices):
        STRONG_YES = "strong_yes", "Strong hire"
        YES = "yes", "Hire"
        NO = "no", "No hire"
        STRONG_NO = "strong_no", "Strong no hire"

    interview = models.ForeignKey(Interview, on_delete=models.CASCADE, related_name="feedback")
    interviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    scores = models.JSONField(default=dict, blank=True, help_text="criterion → 1-5")
    recommendation = models.CharField(max_length=10, choices=Recommendation.choices)
    notes = models.TextField(blank=True, max_length=4000)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["interview", "interviewer"], name="interview_feedback_unique")]


class Offer(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending_approval", "Waiting for approval"
        APPROVED = "approved", "Approved"
        RELEASED = "released", "Released to candidate"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        EXPIRED = "expired", "Expired"
        WITHDRAWN = "withdrawn", "Withdrawn"
        REJECTED = "rejected", "Not approved"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    code = models.CharField(max_length=20, editable=False)
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="offers")
    designation = models.ForeignKey(Designation, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    job_level = models.ForeignKey(JobLevel, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    joining_date = models.DateField()
    base_annual = models.DecimalField(max_digits=12, decimal_places=2)
    variable_annual = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    joining_bonus = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="INR")
    benefits = models.CharField(max_length=500, blank=True)
    expires_on = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=18, choices=Status.choices, default=Status.DRAFT)
    approval = models.ForeignKey("workflows.ApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    responded_on = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = next_id(self.organization, "OFF", model=Offer)
        super().save(*args, **kwargs)


# --- Onboarding / offboarding checklists -----------------------------------------------------------------------
class ChecklistTemplate(BaseModel):
    class Kind(models.TextChoices):
        ONBOARDING = "onboarding", "Onboarding"
        OFFBOARDING = "offboarding", "Offboarding"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="hr_checklists")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    name = models.CharField(max_length=120)
    worker_types = models.JSONField(default=list, blank=True, help_text="Empty = every worker type.")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    steps = models.JSONField(default=list, help_text='[{"title", "owner": hr|manager|it|finance|facilities|employee, "offset_days", "description"}]')
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["kind", "name"]


class LifecyclePlan(BaseModel):
    """An onboarding or offboarding run for one person. Its steps are ordinary Business OS tasks."""

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="lifecycle_plans")
    kind = models.CharField(max_length=12, choices=ChecklistTemplate.Kind.choices)
    template = models.ForeignKey(ChecklistTemplate, on_delete=models.SET_NULL, null=True, related_name="+")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.IN_PROGRESS)
    started_on = models.DateField()
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


# --- Attendance & leave --------------------------------------------------------------------------------------
class AttendanceRecord(BaseModel):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        HALF_DAY = "half_day", "Half day"
        LEAVE = "leave", "On leave"
        HOLIDAY = "holiday", "Holiday"
        WEEKLY_OFF = "weekly_off", "Weekly off"

    class Mode(models.TextChoices):
        OFFICE = "office", "Office"
        REMOTE = "remote", "Remote"
        FIELD = "field", "Field"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="attendance")
    date = models.DateField()
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)
    break_minutes = models.PositiveSmallIntegerField(default=0)
    mode = models.CharField(max_length=8, choices=Mode.choices, default=Mode.OFFICE)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PRESENT)
    late = models.BooleanField(default=False)
    early_departure = models.BooleanField(default=False)
    source = models.CharField(max_length=20, default="self", help_text="self | manual | correction | integration:<name>")
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-date"]
        constraints = [models.UniqueConstraint(fields=["employee", "date"], name="attendance_one_per_day")]

    @property
    def worked_minutes(self) -> int | None:
        if self.check_in and self.check_out:
            return max(0, int((self.check_out - self.check_in).total_seconds() // 60) - self.break_minutes)
        return None


class AttendanceCorrection(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"
        CHANGES = "changes_requested", "Changes requested"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="attendance_corrections")
    date = models.DateField()
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=300)
    status = models.CharField(max_length=18, choices=Status.choices, default=Status.PENDING)
    approval = models.ForeignKey("workflows.ApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-created_at"]


class LeaveType(BaseModel):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="leave_types")
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=80)
    paid = models.BooleanField(default=True)
    annual_quota = models.DecimalField(max_digits=5, decimal_places=1, default=0, help_text="Days per year (company policy, configurable).")
    carry_forward_max = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    allow_half_day = models.BooleanField(default=True)
    requires_document_after_days = models.PositiveSmallIntegerField(null=True, blank=True)
    hr_approval_over_days = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Also needs HR approval when longer than this.")
    worker_types = models.JSONField(default=list, blank=True, help_text="Empty = every worker type.")
    color = models.CharField(max_length=7, default="#5b3df5")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="leavetype_code_unique")]

    def __str__(self) -> str:
        return self.name


class LeaveBalance(BaseModel):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="leave_balances")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE, related_name="+")
    year = models.PositiveSmallIntegerField()
    entitled = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    carried = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    adjusted = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    used = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    pending = models.DecimalField(max_digits=5, decimal_places=1, default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["employee", "leave_type", "year"], name="leavebalance_unique")]

    @property
    def available(self):
        return self.entitled + self.carried + self.adjusted - self.used - self.pending


class LeaveRequest(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"
        CHANGES = "changes_requested", "Changes requested"

    class Half(models.TextChoices):
        NONE = "", "Full days"
        FIRST = "first", "First half"
        SECOND = "second", "Second half"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="leave_requests")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="requests")
    start_date = models.DateField()
    end_date = models.DateField()
    half_day = models.CharField(max_length=6, choices=Half.choices, blank=True, default="")
    days = models.DecimalField(max_digits=5, decimal_places=1)
    reason = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=18, choices=Status.choices, default=Status.PENDING)
    approval = models.ForeignKey("workflows.ApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-start_date"]
        indexes = [models.Index(fields=["employee", "status"], name="leave_emp_status_idx")]


# --- Performance -----------------------------------------------------------------------------------------------
class ReviewCycle(BaseModel):
    class Frequency(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"
        HALF_YEARLY = "half_yearly", "Half-yearly"
        ANNUAL = "annual", "Annual"
        CUSTOM = "custom", "Custom"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        CLOSED = "closed", "Closed"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="review_cycles")
    name = models.CharField(max_length=80)
    frequency = models.CharField(max_length=12, choices=Frequency.choices, default=Frequency.ANNUAL)
    starts_on = models.DateField()
    ends_on = models.DateField()
    self_review_due = models.DateField(null=True, blank=True)
    manager_review_due = models.DateField(null=True, blank=True)
    peer_feedback = models.BooleanField(default=False)
    peer_visible_to_employee = models.BooleanField(default=False, help_text="Otherwise peer comments are visible to the manager and HR only.")
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.DRAFT)

    class Meta:
        ordering = ["-starts_on"]


class Goal(BaseModel):
    class Level(models.TextChoices):
        COMPANY = "company", "Company"
        BUSINESS_UNIT = "business_unit", "Business unit"
        DEPARTMENT = "department", "Department"
        TEAM = "team", "Team"
        EMPLOYEE = "employee", "Individual"

    class Status(models.TextChoices):
        ON_TRACK = "on_track", "On track"
        AT_RISK = "at_risk", "At risk"
        OFF_TRACK = "off_track", "Off track"
        DONE = "done", "Achieved"
        DROPPED = "dropped", "Dropped"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="goals")
    level = models.CharField(max_length=14, choices=Level.choices)
    parent = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="children",
                               help_text="The goal this one contributes to (cascading).")
    cycle = models.ForeignKey(ReviewCycle, on_delete=models.SET_NULL, null=True, blank=True, related_name="goals")
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, null=True, blank=True, related_name="goals")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, max_length=2000)
    kind = models.CharField(max_length=8, default="goal", help_text="goal | kpi | okr")
    metric = models.CharField(max_length=80, blank=True)
    target = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    current = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    weight = models.PositiveSmallIntegerField(default=0)
    due_on = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ON_TRACK)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        ordering = ["level", "title"]

    @property
    def progress(self) -> int | None:
        if self.target and self.current is not None and self.target != 0:
            return max(0, min(100, int(self.current / self.target * 100)))
        return 100 if self.status == "done" else None


class Review(BaseModel):
    class Kind(models.TextChoices):
        SELF = "self", "Self review"
        MANAGER = "manager", "Manager review"
        PEER = "peer", "Peer feedback"
        FINAL = "final", "Final review"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUBMITTED = "submitted", "Submitted"

    cycle = models.ForeignKey(ReviewCycle, on_delete=models.CASCADE, related_name="reviews")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="hr_reviews_to_write")
    kind = models.CharField(max_length=8, choices=Kind.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    rating = models.PositiveSmallIntegerField(null=True, blank=True, help_text="1–5")
    strengths = models.TextField(blank=True, max_length=3000)
    improvements = models.TextField(blank=True, max_length=3000)
    comments = models.TextField(blank=True, max_length=3000)
    submitted_at = models.DateTimeField(null=True, blank=True)
    due_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["cycle", "kind"]
        constraints = [models.UniqueConstraint(fields=["cycle", "employee", "reviewer", "kind"], name="review_unique")]


class Feedback(BaseModel):
    class Kind(models.TextChoices):
        FEEDBACK = "feedback", "Feedback"
        RECOGNITION = "recognition", "Recognition"
        NOTE = "note", "Performance note"

    class Visibility(models.TextChoices):
        PRIVATE = "private", "Recipient and their manager"
        MANAGER = "manager_only", "Manager and HR only"
        PUBLIC = "public", "Everyone (recognition)"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="feedback_received")
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.FEEDBACK)
    badge = models.CharField(max_length=40, blank=True, help_text="Recognition badge, e.g. team_player, above_and_beyond.")
    body = models.TextField(max_length=2000)
    visibility = models.CharField(max_length=14, choices=Visibility.choices, default=Visibility.PRIVATE)

    class Meta:
        ordering = ["-created_at"]


# --- Learning ------------------------------------------------------------------------------------------------
class Course(BaseModel):
    class Kind(models.TextChoices):
        INTERNAL = "internal", "Internal training"
        EXTERNAL = "external", "External course"
        WORKSHOP = "workshop", "Workshop"
        CERTIFICATION = "certification", "Certification prep"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="courses")
    title = models.CharField(max_length=160)
    provider = models.CharField(max_length=80, blank=True)
    kind = models.CharField(max_length=14, choices=Kind.choices, default=Kind.INTERNAL)
    mandatory = models.BooleanField(default=False)
    duration_hours = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    url = models.URLField(blank=True)
    description = models.TextField(blank=True, max_length=2000)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["title"]


class Enrollment(BaseModel):
    class Status(models.TextChoices):
        ASSIGNED = "assigned", "Assigned"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="enrollments")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ASSIGNED)
    due_on = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    score = models.PositiveSmallIntegerField(null=True, blank=True)
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        ordering = ["status", "due_on"]
        constraints = [models.UniqueConstraint(fields=["course", "employee"], name="enrollment_unique")]


class Skill(BaseModel):
    class Category(models.TextChoices):
        TECHNICAL = "technical", "Technical"
        SOFT = "soft", "Soft skill"
        DOMAIN = "domain", "Domain"
        LANGUAGE = "language", "Language"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="skills")
    name = models.CharField(max_length=80)
    category = models.CharField(max_length=10, choices=Category.choices, default=Category.TECHNICAL)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["organization", "name"], name="skill_name_unique")]


class EmployeeSkill(BaseModel):
    """Proficiency 1–5 with how it was established; self-ratings are kept apart from assessed ones."""

    class Source(models.TextChoices):
        SELF = "self", "Self-assessed"
        MANAGER = "manager", "Manager-assessed"
        ASSESSMENT = "assessment", "Formal assessment"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="skills")
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="holders")
    proficiency = models.PositiveSmallIntegerField(help_text="1 Basic · 2 Working · 3 Proficient · 4 Advanced · 5 Expert")
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.SELF)
    assessed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    assessed_on = models.DateField(null=True, blank=True)
    evidence = models.CharField(max_length=300, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["employee", "skill"], name="employee_skill_unique")]


class Certification(BaseModel):
    class Verification(models.TextChoices):
        PENDING = "pending", "Not verified"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="certifications")
    name = models.CharField(max_length=160)
    provider = models.CharField(max_length=80, blank=True)
    credential_id = models.CharField(max_length=80, blank=True)
    issued_on = models.DateField(null=True, blank=True)
    expires_on = models.DateField(null=True, blank=True)
    document = models.ForeignKey("documents.Document", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    verification = models.CharField(max_length=10, choices=Verification.choices, default=Verification.PENDING)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["expires_on", "name"]


class DevelopmentPlan(BaseModel):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="development_plans")
    career_goal = models.CharField(max_length=200)
    target_role = models.CharField(max_length=120, blank=True)
    skill_gaps = models.JSONField(default=list, blank=True)
    actions = models.JSONField(default=list, blank=True, help_text='[{"title", "due_on", "done"}]')
    status = models.CharField(max_length=10, default="active")

    class Meta:
        ordering = ["-created_at"]


# --- Compensation & benefits (restricted) ----------------------------------------------------------------------
class CompensationRecord(BaseModel):
    """Salary history. Only ever read behind people.payroll.view (sensitive: MFA in production)."""

    class Reason(models.TextChoices):
        HIRE = "hire", "Joining"
        REVISION = "revision", "Salary revision"
        PROMOTION = "promotion", "Promotion"
        CORRECTION = "correction", "Correction"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="compensation")
    effective_date = models.DateField()
    currency = models.CharField(max_length=3, default="INR")
    base_annual = models.DecimalField(max_digits=12, decimal_places=2)
    allowances = models.JSONField(default=dict, blank=True, help_text="name → annual amount")
    variable_target = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    bonus = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reason = models.CharField(max_length=12, choices=Reason.choices, default=Reason.REVISION)
    note = models.CharField(max_length=300, blank=True)
    approval = models.ForeignKey("workflows.ApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        ordering = ["-effective_date"]


class BenefitPlan(BaseModel):
    class Kind(models.TextChoices):
        INSURANCE = "insurance", "Insurance"
        ALLOWANCE = "allowance", "Allowance"
        RETIREMENT = "retirement", "Retirement"
        WELLNESS = "wellness", "Wellness"
        PROGRAM = "program", "Company program"
        OTHER = "other", "Other"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="benefit_plans")
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.OTHER)
    description = models.TextField(blank=True, max_length=2000)
    worker_types = models.JSONField(default=list, blank=True, help_text="Empty = every worker type.")
    org_units = models.JSONField(default=list, blank=True, help_text="Empty = every location.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]


class EmployeeBenefit(BaseModel):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="benefits")
    plan = models.ForeignKey(BenefitPlan, on_delete=models.CASCADE, related_name="enrollments")
    enrolled_on = models.DateField()
    status = models.CharField(max_length=10, default="active")
    details = models.CharField(max_length=300, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["employee", "plan"], name="employee_benefit_unique")]


# --- Engagement ------------------------------------------------------------------------------------------------
class Survey(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="surveys")
    title = models.CharField(max_length=160)
    description = models.CharField(max_length=500, blank=True)
    questions = models.JSONField(default=list, help_text='[{"id", "text", "type": scale|text|choice, "options"}]')
    anonymous = models.BooleanField(default=True)
    min_group = models.PositiveSmallIntegerField(default=3, help_text="Results for groups smaller than this are hidden.")
    opens_on = models.DateField()
    closes_on = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        ordering = ["-opens_on"]


class SurveyParticipation(BaseModel):
    """Who answered (to prevent duplicates). For anonymous surveys this is never linked to the answers."""

    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="participants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["survey", "user"], name="survey_participation_unique")]


class SurveyResponse(BaseModel):
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="responses")
    respondent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                   help_text="Empty for anonymous surveys.")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                   help_text="For group results only (suppressed below the minimum group size).")
    answers = models.JSONField(default=dict)


# --- HR service desk & employee relations ----------------------------------------------------------------------
class HRRequest(BaseModel):
    class Category(models.TextChoices):
        LETTER = "employment_letter", "Employment letter"
        DOCUMENT = "document", "Document request"
        LEAVE = "leave", "Leave issue"
        PAYROLL = "payroll", "Payroll question"
        ATTENDANCE = "attendance", "Attendance issue"
        BENEFITS = "benefits", "Benefits question"
        PROFILE = "profile_correction", "Profile correction"
        TRANSFER = "transfer", "Transfer request"
        OTHER = "other", "Other HR support"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In progress"
        WAITING = "waiting", "Waiting for employee"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    code = models.CharField(max_length=20, editable=False)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="hr_requests")
    category = models.CharField(max_length=20, choices=Category.choices)
    subject = models.CharField(max_length=160)
    description = models.TextField(max_length=4000, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    resolution = models.TextField(max_length=2000, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = next_id(self.organization, "HRQ", model=HRRequest)
        super().save(*args, **kwargs)


class HRRequestComment(BaseModel):
    request = models.ForeignKey(HRRequest, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    body = models.TextField(max_length=2000)
    internal = models.BooleanField(default=False, help_text="HR-only note; the employee doesn't see it.")

    class Meta:
        ordering = ["created_at"]


class HRCase(BaseModel):
    class Kind(models.TextChoices):
        CONCERN = "concern", "Workplace concern"
        COMPLAINT = "complaint", "Complaint"
        GRIEVANCE = "grievance", "Grievance"
        INVESTIGATION = "investigation", "Investigation"
        DISCIPLINARY = "disciplinary", "Disciplinary action"
        CORRECTIVE = "corrective_action", "Corrective action"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        INVESTIGATING = "investigating", "Investigating"
        ACTION = "action", "Action in progress"
        CLOSED = "closed", "Closed"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    code = models.CharField(max_length=20, editable=False)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="hr_cases")
    kind = models.CharField(max_length=18, choices=Kind.choices)
    summary = models.CharField(max_length=200)
    severity = models.CharField(max_length=8, default="medium")
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.OPEN)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    outcome = models.TextField(max_length=2000, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = next_id(self.organization, "HRC", model=HRCase)
        super().save(*args, **kwargs)


class HRCaseNote(BaseModel):
    case = models.ForeignKey(HRCase, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    body = models.TextField(max_length=4000)

    class Meta:
        ordering = ["created_at"]


# --- Promotions, transfers, offboarding --------------------------------------------------------------------------
class LifecycleChange(BaseModel):
    class Kind(models.TextChoices):
        PROMOTION = "promotion", "Promotion"
        TRANSFER = "transfer", "Transfer"
        SALARY = "salary_revision", "Salary revision"

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for approval"
        APPROVED = "approved", "Approved (scheduled)"
        APPLIED = "applied", "Applied"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"
        CHANGES = "changes_requested", "Changes requested"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="lifecycle_changes")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    proposed = models.JSONField(default=dict, help_text="designation_id, job_level_id, department_id, team_id, org_unit_id, manager_id")
    compensation = models.JSONField(default=dict, blank=True, help_text="Restricted: base_annual, variable_target, currency")
    effective_date = models.DateField()
    reason = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=18, choices=Status.choices, default=Status.PENDING)
    approval = models.ForeignKey("workflows.ApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class OffboardingCase(BaseModel):
    class Kind(models.TextChoices):
        RESIGNATION = "resignation", "Resignation"
        TERMINATION = "termination", "Termination"
        RETIREMENT = "retirement", "Retirement"
        CONTRACT_END = "contract_end", "End of contract"

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for approval"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        REJECTED = "rejected", "Not approved"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="offboarding_cases")
    kind = models.CharField(max_length=14, choices=Kind.choices)
    notice_start = models.DateField()
    last_working_day = models.DateField()
    reason = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    approval = models.ForeignKey("workflows.ApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    access_revoked_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    # Exit interview (restricted to people.offboarding.manage)
    exit_reason = models.CharField(max_length=40, blank=True)
    exit_feedback = models.TextField(blank=True, max_length=4000)
    exit_suggestions = models.TextField(blank=True, max_length=2000)
    manager_feedback = models.TextField(blank=True, max_length=2000)
    rehire_eligible = models.BooleanField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["employee"], condition=Q(status__in=["pending", "in_progress"]),
                                               name="one_open_offboarding")]
