"""
Double-entry posting engine. The only way anything reaches the general ledger.

    post(entity, date, lines=[(system_key | Account, debit, credit, extra), …], …)   → posted, numbered, immutable Journal
    reverse(journal, reason)                                                       → mirror journal; original marked reversed

Guarantees: balanced (to the paisa), ≥ 2 lines, postable active accounts of the same entity, open period (soft-closed
periods accept adjusting entries only), idempotent for system postings (same source posts once), audited.
A missing account mapping raises instead of silently posting to a wrong account.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as Date
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.audit.services import record
from apps.core.api.exceptions import DomainError

from .models import Account, FinancialEntity, FinancialPeriod, Journal, JournalLine, NumberSeries

CENT = Decimal("0.01")
ZERO = Decimal("0")


def q2(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


# --- numbering ------------------------------------------------------------------------------------------------------
SERIES = {
    "journal": "JV-", "invoice": "INV-", "bill": "BILL-", "credit_note": "CN-", "debit_note": "DN-", "payment_out": "PAY-", "payment_in": "RCPT-",
    "settlement": "STL-", "expense": "EXP-", "budget": "BUD-", "asset": "FA-", "dispute": "DSP-", "agreement": "AGR-", "payment_run": "PRUN-",
    # Procurement uses the same controlled series
    "pr": "PR-", "po": "PO-", "rfq": "RFQ-", "rfp": "RFP-", "rfi": "RFI-", "quote": "QT-", "grn": "GRN-", "srn": "SRN-", "contract": "CT-",
    "supplier": "SUP-", "award": "AWD-", "pexc": "PEX-", "recurring": "RP-",
}


def next_number(organization, key: str) -> str:
    """Gap-free per organization: the row is locked while the number is taken, inside the caller's transaction."""
    prefix = SERIES.get(key, key.upper()[:6] + "-")
    with transaction.atomic():
        s = NumberSeries.objects.select_for_update().filter(organization=organization, key=key).first()
        if s is None:
            try:
                with transaction.atomic():
                    NumberSeries.objects.create(organization=organization, key=key, prefix=prefix)
            except IntegrityError:
                pass
            s = NumberSeries.objects.select_for_update().get(organization=organization, key=key)
        n = s.next_value
        s.next_value = n + 1
        s.save(update_fields=["next_value", "updated_at"])
    return f"{s.prefix}{n:0{s.padding}d}"


# --- entity / period / accounts -------------------------------------------------------------------------------------
def default_entity(organization) -> FinancialEntity:
    e = FinancialEntity.objects.filter(organization=organization, is_default=True, is_active=True).first() or \
        FinancialEntity.objects.filter(organization=organization, is_active=True).first()
    if e is None:
        raise DomainError("Finance isn’t set up for this organization yet (no financial entity).", code="finance_not_configured", status_code=409)
    return e


def fiscal_year_of(entity: FinancialEntity, d: Date) -> int:
    return d.year if d.month >= entity.fiscal_year_start_month else d.year - 1


def period_for(entity: FinancialEntity, d: Date, *, create: bool = True) -> FinancialPeriod:
    p = FinancialPeriod.objects.filter(entity=entity, start__lte=d, end__gte=d).first()
    if p is None and create:
        import calendar

        start = d.replace(day=1)
        end = d.replace(day=calendar.monthrange(d.year, d.month)[1])
        p, _ = FinancialPeriod.objects.get_or_create(entity=entity, start=start, defaults={"end": end, "name": start.strftime("%Y-%m")})
    if p is None:
        raise DomainError("No financial period covers this date.", code="period_missing", status_code=409)
    return p


def account(entity: FinancialEntity, key) -> Account:
    if isinstance(key, Account):
        acc = key
    else:
        acc = Account.objects.filter(entity=entity, system_key=key, is_active=True).first() or \
              Account.objects.filter(entity=entity, code=str(key), is_active=True).first()
    if acc is None:
        raise DomainError(f"Missing account mapping “{key}”. Set it up in Finance settings → Chart of accounts before posting.",
                          code="missing_account_mapping", status_code=409)
    if acc.entity_id != entity.pk or not acc.is_postable or not acc.is_active:
        raise DomainError(f"Account {acc} can’t take postings.", code="account_not_postable", status_code=409)
    return acc


