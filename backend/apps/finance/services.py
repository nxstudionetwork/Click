"""
Finance document services. Every approval goes through the central engine (apps.workflows) and every financial
consequence through the ledger; nothing here posts directly to tables another module owns.
"""

from __future__ import annotations

import csv
import hashlib
import io
from datetime import date as Date
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.access.security import decrypt, encrypt
from apps.audit.services import record
from apps.core.api.exceptions import DomainError
from apps.workflows import engine
from apps.workflows.hooks import on_decision
from apps.workspace.notify import notify

from . import ledger
from .defaults import CLOSE_TASKS
from .ledger import Line, q2
from .models import (Account, BankAccount, BankTransaction, Budget, BudgetCommitment, BudgetLine, CloseTask, CostCenter, DepreciationEntry,
                     ExpenseCategory, ExpenseClaim, FinancePayment, FinancialDispute, FinancialPeriod, FixedAsset, Invoice, InvoiceLine, Journal,
                     JournalLine, PartnerAgreement, PaymentRun, ReconciliationException, SettlementBatch, TaxRule)

ZERO = Decimal("0")


def dec(v, field="amount") -> Decimal:
    try:
        return q2(Decimal(str(v)))
    except (InvalidOperation, TypeError, ValueError):
        raise DomainError("Enter a valid amount.", code="validation_error", details={field: ["Enter a valid amount."]})


def _date(v, field="date") -> Date:
    d = parse_date(str(v or ""))
    if d is None:
        raise DomainError("Enter a valid date.", code="validation_error", details={field: ["Enter a valid date."]})
    return d


def _same_person(ctx, user_id, what: str):
    if user_id and user_id == ctx.user.pk:
        raise DomainError(f"Segregation of duties: you can’t {what} something you prepared yourself.", code="sod_blocked", status_code=403)


# =====================================================================================================================
# Manual journals
# =====================================================================================================================
def create_journal(request, ctx, *, date, description, lines: list[dict], kind="manual", reference="", submit=True) -> Journal:
    ctx.require("finance.ledger.create")
    if kind not in ("manual", "adjusting", "accrual", "recurring"):
        raise DomainError("Choose manual, adjusting, accrual or recurring.", code="validation_error")
    entity = ledger.default_entity(ctx.organization)
    built = []
    for i, ln in enumerate(lines):
        acc = Account.objects.filter(entity=entity, pk=ln.get("account_id")).first()
        if acc is None:
            raise DomainError(f"Line {i + 1}: choose an account.", code="validation_error")
        cc = CostCenter.objects.filter(organization=ctx.organization, pk=ln["cost_center_id"]).first() if ln.get("cost_center_id") else None
        built.append(Line(acc, debit=dec(ln.get("debit") or 0), credit=dec(ln.get("credit") or 0), description=str(ln.get("description", ""))[:300],
                          extra={"cost_center": cc, "department": cc.department if cc else None}))
    j = ledger.build(entity, date=_date(date), description=description, lines=built, kind=kind, user=ctx.user, reference=reference,
                     source=("finance", "finance.manual", ""), department=ctx.employee.department if ctx.employee else None)
    record(request, "finance.journal.created", category="financial", module="finance", resource=j, new={"total": j.total, "kind": kind})
    if submit:
        submit_journal(request, ctx, j)
    return j


def submit_journal(request, ctx, j: Journal) -> Journal:
    if j.status != Journal.Status.DRAFT:
        raise DomainError("Only draft journals can be submitted.", code="invalid_state", status_code=409)
    req = engine.submit(request, "finance.journal", title=f"Journal: {j.description}"[:160], amount=j.total, description=j.description,
                        resource_type="finance.journal", resource_id=str(j.pk), skip_permission=True)
    j.status, j.approval = Journal.Status.PENDING, req
    j.save(update_fields=["status", "approval", "updated_at"])
    return j


@on_decision("finance.journal")
def _journal_decided(req, outcome):
    j = Journal.objects.filter(pk=req.resource_id).first()
    if j is None or j.status != Journal.Status.PENDING:
        return
    if outcome == "approved":
        step = req.steps.filter(status="approved").order_by("-sequence").first()
        ledger.finalize(j, user=step.decided_by if step else None)
    elif outcome in ("rejected", "cancelled"):
        j.status = Journal.Status.REJECTED
        j.save(update_fields=["status", "updated_at"])
    elif outcome == "changes_requested":
        pass


# =====================================================================================================================
# Invoices (AR), credit / debit notes, vendor bills (AP)
# =====================================================================================================================
def _tax(org, rule_id, on_date):
    if not rule_id:
        return None
    r = TaxRule.objects.filter(organization=org, pk=rule_id, is_active=True).first()
    if r is None or r.effective_from > on_date or (r.effective_to and r.effective_to < on_date):
        raise DomainError("That tax rule isn’t in effect on this date.", code="validation_error")
    return r


def create_invoice(request, ctx, data: dict, *, kind: str, created_by=None, source=None) -> Invoice:
    """Draft document with lines. kind: customer_invoice | partner_invoice | vendor_bill (notes use create_note)."""
    perm = "finance.bill.create" if kind == "vendor_bill" else "finance.invoice.create"
    if ctx is not None:
        ctx.require(perm)
    org = ctx.organization if ctx else data["organization"]
    entity = ledger.default_entity(org)
    issue = _date(data.get("issue_date") or timezone.localdate().isoformat(), "issueDate")
    due = _date(data.get("due_date") or (issue + timedelta(days=int(data.get("terms_days") or 30))).isoformat(), "dueDate")
    lines = data.get("lines") or []
    if not lines:
        raise DomainError("Add at least one line.", code="validation_error", details={"lines": ["Required."]})
    if not str(data.get("party_name", "")).strip():
        raise DomainError("Who is this for?", code="validation_error", details={"partyName": ["Required."]})
    default_key = "general_expense" if kind == "vendor_bill" else "other_revenue"
    if kind == "vendor_bill" and data.get("supplier_invoice_number"):
        dup = Invoice.objects.filter(organization=org, kind="vendor_bill", party_id=str(data.get("party_id", "")),
                                     supplier_invoice_number__iexact=data["supplier_invoice_number"]).exclude(status__in=["void", "rejected"]).first()
        if dup:
            raise DomainError(f"Possible duplicate: {dup.number or 'a draft bill'} already has supplier invoice {dup.supplier_invoice_number}.",
                              code="duplicate_invoice", status_code=409)
    with transaction.atomic():
        inv = Invoice.objects.create(
            organization=org, entity=entity, kind=kind, party_type=data.get("party_type") or ("supplier" if kind == "vendor_bill" else "customer"),
            party_id=str(data.get("party_id", ""))[:64], party_name=str(data["party_name"])[:160], supplier_invoice_number=str(data.get("supplier_invoice_number", ""))[:60],
            revenue_type=data.get("revenue_type", "") if kind != "vendor_bill" else "", issue_date=issue, due_date=due,
            currency=data.get("currency") or entity.base_currency, terms=str(data.get("terms", ""))[:300], created_by=created_by or (ctx.user if ctx else None),
            cost_center=CostCenter.objects.filter(organization=org, pk=data.get("cost_center_id")).first() if data.get("cost_center_id") else None,
            source_module=(source or {}).get("module", ""), source_type=(source or {}).get("type", ""), source_id=str((source or {}).get("id", "")),
            source_label=(source or {}).get("label", ""), match_status="pending" if (source or {}).get("match") else "not_required",
            department=(ctx.employee.department if ctx and ctx.employee else None), org_unit=(ctx.employee.org_unit if ctx and ctx.employee else None))
        if data.get("partner_id"):
            from apps.partners.models import Partner

            inv.partner = Partner.objects.filter(pk=data["partner_id"]).first()
        sub = tax = ZERO
        for ln in lines:
            qty, price = Decimal(str(ln.get("quantity") or 1)), dec(ln.get("unit_price"), "unitPrice")
            rule = _tax(org, ln.get("tax_rule_id"), issue)
            acc = Account.objects.filter(entity=entity, pk=ln["account_id"]).first() if ln.get("account_id") else None
            acc = acc or Account.objects.filter(entity=entity, system_key=ln.get("account_key") or default_key).first()
            total = q2(qty * price)
            t = q2(total * (rule.rate if rule else ZERO) / 100)
            InvoiceLine.objects.create(invoice=inv, description=str(ln.get("description") or "Item")[:300], quantity=qty, unit_price=price, account=acc,
                                       tax_rule=rule, tax_rate=rule.rate if rule else ZERO, tax_amount=t, line_total=total,
                                       source_line_id=str(ln.get("source_line_id", ""))[:64])
            sub, tax = sub + total, tax + t
        inv.subtotal, inv.tax_total, inv.total = sub, tax, sub + tax
        inv.save()
    record(request, f"finance.{kind}.created", category="financial", module="finance", resource=inv, new={"total": inv.total, "party": inv.party_name})
    return inv


