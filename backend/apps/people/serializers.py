"""People & HR serializers. Restricted fields are dropped server-side for callers without the permission."""

from rest_framework import serializers

from apps.access.crud import OSSerializer
from apps.organization.models import Department, OrgUnit, Team

from . import models as m


def _ref(obj, label="name"):
    return {"id": str(obj.pk), "name": getattr(obj, label)} if obj else None


class EmployeeDirectorySerializer(serializers.ModelSerializer):
    """What every colleague may see (people.directory.view)."""

    designation = serializers.SerializerMethodField()
    department = serializers.SerializerMethodField()
    team = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    business_unit = serializers.SerializerMethodField()
    manager = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = m.Employee
        fields = ["id", "employee_id", "full_name", "preferred_name", "display_name", "work_email", "work_phone", "designation", "department",
                  "team", "location", "business_unit", "manager", "status", "worker_type", "work_mode", "avatar_url"]

    def get_designation(self, e):
        return _ref(e.designation)

    def get_department(self, e):
        return _ref(e.department)

    def get_team(self, e):
        return _ref(e.team)

    def get_location(self, e):
        return _ref(e.org_unit)

    def get_business_unit(self, e):
        if not e.org_unit_id:
            return None
        cache = self.context.setdefault("_bu", {})
        if e.org_unit_id not in cache:
            bu = next((u for u in e.org_unit.ancestors() if u.unit_type == "business_unit"), None) if e.org_unit else None
            cache[e.org_unit_id] = _ref(bu)
        return cache[e.org_unit_id]

    def get_manager(self, e):
        return {"id": str(e.manager_id), "name": e.manager.display_name} if e.manager_id else None

    def get_avatar_url(self, e):
        acct = getattr(e.user, "os_account", None) if e.user_id else None
        return acct.avatar.url if acct and acct.avatar else None


class EmployeeSerializer(EmployeeDirectorySerializer):
    """The employment record (people.employee.view). Writable by people.employee.create/edit."""

    designation_id = serializers.PrimaryKeyRelatedField(source="designation", queryset=m.Designation.objects.all(), required=False, allow_null=True, write_only=True)
    job_level_id = serializers.PrimaryKeyRelatedField(source="job_level", queryset=m.JobLevel.objects.all(), required=False, allow_null=True, write_only=True)
    department_id = serializers.PrimaryKeyRelatedField(source="department", queryset=Department.objects.all(), required=False, allow_null=True, write_only=True)
    team_id = serializers.PrimaryKeyRelatedField(source="team", queryset=Team.objects.all(), required=False, allow_null=True, write_only=True)
    org_unit_id = serializers.PrimaryKeyRelatedField(source="org_unit", queryset=OrgUnit.objects.all(), required=False, allow_null=True, write_only=True)
    manager_id = serializers.PrimaryKeyRelatedField(source="manager", queryset=m.Employee.objects.all(), required=False, allow_null=True, write_only=True)
    schedule_id = serializers.PrimaryKeyRelatedField(source="schedule", queryset=m.WorkSchedule.objects.all(), required=False, allow_null=True, write_only=True)
    position_id = serializers.PrimaryKeyRelatedField(source="position", queryset=m.Position.objects.all(), required=False, allow_null=True, write_only=True)
    job_level = serializers.SerializerMethodField()
    has_account = serializers.SerializerMethodField()
    tenure_days = serializers.SerializerMethodField()

    class Meta(EmployeeDirectorySerializer.Meta):
        fields = EmployeeDirectorySerializer.Meta.fields + [
            "employment_type", "job_level", "joined_on", "probation_end_on", "confirmed_on", "contract_end_on", "exit_date", "exit_reason",
            "has_account", "tenure_days", "designation_id", "job_level_id", "department_id", "team_id", "org_unit_id", "manager_id",
            "schedule_id", "position_id", "created_at"]
        read_only_fields = ["employee_id", "exit_date", "exit_reason", "created_at"]

    def get_job_level(self, e):
        return _ref(e.job_level)

    def get_has_account(self, e):
        return bool(e.user_id and hasattr(e.user, "os_account"))

    def get_tenure_days(self, e):
        from django.utils import timezone

        return (timezone.localdate() - e.joined_on).days if e.joined_on and e.joined_on <= timezone.localdate() else None

    def validate(self, attrs):
        org = self.context["authz"].organization
        for key in ("designation", "job_level", "department", "org_unit", "manager", "schedule", "position"):
            v = attrs.get(key)
            if v is not None and getattr(v, "organization_id", org.pk) != org.pk:
                raise serializers.ValidationError({key: "Not in your organization."})
        team = attrs.get("team")
        if team is not None and team.department.organization_id != org.pk:
            raise serializers.ValidationError({"team": "Not in your organization."})
        if self.instance is not None and attrs.get("manager") is not None:
            mgr, seen = attrs["manager"], set()
            while mgr is not None and mgr.pk not in seen:
                if mgr.pk == self.instance.pk:
                    raise serializers.ValidationError({"manager": "That would create a reporting loop."})
                seen.add(mgr.pk)
                mgr = mgr.manager
        if "status" in attrs and attrs["status"] in m.Employee.EXITED:
            raise serializers.ValidationError({"status": "Use the offboarding workflow to record an exit."})
        return attrs


class PrivateSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.EmployeePrivate
        fields = ["date_of_birth", "personal_email", "personal_phone", "address", "emergency_contact_name", "emergency_contact_relation",
                  "emergency_contact_phone", "share_birthday"]


class JobLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.JobLevel
        fields = ["id", "code", "name", "rank"]


class DesignationSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.Designation
        fields = ["id", "code", "name", "grade", "is_active"]


class ScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.WorkSchedule
        fields = ["id", "name", "kind", "start_time", "end_time", "grace_minutes", "working_days", "org_unit", "department", "is_default"]

    def validate_working_days(self, v):
        if not isinstance(v, list) or any(d not in range(1, 8) for d in v):
            raise serializers.ValidationError("Use weekday numbers 1 (Monday) to 7 (Sunday).")
        return sorted(set(v))


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = m.Holiday
        fields = ["id", "calendar", "date", "name", "optional"]


class HolidayCalendarSerializer(serializers.ModelSerializer):
    holidays = HolidaySerializer(many=True, read_only=True)
    org_unit_name = serializers.CharField(source="org_unit.name", read_only=True, default=None)

    class Meta:
        model = m.HolidayCalendar
        fields = ["id", "name", "org_unit", "org_unit_name", "department", "holidays"]


class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.LeaveType
        fields = ["id", "code", "name", "paid", "annual_quota", "carry_forward_max", "allow_half_day", "requires_document_after_days",
                  "hr_approval_over_days", "worker_types", "color", "is_active"]


class LeaveRequestSerializer(serializers.ModelSerializer):
    employee = serializers.SerializerMethodField()
    leave_type = serializers.SerializerMethodField()
    approval_id = serializers.UUIDField(source="approval.pk", read_only=True, default=None)

    class Meta:
        model = m.LeaveRequest
        fields = ["id", "employee", "leave_type", "start_date", "end_date", "half_day", "days", "reason", "status", "approval_id", "created_at"]

    def get_employee(self, x):
        return {"id": str(x.employee_id), "name": x.employee.display_name}

    def get_leave_type(self, x):
        return {"id": str(x.leave_type_id), "name": x.leave_type.name, "color": x.leave_type.color, "paid": x.leave_type.paid}


class PositionSerializer(OSSerializer):
    restricted_fields = {"salary_min": "people.payroll.view", "salary_max": "people.payroll.view"}
    department_name = serializers.CharField(source="department.name", read_only=True)
    location_name = serializers.CharField(source="org_unit.name", read_only=True, default=None)
    filled = serializers.SerializerMethodField()
    reporting_manager_name = serializers.CharField(source="reporting_manager.display_name", read_only=True, default=None)

    class Meta:
        model = m.Position
        fields = ["id", "code", "title", "description", "department", "department_name", "team", "org_unit", "location_name", "job_level",
                  "designation", "worker_type", "employment_type", "reporting_manager", "reporting_manager_name", "headcount", "filled",
                  "salary_min", "salary_max", "currency", "status", "approval", "created_at"]
        read_only_fields = ["code", "status", "approval", "created_at"]

    def get_filled(self, p):
        return p.holders.filter(status__in=m.Employee.WORKING + ("pre_onboarding",)).count()


