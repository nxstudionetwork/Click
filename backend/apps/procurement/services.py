"""
Procurement lifecycle services.

    need → PurchaseRequest (budget check, policy checks) → approval (engine "procurement.request") → budget reserved
    → SourcingEvent (RFQ/RFP/RFI) → Quotations (revisions on negotiation) → weighted comparison + TCO → Award (approved)
    → PurchaseOrder (approved, versioned, amendments approved) → sent / confirmed / delivery tracked
    → GoodsReceipt / QualityInspection / ServiceReceipt → supplier invoice recorded in Finance (vendor bill)
    → three- or two-way match (registered with Finance) → Finance approves, pays, reconciles → supplier performance

Separation of duties (configurable): requester ≠ approver (engine) ≠ buyer (policy) ≠ receiver (policy) ≠ payment
releaser (Finance). Detectors flag patterns for review; they never accuse anyone.
"""

from __future__ import annotations

import re
from datetime import date as Date
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.access.security import encrypt
from apps.audit.services import record
from apps.core.api.exceptions import DomainError
from apps.finance import ledger
from apps.finance import services as fin
from apps.workflows import engine
from apps.workflows.hooks import on_decision
from apps.workspace.notify import notify, notify_many

from .models import (Award, ConflictDeclaration, ContractObligation, EventSupplier, GoodsReceipt, GoodsReceiptLine, NegotiationNote, ProcurementCategory,
                     ProcurementContract, ProcurementException, ProcurementPolicy, PurchaseOrder, PurchaseOrderAmendment, PurchaseOrderLine,
                     PurchaseOrderVersion, PurchaseRequest, PurchaseRequestLine, QualityInspection, Quotation, QuotationLine, QuotationScore,
                     RecurringPurchase, ServiceReceipt, SourcingEvent, SourcingLine, Supplier, SupplierBankChange, SupplierStatusEvent)

ZERO = Decimal("0")
HUNDRED = Decimal("100")
q2 = ledger.q2

# Inventory integration point: the Inventory module registers receivers here (stock stays Inventory's source of truth).
INVENTORY_RECEIVERS: list = []


def dec(v, field="amount") -> Decimal:
    try:
        return q2(Decimal(str(v)))
    except (InvalidOperation, TypeError, ValueError):
        raise DomainError("Enter a valid amount.", code="validation_error", details={field: ["Enter a valid amount."]})


def qty(v, field="quantity") -> Decimal:
    try:
        d = Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        raise DomainError("Enter a valid quantity.", code="validation_error", details={field: ["Enter a valid quantity."]})
    if d < 0:
        raise DomainError("Quantities can't be negative.", code="validation_error")
    return d


def _date(v, field="date", required=True):
    d = parse_date(str(v or ""))
    if d is None and required:
        raise DomainError("Enter a valid date.", code="validation_error", details={field: ["Enter a valid date."]})
    return d


def policy(org) -> ProcurementPolicy:
    p, _ = ProcurementPolicy.objects.get_or_create(organization=org, defaults={"contract_alert_days": [90, 60, 30]})
    return p


def _decider(req):
    step = req.steps.filter(status="approved").order_by("-sequence").first()
    return step.decided_by if step else None


def raise_exception(org, kind, *, source_type, source_id, label="", description, amount=ZERO, owner=None, reason="", detected=False) -> ProcurementException:
    exc, made = ProcurementException.objects.get_or_create(organization=org, kind=kind, source_type=source_type, source_id=str(source_id), defaults={
        "number": ledger.next_number(org, "pexc"), "source_label": label[:80], "description": description[:500], "amount": amount or ZERO, "owner": owner,
        "reason": reason, "detected": detected})
    if made and detected:
        from apps.access.authz import holders_of

        notify_many(holders_of("procurement.exception.manage", org)[:10], "business", f"Procurement flag: {exc.get_kind_display()}",
                    body=f"{label}: {description[:150]} — flagged for review, not a finding.", link="/procurement/exceptions", module="procurement")
    return exc


# =====================================================================================================================
# Suppliers
# =====================================================================================================================
def _norm(s: str) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    s = re.sub(r"\b(pvt|private|ltd|limited|llp|inc|co|company|india|the|and)\b", " ", s)
    return " ".join(s.split())


def duplicates(org, *, legal_name="", tax_id="", email="", phone="", bank_last4="", bank_ifsc="", exclude=None) -> list[dict]:
    """Possible duplicates for controlled review — never merged automatically."""
    out = []
    n = _norm(legal_name)
    domain = email.split("@")[-1].lower() if "@" in (email or "") else ""
    for s in Supplier.objects.filter(organization=org).exclude(pk=getattr(exclude, "pk", exclude)):
        why = []
        if n and (_norm(s.legal_name) == n or _norm(s.trading_name) == n or (len(n) > 5 and (n in _norm(s.legal_name) or _norm(s.legal_name) in n))):
            why.append("similar name")
        if tax_id and s.tax_id and tax_id.upper() == s.tax_id.upper():
            why.append("same tax ID")
        if bank_last4 and bank_ifsc and s.bank_last4 == bank_last4 and s.bank_ifsc.upper() == bank_ifsc.upper():
            why.append("same bank account")
        if domain and domain not in ("gmail.com", "yahoo.com", "outlook.com", "hotmail.com") and s.email.lower().endswith("@" + domain):
            why.append("same email domain")
        if phone and s.phone and re.sub(r"\D", "", phone)[-10:] == re.sub(r"\D", "", s.phone)[-10:]:
            why.append("same phone")
        if why:
            out.append({"id": str(s.pk), "code": s.code, "name": s.legal_name, "status": s.status, "why": why})
    return out


def create_supplier(request, ctx, data: dict) -> Supplier:
    ctx.require("procurement.supplier.create")
    org = ctx.organization
    name = str(data.get("legal_name", "")).strip()
    if len(name) < 2:
        raise DomainError("Enter the legal name.", code="validation_error", details={"legalName": ["Required."]})
    dups = duplicates(org, legal_name=name, tax_id=str(data.get("tax_id", "")), email=str(data.get("email", "")), phone=str(data.get("phone", "")))
    if dups and not data.get("confirm_not_duplicate"):
        raise DomainError(f"Possible duplicate of {dups[0]['name']} ({', '.join(dups[0]['why'])}). Review it, or confirm this is a different business.",
                          code="possible_duplicate", status_code=409, details={"duplicates": dups})
    partner = None
    if data.get("partner_id"):
        from apps.partners.models import Partner

        partner = Partner.objects.filter(pk=data["partner_id"]).first()
    with transaction.atomic():
        s = Supplier.objects.create(
            organization=org, code=ledger.next_number(org, "supplier"), legal_name=name[:200], trading_name=str(data.get("trading_name", ""))[:200],
            supplier_type=data.get("supplier_type") if data.get("supplier_type") in Supplier.Type.values else "other",
            relationship=data.get("relationship") if data.get("relationship") in Supplier.Relationship.values else ("both" if partner else "procurement_supplier"),
            partner=partner, contact_name=str(data.get("contact_name", ""))[:120], email=str(data.get("email", ""))[:254], phone=str(data.get("phone", ""))[:30],
            website=str(data.get("website", ""))[:200], address=str(data.get("address", ""))[:300], city=str(data.get("city", ""))[:80],
            state=str(data.get("state", ""))[:80], tax_id=str(data.get("tax_id", "")).upper()[:20], pan=str(data.get("pan", "")).upper()[:10],
            registration_number=str(data.get("registration_number", ""))[:40], payment_terms_days=int(data.get("payment_terms_days") or 30),
            created_by=ctx.user, status="registered", preference="conditional")
        if data.get("category_ids"):
            s.categories.set(ProcurementCategory.objects.filter(organization=org, pk__in=data["category_ids"]))
        if dups:
            raise_exception(org, "duplicate_supplier", source_type="procurement.supplier", source_id=s.pk, label=s.code,
                            description=f"Created despite a possible duplicate: {dups[0]['name']} ({', '.join(dups[0]['why'])}).", owner=ctx.user, detected=True)
    record(request, "procurement.supplier.created", category="data", module="procurement", resource=s, new={"name": s.legal_name, "code": s.code})
    return s


VERIFY_CHECKS = ("legal_name", "tax_registration", "business_registration", "address", "bank_account", "contact", "certifications", "insurance",
                 "compliance_documents")
REQUIRED_CHECKS = ("legal_name", "tax_registration", "bank_account")


def verify(request, ctx, s: Supplier, check: str, status: str, note: str = "") -> Supplier:
    ctx.require("procurement.supplier.edit")
    if check not in VERIFY_CHECKS or status not in ("verified", "failed", "not_applicable"):
        raise DomainError("Unknown check.", code="validation_error")
    if check == "bank_account" and not s.bank_last4:
        raise DomainError("Add bank details (through a bank change request) before verifying them.", code="validation_error")
    s.verification = {**(s.verification or {}), check: {"status": status, "by": ctx.user.full_name, "at": timezone.now().isoformat(), "note": note[:200]}}
    if check == "bank_account":
        s.bank_verified = status == "verified"
    s.save(update_fields=["verification", "bank_verified", "updated_at"])
    record(request, "procurement.supplier.verified", category="data", module="procurement", resource=s, new={"check": check, "status": status})
    return s


def submit_onboarding(request, ctx, s: Supplier) -> Supplier:
    ctx.require("procurement.supplier.create")
    if s.status not in ("registered", "invited", "rejected"):
        raise DomainError("This supplier isn't waiting for onboarding.", code="invalid_state", status_code=409)
    missing = [c for c in REQUIRED_CHECKS if (s.verification or {}).get(c, {}).get("status") not in ("verified", "not_applicable")]
    if missing:
        raise DomainError("Complete verification first: " + ", ".join(c.replace("_", " ") for c in missing) + ".", code="verification_incomplete",
                          status_code=409, details={"missing": missing})
    req = engine.submit(request, "procurement.supplier", title=f"Supplier onboarding: {s.legal_name}", description=f"{s.code} · {s.get_supplier_type_display()}",
                        resource_type="procurement.supplier", resource_id=str(s.pk))
    s.status, s.approval = "under_review", req
    s.save(update_fields=["status", "approval", "updated_at"])
    return s


@on_decision("procurement.supplier")
def _supplier_decided(req, outcome):
    s = Supplier.objects.filter(pk=req.resource_id).first()
    if s is None or s.status != "under_review":
        return
    if outcome == "approved":
        s.status, s.preference = "active", "approved"
    elif outcome in ("rejected", "cancelled"):
        s.status = "rejected" if outcome == "rejected" else "registered"
    s.save(update_fields=["status", "preference", "updated_at"])
    SupplierStatusEvent.objects.create(supplier=s, field="status", from_value="under_review", to_value=s.status, note=f"Onboarding {outcome}", by=_decider(req))


def set_preference(request, ctx, s: Supplier, preference: str, reason_category: str, note: str) -> Supplier:
    """Preferred / approved / conditional / restricted / blocked. Restricting or blocking is controlled and audited."""
    ctx.require("procurement.supplier.approve")
    if preference not in Supplier.Preference.values:
        raise DomainError("Choose a status.", code="validation_error")
    if preference in ("restricted", "blocked") and (not note.strip() or reason_category not in
                                                    ("compliance", "quality", "contract", "fraud_investigation", "legal", "performance", "other_approved")):
        raise DomainError("Give the reason category and a note.", code="reason_required")
    before = s.preference
    s.preference, s.restriction_reason = preference, note[:300] if preference in ("restricted", "blocked") else ""
    s.save(update_fields=["preference", "restriction_reason", "updated_at"])
    SupplierStatusEvent.objects.create(supplier=s, from_value=before, to_value=preference, reason_category=reason_category, note=note[:300], by=ctx.user)
    record(request, "procurement.supplier.preference", category="data", module="procurement", resource=s, old={"preference": before},
           new={"preference": preference, "reason": reason_category}, sensitive=preference in ("blocked",) and reason_category == "fraud_investigation")
    return s


def request_bank_change(request, ctx, s: Supplier, *, account: str, ifsc: str, reason: str, evidence: str) -> SupplierBankChange:
    ctx.require("procurement.supplier_bank.manage")
    digits = "".join(ch for ch in account if ch.isalnum())
    if len(digits) < 6 or not re.fullmatch(r"[A-Za-z]{4}0[A-Za-z0-9]{6}", ifsc or ""):
        raise DomainError("Enter the full account number and a valid IFSC.", code="validation_error")
    if not reason.strip() or not evidence.strip():
        raise DomainError("Say why it changed and how you verified it independently.", code="reason_required")
    with transaction.atomic():
        bc = SupplierBankChange.objects.create(supplier=s, account_enc=encrypt(digits), last4=digits[-4:], ifsc=ifsc.upper(), reason=reason[:300],
                                               evidence=evidence[:300], requested_by=ctx.user)
        bc.approval = engine.submit(request, "procurement.supplier_bank", title=f"Bank change: {s.legal_name}", priority="high",
                                    description=f"New account ending {bc.last4} ({bc.ifsc}). Reason: {reason}. Verified by: {evidence}",
                                    resource_type="procurement.supplier_bank", resource_id=str(bc.pk))
        bc.save(update_fields=["approval", "updated_at"])
    record(request, "procurement.supplier.bank_change_requested", category="financial", module="procurement", resource=s, sensitive=True,
           new={"last4": bc.last4})
    return bc


