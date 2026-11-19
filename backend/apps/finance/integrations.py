"""Finance plugs into the shared Business OS registries: global search, Business AI, alerts and Home pulse. Every
provider filters in the database with the caller's scope; AI answers cite records and never invent figures."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from apps.workspace import ai as ai_mod
from apps.workspace import alerts as alerts_mod
from apps.workspace import search as search_mod

from . import ledger, platform, reports
from . import services as svc
from .models import Budget, ExpenseClaim, FinancePayment, Invoice, Journal, ReconciliationException, SettlementBatch

ZERO = Decimal("0")


def _org():
    from apps.organization.models import Organization

    return Organization.objects.filter(is_active=True).order_by("created_at").first()


# --- search ---------------------------------------------------------------------------------------------------------
def _scoped(ctx, qs, code, owner="created_by", unit="org_unit", department="department"):
    s = ctx.scope(code)
    if s.is_empty:
        return qs.none()
    return qs if s.org_wide else qs.filter(s.q(unit=unit, department=department, owner=owner, organization=None))


def _s_journals(ctx, q, n):
    qs = _scoped(ctx, Journal.objects.filter(organization=ctx.organization).filter(Q(number__iexact=q) | Q(description__icontains=q)), "finance.ledger.view")
    return [{"id": str(j.pk), "title": f"{j.number or 'Draft'} · {j.description}"[:120], "subtitle": f"{j.get_status_display()} · {j.total}",
             "path": f"/finance/journals?open={j.pk}"} for j in qs[:n]]


def _s_invoices(ctx, q, n):
    base = Invoice.objects.filter(organization=ctx.organization).filter(Q(number__iexact=q) | Q(party_name__icontains=q) | Q(supplier_invoice_number__iexact=q))
    out = []
    for kinds, code, path in ((["customer_invoice", "partner_invoice", "credit_note", "debit_note"], "finance.invoice.view", "receivables"),
                              (["vendor_bill"], "finance.bill.view", "payables")):
        for i in _scoped(ctx, base.filter(kind__in=kinds), code)[:n]:
            out.append({"id": str(i.pk), "title": f"{i.number or 'Draft'} · {i.party_name}", "subtitle": f"{i.get_kind_display()} · {i.total} · {i.get_status_display()}",
                        "path": f"/finance/{path}?open={i.pk}"})
    return out[:n]


def _s_payments(ctx, q, n):
    qs = _scoped(ctx, FinancePayment.objects.filter(organization=ctx.organization).filter(Q(number__iexact=q) | Q(party_name__icontains=q) | Q(reference__iexact=q)),
                 "finance.payment.view", unit="invoice__org_unit", department="invoice__department")
    return [{"id": str(p.pk), "title": f"{p.number} · {p.party_name}", "subtitle": f"{p.get_direction_display()} · {p.amount} · {p.get_status_display()}",
             "path": "/finance/payments"} for p in qs[:n]]


def _s_settlements(ctx, q, n):
    if not ctx.scope("finance.settlement.view").org_wide:
        return []
    return [{"id": str(b.pk), "title": b.number, "subtitle": f"{b.partners} partners · {b.net_payable} · {b.get_status_display()}",
             "path": f"/finance/settlements?open={b.pk}"} for b in SettlementBatch.objects.filter(organization=ctx.organization, number__iexact=q)[:n]]


def _s_expenses(ctx, q, n):
    base = ExpenseClaim.objects.filter(organization=ctx.organization).filter(Q(number__iexact=q) | Q(purpose__icontains=q)).select_related("claimant")
    s = ctx.scope("finance.expense.view")
    qs = base if s.org_wide else base.filter(s.q(unit="org_unit", department="department", owner="claimant", organization=None) | Q(claimant=ctx.user))
    return [{"id": str(c.pk), "title": f"{c.number} · {c.purpose}"[:120], "subtitle": f"{c.claimant.full_name} · {c.amount} · {c.get_status_display()}",
             "path": "/finance/expenses"} for c in qs[:n]]


for _p in (
    search_mod.Provider("journal", "Journals", "finance.ledger.view", _s_journals),
    search_mod.Provider("invoice", "Invoices & bills", None, _s_invoices),
    search_mod.Provider("fin_payment", "Finance payments", "finance.payment.view", _s_payments),
    search_mod.Provider("settlement", "Partner settlements", "finance.settlement.view", _s_settlements),
    search_mod.Provider("expense", "Expense claims", None, _s_expenses),
):
    search_mod.PROVIDERS[_p.type] = _p


# --- Business AI ----------------------------------------------------------------------------------------------------
def _org_wide(ctx, code):
    return ctx.scope(code).org_wide


def _ai_expenses(ctx, q):
    if not _org_wide(ctx, "finance.report.view"):
        return {"answer": "Company-wide expense analysis needs organization-wide finance report access.", "denied": True}
    e = ledger.default_entity(ctx.organization)
    today = timezone.localdate()
    this_start = today.replace(day=1)
    last_end = this_start - timedelta(days=1)
    last_start = last_end.replace(day=1)
    a = reports.profit_and_loss(e, this_start, today)
    b = reports.profit_and_loss(e, last_start, last_end)

    def by_acc(r):
        return {row["name"]: row["amount"] for s in r["sections"] if s["type"] in ("expense", "cost_of_revenue") for row in s["rows"]}

    ca, cb = by_acc(a), by_acc(b)
    moves = sorted(((k, ca.get(k, ZERO) - cb.get(k, ZERO)) for k in set(ca) | set(cb)), key=lambda x: -abs(x[1]))[:5]
    if not moves:
        return {"answer": "No expenses are posted for this month or last month yet."}
    return {"answer": "Biggest changes in expenses this month vs last month (posted ledger): " +
                      "; ".join(f"{k}: {'+' if v >= 0 else ''}{v:,.2f}" for k, v in moves) + ".", "link": "/finance/reports?r=pl"}


def _ai_budgets(ctx, q):
    rows = []
    s = ctx.scope("finance.budget.view")
    qs = Budget.objects.filter(organization=ctx.organization, status="active")
    if not s.org_wide:
        qs = qs.filter(s.q(unit="org_unit", department="department", owner="owner", organization=None))
    for b in qs:
        f = svc.budget_figures(b)
        if f["used_pct"] is not None and (f["used_pct"] >= 80 or f["forecast"] > f["budget"]):
            rows.append(f"{b.name} ({b.number}): {f['used_pct']}% used incl. commitments, forecast {f['forecast']:,.0f} vs budget {f['budget']:,.0f}")
    return {"answer": ("Budgets at risk: " + "; ".join(rows) + ". Forecasts are estimates.") if rows else "No budgets in your scope are at risk.",
            "link": "/finance/budgets"}


def _ai_receivables(ctx, q):
    if not ctx.has("finance.invoice.view"):
        return {"answer": "You don't have access to receivables.", "denied": True}
    a = reports.aging(ctx.organization, "receivable")
    over = [r for r in a["rows"] if r["days_overdue"] > 0]
    if not over:
        return {"answer": "No receivables are overdue.", "link": "/finance/receivables"}
    return {"answer": f"{len(over)} overdue invoices totalling {sum(r['outstanding'] for r in over):,.2f}: " +
                      "; ".join(f"{r['number']} {r['party']} {r['outstanding']:,.2f} ({r['days_overdue']} days)" for r in over[:6]) + ".",
            "link": "/finance/receivables?overdue=1"}


def _ai_unreconciled(ctx, q):
    if not ctx.has("finance.reconciliation.view"):
        return {"answer": "You don't have access to reconciliation.", "denied": True}
    exc = ReconciliationException.objects.filter(organization=ctx.organization, status="open")
    unp = FinancePayment.objects.filter(organization=ctx.organization, status="paid", reconciled=False).count()
    return {"answer": f"{exc.count()} open reconciliation exceptions (" + ", ".join(sorted({x.kind.replace('_', ' ') for x in exc[:50]})) +
                      f"); {unp} paid transactions not yet matched to a bank statement.", "link": "/finance/reconciliation"}


def _ai_month(ctx, q):
    if not _org_wide(ctx, "finance.report.view"):
        return {"answer": "The company finance summary needs organization-wide finance report access.", "denied": True}
    today = timezone.localdate()
    p = platform.platform_summary(ctx.organization, today.replace(day=1), today)
    pl = reports.profit_and_loss(ledger.default_entity(ctx.organization), today.replace(day=1), today)
    return {"answer": f"Month to date: gross transaction value {p['gross_transaction_value']:,.2f} (not revenue) across {p['transactions']} transactions; "
                      f"Click revenue {pl['revenue']:,.2f}; net revenue after payment costs and Click-funded discounts {p['click_net_revenue']:,.2f}; "
                      f"partner earnings {p['partner_earnings']:,.2f}; net profit {pl['net_profit']:,.2f}; settlement liability {p['settlement_liability']:,.2f}.",
            "link": "/finance"}


def _ai_forecast(ctx, q):
    if not ctx.has("finance.bank.view") or not _org_wide(ctx, "finance.report.view"):
        return {"answer": "Cash forecasts need banking and organization-wide report access.", "denied": True}
    f = reports.forecast(ledger.default_entity(ctx.organization))
    return {"answer": f"FORECAST (not confirmed): starting cash {f['starting_cash']:,.2f}; projected in {f['horizon_days']} days {f['projected_cash']:,.2f} "
                      f"after receipts {f['expected_receipts']:,.2f}, vendor payments {f['vendor_payments']:,.2f}, partner settlements {f['partner_settlements']:,.2f}"
                      + (f"; runway about {f['runway_months']} months at the recent burn." if f["runway_months"] else ".") +
                      " Assumptions: " + "; ".join(f["assumptions"]) + ".", "link": "/finance/cash"}


def _ai_draft_journal(ctx, q):
    return {"answer": "I can't post or approve journals. Prepare it under Finance → Journals; it goes to a controller for approval.",
            "link": "/finance/journals?new=1"}


ai_mod.EXTRA_TOOLS += [
    ai_mod.Tool("fin_expenses", "Expense changes", "finance.report.view", ("expenses increase", "why did expenses", "expense change", "spending increase"), _ai_expenses),
    ai_mod.Tool("fin_budgets", "Budgets at risk", "finance.budget.view", ("budget", "budgets at risk", "over budget"), _ai_budgets),
    ai_mod.Tool("fin_ar", "Overdue receivables", "finance.invoice.view", ("overdue receivable", "receivables", "who owes", "outstanding invoices"), _ai_receivables),
    ai_mod.Tool("fin_recon", "Unreconciled transactions", "finance.reconciliation.view", ("unreconciled", "reconciliation", "unmatched"), _ai_unreconciled),
    ai_mod.Tool("fin_month", "Finance summary", "finance.report.view", ("finance performance", "this month's finance", "finance summary", "profit"), _ai_month),
    ai_mod.Tool("fin_forecast", "Cash forecast", "finance.bank.view", ("cash forecast", "forecast cash", "runway", "cash position"), _ai_forecast),
    ai_mod.Tool("fin_journal", "Journal help", "finance.ledger.view", ("draft journal", "post a journal", "create journal"), _ai_draft_journal),
]


# --- alerts ---------------------------------------------------------------------------------------------------------
@alerts_mod.detector("finance.overdue_receivables", category="finance", source="Finance", permission="finance.invoice.view")
def _overdue(org):
    today = timezone.localdate()
    qs = Invoice.objects.filter(organization=org, kind__in=["customer_invoice", "partner_invoice"], status__in=["issued", "partially_paid"], due_date__lt=today - timedelta(days=30))
    n = qs.count()
    if not n:
        return []
    amt = sum((i.total - i.amount_paid for i in qs), ZERO)
    return [alerts_mod.Found("ar30", "high" if n > 5 else "medium", f"{n} invoices overdue more than 30 days", detail=f"₹{amt:,.0f} outstanding.",
                             link="/finance/receivables?overdue=1", action="Follow up with the customers or partners; consider a dispute or credit note.", metric=Decimal(n))]


@alerts_mod.detector("finance.recon_exceptions", category="finance", source="Finance", permission="finance.reconciliation.view")
def _recon(org):
    n = ReconciliationException.objects.filter(organization=org, status="open").count()
    if not n:
        return []
    return [alerts_mod.Found("open", "high" if n > 10 else "medium", f"{n} reconciliation exceptions open", link="/finance/reconciliation",
                             action="Resolve gateway, bank and settlement mismatches before the period close.", metric=Decimal(n))]


@alerts_mod.detector("finance.budget_exceeded", category="finance", source="Finance", permission="finance.budget.view")
def _budgets(org):
    out = []
    for b in Budget.objects.filter(organization=org, status="active"):
        f = svc.budget_figures(b)
        if f["available"] < 0:
            out.append(alerts_mod.Found(str(b.pk), "high", f"Budget exceeded: {b.name}", detail=f"Over by ₹{-f['available']:,.0f} including commitments.",
                                        link="/finance/budgets", action="Pause new commitments or request a budget revision."))
    return out


@alerts_mod.detector("finance.payments_waiting", category="finance", source="Finance", permission="finance.payment.execute")
def _payments_waiting(org):
    n = FinancePayment.objects.filter(organization=org, status="approved").count()
    if not n:
        return []
    return [alerts_mod.Found("approved", "medium", f"{n} approved payments waiting to be released", link="/finance/payments",
                             action="Release them from the payments page (the preparer cannot release their own).", metric=Decimal(n))]


# --- Home pulse -----------------------------------------------------------------------------------------------------
def _click_revenue(ctx, p, unit):
    from apps.workspace.pulse import _sum
    from .models import TransactionBreakdown

    out = _sum(TransactionBreakdown.objects.filter(organization=ctx.organization).exclude(kind="stored_value"), "occurred_at", p, value_field="click_revenue")
    out["note"] = "Click's own revenue from platform transactions (commission, fees). GTV is shown separately."
    return out


try:
    from apps.workspace import pulse as pulse_mod

    pulse_mod.METRICS["click_revenue"] = pulse_mod.Metric("click_revenue", "Click platform revenue", ("finance.overview.view",), _click_revenue, "money",
                                                          "/finance/platform", "Finance", description="Commission and fees Click earned — not GMV.")
except Exception:  # pragma: no cover — pulse is optional
    pass
