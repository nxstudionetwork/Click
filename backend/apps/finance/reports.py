"""Financial reports straight from the posted ledger. Every figure drills down: report → account → lines → journal → source."""

from __future__ import annotations

from collections import defaultdict
from datetime import date as Date
from datetime import timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from . import ledger
from .models import Account, BankAccount, FinancePayment, Invoice, Journal, JournalLine, SettlementBatch, TaxRule

ZERO = Decimal("0")
POSTED = ["posted", "reversed"]  # a reversed journal stays in the ledger; its reversal offsets it
PL_TYPES = ["revenue", "cost_of_revenue", "expense", "other_income", "other_expense"]


def _sums(entity, *, since=None, until=None, extra: Q | None = None):
    qs = JournalLine.objects.filter(journal__entity=entity, journal__status__in=POSTED)
    if since:
        qs = qs.filter(journal__date__gte=since)
    if until:
        qs = qs.filter(journal__date__lte=until)
    if extra is not None:
        qs = qs.filter(extra)
    return {r["account"]: (r["d"] or ZERO, r["c"] or ZERO) for r in qs.values("account").annotate(d=Sum("debit"), c=Sum("credit"))}


def _natural(acc: Account, d, c):
    return d - c if acc.debit_normal else c - d


def trial_balance(entity, until: Date) -> dict:
    sums = _sums(entity, until=until)
    rows, td, tc = [], ZERO, ZERO
    for acc in Account.objects.filter(entity=entity, pk__in=sums.keys()).order_by("code"):
        d, c = sums[acc.pk]
        net = d - c
        rows.append({"account_id": str(acc.pk), "code": acc.code, "name": acc.name, "type": acc.type,
                     "debit": net if net > 0 else ZERO, "credit": -net if net < 0 else ZERO})
        td, tc = td + max(net, ZERO), tc + max(-net, ZERO)
    return {"as_of": until, "rows": rows, "total_debit": td, "total_credit": tc, "balanced": td == tc}


def profit_and_loss(entity, start: Date, end: Date) -> dict:
    sums = _sums(entity, since=start, until=end, extra=Q(account__type__in=PL_TYPES))
    groups = defaultdict(list)
    for acc in Account.objects.filter(entity=entity, pk__in=sums.keys()).order_by("code"):
        groups[acc.type].append({"account_id": str(acc.pk), "code": acc.code, "name": acc.name, "amount": _natural(acc, *sums[acc.pk])})
    tot = {t: sum((r["amount"] for r in groups[t]), ZERO) for t in PL_TYPES}
    gross_profit = tot["revenue"] - tot["cost_of_revenue"]
    operating = gross_profit - tot["expense"]
    net = operating + tot["other_income"] - tot["other_expense"]
    return {"from": start, "to": end, "sections": [{"type": t, "label": dict(Account.Type.choices)[t], "rows": groups[t], "total": tot[t]} for t in PL_TYPES],
            "revenue": tot["revenue"], "gross_profit": gross_profit, "operating_profit": operating, "net_profit": net,
            "note": "Revenue here is Click's own revenue (commission, fees, subscriptions, advertising, sales as principal) — not gross transaction value."}


def balance_sheet(entity, as_of: Date) -> dict:
    sums = _sums(entity, until=as_of)
    groups = defaultdict(list)
    for acc in Account.objects.filter(entity=entity, pk__in=sums.keys(), type__in=["asset", "liability", "equity"]).order_by("code"):
        groups[acc.type].append({"account_id": str(acc.pk), "code": acc.code, "name": acc.name, "amount": _natural(acc, *sums[acc.pk])})
    pl = profit_and_loss(entity, Date(1900, 1, 1), as_of)["net_profit"]
    assets = sum((r["amount"] for r in groups["asset"]), ZERO)
    liabilities = sum((r["amount"] for r in groups["liability"]), ZERO)
    equity = sum((r["amount"] for r in groups["equity"]), ZERO) + pl
    return {"as_of": as_of, "assets": groups["asset"], "liabilities": groups["liability"], "equity": groups["equity"], "current_earnings": pl,
            "total_assets": assets, "total_liabilities": liabilities, "total_equity": equity, "balanced": assets == liabilities + equity}