@on_decision("procurement.supplier_bank")
def _bank_decided(req, outcome):
    bc = SupplierBankChange.objects.filter(pk=req.resource_id, status="pending").select_related("supplier").first()
    if bc is None:
        return
    if outcome == "approved":
        s = bc.supplier
        old = s.bank_last4
        s.bank_account_enc, s.bank_last4, s.bank_ifsc, s.bank_changed_at = bc.account_enc, bc.last4, bc.ifsc, timezone.now()
        s.bank_verified = True
        s.verification = {**(s.verification or {}), "bank_account": {"status": "verified", "by": getattr(_decider(req), "full_name", ""),
                                                                     "at": timezone.now().isoformat(), "note": bc.evidence[:200]}}
        s.save()
        bc.status = "approved"
        record(None, "procurement.supplier.bank_changed", category="financial", module="procurement", resource=s, organization=s.organization,
               actor=_decider(req), sensitive=True, old={"last4": old}, new={"last4": s.bank_last4})
        from apps.access.authz import holders_of

        notify_many([u for u in holders_of("finance.bank.manage", s.organization)], "security", f"Supplier bank details changed: {s.legal_name}",
                    body=f"Now ends {s.bank_last4}. Check open payments to this supplier.", priority="critical", link=f"/procurement/suppliers?open={s.pk}")
    elif outcome in ("rejected", "cancelled"):
        bc.status = "rejected"
    bc.save(update_fields=["status", "updated_at"])


# =====================================================================================================================
# Purchase requests
# =====================================================================================================================
def create_pr(request, ctx, data: dict) -> PurchaseRequest:
    ctx.require("procurement.request.create")
    org = ctx.organization
    cat = ProcurementCategory.objects.filter(organization=org, pk=data.get("category_id"), is_active=True).first()
    if cat is None:
        raise DomainError("Choose a category.", code="validation_error", details={"categoryId": ["Required."]})
    title = str(data.get("title", "")).strip()
    lines = data.get("lines") or []
    if len(title) < 3 or not lines:
        raise DomainError("Add a title and at least one item.", code="validation_error")
    if len(str(data.get("justification", "")).strip()) < 10:
        raise DomainError("Explain the business need.", code="validation_error", details={"justification": ["Required."]})
    emp = ctx.employee
    rtype = data.get("request_type") if data.get("request_type") in PurchaseRequest.Type.values else "standard"
    from apps.finance.models import CostCenter

    with transaction.atomic():
        pr = PurchaseRequest.objects.create(
            organization=org, number=ledger.next_number(org, "pr"), title=title[:200], requester=ctx.user,
            department=emp.department if emp else None, org_unit=emp.org_unit if emp else None, category=cat, request_type=rtype,
            expenditure="capex" if rtype == "capex" or cat.expenditure == "capex" else (data.get("expenditure") or "opex"),
            priority=data.get("priority") if data.get("priority") in ("low", "normal", "high", "critical") else "normal",
            required_by=_date(data.get("required_by"), required=False), justification=str(data["justification"])[:4000], project=str(data.get("project", ""))[:120],
            cost_center=CostCenter.objects.filter(organization=org, pk=data.get("cost_center_id")).first() if data.get("cost_center_id") else None,
            preferred_supplier=Supplier.objects.filter(organization=org, pk=data.get("preferred_supplier_id")).first() if data.get("preferred_supplier_id") else None,
            is_emergency=rtype == "emergency", emergency_reason=str(data.get("emergency_reason", ""))[:500],
            single_source=bool(data.get("single_source")), single_source_reason=str(data.get("single_source_reason", ""))[:30],
            single_source_justification=str(data.get("single_source_justification", ""))[:4000], template=str(data.get("template", ""))[:40])
        total = ZERO
        for ln in lines:
            q, p = qty(ln.get("quantity") or 1), dec(ln.get("estimated_unit_cost"), "estimatedUnitCost")
            t = q2(q * p)
            PurchaseRequestLine.objects.create(request=pr, description=str(ln.get("description") or "Item")[:300], specification=str(ln.get("specification", ""))[:2000],
                                               quantity=q, uom=str(ln.get("uom") or "each")[:12], estimated_unit_cost=p, line_total=t)
            total += t
        pr.estimated_total = total
        pr.save(update_fields=["estimated_total", "updated_at"])
    record(request, "procurement.request.created", category="data", module="procurement", resource=pr, new={"total": pr.estimated_total, "title": pr.title})
    return pr


def budget_check(pr: PurchaseRequest) -> dict:
    return fin.check_budget(pr.organization, pr.estimated_total, department=pr.department, org_unit=pr.org_unit, cost_center=pr.cost_center,
                            category=pr.category.budget_category)


def submit_pr(request, ctx, pr: PurchaseRequest, *, budget_override_reason: str = "") -> PurchaseRequest:
    if pr.requester_id != ctx.user.pk:
        raise DomainError("Only the requester can submit this request.", code="permission_denied", status_code=403)
    if pr.status not in ("draft",):
        raise DomainError("Only drafts can be submitted.", code="invalid_state", status_code=409)
    org = ctx.organization
    pol = policy(org)
    if pr.is_emergency:
        if len(pr.emergency_reason.strip()) < 10:
            raise DomainError("Describe the emergency.", code="validation_error", details={"emergencyReason": ["Required."]})
        if pr.estimated_total > pol.emergency_max_amount:
            raise DomainError(f"Emergency purchases are limited to {pol.emergency_max_amount}. Use the normal process.", code="emergency_limit", status_code=409)
    if pr.single_source and (not pr.single_source_reason or len(pr.single_source_justification.strip()) < 20):
        raise DomainError("Single-source purchases need a reason and a business justification.", code="validation_error")
    check = budget_check(pr)
    flags = []
    if check["status"] == "insufficient":
        if not budget_override_reason.strip():
            raise DomainError(check["message"] + " Give a reason to request a budget override.", code="budget_insufficient", status_code=409,
                              details={"budget": {k: str(v) for k, v in check.items() if k in ("budget", "committed", "available", "after")}})
        flags.append("BUDGET OVERRIDE: " + budget_override_reason)
    elif check["status"] == "no_budget":
        flags.append("No approved budget covers this purchase.")
    with transaction.atomic():
        pr.budget_check = {k: (str(v) if isinstance(v, Decimal) else v) for k, v in check.items()}
        pr.budget_id = check.get("budget_id", "") or ""
        desc = pr.justification + ("\n\n" + "\n".join(flags) if flags else "")
        if pr.is_emergency:
            desc = f"EMERGENCY: {pr.emergency_reason}\n\n" + desc
        req = engine.submit(request, "procurement.request", title=f"{pr.number}: {pr.title}", amount=pr.estimated_total, department=pr.department,
                            org_unit=pr.org_unit, description=desc[:4000], resource_type="procurement.request", resource_id=str(pr.pk),
                            priority="critical" if pr.is_emergency else ("high" if pr.priority in ("high", "critical") else "normal"),
                            blocking=pr.is_emergency, metadata={"budget": pr.budget_check, "category": pr.category.code})
        pr.status, pr.approval = "submitted", req
        pr.post_review = "pending" if pr.is_emergency else "na"
        pr.save()
        if check["status"] == "insufficient":
            raise_exception(org, "budget_exceeded", source_type="procurement.request", source_id=pr.pk, label=pr.number, amount=pr.estimated_total,
                            description=check["message"], reason=budget_override_reason, owner=ctx.user)
        if pr.is_emergency:
            raise_exception(org, "emergency_purchase", source_type="procurement.request", source_id=pr.pk, label=pr.number, amount=pr.estimated_total,
                            description=pr.emergency_reason, reason="Post-purchase review required", owner=ctx.user)
        if pr.single_source:
            raise_exception(org, "single_source", source_type="procurement.request", source_id=pr.pk, label=pr.number, amount=pr.estimated_total,
                            description=f"{pr.get_single_source_reason_display()}: {pr.single_source_justification[:300]}", owner=ctx.user)
    detect_split(pr)
    return pr


@on_decision("procurement.request")
def _pr_decided(req, outcome):
    pr = PurchaseRequest.objects.filter(pk=req.resource_id).select_related("category").first()
    if pr is None:
        return
    if outcome == "approved" and pr.status == "submitted":
        pr.status, pr.approved_at = "approved", timezone.now()
        pr.save(update_fields=["status", "approved_at", "updated_at"])
        if pr.budget_id:
            fin.reserve(pr.organization, budget_id=pr.budget_id, amount=pr.estimated_total, source_module="procurement", source_type="procurement.request",
                        source_id=pr.pk, label=pr.number)
        from apps.access.authz import holders_of

        notify_many(holders_of("procurement.order.create", pr.organization)[:10], "business", f"Ready for sourcing: {pr.number} {pr.title}",
                    body=f"{pr.estimated_total} · {pr.category.name}", link=f"/procurement/requests?open={pr.pk}", module="procurement")
    elif outcome in ("rejected", "cancelled") and pr.status in ("submitted", "changes_requested"):
        pr.status = "rejected" if outcome == "rejected" else "cancelled"
        pr.save(update_fields=["status", "updated_at"])
    elif outcome == "changes_requested":
        pr.status = "changes_requested"
        pr.save(update_fields=["status", "updated_at"])
    elif outcome == "resubmitted":
        pr.status = "submitted"
        pr.save(update_fields=["status", "updated_at"])


def cancel_pr(request, ctx, pr: PurchaseRequest, reason: str):
    if pr.requester_id != ctx.user.pk and not ctx.has("procurement.request.approve"):
        raise DomainError("You can't cancel this request.", code="permission_denied", status_code=403)
    if pr.status in ("ordered", "closed", "cancelled", "rejected"):
        raise DomainError("This request can't be cancelled now.", code="invalid_state", status_code=409)
    if pr.approval_id and pr.approval.status in ("pending", "changes_requested") and pr.requester_id == ctx.user.pk:
        engine.cancel(request, pr.approval, reason=reason)
    pr.status = "cancelled"
    pr.save(update_fields=["status", "updated_at"])
    fin.release("procurement.request", pr.pk)
    record(request, "procurement.request.cancelled", category="data", module="procurement", resource=pr, new={"reason": reason})


def post_review(request, ctx, pr: PurchaseRequest, note: str):
    ctx.require("procurement.exception.approve")
    if pr.post_review != "pending":
        raise DomainError("No post-purchase review is due.", code="invalid_state", status_code=409)
    if pr.requester_id == ctx.user.pk:
        raise DomainError("Someone else must review your emergency purchase.", code="self_change_denied", status_code=403)
    pr.post_review, pr.post_review_note = "done", note[:500]
    pr.save(update_fields=["post_review", "post_review_note", "updated_at"])
    ProcurementException.objects.filter(kind="emergency_purchase", source_id=str(pr.pk)).update(status="resolved", resolution=note[:500], resolved_by=ctx.user)
    record(request, "procurement.emergency.reviewed", category="data", module="procurement", resource=pr, new={"note": note[:200]})


# =====================================================================================================================
# Sourcing
# =====================================================================================================================
DEFAULT_CRITERIA = {
    "rfq": [{"key": "price", "label": "Price (total cost)", "weight": 40, "auto": "price"}, {"key": "quality", "label": "Quality", "weight": 20},
            {"key": "delivery", "label": "Delivery time", "weight": 15, "auto": "delivery"}, {"key": "warranty", "label": "Warranty", "weight": 10, "auto": "warranty"},
            {"key": "support", "label": "Support", "weight": 10}, {"key": "compliance", "label": "Compliance", "weight": 5}],
    "rfp": [{"key": "technical", "label": "Technical fit", "weight": 40}, {"key": "price", "label": "Commercial (total cost)", "weight": 30, "auto": "price"},
            {"key": "experience", "label": "Experience & references", "weight": 15}, {"key": "delivery", "label": "Timeline", "weight": 10, "auto": "delivery"},
            {"key": "compliance", "label": "Compliance", "weight": 5}],
    "rfi": [],
}


