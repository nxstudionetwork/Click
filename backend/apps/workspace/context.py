"""
`GET /os/me/context`: everything the shell needs after sign-in, computed from the server's authorization engine.

User → Organization → (Business unit → Region → … → Location) → Department → Team → Roles → Permissions →
Approval authority, plus permission-filtered navigation and quick actions. The client never decides access; it
renders what this returns (and the API re-checks every request anyway).
"""

from django.conf import settings

from apps.access import registry
from apps.access.authz import AuthContext
from apps.access.serializers import avatar_url, dept_brief, team_brief, unit_brief

QUICK_ACTIONS = (
    # key, label, icon, path, permission (None = every staff account)
    ("create_task", "Create task", "plus", "/tasks?new=1", None),
    ("start_approval", "Start approval", "check", "/approvals/new", "workflows.request.create"),
    ("submit_expense", "Submit expense", "receipt", "/approvals/new?policy=finance.expense", "finance.expense.create"),
    ("purchase_request", "Create purchase request", "bag", "/approvals/new?policy=procurement.request", "procurement.request.create"),
    ("request_leave", "Request leave", "calendar", "/people/leave?new=1", "people.leave.create"),
    ("check_in", "Check in / out", "clock", "/people/attendance", "people.attendance.create"),
    ("add_employee", "Add employee", "team", "/people/directory?new=1", "people.employee.create"),
    ("open_position", "Open a position", "briefcase", "/people/positions?new=1", "people.position.create"),
    ("hr_request", "Raise HR request", "help", "/people/requests?new=1", "people.request.create"),
    ("search_employee", "Find employee", "search", "/search?type=employee", "people.directory.view"),
    ("search_partner", "Find partner", "store", "/search?type=partner", "partners.partner.view"),
    ("upload_document", "Upload document", "book", "/people/me?tab=documents", "people.document.create"),
    ("create_announcement", "Post announcement", "send", "/announcements?new=1", "communications.announcement.create"),
    ("create_project", "Create project", "target", "/m/projects", "projects.project.create"),
    ("create_campaign", "Create campaign", "tag", "/m/marketing", "marketing.campaign.create"),
    ("open_reports", "Generate report", "chart", "/m/analytics", "analytics.report.create"),
    ("invite_user", "Invite user", "user", "/settings/users?invite=1", "identity.user.create"),
    ("view_audit", "Audit trail", "history", "/settings/audit", "audit.event.view"),
)

# Core pages partner accounts get; everything else must come from explicit grants.
PARTNER_CORE = {"home", "notifications", "tasks", "approvals", "my_work"}


def navigation(ctx: AuthContext) -> list[dict]:
    groups = []
    for gkey, glabel in registry.GROUPS:
        items = []
        for m in registry.MODULES:
            if m.group != gkey:
                continue
            if m.always_visible:
                visible = ctx.kind != "partner" or m.key in PARTNER_CORE
            else:
                visible = ctx.sees_in_navigation(m)
            if visible:
                items.append({"key": m.key, "label": m.label, "icon": m.icon, "path": m.route, "status": m.status})
        if items:
            groups.append({"key": gkey, "label": glabel, "items": items})
    return groups


def quick_actions(ctx: AuthContext) -> list[dict]:
    if ctx.kind == "partner":
        return [{"key": k, "label": label, "icon": icon, "path": path} for k, label, icon, path, perm in QUICK_ACTIONS
                if perm is not None and ctx.has(perm)]
    return [{"key": k, "label": label, "icon": icon, "path": path}
            for k, label, icon, path, perm in QUICK_ACTIONS if perm is None or ctx.has(perm)]


AMBIENT_VIEW_CODES = {"people.directory.view", "documents.document.view", "analytics.kpi.view"}