def cash_flow(entity, start: Date, end: Date) -> dict:
    """Direct method from movements on cash, bank and gateway accounts, classified by the other side of each journal."""
    cash_keys = ["cash", "bank", "gateway_clearing"]
    cash_ids = set(Account.objects.filter(entity=entity, system_key__in=cash_keys).values_list("pk", flat=True)) | \
        set(BankAccount.objects.filter(entity=entity).values_list("gl_account_id", flat=True))
    lines = JournalLine.objects.filter(journal__entity=entity, journal__status__in=POSTED, journal__date__gte=start, journal__date__lte=end,
                                       account_id__in=cash_ids).select_related("journal")
    buckets = defaultdict(lambda: ZERO)
    investing_keys = {"fixed_assets", "asset_clearing", "accumulated_depreciation"}
    financing_keys = {"share_capital", "retained_earnings"}
    lines = list(lines)
    others = defaultdict(set)  # one query for the counter-accounts of every journal involved
    for jid, key in JournalLine.objects.filter(journal_id__in={ln.journal_id for ln in lines}).exclude(account_id__in=cash_ids) \
            .values_list("journal_id", "account__system_key"):
        others[jid].add(key)
    for ln in lines:
        other = others[ln.journal_id]
        cat = "investing" if other & investing_keys else "financing" if other & financing_keys else "operating"
        buckets[cat] += ln.debit - ln.credit
    opening = sum((ledger.balance(Account.objects.get(pk=i), until=start - timedelta(days=1)) for i in cash_ids), ZERO)
    net = sum(buckets.values(), ZERO)
    return {"from": start, "to": end, "operating": buckets["operating"], "investing": buckets["investing"], "financing": buckets["financing"],
            "net_change": net, "opening_cash": opening, "closing_cash": opening + net,
            "note": "Includes payment-gateway clearing balances, which are not freely available until the gateway settles."}


def general_ledger(entity, account: Account, start: Date, end: Date) -> dict:
    opening = ledger.balance(account, until=start - timedelta(days=1))
    rows, running = [], opening
    for ln in JournalLine.objects.filter(account=account, journal__status__in=POSTED, journal__date__gte=start, journal__date__lte=end) \
            .select_related("journal", "partner").order_by("journal__date", "journal__number")[:2000]:
        running += (ln.debit - ln.credit) if account.debit_normal else (ln.credit - ln.debit)
        rows.append({"journal_id": str(ln.journal_id), "number": ln.journal.number, "date": ln.journal.date, "description": ln.description,
                     "debit": ln.debit, "credit": ln.credit, "balance": running, "party": ln.party_name or (str(ln.partner) if ln.partner_id else ""),
                     "source": f"{ln.journal.source_type}:{ln.journal.source_id}" if ln.journal.source_id else "manual"})
    return {"account": {"id": str(account.pk), "code": account.code, "name": account.name, "type": account.type}, "from": start, "to": end,
            "opening": opening, "closing": running, "rows": rows}


BUCKETS = [("current", None, 0), ("1-30", 1, 30), ("31-60", 31, 60), ("61-90", 61, 90), ("91-120", 91, 120), ("120+", 121, None)]


def aging(org, kind: str, as_of: Date | None = None) -> dict:
    as_of = as_of or timezone.localdate()
    kinds = ["customer_invoice", "partner_invoice"] if kind == "receivable" else ["vendor_bill"]
    docs = Invoice.objects.filter(organization=org, kind__in=kinds, status__in=["issued", "partially_paid", "disputed"])
    rows = []
    totals = {b[0]: ZERO for b in BUCKETS}
    for inv in docs:
        out = inv.total - inv.amount_paid
        if out <= 0:
            continue
        days = (as_of - inv.due_date).days
        bucket = next(b for b, lo, hi in BUCKETS if (lo is None and days <= 0) or (lo is not None and days >= lo and (hi is None or days <= hi)))
        totals[bucket] += out
        rows.append({"id": str(inv.pk), "number": inv.number, "party": inv.party_name, "due_date": inv.due_date, "days_overdue": max(0, days),
                     "bucket": bucket, "outstanding": out, "status": inv.status, "risk": "high" if days > 90 else "medium" if days > 30 else "low"})
    return {"kind": kind, "as_of": as_of, "buckets": [{"bucket": b, "amount": totals[b]} for b, _, _ in BUCKETS],
            "total": sum(totals.values(), ZERO), "rows": sorted(rows, key=lambda r: -r["days_overdue"])}