def create_event(request, ctx, data: dict) -> SourcingEvent:
    ctx.require("procurement.sourcing.create")
    org = ctx.organization
    kind = data.get("kind") if data.get("kind") in SourcingEvent.Kind.values else "rfq"
    pr = PurchaseRequest.objects.filter(organization=org, pk=data.get("purchase_request_id")).first() if data.get("purchase_request_id") else None
    if pr is not None and pr.status not in ("approved", "sourcing"):
        raise DomainError("Source only approved purchase requests.", code="invalid_state", status_code=409)
    cat = pr.category if pr else ProcurementCategory.objects.filter(organization=org, pk=data.get("category_id")).first()
    if cat is None:
        raise DomainError("Choose a category or an approved purchase request.", code="validation_error")
    criteria = data.get("criteria") or DEFAULT_CRITERIA[kind]
    if criteria and sum(Decimal(str(c.get("weight") or 0)) for c in criteria) != 100:
        raise DomainError("Evaluation weights must add up to 100.", code="validation_error", details={"criteria": ["Weights must total 100."]})
    with transaction.atomic():
        ev = SourcingEvent.objects.create(
            organization=org, number=ledger.next_number(org, kind), kind=kind, title=str(data.get("title") or (pr.title if pr else ""))[:200] or "Sourcing event",
            purchase_request=pr, category=cat, description=str(data.get("description") or (pr.justification if pr else ""))[:4000],
            requirements=str(data.get("requirements", ""))[:4000], deliverables=str(data.get("deliverables", ""))[:4000], timeline=str(data.get("timeline", ""))[:200],
            delivery_location=str(data.get("delivery_location", ""))[:200], required_delivery=_date(data.get("required_delivery"), required=False) or (pr.required_by if pr else None),
            commercial_terms=str(data.get("commercial_terms", ""))[:4000], contract_requirements=str(data.get("contract_requirements", ""))[:4000],
            response_deadline=parse_datetime(str(data.get("response_deadline") or "")) or None, criteria=criteria, owner=ctx.user)
        src_lines = data.get("lines") or ([{"description": ln.description, "specification": ln.specification, "quantity": ln.quantity, "uom": ln.uom}
                                           for ln in pr.lines.all()] if pr else [])
        for ln in src_lines:
            SourcingLine.objects.create(event=ev, description=str(ln.get("description") or "Item")[:300], specification=str(ln.get("specification", ""))[:2000],
                                        quantity=qty(ln.get("quantity") or 1), uom=str(ln.get("uom") or "each")[:12])
        if pr and pr.status == "approved":
            pr.status = "sourcing"
            pr.save(update_fields=["status", "updated_at"])
    record(request, f"procurement.{kind}.created", category="data", module="procurement", resource=ev, new={"title": ev.title})
    return ev


def invite(request, ctx, ev: SourcingEvent, supplier_ids: list) -> int:
    ctx.require("procurement.sourcing.manage") if ev.owner_id != ctx.user.pk else ctx.require("procurement.sourcing.create")
    if ev.status in ("awarded", "cancelled", "closed"):
        raise DomainError("This event is finished.", code="invalid_state", status_code=409)
    n = 0
    for s in Supplier.objects.filter(organization=ev.organization, pk__in=supplier_ids):
        if s.preference == "blocked":
            raise DomainError(f"{s.legal_name} is blocked and can't be invited.", code="supplier_blocked", status_code=409)
        _, made = EventSupplier.objects.get_or_create(event=ev, supplier=s)
        n += made
    record(request, "procurement.sourcing.invited", category="data", module="procurement", resource=ev, metadata={"invited": n})
    return n


def publish(request, ctx, ev: SourcingEvent) -> SourcingEvent:
    if ev.status != "draft":
        raise DomainError("Already published.", code="invalid_state", status_code=409)
    if not ev.invites.exists():
        raise DomainError("Invite at least one supplier.", code="validation_error")
    if ev.kind != "rfi" and not ev.lines.exists():
        raise DomainError("Add the items or scope to quote for.", code="validation_error")
    if ev.response_deadline is None or ev.response_deadline <= timezone.now():
        raise DomainError("Set a response deadline in the future.", code="validation_error", details={"responseDeadline": ["Required."]})
    ev.status, ev.published_at = "published", timezone.now()
    ev.save(update_fields=["status", "published_at", "updated_at"])
    record(request, f"procurement.{ev.kind}.published", category="data", module="procurement", resource=ev,
           metadata={"suppliers": ev.invites.count(), "note": "Suppliers are contacted outside Business OS until the supplier portal is enabled."})
    return ev


def _recalc(q: Quotation):
    sub = tax = ZERO
    for ln in q.lines.all():
        base = q2(ln.quantity * ln.unit_price) - ln.discount
        ln.line_total = base
        ln.save(update_fields=["line_total", "updated_at"])
        sub += base
        tax += q2(base * ln.tax_rate / HUNDRED)
    q.subtotal, q.tax = sub, tax
    q.total = sub - q.discount + tax + q.shipping + q.other_charges
    q.tco_total = q.total + sum((dec(v) for k, v in (q.tco or {}).items() if k != "years" and v not in (None, "")), ZERO)
    q.save()


def record_quote(request, ctx, ev: SourcingEvent, data: dict) -> Quotation:
    ctx.require("procurement.quotation.create")
    if ev.status not in ("published", "responses", "evaluation"):
        raise DomainError("Quotes are recorded while the event is open.", code="invalid_state", status_code=409)
    inv = EventSupplier.objects.filter(event=ev, supplier_id=data.get("supplier_id")).select_related("supplier").first()
    if inv is None:
        raise DomainError("Only invited suppliers can quote.", code="validation_error")
    if Quotation.objects.filter(event=ev, supplier=inv.supplier, is_current=True).exists():
        raise DomainError("This supplier already has a quote. Negotiation creates a revision instead of replacing it.", code="duplicate_quote", status_code=409)
    with transaction.atomic():
        q = Quotation.objects.create(organization=ev.organization, number=ledger.next_number(ev.organization, "quote"), event=ev, supplier=inv.supplier,
                                     quote_reference=str(data.get("quote_reference", ""))[:60], quote_date=_date(data.get("quote_date") or timezone.localdate().isoformat()),
                                     valid_until=_date(data.get("valid_until"), required=False), discount=dec(data.get("discount") or 0),
                                     shipping=dec(data.get("shipping") or 0), other_charges=dec(data.get("other_charges") or 0),
                                     payment_terms_days=int(data.get("payment_terms_days") or 30), delivery_days=data.get("delivery_days") or None,
                                     warranty_months=data.get("warranty_months") or None, notes=str(data.get("notes", ""))[:4000], tco=data.get("tco") or {},
                                     received_by=ctx.user)
        ev_lines = list(ev.lines.all())
        for i, ln in enumerate(data.get("lines") or []):
            QuotationLine.objects.create(quotation=q, sourcing_line=ev_lines[i] if i < len(ev_lines) else None, description=str(ln.get("description") or
                                         (ev_lines[i].description if i < len(ev_lines) else "Item"))[:300], quantity=qty(ln.get("quantity") or
                                         (ev_lines[i].quantity if i < len(ev_lines) else 1)), unit_price=dec(ln.get("unit_price"), "unitPrice"),
                                         discount=dec(ln.get("discount") or 0), tax_rate=Decimal(str(ln.get("tax_rate") or 0)))
        if ev.kind != "rfi" and not q.lines.exists():
            raise DomainError("Enter the quoted prices.", code="validation_error")
        _recalc(q)
        inv.status, inv.responded_at = "responded", timezone.now()
        inv.save(update_fields=["status", "responded_at", "updated_at"])
        if ev.status == "published":
            ev.status = "responses"
            ev.save(update_fields=["status", "updated_at"])
    record(request, "procurement.quote.submitted", category="data", module="procurement", resource=q, new={"supplier": inv.supplier.code, "total": q.total})
    return q


def has_conflict(user, supplier) -> ConflictDeclaration | None:
    return ConflictDeclaration.objects.filter(declarant=user, supplier=supplier).exclude(status="mitigated").first()


def score(request, ctx, q: Quotation, criterion: str, value, note="") -> QuotationScore:
    ctx.require("procurement.quotation.evaluate")
    keys = {c["key"]: c for c in q.event.criteria}
    if criterion not in keys or keys[criterion].get("auto"):
        raise DomainError("This criterion is scored automatically or doesn't exist.", code="validation_error")
    if has_conflict(ctx.user, q.supplier):
        raise DomainError("You declared a conflict of interest with this supplier and can't evaluate it.", code="conflict_of_interest", status_code=403)
    v = Decimal(str(value))
    if not (0 <= v <= 100):
        raise DomainError("Scores are 0–100.", code="validation_error")
    s, _ = QuotationScore.objects.update_or_create(quotation=q, criterion=criterion, evaluator=ctx.user, defaults={"score": v, "note": note[:300]})
    if q.event.status in ("published", "responses"):
        SourcingEvent.objects.filter(pk=q.event_id).update(status="evaluation")
    record(request, "procurement.quote.evaluated", category="data", module="procurement", resource=q, new={"criterion": criterion, "score": v})
    return s


def comparison(ev: SourcingEvent) -> dict:
    quotes = list(ev.quotations.filter(is_current=True).select_related("supplier").prefetch_related("scores", "lines"))
    if not quotes:
        return {"criteria": ev.criteria, "rows": [], "quotes": []}
    use_tco = any(q.tco for q in quotes)
    price_basis = {q.pk: (q.tco_total if use_tco else q.total) for q in quotes}
    min_price = min((v for v in price_basis.values() if v > 0), default=None)
    days = [q.delivery_days for q in quotes if q.delivery_days]
    warr = [q.warranty_months for q in quotes if q.warranty_months]
    terms = [q.payment_terms_days for q in quotes if q.payment_terms_days]
    out = []
    for q in quotes:
        scores = {}
        for c in ev.criteria:
            auto = c.get("auto")
            if auto == "price":
                v = (min_price / price_basis[q.pk] * HUNDRED) if min_price and price_basis[q.pk] else ZERO
            elif auto == "delivery":
                v = (Decimal(min(days)) / Decimal(q.delivery_days) * HUNDRED) if days and q.delivery_days else ZERO
            elif auto == "warranty":
                v = (Decimal(q.warranty_months) / Decimal(max(warr)) * HUNDRED) if warr and q.warranty_months else ZERO
            elif auto == "payment_terms":
                v = (Decimal(q.payment_terms_days) / Decimal(max(terms)) * HUNDRED) if terms else ZERO
            else:
                vals = [s.score for s in q.scores.all() if s.criterion == c["key"]]
                v = (sum(vals) / len(vals)) if vals else None
            scores[c["key"]] = None if v is None else q2(v)
        weighted = sum(((scores[c["key"]] or ZERO) * Decimal(str(c["weight"])) / HUNDRED for c in ev.criteria), ZERO)
        complete = all(scores[c["key"]] is not None for c in ev.criteria)
        out.append({"quotation_id": str(q.pk), "number": q.number, "supplier": str(q.supplier), "supplier_id": str(q.supplier_id),
                    "supplier_preference": q.supplier.preference, "total": q.total, "tco_total": q.tco_total, "delivery_days": q.delivery_days,
                    "warranty_months": q.warranty_months, "payment_terms_days": q.payment_terms_days, "valid_until": q.valid_until, "revision": q.revision,
                    "scores": scores, "weighted": q2(weighted), "complete": complete, "status": q.status, "tco": q.tco})
    out.sort(key=lambda r: -r["weighted"])
    for i, r in enumerate(out, start=1):
        r["rank"] = i
    return {"criteria": ev.criteria, "basis": "total cost of ownership" if use_tco else "quoted total", "rows": out}


def negotiate(request, ctx, q: Quotation, *, changes: dict, note: str, participants: str = "") -> Quotation:
    ctx.require("procurement.quotation.evaluate")
    if not q.is_current or q.status in ("awarded", "rejected"):
        raise DomainError("Negotiate on the current quote.", code="invalid_state", status_code=409)
    if not note.strip():
        raise DomainError("Record what was discussed.", code="reason_required")
    with transaction.atomic():
        new = Quotation.objects.create(organization=q.organization, number=f"{q.number.split('/')[0]}/R{q.revision + 1}", event=q.event, supplier=q.supplier,
                                       quote_reference=q.quote_reference, quote_date=timezone.localdate(), valid_until=_date(changes.get("valid_until"), required=False) or q.valid_until,
                                       discount=dec(changes.get("discount", q.discount)), shipping=dec(changes.get("shipping", q.shipping)),
                                       other_charges=dec(changes.get("other_charges", q.other_charges)),
                                       payment_terms_days=int(changes.get("payment_terms_days") or q.payment_terms_days),
                                       delivery_days=changes.get("delivery_days") or q.delivery_days, warranty_months=changes.get("warranty_months") or q.warranty_months,
                                       notes=q.notes, tco=changes.get("tco") or q.tco, revision=q.revision + 1, original=q.original or q, received_by=ctx.user)
        prices = {str(x.get("line_id")): x for x in changes.get("lines") or []}
        for ln in q.lines.all():
            ch = prices.get(str(ln.pk), {})
            QuotationLine.objects.create(quotation=new, sourcing_line=ln.sourcing_line, description=ln.description, quantity=ln.quantity,
                                         unit_price=dec(ch.get("unit_price", ln.unit_price)), discount=dec(ch.get("discount", ln.discount)), tax_rate=ln.tax_rate)
        _recalc(new)
        q.is_current, q.status = False, "superseded"
        q.save(update_fields=["is_current", "status", "updated_at"])
        NegotiationNote.objects.create(event=q.event, quotation=new, previous_total=q.total, new_total=new.total, changes=changes, participants=participants[:300],
                                       note=note[:4000], by=ctx.user)
        SourcingEvent.objects.filter(pk=q.event_id).update(status="negotiation")
    record(request, "procurement.negotiation.recorded", category="data", module="procurement", resource=new, old={"total": q.total}, new={"total": new.total})
    return new


