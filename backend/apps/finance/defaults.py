"""
Finance starting configuration, installed idempotently with the access templates (os_bootstrap / seed). Everything is
data that finance administrators change afterwards — account codes, tax rates, fees and limits are templates, not
business rules baked into code. Tax rates must be reviewed with a qualified professional before production use.
"""

from datetime import date
from decimal import Decimal

D = Decimal

# (code, name, type, system_key, parent_code)
CHART = [
    ("1000", "Assets", "asset", "", None),
    ("1100", "Cash in hand", "asset", "cash", "1000"),
    ("1200", "Bank accounts", "asset", "bank", "1000"),
    ("1210", "Payment gateway clearing", "asset", "gateway_clearing", "1000"),
    ("1300", "Accounts receivable", "asset", "ar", "1000"),
    ("1310", "Partner receivables", "asset", "partner_receivable", "1000"),
    ("1350", "Input tax credit", "asset", "input_tax", "1000"),
    ("1400", "Inventory (Click-owned)", "asset", "inventory", "1000"),
    ("1500", "Fixed assets", "asset", "fixed_assets", "1000"),
    ("1510", "Accumulated depreciation", "asset", "accumulated_depreciation", "1000"),
    ("1600", "Capital work in progress / assets awaiting capitalisation", "asset", "asset_clearing", "1000"),
    ("2000", "Liabilities", "liability", "", None),
    ("2100", "Accounts payable", "liability", "ap", "2000"),
    ("2110", "Goods received not invoiced", "liability", "grni", "2000"),
    ("2200", "Taxes payable", "liability", "tax_payable", "2000"),
    ("2210", "TDS payable", "liability", "tds_payable", "2000"),
    ("2300", "Partner payables (settlements due)", "liability", "partner_payable", "2000"),
    ("2400", "Customer wallet & gift card balances", "liability", "stored_value", "2000"),
    ("2500", "Employee reimbursements payable", "liability", "employee_payable", "2000"),
    ("2600", "Payroll payable", "liability", "payroll_payable", "2000"),
    ("2700", "Customer refunds payable", "liability", "refunds_payable", "2000"),
    ("3000", "Equity", "equity", "", None),
    ("3100", "Share capital", "equity", "share_capital", "3000"),
    ("3200", "Retained earnings", "equity", "retained_earnings", "3000"),
    ("4000", "Revenue", "revenue", "", None),
    ("4100", "Platform commission", "revenue", "commission_revenue", "4000"),
    ("4150", "Platform fees", "revenue", "platform_fee_revenue", "4000"),
    ("4200", "Service, delivery & convenience fees", "revenue", "service_fee_revenue", "4000"),
    ("4300", "Subscription revenue", "revenue", "subscription_revenue", "4000"),
    ("4400", "Advertising & sponsored placements", "revenue", "advertising_revenue", "4000"),
    ("4500", "Sales of Click-owned goods & services", "revenue", "principal_revenue", "4000"),
    ("4900", "Other operating revenue", "revenue", "other_revenue", "4000"),
    ("5000", "Cost of revenue", "cost_of_revenue", "", None),
    ("5100", "Payment gateway charges", "cost_of_revenue", "payment_costs", "5000"),
    ("5200", "Click-funded promotions & discounts", "cost_of_revenue", "promotion_cost", "5000"),
    ("5300", "Click-funded refunds", "cost_of_revenue", "refund_cost", "5000"),
    ("5400", "Cost of goods sold (Click-owned)", "cost_of_revenue", "cogs", "5000"),
    ("6000", "Operating expenses", "expense", "", None),
    ("6100", "Salaries & wages", "expense", "salaries", "6000"),
    ("6200", "Technology & software", "expense", "technology", "6000"),
    ("6300", "Marketing", "expense", "marketing", "6000"),
    ("6400", "Rent & facilities", "expense", "rent", "6000"),
    ("6500", "Utilities", "expense", "utilities", "6000"),
    ("6600", "Travel & meals", "expense", "travel", "6000"),
    ("6700", "Office & consumables", "expense", "office", "6000"),
    ("6800", "Professional services", "expense", "professional", "6000"),
    ("6850", "Field operations", "expense", "field_ops", "6000"),
    ("6900", "Depreciation", "expense", "depreciation", "6000"),
    ("6990", "General expenses", "expense", "general_expense", "6000"),
    ("7000", "Other income", "other_income", "", None),
    ("7100", "Interest income", "other_income", "interest_income", "7000"),
    ("7200", "Foreign exchange gain", "other_income", "fx_gain", "7000"),
    ("7300", "Gain on asset disposal", "other_income", "disposal_gain", "7000"),
    ("8000", "Other expenses", "other_expense", "", None),
    ("8100", "Foreign exchange loss", "other_expense", "fx_loss", "8000"),
    ("8200", "Loss on asset disposal", "other_expense", "disposal_loss", "8000"),
    ("8300", "Rounding & write-offs", "other_expense", "write_off", "8000"),
]