def tax_report(entity, start: Date, end: Date) -> dict:
    rows = []
    for r in TaxRule.objects.filter(organization=entity.organization).order_by("code", "-version"):
        q = JournalLine.objects.filter(journal__entity=entity, journal__status__in=POSTED, journal__date__gte=start, journal__date__lte=end, tax_rule=r)
        agg = q.aggregate(d=Sum("debit"), c=Sum("credit"))
        out_tax = (agg["c"] or ZERO) if r.output_account_id else ZERO
        in_tax = (agg["d"] or ZERO) if r.input_account_id else ZERO
        if out_tax or in_tax:
            rows.append({"code": r.code, "name": r.name, "rate": r.rate, "output_tax": out_tax, "input_tax": in_tax})
    platform_fee_tax = JournalLine.objects.filter(journal__entity=entity, journal__status__in=POSTED, journal__date__gte=start, journal__date__lte=end,
                                                  account__system_key="tax_payable", tax_rule__isnull=True).aggregate(c=Sum("credit"), d=Sum("debit"))
    pf = (platform_fee_tax["c"] or ZERO) - (platform_fee_tax["d"] or ZERO)
    output = sum((r["output_tax"] for r in rows), ZERO) + pf
    inp = sum((r["input_tax"] for r in rows), ZERO)
    return {"from": start, "to": end, "rows": rows, "platform_fee_tax": pf, "output_tax": output, "input_tax": inp, "net_payable": output - inp,
            "tax_payable_balance": ledger.key_balance(entity, "tax_payable", until=end),
            "disclaimer": "Prepared from the ledger to support filing. Rates and treatment must be reviewed by a qualified tax professional."}


def cash_position(entity) -> dict:
    accounts = []
    for b in BankAccount.objects.filter(entity=entity, is_active=True).select_related("gl_account"):
        accounts.append({"id": str(b.pk), "name": b.name, "bank": b.bank_name, "type": b.account_type, "last4": b.last4, "balance": ledger.balance(b.gl_account),
                         "restricted": b.is_restricted, "currency": b.currency})
    available = sum((a["balance"] for a in accounts if not a["restricted"]), ZERO)
    pending = sum((a["balance"] for a in accounts if a["restricted"]), ZERO)
    return {"accounts": accounts, "available": available, "pending_or_restricted": pending, "cash_in_hand": ledger.key_balance(entity, "cash"),
            "note": "Pending gateway balances and restricted funds are not counted as available cash."}