def award(request, ctx, ev: SourcingEvent, q: Quotation, *, reason: str, exception_reason: str = "") -> Award:
    ctx.require("procurement.award.create")
    if ev.kind == "rfi":
        raise DomainError("RFIs gather information; run an RFQ or RFP to award.", code="invalid_state", status_code=409)
    if ev.status in ("awarded", "cancelled", "closed") or not q.is_current or q.event_id != ev.pk:
        raise DomainError("This quote can't be awarded.", code="invalid_state", status_code=409)
    if len(reason.strip()) < 20:
        raise DomainError("Record why this supplier was selected.", code="reason_required")
    if q.valid_until and q.valid_until < timezone.localdate():
        raise DomainError("This quote has expired. Ask the supplier to extend it.", code="quote_expired", status_code=409)
    pol = policy(ev.organization)
    n_quotes = ev.quotations.filter(is_current=True).count()
    pr = ev.purchase_request
    threshold = ev.category.rfq_required_above or pol.rfq_required_above
    if n_quotes < pol.min_quotes and q.total >= threshold and not (pr and pr.single_source):
        if not exception_reason.strip():
            raise DomainError(f"Only {n_quotes} quote(s) for a purchase above {threshold}; policy needs {pol.min_quotes}. Give a reason to record an exception.",
                              code="insufficient_quotes", status_code=409)
        raise_exception(ev.organization, "no_competitive_quotes", source_type="procurement.event", source_id=ev.pk, label=ev.number, amount=q.total,
                        description=f"{n_quotes} of {pol.min_quotes} quotes", reason=exception_reason, owner=ctx.user)
    # Savings are measured before tax: GST is recoverable input credit, not money Click saves.
    initial = (q.original or q).subtotal
    benchmark = pr.estimated_total if pr else None
    final = q.subtotal
    if q.revision > 1:
        method, savings = "negotiated", max(ZERO, initial - final)
    elif n_quotes >= 2:
        others = [x.subtotal for x in ev.quotations.filter(is_current=True).exclude(pk=q.pk)]
        method, savings = "competitive_bid", max(ZERO, (sum(others) / len(others)) - final) if others else ZERO
    else:
        method, savings = "", ZERO
    with transaction.atomic():
        a = Award.objects.create(organization=ev.organization, number=ledger.next_number(ev.organization, "award"), event=ev, quotation=q, supplier=q.supplier,
                                 amount=q.total, reason=reason[:4000], evaluation=_jsonable(comparison(ev)), benchmark=benchmark, initial_quote=initial,
                                 savings=q2(savings), savings_method=method, created_by=ctx.user)
        a.approval = engine.submit(request, "procurement.award", title=f"Award {ev.number} to {q.supplier}", amount=q.total, description=reason,
                                   department=pr.department if pr else None, org_unit=pr.org_unit if pr else None, resource_type="procurement.award",
                                   resource_id=str(a.pk))
        a.save(update_fields=["approval", "updated_at"])
    return a


def _jsonable(v):
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, Date):
        return v.isoformat()
    return v


@on_decision("procurement.award")
def _award_decided(req, outcome):
    a = Award.objects.filter(pk=req.resource_id, status="pending_approval").select_related("event", "quotation", "supplier", "event__purchase_request").first()
    if a is None:
        return
    if outcome != "approved":
        if outcome in ("rejected", "cancelled"):
            a.status = "rejected"
            a.save(update_fields=["status", "updated_at"])
        return
    with transaction.atomic():
        a.status = "approved"
        a.save(update_fields=["status", "updated_at"])
        ev = a.event
        ev.quotations.filter(is_current=True).exclude(pk=a.quotation_id).update(status="rejected")
        Quotation.objects.filter(pk=a.quotation_id).update(status="awarded")
        ev.status = "awarded"
        ev.save(update_fields=["status", "updated_at"])
        po = po_from_quote(a.quotation, a.created_by, pr=ev.purchase_request, award=a)
    notify(a.created_by, "approval_result", f"Award approved — draft {po.number} created", link=f"/procurement/orders?open={po.pk}", module="procurement")


# =====================================================================================================================
# Purchase orders
# =====================================================================================================================
def tax_rule_for(org, rate, on=None):
    """The active GST rule for a quoted rate, so Finance books input tax on the bill. None for 0% or when no rule exists
    (the three-way match then flags the difference instead of silently dropping the tax)."""
    from apps.finance.models import TaxRule

    rate = Decimal(str(rate or 0))
    if rate <= 0:
        return None
    on = on or timezone.localdate()
    return (TaxRule.objects.filter(organization=org, is_active=True, kind="gst", rate=rate, effective_from__lte=on)
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on)).order_by("-version").first())


def _po_lines_from(lines, category):
    return [dict(description=ln["description"], quantity=ln["quantity"], uom=ln.get("uom", "each"), unit_price=ln["unit_price"], discount=ln.get("discount", ZERO),
                 tax_rate=ln.get("tax_rate", ZERO), tax_rule=ln.get("tax_rule") or tax_rule_for(category.organization, ln.get("tax_rate")),
                 is_service=category.is_service, is_capex=category.expenditure == "capex", is_inventory=category.is_inventory) for ln in lines]


def _create_po(org, *, supplier, category, created_by, lines, pr=None, event=None, award=None, contract=None, shipping=ZERO, discount=ZERO, **extra) -> PurchaseOrder:
    entity = ledger.default_entity(org)
    po = PurchaseOrder.objects.create(organization=org, number=ledger.next_number(org, "po"), supplier=supplier, entity=entity, category=category,
                                      purchase_request=pr, event=event, award=award, contract=contract, created_by=created_by,
                                      department=pr.department if pr else None, org_unit=pr.org_unit if pr else None, cost_center=pr.cost_center if pr else None,
                                      project=pr.project if pr else "", payment_terms_days=supplier.payment_terms_days, shipping=shipping, discount=discount,
                                      is_emergency=bool(pr and pr.is_emergency), expected_delivery=(pr.required_by if pr else None), **extra)
    for i, ln in enumerate(lines, start=1):
        PurchaseOrderLine.objects.create(order=po, line_no=i, **ln)
    recalc_po(po)
    return po


def recalc_po(po: PurchaseOrder):
    sub = tax = ZERO
    for ln in po.lines.all():
        base = q2(ln.quantity * ln.unit_price) - ln.discount
        ln.line_total = base
        ln.save(update_fields=["line_total", "updated_at"])
        sub += base
        tax += q2(base * ln.tax_rate / HUNDRED)
    po.subtotal, po.tax = sub, tax
    po.total = sub - po.discount + tax + po.shipping
    po.save(update_fields=["subtotal", "tax", "total", "updated_at"])


def po_from_quote(q: Quotation, user, *, pr=None, award=None) -> PurchaseOrder:
    lines = [{"description": ln.description, "quantity": ln.quantity, "unit_price": ln.unit_price, "discount": ln.discount, "tax_rate": ln.tax_rate}
             for ln in q.lines.all()]
    po = _create_po(q.organization, supplier=q.supplier, category=q.event.category, created_by=user, lines=_po_lines_from(lines, q.event.category), pr=pr,
                    event=q.event, award=award, shipping=q.shipping + q.other_charges, discount=q.discount, warranty=f"{q.warranty_months} months" if q.warranty_months else "")
    po.payment_terms_days = q.payment_terms_days
    if q.delivery_days:
        po.expected_delivery = timezone.localdate() + timedelta(days=q.delivery_days)
    po.save(update_fields=["payment_terms_days", "expected_delivery", "updated_at"])
    return po


def create_po(request, ctx, data: dict) -> PurchaseOrder:
    """Direct PO from an approved request (small value, single source, emergency, or under a contract); otherwise sourcing first."""
    ctx.require("procurement.order.create")
    org = ctx.organization
    pr = PurchaseRequest.objects.filter(organization=org, pk=data.get("purchase_request_id")).select_related("category").first()
    if pr is None or pr.status not in ("approved", "sourcing"):
        raise DomainError("Raise purchase orders from an approved purchase request.", code="invalid_state", status_code=409)
    supplier = Supplier.objects.filter(organization=org, pk=data.get("supplier_id")).first()
    if supplier is None:
        raise DomainError("Choose the supplier.", code="validation_error")
    pol = policy(org)
    if pol.requester_not_buyer and pr.requester_id == ctx.user.pk:
        raise DomainError("Segregation of duties: the requester can't raise the purchase order.", code="sod_blocked", status_code=403)
    contract = ProcurementContract.objects.filter(organization=org, pk=data.get("contract_id"), supplier=supplier, status="active").first() if data.get("contract_id") else None
    threshold = pr.category.rfq_required_above or pol.rfq_required_above
    if pr.estimated_total >= threshold and not (pr.single_source or pr.is_emergency or contract):
        if not str(data.get("exception_reason", "")).strip():
            raise DomainError(f"Purchases of {threshold} or more need competitive sourcing (RFQ), a contract, or an approved exception.",
                              code="sourcing_required", status_code=409)
        raise_exception(org, "no_competitive_quotes", source_type="procurement.request", source_id=pr.pk, label=pr.number, amount=pr.estimated_total,
                        description="Direct PO without competitive sourcing", reason=str(data["exception_reason"]), owner=ctx.user)
    from apps.finance.models import TaxRule

    rule = TaxRule.objects.filter(organization=org, pk=data.get("tax_rule_id")).first() if data.get("tax_rule_id") else None
    lines = [{"description": ln.description, "quantity": ln.quantity, "uom": ln.uom, "unit_price": dec(
        next((x.get("unit_price") for x in data.get("lines") or [] if str(x.get("line_id")) == str(ln.pk)), None) or ln.estimated_unit_cost),
        "tax_rate": rule.rate if rule else ZERO, "tax_rule": rule} for ln in pr.lines.all()]
    with transaction.atomic():
        po = _create_po(org, supplier=supplier, category=pr.category, created_by=ctx.user, lines=_po_lines_from(lines, pr.category), pr=pr, contract=contract,
                        delivery_location=str(data.get("delivery_location", ""))[:200], terms=str(data.get("terms", ""))[:4000])
    record(request, "procurement.order.created", category="data", module="procurement", resource=po, new={"total": po.total, "supplier": supplier.code})
    return po


def submit_po(request, ctx, po: PurchaseOrder, *, exception_reason: str = "") -> PurchaseOrder:
    ctx.require("procurement.order.create")
    if po.status != "draft":
        raise DomainError("Only drafts can be submitted.", code="invalid_state", status_code=409)
    pol = policy(po.organization)
    if not po.supplier.can_be_ordered_from:
        if pol.block_unapproved_suppliers or po.supplier.preference == "blocked":
            raise DomainError(f"{po.supplier} is not an active, approved supplier ({po.supplier.get_status_display()}, {po.supplier.get_preference_display()}).",
                              code="supplier_not_approved", status_code=409)
        raise_exception(po.organization, "supplier_onboarding_incomplete", source_type="procurement.order", source_id=po.pk, label=po.number,
                        amount=po.total, description=str(po.supplier), reason=exception_reason, owner=ctx.user)
    if not po.lines.exists() or po.total <= 0:
        raise DomainError("Add lines with prices.", code="validation_error")
    po.approval = engine.submit(request, "procurement.order", title=f"{po.number} · {po.supplier}", amount=po.total, department=po.department,
                                org_unit=po.org_unit, description=f"{po.category.name}{' · EMERGENCY' if po.is_emergency else ''}" +
                                                                  (f" · from {po.purchase_request.number}" if po.purchase_request_id else ""),
                                resource_type="procurement.order", resource_id=str(po.pk), priority="critical" if po.is_emergency else "normal")
    po.status = "pending_approval"
    po.save(update_fields=["approval", "status", "updated_at"])
    return po


