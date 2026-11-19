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
    # Employee self-service: always limited to their own record
    ("people.leave.create", "own"), ("people.leave.view", "own"), ("people.attendance.create", "own"), ("people.attendance.view", "own"),
    ("people.request.create", "own"), ("people.document.create", "own"), ("people.goal.create", "own"), ("people.goal.view", "own"),
    ("people.performance.view", "own"), ("people.learning.view", "own"), ("people.feedback.create", "organization"),
    ("documents.document.view", "organization"),
    ("ai.assistant.view", "own"),
    ("analytics.kpi.view", "department"),
]

# Given automatically to anyone with direct reports (decided from the reporting line in People & HR).
MANAGER = [
    ("people.employee.view", "reports"), ("people.attendance.view", "reports"), ("people.attendance.approve", "reports"),
    ("people.leave.view", "reports"), ("people.leave.approve", "reports"), ("people.performance.view", "reports"),
    ("people.performance.review", "reports"), ("people.goal.view", "reports"), ("people.goal.create", "reports"), ("people.goal.edit", "reports"),
    ("people.learning.view", "reports"), ("people.learning.assign", "reports"), ("people.lifecycle.create", "reports"),
    ("people.document.view", "reports"), ("workflows.task.assign", "reports"), ("workflows.request.view", "reports"),
]
HR_ALL = [c for c in registry.PERMISSIONS if c.startswith("people.")]


def _all_actions(module: str, actions=None) -> list[str]:
    return [c for c, (m, r, a) in registry.PERMISSIONS.items() if m.key == module and (actions is None or a in actions)]


