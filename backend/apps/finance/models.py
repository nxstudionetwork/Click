"""
Click Business OS — Module 4: Finance. The financial source of truth, and only that.

    Customer / Partner / Order / Product / Employee / Identity      → owned by their own apps (referenced, never copied)
    Financial consequence (ledger, payables, receivables, tax …)    → owned here

Core rules built into the data model
- Click is a platform / mediator: a customer payment is NOT Click revenue. Every platform payment gets a
  TransactionBreakdown (gross → partner share / Click commission / fees / tax / gateway cost / discount funding) using
  the PartnerAgreement in force at the time, snapshotted so history never changes when agreements do.
- Double entry: every financial consequence is a balanced Journal; posted journals are immutable. Corrections are
  reversals, credit / debit notes or corrective journals — never edits.
- Periods: closed / locked periods refuse postings; reopening needs a reason and an approval.
- Multi-entity and multi-currency ready: every journal belongs to a FinancialEntity; lines carry base and original
  currency amounts with the rate used.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel
from apps.organization.commercial import CommercialModel
from apps.organization.models import Department, Organization, OrgUnit

ZERO = Decimal("0")
MONEY = {"max_digits": 16, "decimal_places": 2, "default": ZERO}


class NumberSeries(BaseModel):
    """Controlled, gap-free document numbering (JV-000001, INV-000001, PO-000001 …), configurable per organization."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="number_series")
    key = models.CharField(max_length=40)
    prefix = models.CharField(max_length=12)
    next_value = models.PositiveIntegerField(default=1)
    padding = models.PositiveSmallIntegerField(default=6)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "key"], name="number_series_unique")]


class FinancialEntity(BaseModel):
    """A legal / accounting entity. Click is one today; subsidiaries and regional entities slot in without redesign."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="financial_entities")
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=150)
    legal_name = models.CharField(max_length=200, blank=True)
    base_currency = models.CharField(max_length=3, default="INR")
    country = models.CharField(max_length=2, default="IN")
    tax_registration = models.CharField(max_length=40, blank=True, help_text="e.g. GSTIN (shown masked).")
    fiscal_year_start_month = models.PositiveSmallIntegerField(default=4)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="fin_entity_code_unique")]

    def __str__(self):
        return self.name


class Account(BaseModel):
    class Type(models.TextChoices):
        ASSET = "asset", "Asset"
        LIABILITY = "liability", "Liability"
        EQUITY = "equity", "Equity"
        REVENUE = "revenue", "Revenue"
        COST_OF_REVENUE = "cost_of_revenue", "Cost of revenue"
        EXPENSE = "expense", "Operating expense"
        OTHER_INCOME = "other_income", "Other income"
        OTHER_EXPENSE = "other_expense", "Other expense"

    DEBIT_NORMAL = ("asset", "cost_of_revenue", "expense", "other_expense")

    entity = models.ForeignKey(FinancialEntity, on_delete=models.CASCADE, related_name="accounts")
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=150)
    type = models.CharField(max_length=16, choices=Type.choices)
    parent = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="children")
    system_key = models.CharField(max_length=40, blank=True, help_text="Stable mapping used by automatic postings (e.g. partner_payable).")
    is_postable = models.BooleanField(default=True, help_text="Header accounts group others and take no postings.")
    is_active = models.BooleanField(default=True)
    description = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["code"]
        constraints = [models.UniqueConstraint(fields=["entity", "code"], name="fin_account_code_unique"),
                       models.UniqueConstraint(fields=["entity", "system_key"], condition=~Q(system_key=""), name="fin_account_system_key_unique")]

    def __str__(self):
        return f"{self.code} {self.name}"

    @property
    def debit_normal(self) -> bool:
        return self.type in self.DEBIT_NORMAL


class CostCenter(BaseModel):
    class Kind(models.TextChoices):
        COST_CENTER = "cost_center", "Cost center"
        PROFIT_CENTER = "profit_center", "Profit center"
        PROJECT = "project", "Project"
        CAMPAIGN = "campaign", "Campaign"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="cost_centers")
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=14, choices=Kind.choices, default=Kind.COST_CENTER)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="fin_cost_center_unique")]


class FinancialPeriod(BaseModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        SOFT_CLOSED = "soft_closed", "Soft closed (adjustments only)"
        CLOSED = "closed", "Closed"
        LOCKED = "locked", "Locked"

    entity = models.ForeignKey(FinancialEntity, on_delete=models.CASCADE, related_name="periods")
    name = models.CharField(max_length=20)
    start = models.DateField()
    end = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    closed_at = models.DateTimeField(null=True, blank=True)
    reopened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    reopened_at = models.DateTimeField(null=True, blank=True)
    reopen_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["start"]
        constraints = [models.UniqueConstraint(fields=["entity", "start"], name="fin_period_unique")]

    def __str__(self):
        return self.name


class ExchangeRate(BaseModel):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    currency = models.CharField(max_length=3)
    base_currency = models.CharField(max_length=3, default="INR")
    rate = models.DecimalField(max_digits=18, decimal_places=8, help_text="1 unit of currency = rate × base currency.")
    on_date = models.DateField()
    source = models.CharField(max_length=60, default="manual")
    set_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-on_date"]
        constraints = [models.UniqueConstraint(fields=["organization", "currency", "base_currency", "on_date"], name="fx_rate_unique")]


class TaxRule(BaseModel):
    """Configurable, versioned tax rates. Rates here are starting templates — review with a qualified tax professional."""

    class Kind(models.TextChoices):
        GST = "gst", "GST"
        CGST = "cgst", "CGST"
        SGST = "sgst", "SGST"
        IGST = "igst", "IGST"
        UTGST = "utgst", "UTGST"
        TDS = "tds", "TDS"
        TCS = "tcs", "TCS"
        OTHER = "other", "Other"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="tax_rules")
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=8, choices=Kind.choices)
    rate = models.DecimalField(max_digits=7, decimal_places=4)
    jurisdiction = models.CharField(max_length=40, default="IN")
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    output_account = models.ForeignKey(Account, on_delete=models.PROTECT, null=True, blank=True, related_name="+", help_text="Tax payable (sales).")
    input_account = models.ForeignKey(Account, on_delete=models.PROTECT, null=True, blank=True, related_name="+", help_text="Input credit (purchases).")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code", "-version"]
        constraints = [models.UniqueConstraint(fields=["organization", "code", "version"], name="tax_rule_version_unique")]


class PaymentMethodConfig(BaseModel):
    """How each customer payment method settles: gateway cost and settlement delay (no credentials stored here)."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    method = models.CharField(max_length=30)
    label = models.CharField(max_length=60)
    gateway = models.CharField(max_length=40, default="internal")
    fee_pct = models.DecimalField(max_digits=6, decimal_places=3, default=ZERO)
    fee_fixed = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    settlement_days = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "method"], name="pay_method_cfg_unique")]