@on_decision("procurement.order")
def _po_decided(req, outcome):
    po = PurchaseOrder.objects.filter(pk=req.resource_id, status="pending_approval").select_related("purchase_request", "category").first()
    if po is None:
        return
    if outcome == "approved":
        with transaction.atomic():
            po.status, po.approved_at = "approved", timezone.now()
            po.save(update_fields=["status", "approved_at", "updated_at"])
            PurchaseOrderVersion.objects.get_or_create(order=po, version=1, defaults={"snapshot": po_snapshot(po), "reason": "Approved", "by": _decider(req)})
            pr = po.purchase_request
            pr_commit = None
            if pr is not None:
                from apps.finance.models import BudgetCommitment

                pr_commit = BudgetCommitment.objects.filter(source_type="procurement.request", source_id=str(pr.pk)).first()
                PurchaseRequest.objects.filter(pk=pr.pk).update(status="ordered")
            budget_id = pr_commit.budget_id if pr_commit else None
            if budget_id is None:
                b = fin.find_budget(po.organization, department=po.department, org_unit=po.org_unit, cost_center=po.cost_center,
                                    category=po.category.budget_category)
                budget_id = b.pk if b else None
            if pr_commit:
                fin.release("procurement.request", pr.pk)
            if budget_id:
                fin.reserve(po.organization, budget_id=budget_id, amount=po.total, source_module="procurement", source_type="procurement.order",
                            source_id=po.pk, label=po.number)
    elif outcome in ("rejected", "cancelled"):
        po.status = "draft"
        po.save(update_fields=["status", "updated_at"])


def po_snapshot(po: PurchaseOrder) -> dict:
    return _jsonable({"version": po.version, "supplier": po.supplier.code, "total": po.total, "expected_delivery": po.expected_delivery, "terms": po.terms,
                      "lines": [{"line_no": ln.line_no, "description": ln.description, "quantity": ln.quantity, "unit_price": ln.unit_price, "tax_rate": ln.tax_rate}
                                for ln in po.lines.all()]})


def send_po(request, ctx, po: PurchaseOrder) -> PurchaseOrder:
    ctx.require("procurement.order.create")
    if po.status != "approved":
        raise DomainError("Only approved orders can be sent.", code="invalid_state", status_code=409)
    po.status, po.sent_at = "sent", timezone.now()
    po.save(update_fields=["status", "sent_at", "updated_at"])
    record(request, "procurement.order.sent", category="data", module="procurement", resource=po, new={"to": po.supplier.email or "supplier"})
    return po


def confirm_po(request, ctx, po: PurchaseOrder, *, result: str, note: str = "", confirmed_delivery=None) -> PurchaseOrder:
    """Records the supplier's confirmation. Changes go back to procurement as an amendment — never silently applied."""
    ctx.require("procurement.order.create")
    if po.status not in ("sent", "approved"):
        raise DomainError("Confirm orders that were sent.", code="invalid_state", status_code=409)
    if result not in ("accepted", "accepted_with_changes", "rejected", "partially_accepted"):
        raise DomainError("Choose the supplier's response.", code="validation_error")
    po.confirmation, po.confirmation_note = result, note[:500]
    if confirmed_delivery:
        po.confirmed_delivery = _date(confirmed_delivery)
    if result == "accepted":
        po.status = "confirmed"
    else:
        notify(po.created_by, "business", f"{po.number}: supplier {result.replace('_', ' ')}", body=note[:200] or "Review and amend the order.",
               link=f"/procurement/orders?open={po.pk}", module="procurement", priority="important")
    po.save()
    record(request, "procurement.order.confirmation", category="data", module="procurement", resource=po, new={"result": result, "note": note[:200]})
    return po


def update_delivery(request, ctx, po: PurchaseOrder, data: dict) -> PurchaseOrder:
    ctx.require("procurement.order.edit")
    for f in ("carrier", "tracking_number", "delivery_status"):
        if f in data:
            setattr(po, f, str(data[f])[:80])
    if data.get("confirmed_delivery"):
        po.confirmed_delivery = _date(data["confirmed_delivery"])
    po.save()
    return po


def request_amendment(request, ctx, po: PurchaseOrder, *, reason: str, changes: dict) -> PurchaseOrderAmendment:
    ctx.require("procurement.order.edit")
    if not po.is_locked or po.status in ("completed", "cancelled", "closed"):
        raise DomainError("Drafts are edited directly; finished orders can't be amended.", code="invalid_state", status_code=409)
    if not reason.strip():
        raise DomainError("Give the reason for the amendment.", code="reason_required")
    if po.amendments.filter(status="pending_approval").exists():
        raise DomainError("An amendment is already waiting for approval.", code="duplicate_request", status_code=409)
    lines = {str(ln.pk): ln for ln in po.lines.all()}
    new_total = ZERO
    for ln_id, ln in lines.items():
        ch = next((x for x in changes.get("lines") or [] if str(x.get("line_id")) == ln_id), {})
        q_, p_ = qty(ch.get("quantity", ln.quantity)), dec(ch.get("unit_price", ln.unit_price))
        if q_ < ln.received_qty:
            raise DomainError(f"Line {ln.line_no}: can't reduce below the {ln.received_qty} already received.", code="validation_error")
        base = q2(q_ * p_) - ln.discount
        new_total += base + q2(base * ln.tax_rate / HUNDRED)
    new_total += po.shipping - po.discount
    with transaction.atomic():
        am = PurchaseOrderAmendment.objects.create(order=po, from_version=po.version, reason=reason[:300], changes=_jsonable(changes), new_total=new_total,
                                                   requested_by=ctx.user)
        am.approval = engine.submit(request, "procurement.amendment", title=f"Amend {po.number} (v{po.version}→v{po.version + 1})", amount=max(new_total, Decimal("0.01")),
                                    description=f"{reason}\nTotal {po.total} → {new_total}", department=po.department, org_unit=po.org_unit,
                                    resource_type="procurement.amendment", resource_id=str(am.pk))
        am.save(update_fields=["approval", "updated_at"])
    return am


@on_decision("procurement.amendment")
def _amendment_decided(req, outcome):
    am = PurchaseOrderAmendment.objects.filter(pk=req.resource_id, status="pending_approval").select_related("order").first()
    if am is None:
        return
    if outcome != "approved":
        if outcome in ("rejected", "cancelled"):
            am.status = "rejected"
            am.save(update_fields=["status", "updated_at"])
        return
    po = am.order
    with transaction.atomic():
        PurchaseOrderVersion.objects.get_or_create(order=po, version=po.version, defaults={"snapshot": po_snapshot(po), "reason": "Before amendment", "by": _decider(req)})
        for ch in am.changes.get("lines") or []:
            ln = po.lines.filter(pk=ch.get("line_id")).first()
            if ln:
                ln.quantity, ln.unit_price = qty(ch.get("quantity", ln.quantity)), dec(ch.get("unit_price", ln.unit_price))
                ln.save(update_fields=["quantity", "unit_price", "updated_at"])
        if am.changes.get("expected_delivery"):
            po.expected_delivery = _date(am.changes["expected_delivery"])
        if am.changes.get("terms"):
            po.terms = str(am.changes["terms"])[:4000]
        po.version += 1
        po.save()
        recalc_po(po)
        PurchaseOrderVersion.objects.create(order=po, version=po.version, snapshot=po_snapshot(po), reason=am.reason, by=_decider(req))
        am.status = "approved"
        am.save(update_fields=["status", "updated_at"])
        from apps.finance.models import BudgetCommitment

        c = BudgetCommitment.objects.filter(source_type="procurement.order", source_id=str(po.pk)).first()
        if c:
            fin.reserve(po.organization, budget_id=c.budget_id, amount=po.total, source_module="procurement", source_type="procurement.order",
                        source_id=po.pk, label=po.number)
    record(None, "procurement.order.amended", category="data", module="procurement", resource=po, organization=po.organization, actor=_decider(req),
           new={"version": po.version, "total": po.total, "reason": am.reason})


def cancel_po(request, ctx, po: PurchaseOrder, reason: str) -> PurchaseOrder:
    ctx.require("procurement.order.edit")
    if po.status in ("cancelled", "completed", "closed") or po.lines.filter(received_qty__gt=0).exists() or po.lines.filter(invoiced_qty__gt=0).exists():
        raise DomainError("Orders with receipts or invoices can't be cancelled; close them instead.", code="invalid_state", status_code=409)
    if not reason.strip():
        raise DomainError("Give a reason.", code="reason_required")
    po.status, po.cancel_reason = "cancelled", reason[:300]
    po.save(update_fields=["status", "cancel_reason", "updated_at"])
    fin.release("procurement.order", po.pk)
    record(request, "procurement.order.cancelled", category="data", module="procurement", resource=po, new={"reason": reason})
    return po


def close_po(request, ctx, po: PurchaseOrder, reason: str = "") -> PurchaseOrder:
    ctx.require("procurement.order.edit")
    if po.status in ("cancelled", "closed", "draft", "pending_approval"):
        raise DomainError("This order can't be closed.", code="invalid_state", status_code=409)
    po.status, po.closed_at = "closed", timezone.now()
    po.save(update_fields=["status", "closed_at", "updated_at"])
    fin.release("procurement.order", po.pk)
    record(request, "procurement.order.closed", category="data", module="procurement", resource=po, new={"reason": reason})
    return po


def _refresh_po_status(po: PurchaseOrder):
    lines = list(po.lines.all())
    goods = [ln for ln in lines if not ln.is_service]
    services = [ln for ln in lines if ln.is_service]
    received_all = all(ln.accepted_qty >= ln.quantity for ln in goods) and all(ln.service_accepted_amount >= ln.line_total for ln in services)
    received_any = any(ln.received_qty > 0 for ln in goods) or any(ln.service_accepted_amount > 0 for ln in services)
    invoiced_all = all(ln.invoiced_qty >= ln.quantity for ln in lines)
    invoiced_any = any(ln.invoiced_qty > 0 for ln in lines)
    if po.status in ("cancelled", "closed"):
        return
    if received_all and invoiced_all:
        po.status = "completed"
    elif invoiced_all:
        po.status = "invoiced"
    elif invoiced_any:
        po.status = "partially_invoiced"
    elif received_all:
        po.status = "received"
    elif received_any:
        po.status = "partially_received"
    po.save(update_fields=["status", "updated_at"])


# =====================================================================================================================
# Receiving
# =====================================================================================================================
def receive(request, ctx, po: PurchaseOrder, lines: list[dict], *, received_on=None, delivery_note="", condition="", evidence="", inspect=False) -> GoodsReceipt:
    ctx.require("procurement.receipt.create", **({"unit": po.org_unit_id} if po.org_unit_id else {}))
    if po.status not in ("approved", "sent", "confirmed", "partially_received", "partially_invoiced"):
        raise DomainError("Receive against an approved, open purchase order.", code="invalid_state", status_code=409)
    if policy(po.organization).receiver_not_buyer and po.created_by_id == ctx.user.pk:
        raise DomainError("Segregation of duties: the buyer who raised the order can't receive it.", code="sod_blocked", status_code=403)
    by_id = {str(ln.pk): ln for ln in po.lines.filter(is_service=False)}
    rows = [x for x in lines if x.get("line_id") in by_id and qty(x.get("received_qty") or 0) > 0]
    if not rows:
        raise DomainError("Enter what was received.", code="validation_error")
    with transaction.atomic():
        grn = GoodsReceipt.objects.create(organization=po.organization, number=ledger.next_number(po.organization, "grn"), order=po, received_by=ctx.user,
                                          received_on=_date(received_on, required=False) or timezone.localdate(), delivery_note=delivery_note[:80],
                                          condition=condition[:200], evidence=evidence[:300], status="inspection" if inspect else "accepted")
        for x in rows:
            ln = PurchaseOrderLine.objects.select_for_update().get(pk=by_id[x["line_id"]].pk)
            rec, rej, dmg = qty(x.get("received_qty")), qty(x.get("rejected_qty") or 0), qty(x.get("damaged_qty") or 0)
            if rej + dmg > rec:
                raise DomainError(f"Line {ln.line_no}: rejected + damaged exceeds received.", code="validation_error")
            if ln.received_qty - ln.rejected_qty + rec - rej - dmg > ln.quantity:
                raise DomainError(f"Line {ln.line_no}: more than ordered ({ln.quantity}). Amend the order first.", code="over_receipt", status_code=409)
            GoodsReceiptLine.objects.create(receipt=grn, order_line=ln, received_qty=rec, rejected_qty=rej, damaged_qty=dmg, batch=str(x.get("batch", ""))[:60],
                                            serials=x.get("serials") or [], note=str(x.get("note", ""))[:200])
            ln.received_qty += rec
            ln.rejected_qty += rej + dmg
            ln.save(update_fields=["received_qty", "rejected_qty", "updated_at"])
        _refresh_po_status(po)
        if not inspect:
            _after_acceptance(grn)
    record(request, "procurement.receipt.created", category="data", module="procurement", resource=grn, new={"order": po.number, "lines": len(rows)})
    return grn