def _invoice_lines(inv: Invoice, sign: int = 1, kind: str | None = None) -> list[Line]:
    """sign 1 = normal posting, -1 = reversed (credit note). `kind` = how to post (a note posts like its original)."""
    kind = kind or inv.kind
    party = {"party_type": inv.party_type, "party_id": inv.party_id, "party_name": inv.party_name, "partner": inv.partner,
             "cost_center": inv.cost_center, "department": inv.department, "org_unit": inv.org_unit}
    out = []
    if kind in ("customer_invoice", "partner_invoice"):
        ar = "partner_receivable" if inv.party_type == "partner" else "ar"
        out.append(Line(ar, debit=inv.total if sign > 0 else ZERO, credit=inv.total if sign < 0 else ZERO, extra=party))
        for ln in inv.lines.select_related("account", "tax_rule"):
            out.append(Line(ln.account, credit=ln.line_total if sign > 0 else ZERO, debit=ln.line_total if sign < 0 else ZERO, description=ln.description, extra=party))
            if ln.tax_amount:
                acc = ln.tax_rule.output_account if ln.tax_rule and ln.tax_rule.output_account_id else "tax_payable"
                out.append(Line(acc, credit=ln.tax_amount if sign > 0 else ZERO, debit=ln.tax_amount if sign < 0 else ZERO, extra={"tax_rule": ln.tax_rule}))
    else:  # vendor bill
        payable = "employee_payable" if inv.party_type == "employee" else "ap"
        out.append(Line(payable, credit=inv.total if sign > 0 else ZERO, debit=inv.total if sign < 0 else ZERO, extra=party))
        for ln in inv.lines.select_related("account", "tax_rule"):
            out.append(Line(ln.account, debit=ln.line_total if sign > 0 else ZERO, credit=ln.line_total if sign < 0 else ZERO, description=ln.description, extra=party))
            if ln.tax_amount:
                acc = ln.tax_rule.input_account if ln.tax_rule and ln.tax_rule.input_account_id else "input_tax"
                out.append(Line(acc, debit=ln.tax_amount if sign > 0 else ZERO, credit=ln.tax_amount if sign < 0 else ZERO, extra={"tax_rule": ln.tax_rule}))
    return out


def issue_invoice(request, ctx, inv: Invoice) -> Invoice:
    """AR invoices: issue and post (no approval needed to bill a customer; credit notes need approval)."""
    ctx.require("finance.invoice.create")
    if inv.kind not in ("customer_invoice", "partner_invoice") or inv.status != Invoice.Status.DRAFT:
        raise DomainError("Only draft invoices can be issued.", code="invalid_state", status_code=409)
    with transaction.atomic():
        inv.number = ledger.next_number(inv.organization, "invoice")
        inv.journal = ledger.post(inv.entity, user=ctx.user, request=request, date=inv.issue_date, description=f"Invoice {inv.number} · {inv.party_name}"[:300],
                                  lines=_invoice_lines(inv), source=("finance", "finance.invoice", str(inv.pk)), reference=inv.number)
        inv.status = Invoice.Status.ISSUED
        inv.save(update_fields=["number", "journal", "status", "updated_at"])
    record(request, "finance.invoice.issued", category="financial", module="finance", resource=inv, resource_label=inv.number, new={"total": inv.total})
    return inv


def create_note(request, ctx, original: Invoice, *, kind: str, amount, reason: str) -> Invoice:
    """Credit / debit note against an issued document: approved, then posted. The original is never touched."""
    ctx.require("finance.invoice.create")
    if kind not in ("credit_note", "debit_note") or original.status in ("draft", "void", "rejected", "pending_approval"):
        raise DomainError("Notes can only be raised against an issued document.", code="invalid_state", status_code=409)
    amount = dec(amount)
    if amount <= 0 or (kind == "credit_note" and amount > original.total - sum((n.total for n in original.notes.filter(kind="credit_note")
                                                                                  .exclude(status__in=["rejected", "void"])), ZERO)):
        raise DomainError("The credit note can’t exceed what is left on the original document.", code="validation_error")
    if not reason.strip():
        raise DomainError("Give a reason.", code="reason_required")
    ratio = amount / original.total if original.total else Decimal("1")
    with transaction.atomic():
        note = Invoice.objects.create(organization=original.organization, entity=original.entity, kind=kind, party_type=original.party_type,
                                      party_id=original.party_id, party_name=original.party_name, partner=original.partner, issue_date=timezone.localdate(),
                                      due_date=timezone.localdate(), currency=original.currency, original=original, reason=reason[:300],
                                      created_by=ctx.user, cost_center=original.cost_center, department=original.department, org_unit=original.org_unit)
        sub = tax = ZERO
        for ln in original.lines.all():
            lt, tx = q2(ln.line_total * ratio), q2(ln.tax_amount * ratio)
            InvoiceLine.objects.create(invoice=note, description=f"Adjustment: {ln.description}"[:300], quantity=Decimal("1"), unit_price=lt, account=ln.account,
                                       tax_rule=ln.tax_rule, tax_rate=ln.tax_rate, tax_amount=tx, line_total=lt)
            sub, tax = sub + lt, tax + tx
        note.subtotal, note.tax_total, note.total = sub, tax, sub + tax
        req = engine.submit(request, "finance.credit_note", title=f"{note.get_kind_display()} for {original.number}", amount=note.total,
                            description=reason, resource_type="finance.invoice", resource_id=str(note.pk), skip_permission=True)
        note.status, note.approval = Invoice.Status.PENDING, req
        note.save()
    return note


@on_decision("finance.credit_note")
def _note_decided(req, outcome):
    note = Invoice.objects.filter(pk=req.resource_id).select_related("original").first()
    if note is None or note.status != Invoice.Status.PENDING:
        return
    if outcome == "approved":
        step = req.steps.filter(status="approved").order_by("-sequence").first()
        orig = note.original
        sign = -1 if note.kind == "credit_note" else 1  # credit notes reverse the original's posting (AR or AP alike)
        with transaction.atomic():
            note.number = ledger.next_number(note.organization, note.kind)
            note.journal = ledger.post(note.entity, user=step.decided_by if step else None, date=note.issue_date,
                                       description=f"{note.get_kind_display()} {note.number} for {orig.number}: {note.reason}"[:300],
                                       lines=_invoice_lines(note, sign, kind=orig.kind), source=("finance", "finance.note", str(note.pk)),
                                       reference=orig.number)
            note.status = Invoice.Status.ISSUED
            note.save(update_fields=["number", "journal", "status", "updated_at"])
            if note.kind == "credit_note":  # reduces what is outstanding on the original
                orig.amount_paid = orig.amount_paid + note.total
                orig.status = Invoice.Status.PAID if orig.amount_paid >= orig.total else Invoice.Status.PARTIAL
                orig.save(update_fields=["amount_paid", "status", "updated_at"])
    elif outcome in ("rejected", "cancelled"):
        note.status = Invoice.Status.REJECTED
        note.save(update_fields=["status", "updated_at"])