TAX_RULES = [  # code, name, kind, rate, output key, input key
    ("GST18", "GST 18% (intra-state: CGST 9% + SGST 9%)", "gst", D("18"), "tax_payable", "input_tax"),
    ("GST12", "GST 12%", "gst", D("12"), "tax_payable", "input_tax"),
    ("GST5", "GST 5%", "gst", D("5"), "tax_payable", "input_tax"),
    ("IGST18", "IGST 18% (inter-state)", "igst", D("18"), "tax_payable", "input_tax"),
    ("GST0", "GST exempt / nil", "gst", D("0"), "tax_payable", "input_tax"),
    ("TDS194C", "TDS on contractors (194C) 2%", "tds", D("2"), "tds_payable", None),
    ("TDS194J", "TDS on professional fees (194J) 10%", "tds", D("10"), "tds_payable", None),
    ("TCS52", "TCS by e-commerce operator (sec. 52) 1%", "tcs", D("1"), "tax_payable", None),
]

PAYMENT_METHODS = [  # method, label, fee %, settlement days
    ("upi", "UPI", D("0"), 1), ("card", "Card", D("2.0"), 2), ("netbanking", "Net banking", D("1.5"), 2), ("wallet", "Click Wallet", D("0"), 0),
    ("cash_on_delivery", "Cash on delivery", D("0"), 1), ("cash", "Cash to driver", D("0"), 1), ("pay_at_venue", "Pay at venue", D("0"), 0),
    ("gift_card", "Click Gift Card", D("0"), 0),
]

EXPENSE_CATEGORIES = [  # key, name, account key, limit per claim, receipt above, mileage rate, note
    ("travel", "Travel", "travel", D("25000"), D("500"), None, "Economy fares; hotels within city limits."),
    ("meals", "Meals", "travel", D("2000"), D("300"), None, "Business meals only; alcohol is not reimbursed."),
    ("mileage", "Mileage", "travel", D("5000"), D("0"), D("9.00"), "Personal vehicle on company work, per km."),
    ("office", "Office supplies", "office", D("10000"), D("500"), None, ""),
    ("software", "Software & subscriptions", "technology", D("15000"), D("0"), None, "Recurring tools go through Procurement."),
    ("field", "Field operations", "field_ops", D("10000"), D("300"), None, ""),
    ("marketing", "Marketing", "marketing", D("20000"), D("0"), None, ""),
    ("other", "Other", "general_expense", D("5000"), D("0"), None, "Explain in the purpose."),
]

CLOSE_TASKS = [
    ("bank_rec", "Bank reconciliation complete"), ("gateway_rec", "Payment gateway reconciliation complete"),
    ("settlements", "Partner settlements complete"), ("ar_review", "Receivables reviewed"), ("ap_review", "Payables reviewed"),
    ("tax_review", "Tax reviewed"), ("expenses", "Expenses reviewed"), ("accruals", "Accruals posted"),
    ("assets", "Fixed assets & depreciation updated"), ("payroll", "Payroll posted"), ("intercompany", "Intercompany reconciled (if applicable)"),
    ("management_review", "Management review complete"),
]