def _after_acceptance(grn: GoodsReceipt):
    """Inventory and asset hand-offs for accepted goods."""
    inv_lines = [rl for rl in grn.lines.select_related("order_line") if rl.order_line.is_inventory and rl.received_qty - rl.rejected_qty - rl.damaged_qty > 0]
    if inv_lines:
        if INVENTORY_RECEIVERS:
            for fn in INVENTORY_RECEIVERS:
                fn(grn, inv_lines)
            grn.inventory_status = "posted"
        else:
            grn.inventory_status = "pending"  # Inventory module not connected: stock is NOT updated here (Inventory owns quantities)
        grn.save(update_fields=["inventory_status", "updated_at"])
    from apps.finance.models import FixedAsset

    for rl in grn.lines.select_related("order_line", "order_line__order"):
        ln = rl.order_line
        accepted = rl.received_qty - rl.rejected_qty - rl.damaged_qty
        if not ln.is_capex or accepted <= 0:
            continue
        po = ln.order
        FixedAsset.objects.get_or_create(source_type="procurement.grn_line", source_id=str(rl.pk), defaults={
            "organization": po.organization, "entity": po.entity, "number": ledger.next_number(po.organization, "asset"),
            "name": f"{ln.description} ×{accepted.normalize():f}"[:160], "category": "computers" if "TECH" in po.category.code else
            "furniture" if "FURN" in po.category.code else "vehicles" if po.category.code == "VEH" else "office_equipment" if po.category.code.startswith("OFF") else "other",
            "acquisition_date": grn.received_on, "cost": q2(accepted * ln.unit_price), "department": po.department, "org_unit": po.org_unit,
            "cost_center": po.cost_center, "source_module": "procurement", "status": "draft"})


def inspect(request, ctx, grn: GoodsReceipt, *, result: str, rejections: dict, notes: str = "", corrective_action: str = "", evidence: str = "") -> GoodsReceipt:
    ctx.require("procurement.receipt.inspect")
    if grn.status != "inspection":
        raise DomainError("This receipt isn't waiting for inspection.", code="invalid_state", status_code=409)
    if grn.received_by_id == ctx.user.pk:
        raise DomainError("The receiver can't also inspect the same delivery.", code="sod_blocked", status_code=403)
    if result not in ("accepted", "rejected", "partial"):
        raise DomainError("Choose the result.", code="validation_error")
    if result != "accepted" and not notes.strip():
        raise DomainError("Record what was wrong.", code="reason_required")
    with transaction.atomic():
        for rl in grn.lines.select_related("order_line"):
            extra = rl.received_qty - rl.rejected_qty - rl.damaged_qty if result == "rejected" else qty(rejections.get(str(rl.pk)) or 0) if result == "partial" else ZERO
            if extra:
                if extra > rl.received_qty - rl.rejected_qty - rl.damaged_qty:
                    raise DomainError("Rejected more than was accepted at receipt.", code="validation_error")
                rl.rejected_qty += extra
                rl.save(update_fields=["rejected_qty", "updated_at"])
                PurchaseOrderLine.objects.filter(pk=rl.order_line_id).update(rejected_qty=rl.order_line.rejected_qty + extra)
        QualityInspection.objects.create(receipt=grn, result=result, inspector=ctx.user, notes=notes[:4000], corrective_action=corrective_action[:4000], evidence=evidence[:300])
        grn.status = {"accepted": "accepted", "rejected": "rejected", "partial": "partial"}[result]
        grn.save(update_fields=["status", "updated_at"])
        _refresh_po_status(grn.order)
        if result != "rejected":
            _after_acceptance(grn)
    record(request, "procurement.receipt.inspected", category="data", module="procurement", resource=grn, new={"result": result})
    return grn


def submit_service_receipt(request, ctx, po: PurchaseOrder, data: dict) -> ServiceReceipt:
    ctx.require("procurement.receipt.create")
    ln = po.lines.filter(pk=data.get("line_id"), is_service=True).first()
    if ln is None:
        raise DomainError("Choose the service line.", code="validation_error")
    amount = dec(data.get("amount"))
    if amount <= 0 or ln.service_accepted_amount + amount > ln.line_total:
        raise DomainError("The value must be positive and within the ordered amount.", code="validation_error")
    if len(str(data.get("deliverables", "")).strip()) < 5:
        raise DomainError("Describe what was delivered.", code="validation_error")
    sr = ServiceReceipt.objects.create(organization=po.organization, number=ledger.next_number(po.organization, "srn"), order=po, order_line=ln,
                                       period_from=_date(data.get("period_from"), required=False), period_to=_date(data.get("period_to"), required=False),
                                       deliverables=str(data["deliverables"])[:4000], milestone=str(data.get("milestone", ""))[:120],
                                       completion_pct=Decimal(str(data.get("completion_pct") or 100)), amount=amount, evidence=str(data.get("evidence", ""))[:300],
                                       submitted_by=ctx.user)
    pr = po.purchase_request
    target = pr.requester if pr and pr.requester_id != ctx.user.pk else None
    if target:
        notify(target, "task_assigned", f"Confirm service delivery: {po.number}", body=sr.deliverables[:200], link=f"/procurement/receiving?tab=services",
               module="procurement")
    return sr


def decide_service_receipt(request, ctx, sr: ServiceReceipt, decision: str, note: str = "") -> ServiceReceipt:
    po = sr.order
    is_requester = po.purchase_request_id and po.purchase_request.requester_id == ctx.user.pk
    if not (is_requester or ctx.has("procurement.receipt.inspect")):
        raise DomainError("Only the requester or a quality inspector can accept services.", code="permission_denied", status_code=403)
    if ctx.user.pk in (sr.submitted_by_id, po.created_by_id):
        raise DomainError("Segregation of duties: someone other than the buyer or submitter accepts the service.", code="sod_blocked", status_code=403)
    if sr.status != "submitted" or decision not in ("accepted", "rejected"):
        raise DomainError("Invalid decision.", code="invalid_state", status_code=409)
    if decision == "rejected" and not note.strip():
        raise DomainError("Say why it is rejected.", code="reason_required")
    with transaction.atomic():
        sr.status, sr.decided_by, sr.decision_note = decision, ctx.user, note[:300]
        sr.save()
        if decision == "accepted" and sr.order_line_id:
            PurchaseOrderLine.objects.filter(pk=sr.order_line_id).update(service_accepted_amount=sr.order_line.service_accepted_amount + sr.amount)
            _refresh_po_status(po)
    record(request, f"procurement.service.{decision}", category="data", module="procurement", resource=sr, new={"amount": sr.amount})
    return sr


# =====================================================================================================================
# Supplier invoices → Finance (Finance owns AP; Procurement validates the match)
# =====================================================================================================================
def record_supplier_invoice(request, ctx, po: PurchaseOrder, data: dict):
    ctx.require("finance.bill.create")
    if po.status in ("draft", "pending_approval", "cancelled"):
        raise DomainError("Record invoices against an approved order.", code="invalid_state", status_code=409)
    if not str(data.get("supplier_invoice_number", "")).strip():
        raise DomainError("Enter the supplier's invoice number.", code="validation_error")
    key = "inventory" if po.category.is_inventory else ("asset_clearing" if po.category.expenditure == "capex" else po.category.finance_account_key)
    lines = []
    for ln in po.lines.select_related("tax_rule"):
        x = next((r for r in data.get("lines") or [] if str(r.get("line_id")) == str(ln.pk)), None)
        q_ = qty(x.get("quantity")) if x else (ln.accepted_qty - ln.invoiced_qty if not ln.is_service else Decimal("1"))
        price = dec(x.get("unit_price")) if x else (ln.unit_price if not ln.is_service else max(ZERO, ln.service_accepted_amount - ln.invoiced_qty * ln.unit_price))
        if q_ <= 0:
            continue
        rule = ln.tax_rule or tax_rule_for(po.organization, ln.tax_rate)
        lines.append({"description": ln.description, "quantity": q_, "unit_price": price, "account_key": key, "tax_rule_id": str(rule.pk) if rule else None,
                      "source_line_id": str(ln.pk)})
    if not lines:
        raise DomainError("Nothing on this order is ready to invoice yet (receive it first).", code="nothing_to_invoice", status_code=409)
    inv = fin.create_invoice(request, ctx, {"party_name": str(po.supplier), "party_type": "supplier", "party_id": str(po.supplier_id),
                                            "supplier_invoice_number": data["supplier_invoice_number"], "issue_date": data.get("issue_date"),
                                            "terms_days": po.payment_terms_days, "lines": lines, "cost_center_id": str(po.cost_center_id) if po.cost_center_id else None},
                             kind="vendor_bill", source={"module": "procurement", "type": "procurement.order", "id": po.pk, "label": po.number, "match": True})
    if po.department_id or po.org_unit_id:
        inv.department, inv.org_unit = po.department, po.org_unit
        inv.save(update_fields=["department", "org_unit", "updated_at"])
    fin.run_match(inv)
    return inv


def match_po_invoice(inv) -> dict:
    """Three-way (PO + receipt + invoice) or two-way (PO + invoice + service acceptance) depending on the category."""
    po = PurchaseOrder.objects.filter(pk=inv.source_id).select_related("supplier", "category").first()
    if po is None:
        return {"status": "exception", "issues": ["Purchase order not found"], "mode": "unknown"}
    pol = policy(po.organization)
    tol_pct, tol_amt = pol.match_tolerance_pct, pol.match_tolerance_amount
    mode = po.category.match_mode
    issues = []
    if inv.party_id and inv.party_id != str(po.supplier_id):
        issues.append("Supplier on the invoice differs from the PO")
    if po.status in ("cancelled", "draft", "pending_approval"):
        issues.append(f"PO is {po.get_status_display().lower()}")
    lines = {str(ln.pk): ln for ln in po.lines.all()}
    for il in inv.lines.all():
        ln = lines.get(il.source_line_id)
        if ln is None:
            issues.append(f"“{il.description}” isn't on the PO")
            continue
        if mode != "none" and abs(il.unit_price - ln.unit_price) > max(ln.unit_price * tol_pct / HUNDRED, ZERO) and not ln.is_service:
            issues.append(f"Line {ln.line_no}: price {il.unit_price} vs PO {ln.unit_price}")
        if il.tax_rate != ln.tax_rate:
            issues.append(f"Line {ln.line_no}: tax {il.tax_rate}% vs PO {ln.tax_rate}%")
        if ln.is_service:
            billed_before = ln.invoiced_qty * ln.unit_price
            if il.line_total > ln.service_accepted_amount - billed_before + tol_amt:
                issues.append(f"Line {ln.line_no}: billed {il.line_total} but only {ln.service_accepted_amount - billed_before} of service accepted")
        elif mode == "three_way":
            if il.quantity > ln.accepted_qty - ln.invoiced_qty:
                issues.append(f"Line {ln.line_no}: invoiced {il.quantity.normalize():f} but {(ln.accepted_qty - ln.invoiced_qty).normalize():f} accepted and not yet invoiced")
        elif mode == "two_way" and il.quantity > ln.quantity - ln.invoiced_qty:
            issues.append(f"Line {ln.line_no}: invoiced more than ordered")
    already = sum((i.total for i in type(inv).objects.filter(source_type="procurement.order", source_id=inv.source_id).exclude(pk=inv.pk)
                   .exclude(status__in=["void", "rejected"])), ZERO)
    if already + inv.total > po.total + tol_amt:
        issues.append(f"Invoices ({already + inv.total}) exceed the PO total ({po.total})")
    status = "not_required" if mode == "none" else ("matched" if not issues else "exception")
    if issues:
        raise_exception(po.organization, "three_way_mismatch", source_type="finance.invoice", source_id=inv.pk, label=f"{po.number} / {inv.supplier_invoice_number}",
                        amount=inv.total, description="; ".join(issues)[:500], detected=True)
    return {"status": status, "mode": mode, "issues": issues, "po": po.number}


def _bill_approved(inv):
    if inv.source_type != "procurement.order":
        return
    po = PurchaseOrder.objects.filter(pk=inv.source_id).first()
    if po is None:
        return
    with transaction.atomic():
        for il in inv.lines.all():
            ln = po.lines.filter(pk=il.source_line_id).first()
            if ln:
                PurchaseOrderLine.objects.filter(pk=ln.pk).update(invoiced_qty=ln.invoiced_qty + (il.quantity if not ln.is_service else il.line_total / ln.unit_price if ln.unit_price else ZERO))
        fin.consume("procurement.order", po.pk, inv.subtotal)
        _refresh_po_status(po)


fin.MATCHERS["procurement.order"] = match_po_invoice
if _bill_approved not in fin.BILL_APPROVED_HOOKS:
    fin.BILL_APPROVED_HOOKS.append(_bill_approved)