class HeadcountPlanSerializer(OSSerializer):
    restricted_fields = {"budget": "people.payroll.view"}
    department_name = serializers.CharField(source="department.name", read_only=True)

    class Meta:
        model = m.HeadcountPlan
        fields = ["id", "department", "department_name", "org_unit", "period", "approved", "planned", "budget", "notes"]


class OpeningSerializer(serializers.ModelSerializer):
    position_code = serializers.CharField(source="position.code", read_only=True)
    department_name = serializers.CharField(source="position.department.name", read_only=True)
    location_name = serializers.CharField(source="position.org_unit.name", read_only=True, default=None)
    counts = serializers.SerializerMethodField()
    hiring_manager_name = serializers.CharField(source="hiring_manager.display_name", read_only=True, default=None)
    recruiter_name = serializers.CharField(source="recruiter.full_name", read_only=True, default=None)

    class Meta:
        model = m.JobOpening
        fields = ["id", "code", "position", "position_code", "title", "description", "status", "openings", "recruiter", "recruiter_name",
                  "hiring_manager", "hiring_manager_name", "internal", "external", "opened_on", "closed_on", "department_name", "location_name",
                  "counts", "created_at"]
        read_only_fields = ["code", "created_at"]

    def get_counts(self, o):
        from django.db.models import Count

        return dict(o.applications.values_list("stage").annotate(n=Count("id")))


class CandidateSerializer(OSSerializer):
    restricted_fields = {"expected_compensation": "people.offer.view"}
    applications = serializers.SerializerMethodField()

    class Meta:
        model = m.Candidate
        fields = ["id", "code", "full_name", "email", "phone", "current_company", "current_title", "experience_years", "skills", "education",
                  "location", "source", "expected_compensation", "notice_days", "talent_pool", "consent_on", "notes", "applications", "created_at"]
        read_only_fields = ["code", "created_at"]

    def get_applications(self, c):
        return [{"id": str(a.pk), "opening": a.opening.title, "opening_id": str(a.opening_id), "stage": a.stage} for a in c.applications.select_related("opening")]


class ApplicationSerializer(serializers.ModelSerializer):
    candidate = serializers.SerializerMethodField()
    interviews = serializers.SerializerMethodField()
    offers = serializers.SerializerMethodField()
    days_in_stage = serializers.SerializerMethodField()

    class Meta:
        model = m.Application
        fields = ["id", "candidate", "opening", "stage", "stage_changed_at", "days_in_stage", "rejection_reason", "interviews", "offers", "created_at"]

    def get_candidate(self, a):
        c = a.candidate
        return {"id": str(c.pk), "code": c.code, "full_name": c.full_name, "current_title": c.current_title, "experience_years": c.experience_years,
                "source": c.source, "skills": c.skills[:6]}

    def get_interviews(self, a):
        return [{"id": str(i.pk), "round": i.round_name, "at": i.scheduled_at, "status": i.status, "feedback": i.feedback.count()} for i in a.interviews.all()]

    def get_offers(self, a):
        return [{"id": str(o.pk), "code": o.code, "status": o.status} for o in a.offers.all()]

    def get_days_in_stage(self, a):
        from django.utils import timezone

        return (timezone.now() - a.stage_changed_at).days if a.stage_changed_at else None


class CourseSerializer(serializers.ModelSerializer):
    enrolled = serializers.IntegerField(source="enrollments.count", read_only=True)

    class Meta:
        model = m.Course
        fields = ["id", "title", "provider", "kind", "mandatory", "duration_hours", "url", "description", "is_active", "enrolled"]


class SkillSerializer(serializers.ModelSerializer):
    holders = serializers.IntegerField(source="holders.count", read_only=True)

    class Meta:
        model = m.Skill
        fields = ["id", "name", "category", "holders"]


class ReviewCycleSerializer(serializers.ModelSerializer):
    progress = serializers.SerializerMethodField()

    class Meta:
        model = m.ReviewCycle
        fields = ["id", "name", "frequency", "starts_on", "ends_on", "self_review_due", "manager_review_due", "peer_feedback",
                  "peer_visible_to_employee", "status", "progress"]
        read_only_fields = ["status"]

    def get_progress(self, c):
        total = c.reviews.count()
        return {"total": total, "submitted": c.reviews.filter(status="submitted").count()}

    def validate(self, attrs):
        s, e = attrs.get("starts_on", getattr(self.instance, "starts_on", None)), attrs.get("ends_on", getattr(self.instance, "ends_on", None))
        if s and e and e < s:
            raise serializers.ValidationError({"endsOn": "The cycle ends before it starts."})
        return attrs