# Three-way match providers (Procurement registers one). Each returns {"status": matched|exception|not_required, "issues": [...]}.
MATCHERS: dict = {}


def run_match(inv: Invoice) -> dict:
    fn = MATCHERS.get(inv.source_type)
    if fn is None:
        result = {"status": "not_required", "issues": []}
    else:
        result = fn(inv)
    inv.match_status, inv.match_detail = result["status"], result
    inv.save(update_fields=["match_status", "match_detail", "updated_at"])
    return result


def submit_bill(request, ctx, inv: Invoice, *, override_reason: str = "") -> Invoice:
    ctx.require("finance.bill.create")
    if inv.kind != "vendor_bill" or inv.status != Invoice.Status.DRAFT:
        raise DomainError("Only draft bills can be submitted.", code="invalid_state", status_code=409)
    m = run_match(inv)
    if m["status"] == "exception":
        if not override_reason.strip():
            raise DomainError("This bill doesn’t match the purchase order / receipt: " + "; ".join(m["issues"][:4]) +
                              ". Fix it, or give a reason to request an approved exception.", code="match_exception", status_code=409,
                              details={"issues": m["issues"]})
        inv.match_status = Invoice.Match.OVERRIDDEN
        inv.match_detail = {**m, "override_reason": override_reason[:300], "override_by": str(ctx.user.pk)}
        inv.save(update_fields=["match_status", "match_detail", "updated_at"])
        ReconciliationException.objects.get_or_create(organization=inv.organization, kind="three_way_mismatch", source_type="finance.invoice",
                                                      source_id=str(inv.pk), defaults={"area": "ledger", "amount": inv.total,
                                                                                       "description": "; ".join(m["issues"])[:300], "owner": ctx.user})
    req = engine.submit(request, "finance.bill", title=f"Bill {inv.supplier_invoice_number or ''} · {inv.party_name}"[:160], amount=inv.total,
                        description=("MATCH EXCEPTION — " + override_reason) if inv.match_status == "overridden" else f"Due {inv.due_date:%d %b}",
                        resource_type="finance.invoice", resource_id=str(inv.pk), skip_permission=True, blocking=inv.match_status == "overridden",
                        priority="high" if inv.match_status == "overridden" else "normal")
    inv.status, inv.approval = Invoice.Status.PENDING, req
    inv.save(update_fields=["status", "approval", "updated_at"])
    return inv


@on_decision("finance.bill")
def _bill_decided(req, outcome):
    inv = Invoice.objects.filter(pk=req.resource_id).first()
    if inv is None or inv.status != Invoice.Status.PENDING:
        return
    if outcome == "approved":
        step = req.steps.filter(status="approved").order_by("-sequence").first()
        with transaction.atomic():
            inv.number = ledger.next_number(inv.organization, "bill")
            inv.journal = ledger.post(inv.entity, user=step.decided_by if step else None, date=inv.issue_date,
                                      description=f"Bill {inv.number} · {inv.party_name} ({inv.supplier_invoice_number})"[:300], lines=_invoice_lines(inv),
                                      source=("finance", "finance.invoice", str(inv.pk)), reference=inv.supplier_invoice_number)
            inv.status = Invoice.Status.ISSUED
            inv.save(update_fields=["number", "journal", "status", "updated_at"])
        for fn in BILL_APPROVED_HOOKS:
            fn(inv)
    elif outcome in ("rejected", "cancelled"):
        inv.status = Invoice.Status.REJECTED
        inv.save(update_fields=["status", "updated_at"])


BILL_APPROVED_HOOKS: list = []  # e.g. Procurement marks the PO invoiced and consumes the budget commitment


def void_draft(request, ctx, inv: Invoice, reason: str):
    if inv.status not in ("draft", "rejected"):
        raise DomainError("Issued documents are corrected with a credit note, never voided or edited.", code="invalid_state", status_code=409)
    inv.status, inv.reason = Invoice.Status.VOID, reason[:300]
    inv.save(update_fields=["status", "reason", "updated_at"])
    record(request, "finance.invoice.void", category="financial", module="finance", resource=inv, new={"reason": reason})


# =====================================================================================================================
# Payments (received & paid out), payment runs
# =====================================================================================================================
def receive_payment(request, ctx, inv: Invoice, *, amount, date, bank_account, reference="", method="bank_transfer") -> FinancePayment:
    ctx.require("finance.payment.create")
    if inv.kind not in ("customer_invoice", "partner_invoice") or inv.status not in ("issued", "partially_paid"):
        raise DomainError("Record receipts against an issued invoice.", code="invalid_state", status_code=409)
    amount = dec(amount)
    if amount <= 0 or amount > inv.total - inv.amount_paid:
        raise DomainError("The amount must be positive and not more than what is outstanding.", code="validation_error")
    d = _date(date)
    with transaction.atomic():
        pay = FinancePayment.objects.create(organization=inv.organization, entity=inv.entity, number=ledger.next_number(inv.organization, "payment_in"),
                                            direction="in", invoice=inv, party_name=inv.party_name, partner=inv.partner, amount=amount, date=d,
                                            method=method, bank_account=bank_account, reference=reference[:80], status="paid", created_by=ctx.user,
                                            executed_by=ctx.user)
        ar = "partner_receivable" if inv.party_type == "partner" else "ar"
        pay.journal = ledger.post(inv.entity, user=ctx.user, request=request, date=d, description=f"Receipt {pay.number} for {inv.number}",
                                  lines=[Line(bank_account.gl_account, debit=amount),
                                         Line(ar, credit=amount, extra={"party_type": inv.party_type, "party_id": inv.party_id, "party_name": inv.party_name,
                                                                         "partner": inv.partner})],
                                  source=("finance", "finance.payment", str(pay.pk)), reference=reference)
        pay.save(update_fields=["journal", "updated_at"])
        inv.amount_paid += amount
        inv.status = Invoice.Status.PAID if inv.amount_paid >= inv.total else Invoice.Status.PARTIAL
        inv.save(update_fields=["amount_paid", "status", "updated_at"])
    return pay


def duplicate_payment(org, *, party_name, amount, invoice=None) -> FinancePayment | None:
    since = timezone.localdate() - timedelta(days=30)
    qs = FinancePayment.objects.filter(organization=org, direction="out", amount=amount, party_name__iexact=party_name, date__gte=since) \
        .exclude(status__in=["void", "failed"])
    if invoice is not None:
        qs = qs.filter(invoice=invoice)
    return qs.first()


