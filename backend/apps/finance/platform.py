"""
Platform finance: what a customer payment means for Click.

    Payment (apps.payments, source of truth for the money movement)
      → TransactionBreakdown (GTV → partner share, Click commission & fees, tax on fees, gateway cost, discount funding)
      → balanced Journal (partner payable is a liability, never revenue)
      → SettlementBatch (net partner payable per partner, approved, paid, reconciled)

Accounting by commercial model
- Marketplace / commission / agency: Click earns commission + fees (+ delivery fee when Click delivers); the rest is the
  partner's money held by Click (partner payable). Tax collected on goods belongs to the partner's side; tax Click charges
  on its own fees is Click's liability.
- Click-operated / Click-owned inventory: Click is the seller of record; revenue = paid − tax.
- Wallet top-ups and gift-card purchases are stored value (a liability to customers), not revenue.

Where the customer's money sits depends on how they paid (gateway clearing, cash, wallet liability, or — for
pay-at-venue — already with the partner, which reduces what Click owes them).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.audit.services import record
from apps.core.api.exceptions import DomainError
from apps.organization.commercial import click_is_principal

from . import ledger
from .ledger import Line, q2
from .models import (Account, FinancePayment, Journal, JournalLine, PartnerAdjustment, PartnerAgreement, PaymentMethodConfig, ReconciliationException,
                     SettlementBatch, SettlementLine, TransactionBreakdown)

ZERO = Decimal("0")
HUNDRED = Decimal("100")

SOURCE_ACCOUNT = {"upi": "gateway_clearing", "card": "gateway_clearing", "netbanking": "gateway_clearing", "wallet": "stored_value",
                  "gift_card": "stored_value", "cash_on_delivery": "cash", "cash": "cash", "pay_at_venue": "partner_payable"}


def pname(p) -> str:
    """Display name for a partner: business name with its Click partner ID (the ID namespace stays CLK-PT-…)."""
    if p is None:
        return ""
    return f"{p.business_name} ({p.partner_code})" if p.business_name and p.partner_code else (p.business_name or str(p))


def agreement_for(org, partner, on_date) -> PartnerAgreement | None:
    base = PartnerAgreement.objects.filter(organization=org, status=PartnerAgreement.Status.ACTIVE, effective_from__lte=on_date) \
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date)).order_by("-effective_from", "-version")
    return (base.filter(partner=partner).first() if partner else None) or base.filter(partner__isnull=True).first()


def _partner_of_order(order):
    link = getattr(order.store, "partner_link", None)
    return link.partner if link else None


def _pct(v, pct) -> Decimal:
    return q2(Decimal(v) * Decimal(pct) / HUNDRED)


def compute_sale(payment, order, agreement, method_cfg) -> dict:
    gross = q2(payment.amount)
    ratio = (Decimal(payment.amount) / Decimal(order.total)) if order.total else Decimal("1")
    ratio = min(Decimal("1"), ratio)
    scale = lambda v: q2(Decimal(v or 0) * ratio)  # noqa: E731  (split-tender payments carry their share of the order)
    merch, disc, tax, delivery = scale(order.subtotal), scale(order.discount), scale(order.tax), scale(order.delivery_fee)
    gateway_fee = q2(gross * (method_cfg.fee_pct if method_cfg else ZERO) / HUNDRED + (method_cfg.fee_fixed if method_cfg else ZERO)) \
        if SOURCE_ACCOUNT.get(payment.method) == "gateway_clearing" else ZERO
    model = agreement.commercial_model if agreement else "marketplace"
    out = {"gross": gross, "merchandise": merch, "tax_collected": tax, "delivery_fee": delivery, "gateway_fee": gateway_fee, "commercial_model": model,
           "discount_partner": ZERO, "discount_click": ZERO, "commission": ZERO, "platform_fee": ZERO, "fee_tax": ZERO, "partner_share": ZERO,
           "click_revenue": ZERO}
    if click_is_principal(model):
        out["click_revenue"] = gross - tax
        out["click_net"] = out["click_revenue"] - gateway_fee
        return out
    a = agreement
    if a.promo_funding == "click":
        dc = disc
    elif a.promo_funding == "shared":
        dc = _pct(disc, a.promo_click_share_pct)
    else:
        dc = ZERO
    dp = disc - dc
    base = merch - dp
    commission = _pct(base, a.commission_pct) + q2(a.fixed_fee * ratio)
    platform_fee = _pct(base, a.platform_fee_pct)
    fee_tax = _pct(commission + platform_fee, a.tax_on_fees_pct)
    delivery_click = delivery if a.delivery_fee_to == "click" else ZERO
    click_revenue = commission + platform_fee + delivery_click
    partner_share = gross + dc - click_revenue - fee_tax  # remainder keeps the entry balanced to the paisa
    out.update(discount_partner=dp, discount_click=dc, commission=commission, platform_fee=platform_fee, fee_tax=fee_tax,
               partner_share=partner_share, click_revenue=click_revenue, click_net=click_revenue - gateway_fee - dc)
    return out


def _sale_lines(b: TransactionBreakdown, src_key: str) -> list[Line]:
    p = {"partner": b.partner, "party_type": "partner" if b.partner_id else "", "party_id": str(b.partner_id or ""),
         "party_name": b.store_name}
    lines = [Line(src_key, debit=b.gross, description=f"Customer payment {b.method}", extra=p if src_key == "partner_payable" else {})]
    if click_is_principal(b.commercial_model):
        lines += [Line("principal_revenue", credit=b.click_revenue, description="Sale (Click is seller of record)"),
                  Line("tax_payable", credit=b.tax_collected, description="Output tax")]
    else:
        delivery_click = b.click_revenue - b.commission - b.platform_fee
        lines += [Line("partner_payable", credit=b.partner_share, description="Partner share (held for settlement)", extra=p),
                  Line("commission_revenue", credit=b.commission, description="Click commission"),
                  Line("platform_fee_revenue", credit=b.platform_fee, description="Platform fee"),
                  Line("service_fee_revenue", credit=delivery_click, description="Delivery / convenience fee"),
                  Line("tax_payable", credit=b.fee_tax, description="Tax on Click fees"),
                  Line("promotion_cost", debit=b.discount_click, description="Click-funded discount")]
    if b.gateway_fee:
        lines += [Line("payment_costs", debit=b.gateway_fee, description="Gateway charges"),
                  Line("gateway_clearing", credit=b.gateway_fee, description="Gateway charges withheld")]
    return lines


def record_sale(org, entity, payment) -> TransactionBreakdown | None:
    order = payment.order
    partner = _partner_of_order(order)
    on_date = timezone.localtime(payment.created_at).date()
    agreement = agreement_for(org, partner, on_date)
    if agreement is None:
        raise DomainError("No active partner agreement (not even a default).", code="agreement_missing", status_code=409)
    cfg = PaymentMethodConfig.objects.filter(organization=org, method=payment.method).first()
    calc = compute_sale(payment, order, agreement, cfg)
    with transaction.atomic():
        b = TransactionBreakdown.objects.create(
            organization=org, entity=entity, kind="sale", payment=payment, order=order, partner=partner, store_name=order.store.name[:160],
            agreement=agreement, agreement_snapshot=agreement.snapshot(), method=payment.method, currency=payment.currency,
            occurred_at=payment.created_at, settlement_status="na" if click_is_principal(calc["commercial_model"]) or not partner else "unsettled",
            **{k: v for k, v in calc.items()})
        j = ledger.post(entity, date=on_date, description=f"Order {order.pk.hex[:8]} · {order.store.name}"[:300], lines=_sale_lines(b, SOURCE_ACCOUNT.get(payment.method, "gateway_clearing")),
                        source=("payments", "payments.payment.sale", str(payment.pk)), reference=payment.provider_reference[:80])
        b.journal = j
        b.save(update_fields=["journal", "updated_at"])
    if partner is None and not click_is_principal(calc["commercial_model"]):
        ReconciliationException.objects.get_or_create(organization=org, kind="store_without_partner", source_type="orders.order", source_id=str(order.pk),
                                                      defaults={"area": "settlement", "amount": b.partner_share,
                                                                "description": f"{order.store.name} is not linked to a partner; its share can't be settled."})
    return b


def record_stored_value(org, entity, payment) -> TransactionBreakdown:
    what = "Wallet top-up" if payment.wallet_topup_id else "Gift card purchase"
    with transaction.atomic():
        b = TransactionBreakdown.objects.create(organization=org, entity=entity, kind="stored_value", payment=payment, commercial_model="other_approved",
                                                method=payment.method, currency=payment.currency, gross=payment.amount, occurred_at=payment.created_at,
                                                settlement_status="na", agreement_snapshot={})
        j = ledger.post(entity, date=timezone.localtime(payment.created_at).date(), description=f"{what} (customer balance, not revenue)",
                        lines=[Line(SOURCE_ACCOUNT.get(payment.method, "gateway_clearing"), debit=payment.amount),
                               Line("stored_value", credit=payment.amount)],
                        source=("payments", "payments.payment.stored_value", str(payment.pk)))
        b.journal = j
        b.save(update_fields=["journal", "updated_at"])
    return b


def record_refund(org, entity, payment) -> TransactionBreakdown | None:
    sale = TransactionBreakdown.objects.filter(payment=payment, kind__in=["sale", "stored_value"]).first()
    if sale is None:
        return None
    src = SOURCE_ACCOUNT.get(payment.method, "gateway_clearing")
    on_date = timezone.localtime(payment.updated_at).date()
    snap = sale.agreement_snapshot or {}
    resp = snap.get("refund_responsibility", "partner")
    click_pct = Decimal(snap.get("refund_click_share_pct") or 0) if resp == "shared" else (HUNDRED if resp == "click" else ZERO)
    p = {"partner": sale.partner, "party_type": "partner" if sale.partner_id else "", "party_id": str(sale.partner_id or ""), "party_name": sale.store_name}
    if sale.kind == "stored_value":
        lines = [Line("stored_value", debit=sale.gross), Line(src, credit=sale.gross)]
        partner_back = click_cost = ZERO
    elif click_is_principal(sale.commercial_model):
        lines = [Line("principal_revenue", debit=sale.click_revenue), Line("tax_payable", debit=sale.tax_collected), Line(src, credit=sale.gross)]
        partner_back = click_cost = ZERO
    else:
        click_cost = _pct(sale.partner_share, click_pct)
        partner_back = sale.partner_share - click_cost  # what the partner gives back (deducted at the next settlement)
        delivery_click = sale.click_revenue - sale.commission - sale.platform_fee
        lines = [Line("partner_payable", debit=partner_back, description="Refund recovered from partner", extra=p),
                 Line("refund_cost", debit=click_cost, description="Refund cost borne by Click"),
                 Line("commission_revenue", debit=sale.commission), Line("platform_fee_revenue", debit=sale.platform_fee),
                 Line("service_fee_revenue", debit=delivery_click), Line("tax_payable", debit=sale.fee_tax),
                 Line("promotion_cost", credit=sale.discount_click), Line(src, credit=sale.gross, description="Refund to customer")]
    with transaction.atomic():
        b = TransactionBreakdown.objects.create(
            organization=org, entity=entity, kind="refund", payment=payment, order=sale.order, partner=sale.partner, store_name=sale.store_name,
            commercial_model=sale.commercial_model, agreement=sale.agreement, agreement_snapshot=snap, method=sale.method, currency=sale.currency,
            gross=-sale.gross, merchandise=-sale.merchandise, discount_partner=-sale.discount_partner, discount_click=-sale.discount_click,
            tax_collected=-sale.tax_collected, delivery_fee=-sale.delivery_fee, commission=-sale.commission, platform_fee=-sale.platform_fee,
            fee_tax=-sale.fee_tax, partner_share=-partner_back, click_revenue=-sale.click_revenue,
            click_net=-(sale.click_revenue) - click_cost + sale.discount_click, occurred_at=payment.updated_at,
            settlement_status="unsettled" if partner_back and sale.partner_id else "na")
        j = ledger.post(entity, date=on_date, description=f"Refund · {sale.store_name or 'stored value'} ({resp} responsibility)"[:300], lines=lines,
                        source=("payments", "payments.payment.refund", str(payment.pk)))
        b.journal = j
        b.save(update_fields=["journal", "updated_at"])
    return b


def sync(org, *, limit: int = 5000) -> dict:
    """Idempotent: bring every captured / refunded platform payment into Finance. Safe to run repeatedly (job + on demand)."""
    from apps.payments.models import Payment

    entity = ledger.default_entity(org)
    out = {"sales": 0, "stored_value": 0, "refunds": 0, "unclassified": 0, "errors": 0}
    done_sale = set(TransactionBreakdown.objects.filter(organization=org, kind__in=["sale", "stored_value"]).values_list("payment_id", flat=True))
    done_ref = set(TransactionBreakdown.objects.filter(organization=org, kind="refund").values_list("payment_id", flat=True))
    qs = Payment.objects.filter(status__in=[Payment.Status.CAPTURED, Payment.Status.REFUNDED]).select_related(
        "order__store__partner_link__partner").order_by("created_at")
    for pay in qs[:limit]:
        try:
            if pay.pk not in done_sale:
                if pay.order_id:
                    record_sale(org, entity, pay)
                    out["sales"] += 1
                elif pay.wallet_topup_id or pay.gift_card_id:
                    record_stored_value(org, entity, pay)
                    out["stored_value"] += 1
                else:
                    out["unclassified"] += 1
                    continue
            if pay.status == Payment.Status.REFUNDED and pay.pk not in done_ref:
                if record_refund(org, entity, pay):
                    out["refunds"] += 1
        except DomainError as e:
            out["errors"] += 1
            ReconciliationException.objects.get_or_create(organization=org, kind="posting_failed", source_type="payments.payment", source_id=str(pay.pk),
                                                          defaults={"area": "ledger", "amount": pay.amount, "description": str(e.detail)[:300]})
    return out


def unclassified_payments(org) -> dict:
    from apps.payments.models import Payment, PAYMENT_TARGETS

    qs = Payment.objects.filter(status=Payment.Status.CAPTURED, order__isnull=True, wallet_topup__isnull=True, gift_card__isnull=True)
    by = {}
    for t in PAYMENT_TARGETS:
        if t in ("order", "wallet_topup", "gift_card"):
            continue
        agg = qs.filter(**{f"{t}__isnull": False}).aggregate(n=Sum("amount"))
        if agg["n"]:
            by[t] = agg["n"]
    return {"total": sum(by.values(), ZERO), "by_service": by,
            "note": "Captured payments for services not yet linked to a partner agreement (rides, bookings, …). Counted in GTV, "
                    "kept out of revenue until their commercial model is configured."}


# --------------------------------------------------------------------------------------------------------------------
# Settlements
# --------------------------------------------------------------------------------------------------------------------
def create_batch(request, ctx, period_to) -> SettlementBatch:
    org = ctx.organization
    entity = ledger.default_entity(org)
    rows = TransactionBreakdown.objects.filter(organization=org, partner__isnull=False, settlement_status="unsettled",
                                               occurred_at__date__lte=period_to).select_related("partner")
    adjustments = PartnerAdjustment.objects.filter(organization=org, settlement_line__isnull=True, created_at__date__lte=period_to)
    by_partner = defaultdict(lambda: {"rows": [], "adj": []})
    for b in rows:
        by_partner[b.partner_id]["rows"].append(b)
    for a in adjustments:
        by_partner[a.partner_id]["adj"].append(a)
    if not by_partner:
        raise DomainError("Nothing to settle up to this date.", code="nothing_to_settle", status_code=409)
    with transaction.atomic():
        batch = SettlementBatch.objects.create(organization=org, entity=entity, number=ledger.next_number(org, "settlement"), period_to=period_to,
                                               created_by=ctx.user)
        totals = defaultdict(lambda: ZERO)
        n = 0
        for pid, d in by_partner.items():
            sales = [b for b in d["rows"] if b.kind == "sale"]
            refunds = [b for b in d["rows"] if b.kind == "refund"]
            share = sum((b.partner_share for b in d["rows"]), ZERO)
            adj = sum((a.amount for a in d["adj"]), ZERO)
            net = share + adj
            if net <= 0:  # nothing payable yet: carried forward (refunds exceeding sales are recovered from future sales)
                continue
            partner = (d["rows"] or d["adj"])[0].partner
            line = SettlementLine.objects.create(
                batch=batch, partner=partner, transactions=len(d["rows"]), gross=sum((b.gross for b in sales), ZERO),
                commission=sum((b.commission for b in sales), ZERO) + sum((b.commission for b in refunds), ZERO),
                platform_fee=sum((b.platform_fee for b in d["rows"]), ZERO), fee_tax=sum((b.fee_tax for b in d["rows"]), ZERO),
                refunds=sum((b.partner_share for b in refunds), ZERO), adjustments=adj, partner_share=share, net_payable=net)
            TransactionBreakdown.objects.filter(pk__in=[b.pk for b in d["rows"]]).update(settlement_status="in_batch", settlement_line=line)
            PartnerAdjustment.objects.filter(pk__in=[a.pk for a in d["adj"]]).update(settlement_line=line)
            totals["gross"] += sum((b.partner_share for b in sales), ZERO)
            totals["refunds"] += line.refunds
            totals["deductions"] += min(adj, ZERO)
            totals["net"] += net
            n += 1
        if n == 0:
            raise DomainError("Every partner's balance is zero or negative up to this date (carried forward).", code="nothing_to_settle", status_code=409)
        batch.partners, batch.gross_partner_amount, batch.refund_adjustments = n, totals["gross"], totals["refunds"]
        batch.deductions, batch.net_payable = totals["deductions"], totals["net"]
        batch.save()
    record(request, "finance.settlement.created", category="financial", module="finance", resource=batch, new={"net": batch.net_payable, "partners": n})
    return batch


def submit_batch(request, ctx, batch: SettlementBatch) -> SettlementBatch:
    from apps.workflows import engine

    if batch.status != SettlementBatch.Status.CALCULATED:
        raise DomainError("Only calculated batches can be submitted.", code="invalid_state", status_code=409)
    req = engine.submit(request, "finance.settlement", title=f"Partner settlement {batch.number}", amount=batch.net_payable,
                        description=f"{batch.partners} partners up to {batch.period_to:%d %b %Y}", resource_type="finance.settlement",
                        resource_id=str(batch.pk), blocking=True)
    batch.status, batch.approval = SettlementBatch.Status.PENDING, req
    batch.save(update_fields=["status", "approval", "updated_at"])
    return batch


def pay_batch(request, ctx, batch: SettlementBatch, bank_account, reference: str = "") -> SettlementBatch:
    """Executes an approved batch: one outgoing payment per partner, posted Dr partner payable / Cr bank."""
    ctx.require("finance.payment.execute")
    if batch.status != SettlementBatch.Status.APPROVED:
        raise DomainError("The batch must be approved before paying.", code="invalid_state", status_code=409)
    if batch.created_by_id == ctx.user.pk:
        raise DomainError("Segregation of duties: the person who prepared the batch can’t also release the money.", code="sod_blocked",
                          status_code=403)
    today = timezone.localdate()
    with transaction.atomic():
        for line in batch.lines.select_related("partner"):
            pay = FinancePayment.objects.create(
                organization=batch.organization, entity=batch.entity, number=ledger.next_number(batch.organization, "payment_out"), direction="out",
                purpose="settlement", settlement_line=line, party_name=pname(line.partner)[:160],
                partner=line.partner, amount=line.net_payable, date=today, bank_account=bank_account, reference=reference[:80], status="paid",
                created_by=batch.created_by, executed_by=ctx.user, approval=batch.approval)
            j = ledger.post(batch.entity, user=ctx.user, request=request, date=today, description=f"Settlement {batch.number} · {pay.party_name}"[:300],
                            lines=[Line("partner_payable", debit=line.net_payable, extra={"partner": line.partner, "party_type": "partner",
                                                                                          "party_id": str(line.partner_id), "party_name": pay.party_name}),
                                   Line(bank_account.gl_account, credit=line.net_payable)],
                            source=("finance", "finance.payment", str(pay.pk)), reference=batch.number)
            pay.journal = j
            pay.save(update_fields=["journal", "updated_at"])
            line.payment, line.status = pay, "paid"
            line.save(update_fields=["payment", "status", "updated_at"])
            TransactionBreakdown.objects.filter(settlement_line=line).update(settlement_status="settled")
        batch.status, batch.paid_at = SettlementBatch.Status.PAID, timezone.now()
        batch.save(update_fields=["status", "paid_at", "updated_at"])
    record(request, "finance.settlement.paid", category="financial", module="finance", resource=batch, sensitive=True, new={"net": batch.net_payable})
    return batch


def release_batch(batch: SettlementBatch):
    """Rejected / cancelled batch: transactions go back to the pool for the next batch."""
    TransactionBreakdown.objects.filter(settlement_line__batch=batch).update(settlement_status="unsettled", settlement_line=None)
    PartnerAdjustment.objects.filter(settlement_line__batch=batch).update(settlement_line=None)


def add_adjustment(request, ctx, partner, kind: str, amount, reason: str) -> PartnerAdjustment:
    if not reason.strip():
        raise DomainError("Give a reason.", code="reason_required")
    amount = q2(amount)
    if amount == 0:
        raise DomainError("Enter a non-zero amount.", code="validation_error")
    entity = ledger.default_entity(ctx.organization)
    p = {"partner": partner, "party_type": "partner", "party_id": str(partner.pk), "party_name": pname(partner)[:160]}
    with transaction.atomic():
        adj = PartnerAdjustment.objects.create(organization=ctx.organization, partner=partner, kind=kind, amount=amount, reason=reason[:300],
                                               created_by=ctx.user)
        if amount > 0:  # Click owes the partner more (incentive / correction in their favour)
            lines = [Line("marketing" if kind == "incentive" else "general_expense", debit=amount), Line("partner_payable", credit=amount, extra=p)]
        else:  # deduction: penalties / advertising are Click income
            key = "advertising_revenue" if kind == "advertising" else "other_revenue"
            lines = [Line("partner_payable", debit=-amount, extra=p), Line(key, credit=-amount)]
        adj.journal = ledger.post(entity, user=ctx.user, request=request, date=timezone.localdate(), description=f"Partner {kind}: {reason}"[:300],
                                  lines=lines, source=("finance", "finance.partner_adjustment", str(adj.pk)))
        adj.save(update_fields=["journal", "updated_at"])
    record(request, "finance.partner_adjustment", category="financial", module="finance", resource=adj, new={"amount": amount, "kind": kind})
    return adj


def statement(org, partner, start, end) -> dict:
    entity = ledger.default_entity(org)
    pp = Account.objects.filter(entity=entity, system_key="partner_payable").first()
    lines = JournalLine.objects.filter(account=pp, partner=partner, journal__status__in=["posted", "reversed"])

    def bal(qs):
        a = qs.aggregate(d=Sum("debit"), c=Sum("credit"))
        return (a["c"] or ZERO) - (a["d"] or ZERO)

    opening = bal(lines.filter(journal__date__lt=start))
    closing = bal(lines.filter(journal__date__lte=end))
    bds = TransactionBreakdown.objects.filter(organization=org, partner=partner, occurred_at__date__gte=start, occurred_at__date__lte=end)
    sales, refunds = bds.filter(kind="sale"), bds.filter(kind="refund")
    s = lambda qs, f: qs.aggregate(x=Sum(f))["x"] or ZERO  # noqa: E731
    adj = PartnerAdjustment.objects.filter(organization=org, partner=partner, created_at__date__gte=start, created_at__date__lte=end)
    pays = FinancePayment.objects.filter(organization=org, partner=partner, direction="out", status="paid", date__gte=start, date__lte=end)
    return {
        "partner": {"id": str(partner.pk), "name": pname(partner)}, "from": start, "to": end, "currency": entity.base_currency,
        "opening_balance": opening, "sales": s(sales, "gross"), "transactions": sales.count(), "commission": s(sales, "commission"),
        "platform_fees": s(sales, "platform_fee"), "tax_on_fees": s(sales, "fee_tax"), "click_funded_discounts": s(sales, "discount_click"),
        "partner_funded_discounts": s(sales, "discount_partner"), "refunds": s(refunds, "partner_share"),
        "penalties_and_deductions": sum((a.amount for a in adj if a.amount < 0), ZERO), "credits_and_incentives": sum((a.amount for a in adj if a.amount > 0), ZERO),
        "payments": s(pays, "amount"), "closing_balance": closing,
        "detail": [{"date": b.occurred_at, "kind": b.kind, "order": str(b.order_id) if b.order_id else None, "gross": b.gross, "commission": b.commission,
                    "fees": b.platform_fee, "fee_tax": b.fee_tax, "partner_share": b.partner_share, "settlement": b.settlement_status,
                    "journal": b.journal.number if b.journal_id else None} for b in bds.select_related("journal").order_by("-occurred_at")[:300]],
        "adjustments": [{"date": a.created_at, "kind": a.kind, "amount": a.amount, "reason": a.reason} for a in adj],
        "payouts": [{"date": p.date, "number": p.number, "amount": p.amount, "reference": p.reference} for p in pays],
        "check": {"opening_plus_movements": opening + s(bds, "partner_share") + sum((a.amount for a in adj), ZERO) - s(pays, "amount"),
                  "note": "Opening + partner share + adjustments − payouts should equal the closing balance."},
    }


def platform_summary(org, start, end) -> dict:
    qs = TransactionBreakdown.objects.filter(organization=org, occurred_at__date__gte=start, occurred_at__date__lte=end)
    s = lambda q, f: q.aggregate(x=Sum(f))["x"] or ZERO  # noqa: E731
    sales, refunds, sv = qs.filter(kind="sale"), qs.filter(kind="refund"), qs.filter(kind="stored_value")
    entity = ledger.default_entity(org)
    gtv = s(sales, "gross")
    click_rev = s(qs.exclude(kind="stored_value"), "click_revenue")
    return {
        "from": start, "to": end, "currency": entity.base_currency,
        "gross_transaction_value": gtv, "transactions": sales.count(), "customer_payments_incl_stored_value": gtv + s(sv, "gross"),
        "stored_value_loaded": s(sv, "gross"), "partner_earnings": s(qs.exclude(kind="stored_value"), "partner_share"),
        "click_commission": s(qs, "commission"), "platform_fees": s(qs, "platform_fee"), "click_revenue": click_rev,
        "tax_on_fees": s(qs, "fee_tax"), "goods_tax_collected": s(qs, "tax_collected"), "payment_costs": s(qs, "gateway_fee"),
        "click_funded_discounts": s(sales, "discount_click"), "partner_funded_discounts": s(sales, "discount_partner"),
        "refunds_gross": -s(refunds, "gross"), "refund_count": refunds.count(), "click_net_revenue": s(qs, "click_net"),
        "settlement_liability": ledger.key_balance(entity, "partner_payable"),
        "unclassified": unclassified_payments(org),
        "by_model": [{"model": r["commercial_model"], "gtv": r["g"], "revenue": r["r"]} for r in
                     sales.values("commercial_model").annotate(g=Sum("gross"), r=Sum("click_revenue")).order_by("-g")],
        "note": "Gross transaction value is what customers paid through Click. It is not Click revenue.",
    }


def unit_economics(org, start, end) -> dict:
    p = platform_summary(org, start, end)
    n = p["transactions"] or 0
    merch = TransactionBreakdown.objects.filter(organization=org, kind="sale", occurred_at__date__gte=start, occurred_at__date__lte=end) \
        .aggregate(x=Sum("merchandise"))["x"] or ZERO

    def ratio(a, b, pct=False):
        if not b:
            return None
        v = Decimal(a) / Decimal(b) * (HUNDRED if pct else 1)
        return q2(v)

    return {
        "transactions": n, "average_order_value": ratio(p["gross_transaction_value"], n), "revenue_per_transaction": ratio(p["click_revenue"], n),
        "net_revenue_per_transaction": ratio(p["click_net_revenue"], n), "take_rate_pct": ratio(p["click_revenue"], p["gross_transaction_value"], True),
        "effective_commission_pct": ratio(p["click_commission"], merch, True), "payment_cost_pct": ratio(p["payment_costs"], p["gross_transaction_value"], True),
        "refund_rate_pct": ratio(p["refund_count"], n, True), "partner_earnings": p["partner_earnings"], "click_earnings": p["click_net_revenue"],
        "unavailable": ["Customer acquisition cost", "Partner acquisition cost", "Repeat rate", "Cost per delivery"],
        "unavailable_note": "Shown only when a reliable source exists (marketing spend attribution and delivery costs aren't recorded yet).",
    }
