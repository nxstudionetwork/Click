"""
Global search foundation. Each entity type registers a provider with the permission it needs; the provider filters
its queryset with the caller's scope *in the database*, so restricted records are never returned, counted or hinted
at. Future modules (customers, invoices, products, orders, documents …) add a provider here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from django.db.models import Q

from apps.access.authz import AuthContext


@dataclass(frozen=True)
class Provider:
    type: str
    label: str
    permission: str | None
    search: Callable[[AuthContext, str, int], list[dict]]


def _employees(ctx, q, n):
    from apps.people.models import Employee

    # Directory: names, designation and location only. Full records need people.employee.view.
    scope = ctx.scope("people.directory.view")
    qs = scope.filter(Employee.objects.exclude(status="exited"), unit="org_unit", department="department", team="team", owner="user")
    qs = qs.filter(Q(full_name__icontains=q) | Q(employee_id__iexact=q) | Q(work_email__icontains=q)).select_related("designation", "org_unit")
    return [{"id": str(e.pk), "title": e.full_name, "subtitle": " · ".join(x for x in [e.designation.name if e.designation else "",
            e.org_unit.name if e.org_unit else "", e.employee_id] if x), "path": f"/people/{e.pk}"} for e in qs[:n]]


def _accounts(ctx, q, n):
    from apps.access.models import OSAccount

    qs = OSAccount.objects.filter(organization=ctx.organization).select_related("user")
    scope = ctx.scope("identity.user.view")
    if not scope.org_wide:
        qs = qs.filter(scope.q(unit="user__employee__org_unit", department="user__employee__department", owner="user", organization=None))
    qs = qs.filter(Q(user__full_name__icontains=q) | Q(user__email__icontains=q))
    return [{"id": str(a.pk), "title": a.user.full_name or a.user.email, "subtitle": f"{a.get_kind_display()} · {a.get_status_display()}",
             "path": f"/settings/users/{a.pk}"} for a in qs[:n]]


def _roles(ctx, q, n):
    from apps.access.models import Role

    qs = Role.objects.filter(organization=ctx.organization).filter(Q(name__icontains=q) | Q(key__icontains=q))
    return [{"id": str(r.pk), "title": r.name, "subtitle": r.description[:80], "path": f"/settings/roles/{r.pk}"} for r in qs[:n]]


def _units(ctx, q, n):
    from apps.organization.models import OrgUnit

    scope = ctx.scope("organization.unit.view")
    qs = OrgUnit.objects.filter(organization=ctx.organization).filter(Q(name__icontains=q) | Q(code__iexact=q) | Q(city__icontains=q))
    if not scope.org_wide:
        cond = Q(pk__in=[])
        for p in scope.unit_paths:
            cond |= Q(path__startswith=p)
        qs = qs.filter(cond)
    return [{"id": str(u.pk), "title": u.name, "subtitle": u.get_unit_type_display(), "path": f"/settings/organization?unit={u.pk}"} for u in qs[:n]]


def _tasks(ctx, q, n):
    from apps.workflows.models import Task

    qs = Task.objects.filter(Q(assignee=ctx.user) | Q(created_by=ctx.user)).filter(title__icontains=q)
    return [{"id": str(t.pk), "title": t.title, "subtitle": f"Task · {t.get_status_display()}", "path": f"/tasks?open={t.pk}"} for t in qs[:n]]


def _approvals(ctx, q, n):
    from apps.workflows.selectors import visible_requests

    qs = visible_requests(ctx).filter(Q(title__icontains=q) | Q(reference__iexact=q))
    return [{"id": str(r.pk), "title": r.title, "subtitle": f"{r.reference} · {r.get_status_display()}", "path": f"/approvals/{r.pk}"} for r in qs[:n]]


def _partners(ctx, q, n):
    from apps.partners.models import Partner

    scope = ctx.scope("partners.partner.view")
    qs = Partner.objects.filter(Q(business_name__icontains=q) | Q(partner_code__iexact=q)).select_related("category")
    if not scope.org_wide:  # partner records carry no org unit yet: narrower scopes see only their own partner
        qs = qs.filter(pk__in=scope.partner_ids)
    return [{"id": str(p.pk), "title": p.business_name or str(p), "subtitle": f"{p.partner_code or 'Draft'} · {p.get_status_display()}",
             "path": f"/m/partners?partner={p.pk}"} for p in qs[:n]]


PROVIDERS: dict[str, Provider] = {p.type: p for p in (
    Provider("employee", "Employees", "people.directory.view", _employees),
    Provider("partner", "Partners", "partners.partner.view", _partners),
    Provider("approval", "Approvals", None, _approvals),
    Provider("task", "Tasks", None, _tasks),
    Provider("user", "User accounts", "identity.user.view", _accounts),
    Provider("role", "Roles", "access.role.view", _roles),
    Provider("unit", "Locations & units", "organization.unit.view", _units),
)}


def search(ctx: AuthContext, q: str, *, types: list[str] | None = None, limit: int = 6) -> list[dict]:
    q = (q or "").strip()[:100]
    if len(q) < 2:
        return []
    groups = []
    for key, p in PROVIDERS.items():
        if types and key not in types:
            continue
        if p.permission and not ctx.has(p.permission):
            continue
        results = p.search(ctx, q, limit)
        if results:
            groups.append({"type": key, "label": p.label, "results": results})
    return groups


def searchable_types(ctx: AuthContext) -> list[dict]:
    return [{"type": k, "label": p.label} for k, p in PROVIDERS.items() if not p.permission or ctx.has(p.permission)]