def create_outgoing(request, ctx, *, invoice=None, claim=None, amount=None, date=None, bank_account=None, reference="", run=None,
                    allow_duplicate=False) -> FinancePayment:
    ctx.require("finance.payment.create")
    org = ctx.organization
    entity = ledger.default_entity(org)
    if invoice is not None:
        if not (invoice.kind == "vendor_bill" and invoice.status in ("issued", "partially_paid")):
            raise DomainError("Only approved bills can be paid.", code="invalid_state", status_code=409)
        if invoice.match_status == "exception":
            raise DomainError("The bill has an unresolved three-way match exception.", code="match_exception", status_code=409)
        amount = dec(amount if amount is not None else invoice.total - invoice.amount_paid)
        if amount <= 0 or amount > invoice.total - invoice.amount_paid:
            raise DomainError("The amount must not exceed what is outstanding.", code="validation_error")
        party, purpose = invoice.party_name, "invoice"
    elif claim is not None:
        if claim.status != ExpenseClaim.Status.APPROVED:
            raise DomainError("Only approved expense claims can be reimbursed.", code="invalid_state", status_code=409)
        amount, party, purpose = claim.amount, claim.claimant.full_name, "reimbursement"
    else:
        raise DomainError("Pay a bill or an expense claim.", code="validation_error")
    dup = duplicate_payment(org, party_name=party, amount=amount, invoice=invoice)
    if dup and not allow_duplicate:
        raise DomainError(f"Possible duplicate payment: {dup.number} ({dup.amount}) to {party} on {dup.date:%d %b}.", code="duplicate_payment",
                          status_code=409, details={"payment": dup.number})
    pay = FinancePayment.objects.create(organization=org, entity=entity, number=ledger.next_number(org, "payment_out"), direction="out", purpose=purpose,
                                        invoice=invoice, expense_claim=claim, party_name=party[:160], partner=getattr(invoice, "partner", None),
                                        amount=amount, date=_date(date) if date else timezone.localdate(), bank_account=bank_account,
                                        reference=reference[:80], status="draft", created_by=ctx.user, run=run)
    record(request, "finance.payment.created", category="financial", module="finance", resource=pay, new={"amount": amount, "party": party})
    return pay


def submit_payment(request, ctx, pay: FinancePayment) -> FinancePayment:
    if pay.status != "draft" or pay.run_id:
        raise DomainError("Only draft single payments can be submitted (runs are approved as a whole).", code="invalid_state", status_code=409)
    req = engine.submit(request, "finance.payment", title=f"Pay {pay.party_name}", amount=pay.amount, description=f"{pay.number} · {pay.purpose}",
                        resource_type="finance.payment", resource_id=str(pay.pk), skip_permission=True)
    pay.status, pay.approval = "pending_approval", req
    pay.save(update_fields=["status", "approval", "updated_at"])
    return pay


@on_decision("finance.payment")
def _payment_decided(req, outcome):
    target = FinancePayment.objects.filter(pk=req.resource_id).first() if req.resource_type == "finance.payment" else None
    run = PaymentRun.objects.filter(pk=req.resource_id).first() if req.resource_type == "finance.payment_run" else None
    status = {"approved": "approved", "rejected": "void", "cancelled": "void"}.get(outcome)
    if status is None:
        return
    if target and target.status == "pending_approval":
        target.status = status
        target.save(update_fields=["status", "updated_at"])
    if run and run.status == "pending_approval":
        run.status = "approved" if outcome == "approved" else "cancelled"
        run.save(update_fields=["status", "updated_at"])
        run.payments.filter(status="pending_approval").update(status=status)


def execute_payment(request, ctx, pay: FinancePayment, *, bank_account=None, reference="") -> FinancePayment:
    """Release approved money. The preparer can’t release it (approver ≠ creator is enforced by the engine)."""
    ctx.require("finance.payment.execute")
    if pay.status != "approved":
        raise DomainError("Only approved payments can be released.", code="invalid_state", status_code=409)
    _same_person(ctx, pay.created_by_id, "release")
    bank = bank_account or pay.bank_account
    if bank is None:
        raise DomainError("Choose the bank account to pay from.", code="validation_error")
    with transaction.atomic():
        if pay.invoice_id:
            inv = Invoice.objects.select_for_update().get(pk=pay.invoice_id)
            payable = "employee_payable" if inv.party_type == "employee" else "ap"
            party = {"party_type": inv.party_type, "party_id": inv.party_id, "party_name": inv.party_name}
        else:
            inv, payable = None, "employee_payable"
            party = {"party_type": "employee", "party_id": str(pay.expense_claim.claimant_id), "party_name": pay.party_name}
        pay.journal = ledger.post(pay.entity, user=ctx.user, request=request, date=timezone.localdate(), description=f"Payment {pay.number} · {pay.party_name}"[:300],
                                  lines=[Line(payable, debit=pay.amount, extra=party), Line(bank.gl_account, credit=pay.amount)],
                                  source=("finance", "finance.payment", str(pay.pk)), reference=reference or pay.number)
        pay.status, pay.executed_by, pay.bank_account = "paid", ctx.user, bank
        pay.reference = (reference or pay.reference)[:80]
        pay.save()
        if inv:
            inv.amount_paid += pay.amount
            inv.status = Invoice.Status.PAID if inv.amount_paid >= inv.total else Invoice.Status.PARTIAL
            inv.save(update_fields=["amount_paid", "status", "updated_at"])
        if pay.expense_claim_id:
            ExpenseClaim.objects.filter(pk=pay.expense_claim_id).update(status=ExpenseClaim.Status.PAID)
    record(request, "finance.payment.executed", category="financial", module="finance", resource=pay, sensitive=True,
           new={"amount": pay.amount, "party": pay.party_name, "bank": bank.name})
    return pay


def create_run(request, ctx, *, due_by, include_reimbursements=True, bank_account=None) -> PaymentRun:
    ctx.require("finance.payment.create")
    org = ctx.organization
    bills = Invoice.objects.filter(organization=org, kind="vendor_bill", status__in=["issued", "partially_paid"], due_date__lte=due_by) \
        .exclude(match_status="exception").exclude(payments__status__in=["draft", "pending_approval", "approved"])
    claims = ExpenseClaim.objects.filter(organization=org, status="approved") if include_reimbursements else ExpenseClaim.objects.none()
    if not bills.exists() and not claims.exists():
        raise DomainError("Nothing is due for payment.", code="nothing_due", status_code=409)
    with transaction.atomic():
        run = PaymentRun.objects.create(organization=org, number=ledger.next_number(org, "payment_run"), created_by=ctx.user, bank_account=bank_account,
                                        kind="mixed" if include_reimbursements else "vendor")
        for b in bills:
            create_outgoing(request, ctx, invoice=b, run=run, bank_account=bank_account, allow_duplicate=True)
        for c in claims.exclude(pk__in=FinancePayment.objects.filter(expense_claim__isnull=False).exclude(status="void").values("expense_claim")):
            create_outgoing(request, ctx, claim=c, run=run, bank_account=bank_account, allow_duplicate=True)
        run.total = run.payments.aggregate(t=Sum("amount"))["t"] or ZERO
        req = engine.submit(request, "finance.payment", title=f"Payment run {run.number}", amount=run.total,
                            description=f"{run.payments.count()} payments due by {due_by:%d %b}", resource_type="finance.payment_run", resource_id=str(run.pk),
                            skip_permission=True, blocking=True)
        run.status, run.approval = "pending_approval", req
        run.save()
        run.payments.update(status="pending_approval", approval=req)
    return run


def execute_run(request, ctx, run: PaymentRun) -> PaymentRun:
    if run.status != "approved":
        raise DomainError("Only approved runs can be executed.", code="invalid_state", status_code=409)
    _same_person(ctx, run.created_by_id, "release")
    for p in run.payments.filter(status="approved"):
        execute_payment(request, ctx, p, bank_account=run.bank_account or p.bank_account)
    run.status, run.executed_by = "completed", ctx.user
    run.save(update_fields=["status", "executed_by", "updated_at"])
    return run