class GoalSerializer(serializers.ModelSerializer):
    progress = serializers.IntegerField(read_only=True)
    employee_name = serializers.CharField(source="employee.display_name", read_only=True, default=None)
    children = serializers.SerializerMethodField()

    class Meta:
        model = m.Goal
        fields = ["id", "level", "parent", "cycle", "org_unit", "department", "team", "employee", "employee_name", "title", "description", "kind",
                  "metric", "target", "current", "weight", "due_on", "status", "progress", "children", "created_at"]

    def get_children(self, g):
        return g.children.count()


class BenefitPlanSerializer(serializers.ModelSerializer):
    enrolled = serializers.IntegerField(source="enrollments.count", read_only=True)

    class Meta:
        model = m.BenefitPlan
        fields = ["id", "name", "kind", "description", "worker_types", "org_units", "is_active", "enrolled"]


class SurveySerializer(serializers.ModelSerializer):
    responses = serializers.IntegerField(source="participants.count", read_only=True)

    class Meta:
        model = m.Survey
        fields = ["id", "title", "description", "questions", "anonymous", "min_group", "opens_on", "closes_on", "status", "responses"]

    def validate_questions(self, v):
        if not isinstance(v, list) or not v:
            raise serializers.ValidationError("Add at least one question.")
        for i, q in enumerate(v):
            if not q.get("text") or q.get("type") not in ("scale", "text", "choice"):
                raise serializers.ValidationError(f"Question {i + 1} needs text and a type (scale, text or choice).")
            q.setdefault("id", f"q{i + 1}")
        return v


class ChecklistTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.ChecklistTemplate
        fields = ["id", "kind", "name", "worker_types", "department", "steps", "is_default"]

    def validate_steps(self, v):
        owners = {"hr", "manager", "it", "finance", "facilities", "employee"}
        if not isinstance(v, list) or not v:
            raise serializers.ValidationError("Add at least one step.")
        for s in v:
            if not s.get("title") or s.get("owner", "hr") not in owners:
                raise serializers.ValidationError("Each step needs a title and an owner (hr, manager, it, finance, facilities, employee).")
        return v


class HRRequestSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.display_name", read_only=True)
    assignee_name = serializers.CharField(source="assignee.full_name", read_only=True, default=None)

    class Meta:
        model = m.HRRequest
        fields = ["id", "code", "employee", "employee_name", "category", "subject", "description", "status", "assignee", "assignee_name",
                  "resolution", "resolved_at", "created_at", "updated_at"]
        read_only_fields = ["code", "resolved_at", "created_at", "updated_at"]


class HRCaseSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.display_name", read_only=True)
    assigned_to_name = serializers.CharField(source="assigned_to.full_name", read_only=True, default=None)

    class Meta:
        model = m.HRCase
        fields = ["id", "code", "employee", "employee_name", "kind", "summary", "severity", "status", "assigned_to", "assigned_to_name",
                  "outcome", "closed_at", "created_at"]
        read_only_fields = ["code", "closed_at", "created_at"]


class OffboardingSerializer(OSSerializer):
    restricted_fields = {"exit_reason": "people.offboarding.manage", "exit_feedback": "people.offboarding.manage",
                         "exit_suggestions": "people.offboarding.manage", "manager_feedback": "people.offboarding.manage",
                         "rehire_eligible": "people.offboarding.manage"}
    employee_name = serializers.CharField(source="employee.display_name", read_only=True)
    checklist = serializers.SerializerMethodField()

    class Meta:
        model = m.OffboardingCase
        fields = ["id", "employee", "employee_name", "kind", "notice_start", "last_working_day", "reason", "status", "approval", "access_revoked_at",
                  "completed_at", "exit_reason", "exit_feedback", "exit_suggestions", "manager_feedback", "rehire_eligible", "checklist", "created_at"]
        read_only_fields = ["status", "approval", "access_revoked_at", "completed_at", "created_at"]

    def get_checklist(self, c):
        from .services import plan_progress

        plan = c.employee.lifecycle_plans.filter(kind="offboarding").first()
        return plan_progress(plan) if plan else None
