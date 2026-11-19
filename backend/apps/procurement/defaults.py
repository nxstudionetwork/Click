"""Procurement starting configuration (idempotent, editable afterwards): category tree, request templates, role
templates, approval policies and purchasing policy values."""

from decimal import Decimal

D = Decimal

# code, name, parent, expenditure, finance account key, budget category, match mode, inventory, service
CATEGORIES = [
    ("TECH", "Technology", None, "opex", "technology", "technology", "three_way", False, False),
    ("TECH-HW", "Hardware", "TECH", "capex", "asset_clearing", "technology", "three_way", False, False),
    ("TECH-SW", "Software & licences", "TECH", "opex", "technology", "technology", "two_way", False, True),
    ("TECH-CLOUD", "Cloud & hosting", "TECH", "opex", "technology", "technology", "two_way", False, True),
    ("TECH-SEC", "Security", "TECH", "opex", "technology", "technology", "two_way", False, True),
    ("TECH-NET", "Networking", "TECH", "capex", "asset_clearing", "technology", "three_way", False, False),
    ("OFF", "Office", None, "opex", "office", "operations", "three_way", False, False),
    ("OFF-FURN", "Furniture", "OFF", "capex", "asset_clearing", "operations", "three_way", False, False),
    ("OFF-STAT", "Stationery", "OFF", "opex", "office", "operations", "three_way", False, False),
    ("OFF-CONS", "Consumables", "OFF", "opex", "office", "operations", "three_way", False, False),
    ("MKT", "Marketing", None, "opex", "marketing", "marketing", "two_way", False, True),
    ("MKT-ADS", "Advertising", "MKT", "opex", "marketing", "marketing", "two_way", False, True),
    ("MKT-CRE", "Creative services", "MKT", "opex", "marketing", "marketing", "two_way", False, True),
    ("MKT-EVT", "Events", "MKT", "opex", "marketing", "marketing", "two_way", False, True),
    ("OPS", "Operations", None, "opex", "field_ops", "operations", "three_way", False, False),
    ("OPS-EQP", "Equipment", "OPS", "capex", "asset_clearing", "operations", "three_way", False, False),
    ("OPS-MNT", "Maintenance", "OPS", "opex", "field_ops", "operations", "two_way", False, True),
    ("OPS-FLD", "Field supplies", "OPS", "opex", "field_ops", "operations", "three_way", False, False),
    ("OPS-INV", "Click-owned inventory (for resale)", "OPS", "opex", "inventory", "operations", "three_way", True, False),
    ("PRO", "Professional services", None, "opex", "professional", "", "two_way", False, True),
    ("PRO-LEG", "Legal", "PRO", "opex", "professional", "", "two_way", False, True),
    ("PRO-CON", "Consulting", "PRO", "opex", "professional", "", "two_way", False, True),
    ("PRO-ACC", "Accounting", "PRO", "opex", "professional", "", "two_way", False, True),
    ("PRO-TRN", "Training", "PRO", "opex", "professional", "", "two_way", False, True),
    ("FAC", "Facilities", None, "opex", "rent", "operations", "two_way", False, True),
    ("FAC-RENT", "Rent", "FAC", "opex", "rent", "operations", "two_way", False, True),
    ("FAC-UTIL", "Utilities", "FAC", "opex", "utilities", "operations", "two_way", False, True),
    ("FAC-MNT", "Facility maintenance", "FAC", "opex", "rent", "operations", "two_way", False, True),
    ("FAC-SEC", "Security services", "FAC", "opex", "rent", "operations", "two_way", False, True),
    ("VEH", "Vehicles", None, "capex", "asset_clearing", "operations", "three_way", False, False),
]

TEMPLATES = [  # key, name, category, request type, expenditure, justification hint, documents, sourcing note
    ("it_hardware", "IT hardware purchase", "TECH-HW", "hardware", "capex", "Who needs it, why the current device can't be used.", "Specification sheet",
     "Competitive quotes above the RFQ threshold. Registered as a fixed asset on receipt."),
    ("software", "Software purchase", "TECH-SW", "software", "opex", "Problem it solves, number of users, alternatives considered.",
     "Security review for SaaS handling customer data", "Check existing licences and contracts first."),
    ("marketing", "Marketing services", "MKT-CRE", "service", "opex", "Campaign, audience, expected outcome.", "Brief / scope of work", "RFP for agencies."),
    ("office_supplies", "Office supplies", "OFF-STAT", "standard", "opex", "Quantity and location.", "", "Use preferred suppliers."),
    ("professional", "Professional services", "PRO-CON", "service", "opex", "Scope, deliverables, timeline.", "Statement of work", "RFP above the RFQ threshold."),
    ("facility_maintenance", "Facility maintenance", "FAC-MNT", "service", "opex", "What is broken or due, at which site.", "", "Annual maintenance contract if recurring."),
    ("capital_equipment", "Capital equipment", "OPS-EQP", "capex", "capex", "Business case, useful life, alternatives.", "Business case", "Finance approval and asset registration."),
    ("subscription", "Recurring subscription", "TECH-CLOUD", "subscription", "opex", "Plan, seats, renewal date.", "", "Set up as a recurring purchase with a contract."),
    ("emergency", "Emergency purchase", "OPS-FLD", "emergency", "opex", "What happened, why normal sourcing can't wait.", "",
     "Temporary approval now; post-purchase review is mandatory."),
]


