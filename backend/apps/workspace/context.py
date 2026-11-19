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
    # key, label, icon, path, permission (None = every account)
    ("create_task", "Create task", "plus", "/tasks?new=1", None),
    ("start_approval", "Start approval", "check", "/approvals/new", "workflows.request.create"),
    ("submit_expense", "Submit expense", "receipt", "/approvals/new?policy=finance.expense", "finance.expense.create"),
    ("search_employee", "Find employee", "team", "/search?type=employee", "people.directory.view"),
    ("search_partner", "Find partner", "store", "/search?type=partner", "partners.partner.view"),
    ("open_reports", "Open reports", "chart", "/m/analytics", "analytics.report.view"),
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
    return [{"key": k, "label": label, "icon": icon, "path": path}
            for k, label, icon, path, perm in QUICK_ACTIONS if perm is None or ctx.has(perm)]


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