COST_CENTERS = [("CC-TECH", "Technology", "TECH"), ("CC-OPS", "Operations", "OPS"), ("CC-FIN", "Finance", "FIN"), ("CC-HR", "People & HR", "HR"),
                ("CC-MKT", "Marketing", "MKT"), ("CC-PTN", "Partnerships", "PTN"), ("CC-LEAD", "Leadership", "LEAD")]

FIN = "finance"


def _actions(module, actions=None):
    from apps.access import registry

    return [c for c, (m, r, a) in registry.PERMISSIONS.items() if m.key == module and (actions is None or a in actions)]


def roles():
    view = [(c, "organization") for c in _actions(FIN, {"view"})]
    return [
        {"key": "accountant", "name": "Accountant", "priority": 26, "audience": "employee",
         "description": "Journals, invoices, bills, reconciliation and close tasks. Cannot approve or pay.",
         "grants": view + [("finance.ledger.create", "organization"), ("finance.invoice.create", "organization"), ("finance.invoice.edit", "organization"),
                           ("finance.bill.create", "organization"), ("finance.reconciliation.manage", "organization"), ("finance.asset.create", "organization"),
                           ("finance.asset.edit", "organization"), ("finance.period.close", "organization"), ("finance.report.export", "organization"),
                           ("finance.dispute.manage", "organization")],
         "widgets": ["finance_snapshot", "approvals", "alerts", "my_work"], "pulse": ["expenses", "approvals"]},
        {"key": "payables-executive", "name": "Accounts Payable Executive", "priority": 27, "audience": "employee",
         "description": "Vendor bills, three-way match follow-up and payment preparation. Cannot approve payments.",
         "grants": [("finance.overview.view", "organization"), ("finance.bill.view", "organization"), ("finance.bill.create", "organization"),
                    ("finance.payment.view", "organization"), ("finance.payment.create", "organization"), ("procurement.order.view", "organization"),
                    ("procurement.receipt.view", "organization")],
         "widgets": ["approvals", "alerts", "my_work"]},
        {"key": "treasury-manager", "name": "Treasury Manager", "priority": 23, "audience": "employee", "requires_mfa": True,
         "description": "Bank accounts, payment execution, cash position and reconciliation.",
         "grants": [("finance.overview.view", "organization"), ("finance.bank.view", "organization"), ("finance.bank.manage", "organization"),
                    ("finance.payment.view", "organization"), ("finance.payment.execute", "organization"), ("finance.reconciliation.view", "organization"),
                    ("finance.reconciliation.manage", "organization"), ("finance.report.view", "organization"), ("finance.settlement.view", "organization")],
         "widgets": ["finance_snapshot", "alerts", "approvals"]},
        {"key": "settlement-executive", "name": "Settlement Executive", "priority": 28, "audience": "employee",
         "description": "Partner statements and settlement batches. Cannot approve or pay them.",
         "grants": [("finance.overview.view", "organization"), ("finance.settlement.view", "organization"), ("finance.settlement.create", "organization"),
                    ("finance.settlement.export", "organization"), ("finance.commission.view", "organization"), ("finance.dispute.view", "organization"),
                    ("finance.dispute.manage", "organization"), ("partners.partner.view", "organization")],
         "widgets": ["approvals", "alerts", "my_work"]},
        {"key": "financial-controller", "name": "Financial Controller", "priority": 21, "audience": "employee", "requires_mfa": True,
         "description": "Approves journals, closes and reopens periods, owns controls and reporting.",
         "grants": view + [("finance.ledger.approve", "organization"), ("finance.period.close", "organization"), ("finance.period.reopen", "organization"),
                           ("finance.report.export", "organization"), ("finance.invoice.approve", "organization"), ("finance.asset.approve", "organization"),
                           ("finance.settings.configure", "organization"), ("finance.tax.configure", "organization")],
         "limits": {"journal": None, "refund": D("100000")}, "widgets": ["finance_snapshot", "approvals", "alerts", "insights"]},
        {"key": "tax-manager", "name": "Tax Manager", "priority": 29, "audience": "employee",
         "description": "Tax rules, tax reports and reconciliation.",
         "grants": [("finance.overview.view", "organization"), ("finance.tax.view", "organization"), ("finance.tax.configure", "organization"),
                    ("finance.tax.export", "organization"), ("finance.report.view", "organization"), ("finance.invoice.view", "organization"),
                    ("finance.bill.view", "organization")],
         "widgets": ["alerts", "approvals"]},
    ]


