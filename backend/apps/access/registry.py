"""
The Business OS module and permission catalogue. Code is the source of truth; `sync_permissions` mirrors it into
the Permission table after every migrate so roles can reference rows.

Permission code: <module>.<resource>.<action>     e.g. finance.invoice.approve
Granted with a scope on a role:                     finance.invoice.approve @ branch

Adding a module later = add a Module here (resources + actions), then build its API on the same OS view base.
Nothing else (login, roles, navigation, search, audit, approvals) needs a module-specific copy.

The 50-area business map (work_details/os/modules_os.txt) is grouped into the navigation workspaces below
(`includes`), so the sidebar stays usable while every area still has one home.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ACTIONS = ("view", "create", "edit", "delete", "approve", "reject", "export", "import", "manage", "configure", "assign")

# Narrowest → broadest. A role grants each permission at one of these levels, resolved from the
# assignee's anchor (assignment's unit / department / team, else the employee record).
SCOPES = ("own", "reports", "team", "department", "branch", "city", "state", "region", "business_unit", "organization")
SCOPE_LABELS = {
    "own": "Own records", "reports": "My reports (reporting line)", "team": "Team", "department": "Department", "branch": "Branch / site", "city": "City",
    "state": "State", "region": "Region", "business_unit": "Business unit", "organization": "Entire organization",
}

APPROVAL_TYPES = {
    "general": "General", "expense": "Expense", "purchase": "Purchase", "refund": "Refund", "discount": "Discount",
    "hiring": "Hiring", "payment": "Payment", "journal": "Journal entry", "settlement": "Partner settlement", "budget": "Budget",
}


@dataclass(frozen=True)
class Resource:
    key: str
    label: str
    actions: tuple[str, ...]
    sensitive: bool = False  # salary, identity admin, sensitive audit … (may require MFA, never shown by default)


@dataclass(frozen=True)
class Module:
    key: str
    label: str
    group: str  # core | business | platform | administration
    icon: str
    description: str
    status: str = "planned"  # live | foundation | planned
    resources: tuple[Resource, ...] = ()
    submodules: tuple[str, ...] = ()
    includes: tuple[str, ...] = ()  # business areas from the 50-area map that live inside this workspace
    path: str = ""
    always_visible: bool = False  # core workspace pages every signed-in account has
    nav_requires: tuple[str, ...] = ()  # if set, the sidebar entry needs one of these (not just any permission in the module)

    @property
    def route(self) -> str:
        return self.path or f"/m/{self.key}"


R = Resource
CRUD = ("view", "create", "edit", "delete")
VIEW = ("view",)
APPROVE = ("view", "create", "edit", "approve", "reject", "export")

MODULES: tuple[Module, ...] = (
    # ---- CORE (every account; data inside is still scoped) ----
    Module("home", "Home", "core", "home", "Your command center: what to know and what to do today.", "live", path="/home", always_visible=True),
    Module("my_work", "My Work", "core", "inbox", "Tasks, approvals and requests that need you.", "live", path="/my-work", always_visible=True),
    Module("approvals", "Approvals", "core", "check", "Approval inbox, your requests and history.", "live", path="/approvals", always_visible=True),
    Module("tasks", "Tasks", "core", "list", "Tasks assigned to you and by you.", "live", path="/tasks", always_visible=True),
    Module("notifications", "Notifications", "core", "bell", "Approvals, tasks, security and business alerts.", "live", path="/notifications", always_visible=True),
    Module("calendar", "Calendar", "core", "calendar", "Deadlines from your tasks and approvals.", "live", path="/calendar", always_visible=True),

    # ---- BUSINESS ----
    Module("people", "People & HR", "business", "team", "The employee lifecycle: directory, talent, workforce, performance, learning, pay and exits.",
           "live", path="/people",
           resources=(R("directory", "Employee directory", VIEW),
                      R("employee", "Employee records", CRUD + ("export", "import")),
                      R("personal", "Personal & contact details", ("view", "edit"), sensitive=True),
                      R("position", "Positions & headcount", CRUD + ("approve",)),
                      R("workforce", "Workforce planning", ("view", "manage")),
                      R("recruitment", "Recruitment (openings & pipeline)", ("view", "create", "edit", "manage")),
                      R("candidate", "Candidate profiles", ("view", "edit"), sensitive=False),
                      R("offer", "Offers", ("view", "create", "approve")),
                      R("onboarding", "Onboarding", ("view", "manage")),
                      R("attendance", "Attendance", ("view", "create", "manage", "approve")),
                      R("leave", "Leave", ("view", "create", "approve", "manage")),
                      R("schedule", "Schedules, shifts & holidays", ("view", "manage")),
                      R("performance", "Performance reviews", ("view", "review", "manage")),
                      R("goal", "Goals & OKRs", ("view", "create", "edit")),
                      R("feedback", "Feedback & recognition", ("view", "create")),
                      R("learning", "Learning, skills & certifications", ("view", "assign", "manage", "verify")),
                      R("payroll", "Compensation & payroll", ("view", "manage", "approve", "export"), sensitive=True),
                      R("benefit", "Benefits", ("view", "manage")),
                      R("engagement", "Surveys & engagement", ("view", "manage")),
                      R("request", "HR requests", ("view", "create", "manage")),
                      R("case", "Employee relations cases", ("view", "manage"), sensitive=True),
                      R("lifecycle", "Promotions & transfers", ("view", "create", "approve")),
                      R("offboarding", "Offboarding & exits", ("view", "manage", "approve")),
                      R("document", "Employee documents", ("view", "create", "verify")),
                      R("document_restricted", "Restricted documents (ID, tax, medical)", ("view", "create"), sensitive=True),
                      R("analytics", "HR analytics", ("view", "export")),
                      R("settings", "HR settings & policies", ("view", "configure"))),
           submodules=("Employee Directory", "People 360", "Org Chart", "Positions", "Workforce Planning", "Recruitment", "Candidates",
                       "Interviews", "Offers", "Onboarding", "Attendance", "Leave", "Shifts & Holidays", "Goals", "Reviews", "Feedback",
                       "Learning", "Skills", "Certifications", "Compensation", "Benefits", "Payroll Integration", "Self Service", "HR Requests",
                       "Recognition", "Engagement", "Promotions & Transfers", "Offboarding", "Exit Interviews", "HR Analytics")),
    Module("finance", "Finance", "business", "receipt", "Accounting, receivables, payables, cash, expenses, budgets, tax and assets.", "foundation",
           resources=(R("overview", "Finance overview", VIEW), R("ledger", "General ledger & journals", CRUD + ("approve",)),
                      R("invoice", "Invoices", APPROVE + ("delete",)), R("expense", "Expenses", APPROVE + ("delete",)),
                      R("payment", "Payments & payables", APPROVE), R("budget", "Budgets", CRUD + ("approve",)),
                      R("tax", "Tax", ("view", "configure")), R("asset", "Fixed assets", CRUD), R("report", "Financial reports", ("view", "export"))),
           submodules=("Accounting", "Accounts Receivable", "Accounts Payable", "Cash & Banking", "Expenses", "Budgets",
                       "Financial Reports", "Taxes", "Assets")),
    Module("sales", "Sales & CRM", "business", "briefcase", "Leads, opportunities, quotes, customer 360, loyalty and retention.", "foundation",
           resources=(R("customer", "Customers", ("view", "edit", "export")), R("lead", "Leads & opportunities", CRUD),
                      R("quote", "Quotes & sales orders", APPROVE), R("pricing", "Pricing & discounts", ("view", "configure", "approve"))),
           submodules=("Leads", "Opportunities", "Customers", "Customer 360", "Segments", "Quotes", "Sales Orders", "Pricing", "Discounts",
                       "Returns", "Refunds", "Communication History", "Loyalty", "Retention", "Feedback", "Sales Analytics"),
           includes=("Sales & Commerce", "Customer / CRM")),
    Module("procurement", "Procurement", "business", "bag", "Buying: requests, RFQs, quotations, purchase orders and goods receipt.", "foundation",
           resources=(R("request", "Purchase requests", APPROVE), R("order", "Purchase orders", APPROVE), R("supplier", "Suppliers", CRUD)),
           submodules=("Purchase Requests", "Purchase Orders", "Suppliers", "Supplier Evaluation", "Quotations", "RFQ",
                       "Comparative Statements", "Contracts", "Purchase Approvals", "Goods Receipt", "Supplier Invoices", "Procurement Analytics")),
    Module("inventory", "Inventory", "business", "warehouse", "What Click owns or holds: SKUs, stock, warehouses, transfers and valuation.", "foundation",
           resources=(R("stock", "Stock", ("view", "edit", "approve")), R("transfer", "Stock transfers", APPROVE), R("product", "Products & SKUs", CRUD)),
           submodules=("Products", "SKU Management", "Stock", "Warehouses", "Branch Stock", "Stock Transfers", "Stock Adjustments",
                       "Goods Receipt", "Goods Dispatch", "Batches", "Serial Numbers", "Expiry", "Stock Counts", "Low Stock",
                       "Damaged Stock", "Inventory Valuation")),
    Module("supply_chain", "Supply Chain", "business", "parcel", "Planning, fulfillment, dispatch, logistics partners, routes and returns.", "foundation",
           resources=(R("shipment", "Shipments", CRUD), R("plan", "Supply & demand plans", ("view", "manage"))),
           submodules=("Supply Planning", "Demand Planning", "Fulfillment", "Dispatch", "Delivery", "Logistics Partners", "Routes",
                       "Shipments", "Tracking", "Returns", "Reverse Logistics", "Delivery Performance", "Logistics Cost"),
           includes=("Supply Chain & Logistics", "Maps, Locations & Geospatial Operations")),
    Module("partners", "Partners", "business", "store", "Partner lifecycle: applications, KYC/KYB, contracts, performance, commission and settlements.", "foundation",
           resources=(R("partner", "Partners", ("view", "edit", "approve", "reject", "export")), R("verification", "Verification & KYC", ("view", "approve", "reject")),
                      R("commission", "Commission & settlements", ("view", "configure", "approve")), R("workspace", "Partner workspace", VIEW)),
           submodules=("Partner Directory", "Applications", "Verification", "KYC/KYB", "Contracts", "Categories", "Performance", "Ratings",
                       "Commission", "Settlements", "Documents", "Partner Support", "Suspension", "Compliance", "Commercial Model"),
           includes=("Partners & Suppliers", "Merchant & Business Management", "Strategic Partnerships")),
    Module("operations", "Operations", "business", "wrench", "Day-to-day running: orders, service operations, escalations, SOPs and shifts.", "foundation",
           resources=(R("order", "Orders", ("view", "edit", "export")), R("incident", "Incidents & escalations", CRUD), R("sop", "SOPs & checklists", CRUD)),
           submodules=("Operational Dashboard", "Orders", "Service Operations", "Partner Operations", "Escalations", "Incident Management",
                       "SOPs", "Checklists", "Daily Operations", "Shift Management", "Exception Management")),
    Module("services", "Click Services", "business", "sparkle", "Services offered through the ecosystem, bookings, field workforce and SLAs.", "foundation",
           resources=(R("service", "Service catalogue", CRUD), R("booking", "Bookings & reservations", ("view", "edit", "approve")),
                      R("field_worker", "Field workforce", CRUD)),
           submodules=("Service Directory", "Categories", "Providers", "Service Areas", "Pricing", "Availability", "Bookings",
                       "Assignments", "SLA", "Reviews", "Complaints", "Refunds", "Commission", "Field Workers", "Drivers", "Technicians"),
           includes=("Click Services", "Bookings & Reservations", "Field Workforce & Service Personnel")),
    Module("marketing", "Marketing", "business", "tag", "Campaigns, offers, loyalty, sponsored listings, social, content and website.", "foundation",
           resources=(R("campaign", "Campaigns", APPROVE), R("sponsored", "Sponsored placements & auction", ("view", "configure", "approve")),
                      R("loyalty", "Loyalty, rewards & gift cards", ("view", "configure")), R("content", "Content, social & website", CRUD + ("approve",))),
           submodules=("Campaigns", "Promotions", "Coupons", "Referrals", "Push / Email / SMS", "Audience Segments", "Sponsored Listings",
                       "Discover Promotions", "Bidding & Auction", "Loyalty & Gift Cards", "Social Media", "Content & Media",
                       "Website & SEO", "Marketing Analytics"),
           includes=("Marketing", "Advertising & Sponsored Marketplace", "Loyalty, Rewards & Gift Cards", "Social Media & Digital Presence",
                     "Content & Media", "Website & Digital Platforms")),
    Module("cx", "Customer Experience", "business", "help", "Customer and partner support, contact center, complaints and satisfaction.", "foundation",
           resources=(R("ticket", "Support tickets", ("view", "edit", "assign", "export")), R("call", "Calls & contact center", ("view", "manage"))),
           submodules=("Customer Support", "Partner Support", "Contact Center", "Tickets", "Live Chat", "Call Center", "IVR & Queues",
                       "Complaints", "Refund Requests", "Escalations", "SLA", "Customer Satisfaction", "Support Analytics"),
           includes=("Customer Experience & Support", "Call Assistance & Communications", "Support & Service Desk")),
    Module("projects", "Projects", "business", "target", "Projects, milestones, resources, timesheets and project profitability.", "foundation",
           resources=(R("project", "Projects", CRUD + ("approve",)), R("timesheet", "Timesheets", APPROVE)),
           submodules=("Projects", "Teams", "Tasks", "Milestones", "Dependencies", "Budgets", "Expenses", "Resources", "Timesheets", "Reports")),
    Module("legal", "Legal", "business", "scale", "Contracts, agreements, renewals, legal cases and obligations.", "foundation",
           resources=(R("contract", "Contracts & agreements", APPROVE + ("delete",)), R("case", "Legal cases", CRUD)),
           submodules=("Contracts", "Partner Agreements", "Supplier Agreements", "Employee Agreements", "NDAs", "Terms & Conditions",
                       "Renewals", "Expiry Tracking", "Legal Cases", "Compliance Obligations"),
           includes=("Legal & Contracts",)),
    Module("risk", "Risk & Compliance", "business", "shield", "Risk register, compliance, trust & safety, fraud, quality and governance.", "foundation",
           resources=(R("risk", "Risk register", CRUD), R("fraud", "Fraud & trust-safety cases", ("view", "edit", "approve")),
                      R("policy", "Policies & controls", CRUD + ("approve",)), R("quality", "Quality", CRUD), R("governance", "Governance & board", VIEW + ("manage",))),
           submodules=("Risk Register", "Compliance", "Policies", "Internal Controls", "Fraud Monitoring", "Trust & Safety", "Investigations",
                       "Audit Findings", "Corrective Actions", "Quality Management", "Corporate Governance", "Authority Matrix", "ESG & CSR"),
           includes=("Risk, Compliance & Security", "Trust, Safety & Fraud", "Quality Management", "Corporate Governance", "Sustainability & CSR")),

    # ---- PLATFORM ----
    Module("payments", "Payments & Settlements", "platform", "card", "Payment transactions, partner payouts, commission, refunds, reconciliation, billing.", "foundation",
           resources=(R("transaction", "Payment transactions", ("view", "export")), R("settlement", "Settlements & payouts", APPROVE),
                      R("refund", "Refunds & chargebacks", APPROVE), R("billing", "Billing & subscriptions", ("view", "configure"))),
           submodules=("Payment Accounts", "Transactions", "Settlements", "Partner Payouts", "Commission", "Refunds", "Chargebacks",
                       "Reconciliation", "Gateways", "Billing & Subscriptions", "Revenue Streams", "Revenue Recognition"),
           includes=("Treasury & Payments", "Billing & Subscription Management", "Revenue & Commission Management")),
    Module("analytics", "Analytics", "platform", "chart", "Executive intelligence, KPIs, forecasts and every department's analytics.", "foundation",
           resources=(R("business", "Business snapshot", VIEW), R("report", "Reports & dashboards", ("view", "create", "export")),
                      R("kpi", "KPIs, goals & OKRs", ("view", "manage"))),
           submodules=("Executive Dashboard", "Finance", "Sales", "Customers", "Partners", "Operations", "HR", "Inventory", "Marketing",
                       "Branches", "Profitability", "Forecasting", "KPIs & OKRs", "Board Reports", "Custom Reports"),
           includes=("Analytics & Business Intelligence", "Executive Intelligence", "Strategy & Performance")),
    Module("ai", "AI & Automation", "platform", "sparkle", "Click Business AI (inherits your permissions), workflow automation and scheduled jobs.", "foundation",
           resources=(R("assistant", "Business AI", ("view",)), R("automation", "Automations & rules", ("view", "configure"))),
           submodules=("Business AI Assistant", "Ask Your Business Data", "Insights", "Anomaly Detection", "Forecasting", "Report Generation",
                       "Document Understanding", "Workflow Automation", "Rule Engine", "Scheduled Jobs")),
    Module("documents", "Documents", "platform", "book", "Company documents, SOPs, policies, templates and the knowledge base.", "foundation",
           resources=(R("document", "Documents", CRUD + ("approve",)),),
           submodules=("Company Documents", "SOPs", "Policies", "Manuals", "Templates", "Forms", "Knowledge Base", "Version Control",
                       "Document Approval", "Document Search"),
           includes=("Documents & Knowledge",)),
    Module("audit", "Audit", "platform", "history", "Who did what, when, and what changed. Append-only.", "live", path="/settings/audit",
           resources=(R("event", "Audit events", ("view", "export")), R("sensitive", "Sensitive audit events", VIEW, sensitive=True))),
    Module("communications", "Communications", "platform", "send", "Announcements, channels, messaging and communication history.", "foundation",
           resources=(R("announcement", "Announcements", CRUD + ("approve",)), R("channel", "Channels & templates", ("view", "configure"))),
           submodules=("Internal Announcements", "Department Channels", "Direct Messages", "Email", "SMS", "Push", "WhatsApp / External",
                       "Templates", "Broadcasts", "Communication History"),
           includes=("Communications", "Customer & Partner Communications")),
    Module("technology", "Technology", "platform", "device", "IT assets, platform operations, APIs and developer platform.", "foundation",
           resources=(R("asset", "IT assets & licences", CRUD), R("platform", "Platform operations", ("view", "manage")),
                      R("api", "APIs & developer platform", ("view", "configure"))),
           submodules=("IT Assets", "Devices", "Software & Licences", "IT Tickets", "Servers & Databases", "Deployments", "Monitoring",
                       "Logs", "Backups", "Disaster Recovery", "API Management", "OAuth", "Rate Limits", "Sandbox"),
           includes=("IT & Internal Technology", "Infrastructure & Platform Operations", "API & Developer Platform")),

    # ---- ADMINISTRATION ----
    Module("organization", "Organization", "administration", "building", "Company, business units, locations, departments and teams.", "live", path="/settings/organization",
           resources=(R("unit", "Units & locations", ("view", "create", "edit", "manage")), R("department", "Departments & teams", ("view", "create", "edit", "manage"))),
           includes=("Locations / Branches",)),
    Module("identity", "Users", "administration", "user", "Accounts, invitations, suspension and sessions.", "live", path="/settings/users",
           resources=(R("user", "User accounts", ("view", "create", "edit", "manage"), sensitive=True),
                      R("service_account", "Service accounts", ("view", "manage"), sensitive=True),
                      R("security", "Security events, sessions & sign-in risk", ("view", "manage"), sensitive=True))),
    Module("access", "Identity & Access", "administration", "key",
           "Who can do what, where: roles, packages, requests, reviews, segregation of duties, emergency access and effective-access tools.",
           "live", path="/access",
           nav_requires=("access.role.view", "access.analysis.view", "access.package.view", "access.review.view", "access.sod.view",
                         "access.emergency.view", "access.emergency.create", "identity.user.view"),
           resources=(R("role", "Roles", ("view", "create", "edit", "delete", "assign"), sensitive=True),
                      R("package", "Access packages", ("view", "manage")),
                      R("request", "Access requests", ("view", "create", "approve")),
                      R("review", "Access reviews & certification", ("view", "manage")),
                      R("analysis", "Effective access, who-has-access, simulator & role comparison", ("view",)),
                      R("sod", "Segregation of duties (rules & exceptions)", ("view", "configure", "approve"), sensitive=True),
                      R("emergency", "Emergency (break-glass) access", ("view", "create", "manage"), sensitive=True)),
           submodules=("Identity Directory", "Service Accounts", "Role Directory", "Role Comparison", "Access Packages", "Access Requests",
                       "Temporary Access", "Delegations", "Access Reviews", "Approval Authority", "Effective Access", "Permission Simulator",
                       "Who Has Access", "Segregation of Duties", "Privileged Access", "Emergency Access", "Security Events", "Orphaned & Unused Access")),
    Module("workflows", "Workflows", "administration", "flow", "Approval policies, levels, limits and escalation.", "live", path="/settings/workflows",
           nav_requires=("workflows.policy.view", "workflows.policy.configure"),
           resources=(R("policy", "Approval policies", ("view", "configure")), R("request", "Approval requests", ("view", "create")),
                      R("task", "Tasks", ("view", "assign")))),
    Module("integrations", "Integrations", "administration", "plug", "Payment, SMS, email, maps, logistics and other connectors.", "live", path="/settings/integrations",
           resources=(R("integration", "Integrations", ("view", "configure"), sensitive=True),)),
    Module("system", "System Settings", "administration", "settings", "System health, security policy and configuration.", "live", path="/settings/system",
           resources=(R("health", "System health", VIEW), R("settings", "System configuration", ("view", "configure"), sensitive=True))),
)

MODULE_BY_KEY = {m.key: m for m in MODULES}

# What makes someone an administrator (for the "Administrator" sign-in path and admin badges). Raising requests or
# assigning tasks lives in the workflows module too, but that is everyday work, not administration.
ADMIN_CODE_PREFIXES = ("organization.", "identity.", "access.role.", "access.package.", "access.review.", "access.analysis.", "access.sod.",
                       "access.emergency.", "workflows.policy.", "integrations.", "system.", "audit.")
# Requesting access for yourself ("access.request.create") and managers approving their reports' requests are everyday
# work, not administration: they never make someone an administrator or put Identity & Access in their sidebar.


def is_admin_code(code: str) -> bool:
    return code.startswith(ADMIN_CODE_PREFIXES)
GROUPS = (("core", "Core"), ("business", "Business"), ("platform", "Platform"), ("administration", "Administration"))


def all_permissions() -> dict[str, tuple[Module, Resource, str]]:
    out = {}
    for module in MODULES:
        for res in module.resources:
            for action in res.actions:
                out[f"{module.key}.{res.key}.{action}"] = (module, res, action)
    return out


PERMISSIONS = all_permissions()


def is_known(code: str) -> bool:
    return code in PERMISSIONS


def is_sensitive(code: str) -> bool:
    entry = PERMISSIONS.get(code)
    return bool(entry and entry[1].sensitive)


def sync_permissions(using: str = "default") -> None:
    """Mirror the catalogue into the Permission table. Removed codes are deactivated, never deleted (roles keep history)."""
    from .models import Permission

    existing = {p.code: p for p in Permission.objects.using(using).all()}
    for code, (module, res, action) in PERMISSIONS.items():
        label = f"{action.capitalize()} · {res.label}"
        p = existing.get(code)
        if p is None:
            Permission.objects.using(using).create(code=code, module=module.key, resource=res.key, action=action,
                                                   label=label, sensitive=res.sensitive)
        elif (p.label, p.sensitive, p.is_active) != (label, res.sensitive, True):
            p.label, p.sensitive, p.is_active = label, res.sensitive, True
            p.save(using=using, update_fields=["label", "sensitive", "is_active", "updated_at"])
    Permission.objects.using(using).exclude(code__in=PERMISSIONS.keys()).filter(is_active=True).update(is_active=False)