# =====================================================================================================================
# Expense claims (policy finance.expense — the same approval type expenses always used)
# =====================================================================================================================
def check_expense_policy(cat: ExpenseCategory, amount: Decimal, has_receipt: bool, distance=None) -> list[str]:
    flags = []
    if cat.limit_per_claim is not None and amount > cat.limit_per_claim:
        flags.append(f"Above the {cat.name} limit of {cat.limit_per_claim} per claim — the approver will see this.")
    if amount > cat.receipt_required_above and not has_receipt:
        flags.append(f"Receipt required for {cat.name} above {cat.receipt_required_above}.")
    if cat.mileage_rate and distance:
        expected = q2(Decimal(str(distance)) * cat.mileage_rate)
        if amount > expected:
            flags.append(f"Mileage at {cat.mileage_rate}/km for {distance} km is {expected}; claimed {amount}.")
    return flags


def submit_claim(request, ctx, data: dict) -> ExpenseClaim:
    ctx.require("finance.expense.create")
    cat = ExpenseCategory.objects.filter(organization=ctx.organization, pk=data.get("category_id"), is_active=True).first()
    if cat is None:
        raise DomainError("Choose a category.", code="validation_error", details={"categoryId": ["Required."]})
    amount = dec(data.get("amount"))
    if amount <= 0:
        raise DomainError("Enter the amount.", code="validation_error")
    d = _date(data.get("date"))
    if d > timezone.localdate():
        raise DomainError("Expenses can’t be dated in the future.", code="validation_error", details={"date": ["In the future."]})
    if len(str(data.get("purpose", "")).strip()) < 5:
        raise DomainError("Describe the business purpose.", code="validation_error", details={"purpose": ["Required."]})
    has_receipt = bool(data.get("has_receipt"))
    flags = check_expense_policy(cat, amount, has_receipt, data.get("distance_km"))
    if any(f.startswith("Receipt required") for f in flags):
        raise DomainError(flags[0] + " Attach it to the claim, then submit.", code="receipt_required", status_code=400)
    emp = ctx.employee
    dup = ExpenseClaim.objects.filter(claimant=ctx.user, date=d, amount=amount, category=cat).exclude(status__in=["rejected", "cancelled"]).first()
    if dup:
        flags.append(f"Same amount, date and category as {dup.number}.")
    cc = CostCenter.objects.filter(organization=ctx.organization, pk=data.get("cost_center_id")).first() if data.get("cost_center_id") else None
    with transaction.atomic():
        c = ExpenseClaim.objects.create(organization=ctx.organization, number=ledger.next_number(ctx.organization, "expense"), claimant=ctx.user, category=cat,
                                        date=d, amount=amount, purpose=str(data.get("purpose", ""))[:300], merchant=str(data.get("merchant", ""))[:120],
                                        distance_km=data.get("distance_km") or None, has_receipt=has_receipt, policy_flags=flags, cost_center=cc,
                                        org_unit=emp.org_unit if emp else None, department=emp.department if emp else None, status="submitted")
        req = engine.submit(request, "finance.expense", title=f"{cat.name}: {c.purpose}"[:160], amount=amount, org_unit=c.org_unit, department=c.department,
                            description=c.purpose + (("\nPolicy: " + " ".join(flags)) if flags else ""), resource_type="finance.expense_claim",
                            resource_id=str(c.pk), priority="high" if flags else "normal")
        c.approval = req
        c.save(update_fields=["approval", "updated_at"])
    return c


@on_decision("finance.expense")
def _expense_decided(req, outcome):
    if req.resource_type != "finance.expense_claim":
        return  # older direct expense approvals carry no claim
    c = ExpenseClaim.objects.filter(pk=req.resource_id).select_related("category__account", "claimant").first()
    if c is None or c.status != "submitted":
        return
    if outcome == "approved":
        entity = ledger.default_entity(c.organization)
        step = req.steps.filter(status="approved").order_by("-sequence").first()
        c.journal = ledger.post(entity, user=step.decided_by if step else None, date=timezone.localdate(), description=f"Expense {c.number} · {c.claimant.full_name}",
                                lines=[Line(c.category.account, debit=c.amount, extra={"cost_center": c.cost_center, "department": c.department, "org_unit": c.org_unit}),
                                       Line("employee_payable", credit=c.amount, extra={"party_type": "employee", "party_id": str(c.claimant_id),
                                                                                       "party_name": c.claimant.full_name})],
                                source=("finance", "finance.expense_claim", str(c.pk)))
        c.status = "approved"
        c.save(update_fields=["journal", "status", "updated_at"])
        consume_for_spend(c.organization, amount=c.amount, department=c.department, org_unit=c.org_unit, cost_center=c.cost_center)
    elif outcome in ("rejected", "cancelled"):
        c.status = "rejected" if outcome == "rejected" else "cancelled"
        c.save(update_fields=["status", "updated_at"])


# =====================================================================================================================
# Budgets, actuals, commitments (the Procurement integration point)
# =====================================================================================================================
def fy_bounds(entity, year: int) -> tuple[Date, Date]:
    start = Date(year, entity.fiscal_year_start_month, 1)
    end_year = year + 1 if entity.fiscal_year_start_month > 1 else year
    end = Date(end_year, entity.fiscal_year_start_month, 1) - timedelta(days=1) if entity.fiscal_year_start_month > 1 else Date(year, 12, 31)
    return start, end


def _budget_lines_q(b: Budget) -> Q:
    q = Q(journal__status__in=["posted", "reversed"], journal__entity=b.entity, account__type__in=["expense", "cost_of_revenue", "asset"])
    if b.department_id:
        q &= Q(department_id__in=b.department.descendant_ids()) if hasattr(b.department, "descendant_ids") else Q(department=b.department)
    if b.cost_center_id:
        q &= Q(cost_center=b.cost_center)
    if b.org_unit_id:
        q &= Q(org_unit__path__startswith=b.org_unit.path)
    accounts = [ln.account_id for ln in b.lines.all() if ln.account_id]
    if accounts:
        q &= Q(account_id__in=accounts)
    else:
        q &= ~Q(account__system_key__in=["bank", "cash", "gateway_clearing", "ar", "partner_receivable", "input_tax"])
    return q


def budget_figures(b: Budget, today: Date | None = None) -> dict:
    today = today or timezone.localdate()
    start, end = fy_bounds(b.entity, b.fiscal_year)
    total = b.amount
    agg = JournalLine.objects.filter(_budget_lines_q(b), journal__date__gte=start, journal__date__lte=end).aggregate(d=Sum("debit"), c=Sum("credit"))
    actual = (agg["d"] or ZERO) - (agg["c"] or ZERO)
    committed = sum((c.open_amount for c in b.commitments.exclude(status__in=["consumed", "released"])), ZERO)
    elapsed = max(1, min(12, (today.year - start.year) * 12 + today.month - start.month + 1)) if today >= start else 1
    run_rate = q2(actual / elapsed * 12) if today >= start else ZERO
    forecast = max(run_rate, actual + committed)
    available = total - actual - committed
    return {"budget": total, "actual": actual, "committed": committed, "available": available, "forecast": forecast,
            "variance": total - forecast, "variance_pct": q2((total - forecast) / total * 100) if total else None,
            "used_pct": q2((actual + committed) / total * 100) if total else None, "fiscal_year": f"FY {b.fiscal_year}-{str(b.fiscal_year + 1)[-2:]}",
            "forecast_note": f"Estimate: higher of run-rate ({elapsed} months elapsed) and actual + committed. Not a confirmed figure."}


