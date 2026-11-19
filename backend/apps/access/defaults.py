"""
Built-in role templates (is_system=True, read-only; duplicate to customise) and approval policies installed by
`manage.py os_bootstrap`. Grants use patterns over the registry: "finance.*.view" @ scope.

Approval limits here are starting templates, not business rules baked into code: they live in the database and
administrators change them per role.
"""

from decimal import Decimal
from fnmatch import fnmatch

from . import registry

ADMIN_MODULES = ("organization", "identity", "access", "workflows", "integrations", "system", "audit")
BUSINESS = [m.key for m in registry.MODULES if m.group in ("business", "platform") and m.resources]

EVERYONE = [
    ("people.directory.view", "organization"),
    ("workflows.request.create", "own"),
    ("finance.expense.create", "own"),
    ("procurement.request.create", "own"),
    ("people.leave.create", "own"),
    ("documents.document.view", "organization"),
    ("ai.assistant.view", "own"),
    ("analytics.kpi.view", "department"),
]


def _all_actions(module: str, actions=None) -> list[str]:
    return [c for c, (m, r, a) in registry.PERMISSIONS.items() if m.key == module and (actions is None or a in actions)]


ROLES = [
    {
        "key": "employee", "name": "Employee", "priority": 90, "audience": "employee",
        "description": "Every Click employee: directory, own requests, own tasks, Business AI.",
        "grants": EVERYONE, "widgets": ["approvals", "my_work", "calendar", "notifications"],
    },
    {
        "key": "os-admin", "name": "System Administrator", "priority": 5, "audience": "employee", "requires_mfa": True,
        "description": "Runs the Business OS: users, roles, organization, workflows, integrations, system and audit. No business data.",
        "grants": [(c, "organization") for m in ADMIN_MODULES for c in _all_actions(m)] + [("workflows.task.assign", "organization")],
        "widgets": ["security_overview", "approvals", "my_work"],
    },
    {
        "key": "executive", "name": "CEO / Executive", "priority": 10, "audience": "employee",
        "description": "Company-wide visibility across every business area, top approval authority.",
        "grants": [(c, "organization") for m in BUSINESS for c in _all_actions(m, {"view", "approve", "reject", "export"})
                   if not registry.is_sensitive(c)] + [("audit.event.view", "organization"), ("organization.unit.view", "organization"),
                                                       ("organization.department.view", "organization"), ("workflows.request.view", "organization"),
                                                       ("workflows.task.assign", "organization")],
        "limits": {t: None for t in registry.APPROVAL_TYPES},
        "widgets": ["business_snapshot", "approvals", "finance_overview", "operations_overview", "partner_pipeline", "people_overview"],
    },
    {
        "key": "finance-head", "name": "Finance Head", "priority": 20, "audience": "employee",
        "description": "Owns Finance and Payments company-wide.",
        "grants": [(c, "organization") for m in ("finance", "payments") for c in _all_actions(m)]
                  + [("analytics.business.view", "organization"), ("analytics.report.view", "organization"),
                     ("workflows.request.view", "organization"), ("procurement.order.approve", "organization"), ("procurement.order.view", "organization")],
        "limits": {"expense": None, "purchase": None, "payment": None, "refund": None},
        "widgets": ["finance_overview", "approvals", "business_snapshot"],
    },
    {
        "key": "finance-manager", "name": "Finance Manager", "priority": 25, "audience": "employee",
        "description": "Approves expenses and payments up to a limit within their region.",
        "grants": [(c, "region") for c in _all_actions("finance", {"view", "create", "edit", "approve", "reject", "export"})]
                  + [("payments.transaction.view", "region"), ("workflows.request.view", "region")],
        "limits": {"expense": Decimal("50000"), "payment": Decimal("50000"), "refund": Decimal("10000")},
        "widgets": ["approvals", "my_work"],
    },
    {
        "key": "hr-manager", "name": "HR Manager", "priority": 30, "audience": "employee",
        "description": "Employee records, attendance, leave, hiring and payroll (payroll needs MFA).",
        "grants": [(c, "organization") for c in _all_actions("people")] + [("organization.department.view", "organization"),
                                                                           ("organization.unit.view", "organization")],
        "limits": {"hiring": Decimal("1500000")}, "widgets": ["people_overview", "approvals", "my_work"],
    },
    {
        "key": "operations-manager", "name": "Operations Manager", "priority": 35, "audience": "employee",
        "description": "Orders, service operations, incidents, support and partner operations.",
        "grants": [(c, "organization") for m in ("operations", "services", "supply_chain", "cx") for c in _all_actions(m)]
                  + [("partners.partner.view", "organization")],
        "limits": {"refund": Decimal("5000")}, "widgets": ["operations_overview", "approvals", "partner_pipeline"],
    },
    {
        "key": "partner-manager", "name": "Partner Manager", "priority": 40, "audience": "employee",
        "description": "Partner applications, verification, performance and suspensions.",
        "grants": [(c, "organization") for c in _all_actions("partners")],
        "widgets": ["partner_pipeline", "approvals", "my_work"],
    },
    {
        "key": "branch-manager", "name": "Branch Manager", "priority": 45, "audience": "employee",
        "description": "Runs one branch: its people, operations, expenses and approvals.",
        "grants": [("people.employee.view", "branch"), ("people.attendance.view", "branch"), ("people.leave.approve", "branch"),
                   ("people.leave.view", "branch"), ("finance.expense.view", "branch"), ("finance.expense.approve", "branch"),
                   ("procurement.request.view", "branch"), ("procurement.request.approve", "branch"), ("operations.incident.view", "branch"),
                   ("workflows.request.view", "branch"), ("workflows.task.assign", "branch"), ("organization.unit.view", "branch")],
        "limits": {"expense": Decimal("25000"), "purchase": Decimal("25000")},
        "widgets": ["approvals", "people_overview", "my_work"],
    },
    {
        "key": "auditor", "name": "Internal Auditor", "priority": 50, "audience": "employee", "requires_mfa": True,
        "description": "Read-only: audit trail (including sensitive events), finance and approvals.",
        "grants": [("audit.event.view", "organization"), ("audit.event.export", "organization"), ("audit.sensitive.view", "organization"),
                   ("workflows.request.view", "organization")] + [(c, "organization") for c in _all_actions("finance", {"view"})],
        "widgets": ["approvals", "notifications"],
    },
    {
        "key": "partner-business", "name": "Partner Business User", "priority": 80, "audience": "partner",
        "description": "External partner login: only their own partner workspace.",
        "grants": [("partners.workspace.view", "organization"), ("partners.partner.view", "organization"),
                   ("workflows.request.create", "own")],
        "widgets": ["approvals", "notifications"],
    },
]