@dataclass
class Line:
    account: object
    debit: Decimal = ZERO
    credit: Decimal = ZERO
    description: str = ""
    extra: dict = field(default_factory=dict)


def _check_period(p: FinancialPeriod, kind: str):
    if p.status in (FinancialPeriod.Status.CLOSED, FinancialPeriod.Status.LOCKED):
        raise DomainError(f"Period {p.name} is {p.get_status_display().lower()}. Post in an open period or ask for it to be reopened.",
                          code="period_closed", status_code=409)
    if p.status == FinancialPeriod.Status.SOFT_CLOSED and kind not in (Journal.Kind.ADJUSTING, Journal.Kind.ACCRUAL, Journal.Kind.CLOSING,
                                                                       Journal.Kind.REVERSAL):
        raise DomainError(f"Period {p.name} is soft-closed: only adjusting entries are accepted.", code="period_closed", status_code=409)


def build(entity: FinancialEntity, *, date: Date, description: str, lines: list[Line], kind: str = Journal.Kind.SYSTEM, user=None,
          source=("", "", ""), reference: str = "", currency: str | None = None, fx_rate=Decimal("1"), org_unit=None, department=None,
          status: str = Journal.Status.DRAFT) -> Journal:
    """Validate and save a journal with its lines (not posted unless status=posted via `post`)."""
    period = period_for(entity, date)
    _check_period(period, kind)
    clean = []
    for ln in lines:
        d, c = q2(ln.debit), q2(ln.credit)
        if d < 0 or c < 0:  # a negative amount on one side is the same as a positive amount on the other
            d, c = (c.copy_abs(), ZERO) if c < 0 else (ZERO, d.copy_abs())
        if d == 0 and c == 0:
            continue
        clean.append((account(entity, ln.account), d, c, ln))
    if len(clean) < 2:
        raise DomainError("A journal needs at least two non-zero lines.", code="journal_invalid")
    td, tc = sum(x[1] for x in clean), sum(x[2] for x in clean)
    if td != tc:
        raise DomainError(f"Debits ({td}) and credits ({tc}) don’t balance.", code="journal_unbalanced", details={"difference": str(td - tc)})
    cur = currency or entity.base_currency
    rate = Decimal(str(fx_rate or 1))
    with transaction.atomic():
        j = Journal.objects.create(organization=entity.organization, entity=entity, date=date, period=period, kind=kind, status=status,
                                   description=description[:300], reference=reference[:80], source_module=source[0], source_type=source[1],
                                   source_id=str(source[2] or ""), currency=cur, fx_rate=rate, total=td, created_by=user, org_unit=org_unit,
                                   department=department)
        JournalLine.objects.bulk_create([JournalLine(
            journal=j, account=acc, debit=d, credit=c, currency=cur, amount_txn=((d - c) / rate).quantize(CENT) if rate != 1 else d - c,
            description=(ln.description or description)[:300], cost_center=ln.extra.get("cost_center"), org_unit=ln.extra.get("org_unit", org_unit),
            department=ln.extra.get("department", department), partner=ln.extra.get("partner"), party_type=ln.extra.get("party_type", ""),
            party_id=str(ln.extra.get("party_id", "")), party_name=ln.extra.get("party_name", "")[:160], tax_rule=ln.extra.get("tax_rule"))
            for acc, d, c, ln in clean])
    return j


