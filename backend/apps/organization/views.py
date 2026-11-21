"""Organization structure API (os/org/*): units tree, departments, teams. Reads need organization.*.view; writes need manage."""

from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

from apps.access.api import OSView
from apps.audit.services import record
from apps.core.api.exceptions import DomainError

from .models import Department, OrgUnit, Team


def unit_payload(u: OrgUnit, counts: dict) -> dict:
    return {"id": str(u.pk), "parent_id": str(u.parent_id) if u.parent_id else None, "name": u.name, "code": u.code,
            "type": u.unit_type, "type_label": u.get_unit_type_display(), "depth": u.depth, "city": u.city,
            "is_active": u.is_active, "employees": counts.get(u.pk, 0)}


def dept_payload(d: Department) -> dict:
    return {"id": str(d.pk), "name": d.name, "code": d.code, "parent_id": str(d.parent_id) if d.parent_id else None,
            "org_unit_id": str(d.org_unit_id) if d.org_unit_id else None, "head": d.head.full_name if d.head_id else None,
            "is_active": d.is_active,
            "teams": [{"id": str(t.pk), "name": t.name, "code": t.code, "lead": t.lead.full_name if t.lead_id else None}
                      for t in d.teams.all()]}


class OrgTreeView(OSView):
    permissions = {"GET": "organization.unit.view"}

    def get(self, request):
        from django.db.models import Count

        from apps.people.models import Employee

        ctx = self.authz
        scope = ctx.scope("organization.unit.view")
        units = OrgUnit.objects.filter(organization=ctx.organization)
        if not scope.org_wide:
            from django.db.models import Q

            cond = Q(pk__in=[])
            for p in scope.unit_paths:
                cond |= Q(path__startswith=p)
            units = units.filter(cond)
        counts = dict(Employee.objects.filter(organization=ctx.organization).exclude(status="exited")
                      .values_list("org_unit").annotate(n=Count("id")))
        depts = Department.objects.filter(organization=ctx.organization).select_related("head").prefetch_related("teams__lead")
        return Response({
            "organization": {"id": str(ctx.organization.pk), "name": ctx.organization.name, "code": ctx.organization.code},
            "units": [unit_payload(u, counts) for u in units],
            "departments": [dept_payload(d) for d in depts] if ctx.has("organization.department.view") else [],
            "unit_types": [{"key": k, "label": v} for k, v in OrgUnit.Type.choices],
            "can_manage": ctx.has("organization.unit.manage"),
        })


class UnitsView(OSView):
    permissions = {"POST": "organization.unit.manage"}

    def post(self, request):
        return _save_unit(request, self.authz, None)


class UnitDetailView(OSView):
    permissions = {"PATCH": "organization.unit.manage"}

    def patch(self, request, pk):
        unit = OrgUnit.objects.filter(pk=pk, organization=self.authz.organization).first()
        if unit is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        return _save_unit(request, self.authz, unit)


def _save_unit(request, ctx, unit):
    d = request.data
    creating = unit is None
    before = None if creating else {"name": unit.name, "code": unit.code, "type": unit.unit_type, "parent": str(unit.parent_id), "active": unit.is_active}
    unit = unit or OrgUnit(organization=ctx.organization)
    errors = {}
    for f in ("name", "code", "city"):
        if f in d:
            setattr(unit, f, str(d[f]).strip()[:150 if f == "name" else 80])
    if "unit_type" in d:
        if d["unit_type"] not in OrgUnit.Type.values:
            errors["unitType"] = ["Choose a unit type."]
        unit.unit_type = d["unit_type"]
    if "is_active" in d:
        unit.is_active = bool(d["is_active"])
    if "parent_id" in d:
        parent = OrgUnit.objects.filter(pk=d["parent_id"], organization=ctx.organization).first() if d["parent_id"] else None
        if d["parent_id"] and parent is None:
            errors["parentId"] = ["Unknown parent."]
        unit.parent = parent
    if not unit.name or len(unit.name) < 2:
        errors["name"] = ["Enter a name."]
    if not unit.code:
        errors["code"] = ["Enter a short code."]
    elif OrgUnit.objects.filter(organization=ctx.organization, code__iexact=unit.code).exclude(pk=unit.pk).exists():
        errors["code"] = ["This code is already used."]
    if not unit.unit_type:
        errors["unitType"] = ["Choose a unit type."]
    if errors:
        raise DomainError("Please check the highlighted fields.", code="validation_error", details=errors)
    from django.core.exceptions import ValidationError

    try:
        with transaction.atomic():
            unit.save()
    except ValidationError as e:
        raise DomainError("Please check the highlighted fields.", code="validation_error", details=e.message_dict)
    record(request, "organization.unit.create" if creating else "organization.unit.update", category="config", module="organization",
           resource=unit, old=before, new={"name": unit.name, "code": unit.code, "type": unit.unit_type, "parent": str(unit.parent_id), "active": unit.is_active})
    return Response(unit_payload(unit, {}), status=status.HTTP_201_CREATED if creating else status.HTTP_200_OK)


class DepartmentsView(OSView):
    permissions = {"POST": "organization.department.manage"}

    def post(self, request):
        ctx, d = self.authz, request.data
        name, code = str(d.get("name", "")).strip(), str(d.get("code", "")).strip().upper()
        if len(name) < 2 or not code:
            raise DomainError("Enter a name and code.", code="validation_error", details={"name": ["Required."], "code": ["Required."]})
        if Department.objects.filter(organization=ctx.organization, code__iexact=code).exists():
            raise DomainError("This code is already used.", code="validation_error", details={"code": ["Already used."]})
        parent = Department.objects.filter(pk=d.get("parent_id"), organization=ctx.organization).first() if d.get("parent_id") else None
        unit = OrgUnit.objects.filter(pk=d.get("org_unit_id"), organization=ctx.organization).first() if d.get("org_unit_id") else None
        dept = Department.objects.create(organization=ctx.organization, name=name[:120], code=code[:40], parent=parent, org_unit=unit)
        record(request, "organization.department.create", category="config", module="organization", resource=dept)
        return Response(dept_payload(dept), status=status.HTTP_201_CREATED)


class TeamsView(OSView):
    permissions = {"POST": "organization.department.manage"}

    def post(self, request):
        ctx, d = self.authz, request.data
        dept = Department.objects.filter(pk=d.get("department_id"), organization=ctx.organization).first()
        name, code = str(d.get("name", "")).strip(), str(d.get("code", "")).strip().upper()
        if dept is None or len(name) < 2 or not code:
            raise DomainError("Choose a department and enter a name and code.", code="validation_error")
        if Team.objects.filter(department=dept, code__iexact=code).exists():
            raise DomainError("This code is already used in the department.", code="validation_error", details={"code": ["Already used."]})
        team = Team.objects.create(department=dept, name=name[:120], code=code[:40])
        record(request, "organization.team.create", category="config", module="organization", resource=team)
        return Response({"id": str(team.pk), "name": team.name, "code": team.code}, status=status.HTTP_201_CREATED)