# =====================================================================================================================
# Contracts, recurring purchases, exceptions, conflicts
# =====================================================================================================================
def renewal_decision(request, ctx, c: ProcurementContract, decision: str, note: str) -> ProcurementContract:
    ctx.require("procurement.contract.manage")
    if decision not in ("renew", "renegotiate", "resource", "terminate") or not note.strip():
        raise DomainError("Choose renew, renegotiate, re-source or terminate, with your review notes.", code="validation_error")
    c.renewal_decision, c.decision_note = decision, note[:4000]
    if decision == "terminate":
        c.status = "terminated"
    c.save()
    record(request, "procurement.contract.renewal_decision", category="data", module="procurement", resource=c, new={"decision": decision})
    return c


def submit_exception(request, ctx, exc: ProcurementException, reason: str) -> ProcurementException:
    ctx.require("procurement.exception.manage")
    if exc.status != "open":
        raise DomainError("Only open exceptions can be sent for approval.", code="invalid_state", status_code=409)
    if not reason.strip():
        raise DomainError("Give the justification.", code="reason_required")
    exc.reason = reason[:4000]
    exc.approval = engine.submit(request, "procurement.exception", title=f"{exc.number}: {exc.get_kind_display()}", description=f"{exc.description}\n\n{reason}",
                                 resource_type="procurement.exception", resource_id=str(exc.pk))
    exc.status = "pending_approval"
    exc.save()
    return exc


@on_decision("procurement.exception")
def _exception_decided(req, outcome):
    exc = ProcurementException.objects.filter(pk=req.resource_id, status="pending_approval").first()
    if exc is None:
        return
    exc.status = {"approved": "approved", "rejected": "rejected", "cancelled": "open"}.get(outcome, exc.status)
    exc.resolved_by = _decider(req) if outcome == "approved" else None
    exc.save()