def find_budget(org, *, department=None, org_unit=None, cost_center=None, category: str = "", on_date: Date | None = None) -> Budget | None:
    entity = ledger.default_entity(org)
    d = on_date or timezone.localdate()
    fy = ledger.fiscal_year_of(entity, d)
    qs = Budget.objects.filter(organization=org, entity=entity, fiscal_year=fy, status=Budget.Status.ACTIVE)
    candidates = []

    def cat_ok(b):  # a categorised budget only covers that category; an uncategorised request falls back to the department budget
        return not b.category or not category or b.category == category

    for b in qs:
        exact = 0 if (category and b.category == category) else 1
        if b.cost_center_id and cost_center is not None and b.cost_center_id == cost_center.pk:
            candidates.append((0, b))
        elif b.department_id and department is not None and b.department_id == department.pk and cat_ok(b):
            candidates.append((1 + exact, b))
        elif b.org_unit_id and org_unit is not None and org_unit.path.startswith(b.org_unit.path) and cat_ok(b):
            candidates.append((3 + exact, b))
    return sorted(candidates, key=lambda x: x[0])[0][1] if candidates else None


def check_budget(org, amount, **dims) -> dict:
    """What Procurement shows before approval: budget, committed, available, after this request."""
    b = find_budget(org, **dims)
    amount = q2(amount)
    if b is None:
        return {"found": False, "status": "no_budget", "message": "No approved budget covers this department / category this fiscal year.",
                "amount": amount}
    f = budget_figures(b)
    after = f["available"] - amount
    return {"found": True, "budget_id": str(b.pk), "budget_number": b.number, "budget_name": b.name, **{k: f[k] for k in ("budget", "actual", "committed",
            "available")}, "amount": amount, "after": after, "status": "ok" if after >= 0 else "insufficient",
            "message": "Within budget." if after >= 0 else f"Exceeds the available budget by {-after}."}


def reserve(org, *, budget_id, amount, source_module, source_type, source_id, label) -> BudgetCommitment:
    b = Budget.objects.get(pk=budget_id, organization=org)
    c, _ = BudgetCommitment.objects.update_or_create(source_type=source_type, source_id=str(source_id), defaults={
        "organization": org, "budget": b, "source_module": source_module, "source_label": label[:80], "amount": q2(amount), "status": "reserved"})
    return c


def consume(source_type: str, source_id, amount) -> BudgetCommitment | None:
    c = BudgetCommitment.objects.filter(source_type=source_type, source_id=str(source_id)).first()
    if c is None:
        return None
    c.consumed = min(c.amount - c.released, c.consumed + q2(amount))
    c.status = "consumed" if c.consumed >= c.amount - c.released else "partial"
    c.save(update_fields=["consumed", "status", "updated_at"])
    return c


def release(source_type: str, source_id) -> BudgetCommitment | None:
    c = BudgetCommitment.objects.filter(source_type=source_type, source_id=str(source_id)).first()
    if c is None or c.status in ("consumed", "released"):
        return c
    c.released = c.amount - c.consumed
    c.status = "released"
    c.save(update_fields=["released", "status", "updated_at"])
    return c


def consume_for_spend(org, **_dims):
    """Expenses are actuals (they hit the ledger directly); nothing to consume — kept for symmetry with procurement."""
    return None


def submit_budget(request, ctx, b: Budget) -> Budget:
    if b.status != Budget.Status.DRAFT:
        raise DomainError("Only draft budgets can be submitted.", code="invalid_state", status_code=409)
    if b.amount <= 0:
        raise DomainError("Add budget lines first.", code="validation_error")
    req = engine.submit(request, "finance.budget", title=f"Budget {b.number}: {b.name}"[:160], amount=b.amount, department=b.department,
                        org_unit=b.org_unit, description=b.notes or b.name, resource_type="finance.budget", resource_id=str(b.pk))
    b.status, b.approval = Budget.Status.PENDING, req
    b.save(update_fields=["status", "approval", "updated_at"])
    return b


@on_decision("finance.budget")
def _budget_decided(req, outcome):
    b = Budget.objects.filter(pk=req.resource_id).first()
    if b is None or b.status != Budget.Status.PENDING:
        return
    b.status = {"approved": "active", "rejected": "rejected", "cancelled": "draft", "changes_requested": "pending_approval"}.get(outcome, b.status)
    b.save(update_fields=["status", "updated_at"])


# =====================================================================================================================
# Partner agreements (commission engine): versioned, approved, effective-dated
# =====================================================================================================================
def propose_agreement(request, ctx, data: dict) -> PartnerAgreement:
    ctx.require("finance.commission.configure")
    from apps.partners.models import Partner

    partner = Partner.objects.filter(pk=data.get("partner_id")).first() if data.get("partner_id") else None
    eff = _date(data.get("effective_from"), "effectiveFrom")
    if eff < timezone.localdate():
        raise DomainError("Agreements apply from today or later; history is never recalculated.", code="validation_error",
                          details={"effectiveFrom": ["In the past."]})
    prev = PartnerAgreement.objects.filter(organization=ctx.organization, partner=partner).order_by("-version").first()
    fields = {k: dec(data[k]) for k in ("commission_pct", "platform_fee_pct", "fixed_fee", "tax_on_fees_pct", "promo_click_share_pct",
                                        "refund_click_share_pct", "minimum_guarantee") if data.get(k) not in (None, "")}
    for k in ("commission_pct", "platform_fee_pct"):
        if k in fields and not (ZERO <= fields[k] <= 100):
            raise DomainError("Percentages must be between 0 and 100.", code="validation_error", details={k: ["0–100"]})
    with transaction.atomic():
        a = PartnerAgreement.objects.create(
            organization=ctx.organization, partner=partner, code=ledger.next_number(ctx.organization, "agreement"),
            commercial_model=data.get("commercial_model") or (prev.commercial_model if prev else "marketplace"), effective_from=eff,
            delivery_fee_to=data.get("delivery_fee_to") or "click", promo_funding=data.get("promo_funding") or "partner",
            refund_responsibility=data.get("refund_responsibility") or "partner", settlement_frequency=data.get("settlement_frequency") or "weekly",
            payment_terms_days=int(data.get("payment_terms_days") or 2), version=(prev.version + 1) if prev else 1, notes=str(data.get("notes", ""))[:500],
            created_by=ctx.user, **fields)
        req = engine.submit(request, "finance.agreement", title=f"Commercial terms {a.code} · {partner or 'Default'}",
                            description=f"Commission {a.commission_pct}% + fee {a.platform_fee_pct}% + {a.fixed_fee}/txn from {eff:%d %b %Y}",
                            resource_type="finance.agreement", resource_id=str(a.pk))
        a.status, a.approval = "pending_approval", req
        a.save(update_fields=["status", "approval", "updated_at"])
    record(request, "finance.commission.proposed", category="financial", module="finance", resource=a, new=a.snapshot())
    return a


@on_decision("finance.agreement")
def _agreement_decided(req, outcome):
    a = PartnerAgreement.objects.filter(pk=req.resource_id).first()
    if a is None or a.status != "pending_approval":
        return
    if outcome != "approved":
        a.status = "rejected" if outcome in ("rejected", "cancelled") else a.status
        a.save(update_fields=["status", "updated_at"])
        return
    with transaction.atomic():
        for old in PartnerAgreement.objects.filter(organization=a.organization, partner=a.partner, status="active").exclude(pk=a.pk):
            old.effective_to = a.effective_from - timedelta(days=1)
            old.status = "superseded" if old.effective_to < timezone.localdate() or old.effective_from >= a.effective_from else "active"
            old.save(update_fields=["effective_to", "status", "updated_at"])
        a.status = "active"
        a.save(update_fields=["status", "updated_at"])
    record(None, "finance.commission.changed", category="financial", module="finance", resource=a, organization=a.organization, new=a.snapshot())


