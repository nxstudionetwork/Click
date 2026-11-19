"""
Click Business OS — Module 5: Procurement. The source of truth for purchasing:

    what needs buying (PurchaseRequest) → who should supply it (Supplier, SourcingEvent, Quotation, Award)
    → what was ordered (PurchaseOrder, versions & amendments) → what was received (GoodsReceipt, ServiceReceipt)
    → whether it followed policy (ProcurementPolicy, ProcurementException, ConflictDeclaration)

Everything else is referenced, never copied: budgets, commitments, bills, AP, payments and assets are Finance
(apps.finance); stock is Inventory (hook only — no stock table here); people are People & HR; access is Identity.
Click procurement (Click buying for itself / its own inventory) is distinct from marketplace transactions and from
partners buying for themselves; a business can be a partner and a supplier, but the relationship is explicit.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from apps.organization.models import Department, Organization, OrgUnit

ZERO = Decimal("0")
MONEY = {"max_digits": 16, "decimal_places": 2, "default": ZERO}
QTY = {"max_digits": 14, "decimal_places": 3, "default": ZERO}


class ProcurementPolicy(BaseModel):
    """Configurable purchasing rules (one row per organization). Amounts are data, not code."""

    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name="procurement_policy")
    rfq_required_above = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("100000"))
    min_quotes = models.PositiveSmallIntegerField(default=3)
    emergency_max_amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("200000"))
    capex_threshold = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("50000"))
    match_tolerance_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("2"))
    match_tolerance_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("500"))
    receiver_not_buyer = models.BooleanField(default=True, help_text="The buyer who raised the PO can't receive it.")
    requester_not_buyer = models.BooleanField(default=False, help_text="The requester can't also raise the PO.")
    split_window_days = models.PositiveSmallIntegerField(default=14)
    concentration_threshold_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("60"))
    block_unapproved_suppliers = models.BooleanField(default=True)
    contract_alert_days = models.JSONField(default=list, help_text="e.g. [90, 60, 30]")
    code_of_conduct = models.TextField(blank=True)
    gift_policy = models.TextField(blank=True)
    anti_bribery_policy = models.TextField(blank=True)


class ProcurementCategory(BaseModel):
    class Expenditure(models.TextChoices):
        OPEX = "opex", "Operating expenditure"
        CAPEX = "capex", "Capital expenditure"

    class Match(models.TextChoices):
        THREE_WAY = "three_way", "Three-way (PO + receipt + invoice)"
        TWO_WAY = "two_way", "Two-way (PO + invoice, with service confirmation)"
        NONE = "none", "No match"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=120)
    parent = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="children")
    expenditure = models.CharField(max_length=5, choices=Expenditure.choices, default=Expenditure.OPEX)
    finance_account_key = models.CharField(max_length=40, default="general_expense", help_text="Finance system account for bills.")
    budget_category = models.CharField(max_length=40, blank=True, help_text="Matches Finance budget categories.")
    match_mode = models.CharField(max_length=10, choices=Match.choices, default=Match.THREE_WAY)
    is_inventory = models.BooleanField(default=False, help_text="Click-owned stock: receipts update Inventory.")
    is_service = models.BooleanField(default=False)
    rfq_required_above = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True, help_text="Overrides the policy.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="proc_category_code_unique")]

    def __str__(self):
        return self.name


# =====================================================================================================================
# Supplier master
# =====================================================================================================================
class Supplier(BaseModel):
    class Type(models.TextChoices):
        MANUFACTURER = "manufacturer", "Manufacturer"
        DISTRIBUTOR = "distributor", "Distributor"
        WHOLESALER = "wholesaler", "Wholesaler"
        RETAILER = "retailer", "Retailer"
        SERVICE = "service_provider", "Service provider"
        CONSULTANT = "consultant", "Consultant"
        TECHNOLOGY = "technology", "Technology provider"
        CONTRACTOR = "contractor", "Contractor"
        LOGISTICS = "logistics", "Logistics provider"
        PROFESSIONAL = "professional", "Professional firm"
        LOCAL = "local", "Local supplier"
        INTERNATIONAL = "international", "International supplier"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        INVITED = "invited", "Invited"
        REGISTERED = "registered", "Registered — documents pending"
        UNDER_REVIEW = "under_review", "Under review"
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        REJECTED = "rejected", "Rejected"

    class Preference(models.TextChoices):
        PREFERRED = "preferred", "Preferred"
        APPROVED = "approved", "Approved"
        CONDITIONAL = "conditional", "Conditional"
        RESTRICTED = "restricted", "Restricted"
        BLOCKED = "blocked", "Blocked"

    class Relationship(models.TextChoices):
        SUPPLIER = "procurement_supplier", "Procurement supplier"
        PARTNER = "marketplace_partner", "Marketplace partner"
        BOTH = "both", "Both"
        OTHER = "other", "Other"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    code = models.CharField(max_length=20)
    legal_name = models.CharField(max_length=200)
    trading_name = models.CharField(max_length=200, blank=True)
    supplier_type = models.CharField(max_length=16, choices=Type.choices, default=Type.OTHER)
    categories = models.ManyToManyField(ProcurementCategory, blank=True, related_name="suppliers")
    relationship = models.CharField(max_length=22, choices=Relationship.choices, default=Relationship.SUPPLIER)
    partner = models.ForeignKey("partners.Partner", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
                                help_text="Only when the same business is also a Click marketplace partner (no access is granted by this link).")
    contact_name = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    website = models.CharField(max_length=200, blank=True)
    address = models.CharField(max_length=300, blank=True)
    city = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=80, blank=True)
    country = models.CharField(max_length=2, default="IN")
    tax_id = models.CharField(max_length=20, blank=True, help_text="GSTIN; shown masked outside procurement administration.")
    pan = models.CharField(max_length=10, blank=True)
    registration_number = models.CharField(max_length=40, blank=True)
    bank_account_enc = models.TextField(blank=True)
    bank_last4 = models.CharField(max_length=4, blank=True)
    bank_ifsc = models.CharField(max_length=11, blank=True)
    bank_verified = models.BooleanField(default=False)
    bank_changed_at = models.DateTimeField(null=True, blank=True)
    payment_terms_days = models.PositiveSmallIntegerField(default=30)
    currency = models.CharField(max_length=3, default="INR")
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.REGISTERED)
    preference = models.CharField(max_length=12, choices=Preference.choices, default=Preference.CONDITIONAL)
    risk_level = models.CharField(max_length=6, choices=[("low", "Low"), ("medium", "Medium"), ("high", "High")], default="medium")
    risk_factors = models.JSONField(default=dict, blank=True, help_text="{factor: {level, note, by, at}} — flags for review, never verdicts.")
    verification = models.JSONField(default=dict, blank=True, help_text="{check: {status, by, at, note}} for legal name, tax, bank, …")
    restriction_reason = models.CharField(max_length=300, blank=True)
    approval = models.ForeignKey("workflows.ApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        ordering = ["legal_name"]
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="proc_supplier_code_unique")]

    def __str__(self):
        return self.trading_name or self.legal_name

    @property
    def can_be_ordered_from(self) -> bool:
        return self.status == self.Status.ACTIVE and self.preference not in (self.Preference.RESTRICTED, self.Preference.BLOCKED)


class SupplierBankChange(BaseModel):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="bank_changes")
    account_enc = models.TextField()
    last4 = models.CharField(max_length=4)
    ifsc = models.CharField(max_length=11)
    reason = models.CharField(max_length=300)
    evidence = models.CharField(max_length=300, blank=True, help_text="How it was verified (cancelled cheque, call-back to a known number …).")
    status = models.CharField(max_length=10, choices=[("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")], default="pending")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    approval = models.ForeignKey("workflows.ApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-created_at"]


class SupplierStatusEvent(BaseModel):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="status_events")
    from_value = models.CharField(max_length=20)
    to_value = models.CharField(max_length=20)
    field = models.CharField(max_length=12, default="preference")
    reason_category = models.CharField(max_length=20, blank=True)
    note = models.CharField(max_length=300)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        ordering = ["-created_at"]


class ConflictDeclaration(BaseModel):
    class Kind(models.TextChoices):
        SUPPLIER = "supplier_relationship", "Supplier relationship"
        PERSONAL = "personal", "Family / personal relationship"
        FINANCIAL = "financial_interest", "Financial interest"
        EMPLOYMENT = "previous_employment", "Previous employment"
        OTHER = "other", "Other conflict"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    declarant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="procurement_conflicts")
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="conflicts")
    supplier_name = models.CharField(max_length=200, blank=True)
    kind = models.CharField(max_length=24, choices=Kind.choices)
    description = models.TextField()
    status = models.CharField(max_length=10, choices=[("open", "Open"), ("reviewed", "Reviewed"), ("mitigated", "Mitigated")], default="open")
    decision = models.CharField(max_length=300, blank=True, help_text="e.g. excluded from evaluations for this supplier.")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-created_at"]


# =====================================================================================================================
# Requests
# =====================================================================================================================
class PurchaseRequest(BaseModel):
    class Type(models.TextChoices):
        STANDARD = "standard", "Standard purchase"
        URGENT = "urgent", "Urgent purchase"
        EMERGENCY = "emergency", "Emergency purchase"
        RECURRING = "recurring", "Recurring purchase"
        PROJECT = "project", "Project purchase"
        CAPEX = "capex", "Capital expenditure"
        OPEX = "opex", "Operational expenditure"
        SERVICE = "service", "Service purchase"
        SOFTWARE = "software", "Software purchase"
        HARDWARE = "hardware", "Hardware purchase"
        INVENTORY = "inventory", "Inventory purchase"
        CONTRACT = "contract", "Contract purchase"
        SUBSCRIPTION = "subscription", "Subscription purchase"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Waiting for approval"
        CHANGES = "changes_requested", "Changes requested"
        APPROVED = "approved", "Approved — ready for sourcing"
        SOURCING = "sourcing", "Sourcing"
        ORDERED = "ordered", "Ordered"
        CLOSED = "closed", "Closed"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    number = models.CharField(max_length=20)
    title = models.CharField(max_length=200)
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="purchase_requests")
    department = models.ForeignKey(Department, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    cost_center = models.ForeignKey("finance.CostCenter", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    project = models.CharField(max_length=120, blank=True)
    category = models.ForeignKey(ProcurementCategory, on_delete=models.PROTECT, related_name="+")
    request_type = models.CharField(max_length=14, choices=Type.choices, default=Type.STANDARD)
    expenditure = models.CharField(max_length=5, choices=ProcurementCategory.Expenditure.choices, default="opex")
    priority = models.CharField(max_length=8, choices=[("low", "Low"), ("normal", "Normal"), ("high", "High"), ("critical", "Critical")], default="normal")
    required_by = models.DateField(null=True, blank=True)
    justification = models.TextField()
    preferred_supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    estimated_total = models.DecimalField(**MONEY)
    currency = models.CharField(max_length=3, default="INR")
    budget_check = models.JSONField(default=dict, blank=True, help_text="Snapshot of the Finance budget check at submission.")
    budget_id = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=18, choices=Status.choices, default=Status.DRAFT)
    approval = models.ForeignKey("workflows.ApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    is_emergency = models.BooleanField(default=False)
    emergency_reason = models.CharField(max_length=500, blank=True)
    post_review = models.CharField(max_length=8, choices=[("na", "Not needed"), ("pending", "Post-purchase review due"), ("done", "Reviewed")], default="na")
    post_review_note = models.CharField(max_length=500, blank=True)
    single_source = models.BooleanField(default=False)
    single_source_reason = models.CharField(max_length=30, blank=True, choices=[
        ("proprietary", "Proprietary technology"), ("compatibility", "Compatibility requirement"), ("emergency", "Emergency"),
        ("only_supplier", "Only available supplier"), ("existing_contract", "Existing contractual obligation"), ("other", "Other")])
    single_source_justification = models.TextField(blank=True)
    template = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "status"], name="proc_pr_status_idx")]


class PurchaseRequestLine(BaseModel):
    request = models.ForeignKey(PurchaseRequest, on_delete=models.CASCADE, related_name="lines")
    description = models.CharField(max_length=300)
    specification = models.TextField(blank=True)
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("1"))
    uom = models.CharField(max_length=12, default="each")
    estimated_unit_cost = models.DecimalField(max_digits=16, decimal_places=2)
    line_total = models.DecimalField(**MONEY)


# =====================================================================================================================
# Sourcing
# =====================================================================================================================
class SourcingEvent(BaseModel):
    class Kind(models.TextChoices):
        RFQ = "rfq", "RFQ — request for quotation"
        RFP = "rfp", "RFP — request for proposal"
        RFI = "rfi", "RFI — request for information"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        RESPONSES = "responses", "Supplier responses"
        EVALUATION = "evaluation", "Evaluation"
        NEGOTIATION = "negotiation", "Negotiation"
        AWARDED = "awarded", "Awarded"
        CANCELLED = "cancelled", "Cancelled"
        CLOSED = "closed", "Closed"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    number = models.CharField(max_length=20)
    kind = models.CharField(max_length=3, choices=Kind.choices)
    title = models.CharField(max_length=200)
    purchase_request = models.ForeignKey(PurchaseRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name="sourcing_events")
    category = models.ForeignKey(ProcurementCategory, on_delete=models.PROTECT, related_name="+")
    description = models.TextField(blank=True, help_text="Scope of work / need / goal.")
    requirements = models.TextField(blank=True)
    deliverables = models.TextField(blank=True)
    timeline = models.CharField(max_length=200, blank=True)
    delivery_location = models.CharField(max_length=200, blank=True)
    required_delivery = models.DateField(null=True, blank=True)
    commercial_terms = models.TextField(blank=True)
    contract_requirements = models.TextField(blank=True)
    response_deadline = models.DateTimeField(null=True, blank=True)
    criteria = models.JSONField(default=list, help_text='[{"key": "price", "label": "Price", "weight": 40, "auto": "price"}, …] — weights sum to 100.')
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class SourcingLine(BaseModel):
    event = models.ForeignKey(SourcingEvent, on_delete=models.CASCADE, related_name="lines")
    description = models.CharField(max_length=300)
    specification = models.TextField(blank=True)
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("1"))
    uom = models.CharField(max_length=12, default="each")


class EventSupplier(BaseModel):
    event = models.ForeignKey(SourcingEvent, on_delete=models.CASCADE, related_name="invites")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="invites")
    status = models.CharField(max_length=10, choices=[("invited", "Invited"), ("responded", "Responded"), ("declined", "Declined")], default="invited")
    invited_at = models.DateTimeField(auto_now_add=True)
    reminded_at = models.DateTimeField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["event", "supplier"], name="proc_event_supplier_unique")]


class Quotation(BaseModel):
    """A supplier's quote. Negotiation never overwrites it: each round is a new revision linked to the original."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    number = models.CharField(max_length=20)
    event = models.ForeignKey(SourcingEvent, on_delete=models.CASCADE, null=True, blank=True, related_name="quotations")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="quotations")
    quote_reference = models.CharField(max_length=60, blank=True)
    quote_date = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="INR")
    subtotal = models.DecimalField(**MONEY)
    discount = models.DecimalField(**MONEY)
    tax = models.DecimalField(**MONEY)
    shipping = models.DecimalField(**MONEY)
    other_charges = models.DecimalField(**MONEY)
    total = models.DecimalField(**MONEY)
    payment_terms_days = models.PositiveSmallIntegerField(default=30)
    delivery_days = models.PositiveSmallIntegerField(null=True, blank=True)
    warranty_months = models.PositiveSmallIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    tco = models.JSONField(default=dict, blank=True, help_text="Lifetime costs: installation, maintenance, support, training, licensing, operating, disposal.")
    tco_total = models.DecimalField(**MONEY)
    revision = models.PositiveSmallIntegerField(default=1)
    original = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="revisions")
    is_current = models.BooleanField(default=True)
    status = models.CharField(max_length=12, choices=[("received", "Received"), ("shortlisted", "Shortlisted"), ("rejected", "Not selected"),
                                                      ("awarded", "Awarded"), ("superseded", "Superseded by a revision")], default="received")
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        ordering = ["total"]


