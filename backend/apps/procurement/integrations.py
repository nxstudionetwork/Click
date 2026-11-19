"""Procurement plugs into the shared registries: global search (PR- / PO- / RFQ- / suppliers / contracts), Business AI,
alerts and the central document store. Every provider filters in the database with the caller's scope; quotation
pricing never appears in search or AI answers for people without quotation access."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from apps.documents import access as doc_access
from apps.workspace import ai as ai_mod
from apps.workspace import alerts as alerts_mod
from apps.workspace import search as search_mod

from . import services as svc
from .models import Award, ProcurementContract, ProcurementException, PurchaseOrder, PurchaseRequest, Quotation, SourcingEvent, Supplier

ZERO = Decimal("0")


def _scoped(ctx, qs, code, owner="created_by", unit="org_unit", department="department"):
    s = ctx.scope(code)
    if s.is_empty:
        return qs.none()
    return qs if s.org_wide else qs.filter(s.q(unit=unit, department=department, owner=owner, organization=None))


# --- search ---------------------------------------------------------------------------------------------------------
def _s_requests(ctx, q, n):
    base = PurchaseRequest.objects.filter(organization=ctx.organization).filter(Q(number__iexact=q) | Q(title__icontains=q))
    qs = base.filter(requester=ctx.user) | _scoped(ctx, base, "procurement.request.view", owner="requester")
    return [{"id": str(p.pk), "title": f"{p.number} · {p.title}", "subtitle": f"{p.get_status_display()} · {p.estimated_total}",
             "path": f"/procurement/requests?open={p.pk}"} for p in qs.distinct()[:n]]


def _s_orders(ctx, q, n):
    qs = _scoped(ctx, PurchaseOrder.objects.filter(organization=ctx.organization).filter(Q(number__iexact=q) | Q(supplier__legal_name__icontains=q)),
                 "procurement.order.view").select_related("supplier")
    return [{"id": str(p.pk), "title": f"{p.number} · {p.supplier}", "subtitle": f"{p.get_status_display()} · {p.total}", "path": f"/procurement/orders?open={p.pk}"}
            for p in qs[:n]]


def _s_events(ctx, q, n):
    if ctx.scope("procurement.sourcing.view").is_empty:
        return []
    return [{"id": str(e.pk), "title": f"{e.number} · {e.title}", "subtitle": e.get_status_display(), "path": f"/procurement/sourcing?open={e.pk}"}
            for e in SourcingEvent.objects.filter(organization=ctx.organization).filter(Q(number__iexact=q) | Q(title__icontains=q))[:n]]


def _s_suppliers(ctx, q, n):
    if ctx.scope("procurement.supplier.view").is_empty:
        return []
    return [{"id": str(s.pk), "title": f"{s} ({s.code})", "subtitle": f"{s.get_status_display()} · {s.get_preference_display()}",
             "path": f"/procurement/suppliers?open={s.pk}"}
            for s in Supplier.objects.filter(organization=ctx.organization).filter(Q(legal_name__icontains=q) | Q(trading_name__icontains=q) | Q(code__iexact=q))[:n]]


def _s_contracts(ctx, q, n):
    if ctx.scope("procurement.contract.view").is_empty:
        return []
    return [{"id": str(c.pk), "title": f"{c.number} · {c.title}", "subtitle": f"{c.supplier} · ends {c.end_date:%d %b %Y}", "path": "/procurement/contracts"}
            for c in ProcurementContract.objects.filter(organization=ctx.organization).filter(Q(number__iexact=q) | Q(title__icontains=q)).select_related("supplier")[:n]]


def _s_quotes(ctx, q, n):  # quotations carry confidential pricing: only for quotation viewers
    if ctx.scope("procurement.quotation.view").is_empty:
        return []
    return [{"id": str(x.pk), "title": f"{x.number} · {x.supplier}", "subtitle": f"{x.event.number if x.event_id else ''} · {x.total}",
             "path": f"/procurement/sourcing?open={x.event_id}"}
            for x in Quotation.objects.filter(organization=ctx.organization, number__iexact=q).select_related("supplier", "event")[:n]]


for _p in (
    search_mod.Provider("purchase_request", "Purchase requests", None, _s_requests),
    search_mod.Provider("purchase_order", "Purchase orders", "procurement.order.view", _s_orders),
    search_mod.Provider("sourcing", "RFQ / RFP / RFI", "procurement.sourcing.view", _s_events),
    search_mod.Provider("supplier", "Suppliers", "procurement.supplier.view", _s_suppliers),
    search_mod.Provider("contract", "Procurement contracts", "procurement.contract.view", _s_contracts),
    search_mod.Provider("quotation", "Quotations", "procurement.quotation.view", _s_quotes),
):
    search_mod.PROVIDERS[_p.type] = _p


# --- documents (central store; Procurement decides who sees supplier and contract files) -----------------------------
@doc_access.register("procurement.supplier")
def _supplier_docs(ctx, resource_id, action, document=None):
    if not Supplier.objects.filter(pk=resource_id, organization=ctx.organization).exists():
        return False
    if action == "view":
        return ctx.has("procurement.supplier.view") and (document is None or document.sensitivity != "restricted" or ctx.has("procurement.supplier_bank.view"))
    if action in ("upload", "upload_restricted"):
        return ctx.has("procurement.supplier.edit")
    if action in ("verify", "archive"):
        return ctx.has("procurement.supplier.approve")
    return False


@doc_access.register("procurement.contract")
def _contract_docs(ctx, resource_id, action, document=None):
    if not ProcurementContract.objects.filter(pk=resource_id, organization=ctx.organization).exists():
        return False
    return ctx.has("procurement.contract.view") if action == "view" else ctx.has("procurement.contract.manage")


@doc_access.register("procurement.order")
def _order_docs(ctx, resource_id, action, document=None):
    po = PurchaseOrder.objects.filter(pk=resource_id, organization=ctx.organization).first()
    if po is None:
        return False
    if action == "view":
        return ctx.can("procurement.order.view", **({"unit": po.org_unit_id} if po.org_unit_id else {})) or ctx.has("procurement.receipt.create")
    return ctx.has("procurement.order.edit") or ctx.has("procurement.receipt.create")


# --- Business AI ----------------------------------------------------------------------------------------------------
def _ai_contracts(ctx, q):
    rows = list(svc.contracts_due(ctx.organization, 90))
    if not rows:
        return {"answer": "No procurement contracts expire in the next 90 days.", "link": "/procurement/contracts"}
    return {"answer": f"{len(rows)} contracts expire within 90 days: " + "; ".join(f"{c.number} {c.supplier} ({c.end_date:%d %b})"
                                                                                + (f" — decision: {c.renewal_decision}" if c.renewal_decision else " — no renewal decision yet")
                                                                                for c in rows[:8]) + ".", "link": "/procurement/contracts"}


def _ai_why_selected(ctx, q):
    a = Award.objects.filter(organization=ctx.organization, status="approved").select_related("supplier", "event").order_by("-created_at")
    import re

    m = re.search(r"(RFQ|RFP|AWD)-\d+", q.upper())
    if m:
        a = a.filter(Q(number=m.group(0)) | Q(event__number=m.group(0)))
    name = next((s for s in Supplier.objects.filter(organization=ctx.organization) if s.legal_name.lower() in q.lower() or (s.trading_name and s.trading_name.lower() in q.lower())), None)
    if name:
        a = a.filter(supplier=name)
    a = a.first()
    if a is None:
        return {"answer": "I couldn't find an approved award matching that. Mention the RFQ number or supplier name.", "link": "/procurement/sourcing"}
    rows = (a.evaluation or {}).get("rows", [])
    rank = next((r for r in rows if r.get("supplier_id") == str(a.supplier_id)), {})
    return {"answer": f"{a.supplier} was selected for {a.event.number} ({a.event.title}): {a.reason} Weighted score {rank.get('weighted', '—')} "
                      f"(rank {rank.get('rank', '—')} of {len(rows)}).", "link": f"/procurement/sourcing?open={a.event_id}"}


def _ai_concentration(ctx, q):
    if not ctx.scope("procurement.analytics.view").org_wide:
        return {"answer": "Supplier concentration needs organization-wide procurement analytics access.", "denied": True}
    data = svc.analytics(ctx.organization, timezone.localdate().replace(month=1, day=1), timezone.localdate())
    risky = [c for c in data["concentration"] if c["top"] and Decimal(str(c["top"][0]["share_pct"])) >= svc.policy(ctx.organization).concentration_threshold_pct]
    if not risky:
        return {"answer": "No category is concentrated above the policy threshold this year.", "link": "/procurement/analytics"}
    return {"answer": "High concentration: " + "; ".join(f"{c['category']} — {c['top'][0]['supplier']} {c['top'][0]['share_pct']}%" for c in risky[:8]) + ".",
            "link": "/procurement/analytics"}


def _ai_flags(ctx, q):
    kinds = {"below the approval threshold": "split_purchase", "split": "split_purchase", "duplicate supplier": "duplicate_supplier",
             "outside contract": "invoice_without_po", "without po": "invoice_without_po", "maverick": "invoice_without_po", "price": "price_increase",
             "emergency": "repeated_emergency"}
    kind = next((v for k, v in kinds.items() if k in q.lower()), None)
    qs = ProcurementException.objects.filter(organization=ctx.organization, status__in=["open", "pending_approval"])
    if kind:
        qs = qs.filter(kind=kind)
    rows = list(qs[:10])
    if not rows:
        return {"answer": "Nothing is flagged for that right now.", "link": "/procurement/exceptions"}
    return {"answer": "Flagged for review (not findings): " + "; ".join(f"{x.get_kind_display()} — {x.source_label}: {x.description}" for x in rows) + ".",
            "link": "/procurement/exceptions"}


def _ai_supplier(ctx, q):
    s = next((s for s in Supplier.objects.filter(organization=ctx.organization) if s.legal_name.lower() in q.lower() or (s.trading_name and s.trading_name.lower() in q.lower())
              or s.code.lower() in q.lower()), None)
    if s is None:
        return {"answer": "Which supplier? Mention its name or SUP- code.", "link": "/procurement/suppliers"}
    sc = svc.supplier_scorecard(s)
    return {"answer": f"{s} ({s.code}): {s.get_status_display()}, {s.get_preference_display()}, risk {s.risk_level}. {sc['orders']} orders worth {sc['spend']}; "
                      f"on-time {sc['on_time_pct'] or '—'}%, rejection {sc['rejection_pct'] or '—'}%, invoice match {sc['invoice_match_pct'] or '—'}%, "
                      f"overall {sc['overall'] or '—'}/100. {sc['basis']}", "link": f"/procurement/suppliers?open={s.pk}"}


def _ai_draft(ctx, q):
    return {"answer": "I can't submit or approve purchases. Start a purchase request from a template; it goes through budget check and approval.",
            "link": "/procurement/requests?new=1"}


ai_mod.EXTRA_TOOLS += [
    ai_mod.Tool("proc_contracts", "Expiring contracts", "procurement.contract.view", ("contracts expire", "contract expiring", "contracts expiring", "renewal"), _ai_contracts),
    ai_mod.Tool("proc_award", "Why a supplier was selected", "procurement.award.view", ("why was", "selected", "why did we choose", "award"), _ai_why_selected),
    ai_mod.Tool("proc_concentration", "Supplier concentration", "procurement.analytics.view", ("concentration", "over-dependent", "dependence"), _ai_concentration),
    ai_mod.Tool("proc_flags", "Procurement risk flags", "procurement.exception.view",
                ("below the approval threshold", "split purchase", "duplicate supplier", "outside contract", "maverick", "purchases without po"), _ai_flags),
    ai_mod.Tool("proc_supplier", "Supplier performance", "procurement.supplier.view", ("supplier performance", "summarize this supplier", "supplier score"), _ai_supplier),
    ai_mod.Tool("proc_draft", "Purchase request help", "procurement.request.create", ("draft purchase request", "draft a purchase", "draft rfq"), _ai_draft),
]


# --- alerts ---------------------------------------------------------------------------------------------------------
@alerts_mod.detector("procurement.overdue_pos", category="operations", source="Procurement", permission="procurement.order.view")
def _overdue_pos(org):
    qs = PurchaseOrder.objects.filter(organization=org, status__in=["approved", "sent", "confirmed", "partially_received"], expected_delivery__lt=timezone.localdate())
    n = qs.count()
    if not n:
        return []
    return [alerts_mod.Found("po", "high" if n > 5 else "medium", f"{n} purchase orders overdue", detail=f"₹{(qs.aggregate(t=Sum('total'))['t'] or 0):,.0f} not yet received.",
                             link="/procurement/orders?overdue=1", action="Chase the suppliers and update delivery dates.", metric=Decimal(n))]


@alerts_mod.detector("procurement.contracts_expiring", category="operations", source="Procurement", permission="procurement.contract.view")
def _contracts(org):
    rows = list(svc.contracts_due(org, 30))
    return [alerts_mod.Found(str(c.pk), "high" if (c.end_date - timezone.localdate()).days <= 7 else "medium", f"Contract expiring: {c.title}",
                             detail=f"{c.supplier} · ends {c.end_date:%d %b}", link="/procurement/contracts",
                             action="Review performance and spend, then renew, renegotiate, re-source or terminate.") for c in rows if not c.renewal_decision]


@alerts_mod.detector("procurement.flags", category="risk", source="Procurement", permission="procurement.exception.view")
def _flags(org):
    n = ProcurementException.objects.filter(organization=org, status="open", detected=True).count()
    if not n:
        return []
    return [alerts_mod.Found("open", "medium", f"{n} procurement patterns flagged for review", link="/procurement/exceptions",
                             action="Review each flag; they are patterns, not findings.", metric=Decimal(n), risk=True)]