ROLES = [
    {
        "key": "employee", "name": "Employee", "priority": 90, "audience": "employee",
        "description": "Every Click employee: directory, own requests, own tasks, self-service HR, Business AI.",
        "grants": EVERYONE, "widgets": ["priorities", "my_work", "approvals", "upcoming", "training_due", "upcoming_reviews", "announcements"],
    },
    {
        "key": "people-manager", "name": "People Manager (automatic)", "priority": 60, "audience": "employee",
        "description": "Applied automatically to anyone with direct reports: team leave, attendance, goals, reviews and tasks — reports only.",
        "grants": MANAGER, "widgets": ["team", "pending_leave", "upcoming_reviews"],
    },
    {
        "key": "os-admin", "name": "System Administrator", "priority": 5, "audience": "employee", "requires_mfa": True,
        "description": "Runs the Business OS: users, roles, organization, workflows, integrations, system and audit. No business data.",
        "grants": [(c, "organization") for m in ADMIN_MODULES for c in _all_actions(m)] + [("workflows.task.assign", "organization")],
        "widgets": ["security_overview", "system_status", "alerts", "approvals", "my_work"],
    },
    {
        "key": "executive", "name": "CEO / Executive", "priority": 10, "audience": "employee",
        "description": "Company-wide visibility across every business area, top approval authority.",
        "grants": [(c, "organization") for m in BUSINESS for c in _all_actions(m, {"view", "approve", "reject", "export"})
                   if not registry.is_sensitive(c)] + [("audit.event.view", "organization"), ("organization.unit.view", "organization"),
                                                       ("organization.department.view", "organization"), ("workflows.request.view", "organization"),
                                                       ("workflows.task.assign", "organization")],
        "limits": {t: None for t in registry.APPROVAL_TYPES},
        "widgets": ["business_pulse", "priorities", "approvals", "alerts", "ecosystem", "risk_watch", "insights", "opportunities", "finance_snapshot",
                    "partner_snapshot", "services_snapshot", "people_overview", "ai_briefing"],
        "pulse": ["gmv", "orders", "bookings", "customers", "partners", "open_tickets", "operational_issues", "headcount"],
    },
    {
        "key": "finance-head", "name": "Finance Head", "priority": 20, "audience": "employee",
        "description": "Owns Finance and Payments company-wide.",
        "grants": [(c, "organization") for m in ("finance", "payments") for c in _all_actions(m)]
                  + [("analytics.business.view", "organization"), ("analytics.report.view", "organization"),
                     ("workflows.request.view", "organization"), ("procurement.order.approve", "organization"), ("procurement.order.view", "organization")],
        "limits": {"expense": None, "purchase": None, "payment": None, "refund": None},
        "widgets": ["finance_snapshot", "business_pulse", "approvals", "alerts", "insights", "ai_briefing"],
        "pulse": ["gmv", "refunds", "failed_payments", "expenses", "orders"],
    },
    {
        "key": "finance-manager", "name": "Finance Manager", "priority": 25, "audience": "employee",
        "description": "Approves expenses and payments up to a limit within their region.",
        "grants": [(c, "region") for c in _all_actions("finance", {"view", "create", "edit", "approve", "reject", "export"})]
                  + [("payments.transaction.view", "region"), ("workflows.request.view", "region")],
        "limits": {"expense": Decimal("50000"), "payment": Decimal("50000"), "refund": Decimal("10000")},
        "widgets": ["approvals", "business_pulse", "alerts", "my_work"], "pulse": ["expenses", "approvals"],
    },
    {
        "key": "hr-manager", "name": "HR Manager", "priority": 30, "audience": "employee",
        "description": "Employee records, attendance, leave, hiring and payroll (payroll needs MFA).",
        "grants": [(c, "organization") for c in HR_ALL] + [("organization.department.view", "organization"),
                                                           ("organization.unit.view", "organization"), ("communications.announcement.create", "organization"),
                                                           ("communications.announcement.view", "organization"), ("identity.user.create", "organization")],
        "limits": {"hiring": Decimal("1500000")},
        "widgets": ["people_overview", "approvals", "new_joiners", "probation_ending", "document_expiries", "attendance_exceptions", "open_positions",
                    "pending_leave"], "pulse": ["headcount", "approvals", "expenses"],
    },
    {
        "key": "operations-manager", "name": "Operations Manager", "priority": 35, "audience": "employee",
        "description": "Orders, service operations, incidents, support and partner operations.",
        "grants": [(c, "organization") for m in ("operations", "services", "supply_chain", "cx") for c in _all_actions(m)]
                  + [("partners.partner.view", "organization")],
        "limits": {"refund": Decimal("5000")}, "widgets": ["operations_overview", "business_pulse", "alerts", "services_snapshot", "partner_snapshot", "approvals"],
        "pulse": ["orders", "bookings", "rides", "operational_issues", "open_tickets"],
    },
    {
        "key": "partner-manager", "name": "Partner Manager", "priority": 40, "audience": "employee",
        "description": "Partner applications, verification, performance and suspensions.",
        "grants": [(c, "organization") for c in _all_actions("partners")],
        "widgets": ["partner_snapshot", "business_pulse", "alerts", "risk_watch", "approvals", "my_work"], "pulse": ["partners", "partner_apps"],
    },
    {
        "key": "branch-manager", "name": "Branch Manager", "priority": 45, "audience": "employee",
        "description": "Runs one branch: its people, operations, expenses and approvals.",
        "grants": [("people.employee.view", "branch"), ("people.attendance.view", "branch"), ("people.leave.approve", "branch"),
                   ("people.leave.view", "branch"), ("finance.expense.view", "branch"), ("finance.expense.approve", "branch"),
                   ("procurement.request.view", "branch"), ("procurement.request.approve", "branch"), ("operations.incident.view", "branch"),
                   ("workflows.request.view", "branch"), ("workflows.task.assign", "branch"), ("organization.unit.view", "branch")],
        "limits": {"expense": Decimal("25000"), "purchase": Decimal("25000")},
        "widgets": ["approvals", "team", "people_overview", "attendance_exceptions", "pending_leave", "alerts", "my_work"],
        "pulse": ["headcount", "expenses", "approvals"],
    },
    {
        "key": "auditor", "name": "Internal Auditor", "priority": 50, "audience": "employee", "requires_mfa": True,
        "description": "Read-only: audit trail (including sensitive events), finance and approvals.",
        "grants": [("audit.event.view", "organization"), ("audit.event.export", "organization"), ("audit.sensitive.view", "organization"),
                   ("workflows.request.view", "organization")] + [(c, "organization") for c in _all_actions("finance", {"view"})],
        "widgets": ["alerts", "risk_watch", "approvals"],
    },
    {
        "key": "hr-business-partner", "name": "HR Business Partner", "priority": 32, "audience": "employee",
        "description": "HR for a region: employee records, leave, attendance, performance and recruitment — no payroll or cases.",
        "grants": [(c, "region") for c in HR_ALL if not registry.is_sensitive(c)] + [("organization.department.view", "organization")],
        "widgets": ["people_overview", "approvals", "pending_leave", "attendance_exceptions", "probation_ending", "new_joiners"], "pulse": ["headcount"],
    },
    {
        "key": "recruiter", "name": "Recruiter", "priority": 34, "audience": "employee",
        "description": "Openings, candidates, interviews and offers.",
        "grants": [(c, "organization") for c in HR_ALL if c.split(".")[1] in ("recruitment", "candidate", "offer", "onboarding")]
                  + [("people.position.view", "organization"), ("people.employee.view", "organization")],
        "limits": {"hiring": Decimal("0")}, "widgets": ["open_positions", "approvals", "new_joiners", "my_work"],
    },
    {
        "key": "payroll-admin", "name": "Payroll Administrator", "priority": 36, "audience": "employee", "requires_mfa": True,
        "description": "Compensation, benefits and payroll inputs (sensitive, needs two-step verification).",
        "grants": [(c, "organization") for c in HR_ALL if c.split(".")[1] in ("payroll", "benefit")]
                  + [("people.employee.view", "organization"), ("people.attendance.view", "organization"), ("people.leave.view", "organization")],
        "limits": {"payment": Decimal("0")}, "widgets": ["approvals", "people_overview"],
    },
    {
        "key": "sales-manager", "name": "Sales & CRM Manager", "priority": 42, "audience": "employee",
        "description": "Customers, leads, quotes and pricing approvals.",
        "grants": [(c, "organization") for c in _all_actions("sales")], "limits": {"discount": Decimal("20000")},
        "widgets": ["business_pulse", "approvals", "insights", "my_work"], "pulse": ["customers", "orders", "gmv"],
    },
    {
        "key": "support-lead", "name": "Customer Support Lead", "priority": 43, "audience": "employee",
        "description": "Support tickets, calls, escalations and refunds within limit.",
        "grants": [(c, "organization") for c in _all_actions("cx")] + [("payments.refund.view", "organization"), ("payments.refund.approve", "organization")],
        "limits": {"refund": Decimal("5000")}, "widgets": ["alerts", "business_pulse", "approvals", "priority_inbox", "my_work"],
        "pulse": ["open_tickets", "refunds", "orders"],
    },
    {
        "key": "marketing-manager", "name": "Marketing Manager", "priority": 44, "audience": "employee",
        "description": "Campaigns, sponsored placements, loyalty and content.",
        "grants": [(c, "organization") for c in _all_actions("marketing")] + [("communications.announcement.view", "organization")],
        "limits": {"discount": Decimal("50000")}, "widgets": ["business_pulse", "insights", "opportunities", "approvals"], "pulse": ["customers", "orders"],
    },
    {
        "key": "procurement-officer", "name": "Procurement Officer", "priority": 46, "audience": "employee",
        "description": "Purchase requests, RFQs, suppliers and purchase orders.",
        "grants": [(c, "organization") for c in _all_actions("procurement")] + [("inventory.stock.view", "organization")],
        "limits": {"purchase": Decimal("200000")}, "widgets": ["approvals", "alerts", "my_work"],
    },
    {
        "key": "it-admin", "name": "IT Administrator", "priority": 47, "audience": "employee",
        "description": "IT assets, platform operations, integrations and system health.",
        "grants": [(c, "organization") for c in _all_actions("technology")] + [("system.health.view", "organization"),
                                                                              ("integrations.integration.view", "organization")],
        "widgets": ["system_status", "alerts", "approvals", "my_work"],
    },
    {
        "key": "partner-business", "name": "Partner Business User", "priority": 80, "audience": "partner",
        "description": "External partner login: only their own partner workspace.",
        "grants": [("partners.workspace.view", "organization"), ("partners.partner.view", "organization"),
                   ("workflows.request.create", "own")],
        "widgets": ["priorities", "approvals", "alerts", "announcements"],
    },
]