class QuotationLine(BaseModel):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name="lines")
    sourcing_line = models.ForeignKey(SourcingLine, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    description = models.CharField(max_length=300)
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("1"))
    unit_price = models.DecimalField(max_digits=16, decimal_places=2)
    discount = models.DecimalField(**MONEY)
    tax_rate = models.DecimalField(max_digits=7, decimal_places=4, default=ZERO)
    line_total = models.DecimalField(**MONEY)


class QuotationScore(BaseModel):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name="scores")
    criterion = models.CharField(max_length=30)
    score = models.DecimalField(max_digits=5, decimal_places=2)
    evaluator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["quotation", "criterion", "evaluator"], name="proc_score_unique")]


class NegotiationNote(BaseModel):
    event = models.ForeignKey(SourcingEvent, on_delete=models.CASCADE, related_name="negotiations")
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name="negotiations", help_text="The revision this round produced.")
    previous_total = models.DecimalField(**MONEY)
    new_total = models.DecimalField(**MONEY)
    changes = models.JSONField(default=dict)
    participants = models.CharField(max_length=300, blank=True)
    note = models.TextField()
    by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        ordering = ["created_at"]


class Award(BaseModel):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    number = models.CharField(max_length=20)
    event = models.ForeignKey(SourcingEvent, on_delete=models.PROTECT, related_name="awards")
    quotation = models.ForeignKey(Quotation, on_delete=models.PROTECT, related_name="+")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="+")
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    reason = models.TextField(help_text="Why this supplier: recorded for audit and the AI's “why was Supplier B selected?”.")
    evaluation = models.JSONField(default=dict, help_text="Comparison snapshot at the time of the award.")
    benchmark = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True, help_text="Budget / estimate / last price paid.")
    initial_quote = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    savings = models.DecimalField(**MONEY)
    savings_method = models.CharField(max_length=20, blank=True, choices=[("negotiated", "Negotiated"), ("competitive_bid", "Competitive bid"),
                                                                           ("contract", "Contract"), ("volume", "Volume"), ("avoided", "Avoided cost"),
                                                                           ("process", "Process")])
    status = models.CharField(max_length=18, choices=[("pending_approval", "Waiting for approval"), ("approved", "Approved"), ("rejected", "Rejected")],
                              default="pending_approval")
    approval = models.ForeignKey("workflows.ApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        ordering = ["-created_at"]


# =====================================================================================================================
# Contracts, recurring purchases
# =====================================================================================================================
class ProcurementContract(BaseModel):
    """Procurement context and obligations for a supplier agreement. A future central Legal module owns the legal
    lifecycle and document versions; documents attach through the central document store, never a second repository."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    number = models.CharField(max_length=20)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="contracts")
    title = models.CharField(max_length=200)
    contract_type = models.CharField(max_length=20, choices=[("framework", "Framework / rate contract"), ("service", "Service agreement"),
                                                             ("supply", "Supply agreement"), ("license", "Software licence / SaaS"), ("lease", "Lease / rent"),
                                                             ("maintenance", "Annual maintenance"), ("other", "Other")], default="supply")
    category = models.ForeignKey(ProcurementCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    start_date = models.DateField()
    end_date = models.DateField()
    value = models.DecimalField(**MONEY)
    payment_terms_days = models.PositiveSmallIntegerField(default=30)
    auto_renew = models.BooleanField(default=False)
    notice_period_days = models.PositiveSmallIntegerField(default=30)
    scope = models.TextField(blank=True)
    deliverables = models.TextField(blank=True)
    slas = models.TextField(blank=True)
    pricing_terms = models.TextField(blank=True)
    penalties = models.TextField(blank=True)
    insurance_expiry = models.DateField(null=True, blank=True)
    compliance_notes = models.TextField(blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    status = models.CharField(max_length=12, choices=[("draft", "Draft"), ("active", "Active"), ("expired", "Expired"), ("terminated", "Terminated"),
                                                      ("renewed", "Renewed")], default="active")
    renewal_decision = models.CharField(max_length=12, blank=True, choices=[("renew", "Renew"), ("renegotiate", "Renegotiate"), ("resource", "Re-source"),
                                                                             ("terminate", "Terminate")])
    decision_note = models.TextField(blank=True)
    renewed_from = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["end_date"]


class ContractObligation(BaseModel):
    contract = models.ForeignKey(ProcurementContract, on_delete=models.CASCADE, related_name="obligations")
    kind = models.CharField(max_length=12, choices=[("deliverable", "Deliverable"), ("milestone", "Milestone"), ("sla", "SLA"), ("insurance", "Insurance"),
                                                    ("certificate", "Certificate"), ("payment", "Payment date"), ("renewal", "Renewal date"),
                                                    ("notice", "Notice date"), ("penalty", "Penalty condition")])
    title = models.CharField(max_length=200)
    due_on = models.DateField(null=True, blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    status = models.CharField(max_length=8, choices=[("open", "Open"), ("done", "Done"), ("missed", "Missed")], default="open")
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["due_on"]


class RecurringPurchase(BaseModel):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    number = models.CharField(max_length=20)
    title = models.CharField(max_length=200)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="+")
    contract = models.ForeignKey(ProcurementContract, on_delete=models.SET_NULL, null=True, blank=True, related_name="recurring")
    category = models.ForeignKey(ProcurementCategory, on_delete=models.PROTECT, related_name="+")
    department = models.ForeignKey(Department, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    frequency = models.CharField(max_length=10, choices=[("monthly", "Monthly"), ("quarterly", "Quarterly"), ("yearly", "Yearly")], default="monthly")
    expected_amount = models.DecimalField(max_digits=16, decimal_places=2)
    next_date = models.DateField()
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    is_active = models.BooleanField(default=True)
    last_request = models.ForeignKey(PurchaseRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["next_date"]


# =====================================================================================================================
# Purchase orders & receiving
# =====================================================================================================================
class PurchaseOrder(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending_approval", "Waiting for approval"
        APPROVED = "approved", "Approved"
        SENT = "sent", "Sent to supplier"
        CONFIRMED = "confirmed", "Supplier confirmed"
        PARTIAL_RECEIVED = "partially_received", "Partially received"
        RECEIVED = "received", "Received"
        PARTIAL_INVOICED = "partially_invoiced", "Partially invoiced"
        INVOICED = "invoiced", "Invoiced"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        CLOSED = "closed", "Closed"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    number = models.CharField(max_length=20)
    version = models.PositiveSmallIntegerField(default=1)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="orders")
    entity = models.ForeignKey("finance.FinancialEntity", on_delete=models.PROTECT, related_name="+")
    department = models.ForeignKey(Department, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    cost_center = models.ForeignKey("finance.CostCenter", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    project = models.CharField(max_length=120, blank=True)
    category = models.ForeignKey(ProcurementCategory, on_delete=models.PROTECT, related_name="+")
    purchase_request = models.ForeignKey(PurchaseRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    event = models.ForeignKey(SourcingEvent, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    award = models.OneToOneField(Award, on_delete=models.SET_NULL, null=True, blank=True, related_name="order")
    contract = models.ForeignKey(ProcurementContract, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    currency = models.CharField(max_length=3, default="INR")
    subtotal = models.DecimalField(**MONEY)
    discount = models.DecimalField(**MONEY)
    tax = models.DecimalField(**MONEY)
    shipping = models.DecimalField(**MONEY)
    total = models.DecimalField(**MONEY)
    delivery_location = models.CharField(max_length=200, blank=True)
    expected_delivery = models.DateField(null=True, blank=True)
    confirmed_delivery = models.DateField(null=True, blank=True)
    payment_terms_days = models.PositiveSmallIntegerField(default=30)
    warranty = models.CharField(max_length=120, blank=True)
    terms = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    confirmation = models.CharField(max_length=24, blank=True, choices=[("accepted", "Accepted"), ("accepted_with_changes", "Accepted with changes"),
                                                                        ("rejected", "Rejected"), ("partially_accepted", "Partially accepted")])
    confirmation_note = models.CharField(max_length=500, blank=True)
    carrier = models.CharField(max_length=80, blank=True)
    tracking_number = models.CharField(max_length=80, blank=True)
    delivery_status = models.CharField(max_length=20, blank=True)
    is_emergency = models.BooleanField(default=False)
    approval = models.ForeignKey("workflows.ApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "status"], name="proc_po_status_idx")]

    @property
    def is_locked(self) -> bool:
        """Approved or later: changes only through an approved amendment (new version)."""
        return self.status not in (self.Status.DRAFT, self.Status.PENDING)


class PurchaseOrderLine(BaseModel):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    line_no = models.PositiveSmallIntegerField()
    description = models.CharField(max_length=300)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    uom = models.CharField(max_length=12, default="each")
    unit_price = models.DecimalField(max_digits=16, decimal_places=2)
    discount = models.DecimalField(**MONEY)
    tax_rule = models.ForeignKey("finance.TaxRule", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    tax_rate = models.DecimalField(max_digits=7, decimal_places=4, default=ZERO)
    line_total = models.DecimalField(**MONEY)
    is_service = models.BooleanField(default=False)
    is_capex = models.BooleanField(default=False)
    is_inventory = models.BooleanField(default=False)
    received_qty = models.DecimalField(**QTY)
    rejected_qty = models.DecimalField(**QTY)
    invoiced_qty = models.DecimalField(**QTY)
    service_accepted_amount = models.DecimalField(**MONEY)

    class Meta:
        ordering = ["line_no"]

    @property
    def accepted_qty(self):
        return self.received_qty - self.rejected_qty

    @property
    def remaining_qty(self):
        return max(ZERO, self.quantity - self.received_qty + self.rejected_qty)


class PurchaseOrderVersion(BaseModel):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveSmallIntegerField()
    snapshot = models.JSONField()
    reason = models.CharField(max_length=300)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        ordering = ["-version"]
        constraints = [models.UniqueConstraint(fields=["order", "version"], name="proc_po_version_unique")]


class PurchaseOrderAmendment(BaseModel):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="amendments")
    from_version = models.PositiveSmallIntegerField()
    reason = models.CharField(max_length=300)
    changes = models.JSONField(help_text='{"lines": [{"line_id", "quantity", "unit_price"}], "expected_delivery": …, "terms": …}')
    new_total = models.DecimalField(**MONEY)
    status = models.CharField(max_length=18, choices=[("pending_approval", "Waiting for approval"), ("approved", "Approved"), ("rejected", "Rejected")],
                              default="pending_approval")
    approval = models.ForeignKey("workflows.ApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        ordering = ["-created_at"]


class GoodsReceipt(BaseModel):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    number = models.CharField(max_length=20)
    order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="receipts")
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    received_on = models.DateField()
    delivery_note = models.CharField(max_length=80, blank=True)
    condition = models.CharField(max_length=200, blank=True)
    evidence = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=12, choices=[("accepted", "Accepted"), ("inspection", "Awaiting quality inspection"),
                                                      ("partial", "Partially accepted"), ("rejected", "Rejected")], default="accepted")
    inventory_status = models.CharField(max_length=12, default="na", help_text="na | pending (Inventory module not connected) | posted")

    class Meta:
        ordering = ["-received_on", "-created_at"]


class GoodsReceiptLine(BaseModel):
    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name="lines")
    order_line = models.ForeignKey(PurchaseOrderLine, on_delete=models.PROTECT, related_name="receipt_lines")
    received_qty = models.DecimalField(max_digits=14, decimal_places=3)
    rejected_qty = models.DecimalField(**QTY)
    damaged_qty = models.DecimalField(**QTY)
    batch = models.CharField(max_length=60, blank=True)
    serials = models.JSONField(default=list, blank=True)
    note = models.CharField(max_length=200, blank=True)


class QualityInspection(BaseModel):
    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name="inspections")
    result = models.CharField(max_length=10, choices=[("accepted", "Accepted"), ("rejected", "Rejected"), ("partial", "Partially accepted")])
    inspector = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    notes = models.TextField(blank=True)
    corrective_action = models.TextField(blank=True)
    evidence = models.CharField(max_length=300, blank=True)


class ServiceReceipt(BaseModel):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    number = models.CharField(max_length=20)
    order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="service_receipts")
    order_line = models.ForeignKey(PurchaseOrderLine, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    period_from = models.DateField(null=True, blank=True)
    period_to = models.DateField(null=True, blank=True)
    deliverables = models.TextField()
    milestone = models.CharField(max_length=120, blank=True)
    completion_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("100"))
    amount = models.DecimalField(max_digits=16, decimal_places=2, help_text="Value of the service accepted.")
    evidence = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=10, choices=[("submitted", "Submitted"), ("accepted", "Accepted"), ("rejected", "Rejected")], default="submitted")
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    decision_note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-created_at"]


# =====================================================================================================================
# Exceptions
# =====================================================================================================================
class ProcurementException(BaseModel):
    class Kind(models.TextChoices):
        NO_QUOTES = "no_competitive_quotes", "No competitive quotes"
        BUDGET = "budget_exceeded", "Budget exceeded"
        SINGLE_SOURCE = "single_source", "Single source"
        LATE_PO = "late_po", "Late / overdue PO"
        MISSING_PO = "missing_po", "Purchase without PO"
        INVOICE_NO_PO = "invoice_without_po", "Invoice without PO"
        MISMATCH = "three_way_mismatch", "Three-way mismatch"
        EMERGENCY = "emergency_purchase", "Emergency purchase"
        CONTRACT = "contract_deviation", "Contract deviation"
        ONBOARDING = "supplier_onboarding_incomplete", "Supplier onboarding incomplete"
        SPLIT = "split_purchase", "Possible split purchase"
        REPEATED_EMERGENCY = "repeated_emergency", "Repeated emergency purchases"
        BANK_CHANGE = "bank_change", "Recent supplier bank change"
        DUPLICATE_SUPPLIER = "duplicate_supplier", "Possible duplicate supplier"
        CONCENTRATION = "concentration", "Supplier concentration"
        PRICE_INCREASE = "price_increase", "Unusual price increase"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PENDING = "pending_approval", "Waiting for approval"
        APPROVED = "approved", "Approved exception"
        RESOLVED = "resolved", "Resolved"
        REJECTED = "rejected", "Rejected"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    number = models.CharField(max_length=20)
    kind = models.CharField(max_length=32, choices=Kind.choices)
    source_type = models.CharField(max_length=40)
    source_id = models.CharField(max_length=64)
    source_label = models.CharField(max_length=80, blank=True)
    description = models.CharField(max_length=500)
    amount = models.DecimalField(**MONEY)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=18, choices=Status.choices, default=Status.OPEN)
    approval = models.ForeignKey("workflows.ApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    resolution = models.CharField(max_length=500, blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    detected = models.BooleanField(default=False, help_text="Raised by a detector (flag for review, not an accusation).")

    class Meta:
        ordering = ["status", "-created_at"]
        constraints = [models.UniqueConstraint(fields=["kind", "source_type", "source_id"], name="proc_exception_once")]