def _actions(module, actions=None):
    from apps.access import registry

    return [c for c, (m, r, a) in registry.PERMISSIONS.items() if m.key == module and (actions is None or a in actions)]


def roles():
    allp = [(c, "organization") for c in _actions("procurement")]
    view = [(c, "organization") for c in _actions("procurement", {"view"})]
    fin_view = [("finance.budget.view", "organization"), ("finance.overview.view", "organization")]
    return [
        {"key": "procurement-director", "name": "Procurement Director", "priority": 41, "audience": "employee",
         "description": "Owns procurement company-wide: approvals at the top of the purchase authority, policy and settings.",
         "grants": allp + fin_view, "limits": {"purchase": None}, "widgets": ["approvals", "alerts", "my_work", "insights"]},
        {"key": "procurement-manager", "name": "Procurement Manager", "priority": 42, "audience": "employee",
         "description": "Approves purchase requests, awards and purchase orders within limit; manages suppliers and contracts.",
         "grants": [c for c in allp if not c[0].startswith(("procurement.settings.configure", "procurement.supplier_bank.approve"))] + fin_view,
         "limits": {"purchase": D("1000000")}, "widgets": ["approvals", "alerts", "my_work"]},
        {"key": "category-manager", "name": "Category Manager", "priority": 43, "audience": "employee",
         "description": "Runs sourcing for a category: RFQ/RFP, evaluation, negotiation and award recommendations.",
         "grants": view + [("procurement.sourcing.create", "organization"), ("procurement.sourcing.manage", "organization"),
                           ("procurement.quotation.create", "organization"), ("procurement.quotation.evaluate", "organization"),
                           ("procurement.award.create", "organization"), ("procurement.supplier.create", "organization"),
                           ("procurement.supplier.edit", "organization")], "widgets": ["approvals", "my_work"]},
        {"key": "buyer", "name": "Buyer", "priority": 44, "audience": "employee",
         "description": "Creates purchase orders from approved requests and awards, tracks delivery. Cannot approve.",
         "grants": view + [("procurement.order.create", "organization"), ("procurement.order.edit", "organization"),
                           ("procurement.sourcing.create", "organization"), ("procurement.quotation.create", "organization"),
                           ("procurement.quotation.evaluate", "organization"), ("procurement.award.create", "organization")],
         "widgets": ["approvals", "my_work", "alerts"]},
        {"key": "receiving-officer", "name": "Receiving Officer", "priority": 47, "audience": "employee",
         "description": "Records goods and service receipts at their location.",
         "grants": [("procurement.order.view", "branch"), ("procurement.receipt.view", "branch"), ("procurement.receipt.create", "branch"),
                    ("procurement.supplier.view", "organization")], "widgets": ["my_work", "alerts"]},
        {"key": "quality-inspector", "name": "Quality Inspector", "priority": 48, "audience": "employee",
         "description": "Inspects received goods and records the result.",
         "grants": [("procurement.order.view", "organization"), ("procurement.receipt.view", "organization"), ("procurement.receipt.inspect", "organization")],
         "widgets": ["my_work"]},
        {"key": "contract-manager", "name": "Contract Manager", "priority": 49, "audience": "employee",
         "description": "Procurement contracts, obligations and renewals.",
         "grants": [("procurement.contract.view", "organization"), ("procurement.contract.manage", "organization"), ("procurement.supplier.view", "organization"),
                    ("procurement.order.view", "organization"), ("procurement.analytics.view", "organization")], "widgets": ["alerts", "my_work"]},
        {"key": "procurement-analyst", "name": "Procurement Analyst", "priority": 50, "audience": "employee",
         "description": "Read-only spend, savings, supplier and cycle-time analytics.",
         "grants": view + [("procurement.analytics.export", "organization")], "widgets": ["insights"]},
    ]