POLICIES = [
    {"key": "finance.journal", "name": "Manual journal", "module": "finance", "approval_type": "journal", "submit_permission": "finance.ledger.create",
     "requires_amount": True, "description": "Manual, adjusting and accrual journals are approved by someone other than the preparer.",
     "levels": [("Controller approval", "finance.ledger.approve", 0, 48)]},
    {"key": "finance.bill", "name": "Vendor bill", "module": "finance", "approval_type": "payment", "submit_permission": "finance.bill.create",
     "requires_amount": True, "description": "Bills are checked against the PO and receipt, then approved for payment.",
     "levels": [("Payables approval", "finance.bill.approve", 0, 48), ("Finance Head", "finance.bill.approve", 500000, 72)]},
    {"key": "finance.payment", "name": "Outgoing payment / payment run", "module": "finance", "approval_type": "payment",
     "submit_permission": "finance.payment.create", "requires_amount": True, "description": "Releases money. Creator and approver must differ.",
     "levels": [("Payment approval", "finance.payment.approve", 0, 24), ("Finance Head", "finance.payment.approve", 1000000, 48)]},
    {"key": "finance.settlement", "name": "Partner settlement batch", "module": "finance", "approval_type": "settlement",
     "submit_permission": "finance.settlement.create", "requires_amount": True, "description": "Net partner payouts for a settlement period.",
     "levels": [("Settlement approval", "finance.settlement.approve", 0, 24)]},
    {"key": "finance.credit_note", "name": "Credit / debit note", "module": "finance", "approval_type": "refund", "submit_permission": "finance.invoice.create",
     "requires_amount": True, "description": "Adjusts an issued invoice. Issued invoices are never edited.",
     "levels": [("Finance approval", "finance.invoice.approve", 0, 48)]},
    {"key": "finance.budget", "name": "Budget", "module": "finance", "approval_type": "budget", "submit_permission": "finance.budget.create",
     "requires_amount": True, "description": "Department review, finance review, executive approval for large budgets.",
     "levels": [("Finance review", "finance.budget.approve", 0, 72), ("Executive approval", "finance.budget.approve", 1000000, 96)]},
    {"key": "finance.agreement", "name": "Partner commercial terms", "module": "finance", "approval_type": "general",
     "submit_permission": "finance.commission.configure", "requires_amount": False, "amount_unit": "count",
     "description": "Commission, fees and responsibilities. Applies from its effective date; history is never recalculated.",
     "levels": [("Commercial approval", "finance.commission.approve", 0, 48)]},
    {"key": "finance.period_reopen", "name": "Reopen a closed period", "module": "finance", "approval_type": "general",
     "submit_permission": "finance.period.close", "requires_amount": False, "amount_unit": "count",
     "description": "Reopening closed books needs a reason and a second person.", "levels": [("Controller approval", "finance.period.reopen", 0, 24)]},
]


