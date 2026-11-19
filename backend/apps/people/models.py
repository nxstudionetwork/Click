"""
People & HR is the authoritative source of *who an employee is* (employment record). It never decides what they
can access: that is apps.access (roles, permissions, scopes). The full HR module (attendance, leave, payroll, …)
extends these records later instead of creating new ones.
"""

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from apps.organization.models import Department, Organization, OrgUnit, Team


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


class Employee(BaseModel):
    class Status(models.TextChoices):
        PRE_JOINING = "pre_joining", "Pre-joining"
        ACTIVE = "active", "Active"
        ON_LEAVE = "on_leave", "On leave"
        NOTICE = "notice", "Serving notice"
        EXITED = "exited", "Exited"

    class EmploymentType(models.TextChoices):
        FULL_TIME = "full_time", "Full-time"
        PART_TIME = "part_time", "Part-time"
        CONTRACT = "contract", "Contract"
        INTERN = "intern", "Intern"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="employees")
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="employee",
        help_text="The Click identity this employee signs in with. An employee record can exist before an account.",
    )
    employee_id = models.CharField(max_length=30, help_text="Company employee number, e.g. CLK-E-0001.")
    full_name = models.CharField(max_length=150)
    work_email = models.EmailField(blank=True)
    designation = models.ForeignKey(Designation, on_delete=models.SET_NULL, null=True, blank=True, related_name="employees")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="employees")
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, related_name="employees")
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name="employees",
                                 help_text="Work location (branch, office, warehouse …).")
    manager = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="reports")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    employment_type = models.CharField(max_length=16, choices=EmploymentType.choices, default=EmploymentType.FULL_TIME)
    joined_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["full_name"]
        constraints = [models.UniqueConstraint(fields=["organization", "employee_id"], name="employee_id_unique_per_org")]
        indexes = [models.Index(fields=["organization", "status"], name="employee_org_status_idx")]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.employee_id})"