POLICIES = [
    {"key": "procurement.order", "name": "Purchase order", "module": "procurement", "approval_type": "purchase", "submit_permission": "procurement.order.create",
     "requires_amount": True, "description": "Commits Click to a supplier. Large orders also need Finance.",
     "levels": [("Procurement approval", "procurement.order.approve", 0, 24), ("Finance approval", "finance.payment.approve", 500000, 48)]},
    {"key": "procurement.award", "name": "Supplier selection (award)", "module": "procurement", "approval_type": "purchase",
     "submit_permission": "procurement.award.create", "requires_amount": True, "description": "Why this supplier was chosen, with the comparison.",
     "levels": [("Award approval", "procurement.award.approve", 0, 48)]},
    {"key": "procurement.amendment", "name": "PO amendment", "module": "procurement", "approval_type": "purchase", "submit_permission": "procurement.order.edit",
     "requires_amount": True, "description": "A change to an approved purchase order creates a new version once approved.",
     "levels": [("Procurement approval", "procurement.order.approve", 0, 24)]},
    {"key": "procurement.supplier", "name": "Supplier onboarding", "module": "procurement", "approval_type": "general", "amount_unit": "count",
     "submit_permission": "procurement.supplier.create", "requires_amount": False,
     "description": "Verification, compliance and procurement review, then finance review.",
     "levels": [("Procurement review", "procurement.supplier.approve", 0, 72), ("Finance review", "finance.bill.approve", 0, 72)]},
    {"key": "procurement.supplier_bank", "name": "Supplier bank details change", "module": "procurement", "approval_type": "general", "amount_unit": "count",
     "submit_permission": "procurement.supplier_bank.manage", "requires_amount": False,
     "description": "High-risk change: verified independently and approved by someone else before any payment uses it.",
     "levels": [("Bank change approval", "procurement.supplier_bank.approve", 0, 24)]},
    {"key": "procurement.exception", "name": "Procurement policy exception", "module": "procurement", "approval_type": "general", "amount_unit": "count",
     "submit_permission": "procurement.exception.manage", "requires_amount": False, "description": "Single source, emergency, missing quotes and other deviations.",
     "levels": [("Exception approval", "procurement.exception.approve", 0, 48)]},
]


def install(organization) -> None:
    from apps.access.defaults import expand
    from apps.access.models import Permission, Role, RoleApprovalLimit, RolePermission
    from apps.workflows.models import ApprovalLevel, ApprovalPolicy

    from . import models as m

    m.ProcurementPolicy.objects.get_or_create(organization=organization, defaults={
        "contract_alert_days": [90, 60, 30],
        "code_of_conduct": "Buy only what Click needs, from suppliers chosen on merit and total cost. Declare any conflict of interest before taking part.",
        "gift_policy": "Gifts or hospitality above ₹2,000 from a supplier must be declared and are normally declined.",
        "anti_bribery_policy": "No payment, favour or benefit may be offered or accepted to influence a purchasing decision."})
    cats = {c.code: c for c in m.ProcurementCategory.objects.filter(organization=organization)}
    for code, name, parent, exp, acc, bcat, match, inv, svc in CATEGORIES:
        if code not in cats:
            cats[code] = m.ProcurementCategory.objects.create(organization=organization, code=code, name=name, parent=cats.get(parent) if parent else None,
                                                              expenditure=exp, finance_account_key=acc, budget_category=bcat, match_mode=match,
                                                              is_inventory=inv, is_service=svc)
    perms = {p.code: p for p in Permission.objects.all()}
    for spec in roles():
        role, _ = Role.objects.update_or_create(organization=organization, key=spec["key"], defaults={
            "name": spec["name"], "description": spec["description"], "priority": spec["priority"], "audience": spec["audience"],
            "home_widgets": spec.get("widgets", []), "is_system": True, "is_active": True})
        role.grants.all().delete()
        RolePermission.objects.bulk_create([RolePermission(role=role, permission=perms[c], scope=s) for c, s in expand(spec["grants"]) if c in perms])
        role.approval_limits.all().delete()
        RoleApprovalLimit.objects.bulk_create([RoleApprovalLimit(role=role, approval_type=t, max_amount=v, currency=organization.base_currency)
                                               for t, v in spec.get("limits", {}).items()])
    for spec in POLICIES:
        pol, created = ApprovalPolicy.objects.get_or_create(organization=organization, key=spec["key"], defaults={
            "name": spec["name"], "module": spec["module"], "approval_type": spec["approval_type"], "description": spec["description"],
            "submit_permission": spec["submit_permission"], "requires_amount": spec["requires_amount"], "currency": organization.base_currency,
            "amount_unit": spec.get("amount_unit", "currency")})
        if created:
            for i, (name, perm, min_amount, hours) in enumerate(spec["levels"], start=1):
                ApprovalLevel.objects.create(policy=pol, sequence=i, name=name, approver_permission=perm, min_amount=D(min_amount), escalate_after_hours=hours,
                                             enforce_limit=spec["approval_type"] != "general" and spec.get("amount_unit", "currency") == "currency")
    # Purchase requests (installed by the foundation): add the executive level for very large requests if missing.
    pr = ApprovalPolicy.objects.filter(organization=organization, key="procurement.request").first()
    if pr and not pr.levels.filter(min_amount__gte=1000000).exists():
        ApprovalLevel.objects.get_or_create(policy=pr, sequence=pr.levels.count() + 1, defaults={
            "name": "Executive approval", "approver_permission": "procurement.request.approve", "min_amount": D("1000000"), "escalate_after_hours": 72,
            "enforce_limit": True})