# =====================================================================================================================
# Fixed assets
# =====================================================================================================================
def capitalise(request, ctx, asset: FixedAsset, *, credit_key: str = "asset_clearing") -> FixedAsset:
    ctx.require("finance.asset.approve")
    if asset.status != FixedAsset.Status.DRAFT:
        raise DomainError("Only assets awaiting capitalisation can be capitalised.", code="invalid_state", status_code=409)
    with transaction.atomic():
        asset.capitalised_journal = ledger.post(asset.entity, user=ctx.user, request=request, date=asset.acquisition_date,
                                                description=f"Capitalise {asset.number} {asset.name}"[:300],
                                                lines=[Line("fixed_assets", debit=asset.cost, extra={"department": asset.department, "cost_center": asset.cost_center}),
                                                       Line(credit_key, credit=asset.cost)], source=("finance", "finance.asset", str(asset.pk)))
        asset.status = FixedAsset.Status.ACTIVE
        asset.save(update_fields=["capitalised_journal", "status", "updated_at"])
    return asset


def run_depreciation(request, ctx, period: FinancialPeriod) -> dict:
    ctx.require("finance.asset.approve")
    n, total = 0, ZERO
    for a in FixedAsset.objects.filter(entity=period.entity, status=FixedAsset.Status.ACTIVE, acquisition_date__lte=period.end):
        if DepreciationEntry.objects.filter(asset=a, period=period).exists():
            continue
        depreciable = a.cost - a.salvage_value - a.accumulated_depreciation
        if depreciable <= 0:
            continue
        amt = min(depreciable, q2((a.cost - a.salvage_value) / a.useful_life_months))
        with transaction.atomic():
            j = ledger.post(a.entity, user=ctx.user, request=request, date=period.end, description=f"Depreciation {period.name} · {a.number}",
                            lines=[Line("depreciation", debit=amt, extra={"department": a.department, "cost_center": a.cost_center}),
                                   Line("accumulated_depreciation", credit=amt)], kind="adjusting",
                            source=("finance", "finance.depreciation", f"{a.pk}:{period.pk}"))
            DepreciationEntry.objects.create(asset=a, period=period, amount=amt, journal=j)
            a.accumulated_depreciation += amt
            a.save(update_fields=["accumulated_depreciation", "updated_at"])
        n, total = n + 1, total + amt
    return {"assets": n, "total": total}


def dispose_asset(request, ctx, a: FixedAsset, *, on_date, proceeds, bank_account=None) -> FixedAsset:
    ctx.require("finance.asset.approve")
    if a.status != FixedAsset.Status.ACTIVE:
        raise DomainError("Only assets in use can be disposed.", code="invalid_state", status_code=409)
    proceeds = dec(proceeds)
    gain = proceeds - a.book_value
    lines = [Line("accumulated_depreciation", debit=a.accumulated_depreciation), Line("fixed_assets", credit=a.cost)]
    if proceeds:
        if bank_account is None:
            raise DomainError("Choose the bank account that received the proceeds.", code="validation_error")
        lines.append(Line(bank_account.gl_account, debit=proceeds))
    lines.append(Line("disposal_gain", credit=gain) if gain > 0 else Line("disposal_loss", debit=-gain))
    with transaction.atomic():
        ledger.post(a.entity, user=ctx.user, request=request, date=_date(on_date), description=f"Disposal {a.number} {a.name}"[:300], lines=lines,
                    source=("finance", "finance.asset_disposal", str(a.pk)))
        a.status, a.disposed_on, a.disposal_amount = FixedAsset.Status.DISPOSED, _date(on_date), proceeds
        a.save(update_fields=["status", "disposed_on", "disposal_amount", "updated_at"])
    return a


# =====================================================================================================================
# Banking & reconciliation
# =====================================================================================================================
def set_bank_number(request, ctx, bank: BankAccount, number: str, ifsc: str = "") -> BankAccount:
    ctx.require("finance.bank.manage")
    digits = "".join(ch for ch in number if ch.isalnum())
    if len(digits) < 6:
        raise DomainError("Enter the full account number.", code="validation_error")
    old_last4 = bank.last4
    bank.account_number_enc, bank.last4, bank.ifsc = encrypt(digits), digits[-4:], ifsc.upper()[:11] or bank.ifsc
    bank.save(update_fields=["account_number_enc", "last4", "ifsc", "updated_at"])
    record(request, "finance.bank.details_changed", category="financial", module="finance", resource=bank, sensitive=True,
           old={"last4": old_last4}, new={"last4": bank.last4})
    from apps.access.authz import holders_of

    for u in holders_of("finance.bank.manage", ctx.organization):
        if u.pk != ctx.user.pk:
            notify(u, "security", f"Bank details changed: {bank.name}", body=f"By {ctx.user.full_name}. Now ends {bank.last4}.", priority="critical",
                   link="/finance/banking")
    return bank


def reveal_bank_number(request, ctx, bank: BankAccount) -> str:
    ctx.require("finance.bank.manage")
    record(request, "finance.bank.number_viewed", category="financial", module="finance", resource=bank, sensitive=True)
    return decrypt(bank.account_number_enc) if bank.account_number_enc else ""


def import_statement(request, ctx, bank: BankAccount, file) -> dict:
    ctx.require("finance.reconciliation.manage")
    text = file.read().decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    batch = timezone.now().strftime("%Y%m%d%H%M%S")
    created = dup = bad = 0
    for r in rows:
        try:
            d = _date(r.get("date"))
            amt = dec(r.get("amount"))
        except DomainError:
            bad += 1
            continue
        fp = hashlib.sha256(f"{d}|{amt}|{r.get('reference', '')}|{r.get('description', '')}".encode()).hexdigest()
        _, made = BankTransaction.objects.get_or_create(bank_account=bank, fingerprint=fp, defaults={
            "date": d, "amount": amt, "description": str(r.get("description", ""))[:300], "reference": str(r.get("reference", ""))[:120], "import_batch": batch})
        created, dup = created + made, dup + (not made)
    matched = auto_match(bank)
    record(request, "finance.bank.statement_imported", category="financial", module="finance", resource=bank,
           metadata={"rows": len(rows), "created": created, "duplicates": dup, "invalid": bad, "auto_matched": matched})
    return {"rows": len(rows), "created": created, "duplicates": dup, "invalid": bad, "auto_matched": matched}


def auto_match(bank: BankAccount) -> int:
    n = 0
    for t in bank.transactions.filter(status="unmatched"):
        sign = "in" if t.amount > 0 else "out"
        cands = FinancePayment.objects.filter(bank_account=bank, direction=sign, amount=abs(t.amount), status="paid", reconciled=False,
                                              date__gte=t.date - timedelta(days=4), date__lte=t.date + timedelta(days=4))
        by_ref = [p for p in cands if p.number in (t.reference + t.description) or (p.reference and p.reference in (t.reference + t.description))]
        pick = by_ref[0] if by_ref else (cands.first() if cands.count() == 1 else None)
        if pick:
            t.status, t.matched_payment, t.match_method = "matched", pick, "reference" if by_ref else "amount_date"
            t.save(update_fields=["status", "matched_payment", "match_method", "updated_at"])
            pick.reconciled = True
            pick.save(update_fields=["reconciled", "updated_at"])
            n += 1
    return n