POLICIES = [
    {"key": "people.leave", "name": "Leave request", "module": "people", "approval_type": "general", "amount_unit": "days",
     "submit_permission": "people.leave.create", "requires_amount": True,
     "description": "Manager approval; longer leave also goes to HR.",
     "levels": [("Manager", "people.leave.approve", 0, 24), ("HR", "people.leave.manage", 6, 48)]},
    {"key": "people.attendance_correction", "name": "Attendance correction", "module": "people", "approval_type": "general", "amount_unit": "count",
     "submit_permission": "people.attendance.create", "requires_amount": False, "description": "Missing or wrong check-in / check-out.",
     "levels": [("Manager", "people.attendance.approve", 0, 48)]},
    {"key": "people.position", "name": "New position (hiring)", "module": "people", "approval_type": "hiring", "amount_unit": "currency",
     "submit_permission": "people.position.create", "requires_amount": False, "description": "Approve headcount and budget before hiring starts.",
     "levels": [("HR approval", "people.position.approve", 0, 72)]},
    {"key": "people.offer", "name": "Job offer", "module": "people", "approval_type": "hiring", "amount_unit": "currency",
     "submit_permission": "people.offer.create", "requires_amount": True, "description": "Compensation in the offer, within hiring authority.",
     "levels": [("Offer approval", "people.offer.approve", 0, 48)]},
    {"key": "people.promotion", "name": "Promotion", "module": "people", "approval_type": "general", "amount_unit": "currency",
     "submit_permission": "people.lifecycle.create", "requires_amount": False, "description": "New role, level and pay.",
     "levels": [("HR approval", "people.lifecycle.approve", 0, 72)]},
    {"key": "people.transfer", "name": "Transfer", "module": "people", "approval_type": "general", "amount_unit": "currency",
     "submit_permission": "people.lifecycle.create", "requires_amount": False, "description": "Department, location or manager change.",
     "levels": [("HR approval", "people.lifecycle.approve", 0, 72)]},
    {"key": "people.salary_revision", "name": "Salary revision", "module": "people", "approval_type": "general", "amount_unit": "currency",
     "submit_permission": "people.payroll.manage", "requires_amount": True, "description": "Change to base pay (payroll approval).",
     "levels": [("Payroll approval", "people.payroll.approve", 0, 72)]},
    {"key": "people.offboarding", "name": "Exit (resignation / termination)", "module": "people", "approval_type": "general", "amount_unit": "count",
     "submit_permission": "people.offboarding.manage", "requires_amount": False, "description": "Confirms the exit and starts the offboarding checklist.",
     "levels": [("HR approval", "people.offboarding.approve", 0, 72)]},
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
            "requires_mfa": spec.get("requires_mfa", False), "home_widgets": spec.get("widgets", []), "is_system": True, "is_active": True,
            "home_config": {"pulse": spec.get("pulse", [])}})
        role.grants.all().delete()
        RolePermission.objects.bulk_create([RolePermission(role=role, permission=perms[c], scope=s) for c, s in expand(spec["grants"]) if c in perms])
        role.approval_limits.all().delete()
        RoleApprovalLimit.objects.bulk_create([RoleApprovalLimit(role=role, approval_type=t, max_amount=v, currency=organization.base_currency)
                                               for t, v in spec.get("limits", {}).items()])
        roles[spec["key"]] = role
    for spec in POLICIES:
        pol, created = ApprovalPolicy.objects.get_or_create(organization=organization, key=spec["key"], defaults={
            "name": spec["name"], "module": spec["module"], "approval_type": spec["approval_type"], "description": spec["description"],
            "submit_permission": spec["submit_permission"], "requires_amount": spec["requires_amount"], "currency": organization.base_currency,
            "amount_unit": spec.get("amount_unit", "currency")})
        if created:
            for i, (name, perm, min_amount, hours) in enumerate(spec["levels"], start=1):
                ApprovalLevel.objects.create(policy=pol, sequence=i, name=name, approver_permission=perm,
                                             min_amount=Decimal(min_amount), escalate_after_hours=hours,
                                             enforce_limit=spec["approval_type"] != "general" and spec.get("amount_unit", "currency") == "currency")
    return roles
