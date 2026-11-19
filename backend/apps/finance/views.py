"""/api/v1/os/finance/* — Finance workspace. Scoped by the central engine; entity-wide figures (P&L, platform summary,
settlements, banking) need organization-wide finance access, regional users see their region's documents."""

from __future__ import annotations

import csv
import io
from datetime import date as Date
from datetime import timedelta

from django.db.models import Q, Sum
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.response import Response

from apps.access.api import OSView
from apps.audit.models import AuditEvent
from apps.audit.services import record
from apps.core.api.exceptions import DomainError
from apps.core.api.pagination import DefaultPagination

from . import ledger, platform, reports
from . import services as svc
from .models import (Account, BankAccount, BankTransaction, Budget, BudgetLine, CloseTask, CostCenter, ExpenseCategory, ExpenseClaim, FinancePayment,
                     FinancialDispute, FinancialEntity, FinancialPeriod, FixedAsset, Invoice, Journal, PartnerAgreement, PaymentRun,
                     ReconciliationException, SettlementBatch, TaxRule, TransactionBreakdown)

ZERO = svc.ZERO


def _exact(v):
    """Money must never travel as a float: every Decimal leaves Finance as an exact string."""
    from decimal import Decimal

    if isinstance(v, Decimal):
        return str(v.quantize(Decimal("0.01"))) if v == v.quantize(Decimal("0.01")) or abs(v.as_tuple().exponent) <= 2 else str(v)
    if isinstance(v, dict):
        return {k: _exact(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_exact(x) for x in v]
    return v


class FinView(OSView):
    def finalize_response(self, request, response, *args, **kwargs):
        if isinstance(response, Response) and response.data is not None:
            response.data = _exact(response.data)
        return super().finalize_response(request, response, *args, **kwargs)

NAV = [
    ("overview", "Overview", [("home", "Finance home", "/finance", "finance.overview.view"), ("platform", "Platform revenue & GTV", "/finance/platform", "finance.overview.view"),
                              ("cash", "Cash position & forecast", "/finance/cash", "finance.bank.view|finance.reconciliation.view")]),
    ("accounting", "Accounting", [("journals", "Journals & general ledger", "/finance/journals", "finance.ledger.view"),
                                  ("accounts", "Chart of accounts", "/finance/accounts", "finance.ledger.view"),
                                  ("periods", "Periods & close", "/finance/periods", "finance.period.view")]),
    ("ar_ap", "Receivables & payables", [("receivables", "Receivables & invoices", "/finance/receivables", "finance.invoice.view"),
                                         ("payables", "Payables & vendor bills", "/finance/payables", "finance.bill.view"),
                                         ("payments", "Payments & runs", "/finance/payments", "finance.payment.view")]),
    ("partners", "Partner finance", [("settlements", "Settlements", "/finance/settlements", "finance.settlement.view"),
                                     ("statements", "Partner statements", "/finance/statements", "finance.settlement.view"),
                                     ("agreements", "Commission & agreements", "/finance/agreements", "finance.commission.view"),
                                     ("disputes", "Disputes & chargebacks", "/finance/disputes", "finance.dispute.view")]),
    ("spend", "Spend", [("expenses", "Expenses", "/finance/expenses", None), ("budgets", "Budgets & forecast", "/finance/budgets", "finance.budget.view"),
                        ("assets", "Fixed assets", "/finance/assets", "finance.asset.view")]),
    ("control", "Control", [("reconciliation", "Reconciliation", "/finance/reconciliation", "finance.reconciliation.view"),
                            ("tax", "Tax", "/finance/tax", "finance.tax.view"), ("reports", "Reports", "/finance/reports", "finance.report.view"),
                            ("controls", "Controls & audit", "/finance/controls", "finance.report.view"),
                            ("settings", "Finance settings", "/finance/settings", "finance.settings.view")]),
]


def _allowed(ctx, perm):
    return perm is None or any(ctx.has(p) for p in perm.split("|"))


def _d(v, default=None):
    return parse_date(str(v or "")) or default


def _range(request):
    today = timezone.localdate()
    return _d(request.query_params.get("from"), today.replace(day=1)), _d(request.query_params.get("to"), today)


def _org_wide(ctx, code):
    s = ctx.require(code)
    if not s.org_wide:
        raise DomainError("These figures cover the whole company and need organization-wide finance access.", code="scope_restricted", status_code=403)


def _scoped(ctx, qs, code, *, owner="created_by", unit="org_unit", department="department"):
    s = ctx.require(code)
    return qs if s.org_wide else qs.filter(s.q(unit=unit, department=department, owner=owner, organization=None))


def _page(view, qs, fn):
    pg = DefaultPagination()
    page = pg.paginate_queryset(qs, view.request, view=view)
    return pg.get_paginated_response([fn(x) for x in page])


def _csv(rows: list[dict], name: str):
    out = io.StringIO()
    if rows:
        w = csv.DictWriter(out, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    resp = HttpResponse(out.getvalue(), content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="{name}.csv"'
    return resp


def _entity(ctx):
    return ledger.default_entity(ctx.organization)


def _partner(pid):
    from apps.partners.models import Partner

    p = Partner.objects.filter(pk=pid).first() if pid else None
    if pid and p is None:
        raise DomainError("Unknown partner.", code="validation_error")
    return p


# --- serializers ----------------------------------------------------------------------------------------------------
def j_row(j: Journal):
    return {"id": str(j.pk), "number": j.number, "date": j.date, "kind": j.kind, "status": j.status, "description": j.description, "total": j.total,
            "source": f"{j.source_type}" if j.source_type else "", "source_id": j.source_id, "approval_id": str(j.approval_id) if j.approval_id else None,
            "period": j.period.name if j.period_id else None, "created_by": j.created_by.full_name if j.created_by_id else "System"}


def inv_row(i: Invoice):
    return {"id": str(i.pk), "number": i.number, "kind": i.kind, "kind_label": i.get_kind_display(), "party": i.party_name, "party_type": i.party_type,
            "issue_date": i.issue_date, "due_date": i.due_date, "total": i.total, "paid": i.amount_paid, "outstanding": i.outstanding, "status": i.status,
            "supplier_invoice_number": i.supplier_invoice_number, "match_status": i.match_status, "source": i.source_label or i.source_type,
            "currency": i.currency, "approval_id": str(i.approval_id) if i.approval_id else None, "original": i.original.number if i.original_id else None,
            "overdue": i.status in ("issued", "partially_paid") and i.due_date < timezone.localdate()}


def pay_row(p: FinancePayment):
    return {"id": str(p.pk), "number": p.number, "direction": p.direction, "purpose": p.purpose, "party": p.party_name, "amount": p.amount, "date": p.date,
            "status": p.status, "reference": p.reference, "bank": p.bank_account.name if p.bank_account_id else None, "reconciled": p.reconciled,
            "invoice": p.invoice.number if p.invoice_id else None, "run": p.run.number if p.run_id else None,
            "approval_id": str(p.approval_id) if p.approval_id else None, "created_by": p.created_by.full_name if p.created_by_id else None}


def claim_row(c: ExpenseClaim):
    return {"id": str(c.pk), "number": c.number, "claimant": c.claimant.full_name, "category": c.category.name, "date": c.date, "amount": c.amount,
            "purpose": c.purpose, "merchant": c.merchant, "status": c.status, "status_label": c.get_status_display(), "policy_flags": c.policy_flags,
            "has_receipt": c.has_receipt, "approval_id": str(c.approval_id) if c.approval_id else None}


def agr_row(a: PartnerAgreement):
    return {"id": str(a.pk), "code": a.code, "partner": platform.pname(a.partner) if a.partner_id else "Default (all partners)", "partner_id": str(a.partner_id) if a.partner_id else None,
            "commercial_model": a.commercial_model, "commission_pct": a.commission_pct, "platform_fee_pct": a.platform_fee_pct, "fixed_fee": a.fixed_fee,
            "tax_on_fees_pct": a.tax_on_fees_pct, "delivery_fee_to": a.delivery_fee_to, "promo_funding": a.promo_funding,
            "refund_responsibility": a.refund_responsibility, "settlement_frequency": a.settlement_frequency, "effective_from": a.effective_from,
            "effective_to": a.effective_to, "version": a.version, "status": a.status, "approval_id": str(a.approval_id) if a.approval_id else None}


def batch_row(b: SettlementBatch):
    return {"id": str(b.pk), "number": b.number, "period_to": b.period_to, "status": b.status, "partners": b.partners, "gross": b.gross_partner_amount,
            "deductions": b.deductions, "refunds": b.refund_adjustments, "net_payable": b.net_payable, "created_at": b.created_at, "paid_at": b.paid_at,
            "approval_id": str(b.approval_id) if b.approval_id else None, "created_by": b.created_by.full_name if b.created_by_id else None}


# --- overview -------------------------------------------------------------------------------------------------------
class NavView(FinView):
    def get(self, request):
        ctx = self.authz
        out = []
        for key, label, items in NAV:
            vis = [{"key": k, "label": lbl, "path": p} for k, lbl, p, perm in items if _allowed(ctx, perm)]
            if vis:
                out.append({"key": key, "label": label, "items": vis})
        return Response({"sections": out})


class HomeView(FinView):
    def get(self, request):
        ctx = self.authz
        if not ctx.has("finance.overview.view"):
            return Response({"mode": "self", "claims": [claim_row(c) for c in ExpenseClaim.objects.filter(claimant=request.user).select_related("category", "claimant")[:10]]})
        from apps.workflows.selectors import inbox_for

        org = ctx.organization
        inbox = [r for r in inbox_for(ctx) if r.policy.module == "finance" or r.policy.key == "procurement.request"]
        data = {"mode": "finance", "org_wide": ctx.scope("finance.overview.view").org_wide,
                "my_work": {"approvals": len(inbox), "approvals_by_type": _count_by(inbox),
                            "payments_to_release": FinancePayment.objects.filter(organization=org, status="approved").count() if ctx.has("finance.payment.execute") else None,
                            "runs_to_release": PaymentRun.objects.filter(organization=org, status="approved").count() if ctx.has("finance.payment.execute") else None,
                            "bills_to_submit": Invoice.objects.filter(organization=org, kind="vendor_bill", status="draft").count(),
                            "recon_exceptions": ReconciliationException.objects.filter(organization=org, status="open").count(),
                            "close_tasks": CloseTask.objects.filter(period__entity__organization=org, status="todo", owner=request.user).count()},
                "alerts": finance_alerts(ctx)}
        if data["org_wide"]:
            data["pulse"] = reports.pulse(ctx)
        return Response(data)


def _count_by(reqs):
    out = {}
    for r in reqs:
        out[r.policy.name] = out.get(r.policy.name, 0) + 1
    return out


def finance_alerts(ctx) -> list[dict]:
    org = ctx.organization
    today = timezone.localdate()
    out = []

    def add(sev, title, n, path):
        if n:
            out.append({"severity": sev, "title": title, "count": n, "path": path})

    add("high", "Overdue receivables", Invoice.objects.filter(organization=org, kind__in=["customer_invoice", "partner_invoice"],
                                                              status__in=["issued", "partially_paid"], due_date__lt=today).count(), "/finance/receivables?overdue=1")
    add("medium", "Bills overdue for payment", Invoice.objects.filter(organization=org, kind="vendor_bill", status__in=["issued", "partially_paid"],
                                                                      due_date__lt=today).count(), "/finance/payables")
    add("high", "Open reconciliation exceptions", ReconciliationException.objects.filter(organization=org, status="open").count(), "/finance/reconciliation")
    add("medium", "Unmatched bank lines", BankTransaction.objects.filter(bank_account__entity__organization=org, status="unmatched").count(), "/finance/reconciliation")
    add("high", "Settlement exceptions", SettlementBatch.objects.filter(organization=org, status="exception").count(), "/finance/settlements")
    add("medium", "Payments failed", FinancePayment.objects.filter(organization=org, status="failed").count(), "/finance/payments")
    from apps.payments.models import Payment

    add("medium", "Failed customer payments (24h)", Payment.objects.filter(status="failed", created_at__gte=timezone.now() - timedelta(days=1)).count(),
        "/finance/platform")
    for b in Budget.objects.filter(organization=org, status="active"):
        f = svc.budget_figures(b, today)
        if f["available"] < 0:
            out.append({"severity": "high", "title": f"Budget exceeded: {b.name}", "count": 1, "path": f"/finance/budgets?open={b.pk}"})
    prev = FinancialPeriod.objects.filter(entity__organization=org, end__lt=today.replace(day=1), status="open").order_by("-end").first()
    if prev and (today - prev.end).days > 10:
        out.append({"severity": "medium", "title": f"Period {prev.name} still open {(today - prev.end).days} days after month end", "count": 1, "path": "/finance/periods"})
    return out


class PlatformView(FinView):
    permissions = {"GET": "finance.overview.view"}

    def get(self, request):
        _org_wide(self.authz, "finance.overview.view")
        a, b = _range(request)
        data = platform.platform_summary(self.authz.organization, a, b)
        data["unit_economics"] = platform.unit_economics(self.authz.organization, a, b)
        return Response(data)


class SyncView(FinView):
    permissions = {"POST": "finance.ledger.create"}

    def post(self, request):
        _org_wide(self.authz, "finance.ledger.create")
        out = platform.sync(self.authz.organization)
        out["gateway_exceptions"] = svc.detect_gateway_exceptions(self.authz.organization)
        record(request, "finance.platform.synced", category="financial", module="finance", metadata=out)
        return Response(out)


class BreakdownsView(FinView):
    permissions = {"GET": "finance.settlement.view"}

    def get(self, request):
        _org_wide(self.authz, "finance.settlement.view")
        qs = TransactionBreakdown.objects.filter(organization=self.authz.organization).select_related("partner", "journal")
        p = request.query_params
        if p.get("partner"):
            qs = qs.filter(partner_id=p["partner"])
        if p.get("kind"):
            qs = qs.filter(kind=p["kind"])
        if p.get("settlement"):
            qs = qs.filter(settlement_status=p["settlement"])
        return _page(self, qs, lambda b: {"id": str(b.pk), "kind": b.kind, "date": b.occurred_at, "store": b.store_name, "partner": platform.pname(b.partner) if b.partner_id else None,
                                          "model": b.commercial_model, "method": b.method, "gross": b.gross, "commission": b.commission, "platform_fee": b.platform_fee,
                                          "fee_tax": b.fee_tax, "gateway_fee": b.gateway_fee, "discount_click": b.discount_click, "partner_share": b.partner_share,
                                          "click_revenue": b.click_revenue, "click_net": b.click_net, "settlement": b.settlement_status,
                                          "journal": b.journal.number if b.journal_id else None, "journal_id": str(b.journal_id) if b.journal_id else None,
                                          "agreement": b.agreement_snapshot.get("code")})


# --- accounting -----------------------------------------------------------------------------------------------------
class EntitiesView(FinView):
    permissions = {"GET": "finance.ledger.view"}

    def get(self, request):
        return Response({"results": [{"id": str(e.pk), "code": e.code, "name": e.name, "legal_name": e.legal_name, "currency": e.base_currency,
                                      "fy_start_month": e.fiscal_year_start_month, "default": e.is_default,
                                      "tax_registration": (e.tax_registration[:2] + "•" * max(0, len(e.tax_registration) - 5) + e.tax_registration[-3:]) if e.tax_registration else ""}
                                     for e in FinancialEntity.objects.filter(organization=self.authz.organization)]})


class AccountsView(FinView):
    permissions = {"GET": "finance.ledger.view", "POST": "finance.settings.configure"}

    def get(self, request):
        e = _entity(self.authz)
        with_bal = request.query_params.get("balances") == "true" and self.authz.scope("finance.ledger.view").org_wide
        rows = []
        for a in Account.objects.filter(entity=e).select_related("parent").order_by("code"):
            rows.append({"id": str(a.pk), "code": a.code, "name": a.name, "type": a.type, "system_key": a.system_key, "postable": a.is_postable,
                         "active": a.is_active, "parent": a.parent.code if a.parent_id else None,
                         **({"balance": ledger.balance(a)} if with_bal and a.is_postable else {})})
        return Response({"results": rows, "types": [{"value": v, "label": lbl} for v, lbl in Account.Type.choices]})

    def post(self, request):
        e, d = _entity(self.authz), request.data
        code, name = str(d.get("code", "")).strip(), str(d.get("name", "")).strip()
        if not code or not name or d.get("type") not in Account.Type.values:
            raise DomainError("Enter code, name and type.", code="validation_error")
        if Account.objects.filter(entity=e, code=code).exists():
            raise DomainError("This code is in use.", code="validation_error", details={"code": ["In use."]})
        parent = Account.objects.filter(entity=e, pk=d.get("parent_id")).first() if d.get("parent_id") else None
        a = Account.objects.create(entity=e, code=code[:20], name=name[:150], type=d["type"], parent=parent, description=str(d.get("description", ""))[:300])
        record(request, "finance.account.create", category="config", module="finance", resource=a, new={"code": a.code, "name": a.name})
        return Response({"id": str(a.pk)}, status=status.HTTP_201_CREATED)


class AccountDetailView(FinView):
    permissions = {"PATCH": "finance.settings.configure"}

    def patch(self, request, pk):
        a = Account.objects.filter(pk=pk, entity__organization=self.authz.organization).first()
        if a is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        before = {"name": a.name, "active": a.is_active}
        if "name" in request.data:
            a.name = str(request.data["name"])[:150]
        if "is_active" in request.data:
            if not request.data["is_active"] and a.system_key:
                raise DomainError("This account is used by automatic postings and can’t be deactivated.", code="validation_error")
            a.is_active = bool(request.data["is_active"])
        a.save()
        record(request, "finance.account.update", category="config", module="finance", resource=a, old=before, new={"name": a.name, "active": a.is_active})
        return Response({"id": str(a.pk)})


class LedgerView(FinView):
    permissions = {"GET": "finance.ledger.view"}

    def get(self, request, pk):
        _org_wide(self.authz, "finance.ledger.view")
        a = Account.objects.filter(pk=pk, entity__organization=self.authz.organization).first()
        if a is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        f, t = _range(request)
        data = reports.general_ledger(a.entity, a, f, t)
        if request.query_params.get("export") == "csv":
            self.authz.require("finance.ledger.export")
            record(request, "finance.ledger.export", category="export", module="finance", resource=a, metadata={"rows": len(data["rows"])})
            return _csv(data["rows"], f"ledger-{a.code}")
        return Response(data)


class JournalsView(FinView):
    permissions = {"GET": "finance.ledger.view", "POST": "finance.ledger.create"}

    def get(self, request):
        qs = _scoped(self.authz, Journal.objects.filter(organization=self.authz.organization).select_related("period", "created_by"), "finance.ledger.view")
        p = request.query_params
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        if p.get("kind"):
            qs = qs.filter(kind=p["kind"])
        if q := p.get("q", "").strip():
            qs = qs.filter(Q(number__icontains=q) | Q(description__icontains=q) | Q(reference__icontains=q))
        f, t = _d(p.get("from")), _d(p.get("to"))
        if f:
            qs = qs.filter(date__gte=f)
        if t:
            qs = qs.filter(date__lte=t)
        return _page(self, qs, j_row)

    def post(self, request):
        d = request.data
        j = svc.create_journal(request, self.authz, date=d.get("date"), description=str(d.get("description", ""))[:300], lines=d.get("lines") or [],
                               kind=d.get("kind") or "manual", reference=str(d.get("reference", "")))
        return Response(j_row(j), status=status.HTTP_201_CREATED)


class JournalDetailView(FinView):
    permissions = {"GET": "finance.ledger.view"}

    def get(self, request, pk):
        j = _scoped(self.authz, Journal.objects.filter(organization=self.authz.organization), "finance.ledger.view").filter(pk=pk).first()
        if j is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        return Response({**j_row(j), "reference": j.reference, "currency": j.currency, "fx_rate": j.fx_rate, "posted_at": j.posted_at,
                         "posted_by": j.posted_by.full_name if j.posted_by_id else None, "reversal_of": j.reversal_of.number if j.reversal_of_id else None,
                         "reversed_by": getattr(getattr(j, "reversed_by", None), "number", None), "reversal_reason": j.reversal_reason,
                         "lines": [{"account": f"{ln.account.code} {ln.account.name}", "account_id": str(ln.account_id), "debit": ln.debit, "credit": ln.credit,
                                    "description": ln.description, "party": ln.party_name or (platform.pname(ln.partner) if ln.partner_id else ""),
                                    "cost_center": ln.cost_center.code if ln.cost_center_id else None}
                                   for ln in j.lines.select_related("account", "partner", "cost_center")]})


class JournalReverseView(FinView):
    permissions = {"POST": "finance.ledger.approve"}

    def post(self, request, pk):
        j = Journal.objects.filter(pk=pk, organization=self.authz.organization).first()
        if j is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        r = ledger.reverse(j, reason=str(request.data.get("reason", "")), user=request.user, request=request)
        return Response(j_row(r), status=status.HTTP_201_CREATED)


class PeriodsView(FinView):
    permissions = {"GET": "finance.period.view"}

    def get(self, request):
        e = _entity(self.authz)
        today = timezone.localdate()
        ledger.period_for(e, today)  # current month always exists
        rows = []
        for p in FinancialPeriod.objects.filter(entity=e).order_by("-start")[:24]:
            tasks = p.close_tasks
            rows.append({"id": str(p.pk), "name": p.name, "start": p.start, "end": p.end, "status": p.status, "status_label": p.get_status_display(),
                         "closed_by": p.closed_by.full_name if p.closed_by_id else None, "closed_at": p.closed_at,
                         "reopened_by": p.reopened_by.full_name if p.reopened_by_id else None, "reopen_reason": p.reopen_reason,
                         "tasks_done": tasks.exclude(status="todo").count(), "tasks_total": tasks.count(),
                         "journals": Journal.objects.filter(period=p, status="posted").count()})
        return Response({"results": rows})


class PeriodActionView(FinView):
    def post(self, request, pk, action):
        ctx = self.authz
        p = FinancialPeriod.objects.filter(pk=pk, entity__organization=ctx.organization).first()
        if p is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        if action == "reopen":
            ctx.require("finance.period.close")
            req = svc.request_reopen(request, ctx, p, str(request.data.get("reason", "")))
            return Response({"approval_id": str(req.pk)}, status=status.HTTP_201_CREATED)
        if action == "tasks":
            ctx.require("finance.period.view")
            svc.ensure_close_tasks(p)
            return Response({"results": [{"id": str(t.pk), "key": t.key, "title": t.title, "status": t.status, "note": t.note,
                                          "owner": t.owner.full_name if t.owner_id else None, "completed_by": t.completed_by.full_name if t.completed_by_id else None,
                                          "completed_at": t.completed_at} for t in p.close_tasks.select_related("owner", "completed_by")]})
        if action == "depreciation":
            return Response(svc.run_depreciation(request, ctx, p))
        svc.close_period(request, ctx, p, action=action, override_reason=str(request.data.get("override_reason", "")))
        return Response({"status": p.status})


class CloseTaskView(FinView):
    permissions = {"PATCH": "finance.period.close"}

    def patch(self, request, pk):
        t = CloseTask.objects.filter(pk=pk, period__entity__organization=self.authz.organization).select_related("period").first()
        if t is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        if t.period.status in ("closed", "locked"):
            raise DomainError("The period is closed.", code="period_closed", status_code=409)
        if request.data.get("status") in ("todo", "done", "na"):
            t.status = request.data["status"]
            t.completed_by, t.completed_at = (request.user, timezone.now()) if t.status != "todo" else (None, None)
        if "note" in request.data:
            t.note = str(request.data["note"])[:300]
        if "owner_id" in request.data:
            from apps.users.models import User

            t.owner = User.objects.filter(pk=request.data["owner_id"]).first()
        t.save()
        record(request, "finance.close_task.update", category="financial", module="finance", resource=t.period, resource_label=t.title,
               new={"status": t.status})
        return Response({"id": str(t.pk), "status": t.status})


# --- receivables / payables ------------------------------------------------------------------------------------------
class InvoicesView(FinView):
    def get(self, request):
        ctx = self.authz
        p = request.query_params
        kind = p.get("kind", "receivable")
        code = "finance.bill.view" if kind == "payable" else "finance.invoice.view"
        kinds = ["vendor_bill"] if kind == "payable" else ["customer_invoice", "partner_invoice", "credit_note", "debit_note"]
        qs = _scoped(ctx, Invoice.objects.filter(organization=ctx.organization, kind__in=kinds).select_related("original"), code)
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        if p.get("overdue") == "1":
            qs = qs.filter(status__in=["issued", "partially_paid"], due_date__lt=timezone.localdate())
        if q := p.get("q", "").strip():
            qs = qs.filter(Q(number__icontains=q) | Q(party_name__icontains=q) | Q(supplier_invoice_number__icontains=q))
        if p.get("export") == "csv":
            ctx.require("finance.bill.export" if kind == "payable" else "finance.invoice.export")
            rows = [inv_row(i) for i in qs[:20000]]
            record(request, f"finance.{kind}.export", category="export", module="finance", metadata={"rows": len(rows)})
            return _csv(rows, f"{kind}s")
        return _page(self, qs, inv_row)

    def post(self, request):
        d = request.data
        kind = d.get("kind") if d.get("kind") in ("customer_invoice", "partner_invoice", "vendor_bill") else "customer_invoice"
        inv = svc.create_invoice(request, self.authz, d, kind=kind)
        return Response(inv_row(inv), status=status.HTTP_201_CREATED)


class InvoiceDetailView(FinView):
    def _get(self, pk):
        inv = Invoice.objects.filter(pk=pk, organization=self.authz.organization).select_related("original", "journal").first()
        if inv is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        code = "finance.bill.view" if inv.kind == "vendor_bill" or (inv.original_id and inv.original.kind == "vendor_bill") else "finance.invoice.view"
        if not _scoped(self.authz, Invoice.objects.filter(pk=inv.pk), code).exists():
            raise DomainError("Not found.", code="not_found", status_code=404)
        return inv

    def get(self, request, pk):
        inv = self._get(pk)
        return Response({**inv_row(inv), "terms": inv.terms, "reason": inv.reason, "match_detail": inv.match_detail, "revenue_type": inv.revenue_type,
                         "journal": inv.journal.number if inv.journal_id else None, "journal_id": str(inv.journal_id) if inv.journal_id else None,
                         "source_type": inv.source_type, "source_id": inv.source_id, "subtotal": inv.subtotal, "tax_total": inv.tax_total,
                         "lines": [{"description": ln.description, "quantity": ln.quantity, "unit_price": ln.unit_price, "tax_rate": ln.tax_rate,
                                    "tax_amount": ln.tax_amount, "line_total": ln.line_total, "account": f"{ln.account.code} {ln.account.name}" if ln.account_id else None}
                                   for ln in inv.lines.select_related("account")],
                         "notes": [inv_row(n) for n in inv.notes.all()], "payments": [pay_row(p) for p in inv.payments.select_related("bank_account", "invoice", "run", "created_by")]})

    def post(self, request, pk, action=None):
        ctx, d = self.authz, request.data
        inv = self._get(pk)
        if action == "issue":
            svc.issue_invoice(request, ctx, inv)
        elif action == "submit":
            svc.submit_bill(request, ctx, inv, override_reason=str(d.get("override_reason", "")))
        elif action == "match":
            ctx.require("finance.bill.view")
            return Response(svc.run_match(inv))
        elif action in ("credit_note", "debit_note"):
            note = svc.create_note(request, ctx, inv, kind=action, amount=d.get("amount"), reason=str(d.get("reason", "")))
            return Response(inv_row(note), status=status.HTTP_201_CREATED)
        elif action == "receive":
            bank = BankAccount.objects.filter(pk=d.get("bank_account_id"), entity=inv.entity).first()
            if bank is None:
                raise DomainError("Choose the bank account.", code="validation_error")
            pay = svc.receive_payment(request, ctx, inv, amount=d.get("amount"), date=d.get("date") or timezone.localdate().isoformat(), bank_account=bank,
                                      reference=str(d.get("reference", "")))
            return Response(pay_row(pay), status=status.HTTP_201_CREATED)
        elif action == "void":
            ctx.require("finance.invoice.edit" if inv.kind != "vendor_bill" else "finance.bill.create")
            svc.void_draft(request, ctx, inv, str(d.get("reason", "")))
        elif action == "dispute":
            ctx.require("finance.dispute.manage")
            inv.status = Invoice.Status.DISPUTED
            inv.save(update_fields=["status", "updated_at"])
        else:
            raise DomainError("Not found.", code="not_found", status_code=404)
        inv.refresh_from_db()
        return Response(inv_row(inv))


class PaymentsView(FinView):
    permissions = {"GET": "finance.payment.view", "POST": "finance.payment.create"}

    def get(self, request):
        ctx = self.authz
        qs = _scoped(ctx, FinancePayment.objects.filter(organization=ctx.organization).select_related("bank_account", "invoice", "run", "created_by"),
                     "finance.payment.view", unit="invoice__org_unit", department="invoice__department")
        p = request.query_params
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        if p.get("direction"):
            qs = qs.filter(direction=p["direction"])
        runs = [{"id": str(r.pk), "number": r.number, "status": r.status, "total": r.total, "payments": r.payments.count(), "created_at": r.created_at,
                 "approval_id": str(r.approval_id) if r.approval_id else None} for r in PaymentRun.objects.filter(organization=ctx.organization)[:20]]
        resp = _page(self, qs, pay_row)
        resp.data["runs"] = runs
        return resp

    def post(self, request):
        ctx, d = self.authz, request.data
        inv = Invoice.objects.filter(pk=d.get("invoice_id"), organization=ctx.organization).first() if d.get("invoice_id") else None
        claim = ExpenseClaim.objects.filter(pk=d.get("expense_claim_id"), organization=ctx.organization).first() if d.get("expense_claim_id") else None
        bank = BankAccount.objects.filter(pk=d.get("bank_account_id"), entity__organization=ctx.organization).first() if d.get("bank_account_id") else None
        pay = svc.create_outgoing(request, ctx, invoice=inv, claim=claim, amount=d.get("amount"), date=d.get("date"), bank_account=bank,
                                  reference=str(d.get("reference", "")), allow_duplicate=bool(d.get("confirm_not_duplicate")))
        svc.submit_payment(request, ctx, pay)
        return Response(pay_row(pay), status=status.HTTP_201_CREATED)


class PaymentActionView(FinView):
    def post(self, request, pk, action):
        ctx = self.authz
        pay = FinancePayment.objects.filter(pk=pk, organization=ctx.organization).first()
        if pay is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        if action == "execute":
            bank = BankAccount.objects.filter(pk=request.data.get("bank_account_id"), entity__organization=ctx.organization).first() if request.data.get("bank_account_id") else None
            svc.execute_payment(request, ctx, pay, bank_account=bank, reference=str(request.data.get("reference", "")))
        elif action == "fail":
            ctx.require("finance.payment.execute")
            if pay.status != "approved":
                raise DomainError("Only approved payments can be marked failed.", code="invalid_state", status_code=409)
            pay.status, pay.failure_reason = "failed", str(request.data.get("reason", ""))[:200]
            pay.save(update_fields=["status", "failure_reason", "updated_at"])
        else:
            raise DomainError("Not found.", code="not_found", status_code=404)
        return Response(pay_row(pay))


class RunsView(FinView):
    permissions = {"POST": "finance.payment.create"}

    def post(self, request):
        ctx, d = self.authz, request.data
        bank = BankAccount.objects.filter(pk=d.get("bank_account_id"), entity__organization=ctx.organization).first()
        run = svc.create_run(request, ctx, due_by=_d(d.get("due_by"), timezone.localdate() + timedelta(days=7)),
                             include_reimbursements=bool(d.get("include_reimbursements", True)), bank_account=bank)
        return Response({"id": str(run.pk), "number": run.number, "total": run.total}, status=status.HTTP_201_CREATED)


class RunExecuteView(FinView):
    permissions = {"POST": "finance.payment.execute"}

    def post(self, request, pk):
        run = PaymentRun.objects.filter(pk=pk, organization=self.authz.organization).first()
        if run is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        svc.execute_run(request, self.authz, run)
        return Response({"status": run.status})


# --- partner finance ------------------------------------------------------------------------------------------------
class AgreementsView(FinView):
    permissions = {"GET": "finance.commission.view", "POST": "finance.commission.configure"}

    def get(self, request):
        qs = PartnerAgreement.objects.filter(organization=self.authz.organization).select_related("partner")
        if request.query_params.get("partner"):
            qs = qs.filter(Q(partner_id=request.query_params["partner"]) | Q(partner__isnull=True))
        return Response({"results": [agr_row(a) for a in qs[:300]]})

    def post(self, request):
        a = svc.propose_agreement(request, self.authz, request.data)
        return Response(agr_row(a), status=status.HTTP_201_CREATED)


class SettlementsView(FinView):
    permissions = {"GET": "finance.settlement.view", "POST": "finance.settlement.create"}

    def get(self, request):
        _org_wide(self.authz, "finance.settlement.view")
        org = self.authz.organization
        unsettled = TransactionBreakdown.objects.filter(organization=org, settlement_status="unsettled", partner__isnull=False)
        return Response({"results": [batch_row(b) for b in SettlementBatch.objects.filter(organization=org).select_related("created_by")[:100]],
                         "pending_pool": {"transactions": unsettled.count(), "partners": unsettled.values("partner").distinct().count(),
                                          "partner_share": unsettled.aggregate(t=Sum("partner_share"))["t"] or ZERO},
                         "liability": ledger.key_balance(_entity(self.authz), "partner_payable")})

    def post(self, request):
        _org_wide(self.authz, "finance.settlement.create")
        b = platform.create_batch(request, self.authz, _d(request.data.get("period_to"), timezone.localdate()))
        if request.data.get("submit", True):
            platform.submit_batch(request, self.authz, b)
        return Response(batch_row(b), status=status.HTTP_201_CREATED)


class SettlementDetailView(FinView):
    permissions = {"GET": "finance.settlement.view"}

    def get(self, request, pk):
        _org_wide(self.authz, "finance.settlement.view")
        b = SettlementBatch.objects.filter(pk=pk, organization=self.authz.organization).first()
        if b is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        rows = [{"id": str(ln.pk), "partner": platform.pname(ln.partner), "partner_id": str(ln.partner_id), "transactions": ln.transactions, "gross": ln.gross,
                 "commission": ln.commission, "platform_fee": ln.platform_fee, "fee_tax": ln.fee_tax, "refunds": ln.refunds, "adjustments": ln.adjustments,
                 "partner_share": ln.partner_share, "net_payable": ln.net_payable, "status": ln.status,
                 "payment": ln.payment.number if ln.payment_id else None} for ln in b.lines.select_related("partner", "payment")]
        if request.query_params.get("export") == "csv":
            self.authz.require("finance.settlement.export")
            record(request, "finance.settlement.export", category="export", module="finance", resource=b)
            return _csv(rows, f"settlement-{b.number}")
        return Response({**batch_row(b), "lines": rows})

    def post(self, request, pk, action=None):
        ctx = self.authz
        b = SettlementBatch.objects.filter(pk=pk, organization=ctx.organization).first()
        if b is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        if action == "submit":
            ctx.require("finance.settlement.create")
            platform.submit_batch(request, ctx, b)
        elif action == "pay":
            bank = BankAccount.objects.filter(pk=request.data.get("bank_account_id"), entity__organization=ctx.organization).first()
            if bank is None:
                raise DomainError("Choose the bank account.", code="validation_error")
            platform.pay_batch(request, ctx, b, bank, str(request.data.get("reference", "")))
        else:
            raise DomainError("Not found.", code="not_found", status_code=404)
        return Response(batch_row(b))


class AdjustmentsView(FinView):
    permissions = {"POST": "finance.settlement.create"}

    def post(self, request):
        d = request.data
        p = _partner(d.get("partner_id"))
        if p is None:
            raise DomainError("Choose a partner.", code="validation_error")
        a = platform.add_adjustment(request, self.authz, p, d.get("kind") or "deduction", d.get("amount"), str(d.get("reason", "")))
        return Response({"id": str(a.pk)}, status=status.HTTP_201_CREATED)


class StatementView(FinView):
    permissions = {"GET": "finance.settlement.view"}

    def get(self, request):
        _org_wide(self.authz, "finance.settlement.view")
        p = _partner(request.query_params.get("partner"))
        if p is None:
            raise DomainError("Choose a partner.", code="validation_error")
        a, b = _range(request)
        record(request, "finance.statement.viewed", category="financial", module="finance", resource_type="partner", resource_id=str(p.pk))
        return Response(platform.statement(self.authz.organization, p, a, b))


class PartnersLookupView(FinView):
    permissions = {"GET": "finance.overview.view"}

    def get(self, request):
        from apps.partners.models import Partner

        q = request.query_params.get("q", "").strip()
        qs = Partner.objects.all()
        if q:
            qs = qs.filter(business_name__icontains=q)
        return Response({"results": [{"id": str(p.pk), "name": platform.pname(p)} for p in qs.order_by("business_name")[:30]]})


class DisputesView(FinView):
    permissions = {"GET": "finance.dispute.view", "POST": "finance.dispute.manage"}

    def get(self, request):
        qs = FinancialDispute.objects.filter(organization=self.authz.organization).select_related("owner", "partner")
        return Response({"results": [{"id": str(x.pk), "number": x.number, "kind": x.kind, "kind_label": x.get_kind_display(), "party": x.party_name,
                                      "amount": x.amount, "reason": x.reason, "owner": x.owner.full_name if x.owner_id else None, "deadline": x.deadline,
                                      "status": x.status, "resolution": x.resolution, "impact": x.financial_impact,
                                      "overdue": bool(x.deadline and x.deadline < timezone.localdate() and x.status in ("open", "investigating"))}
                                     for x in qs[:200]]})

    def post(self, request):
        d = request.data
        if d.get("kind") not in FinancialDispute.Kind.values or not str(d.get("party_name", "")).strip():
            raise DomainError("Choose the type and the party.", code="validation_error")
        x = FinancialDispute.objects.create(organization=self.authz.organization, number=ledger.next_number(self.authz.organization, "dispute"),
                                            kind=d["kind"], party_type=d.get("party_type") or "customer", party_name=str(d["party_name"])[:160],
                                            partner=_partner(d.get("partner_id")), amount=svc.dec(d.get("amount")), reason=str(d.get("reason", ""))[:500],
                                            source_type=str(d.get("source_type", ""))[:40], source_id=str(d.get("source_id", ""))[:64], owner=request.user,
                                            deadline=_d(d.get("deadline")))
        record(request, "finance.dispute.create", category="financial", module="finance", resource=x, new={"amount": x.amount, "kind": x.kind})
        return Response({"id": str(x.pk), "number": x.number}, status=status.HTTP_201_CREATED)


class DisputeDetailView(FinView):
    permissions = {"PATCH": "finance.dispute.manage"}

    def patch(self, request, pk):
        x = FinancialDispute.objects.filter(pk=pk, organization=self.authz.organization).first()
        if x is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        d = request.data
        svc.resolve_dispute(request, self.authz, x, status=d.get("status", ""), resolution=str(d.get("resolution", "")), impact=d.get("impact"),
                            post_adjustment=bool(d.get("post_adjustment")))
        return Response({"status": x.status})


# --- spend ----------------------------------------------------------------------------------------------------------
class ExpensesView(FinView):
    def get(self, request):
        ctx = self.authz
        base = ExpenseClaim.objects.filter(organization=ctx.organization).select_related("category", "claimant")
        if request.query_params.get("view") == "all":
            qs = _scoped(ctx, base, "finance.expense.view", owner="claimant")
        else:
            qs = base.filter(claimant=request.user)
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        resp = _page(self, qs, claim_row)
        resp.data["categories"] = [{"id": str(c.pk), "name": c.name, "limit": c.limit_per_claim, "receipt_above": c.receipt_required_above,
                                    "mileage_rate": c.mileage_rate, "note": c.policy_note}
                                   for c in ExpenseCategory.objects.filter(organization=ctx.organization, is_active=True)]
        resp.data["can_view_all"] = ctx.has("finance.expense.view")
        return resp

    def post(self, request):
        c = svc.submit_claim(request, self.authz, request.data)
        return Response(claim_row(c), status=status.HTTP_201_CREATED)


class BudgetsView(FinView):
    permissions = {"GET": "finance.budget.view", "POST": "finance.budget.create"}

    def get(self, request):
        ctx = self.authz
        qs = _scoped(ctx, Budget.objects.filter(organization=ctx.organization).select_related("department", "org_unit", "cost_center", "owner")
                     .prefetch_related("lines", "commitments"), "finance.budget.view", owner="owner")
        rows = []
        for b in qs[:200]:
            rows.append({"id": str(b.pk), "number": b.number, "name": b.name, "fiscal_year": b.fiscal_year, "status": b.status,
                         "department": b.department.name if b.department_id else None, "unit": b.org_unit.name if b.org_unit_id else None,
                         "cost_center": b.cost_center.code if b.cost_center_id else None, "category": b.category, "owner": b.owner.full_name if b.owner_id else None,
                         "approval_id": str(b.approval_id) if b.approval_id else None, **svc.budget_figures(b)})
        return Response({"results": rows})

    def post(self, request):
        ctx, d = self.authz, request.data
        from apps.organization.models import Department, OrgUnit

        e = _entity(ctx)
        name = str(d.get("name", "")).strip()
        if not name or not d.get("lines"):
            raise DomainError("Name the budget and add at least one line.", code="validation_error")
        dept = Department.objects.filter(pk=d.get("department_id"), organization=ctx.organization).first() if d.get("department_id") else None
        unit = OrgUnit.objects.filter(pk=d.get("org_unit_id"), organization=ctx.organization).first() if d.get("org_unit_id") else None
        ctx.require("finance.budget.create", **{k: v for k, v in {"department": dept, "unit": unit}.items() if v})
        b = Budget.objects.create(organization=ctx.organization, entity=e, number=ledger.next_number(ctx.organization, "budget"), name=name[:150],
                                  fiscal_year=int(d.get("fiscal_year") or ledger.fiscal_year_of(e, timezone.localdate())), department=dept, org_unit=unit,
                                  cost_center=CostCenter.objects.filter(pk=d.get("cost_center_id"), organization=ctx.organization).first() if d.get("cost_center_id") else None,
                                  category=str(d.get("category", ""))[:40], owner=request.user, notes=str(d.get("notes", ""))[:500])
        for ln in d["lines"]:
            BudgetLine.objects.create(budget=b, amount=svc.dec(ln.get("amount")), month=ln.get("month") or None,
                                      account=Account.objects.filter(entity=e, pk=ln.get("account_id")).first() if ln.get("account_id") else None)
        record(request, "finance.budget.create", category="financial", module="finance", resource=b, new={"amount": b.amount})
        if d.get("submit", True):
            svc.submit_budget(request, ctx, b)
        return Response({"id": str(b.pk), "number": b.number}, status=status.HTTP_201_CREATED)


class BudgetCheckView(FinView):
    """Read by Procurement and the request forms: budget, committed, available, after this request."""

    def get(self, request):
        from apps.organization.models import Department

        ctx = self.authz
        p = request.query_params
        dept = Department.objects.filter(pk=p.get("department"), organization=ctx.organization).first() if p.get("department") else (ctx.employee.department if ctx.employee else None)
        res = svc.check_budget(ctx.organization, p.get("amount") or 0, department=dept, org_unit=ctx.employee.org_unit if ctx.employee else None,
                               category=p.get("category", ""))
        if not ctx.has("finance.budget.view"):  # requesters see whether it fits, not internal budget figures
            res = {k: res[k] for k in ("found", "status", "message", "amount")}
        return Response(res)


class AssetsView(FinView):
    permissions = {"GET": "finance.asset.view", "POST": "finance.asset.create"}

    def get(self, request):
        qs = FixedAsset.objects.filter(organization=self.authz.organization).select_related("department", "org_unit", "custodian")
        return Response({"results": [{"id": str(a.pk), "number": a.number, "name": a.name, "category": a.category, "acquired": a.acquisition_date, "cost": a.cost,
                                      "accumulated": a.accumulated_depreciation, "book_value": a.book_value, "life_months": a.useful_life_months,
                                      "status": a.status, "department": a.department.name if a.department_id else None,
                                      "location": a.org_unit.name if a.org_unit_id else None, "custodian": a.custodian.full_name if a.custodian_id else None,
                                      "source": f"{a.source_type}" if a.source_type else "manual"} for a in qs[:500]]})

    def post(self, request):
        ctx, d = self.authz, request.data
        e = _entity(ctx)
        a = FixedAsset.objects.create(organization=ctx.organization, entity=e, number=ledger.next_number(ctx.organization, "asset"), name=str(d.get("name", ""))[:160],
                                      category=d.get("category") or "other", acquisition_date=_d(d.get("acquisition_date"), timezone.localdate()),
                                      cost=svc.dec(d.get("cost")), salvage_value=svc.dec(d.get("salvage_value") or 0),
                                      useful_life_months=int(d.get("useful_life_months") or 36), serial_number=str(d.get("serial_number", ""))[:80])
        record(request, "finance.asset.create", category="financial", module="finance", resource=a, new={"cost": a.cost})
        return Response({"id": str(a.pk), "number": a.number}, status=status.HTTP_201_CREATED)


class AssetActionView(FinView):
    def post(self, request, pk, action):
        ctx = self.authz
        a = FixedAsset.objects.filter(pk=pk, organization=ctx.organization).first()
        if a is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        if action == "capitalise":
            svc.capitalise(request, ctx, a, credit_key=request.data.get("credit_key") or ("asset_clearing" if a.source_type else "ap"))
        elif action == "dispose":
            bank = BankAccount.objects.filter(pk=request.data.get("bank_account_id"), entity=a.entity).first() if request.data.get("bank_account_id") else None
            svc.dispose_asset(request, ctx, a, on_date=request.data.get("date") or timezone.localdate().isoformat(), proceeds=request.data.get("proceeds") or 0,
                              bank_account=bank)
        else:
            raise DomainError("Not found.", code="not_found", status_code=404)
        return Response({"status": a.status})


# --- banking & reconciliation ---------------------------------------------------------------------------------------
class BankAccountsView(FinView):
    permissions = {"GET": "finance.bank.view", "POST": "finance.bank.manage"}

    def get(self, request):
        e = _entity(self.authz)
        return Response({"results": [{"id": str(b.pk), "name": b.name, "bank": b.bank_name, "type": b.account_type, "masked": f"••••{b.last4}" if b.last4 else "not set",
                                      "ifsc": b.ifsc, "currency": b.currency, "restricted": b.is_restricted, "gl": b.gl_account.code,
                                      **svc.bank_summary(b)} for b in BankAccount.objects.filter(entity=e, is_active=True).select_related("gl_account")],
                         "position": reports.cash_position(e)})

    def post(self, request):
        ctx, d = self.authz, request.data
        e = _entity(ctx)
        gl = Account.objects.filter(entity=e, pk=d.get("gl_account_id")).first() or Account.objects.get(entity=e, system_key="bank")
        b = BankAccount.objects.create(entity=e, name=str(d.get("name", "Bank account"))[:120], bank_name=str(d.get("bank_name", ""))[:120],
                                       account_type=d.get("account_type") or "current", gl_account=gl, currency=d.get("currency") or e.base_currency)
        if d.get("account_number"):
            svc.set_bank_number(request, ctx, b, str(d["account_number"]), str(d.get("ifsc", "")))
        record(request, "finance.bank.create", category="financial", module="finance", resource=b, sensitive=True)
        return Response({"id": str(b.pk)}, status=status.HTTP_201_CREATED)


class BankAccountActionView(FinView):
    permissions = {"POST": "finance.bank.manage"}

    def post(self, request, pk, action):
        ctx = self.authz
        b = BankAccount.objects.filter(pk=pk, entity__organization=ctx.organization).first()
        if b is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        if action == "change-number":
            svc.set_bank_number(request, ctx, b, str(request.data.get("account_number", "")), str(request.data.get("ifsc", "")))
            return Response({"masked": f"••••{b.last4}"})
        if action == "reveal":
            return Response({"account_number": svc.reveal_bank_number(request, ctx, b)})
        if action == "import":
            ctx.require("finance.reconciliation.manage")
            f = request.FILES.get("file")
            if f is None:
                raise DomainError("Attach a CSV with date, description, amount, reference.", code="validation_error")
            return Response(svc.import_statement(request, ctx, b, f))
        raise DomainError("Not found.", code="not_found", status_code=404)


class BankTransactionsView(FinView):
    permissions = {"GET": "finance.reconciliation.view"}

    def get(self, request):
        qs = BankTransaction.objects.filter(bank_account__entity__organization=self.authz.organization).select_related("bank_account", "matched_payment")
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        return _page(self, qs, lambda t: {"id": str(t.pk), "bank": t.bank_account.name, "date": t.date, "description": t.description, "amount": t.amount,
                                          "reference": t.reference, "status": t.status, "matched": t.matched_payment.number if t.matched_payment_id else None,
                                          "method": t.match_method, "note": t.note})


class BankTransactionMatchView(FinView):
    permissions = {"POST": "finance.reconciliation.manage"}

    def post(self, request, pk):
        t = BankTransaction.objects.filter(pk=pk, bank_account__entity__organization=self.authz.organization).first()
        if t is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        pay = FinancePayment.objects.filter(pk=request.data.get("payment_id"), organization=self.authz.organization).first() if request.data.get("payment_id") else None
        svc.match_manually(request, self.authz, t, pay, exclude_reason=str(request.data.get("exclude_reason", "")))
        return Response({"status": t.status})


class ExceptionsView(FinView):
    permissions = {"GET": "finance.reconciliation.view", "POST": "finance.reconciliation.manage"}

    def get(self, request):
        qs = ReconciliationException.objects.filter(organization=self.authz.organization).select_related("owner", "resolved_by")
        if request.query_params.get("status", "open") != "all":
            qs = qs.filter(status=request.query_params.get("status", "open"))
        return Response({"results": [{"id": str(x.pk), "kind": x.kind, "area": x.area, "amount": x.amount, "description": x.description, "status": x.status,
                                      "source": f"{x.source_type}:{x.source_id}", "owner": x.owner.full_name if x.owner_id else None, "resolution": x.resolution,
                                      "created_at": x.created_at} for x in qs[:300]]})

    def post(self, request):  # run detectors now
        n = svc.detect_gateway_exceptions(self.authz.organization)
        return Response({"new_exceptions": n})


class ExceptionDetailView(FinView):
    permissions = {"PATCH": "finance.reconciliation.manage"}

    def patch(self, request, pk):
        x = ReconciliationException.objects.filter(pk=pk, organization=self.authz.organization).first()
        if x is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        st = request.data.get("status")
        if st not in ("resolved", "ignored") or not str(request.data.get("resolution", "")).strip():
            raise DomainError("Resolve or accept it, with a note.", code="validation_error")
        x.status, x.resolution, x.resolved_by, x.resolved_at = st, str(request.data["resolution"])[:500], request.user, timezone.now()
        x.save()
        record(request, "finance.reconciliation.exception_closed", category="financial", module="finance", resource=x, new={"status": st})
        return Response({"status": x.status})


# --- tax, reports, controls, settings -------------------------------------------------------------------------------
class TaxRulesView(FinView):
    permissions = {"GET": "finance.tax.view", "POST": "finance.tax.configure"}

    def get(self, request):
        return Response({"results": [{"id": str(r.pk), "code": r.code, "name": r.name, "kind": r.kind, "rate": r.rate, "version": r.version,
                                      "effective_from": r.effective_from, "effective_to": r.effective_to, "active": r.is_active}
                                     for r in TaxRule.objects.filter(organization=self.authz.organization)],
                         "disclaimer": "Tax rates are configuration templates. Review with a qualified tax professional before production use."})

    def post(self, request):
        """A rate change is a new version from a date; the old version ends the day before. Nothing is overwritten."""
        ctx, d = self.authz, request.data
        code = str(d.get("code", "")).strip().upper()
        eff = _d(d.get("effective_from"))
        if not code or eff is None:
            raise DomainError("Enter the code and effective date.", code="validation_error")
        prev = TaxRule.objects.filter(organization=ctx.organization, code=code).order_by("-version").first()
        if prev and eff <= prev.effective_from:
            raise DomainError("The new version must start after the current one.", code="validation_error")
        if prev:
            prev.effective_to = eff - timedelta(days=1)
            prev.save(update_fields=["effective_to", "updated_at"])
        r = TaxRule.objects.create(organization=ctx.organization, code=code, name=str(d.get("name") or (prev.name if prev else code))[:120],
                                   kind=d.get("kind") or (prev.kind if prev else "gst"), rate=svc.dec(d.get("rate")), effective_from=eff,
                                   version=(prev.version + 1) if prev else 1, output_account=prev.output_account if prev else None,
                                   input_account=prev.input_account if prev else None)
        record(request, "finance.tax_rule.changed", category="config", module="finance", resource=r, sensitive=True,
               old={"rate": prev.rate if prev else None}, new={"rate": r.rate, "from": eff})
        return Response({"id": str(r.pk), "version": r.version}, status=status.HTTP_201_CREATED)


REPORTS = {"tb": "Trial balance", "pl": "Profit & loss", "bs": "Balance sheet", "cf": "Cash flow", "tax": "Tax report", "ar": "Receivables aging",
           "ap": "Payables aging", "cash": "Cash position", "forecast": "Cash forecast", "platform": "Platform revenue (GTV vs revenue)"}


class ReportsView(FinView):
    permissions = {"GET": "finance.report.view"}

    def get(self, request):
        ctx = self.authz
        _org_wide(ctx, "finance.report.view")
        e = _entity(ctx)
        r = request.query_params.get("r", "pl")
        f, t = _range(request)
        if r == "tb":
            data = reports.trial_balance(e, t)
            rows = data["rows"]
        elif r == "pl":
            data = reports.profit_and_loss(e, f, t)
            rows = [row | {"section": s["label"]} for s in data["sections"] for row in s["rows"]]
        elif r == "bs":
            data = reports.balance_sheet(e, t)
            rows = data["assets"] + data["liabilities"] + data["equity"]
        elif r == "cf":
            data = reports.cash_flow(e, f, t)
            rows = [{k: data[k] for k in ("operating", "investing", "financing", "net_change", "opening_cash", "closing_cash")}]
        elif r == "tax":
            ctx.require("finance.tax.view")
            data = reports.tax_report(e, f, t)
            rows = data["rows"]
        elif r in ("ar", "ap"):
            data = reports.aging(ctx.organization, "receivable" if r == "ar" else "payable", t)
            rows = data["rows"]
        elif r == "cash":
            data = reports.cash_position(e)
            rows = data["accounts"]
        elif r == "forecast":
            data = reports.forecast(e, int(request.query_params.get("days") or 90))
            rows = [data]
        elif r == "platform":
            data = platform.platform_summary(ctx.organization, f, t)
            rows = [{k: v for k, v in data.items() if not isinstance(v, (list, dict))}]
        else:
            raise DomainError("Unknown report.", code="validation_error")
        if request.query_params.get("export") == "csv":
            ctx.require("finance.report.export")
            record(request, f"finance.report.export.{r}", category="export", module="finance", metadata={"from": str(f), "to": str(t), "rows": len(rows)})
            return _csv(rows, f"{r}-{t}")
        return Response({"report": r, "title": REPORTS[r], "data": data, "available": [{"key": k, "label": v} for k, v in REPORTS.items()]})


class ControlsView(FinView):
    permissions = {"GET": "finance.report.view"}

    def get(self, request):
        from apps.access.models import RoleApprovalLimit, SoDRule

        ctx = self.authz
        org = ctx.organization
        limits = [{"role": lim.role.name, "type": lim.approval_type, "max": str(lim.max_amount) if lim.max_amount is not None else "No limit"}
                  for lim in RoleApprovalLimit.objects.filter(role__organization=org, approval_type__in=["expense", "payment", "refund", "journal", "settlement",
                                                                                                           "budget", "purchase"]).select_related("role")]
        sod = [{"name": r.name, "severity": r.severity, "active": r.is_active} for r in SoDRule.objects.filter(organization=org)
               if any(c.startswith(("finance.", "payments.", "procurement.")) for c in r.first + r.second)]
        events = AuditEvent.objects.filter(organization=org, category="financial", sensitive=True).select_related("actor").order_by("-created_at")[:30] \
            if ctx.has("audit.event.view") or ctx.has("finance.report.export") else []
        e = _entity(ctx)
        return Response({
            "approval_limits": limits, "sod_rules": sod,
            "periods": [{"name": p.name, "status": p.status} for p in FinancialPeriod.objects.filter(entity=e).order_by("-start")[:6]],
            "pending_journals": Journal.objects.filter(organization=org, status="pending_approval").count(),
            "manual_journals_30d": Journal.objects.filter(organization=org, kind__in=["manual", "adjusting", "accrual"], created_at__gte=timezone.now() - timedelta(days=30)).count(),
            "unbalanced_check": reports.trial_balance(e, timezone.localdate())["balanced"],
            "bank_changes_90d": AuditEvent.objects.filter(organization=org, action="finance.bank.details_changed", created_at__gte=timezone.now() - timedelta(days=90)).count(),
            "commission_changes_90d": AuditEvent.objects.filter(organization=org, action="finance.commission.changed", created_at__gte=timezone.now() - timedelta(days=90)).count(),
            "sensitive_events": [{"action": x.action, "actor": x.actor.full_name if x.actor_id else "System", "at": x.created_at, "label": x.resource_label} for x in events],
            "principles": ["Posted journals are never edited — corrections are reversals, credit/debit notes or corrective journals.",
                           "Closed periods refuse postings; reopening needs a reason and a second approver.",
                           "Preparers can’t approve or release their own payments, settlements or journals.",
                           "Bank detail changes are encrypted, masked, audited and announced to every bank administrator."],
        })


class SettingsView(FinView):
    permissions = {"GET": "finance.settings.view"}

    def get(self, request):
        from .models import PaymentMethodConfig

        org = self.authz.organization
        return Response({"cost_centers": [{"id": str(c.pk), "code": c.code, "name": c.name, "kind": c.kind, "department": c.department.name if c.department_id else None}
                                          for c in CostCenter.objects.filter(organization=org).select_related("department")],
                         "payment_methods": [{"method": p.method, "label": p.label, "gateway": p.gateway, "fee_pct": p.fee_pct, "settlement_days": p.settlement_days}
                                             for p in PaymentMethodConfig.objects.filter(organization=org)],
                         "expense_categories": [{"id": str(c.pk), "name": c.name, "limit": c.limit_per_claim, "receipt_above": c.receipt_required_above,
                                                 "account": c.account.code} for c in ExpenseCategory.objects.filter(organization=org).select_related("account")]})


class LookupsView(FinView):
    def get(self, request):
        ctx = self.authz
        if not any(ctx.has(c) for c in ("finance.overview.view", "finance.expense.create", "procurement.request.create")):
            raise DomainError("You don’t have permission to do this.", code="permission_denied", status_code=403)
        e = _entity(ctx)
        return Response({"accounts": [{"id": str(a.pk), "code": a.code, "name": a.name, "type": a.type} for a in Account.objects.filter(entity=e, is_active=True, is_postable=True)]
                         if ctx.has("finance.ledger.view") or ctx.has("finance.invoice.create") or ctx.has("finance.bill.create") else [],
                         "cost_centers": [{"id": str(c.pk), "code": c.code, "name": c.name} for c in CostCenter.objects.filter(organization=ctx.organization, is_active=True)],
                         "tax_rules": [{"id": str(r.pk), "code": r.code, "name": r.name, "rate": r.rate} for r in TaxRule.objects.filter(organization=ctx.organization, is_active=True)
                                       .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=timezone.localdate()))],
                         "bank_accounts": [{"id": str(b.pk), "name": b.name, "masked": f"••••{b.last4}" if b.last4 else ""} for b in BankAccount.objects.filter(entity=e, is_active=True)]
                         if ctx.has("finance.payment.view") or ctx.has("finance.bank.view") else [],
                         "currency": e.base_currency, "fiscal_year": ledger.fiscal_year_of(e, timezone.localdate())})