def match_manually(request, ctx, txn: BankTransaction, payment: FinancePayment | None, *, exclude_reason: str = "") -> BankTransaction:
    ctx.require("finance.reconciliation.manage")
    if txn.status != "unmatched":
        raise DomainError("Already handled.", code="invalid_state", status_code=409)
    if payment is None:
        if not exclude_reason.strip():
            raise DomainError("Say why this line is excluded.", code="reason_required")
        txn.status, txn.note = "excluded", exclude_reason[:300]
    else:
        if abs(txn.amount) != payment.amount or payment.reconciled:
            raise DomainError("Amounts differ or the payment is already reconciled.", code="validation_error")
        txn.status, txn.matched_payment, txn.match_method = "matched", payment, "manual"
        payment.reconciled = True
        payment.save(update_fields=["reconciled", "updated_at"])
    txn.matched_by = ctx.user
    txn.save()
    record(request, "finance.bank.matched", category="financial", module="finance", resource=txn, new={"status": txn.status, "note": txn.note})
    return txn


def bank_summary(bank: BankAccount) -> dict:
    book = ledger.balance(bank.gl_account)
    stmt = bank.transactions.exclude(status="excluded").aggregate(t=Sum("amount"))["t"] or ZERO
    return {"book_balance": book, "statement_movements": stmt, "unmatched": bank.transactions.filter(status="unmatched").count(),
            "unreconciled_payments": FinancePayment.objects.filter(bank_account=bank, status="paid", reconciled=False).count()}


def detect_gateway_exceptions(org) -> int:
    """Gateway / payment checks: online payments without a provider reference, duplicate references, order total mismatches."""
    from apps.payments.models import Payment

    n = 0
    online = Payment.objects.filter(status=Payment.Status.CAPTURED, method__in=["upi", "card", "netbanking"])
    for p in online.filter(provider_reference=""):
        _, made = ReconciliationException.objects.get_or_create(organization=org, kind="missing_gateway_reference", source_type="payments.payment",
                                                                source_id=str(p.pk), defaults={"area": "gateway", "amount": p.amount,
                                                                                               "description": f"{p.method} payment captured without a gateway reference"})
        n += made
    seen = {}
    for p in online.exclude(provider_reference="").values("id", "provider", "provider_reference", "amount"):
        k = (p["provider"], p["provider_reference"])
        if k in seen:
            _, made = ReconciliationException.objects.get_or_create(organization=org, kind="duplicate_gateway_reference", source_type="payments.payment",
                                                                    source_id=str(p["id"]), defaults={"area": "gateway", "amount": p["amount"],
                                                                                                      "description": f"Same gateway reference as another payment: {k[1]}"})
            n += made
        seen[k] = p["id"]
    for p in Payment.objects.filter(status=Payment.Status.CAPTURED, order__isnull=False).select_related("order"):
        paid = Payment.objects.filter(order=p.order, status=Payment.Status.CAPTURED).aggregate(t=Sum("amount"))["t"] or ZERO
        if paid > p.order.total:
            _, made = ReconciliationException.objects.get_or_create(organization=org, kind="overpaid_order", source_type="orders.order",
                                                                    source_id=str(p.order_id), defaults={"area": "gateway", "amount": paid - p.order.total,
                                                                                                         "description": f"Captured {paid} for an order totalling {p.order.total}"})
            n += made
    return n


# =====================================================================================================================
# Periods & close
# =====================================================================================================================
def ensure_close_tasks(period: FinancialPeriod):
    for i, (key, title) in enumerate(CLOSE_TASKS):
        CloseTask.objects.get_or_create(period=period, key=key, defaults={"title": title, "sequence": i})


def close_period(request, ctx, period: FinancialPeriod, *, action: str, override_reason: str = "") -> FinancialPeriod:
    ctx.require("finance.period.close")
    before = period.status
    if action == "soft_close" and period.status == "open":
        period.status = "soft_closed"
    elif action == "close" and period.status in ("open", "soft_closed"):
        ensure_close_tasks(period)
        open_tasks = period.close_tasks.filter(status="todo")
        if open_tasks.exists() and not override_reason.strip():
            raise DomainError(f"{open_tasks.count()} close tasks are still open. Complete them or give a reason to close anyway.",
                              code="close_checklist_open", status_code=409, details={"tasks": [t.title for t in open_tasks]})
        pending = Journal.objects.filter(period=period, status=Journal.Status.PENDING).count()
        if pending:
            raise DomainError(f"{pending} journals in this period are still waiting for approval.", code="journals_pending", status_code=409)
        period.status, period.closed_by, period.closed_at = "closed", ctx.user, timezone.now()
    elif action == "lock" and period.status == "closed":
        ctx.require("finance.period.reopen")
        period.status = "locked"
    else:
        raise DomainError(f"Can’t {action.replace('_', ' ')} a period that is {period.get_status_display().lower()}.", code="invalid_state", status_code=409)
    period.save()
    record(request, f"finance.period.{action}", category="financial", module="finance", resource=period, old={"status": before},
           new={"status": period.status, "override": override_reason or None})
    return period


def request_reopen(request, ctx, period: FinancialPeriod, reason: str):
    if period.status != "closed":
        raise DomainError("Only closed (not locked) periods can be reopened.", code="invalid_state", status_code=409)
    if len(reason.strip()) < 10:
        raise DomainError("Explain why the period must be reopened.", code="reason_required")
    return engine.submit(request, "finance.period_reopen", title=f"Reopen {period.name}", description=reason, resource_type="finance.period",
                         resource_id=str(period.pk), priority="high")


@on_decision("finance.period_reopen")
def _reopen_decided(req, outcome):
    if outcome != "approved":
        return
    p = FinancialPeriod.objects.filter(pk=req.resource_id, status="closed").first()
    if p is None:
        return
    step = req.steps.filter(status="approved").order_by("-sequence").first()
    p.status, p.reopened_by, p.reopened_at, p.reopen_reason = "open", step.decided_by if step else None, timezone.now(), req.description[:300]
    p.save()
    record(None, "finance.period.reopened", category="financial", module="finance", resource=p, organization=req.organization, sensitive=True,
           new={"reason": req.description[:300], "by": str(p.reopened_by_id)})


# =====================================================================================================================
# Disputes
# =====================================================================================================================
def resolve_dispute(request, ctx, d: FinancialDispute, *, status: str, resolution: str, impact=None, post_adjustment=False) -> FinancialDispute:
    ctx.require("finance.dispute.manage")
    if status not in ("investigating", "resolved", "rejected"):
        raise DomainError("Choose investigating, resolved or rejected.", code="validation_error")
    if status in ("resolved", "rejected") and not resolution.strip():
        raise DomainError("Record the resolution.", code="reason_required")
    d.status, d.resolution = status, resolution[:500]
    if impact not in (None, ""):
        d.financial_impact = dec(impact)
    if post_adjustment and status == "resolved" and d.financial_impact and d.adjustment_journal_id is None:
        entity = ledger.default_entity(d.organization)
        d.adjustment_journal = ledger.post(entity, user=ctx.user, request=request, date=timezone.localdate(), kind="adjusting",
                                           description=f"Dispute {d.number}: {resolution}"[:300],
                                           lines=[Line("refund_cost", debit=d.financial_impact), Line("refunds_payable", credit=d.financial_impact)],
                                           source=("finance", "finance.dispute", str(d.pk)))
    d.save()
    record(request, "finance.dispute.updated", category="financial", module="finance", resource=d, new={"status": status, "impact": d.financial_impact})
    return d


# Settlement approval hook lives here so all finance hooks register together.
@on_decision("finance.settlement")
def _settlement_decided(req, outcome):
    from .platform import release_batch

    b = SettlementBatch.objects.filter(pk=req.resource_id).first()
    if b is None or b.status != "pending_approval":
        return
    if outcome == "approved":
        b.status = "approved"
    elif outcome in ("rejected", "cancelled"):
        b.status = "cancelled"
        release_batch(b)
    b.save(update_fields=["status", "updated_at"])