POLICIES = [
    {"key": "finance.expense", "name": "Expense claim", "module": "finance", "approval_type": "expense",
     "submit_permission": "finance.expense.create", "requires_amount": True,
     "description": "Business and employee expenses. Higher amounts go to a second level.",
     "levels": [("Finance review", "finance.expense.approve", 0, 48), ("Finance Head", "finance.expense.approve", 50000, 72)]},
    {"key": "procurement.request", "name": "Purchase request", "module": "procurement", "approval_type": "purchase",
     "submit_permission": "procurement.request.create", "requires_amount": True,
     "description": "Buying goods or services. Goes to procurement approvers within limit.",
     "levels": [("Manager approval", "procurement.request.approve", 0, 48), ("Finance approval", "finance.payment.approve", 100000, 72)]},
    {"key": "workflows.general", "name": "General approval", "module": "workflows", "approval_type": "general",
     "submit_permission": "workflows.request.create", "requires_amount": False,
     "description": "Anything else that needs a manager's sign-off.",
     "levels": [("Approver", "workflows.request.view", 0, 72)]},
]


def expand(grants) -> list[tuple[str, str]]:
    out: dict[str, str] = {}
    order = registry.SCOPES
    for pattern, scope in grants:
        for code in registry.PERMISSIONS:
            if fnmatch(code, pattern):
                if code not in out or order.index(scope) > order.index(out[code]):
                    out[code] = scope
    return sorted(out.items())


def install(organization) -> dict:
    """Idempotent: creates/refreshes system roles and default policies for an organization."""
    from apps.workflows.models import ApprovalLevel, ApprovalPolicy

    from .models import Permission, Role, RoleApprovalLimit, RolePermission

    perms = {p.code: p for p in Permission.objects.all()}
    roles = {}
    for spec in ROLES:
        role, _ = Role.objects.update_or_create(organization=organization, key=spec["key"], defaults={
            "name": spec["name"], "description": spec["description"], "priority": spec["priority"], "audience": spec["audience"],
            "requires_mfa": spec.get("requires_mfa", False), "home_widgets": spec.get("widgets", []), "is_system": True, "is_active": True})
        role.grants.all().delete()
        RolePermission.objects.bulk_create([RolePermission(role=role, permission=perms[c], scope=s) for c, s in expand(spec["grants"]) if c in perms])
        role.approval_limits.all().delete()
        RoleApprovalLimit.objects.bulk_create([RoleApprovalLimit(role=role, approval_type=t, max_amount=v, currency=organization.base_currency)
                                               for t, v in spec.get("limits", {}).items()])
        roles[spec["key"]] = role
    for spec in POLICIES:
        pol, created = ApprovalPolicy.objects.get_or_create(organization=organization, key=spec["key"], defaults={
            "name": spec["name"], "module": spec["module"], "approval_type": spec["approval_type"], "description": spec["description"],
            "submit_permission": spec["submit_permission"], "requires_amount": spec["requires_amount"], "currency": organization.base_currency})
        if created:
            for i, (name, perm, min_amount, hours) in enumerate(spec["levels"], start=1):
                ApprovalLevel.objects.create(policy=pol, sequence=i, name=name, approver_permission=perm,
                                             min_amount=Decimal(min_amount), escalate_after_hours=hours, enforce_limit=spec["approval_type"] != "general")
    return roles