def install(organization) -> None:
    from apps.access.models import Permission, Role, RoleApprovalLimit, RolePermission
    from apps.access.defaults import expand
    from apps.organization.models import Department
    from apps.workflows.models import ApprovalLevel, ApprovalPolicy

    from . import models as m

    entity, _ = m.FinancialEntity.objects.get_or_create(organization=organization, code="CLICK-IN", defaults={
        "name": "Click (India)", "legal_name": "Click Technologies Private Limited", "base_currency": organization.base_currency,
        "is_default": True, "fiscal_year_start_month": 4})
    accounts = {a.code: a for a in m.Account.objects.filter(entity=entity)}
    for code, name, typ, key, parent in CHART:
        if code not in accounts:
            accounts[code] = m.Account.objects.create(entity=entity, code=code, name=name, type=typ, system_key=key,
                                                      parent=accounts.get(parent) if parent else None, is_postable=bool(key))
    by_key = {a.system_key: a for a in accounts.values() if a.system_key}
    for code, name, kind, rate, out_k, in_k in TAX_RULES:
        m.TaxRule.objects.get_or_create(organization=organization, code=code, version=1, defaults={
            "name": name, "kind": kind, "rate": rate, "effective_from": date(2017, 7, 1), "output_account": by_key.get(out_k),
            "input_account": by_key.get(in_k) if in_k else None})
    for method, label, fee, days in PAYMENT_METHODS:
        m.PaymentMethodConfig.objects.get_or_create(organization=organization, method=method, defaults={"label": label, "fee_pct": fee,
                                                                                                         "settlement_days": days})
    if not m.PartnerAgreement.objects.filter(organization=organization, partner__isnull=True).exists():
        m.PartnerAgreement.objects.create(organization=organization, code="AGR-DEFAULT", commercial_model="marketplace", commission_pct=D("15"),
                                          platform_fee_pct=D("0"), fixed_fee=D("0"), tax_on_fees_pct=D("18"), effective_from=date(2025, 1, 1),
                                          status="active", notes="Default marketplace terms for partners without their own agreement.")
    for key, name, acc, limit, receipt, mileage, note in EXPENSE_CATEGORIES:
        m.ExpenseCategory.objects.get_or_create(organization=organization, key=key, defaults={
            "name": name, "account": by_key[acc], "limit_per_claim": limit, "receipt_required_above": receipt, "mileage_rate": mileage, "policy_note": note})
    for code, name, dept_code in COST_CENTERS:
        cc, _ = m.CostCenter.objects.get_or_create(organization=organization, code=code, defaults={"name": name})
        if cc.department_id is None:
            dept = Department.objects.filter(organization=organization, code=dept_code).first()
            if dept:
                cc.department = dept
                cc.save(update_fields=["department", "updated_at"])
    if not m.BankAccount.objects.filter(entity=entity).exists():
        m.BankAccount.objects.create(entity=entity, name="Operating account", bank_name="(set the bank)", gl_account=by_key["bank"])
        m.BankAccount.objects.create(entity=entity, name="Payment gateway balance", bank_name="Payment gateway", account_type="gateway",
                                     gl_account=by_key["gateway_clearing"], is_restricted=True)
    # Roles & policies (same template mechanism as the access defaults)
    perms = {p.code: p for p in Permission.objects.all()}
    for spec in roles():
        role, _ = Role.objects.update_or_create(organization=organization, key=spec["key"], defaults={
            "name": spec["name"], "description": spec["description"], "priority": spec["priority"], "audience": spec["audience"],
            "requires_mfa": spec.get("requires_mfa", False), "home_widgets": spec.get("widgets", []), "is_system": True, "is_active": True,
            "home_config": {"pulse": spec.get("pulse", [])}})
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
                ApprovalLevel.objects.create(policy=pol, sequence=i, name=name, approver_permission=perm, min_amount=D(min_amount),
                                             escalate_after_hours=hours,
                                             enforce_limit=spec["approval_type"] != "general" and spec.get("amount_unit", "currency") == "currency")