def run_recurring(org, today=None) -> int:
    today = today or timezone.localdate()
    n = 0
    for rp in RecurringPurchase.objects.filter(organization=org, is_active=True, next_date__lte=today + timedelta(days=7)).select_related("category", "owner"):
        with transaction.atomic():
            pr = PurchaseRequest.objects.create(organization=org, number=ledger.next_number(org, "pr"), title=f"{rp.title} ({rp.next_date:%b %Y})", requester=rp.owner,
                                                department=rp.department, org_unit=getattr(getattr(rp.owner, "employee", None), "org_unit", None), category=rp.category,
                                                request_type="recurring", justification=f"Recurring purchase {rp.number} under "
                                                f"{rp.contract.number if rp.contract_id else 'no contract'}.", preferred_supplier=rp.supplier,
                                                estimated_total=rp.expected_amount, required_by=rp.next_date, single_source=bool(rp.contract_id),
                                                single_source_reason="existing_contract" if rp.contract_id else "",
                                                single_source_justification=f"Existing contract {rp.contract.number} with {rp.supplier}." if rp.contract_id else "")
            PurchaseRequestLine.objects.create(request=pr, description=rp.title, quantity=Decimal("1"), estimated_unit_cost=rp.expected_amount, line_total=rp.expected_amount)
            rp.last_request = pr
            months = {"monthly": 1, "quarterly": 3, "yearly": 12}[rp.frequency]
            m = rp.next_date.month - 1 + months
            rp.next_date = rp.next_date.replace(year=rp.next_date.year + m // 12, month=m % 12 + 1, day=min(rp.next_date.day, 28))
            rp.save()
        notify(rp.owner, "task_assigned", f"Recurring purchase ready to submit: {pr.number}", link=f"/procurement/requests?open={pr.pk}", module="procurement")
        n += 1
    return n


# =====================================================================================================================
# Detectors (flags for review; never accusations)
# =====================================================================================================================
def detect_split(pr: PurchaseRequest):
    pol = policy(pr.organization)
    since = timezone.now() - timedelta(days=pol.split_window_days)
    siblings = PurchaseRequest.objects.filter(organization=pr.organization, requester=pr.requester, category=pr.category, created_at__gte=since,
                                              status__in=["submitted", "approved", "sourcing", "ordered"]).exclude(pk=pr.pk)
    threshold = pr.category.rfq_required_above or pol.rfq_required_above
    total = pr.estimated_total + (siblings.aggregate(t=Sum("estimated_total"))["t"] or ZERO)
    if siblings.exists() and pr.estimated_total < threshold and total >= threshold and all(s.estimated_total < threshold for s in siblings):
        raise_exception(pr.organization, "split_purchase", source_type="procurement.request", source_id=pr.pk, label=pr.number, amount=total,
                        description=f"{siblings.count() + 1} requests in {pol.split_window_days} days for {pr.category.name}, each below {threshold}, "
                                    f"together {total}.", detected=True)


def detect(org) -> int:
    n0 = ProcurementException.objects.filter(organization=org).count()
    pol = policy(org)
    today = timezone.localdate()
    for po in PurchaseOrder.objects.filter(organization=org, status__in=["approved", "sent", "confirmed", "partially_received"],
                                           expected_delivery__lt=today - timedelta(days=2)):
        raise_exception(org, "late_po", source_type="procurement.order", source_id=po.pk, label=po.number, amount=po.total,
                        description=f"Expected {po.expected_delivery:%d %b}; not fully received.", detected=True)
    for dept, n in PurchaseRequest.objects.filter(organization=org, is_emergency=True, created_at__gte=timezone.now() - timedelta(days=30)) \
            .values_list("department").annotate(n=Count("id")):
        if n >= 3:
            raise_exception(org, "repeated_emergency", source_type="organization.department", source_id=f"{dept}:{today:%Y-%m}", label="Emergency purchases",
                            description=f"{n} emergency purchases in 30 days from one department.", detected=True)
    by_cat = {}
    for row in PurchaseOrder.objects.filter(organization=org).exclude(status__in=["draft", "pending_approval", "cancelled"]) \
            .values("category__name", "supplier_id", "supplier__legal_name").annotate(t=Sum("total")):
        by_cat.setdefault(row["category__name"], []).append(row)
    for cat, rows in by_cat.items():
        tot = sum((r["t"] for r in rows), ZERO)
        top = max(rows, key=lambda r: r["t"])
        if tot and len(rows) >= 1 and top["t"] / tot * HUNDRED >= pol.concentration_threshold_pct and tot >= pol.rfq_required_above:
            raise_exception(org, "concentration", source_type="procurement.category", source_id=f"{cat}:{top['supplier_id']}", label=cat, amount=top["t"],
                            description=f"{top['supplier__legal_name']} has {q2(top['t'] / tot * HUNDRED)}% of {cat} spend.", detected=True)
    from apps.finance.models import FinancePayment, Invoice

    for s in Supplier.objects.filter(organization=org, bank_changed_at__gte=timezone.now() - timedelta(days=30)):
        if FinancePayment.objects.filter(organization=org, invoice__party_id=str(s.pk), created_at__gte=s.bank_changed_at).exists():
            raise_exception(org, "bank_change", source_type="procurement.supplier", source_id=f"{s.pk}:{s.bank_changed_at:%Y%m%d}", label=s.code,
                            description=f"Payments prepared within 30 days of a bank change (now ending {s.bank_last4}). Confirm with the supplier.", detected=True)
    for inv in Invoice.objects.filter(organization=org, kind="vendor_bill", source_type="").exclude(status__in=["void", "rejected"]):
        if Supplier.objects.filter(organization=org, pk=inv.party_id).exists() if inv.party_id else True:
            raise_exception(org, "invoice_without_po", source_type="finance.invoice", source_id=inv.pk, label=inv.supplier_invoice_number or inv.party_name,
                            amount=inv.total, description=f"{inv.party_name} billed without a purchase order (maverick spend).", detected=True)
    seen = set()
    for s in Supplier.objects.filter(organization=org).exclude(status="rejected"):
        for d in duplicates(org, legal_name=s.legal_name, tax_id=s.tax_id, email=s.email, phone=s.phone, bank_last4=s.bank_last4, bank_ifsc=s.bank_ifsc, exclude=s):
            key = tuple(sorted([str(s.pk), d["id"]]))
            if key not in seen and ("same tax ID" in d["why"] or "same bank account" in d["why"] or len(d["why"]) >= 2):
                seen.add(key)
                raise_exception(org, "duplicate_supplier", source_type="procurement.supplier", source_id=":".join(key), label=f"{s.code} / {d['code']}",
                                description=f"{s.legal_name} and {d['name']}: {', '.join(d['why'])}. Review before merging — never automatic.", detected=True)
    for ln in PurchaseOrderLine.objects.filter(order__organization=org, order__status__in=["pending_approval", "approved", "sent"]).select_related("order"):
        prev = PurchaseOrderLine.objects.filter(order__organization=org, order__supplier_id=ln.order.supplier_id, description__iexact=ln.description,
                                                order__created_at__lt=ln.order.created_at).exclude(order__status__in=["draft", "cancelled"]).order_by("-order__created_at").first()
        if prev and prev.unit_price and ln.unit_price > prev.unit_price * Decimal("1.2"):
            raise_exception(org, "price_increase", source_type="procurement.order_line", source_id=ln.pk, label=ln.order.number, amount=ln.unit_price,
                            description=f"“{ln.description}” at {ln.unit_price}, last paid {prev.unit_price} ({prev.order.number}).", detected=True)
    return ProcurementException.objects.filter(organization=org).count() - n0


def contracts_due(org, days=90):
    today = timezone.localdate()
    return ProcurementContract.objects.filter(organization=org, status="active", end_date__lte=today + timedelta(days=days)).select_related("supplier", "owner")


# =====================================================================================================================
# Analytics & performance
# =====================================================================================================================
COMMITTED = ["approved", "sent", "confirmed", "partially_received", "received", "partially_invoiced", "invoiced", "completed", "closed"]


def supplier_scorecard(s: Supplier) -> dict:
    from apps.finance.models import FinancialDispute

    pos = PurchaseOrder.objects.filter(supplier=s, status__in=COMMITTED)
    receipts = GoodsReceipt.objects.filter(order__supplier=s).select_related("order")
    on_time = [r for r in receipts if r.order.expected_delivery]
    on_time_n = sum(1 for r in on_time if r.received_on <= (r.order.confirmed_delivery or r.order.expected_delivery))
    lines = GoodsReceiptLine.objects.filter(receipt__order__supplier=s).aggregate(r=Sum("received_qty"), x=Sum("rejected_qty"), d=Sum("damaged_qty"))
    rec, rej = lines["r"] or ZERO, (lines["x"] or ZERO) + (lines["d"] or ZERO)
    from apps.finance.models import Invoice

    bills = Invoice.objects.filter(kind="vendor_bill", party_id=str(s.pk)).exclude(status__in=["void", "rejected"])
    matched = bills.filter(match_status="matched").count()
    checked = bills.exclude(match_status__in=["not_required", "pending"]).count()
    invites = EventSupplier.objects.filter(supplier=s)
    responded = invites.filter(status="responded").count()
    metrics = {
        "orders": pos.count(), "spend": pos.aggregate(t=Sum("total"))["t"] or ZERO,
        "on_time_pct": q2(Decimal(on_time_n) / len(on_time) * HUNDRED) if on_time else None,
        "rejection_pct": q2(rej / rec * HUNDRED) if rec else None, "invoice_match_pct": q2(Decimal(matched) / checked * HUNDRED) if checked else None,
        "response_rate_pct": q2(Decimal(responded) / invites.count() * HUNDRED) if invites.exists() else None,
        "disputes": FinancialDispute.objects.filter(kind="vendor", party_name__iexact=s.legal_name).count(),
    }
    parts = {"delivery": metrics["on_time_pct"], "quality": (HUNDRED - metrics["rejection_pct"]) if metrics["rejection_pct"] is not None else None,
             "invoice_accuracy": metrics["invoice_match_pct"], "responsiveness": metrics["response_rate_pct"],
             "compliance": Decimal(sum(1 for v in (s.verification or {}).values() if v.get("status") == "verified")) / len(REQUIRED_CHECKS) * HUNDRED
             if s.verification else None}
    weights = {"delivery": 30, "quality": 30, "invoice_accuracy": 15, "responsiveness": 10, "compliance": 15}
    have = {k: v for k, v in parts.items() if v is not None}
    overall = q2(sum(min(v, HUNDRED) * weights[k] for k, v in have.items()) / sum(weights[k] for k in have)) if have else None
    return {**metrics, "scores": {k: (q2(min(v, HUNDRED)) if v is not None else None) for k, v in parts.items()}, "overall": overall,
            "basis": "Measured from receipts, inspections, invoice matching, RFQ responses and verification. Blank = no data yet."}


def analytics(org, start: Date, end: Date) -> dict:
    from apps.finance.models import Invoice

    pos = PurchaseOrder.objects.filter(organization=org, status__in=COMMITTED, created_at__date__gte=start, created_at__date__lte=end)
    bills = Invoice.objects.filter(organization=org, kind="vendor_bill", status__in=["issued", "partially_paid", "paid"], issue_date__gte=start, issue_date__lte=end)
    managed = bills.filter(source_type="procurement.order").aggregate(t=Sum("total"))["t"] or ZERO
    unmanaged = bills.exclude(source_type="procurement.order").aggregate(t=Sum("total"))["t"] or ZERO
    committed = pos.aggregate(t=Sum("total"))["t"] or ZERO
    contracted = pos.filter(contract__isnull=False).aggregate(t=Sum("total"))["t"] or ZERO
    emergency = pos.filter(is_emergency=True).aggregate(t=Sum("total"))["t"] or ZERO
    awards = Award.objects.filter(organization=org, status="approved", created_at__date__gte=start, created_at__date__lte=end)
    savings = awards.aggregate(t=Sum("savings"))["t"] or ZERO
    savings_base = sum(((a.benchmark or a.initial_quote or a.amount) for a in awards), ZERO)

    def group(field, label):
        return [{"label": r[label] or "Not set", "amount": r["t"], "orders": r["n"]} for r in
                pos.values(field, label).annotate(t=Sum("total"), n=Count("id")).order_by("-t")[:15]]

    months = []
    for r in pos.values("created_at__year", "created_at__month").annotate(t=Sum("total")).order_by("created_at__year", "created_at__month"):
        months.append({"month": f"{r['created_at__year']}-{r['created_at__month']:02d}", "amount": r["t"]})
    by_cat = {}
    for r in pos.values("category__name", "supplier__legal_name").annotate(t=Sum("total")):
        by_cat.setdefault(r["category__name"], []).append(r)
    concentration = []
    for cat, rows in by_cat.items():
        tot = sum((r["t"] for r in rows), ZERO)
        top = sorted(rows, key=lambda r: -r["t"])
        concentration.append({"category": cat, "total": tot, "suppliers": len(rows),
                              "top": [{"supplier": r["supplier__legal_name"], "share_pct": q2(r["t"] / tot * HUNDRED) if tot else ZERO} for r in top[:3]]})

    def avg_days(pairs):
        ds = [(b - a).total_seconds() / 86400 for a, b in pairs if a and b and b >= a]
        return round(sum(ds) / len(ds), 1) if ds else None

    prs = PurchaseRequest.objects.filter(organization=org, created_at__date__gte=start, created_at__date__lte=end)
    cycle = {
        "request_to_approval": avg_days([(p.created_at, p.approved_at) for p in prs if p.approved_at]),
        "approval_to_rfq": avg_days([(p.approved_at, ev.created_at) for p in prs if p.approved_at for ev in p.sourcing_events.all()[:1]]),
        "rfq_to_first_quote": avg_days([(ev.published_at, ev.quotations.order_by("created_at").values_list("created_at", flat=True).first())
                                        for ev in SourcingEvent.objects.filter(organization=org, published_at__isnull=False, created_at__date__gte=start)]),
        "quote_to_award": avg_days([(a.quotation.created_at, a.created_at) for a in awards.select_related("quotation")]),
        "award_to_po": avg_days([(a.created_at, a.order.created_at) for a in awards if hasattr(a, "order") and a.order]),
        "po_to_receipt": avg_days([(po.approved_at, timezone.make_aware(timezone.datetime.combine(r.received_on, timezone.datetime.min.time())))
                                   for po in pos.filter(approved_at__isnull=False) for r in po.receipts.order_by("received_on")[:1]]),
        "receipt_to_invoice": avg_days([(timezone.make_aware(timezone.datetime.combine(r.received_on, timezone.datetime.min.time())),
                                         timezone.make_aware(timezone.datetime.combine(i.issue_date, timezone.datetime.min.time())))
                                        for po in pos for r in po.receipts.order_by("received_on")[:1]
                                        for i in Invoice.objects.filter(source_type="procurement.order", source_id=str(po.pk)).order_by("issue_date")[:1]]),
    }
    bills_checked = bills.filter(source_type="procurement.order").exclude(match_status__in=["pending", "not_required"])
    invites = EventSupplier.objects.filter(event__organization=org, event__created_at__date__gte=start)
    grns = GoodsReceipt.objects.filter(organization=org, received_on__gte=start, received_on__lte=end).select_related("order")
    timely = [g for g in grns if g.order.expected_delivery]
    return {
        "from": start, "to": end, "committed_spend": committed, "actual_spend": managed + unmanaged, "managed_spend": managed, "unmanaged_spend": unmanaged,
        "contracted_spend": contracted, "non_contract_spend": committed - contracted, "emergency_spend": emergency, "savings": savings,
        "orders": pos.count(), "average_order_value": q2(committed / pos.count()) if pos.count() else None, "supplier_count": pos.values("supplier").distinct().count(),
        "kpis": {
            "savings_pct": q2(savings / savings_base * HUNDRED) if savings_base else None,
            "maverick_spend_pct": q2(unmanaged / (managed + unmanaged) * HUNDRED) if managed + unmanaged else None,
            "contract_coverage_pct": q2(contracted / committed * HUNDRED) if committed else None,
            "emergency_pct": q2(emergency / committed * HUNDRED) if committed else None,
            "invoice_match_rate_pct": q2(Decimal(bills_checked.filter(match_status="matched").count()) / bills_checked.count() * HUNDRED) if bills_checked.exists() else None,
            "supplier_response_rate_pct": q2(Decimal(invites.filter(status="responded").count()) / invites.count() * HUNDRED) if invites.exists() else None,
            "on_time_delivery_pct": q2(Decimal(sum(1 for g in timely if g.received_on <= (g.order.confirmed_delivery or g.order.expected_delivery))) / len(timely) * HUNDRED) if timely else None,
            "quality_acceptance_pct": (lambda a: q2((a["r"] - a["x"]) / a["r"] * HUNDRED) if a["r"] else None)(
                GoodsReceiptLine.objects.filter(receipt__in=grns).aggregate(r=Sum("received_qty"), x=Sum("rejected_qty"))),
        },
        "by_supplier": group("supplier_id", "supplier__legal_name"), "by_category": group("category_id", "category__name"),
        "by_department": group("department_id", "department__name"), "by_location": group("org_unit_id", "org_unit__name"), "by_month": months,
        "capex_opex": [{"label": r["category__expenditure"].upper(), "amount": r["t"]} for r in pos.values("category__expenditure").annotate(t=Sum("total"))],
        "concentration": sorted(concentration, key=lambda r: -r["total"]), "cycle_time_days": cycle,
        "savings_detail": [{"award": a.number, "supplier": str(a.supplier), "benchmark": a.benchmark, "initial": a.initial_quote, "final": (a.initial_quote - a.savings if a.savings_method == "negotiated" else a.initial_quote) if a.initial_quote is not None else a.amount,
                            "savings": a.savings, "method": a.get_savings_method_display() if a.savings_method else "—"} for a in awards.select_related("supplier")[:50]],
        "note": "Committed = approved purchase orders; actual = approved vendor bills. Unmanaged spend = bills without a purchase order.",
    }


def home(ctx) -> dict:
    org = ctx.organization
    today = timezone.localdate()
    month = today.replace(day=1)
    from apps.finance.models import Invoice

    open_po = PurchaseOrder.objects.filter(organization=org, status__in=["approved", "sent", "confirmed", "partially_received", "received", "partially_invoiced"])
    pending_inv = Invoice.objects.filter(organization=org, kind="vendor_bill", source_type="procurement.order", status__in=["draft", "pending_approval"])
    monthly = PurchaseOrder.objects.filter(organization=org, status__in=COMMITTED, approved_at__date__gte=month).aggregate(t=Sum("total"))["t"] or ZERO
    from apps.finance.models import BudgetCommitment

    committed = sum((c.open_amount for c in BudgetCommitment.objects.filter(organization=org, source_module="procurement").exclude(status__in=["consumed", "released"])), ZERO)
    budget_remaining = None
    if ctx.has("finance.budget.view"):
        from apps.finance.models import Budget

        budget_remaining = sum((fin.budget_figures(b)["available"] for b in Budget.objects.filter(organization=org, status="active")), ZERO)
    pulse = [
        {"key": "requests", "label": "Purchase requests (open)", "value": PurchaseRequest.objects.filter(organization=org, status__in=["submitted", "approved", "sourcing"]).count(), "path": "/procurement/requests"},
        {"key": "pending", "label": "Pending approvals", "value": PurchaseRequest.objects.filter(organization=org, status="submitted").count()
         + PurchaseOrder.objects.filter(organization=org, status="pending_approval").count(), "path": "/approvals"},
        {"key": "rfqs", "label": "Open RFQs / RFPs", "value": SourcingEvent.objects.filter(organization=org, status__in=["published", "responses", "evaluation", "negotiation"]).count(), "path": "/procurement/sourcing"},
        {"key": "open_pos", "label": "Open purchase orders", "value": open_po.count(), "path": "/procurement/orders"},
        {"key": "awaiting_receipt", "label": "Awaiting receipt", "value": open_po.filter(status__in=["approved", "sent", "confirmed", "partially_received"]).count(), "path": "/procurement/receiving"},
        {"key": "overdue", "label": "Overdue POs", "value": open_po.filter(status__in=["approved", "sent", "confirmed", "partially_received"], expected_delivery__lt=today).count(),
         "path": "/procurement/orders?overdue=1", "tone": "alert"},
        {"key": "pending_invoices", "label": "Pending supplier invoices", "value": pending_inv.count(), "path": "/finance/payables"},
        {"key": "match_exceptions", "label": "Three-way match exceptions", "value": ProcurementException.objects.filter(organization=org, kind="three_way_mismatch", status="open").count(),
         "path": "/procurement/exceptions?kind=three_way_mismatch", "tone": "alert"},
        {"key": "monthly_spend", "label": "Spend approved this month", "value": monthly, "money": True, "path": "/procurement/analytics"},
        {"key": "committed", "label": "Committed (not yet billed)", "value": committed, "money": True, "path": "/procurement/analytics"},
        {"key": "budget_remaining", "label": "Budget remaining", "value": budget_remaining, "money": True, "path": "/finance/budgets"},
        {"key": "supplier_issues", "label": "Supplier issues", "value": Supplier.objects.filter(organization=org).filter(Q(preference__in=["restricted", "blocked"]) | Q(risk_level="high")).count(),
         "path": "/procurement/suppliers?issues=1"},
        {"key": "contracts_expiring", "label": "Contracts expiring (90 days)", "value": contracts_due(org).count(), "path": "/procurement/contracts"},
    ]
    from apps.workflows.selectors import inbox_for

    mine = {
        "my_requests": PurchaseRequest.objects.filter(requester=ctx.user).exclude(status__in=["closed", "cancelled", "rejected"]).count(),
        "approvals": sum(1 for r in inbox_for(ctx) if r.policy.module == "procurement"),
        "my_events": SourcingEvent.objects.filter(owner=ctx.user).exclude(status__in=["awarded", "cancelled", "closed"]).count(),
        "quotes_to_review": Quotation.objects.filter(event__owner=ctx.user, is_current=True, status="received").count(),
        "pos_to_act": PurchaseOrder.objects.filter(created_by=ctx.user, status__in=["draft", "approved"]).count(),
        "receipts_pending": open_po.filter(status__in=["sent", "confirmed", "partially_received"]).count() if ctx.has("procurement.receipt.create") else None,
        "services_to_confirm": ServiceReceipt.objects.filter(order__purchase_request__requester=ctx.user, status="submitted").count(),
        "contracts_mine": ProcurementContract.objects.filter(owner=ctx.user, status="active").count(),
        "post_reviews": PurchaseRequest.objects.filter(organization=org, post_review="pending").count() if ctx.has("procurement.exception.approve") else None,
    }
    alerts = []
    for k, title, sev in (("overdue", "Purchase orders overdue", "high"), ("match_exceptions", "Invoice match exceptions", "high"),
                          ("contracts_expiring", "Contracts expiring within 90 days", "medium"), ("supplier_issues", "Restricted, blocked or high-risk suppliers", "medium")):
        v = next(p["value"] for p in pulse if p["key"] == k)
        if v:
            alerts.append({"severity": sev, "title": title, "count": v, "path": next(p["path"] for p in pulse if p["key"] == k)})
    for kind, label in (("split_purchase", "Possible split purchases"), ("duplicate_supplier", "Possible duplicate suppliers"),
                        ("bank_change", "Payments after a supplier bank change"), ("invoice_without_po", "Invoices without a PO"),
                        ("concentration", "Supplier concentration"), ("price_increase", "Unusual price increases"), ("repeated_emergency", "Repeated emergency purchases"),
                        ("single_source", "Single-source purchases"), ("budget_exceeded", "Budget overrides")):
        n = ProcurementException.objects.filter(organization=org, kind=kind, status="open").count()
        if n:
            alerts.append({"severity": "medium", "title": label, "count": n, "path": f"/procurement/exceptions?kind={kind}"})
    return {"pulse": pulse, "my_work": mine, "alerts": alerts}