# =====================================================================================================================
# Ledger
# =====================================================================================================================
class Journal(BaseModel):
    class Kind(models.TextChoices):
        MANUAL = "manual", "Manual"
        SYSTEM = "system", "System-generated"
        ADJUSTING = "adjusting", "Adjusting entry"
        ACCRUAL = "accrual", "Accrual"
        REVERSAL = "reversal", "Reversal"
        CLOSING = "closing", "Closing entry"
        RECURRING = "recurring", "Recurring"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending_approval", "Waiting for approval"
        POSTED = "posted", "Posted"
        REVERSED = "reversed", "Reversed"
        REJECTED = "rejected", "Rejected"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    entity = models.ForeignKey(FinancialEntity, on_delete=models.PROTECT, related_name="journals")
    number = models.CharField(max_length=20, blank=True)
    date = models.DateField()
    period = models.ForeignKey(FinancialPeriod, on_delete=models.PROTECT, null=True, related_name="journals")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.MANUAL)
    status = models.CharField(max_length=18, choices=Status.choices, default=Status.DRAFT)
    description = models.CharField(max_length=300)
    reference = models.CharField(max_length=80, blank=True)
    source_module = models.CharField(max_length=30, blank=True)
    source_type = models.CharField(max_length=40, blank=True)
    source_id = models.CharField(max_length=64, blank=True)
    currency = models.CharField(max_length=3, default="INR")
    fx_rate = models.DecimalField(max_digits=18, decimal_places=8, default=Decimal("1"))
    total = models.DecimalField(**MONEY)
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    posted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    posted_at = models.DateTimeField(null=True, blank=True)
    approval = models.ForeignKey("workflows.ApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    reversal_of = models.OneToOneField("self", on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_by")
    reversal_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [models.Index(fields=["entity", "date"], name="fin_journal_entity_date_idx"),
                   models.Index(fields=["source_type", "source_id"], name="fin_journal_source_idx")]
        constraints = [models.UniqueConstraint(fields=["entity", "source_type", "source_id", "kind"],
                                               condition=~Q(source_id="") & Q(kind__in=["system", "reversal"]), name="fin_journal_source_once")]

    def __str__(self):
        return self.number or "draft journal"


