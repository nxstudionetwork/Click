"""
Business OS organization layer: who the company is and where work happens.

    Organization (tenant, e.g. Click)
      └── OrgUnit tree (business unit → region → state → city → branch / office / warehouse / …)
    Department (optionally tied to a unit; no unit = shared corporate function)
      └── Team

Every level is optional: a record can sit at any node. Permission scopes (apps.access) resolve against this tree,
so "Finance → View → Hyderabad Branch" and "Finance → Full → Organization" use the same data.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction

from apps.core.models import BaseModel


class Organization(BaseModel):
    """A tenant. Click runs as one organization today; the model keeps multi-organization open."""

    name = models.CharField(max_length=150)
    legal_name = models.CharField(max_length=200, blank=True)
    code = models.SlugField(max_length=40, unique=True)
    base_currency = models.CharField(max_length=3, default="INR")
    timezone = models.CharField(max_length=64, default="Asia/Kolkata")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class OrgUnit(BaseModel):
    """One node of the organization's structure. `path` ("/<id>/<id>/") makes "this unit and below" one index scan."""

    class Type(models.TextChoices):
        BUSINESS_UNIT = "business_unit", "Business unit"
        REGION = "region", "Region"
        STATE = "state", "State"
        CITY = "city", "City"
        BRANCH = "branch", "Branch"
        OFFICE = "office", "Office"
        WAREHOUSE = "warehouse", "Warehouse"
        SERVICE_CENTER = "service_center", "Service center"
        FACILITY = "facility", "Facility"

    # Physical sites. The "branch" permission scope means the nearest site at or above the anchor.
    SITE_TYPES = frozenset({Type.BRANCH, Type.OFFICE, Type.WAREHOUSE, Type.SERVICE_CENTER, Type.FACILITY})

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="units")
    parent = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="children")
    unit_type = models.CharField(max_length=20, choices=Type.choices)
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=40)
    path = models.CharField(max_length=1200, db_index=True, editable=False, default="")
    depth = models.PositiveSmallIntegerField(default=0, editable=False)
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    city = models.CharField(max_length=80, blank=True)
    timezone = models.CharField(max_length=64, blank=True, help_text="Blank = the organization's time zone.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["path"]
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="orgunit_code_unique_per_org")]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_unit_type_display()})"

    def clean(self):
        if self.parent_id:
            if self.parent.organization_id != self.organization_id:
                raise ValidationError({"parent": "The parent must belong to the same organization."})
            if self.pk and f"/{self.pk}/" in self.parent.path:
                raise ValidationError({"parent": "A unit can't be placed under itself."})

    def _compute_path(self) -> tuple[str, int]:
        if self.parent_id:
            parent = OrgUnit.objects.only("path", "depth").get(pk=self.parent_id)
            return f"{parent.path}{self.pk}/", parent.depth + 1
        return f"/{self.pk}/", 0

    def save(self, *args, **kwargs):
        self.clean()
        old_path = None if self._state.adding else OrgUnit.objects.filter(pk=self.pk).values_list("path", flat=True).first()
        self.path, self.depth = self._compute_path()
        with transaction.atomic():
            super().save(*args, **kwargs)
            if old_path and old_path != self.path:  # moved: re-root every descendant
                for child in OrgUnit.objects.filter(path__startswith=old_path).exclude(pk=self.pk):
                    child.path = self.path + child.path[len(old_path):]
                    child.depth = child.path.count("/") - 2
                    super(OrgUnit, child).save(update_fields=["path", "depth"])

    @property
    def ancestor_ids(self) -> list[str]:
        """Root first, self last."""
        return [p for p in self.path.split("/") if p]

    def ancestors(self):
        ids = self.ancestor_ids
        units = {str(u.pk): u for u in OrgUnit.objects.filter(pk__in=ids)}
        return [units[i] for i in ids if i in units]


class Department(BaseModel):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="departments")
    parent = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="children")
    org_unit = models.ForeignKey(
        OrgUnit, on_delete=models.PROTECT, null=True, blank=True, related_name="departments",
        help_text="Blank = a shared corporate function, not tied to one location.",
    )
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=40)
    head = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="department_code_unique_per_org")]

    def __str__(self) -> str:
        return self.name

    def descendant_ids(self) -> set:
        """This department and every sub-department (departments are few; walked in memory)."""
        rows = list(Department.objects.filter(organization_id=self.organization_id).values_list("id", "parent_id"))
        children: dict = {}
        for pk, parent in rows:
            children.setdefault(parent, []).append(pk)
        out, stack = set(), [self.pk]
        while stack:
            pk = stack.pop()
            if pk in out:
                continue
            out.add(pk)
            stack.extend(children.get(pk, []))
        return out


class Team(BaseModel):
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="teams")
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, null=True, blank=True, related_name="teams")
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=40)
    lead = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["department", "code"], name="team_code_unique_per_department")]

    def __str__(self) -> str:
        return self.name