def post(entity: FinancialEntity, *, request=None, user=None, **kw) -> Journal:
    """Build and post in one step (system postings, approved documents). Idempotent per (source, kind)."""
    src = kw.get("source", ("", "", ""))
    kind = kw.get("kind", Journal.Kind.SYSTEM)
    if src[2] and kind in (Journal.Kind.SYSTEM, Journal.Kind.REVERSAL):
        existing = Journal.objects.filter(entity=entity, source_type=src[1], source_id=str(src[2]), kind=kind).first()
        if existing:
            return existing
    with transaction.atomic():
        j = build(entity, user=user, **kw)
        finalize(j, user=user, request=request)
    return j


def finalize(j: Journal, *, user=None, request=None) -> Journal:
    """Draft / approved journal → posted. Re-validates the period at posting time."""
    if j.status == Journal.Status.POSTED:
        return j
    if j.period:
        _check_period(FinancialPeriod.objects.get(pk=j.period_id), j.kind)
    agg = j.lines.aggregate(d=Sum("debit"), c=Sum("credit"))
    if (agg["d"] or 0) != (agg["c"] or 0):
        raise DomainError("This journal no longer balances.", code="journal_unbalanced")
    if not j.number:
        j.number = next_number(j.organization, "journal")
    j.status, j.posted_at, j.posted_by = Journal.Status.POSTED, timezone.now(), user
    j.save(update_fields=["number", "status", "posted_at", "posted_by", "updated_at"])
    record(request, "finance.journal.posted", category="financial", module="finance", resource=j, actor=user, organization=j.organization,
           resource_label=j.number, new={"total": j.total, "kind": j.kind, "source": f"{j.source_type}:{j.source_id}" if j.source_id else None})
    return j


def reverse(j: Journal, *, reason: str, user=None, request=None, on_date: Date | None = None) -> Journal:
    if j.status != Journal.Status.POSTED:
        raise DomainError("Only posted journals can be reversed.", code="invalid_state", status_code=409)
    if not reason.strip():
        raise DomainError("Give a reason for the reversal.", code="reason_required")
    d = on_date or timezone.localdate()
    lines = [Line(ln.account, debit=ln.credit, credit=ln.debit, description=f"Reversal: {ln.description}",
                  extra={"cost_center": ln.cost_center, "org_unit": ln.org_unit, "department": ln.department, "partner": ln.partner,
                         "party_type": ln.party_type, "party_id": ln.party_id, "party_name": ln.party_name})
             for ln in j.lines.select_related("account", "cost_center", "org_unit", "department", "partner")]
    with transaction.atomic():
        r = build(j.entity, date=d, description=f"Reversal of {j.number}: {reason}"[:300], lines=lines, kind=Journal.Kind.REVERSAL, user=user,
                  source=(j.source_module, j.source_type or "finance.journal", j.source_id or str(j.pk)), reference=j.number)
        r.reversal_of, r.reversal_reason = j, reason[:300]
        r.save(update_fields=["reversal_of", "reversal_reason", "updated_at"])
        finalize(r, user=user, request=request)
        j.status = Journal.Status.REVERSED
        j.save(update_fields=["status", "updated_at"])
    record(request, "finance.journal.reversed", category="financial", module="finance", resource=j, actor=user, organization=j.organization,
           new={"reversal": r.number, "reason": reason})
    return r


# --- balances -------------------------------------------------------------------------------------------------------
def balance(acc: Account, *, until: Date | None = None, since: Date | None = None, **filters) -> Decimal:
    """Natural-sign balance (debit-normal accounts positive when debit > credit)."""
    qs = JournalLine.objects.filter(account=acc, journal__status__in=[Journal.Status.POSTED, Journal.Status.REVERSED])
    if until:
        qs = qs.filter(journal__date__lte=until)
    if since:
        qs = qs.filter(journal__date__gte=since)
    if filters:
        qs = qs.filter(**filters)
    agg = qs.aggregate(d=Sum("debit"), c=Sum("credit"))
    d, c = agg["d"] or ZERO, agg["c"] or ZERO
    return d - c if acc.debit_normal else c - d


def key_balance(entity, key, **kw) -> Decimal:
    acc = Account.objects.filter(entity=entity, system_key=key).first()
    return balance(acc, **kw) if acc else ZERO