class JournalLine(BaseModel):
    journal = models.ForeignKey(Journal, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="lines")
    debit = models.DecimalField(**MONEY)
    credit = models.DecimalField(**MONEY)
    currency = models.CharField(max_length=3, default="INR")
    amount_txn = models.DecimalField(**MONEY, help_text="Signed amount in the transaction currency (debit +, credit −).")
    description = models.CharField(max_length=300, blank=True)
    cost_center = models.ForeignKey(CostCenter, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    partner = models.ForeignKey("partners.Partner", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    party_type = models.CharField(max_length=12, blank=True)
    party_id = models.CharField(max_length=64, blank=True)
    party_name = models.CharField(max_length=160, blank=True)
    tax_rule = models.ForeignKey(TaxRule, on_delete=models.PROTECT, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-debit", "credit"]
        indexes = [models.Index(fields=["account"], name="fin_line_account_idx"), models.Index(fields=["partner"], name="fin_line_partner_idx")]
        constraints = [models.CheckConstraint(condition=Q(debit__gte=0) & Q(credit__gte=0), name="fin_line_non_negative"),
                       models.CheckConstraint(condition=~(Q(debit__gt=0) & Q(credit__gt=0)), name="fin_line_one_side")]


# =====================================================================================================================
# Platform finance: agreements, breakdowns, settlements
# =====================================================================================================================
class PartnerAgreement(BaseModel):
    """Commercial terms with a partner (or the default for everyone). Never edited once active: a change is a new
    version, approved, effective from a date. Historical transactions keep the snapshot they were calculated with."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending_approval", "Waiting for approval"
        ACTIVE = "active", "Active"
        SUPERSEDED = "superseded", "Superseded"
        REJECTED = "rejected", "Rejected"

    class Responsibility(models.TextChoices):
        PARTNER = "partner", "Partner"
        CLICK = "click", "Click"
        SHARED = "shared", "Shared"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    code = models.CharField(max_length=20, blank=True)
    partner = models.ForeignKey("partners.Partner", on_delete=models.PROTECT, null=True, blank=True, related_name="agreements",
                                help_text="Blank = the default agreement for partners without their own.")
    commercial_model = models.CharField(max_length=30, choices=CommercialModel.choices, default=CommercialModel.MARKETPLACE)
    commission_pct = models.DecimalField(max_digits=6, decimal_places=3, default=ZERO)
    platform_fee_pct = models.DecimalField(max_digits=6, decimal_places=3, default=ZERO)
    fixed_fee = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO, help_text="Per transaction.")
    tax_on_fees_pct = models.DecimalField(max_digits=6, decimal_places=3, default=ZERO, help_text="Tax Click charges on its fees.")
    delivery_fee_to = models.CharField(max_length=8, choices=[("click", "Click"), ("partner", "Partner")], default="click")
    promo_funding = models.CharField(max_length=8, choices=Responsibility.choices, default=Responsibility.PARTNER)
    promo_click_share_pct = models.DecimalField(max_digits=6, decimal_places=3, default=ZERO)
    refund_responsibility = models.CharField(max_length=8, choices=Responsibility.choices, default=Responsibility.PARTNER)
    refund_click_share_pct = models.DecimalField(max_digits=6, decimal_places=3, default=ZERO)
    settlement_frequency = models.CharField(max_length=10, choices=[("daily", "Daily"), ("weekly", "Weekly"), ("biweekly", "Every two weeks"),
                                                                    ("monthly", "Monthly")], default="weekly")
    payment_terms_days = models.PositiveSmallIntegerField(default=2)
    minimum_guarantee = models.DecimalField(**MONEY)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=18, choices=Status.choices, default=Status.DRAFT)
    notes = models.CharField(max_length=500, blank=True)
    approval = models.ForeignKey("workflows.ApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-effective_from", "-version"]

    def snapshot(self) -> dict:
        return {k: str(getattr(self, k)) for k in ("code", "commercial_model", "commission_pct", "platform_fee_pct", "fixed_fee", "tax_on_fees_pct",
                                                   "delivery_fee_to", "promo_funding", "promo_click_share_pct", "refund_responsibility",
                                                   "refund_click_share_pct", "version")} | {"id": str(self.pk)}


class TransactionBreakdown(BaseModel):
    """The financial anatomy of one platform payment (or its refund). Never recalculated after posting."""

    class Kind(models.TextChoices):
        SALE = "sale", "Sale"
        REFUND = "refund", "Refund"
        STORED_VALUE = "stored_value", "Stored value (wallet / gift card)"

    class SettlementStatus(models.TextChoices):
        UNSETTLED = "unsettled", "Not settled"
        IN_BATCH = "in_batch", "In a settlement batch"
        SETTLED = "settled", "Settled"
        NOT_APPLICABLE = "na", "No partner payout"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    entity = models.ForeignKey(FinancialEntity, on_delete=models.PROTECT, related_name="+")
    kind = models.CharField(max_length=14, choices=Kind.choices)
    payment = models.ForeignKey("payments.Payment", on_delete=models.PROTECT, related_name="breakdowns")
    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    partner = models.ForeignKey("partners.Partner", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    store_name = models.CharField(max_length=160, blank=True)
    commercial_model = models.CharField(max_length=30, choices=CommercialModel.choices)
    agreement = models.ForeignKey(PartnerAgreement, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    agreement_snapshot = models.JSONField(default=dict)
    method = models.CharField(max_length=30, blank=True)
    currency = models.CharField(max_length=3, default="INR")
    gross = models.DecimalField(**MONEY, help_text="What the customer paid (gross transaction value).")
    merchandise = models.DecimalField(**MONEY)
    discount_partner = models.DecimalField(**MONEY)
    discount_click = models.DecimalField(**MONEY)
    tax_collected = models.DecimalField(**MONEY)
    delivery_fee = models.DecimalField(**MONEY)
    commission = models.DecimalField(**MONEY)
    platform_fee = models.DecimalField(**MONEY)
    fee_tax = models.DecimalField(**MONEY)
    gateway_fee = models.DecimalField(**MONEY)
    partner_share = models.DecimalField(**MONEY)
    click_revenue = models.DecimalField(**MONEY)
    click_net = models.DecimalField(**MONEY, help_text="Click revenue − gateway cost − Click-funded discount/refund cost.")
    occurred_at = models.DateTimeField()
    journal = models.ForeignKey(Journal, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    settlement_status = models.CharField(max_length=10, choices=SettlementStatus.choices, default=SettlementStatus.UNSETTLED)
    settlement_line = models.ForeignKey("SettlementLine", on_delete=models.SET_NULL, null=True, blank=True, related_name="breakdowns")
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [models.Index(fields=["partner", "settlement_status"], name="fin_bd_partner_settle_idx"),
                   models.Index(fields=["occurred_at"], name="fin_bd_occurred_idx")]
        constraints = [models.UniqueConstraint(fields=["payment", "kind"], name="fin_breakdown_once")]


class PartnerAdjustment(BaseModel):
    class Kind(models.TextChoices):
        PENALTY = "penalty", "Penalty"
        ADVERTISING = "advertising", "Advertising charge"
        DEDUCTION = "deduction", "Other deduction"
        CORRECTION = "correction", "Correction"
        INCENTIVE = "incentive", "Incentive / credit"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    partner = models.ForeignKey("partners.Partner", on_delete=models.PROTECT, related_name="+")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2, help_text="Positive = Click owes the partner more; negative = deduction.")
    reason = models.CharField(max_length=300)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    settlement_line = models.ForeignKey("SettlementLine", on_delete=models.SET_NULL, null=True, blank=True, related_name="adjustment_items")
    journal = models.ForeignKey(Journal, on_delete=models.PROTECT, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-created_at"]


class SettlementBatch(BaseModel):
    class Status(models.TextChoices):
        CALCULATED = "calculated", "Calculated"
        PENDING = "pending_approval", "Waiting for approval"
        APPROVED = "approved", "Approved"
        PAID = "paid", "Paid"
        RECONCILED = "reconciled", "Reconciled"
        EXCEPTION = "exception", "Exception"
        CANCELLED = "cancelled", "Cancelled"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    entity = models.ForeignKey(FinancialEntity, on_delete=models.PROTECT, related_name="+")
    number = models.CharField(max_length=20)
    period_to = models.DateField()
    status = models.CharField(max_length=18, choices=Status.choices, default=Status.CALCULATED)
    partners = models.PositiveIntegerField(default=0)
    gross_partner_amount = models.DecimalField(**MONEY)
    deductions = models.DecimalField(**MONEY)
    refund_adjustments = models.DecimalField(**MONEY)
    net_payable = models.DecimalField(**MONEY)
    approval = models.ForeignKey("workflows.ApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class SettlementLine(BaseModel):
    batch = models.ForeignKey(SettlementBatch, on_delete=models.CASCADE, related_name="lines")
    partner = models.ForeignKey("partners.Partner", on_delete=models.PROTECT, related_name="+")
    transactions = models.PositiveIntegerField(default=0)
    gross = models.DecimalField(**MONEY)
    commission = models.DecimalField(**MONEY)
    platform_fee = models.DecimalField(**MONEY)
    fee_tax = models.DecimalField(**MONEY)
    refunds = models.DecimalField(**MONEY)
    adjustments = models.DecimalField(**MONEY)
    partner_share = models.DecimalField(**MONEY)
    net_payable = models.DecimalField(**MONEY)
    status = models.CharField(max_length=12, default="pending")
    payment = models.ForeignKey("FinancePayment", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-net_payable"]


# =====================================================================================================================
# Receivables, payables, payments
# =====================================================================================================================
class Invoice(BaseModel):
    """AR invoices, AP vendor bills and credit / debit notes. Issued documents are never edited — notes correct them."""

    class Kind(models.TextChoices):
        CUSTOMER = "customer_invoice", "Customer invoice"
        PARTNER = "partner_invoice", "Partner invoice"
        VENDOR_BILL = "vendor_bill", "Vendor bill"
        CREDIT_NOTE = "credit_note", "Credit note"
        DEBIT_NOTE = "debit_note", "Debit note"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending_approval", "Waiting for approval"
        ISSUED = "issued", "Issued / approved"
        PARTIAL = "partially_paid", "Partially paid"
        PAID = "paid", "Paid"
        VOID = "void", "Void"
        DISPUTED = "disputed", "Disputed"
        REJECTED = "rejected", "Rejected"

    class RevenueType(models.TextChoices):
        COMMISSION = "platform_commission", "Platform commission"
        SERVICE = "service_fee", "Service fee"
        SUBSCRIPTION = "subscription", "Subscription"
        ADVERTISING = "advertising", "Advertising"
        SPONSORED = "sponsored", "Sponsored placement"
        BOOKING = "booking_fee", "Booking fee"
        MEMBERSHIP = "membership", "Membership"
        OTHER = "other", "Other approved revenue"

    class Match(models.TextChoices):
        NOT_REQUIRED = "not_required", "No match required"
        MATCHED = "matched", "Matched"
        EXCEPTION = "exception", "Match exception"
        OVERRIDDEN = "overridden", "Exception approved"
        PENDING = "pending", "Not checked yet"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    entity = models.ForeignKey(FinancialEntity, on_delete=models.PROTECT, related_name="+")
    number = models.CharField(max_length=24, blank=True)
    kind = models.CharField(max_length=18, choices=Kind.choices)
    party_type = models.CharField(max_length=12, choices=[("customer", "Customer"), ("partner", "Partner"), ("supplier", "Supplier"),
                                                          ("employee", "Employee"), ("other", "Other")])
    party_id = models.CharField(max_length=64, blank=True)
    party_name = models.CharField(max_length=160)
    partner = models.ForeignKey("partners.Partner", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    supplier_invoice_number = models.CharField(max_length=60, blank=True)
    revenue_type = models.CharField(max_length=20, choices=RevenueType.choices, blank=True)
    issue_date = models.DateField()
    due_date = models.DateField()
    currency = models.CharField(max_length=3, default="INR")
    fx_rate = models.DecimalField(max_digits=18, decimal_places=8, default=Decimal("1"))
    subtotal = models.DecimalField(**MONEY)
    tax_total = models.DecimalField(**MONEY)
    total = models.DecimalField(**MONEY)
    amount_paid = models.DecimalField(**MONEY)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    original = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="notes")
    reason = models.CharField(max_length=300, blank=True)
    terms = models.CharField(max_length=300, blank=True)
    source_module = models.CharField(max_length=30, blank=True)
    source_type = models.CharField(max_length=40, blank=True)
    source_id = models.CharField(max_length=64, blank=True)
    source_label = models.CharField(max_length=60, blank=True)
    match_status = models.CharField(max_length=14, choices=Match.choices, default=Match.NOT_REQUIRED)
    match_detail = models.JSONField(default=dict, blank=True)
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    cost_center = models.ForeignKey(CostCenter, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    approval = models.ForeignKey("workflows.ApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    journal = models.ForeignKey(Journal, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        ordering = ["-issue_date", "-created_at"]
        indexes = [models.Index(fields=["kind", "status"], name="fin_invoice_kind_status_idx")]

    @property
    def outstanding(self) -> Decimal:
        return (self.total - self.amount_paid) if self.status not in ("void", "draft", "rejected") else ZERO

    @property
    def is_payable(self) -> bool:
        return self.kind in (self.Kind.VENDOR_BILL, self.Kind.DEBIT_NOTE) and self.party_type in ("supplier", "employee", "other")


class InvoiceLine(BaseModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    description = models.CharField(max_length=300)
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("1"))
    unit_price = models.DecimalField(max_digits=16, decimal_places=2)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    tax_rule = models.ForeignKey(TaxRule, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    tax_rate = models.DecimalField(max_digits=7, decimal_places=4, default=ZERO)
    tax_amount = models.DecimalField(**MONEY)
    line_total = models.DecimalField(**MONEY)
    source_line_id = models.CharField(max_length=64, blank=True, help_text="e.g. the purchase-order line this bill line matches.")


class PaymentRun(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending_approval", "Waiting for approval"
        APPROVED = "approved", "Approved"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    number = models.CharField(max_length=20)
    kind = models.CharField(max_length=16, choices=[("vendor", "Vendor payments"), ("reimbursement", "Employee reimbursements"),
                                                    ("mixed", "Mixed payables")], default="mixed")
    status = models.CharField(max_length=18, choices=Status.choices, default=Status.DRAFT)
    total = models.DecimalField(**MONEY)
    bank_account = models.ForeignKey("BankAccount", on_delete=models.PROTECT, null=True, related_name="+")
    approval = models.ForeignKey("workflows.ApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    executed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-created_at"]


class FinancePayment(BaseModel):
    """Money Click receives against receivables or pays out (bills, settlements, reimbursements). Customer checkout
    payments stay in apps.payments; this is the finance-side cash record."""

    class Direction(models.TextChoices):
        IN = "in", "Received"
        OUT = "out", "Paid out"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending_approval", "Waiting for approval"
        APPROVED = "approved", "Approved — ready to pay"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        VOID = "void", "Void"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    entity = models.ForeignKey(FinancialEntity, on_delete=models.PROTECT, related_name="+")
    number = models.CharField(max_length=20)
    direction = models.CharField(max_length=3, choices=Direction.choices)
    purpose = models.CharField(max_length=16, choices=[("invoice", "Invoice / bill"), ("settlement", "Partner settlement"),
                                                       ("reimbursement", "Expense reimbursement"), ("other", "Other")], default="invoice")
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, null=True, blank=True, related_name="payments")
    settlement_line = models.ForeignKey(SettlementLine, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    expense_claim = models.ForeignKey("ExpenseClaim", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    run = models.ForeignKey(PaymentRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments")
    party_name = models.CharField(max_length=160)
    partner = models.ForeignKey("partners.Partner", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    date = models.DateField()
    method = models.CharField(max_length=20, default="bank_transfer")
    bank_account = models.ForeignKey("BankAccount", on_delete=models.PROTECT, null=True, blank=True, related_name="payments")
    reference = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=18, choices=Status.choices, default=Status.DRAFT)
    approval = models.ForeignKey("workflows.ApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    journal = models.ForeignKey(Journal, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    reconciled = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    executed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    failure_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-date", "-created_at"]


# =====================================================================================================================
# Expenses, budgets
# =====================================================================================================================
class ExpenseCategory(BaseModel):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    key = models.SlugField(max_length=40)
    name = models.CharField(max_length=80)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="+")
    limit_per_claim = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    receipt_required_above = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    mileage_rate = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text="Per km, for mileage claims.")
    policy_note = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["organization", "key"], name="fin_expense_cat_unique")]


class ExpenseClaim(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Waiting for approval"
        APPROVED = "approved", "Approved — awaiting payment"
        REJECTED = "rejected", "Rejected"
        PAID = "paid", "Reimbursed"
        CANCELLED = "cancelled", "Withdrawn"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    number = models.CharField(max_length=20)
    claimant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="expense_claims")
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name="+")
    date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    distance_km = models.DecimalField(max_digits=8, decimal_places=1, null=True, blank=True)
    purpose = models.CharField(max_length=300)
    merchant = models.CharField(max_length=120, blank=True)
    cost_center = models.ForeignKey(CostCenter, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    has_receipt = models.BooleanField(default=False)
    policy_flags = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    approval = models.ForeignKey("workflows.ApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    journal = models.ForeignKey(Journal, on_delete=models.PROTECT, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-date", "-created_at"]


class Budget(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending_approval", "Waiting for approval"
        ACTIVE = "active", "Approved & active"
        REJECTED = "rejected", "Rejected"
        CLOSED = "closed", "Closed"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    entity = models.ForeignKey(FinancialEntity, on_delete=models.PROTECT, related_name="+")
    number = models.CharField(max_length=20)
    name = models.CharField(max_length=150)
    fiscal_year = models.PositiveIntegerField(help_text="Year the fiscal year starts in (FY 2026-27 = 2026).")
    department = models.ForeignKey(Department, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    cost_center = models.ForeignKey(CostCenter, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    category = models.CharField(max_length=40, blank=True, help_text="e.g. technology, marketing (matches procurement categories).")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    status = models.CharField(max_length=18, choices=Status.choices, default=Status.DRAFT)
    approval = models.ForeignKey("workflows.ApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    notes = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-fiscal_year", "name"]

    @property
    def amount(self) -> Decimal:
        return sum((ln.amount for ln in self.lines.all()), ZERO)


class BudgetLine(BaseModel):
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
                                help_text="Blank = any expense account within the budget's dimensions.")
    month = models.PositiveSmallIntegerField(null=True, blank=True, help_text="1–12 calendar month; blank = whole year.")
    amount = models.DecimalField(max_digits=16, decimal_places=2)


class BudgetCommitment(BaseModel):
    """Money reserved against a budget before it is spent (e.g. an approved purchase request / PO)."""

    class Status(models.TextChoices):
        RESERVED = "reserved", "Reserved"
        PARTIAL = "partial", "Partly consumed"
        CONSUMED = "consumed", "Consumed"
        RELEASED = "released", "Released"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    budget = models.ForeignKey(Budget, on_delete=models.PROTECT, related_name="commitments")
    source_module = models.CharField(max_length=30)
    source_type = models.CharField(max_length=40)
    source_id = models.CharField(max_length=64)
    source_label = models.CharField(max_length=80)
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    consumed = models.DecimalField(**MONEY)
    released = models.DecimalField(**MONEY)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RESERVED)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["source_type", "source_id"], name="fin_commitment_source_once")]

    @property
    def open_amount(self) -> Decimal:
        return max(ZERO, self.amount - self.consumed - self.released)


# =====================================================================================================================
# Banking, reconciliation, assets, disputes, close
# =====================================================================================================================
class BankAccount(BaseModel):
    """Account number is encrypted at rest and shown masked; changes need finance.bank.manage and are audited."""

    entity = models.ForeignKey(FinancialEntity, on_delete=models.PROTECT, related_name="bank_accounts")
    name = models.CharField(max_length=120)
    bank_name = models.CharField(max_length=120)
    account_type = models.CharField(max_length=16, choices=[("current", "Current"), ("savings", "Savings"), ("gateway", "Payment gateway balance"),
                                                            ("cash", "Cash")], default="current")
    account_number_enc = models.TextField(blank=True)
    last4 = models.CharField(max_length=4, blank=True)
    ifsc = models.CharField(max_length=11, blank=True)
    currency = models.CharField(max_length=3, default="INR")
    gl_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="+")
    is_restricted = models.BooleanField(default=False, help_text="Funds not freely available (e.g. escrow, pending gateway).")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]


class BankTransaction(BaseModel):
    class Status(models.TextChoices):
        UNMATCHED = "unmatched", "Unmatched"
        MATCHED = "matched", "Matched"
        EXCLUDED = "excluded", "Excluded"

    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name="transactions")
    date = models.DateField()
    description = models.CharField(max_length=300)
    amount = models.DecimalField(max_digits=16, decimal_places=2, help_text="+ money in, − money out.")
    reference = models.CharField(max_length=120, blank=True)
    import_batch = models.CharField(max_length=40, blank=True)
    fingerprint = models.CharField(max_length=64)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.UNMATCHED)
    matched_payment = models.ForeignKey(FinancePayment, on_delete=models.SET_NULL, null=True, blank=True, related_name="bank_matches")
    matched_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    match_method = models.CharField(max_length=12, blank=True)
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-date"]
        constraints = [models.UniqueConstraint(fields=["bank_account", "fingerprint"], name="fin_bank_txn_once")]


class ReconciliationException(BaseModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"
        IGNORED = "ignored", "Accepted / no action"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=30)
    area = models.CharField(max_length=12, choices=[("gateway", "Payment gateway"), ("bank", "Bank"), ("settlement", "Partner settlement"),
                                                    ("ledger", "Ledger"), ("tax", "Tax")])
    source_type = models.CharField(max_length=40)
    source_id = models.CharField(max_length=64)
    amount = models.DecimalField(**MONEY)
    description = models.CharField(max_length=300)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    resolution = models.CharField(max_length=500, blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["status", "-created_at"]
        constraints = [models.UniqueConstraint(fields=["kind", "source_type", "source_id"], name="fin_recon_exception_once")]


class FixedAsset(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Awaiting capitalisation"
        ACTIVE = "active", "In use"
        DISPOSED = "disposed", "Disposed"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    entity = models.ForeignKey(FinancialEntity, on_delete=models.PROTECT, related_name="+")
    number = models.CharField(max_length=20)
    name = models.CharField(max_length=160)
    category = models.CharField(max_length=20, choices=[("computers", "Computers"), ("servers", "Servers"), ("office_equipment", "Office equipment"),
                                                        ("vehicles", "Vehicles"), ("furniture", "Furniture"), ("infrastructure", "Infrastructure"),
                                                        ("other", "Other capital asset")])
    acquisition_date = models.DateField()
    cost = models.DecimalField(max_digits=16, decimal_places=2)
    salvage_value = models.DecimalField(**MONEY)
    useful_life_months = models.PositiveIntegerField(default=36)
    accumulated_depreciation = models.DecimalField(**MONEY)
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    cost_center = models.ForeignKey(CostCenter, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    custodian = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    serial_number = models.CharField(max_length=80, blank=True)
    source_module = models.CharField(max_length=30, blank=True)
    source_type = models.CharField(max_length=40, blank=True)
    source_id = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    capitalised_journal = models.ForeignKey(Journal, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    disposed_on = models.DateField(null=True, blank=True)
    disposal_amount = models.DecimalField(**MONEY)

    class Meta:
        ordering = ["-acquisition_date"]

    @property
    def book_value(self) -> Decimal:
        return self.cost - self.accumulated_depreciation


class DepreciationEntry(BaseModel):
    asset = models.ForeignKey(FixedAsset, on_delete=models.CASCADE, related_name="depreciation")
    period = models.ForeignKey(FinancialPeriod, on_delete=models.PROTECT, related_name="+")
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    journal = models.ForeignKey(Journal, on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["asset", "period"], name="fin_depreciation_once")]


class FinancialDispute(BaseModel):
    class Kind(models.TextChoices):
        PAYMENT = "payment", "Customer payment dispute"
        CHARGEBACK = "chargeback", "Chargeback"
        SETTLEMENT = "settlement", "Partner settlement dispute"
        VENDOR = "vendor", "Vendor billing dispute"
        REFUND = "refund", "Refund dispute"
        COMMISSION = "commission", "Commission dispute"
        TAX = "tax", "Tax dispute"
        INVOICE = "invoice", "Invoice dispute"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        INVESTIGATING = "investigating", "Investigating"
        RESOLVED = "resolved", "Resolved"
        REJECTED = "rejected", "Rejected"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    number = models.CharField(max_length=20)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    party_type = models.CharField(max_length=12, default="customer")
    party_name = models.CharField(max_length=160)
    partner = models.ForeignKey("partners.Partner", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    reason = models.CharField(max_length=500)
    source_type = models.CharField(max_length=40, blank=True)
    source_id = models.CharField(max_length=64, blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    deadline = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.OPEN)
    resolution = models.CharField(max_length=500, blank=True)
    financial_impact = models.DecimalField(**MONEY)
    adjustment_journal = models.ForeignKey(Journal, on_delete=models.PROTECT, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["status", "deadline"]


class CloseTask(BaseModel):
    period = models.ForeignKey(FinancialPeriod, on_delete=models.CASCADE, related_name="close_tasks")
    key = models.CharField(max_length=40)
    title = models.CharField(max_length=160)
    sequence = models.PositiveSmallIntegerField(default=0)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    status = models.CharField(max_length=6, choices=[("todo", "To do"), ("done", "Done"), ("na", "Not applicable")], default="todo")
    note = models.CharField(max_length=300, blank=True)
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [models.UniqueConstraint(fields=["period", "key"], name="fin_close_task_once")]