def forecast(entity, days: int = 90) -> dict:
    """Cash forecast from known commitments (labelled as a forecast, not fact)."""
    today = timezone.localdate()
    horizon = today + timedelta(days=days)
    org = entity.organization
    receipts = Invoice.objects.filter(organization=org, kind__in=["customer_invoice", "partner_invoice"], status__in=["issued", "partially_paid"],
                                      due_date__lte=horizon)
    bills = Invoice.objects.filter(organization=org, kind="vendor_bill", status__in=["issued", "partially_paid"], due_date__lte=horizon)
    exp_in = sum((i.total - i.amount_paid for i in receipts), ZERO)
    exp_out = sum((i.total - i.amount_paid for i in bills), ZERO)
    settle = ledger.key_balance(entity, "partner_payable")
    reimb = ledger.key_balance(entity, "employee_payable")
    tax = ledger.key_balance(entity, "tax_payable") - ledger.key_balance(entity, "input_tax")
    pos = cash_position(entity)
    projected = pos["available"] + pos["pending_or_restricted"] + exp_in - exp_out - settle - reimb - max(tax, ZERO)
    burn = monthly_burn(entity)
    return {"horizon_days": days, "starting_cash": pos["available"] + pos["pending_or_restricted"], "expected_receipts": exp_in, "vendor_payments": exp_out,
            "partner_settlements": settle, "reimbursements": reimb, "taxes": max(tax, ZERO), "projected_cash": projected,
            "average_monthly_burn": burn, "runway_months": round(float(pos["available"] / burn), 1) if burn and burn > 0 else None,
            "label": "FORECAST — based on recorded receivables, payables and liabilities. Payroll and new sales are not included.",
            "assumptions": ["Customers pay on the due date", "All approved bills are paid when due", "Partner payables are settled in full",
                            "Burn = average of the last 3 months' operating expenses and cost of revenue"]}


def monthly_burn(entity) -> Decimal:
    end = timezone.localdate()
    start = end - timedelta(days=90)
    agg = JournalLine.objects.filter(journal__entity=entity, journal__status__in=POSTED, journal__date__gte=start, journal__date__lte=end,
                                     account__type__in=["expense", "cost_of_revenue"]).aggregate(d=Sum("debit"), c=Sum("credit"))
    return ((agg["d"] or ZERO) - (agg["c"] or ZERO)) / 3


def pulse(ctx) -> dict:
    org = ctx.organization
    entity = ledger.default_entity(org)
    today = timezone.localdate()
    month = today.replace(day=1)
    from .platform import platform_summary

    plat = platform_summary(org, month, today)
    pl = profit_and_loss(entity, month, today)
    ar = aging(org, "receivable")
    ap = aging(org, "payable")
    pos = cash_position(entity) if ctx.has("finance.bank.view") or ctx.has("finance.reconciliation.view") else None
    return {
        "period": {"from": month, "to": today}, "currency": entity.base_currency,
        "metrics": [
            {"key": "cash", "label": "Cash & bank (available)", "value": pos["available"] if pos else None, "path": "/finance/cash",
             "hint": f"+ {pos['pending_or_restricted']} pending / restricted" if pos else "Needs banking access"},
            {"key": "gtv", "label": "Gross transaction value (MTD)", "value": plat["gross_transaction_value"], "path": "/finance/platform",
             "hint": "What customers paid — not Click revenue"},
            {"key": "click_revenue", "label": "Click revenue (MTD)", "value": pl["revenue"], "path": "/finance/reports?r=pl"},
            {"key": "net_revenue", "label": "Click net revenue (MTD)", "value": plat["click_net_revenue"], "path": "/finance/platform",
             "hint": "After payment costs and Click-funded discounts"},
            {"key": "expenses", "label": "Expenses (MTD)", "value": sum((s["total"] for s in pl["sections"] if s["type"] in ("expense", "cost_of_revenue")), ZERO),
             "path": "/finance/reports?r=pl"},
            {"key": "partner_payables", "label": "Partner payables", "value": plat["settlement_liability"], "path": "/finance/settlements"},
            {"key": "ar", "label": "Outstanding receivables", "value": ar["total"], "path": "/finance/receivables",
             "hint": f"{sum(b['amount'] for b in ar['buckets'][1:])} overdue"},
            {"key": "ap", "label": "Outstanding payables", "value": ap["total"], "path": "/finance/payables"},
            {"key": "tax", "label": "Taxes payable", "value": ledger.key_balance(entity, "tax_payable"), "path": "/finance/tax"},
            {"key": "stored_value", "label": "Customer wallet & gift card liability", "value": ledger.key_balance(entity, "stored_value"),
             "path": "/finance/reports?r=bs"},
            {"key": "pending_settlements", "label": "Settlements awaiting approval / payment",
             "value": SettlementBatch.objects.filter(organization=org, status__in=["pending_approval", "approved"]).count(), "path": "/finance/settlements"},
        ],
    }