def context_options(ctx: AuthContext) -> dict:
    """Locations the person may switch Home to: everything under the broadest of their *view* grants. One option or
    none means no selector is shown."""
    from apps.organization.models import OrgUnit

    org_wide, paths = False, set()
    for code in ctx.permission_codes:
        # Ambient grants everyone has (company directory, shared documents) don't make someone a multi-location viewer.
        if not code.endswith(".view") or code in AMBIENT_VIEW_CODES:
            continue
        sc = ctx.scope(code)
        org_wide = org_wide or sc.org_wide
        paths |= sc.unit_paths
    qs = OrgUnit.objects.filter(organization=ctx.organization, is_active=True)
    if not org_wide:
        from django.db.models import Q

        cond = Q(pk__in=[])
        for p in paths:
            cond |= Q(path__startswith=p)
        qs = qs.filter(cond)
    units = [unit_brief(u) | {"depth": u.depth, "parent_id": str(u.parent_id) if u.parent_id else None} for u in qs.order_by("path")[:300]]
    prefs = ((ctx.account.preferences or {}).get("home") or {}) if ctx.account else {}
    selected = prefs.get("context_unit")
    if selected and selected not in {u["id"] for u in units}:
        selected = None
    return {"org_wide": org_wide, "units": units, "selected": selected, "switchable": len(units) > 1 or (org_wide and len(units) > 0)}


def build_context(ctx: AuthContext, request) -> dict:
    user, account, emp = ctx.user, ctx.account, ctx.employee
    org = ctx.organization
    chain = [unit_brief(u) for u in emp.org_unit.ancestors()] if emp and emp.org_unit else []
    limits = [{"type": t, "label": registry.APPROVAL_TYPES.get(t, t), "max_amount": str(v) if v is not None else None,
               "currency": org.base_currency} for t, v in sorted(ctx.limits.items())]
    session = getattr(request, "os_session", None)
    manager = emp.manager if emp else None
    return {
        "user": {"id": str(user.pk), "full_name": user.full_name, "email": user.email, "phone": user.phone,
                 "avatar_url": avatar_url(account)},
        "account": {"id": str(account.pk), "kind": account.kind, "status": account.status, "mfa_enabled": account.mfa_enabled,
                    "onboarding_required": account.onboarding_completed_at is None, "timezone": account.timezone or org.timezone,
                    "language": account.language, "last_login_at": account.last_login_at, "access_version": account.access_version,
                    "preferences": {k: v for k, v in (account.preferences or {}).items() if k != "dev_persona"},
                    "partner": ({"id": str(account.partner_id), "name": account.partner.business_name,
                                 "code": account.partner.partner_code} if account.partner_id else None)},
        "employee": ({"id": str(emp.pk), "employee_id": emp.employee_id, "full_name": emp.full_name,
                      "designation": emp.designation.name if emp.designation else None, "status": emp.status,
                      "employment_type": emp.employment_type, "joined_on": emp.joined_on,
                      "manager": {"id": str(manager.pk), "full_name": manager.full_name} if manager else None} if emp else None),
        "organization": {"id": str(org.pk), "name": org.name, "code": org.code, "currency": org.base_currency, "timezone": org.timezone},
        "org_context": {"units": chain, "location": unit_brief(emp.org_unit) if emp else None,
                        "department": dept_brief(emp.department) if emp else None, "team": team_brief(emp.team) if emp else None},
        "roles": [{"id": str(r.pk), "key": r.key, "name": r.name} for r in {r.pk: r for r in ctx.roles}.values()],
        "permissions": [{"code": c, "scope": ctx.scope(c).level} for c in ctx.permission_codes],
        "mfa_blocked": sorted(ctx.mfa_blocked),
        "approval_authority": limits,
        "navigation": navigation(ctx),
        "quick_actions": quick_actions(ctx),
        "context_options": context_options(ctx),
        "is_manager": ctx.is_manager,
        "direct_reports": len(ctx.direct_report_ids),
        "session": {"id": str(session.pk), "expires_at": session.expires_at, "mfa_verified": session.mfa_verified} if session else None,
        "security": {"sensitive_requires_mfa": settings.CLICK_OS_SENSITIVE_REQUIRES_MFA,
                     "idle_minutes": settings.CLICK_OS_IDLE_MINUTES},
    }


def module_payload(ctx: AuthContext, m: registry.Module) -> dict:
    return {
        "key": m.key, "label": m.label, "group": m.group, "icon": m.icon, "description": m.description, "status": m.status,
        "path": m.route, "submodules": list(m.submodules), "includes": list(m.includes),
        "resources": [{"key": r.key, "label": r.label, "sensitive": r.sensitive,
                       "actions": [{"action": a, "allowed": ctx.has(f"{m.key}.{r.key}.{a}"),
                                    "scope": ctx.scope(f"{m.key}.{r.key}.{a}").level} for a in r.actions]}
                      for r in m.resources],
    }
