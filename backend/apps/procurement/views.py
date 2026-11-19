"""/api/v1/os/procurement/* — Procurement workspace. Commercial pricing, quotations, supplier banking and tax details are
field-protected; budgets show figures only to Finance budget viewers; everything is scoped by the central engine."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Q, Sum
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.response import Response

from apps.audit.services import record
from apps.core.api.exceptions import DomainError
from apps.core.api.pagination import DefaultPagination
from apps.finance.views import FinView, _csv

from . import services as svc
from .defaults import TEMPLATES
from .models import (Award, ConflictDeclaration, ContractObligation, EventSupplier, GoodsReceipt, ProcurementCategory, ProcurementContract,
                     ProcurementException, ProcurementPolicy, PurchaseOrder, PurchaseRequest, Quotation, RecurringPurchase, ServiceReceipt, SourcingEvent,
                     Supplier)

NAV = [
    ("overview", "Overview", [("home", "Procurement home", "/procurement", None), ("analytics", "Spend & analytics", "/procurement/analytics", "procurement.analytics.view")]),
    ("requests", "Requests", [("requests", "Purchase requests", "/procurement/requests", None)]),
    ("sourcing", "Sourcing", [("sourcing", "RFQ / RFP / RFI", "/procurement/sourcing", "procurement.sourcing.view")]),
    ("purchasing", "Purchasing", [("orders", "Purchase orders", "/procurement/orders", "procurement.order.view"),
                                  ("recurring", "Recurring purchases", "/procurement/recurring", "procurement.order.view")]),
    ("receiving", "Receiving", [("receiving", "Goods & service receipts", "/procurement/receiving", "procurement.receipt.view|procurement.receipt.create")]),
    ("suppliers", "Suppliers", [("suppliers", "Supplier directory", "/procurement/suppliers", "procurement.supplier.view"),
                                ("contracts", "Contracts & renewals", "/procurement/contracts", "procurement.contract.view")]),
    ("compliance", "Compliance", [("exceptions", "Exceptions & risk", "/procurement/exceptions", "procurement.exception.view"),
                                  ("conflicts", "Conflict of interest", "/procurement/conflicts", None),
                                  ("policies", "Policies & ethics", "/procurement/policies", None)]),
    ("admin", "Administration", [("settings", "Procurement settings", "/procurement/settings", "procurement.settings.view")]),
]


def _allowed(ctx, perm):
    return perm is None or any(ctx.has(p) for p in perm.split("|"))


def _page(view, qs, fn):
    pg = DefaultPagination()
    page = pg.paginate_queryset(qs, view.request, view=view)
    return pg.get_paginated_response([fn(x) for x in page])


def _scoped(ctx, qs, code, *, owner="created_by", unit="org_unit", department="department"):
    s = ctx.require(code)
    return qs if s.org_wide else qs.filter(s.q(unit=unit, department=department, owner=owner, organization=None))


def _get(qs, pk):
    obj = qs.filter(pk=pk).first()
    if obj is None:
        raise DomainError("Not found.", code="not_found", status_code=404)
    return obj


def _mask(v: str) -> str:
    return (v[:2] + "•" * max(0, len(v) - 5) + v[-3:]) if v and len(v) > 5 else ("•••" if v else "")


# --- serializers ----------------------------------------------------------------------------------------------------
def pr_row(p: PurchaseRequest):
    return {"id": str(p.pk), "number": p.number, "title": p.title, "requester": p.requester.full_name, "category": p.category.name, "type": p.request_type,
            "type_label": p.get_request_type_display(), "total": p.estimated_total, "status": p.status, "status_label": p.get_status_display(),
            "priority": p.priority, "required_by": p.required_by, "emergency": p.is_emergency, "single_source": p.single_source, "post_review": p.post_review,
            "department": p.department.name if p.department_id else None, "approval_id": str(p.approval_id) if p.approval_id else None, "created_at": p.created_at}


def po_row(po: PurchaseOrder, ctx=None):
    return {"id": str(po.pk), "number": po.number, "version": po.version, "supplier": str(po.supplier), "supplier_id": str(po.supplier_id),
            "category": po.category.name, "total": po.total, "status": po.status, "status_label": po.get_status_display(), "expected_delivery": po.expected_delivery,
            "overdue": bool(po.expected_delivery and po.expected_delivery < timezone.localdate() and po.status in ("approved", "sent", "confirmed", "partially_received")),
            "emergency": po.is_emergency, "request": po.purchase_request.number if po.purchase_request_id else None, "confirmation": po.confirmation,
            "approval_id": str(po.approval_id) if po.approval_id else None, "buyer": po.created_by.full_name if po.created_by_id else None, "created_at": po.created_at}


def supplier_row(s: Supplier, full=False):
    return {"id": str(s.pk), "code": s.code, "name": str(s), "legal_name": s.legal_name, "type": s.supplier_type, "type_label": s.get_supplier_type_display(),
            "status": s.status, "status_label": s.get_status_display(), "preference": s.preference, "risk_level": s.risk_level, "relationship": s.relationship,
            "city": s.city, "categories": [c.name for c in s.categories.all()], "tax_id": s.tax_id if full else _mask(s.tax_id),
            "bank": f"••••{s.bank_last4} {s.bank_ifsc}" if s.bank_last4 else "not set", "bank_verified": s.bank_verified}


def event_row(e: SourcingEvent):
    return {"id": str(e.pk), "number": e.number, "kind": e.kind, "title": e.title, "category": e.category.name, "status": e.status, "status_label": e.get_status_display(),
            "deadline": e.response_deadline, "invited": e.invites.count(), "responses": e.invites.filter(status="responded").count(),
            "request": e.purchase_request.number if e.purchase_request_id else None, "owner": e.owner.full_name if e.owner_id else None}


# --- overview -------------------------------------------------------------------------------------------------------
class NavView(FinView):
    def get(self, request):
        ctx = self.authz
        out = [{"key": k, "label": lbl, "items": vis} for k, lbl, items in NAV
               if (vis := [{"key": a, "label": b, "path": c} for a, b, c, perm in items if _allowed(ctx, perm)])]
        return Response({"sections": out})


class HomeView(FinView):
    def get(self, request):
        ctx = self.authz
        if not ctx.has("procurement.order.view") and not ctx.has("procurement.request.view"):
            return Response({"mode": "self", "requests": [pr_row(p) for p in PurchaseRequest.objects.filter(requester=request.user).select_related("requester", "category", "department")[:10]]})
        return Response({"mode": "procurement", **svc.home(ctx)})


class LookupsView(FinView):
    def get(self, request):
        ctx = self.authz
        ctx.require("procurement.request.create")
        org = ctx.organization
        from apps.finance.models import CostCenter, TaxRule

        return Response({
            "categories": [{"id": str(c.pk), "code": c.code, "name": c.name, "parent": c.parent.code if c.parent_id else None, "expenditure": c.expenditure,
                            "match_mode": c.match_mode, "inventory": c.is_inventory, "service": c.is_service}
                           for c in ProcurementCategory.objects.filter(organization=org, is_active=True).select_related("parent")],
            "templates": [{"key": k, "name": n, "category": c, "type": t, "expenditure": e, "hint": h, "documents": d, "sourcing": so} for k, n, c, t, e, h, d, so in TEMPLATES],
            "suppliers": [{"id": str(s.pk), "name": str(s), "code": s.code, "preference": s.preference, "status": s.status}
                          for s in Supplier.objects.filter(organization=org).exclude(status="rejected").exclude(preference="blocked").order_by("legal_name")],
            "cost_centers": [{"id": str(c.pk), "code": c.code, "name": c.name} for c in CostCenter.objects.filter(organization=org, is_active=True)],
            "tax_rules": [{"id": str(r.pk), "code": r.code, "rate": r.rate} for r in TaxRule.objects.filter(organization=org, is_active=True, effective_to__isnull=True)],
            "policy": {k: getattr(svc.policy(org), k) for k in ("rfq_required_above", "min_quotes", "emergency_max_amount", "capex_threshold")},
        })


class PoliciesView(FinView):
    """Procurement policy, ethics and code of conduct — readable by everyone; changed in settings."""

    def get(self, request):
        p = svc.policy(self.authz.organization)
        return Response({"code_of_conduct": p.code_of_conduct, "gift_policy": p.gift_policy, "anti_bribery_policy": p.anti_bribery_policy,
                         "rules": [f"Competitive quotes ({p.min_quotes}) above {p.rfq_required_above}, or a justified single-source exception.",
                                   f"Emergency purchases up to {p.emergency_max_amount}, always reviewed afterwards.",
                                   "Only active, approved suppliers receive purchase orders.",
                                   "The buyer who raises an order doesn't receive it; requesters don't approve their own requests.",
                                   f"Invoices are matched to the order (and receipt) within {p.match_tolerance_pct}% / {p.match_tolerance_amount} before payment.",
                                   "Declare any conflict of interest before evaluating or approving a supplier."]})


# --- requests -------------------------------------------------------------------------------------------------------
class RequestsView(FinView):
    def get(self, request):
        ctx = self.authz
        base = PurchaseRequest.objects.filter(organization=ctx.organization).select_related("requester", "category", "department")
        view = request.query_params.get("view", "mine")
        qs = _scoped(ctx, base, "procurement.request.view", owner="requester") if view == "all" else base.filter(requester=request.user)
        if st := request.query_params.get("status"):
            qs = qs.filter(status=st)
        if request.query_params.get("emergency") == "1":
            qs = qs.filter(is_emergency=True)
        if q := request.query_params.get("q", "").strip():
            qs = qs.filter(Q(number__iexact=q) | Q(title__icontains=q))
        if request.query_params.get("export") == "csv":
            ctx.require("procurement.request.export")
            record(request, "procurement.request.export", category="export", module="procurement")
            return _csv([pr_row(p) for p in qs[:20000]], "purchase-requests")
        resp = _page(self, qs, pr_row)
        resp.data["can_view_all"] = ctx.has("procurement.request.view")
        return resp

    def post(self, request):
        pr = svc.create_pr(request, self.authz, request.data)
        if request.data.get("submit"):
            svc.submit_pr(request, self.authz, pr, budget_override_reason=str(request.data.get("budget_override_reason", "")))
        return Response(pr_row(pr), status=status.HTTP_201_CREATED)


class RequestDetailView(FinView):
    def _pr(self, pk):
        ctx = self.authz
        pr = _get(PurchaseRequest.objects.filter(organization=ctx.organization).select_related("requester", "category", "department", "preferred_supplier", "approval"), pk)
        if pr.requester_id != ctx.user.pk and not _scoped(ctx, PurchaseRequest.objects.filter(pk=pr.pk), "procurement.request.view", owner="requester").exists():
            raise DomainError("Not found.", code="not_found", status_code=404)
        return pr

    def get(self, request, pk):
        ctx = self.authz
        pr = self._pr(pk)
        live = svc.budget_check(pr) if pr.status == "draft" else pr.budget_check
        if not ctx.has("finance.budget.view"):
            live = {k: live.get(k) for k in ("found", "status", "message")}
        from apps.finance.models import FinancePayment, Invoice

        pos = list(pr.orders.select_related("supplier", "category", "created_by", "purchase_request"))
        bills = list(Invoice.objects.filter(source_type="procurement.order", source_id__in=[str(p.pk) for p in pos])) if ctx.has("finance.bill.view") else []
        trace = {
            "approval": {"id": str(pr.approval_id), "status": pr.approval.status, "reference": pr.approval.reference} if pr.approval_id else None,
            "sourcing": [event_row(e) for e in pr.sourcing_events.select_related("category", "purchase_request", "owner")],
            "awards": [{"number": a.number, "supplier": str(a.supplier), "amount": a.amount, "reason": a.reason, "status": a.status}
                       for a in Award.objects.filter(event__purchase_request=pr).select_related("supplier")] if ctx.has("procurement.award.view") else [],
            "orders": [po_row(p) for p in pos] if ctx.has("procurement.order.view") or pr.requester_id == ctx.user.pk else [],
            "receipts": [{"number": g.number, "date": g.received_on, "status": g.status} for g in GoodsReceipt.objects.filter(order__in=pos)],
            "invoices": [{"number": i.number or "Draft", "supplier_invoice": i.supplier_invoice_number, "total": i.total, "status": i.status, "match": i.match_status} for i in bills],
            "payments": [{"number": p.number, "amount": p.amount, "status": p.status, "date": p.date} for p in FinancePayment.objects.filter(invoice__in=bills)] if bills else [],
        }
        return Response({**pr_row(pr), "justification": pr.justification, "project": pr.project, "expenditure": pr.expenditure,
                         "emergency_reason": pr.emergency_reason, "single_source_reason": pr.single_source_reason,
                         "single_source_justification": pr.single_source_justification, "post_review_note": pr.post_review_note,
                         "preferred_supplier": str(pr.preferred_supplier) if pr.preferred_supplier_id else None, "budget": live,
                         "lines": [{"id": str(ln.pk), "description": ln.description, "specification": ln.specification, "quantity": ln.quantity, "uom": ln.uom,
                                    "unit_cost": ln.estimated_unit_cost, "total": ln.line_total} for ln in pr.lines.all()],
                         "can_submit": pr.status == "draft" and pr.requester_id == ctx.user.pk, "trace": trace,
                         "can_source": pr.status in ("approved", "sourcing") and ctx.has("procurement.sourcing.create"),
                         "can_order": pr.status in ("approved", "sourcing") and ctx.has("procurement.order.create")})

    def post(self, request, pk, action=None):
        ctx, d = self.authz, request.data
        pr = self._pr(pk)
        if action == "submit":
            svc.submit_pr(request, ctx, pr, budget_override_reason=str(d.get("budget_override_reason", "")))
        elif action == "cancel":
            svc.cancel_pr(request, ctx, pr, str(d.get("reason", "")))
        elif action == "post-review":
            svc.post_review(request, ctx, pr, str(d.get("note", "")))
        else:
            raise DomainError("Not found.", code="not_found", status_code=404)
        return Response(pr_row(pr))


# --- sourcing -------------------------------------------------------------------------------------------------------
class SourcingView(FinView):
    permissions = {"GET": "procurement.sourcing.view", "POST": "procurement.sourcing.create"}

    def get(self, request):
        qs = SourcingEvent.objects.filter(organization=self.authz.organization).select_related("category", "purchase_request", "owner")
        if k := request.query_params.get("kind"):
            qs = qs.filter(kind=k)
        if st := request.query_params.get("status"):
            qs = qs.filter(status=st)
        return _page(self, qs, event_row)

    def post(self, request):
        ev = svc.create_event(request, self.authz, request.data)
        if request.data.get("supplier_ids"):
            svc.invite(request, self.authz, ev, request.data["supplier_ids"])
        return Response(event_row(ev), status=status.HTTP_201_CREATED)


class SourcingDetailView(FinView):
    permissions = {"GET": "procurement.sourcing.view"}

    def get(self, request, pk):
        ctx = self.authz
        ev = _get(SourcingEvent.objects.filter(organization=ctx.organization).select_related("category", "purchase_request", "owner"), pk)
        pricing = ctx.has("procurement.quotation.view")
        quotes = [{"id": str(q.pk), "number": q.number, "supplier": str(q.supplier), "supplier_id": str(q.supplier_id), "revision": q.revision,
                   "current": q.is_current, "status": q.status, "quote_date": q.quote_date, "valid_until": q.valid_until,
                   **({"total": q.total, "subtotal": q.subtotal, "tax": q.tax, "shipping": q.shipping, "discount": q.discount, "tco_total": q.tco_total, "tco": q.tco,
                       "delivery_days": q.delivery_days, "warranty_months": q.warranty_months, "payment_terms_days": q.payment_terms_days,
                       "lines": [{"id": str(ln.pk), "description": ln.description, "quantity": ln.quantity, "unit_price": ln.unit_price, "line_total": ln.line_total}
                                 for ln in q.lines.all()]} if pricing else {})}
                  for q in ev.quotations.select_related("supplier").order_by("supplier__legal_name", "revision")]
        my_conflicts = list(ConflictDeclaration.objects.filter(declarant=request.user).exclude(status="mitigated").values_list("supplier_id", flat=True))
        return Response({**event_row(ev), "description": ev.description, "requirements": ev.requirements, "deliverables": ev.deliverables, "timeline": ev.timeline,
                         "delivery_location": ev.delivery_location, "required_delivery": ev.required_delivery, "commercial_terms": ev.commercial_terms,
                         "contract_requirements": ev.contract_requirements, "criteria": ev.criteria,
                         "lines": [{"id": str(ln.pk), "description": ln.description, "specification": ln.specification, "quantity": ln.quantity, "uom": ln.uom}
                                   for ln in ev.lines.all()],
                         "invites": [{"supplier": str(i.supplier), "supplier_id": str(i.supplier_id), "status": i.status, "invited_at": i.invited_at,
                                      "reminded_at": i.reminded_at, "responded_at": i.responded_at} for i in ev.invites.select_related("supplier")],
                         "quotes": quotes, "comparison": svc.comparison(ev) if pricing else None,
                         "negotiations": [{"quote": n.quotation.number, "from": n.previous_total, "to": n.new_total, "note": n.note, "participants": n.participants,
                                           "by": n.by.full_name if n.by_id else None, "at": n.created_at} for n in ev.negotiations.select_related("quotation", "by")] if pricing else [],
                         "awards": [{"number": a.number, "supplier": str(a.supplier), "amount": a.amount, "reason": a.reason, "status": a.status, "savings": a.savings,
                                     "method": a.savings_method, "approval_id": str(a.approval_id) if a.approval_id else None} for a in ev.awards.select_related("supplier")],
                         "my_conflicts": [str(x) for x in my_conflicts if x]})

    def post(self, request, pk, action=None):
        ctx, d = self.authz, request.data
        ev = _get(SourcingEvent.objects.filter(organization=ctx.organization), pk)
        if action == "invite":
            n = svc.invite(request, ctx, ev, d.get("supplier_ids") or [])
            return Response({"invited": n})
        if action == "publish":
            ctx.require("procurement.sourcing.create")
            svc.publish(request, ctx, ev)
        elif action == "remind":
            ctx.require("procurement.sourcing.create")
            EventSupplier.objects.filter(event=ev, status="invited").update(reminded_at=timezone.now())
            record(request, "procurement.sourcing.reminded", category="data", module="procurement", resource=ev)
        elif action == "close":
            ctx.require("procurement.sourcing.create")
            if ev.status in ("published", "responses"):
                ev.status = "evaluation"
                ev.save(update_fields=["status", "updated_at"])
        elif action == "cancel":
            ctx.require("procurement.sourcing.manage")
            if ev.status == "awarded":
                raise DomainError("Awarded events can't be cancelled.", code="invalid_state", status_code=409)
            ev.status = "cancelled"
            ev.save(update_fields=["status", "updated_at"])
            record(request, "procurement.sourcing.cancelled", category="data", module="procurement", resource=ev, new={"reason": d.get("reason")})
        elif action == "quote":
            q = svc.record_quote(request, ctx, ev, d)
            return Response({"id": str(q.pk), "number": q.number, "total": q.total}, status=status.HTTP_201_CREATED)
        elif action == "award":
            q = _get(Quotation.objects.filter(event=ev), d.get("quotation_id"))
            a = svc.award(request, ctx, ev, q, reason=str(d.get("reason", "")), exception_reason=str(d.get("exception_reason", "")))
            return Response({"id": str(a.pk), "number": a.number, "approval_id": str(a.approval_id)}, status=status.HTTP_201_CREATED)
        else:
            raise DomainError("Not found.", code="not_found", status_code=404)
        return Response(event_row(ev))


class QuotationActionView(FinView):
    def post(self, request, pk, action):
        ctx, d = self.authz, request.data
        q = _get(Quotation.objects.filter(organization=ctx.organization).select_related("event", "supplier"), pk)
        if action == "score":
            for c, v in (d.get("scores") or {}).items():
                svc.score(request, ctx, q, c, v, str(d.get("note", "")))
            return Response({"ok": True})
        if action == "negotiate":
            new = svc.negotiate(request, ctx, q, changes=d.get("changes") or {}, note=str(d.get("note", "")), participants=str(d.get("participants", "")))
            return Response({"id": str(new.pk), "number": new.number, "total": new.total}, status=status.HTTP_201_CREATED)
        raise DomainError("Not found.", code="not_found", status_code=404)


# --- purchase orders ------------------------------------------------------------------------------------------------
class OrdersView(FinView):
    permissions = {"GET": "procurement.order.view", "POST": "procurement.order.create"}

    def get(self, request):
        ctx = self.authz
        qs = _scoped(ctx, PurchaseOrder.objects.filter(organization=ctx.organization).select_related("supplier", "category", "purchase_request", "created_by"),
                     "procurement.order.view")
        p = request.query_params
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        if p.get("overdue") == "1":
            qs = qs.filter(status__in=["approved", "sent", "confirmed", "partially_received"], expected_delivery__lt=timezone.localdate())
        if p.get("receivable") == "1":
            qs = qs.filter(status__in=["approved", "sent", "confirmed", "partially_received", "partially_invoiced"])
        if q := p.get("q", "").strip():
            qs = qs.filter(Q(number__iexact=q) | Q(supplier__legal_name__icontains=q))
        if p.get("export") == "csv":
            ctx.require("procurement.order.export")
            record(request, "procurement.order.export", category="export", module="procurement")
            return _csv([po_row(x) for x in qs[:20000]], "purchase-orders")
        return _page(self, qs, po_row)

    def post(self, request):
        po = svc.create_po(request, self.authz, request.data)
        return Response(po_row(po), status=status.HTTP_201_CREATED)


class OrderDetailView(FinView):
    permissions = {"GET": "procurement.order.view"}

    def _po(self, pk):
        ctx = self.authz
        qs = PurchaseOrder.objects.filter(organization=ctx.organization).select_related("supplier", "category", "purchase_request", "created_by", "contract", "event", "award")
        po = _get(qs, pk)
        if not _scoped(ctx, PurchaseOrder.objects.filter(pk=po.pk), "procurement.order.view").exists():
            raise DomainError("Not found.", code="not_found", status_code=404)
        return po

    def get(self, request, pk):
        ctx = self.authz
        po = self._po(pk)
        from apps.finance.models import BudgetCommitment, Invoice

        bills = Invoice.objects.filter(source_type="procurement.order", source_id=str(po.pk))
        com = BudgetCommitment.objects.filter(source_type="procurement.order", source_id=str(po.pk)).first()
        return Response({**po_row(po), "subtotal": po.subtotal, "tax": po.tax, "shipping": po.shipping, "discount": po.discount, "currency": po.currency,
                         "delivery_location": po.delivery_location, "confirmed_delivery": po.confirmed_delivery, "payment_terms_days": po.payment_terms_days,
                         "warranty": po.warranty, "terms": po.terms, "carrier": po.carrier, "tracking_number": po.tracking_number, "delivery_status": po.delivery_status,
                         "confirmation_note": po.confirmation_note, "contract": po.contract.number if po.contract_id else None, "event": po.event.number if po.event_id else None,
                         "award": po.award.number if po.award_id else None, "match_mode": po.category.match_mode, "cancel_reason": po.cancel_reason,
                         "lines": [{"id": str(ln.pk), "line_no": ln.line_no, "description": ln.description, "quantity": ln.quantity, "uom": ln.uom, "unit_price": ln.unit_price,
                                    "tax_rate": ln.tax_rate, "line_total": ln.line_total, "received": ln.received_qty, "rejected": ln.rejected_qty, "accepted": ln.accepted_qty,
                                    "invoiced": ln.invoiced_qty, "remaining": ln.remaining_qty, "service": ln.is_service, "service_accepted": ln.service_accepted_amount,
                                    "capex": ln.is_capex, "inventory": ln.is_inventory} for ln in po.lines.all()],
                         "versions": [{"version": v.version, "reason": v.reason, "by": v.by.full_name if v.by_id else None, "at": v.created_at, "snapshot": v.snapshot}
                                      for v in po.versions.select_related("by")],
                         "amendments": [{"id": str(a.pk), "reason": a.reason, "new_total": a.new_total, "status": a.status, "from_version": a.from_version,
                                         "approval_id": str(a.approval_id) if a.approval_id else None} for a in po.amendments.all()],
                         "receipts": [{"id": str(g.pk), "number": g.number, "date": g.received_on, "status": g.status, "by": g.received_by.full_name,
                                       "inventory": g.inventory_status} for g in po.receipts.select_related("received_by")],
                         "service_receipts": [{"id": str(s.pk), "number": s.number, "amount": s.amount, "status": s.status, "deliverables": s.deliverables}
                                              for s in po.service_receipts.all()],
                         "invoices": [{"id": str(i.pk), "number": i.number or "Draft", "supplier_invoice": i.supplier_invoice_number, "total": i.total, "status": i.status,
                                       "match": i.match_status, "issues": (i.match_detail or {}).get("issues", [])} for i in bills] if ctx.has("finance.bill.view") or ctx.has("procurement.order.view") else [],
                         "commitment": {"amount": com.amount, "consumed": com.consumed, "open": com.open_amount, "status": com.status} if com and ctx.has("finance.budget.view") else None,
                         "can": {"submit": po.status == "draft" and ctx.has("procurement.order.create"), "send": po.status == "approved",
                                 "receive": ctx.has("procurement.receipt.create") and po.status in ("approved", "sent", "confirmed", "partially_received", "partially_invoiced"),
                                 "invoice": ctx.has("finance.bill.create"), "amend": ctx.has("procurement.order.edit") and po.is_locked
                                 and po.status not in ("completed", "cancelled", "closed")}})

    def post(self, request, pk, action=None):
        ctx, d = self.authz, request.data
        po = self._po(pk)
        if action == "submit":
            svc.submit_po(request, ctx, po, exception_reason=str(d.get("exception_reason", "")))
        elif action == "send":
            svc.send_po(request, ctx, po)
        elif action == "confirm":
            svc.confirm_po(request, ctx, po, result=str(d.get("result", "")), note=str(d.get("note", "")), confirmed_delivery=d.get("confirmed_delivery"))
        elif action == "delivery":
            svc.update_delivery(request, ctx, po, d)
        elif action == "amend":
            am = svc.request_amendment(request, ctx, po, reason=str(d.get("reason", "")), changes=d.get("changes") or {})
            return Response({"id": str(am.pk), "approval_id": str(am.approval_id)}, status=status.HTTP_201_CREATED)
        elif action == "cancel":
            svc.cancel_po(request, ctx, po, str(d.get("reason", "")))
        elif action == "close":
            svc.close_po(request, ctx, po, str(d.get("reason", "")))
        elif action == "receive":
            g = svc.receive(request, ctx, po, d.get("lines") or [], received_on=d.get("received_on"), delivery_note=str(d.get("delivery_note", "")),
                            condition=str(d.get("condition", "")), evidence=str(d.get("evidence", "")), inspect=bool(d.get("inspect")))
            return Response({"id": str(g.pk), "number": g.number, "status": g.status}, status=status.HTTP_201_CREATED)
        elif action == "service-receipt":
            s = svc.submit_service_receipt(request, ctx, po, d)
            return Response({"id": str(s.pk), "number": s.number}, status=status.HTTP_201_CREATED)
        elif action == "invoice":
            inv = svc.record_supplier_invoice(request, ctx, po, d)
            return Response({"id": str(inv.pk), "match": inv.match_status, "issues": (inv.match_detail or {}).get("issues", [])}, status=status.HTTP_201_CREATED)
        else:
            raise DomainError("Not found.", code="not_found", status_code=404)
        po.refresh_from_db()
        return Response(po_row(po))


# --- receiving ------------------------------------------------------------------------------------------------------
class ReceiptsView(FinView):
    def get(self, request):
        ctx = self.authz
        if not (ctx.has("procurement.receipt.view") or ctx.has("procurement.receipt.create")):
            raise DomainError("You don't have permission to do this.", code="permission_denied", status_code=403)
        code = "procurement.receipt.view" if ctx.has("procurement.receipt.view") else "procurement.receipt.create"
        grns = _scoped(ctx, GoodsReceipt.objects.filter(organization=ctx.organization).select_related("order", "order__supplier", "received_by"), code,
                       owner="received_by", unit="order__org_unit", department="order__department")
        services = ServiceReceipt.objects.filter(organization=ctx.organization).select_related("order", "order__supplier", "submitted_by", "order__purchase_request")
        if not ctx.scope(code).org_wide:
            services = services.filter(Q(submitted_by=request.user) | Q(order__purchase_request__requester=request.user))
        return Response({"goods": [{"id": str(g.pk), "number": g.number, "order": g.order.number, "order_id": str(g.order_id), "supplier": str(g.order.supplier),
                                    "date": g.received_on, "status": g.status, "by": g.received_by.full_name, "inventory": g.inventory_status,
                                    "lines": [{"id": str(rl.pk), "description": rl.order_line.description, "received": rl.received_qty, "rejected": rl.rejected_qty,
                                               "damaged": rl.damaged_qty, "batch": rl.batch} for rl in g.lines.select_related("order_line")]} for g in grns[:200]],
                         "services": [{"id": str(s.pk), "number": s.number, "order": s.order.number, "supplier": str(s.order.supplier), "amount": s.amount,
                                       "deliverables": s.deliverables, "completion": s.completion_pct, "status": s.status, "by": s.submitted_by.full_name,
                                       "can_decide": s.status == "submitted" and request.user.pk not in (s.submitted_by_id, s.order.created_by_id) and
                                       (ctx.has("procurement.receipt.inspect") or (s.order.purchase_request_id and s.order.purchase_request.requester_id == request.user.pk))}
                                      for s in services[:200]],
                         "can_inspect": ctx.has("procurement.receipt.inspect")})


class ReceiptActionView(FinView):
    def post(self, request, pk, action):
        ctx, d = self.authz, request.data
        if action == "inspect":
            g = _get(GoodsReceipt.objects.filter(organization=ctx.organization), pk)
            svc.inspect(request, ctx, g, result=str(d.get("result", "")), rejections=d.get("rejections") or {}, notes=str(d.get("notes", "")),
                        corrective_action=str(d.get("corrective_action", "")), evidence=str(d.get("evidence", "")))
            return Response({"status": g.status})
        if action == "decide":
            s = _get(ServiceReceipt.objects.filter(organization=ctx.organization).select_related("order", "order__purchase_request"), pk)
            svc.decide_service_receipt(request, ctx, s, str(d.get("decision", "")), str(d.get("note", "")))
            return Response({"status": s.status})
        raise DomainError("Not found.", code="not_found", status_code=404)


# --- suppliers ------------------------------------------------------------------------------------------------------
class SuppliersView(FinView):
    permissions = {"GET": "procurement.supplier.view", "POST": "procurement.supplier.create"}

    def get(self, request):
        ctx = self.authz
        qs = Supplier.objects.filter(organization=ctx.organization).prefetch_related("categories")
        p = request.query_params
        if q := p.get("q", "").strip():
            qs = qs.filter(Q(legal_name__icontains=q) | Q(trading_name__icontains=q) | Q(code__iexact=q))
        for f in ("status", "preference", "risk_level", "relationship"):
            if p.get(f):
                qs = qs.filter(**{f: p[f]})
        if p.get("category"):
            qs = qs.filter(categories__id=p["category"])
        if p.get("issues") == "1":
            qs = qs.filter(Q(preference__in=["restricted", "blocked"]) | Q(risk_level="high"))
        if p.get("export") == "csv":
            ctx.require("procurement.supplier.export")
            record(request, "procurement.supplier.export", category="export", module="procurement")
            return _csv([supplier_row(s) for s in qs[:20000]], "suppliers")
        full = ctx.has("procurement.supplier.edit")
        return _page(self, qs.distinct(), lambda s: supplier_row(s, full))

    def post(self, request):
        s = svc.create_supplier(request, self.authz, request.data)
        return Response(supplier_row(s, True), status=status.HTTP_201_CREATED)


class SupplierDetailView(FinView):
    permissions = {"GET": "procurement.supplier.view", "PATCH": "procurement.supplier.edit"}

    def get(self, request, pk):
        ctx = self.authz
        s = _get(Supplier.objects.filter(organization=ctx.organization).prefetch_related("categories"), pk)
        full = ctx.has("procurement.supplier.edit")
        return Response({**supplier_row(s, full), "trading_name": s.trading_name, "contact_name": s.contact_name, "email": s.email, "phone": s.phone, "website": s.website,
                         "address": s.address, "state": s.state, "country": s.country, "pan": s.pan if full else _mask(s.pan),
                         "registration_number": s.registration_number, "payment_terms_days": s.payment_terms_days, "currency": s.currency,
                         "partner": str(s.partner) if s.partner_id else None, "verification": s.verification, "checks": svc.VERIFY_CHECKS,
                         "required_checks": svc.REQUIRED_CHECKS, "risk_factors": s.risk_factors, "restriction_reason": s.restriction_reason,
                         "approval_id": str(s.approval_id) if s.approval_id else None, "scorecard": svc.supplier_scorecard(s),
                         "duplicates": svc.duplicates(ctx.organization, legal_name=s.legal_name, tax_id=s.tax_id, email=s.email, phone=s.phone,
                                                      bank_last4=s.bank_last4, bank_ifsc=s.bank_ifsc, exclude=s),
                         "contracts": [{"id": str(c.pk), "number": c.number, "title": c.title, "end": c.end_date, "status": c.status} for c in s.contracts.all()],
                         "orders": [po_row(p) for p in s.orders.select_related("supplier", "category", "purchase_request", "created_by")[:20]],
                         "history": [{"field": e.field, "from": e.from_value, "to": e.to_value, "reason": e.reason_category, "note": e.note,
                                      "by": e.by.full_name if e.by_id else None, "at": e.created_at} for e in s.status_events.select_related("by")[:30]],
                         "bank_changes": [{"id": str(b.pk), "last4": b.last4, "ifsc": b.ifsc, "reason": b.reason, "status": b.status,
                                           "by": b.requested_by.full_name if b.requested_by_id else None, "at": b.created_at,
                                           "approval_id": str(b.approval_id) if b.approval_id else None} for b in s.bank_changes.select_related("requested_by")]
                         if ctx.has("procurement.supplier_bank.view") else []})

    def patch(self, request, pk):
        ctx = self.authz
        s = _get(Supplier.objects.filter(organization=ctx.organization), pk)
        before = supplier_row(s, True)
        for f in ("trading_name", "contact_name", "email", "phone", "website", "address", "city", "state", "registration_number"):
            if f in request.data:
                setattr(s, f, str(request.data[f])[:300])
        for f in ("tax_id", "pan"):
            if f in request.data and str(request.data[f]).upper() != getattr(s, f):
                setattr(s, f, str(request.data[f]).upper()[:20])
                s.verification = {k: v for k, v in (s.verification or {}).items() if k != "tax_registration"}  # changed identifiers need re-verification
        if "payment_terms_days" in request.data:
            s.payment_terms_days = int(request.data["payment_terms_days"] or 30)
        if "supplier_type" in request.data and request.data["supplier_type"] in Supplier.Type.values:
            s.supplier_type = request.data["supplier_type"]
        if "relationship" in request.data and request.data["relationship"] in Supplier.Relationship.values:
            s.relationship = request.data["relationship"]
        s.save()
        if "category_ids" in request.data:
            s.categories.set(ProcurementCategory.objects.filter(organization=ctx.organization, pk__in=request.data["category_ids"] or []))
        record(request, "procurement.supplier.updated", category="data", module="procurement", resource=s, old=before, new=supplier_row(s, True))
        return Response(supplier_row(s, True))

    def post(self, request, pk, action=None):
        ctx, d = self.authz, request.data
        s = _get(Supplier.objects.filter(organization=ctx.organization), pk)
        if action == "verify":
            svc.verify(request, ctx, s, str(d.get("check", "")), str(d.get("status", "")), str(d.get("note", "")))
        elif action == "submit":
            svc.submit_onboarding(request, ctx, s)
        elif action == "preference":
            svc.set_preference(request, ctx, s, str(d.get("preference", "")), str(d.get("reason_category", "")), str(d.get("note", "")))
        elif action == "bank-change":
            bc = svc.request_bank_change(request, ctx, s, account=str(d.get("account_number", "")), ifsc=str(d.get("ifsc", "")), reason=str(d.get("reason", "")),
                                         evidence=str(d.get("evidence", "")))
            return Response({"id": str(bc.pk), "approval_id": str(bc.approval_id)}, status=status.HTTP_201_CREATED)
        elif action == "risk":
            ctx.require("procurement.supplier.edit")
            factor = str(d.get("factor", ""))
            if factor not in ("financial", "compliance", "delivery", "quality", "cybersecurity", "concentration", "single_source", "geographic", "contract", "reputational"):
                raise DomainError("Unknown risk factor.", code="validation_error")
            s.risk_factors = {**(s.risk_factors or {}), factor: {"level": d.get("level", "medium"), "note": str(d.get("note", ""))[:300],
                                                                 "by": ctx.user.full_name, "at": timezone.now().isoformat()}}
            levels = [v.get("level") for v in s.risk_factors.values()]
            s.risk_level = "high" if "high" in levels else "medium" if "medium" in levels else "low"
            s.save(update_fields=["risk_factors", "risk_level", "updated_at"])
            record(request, "procurement.supplier.risk", category="data", module="procurement", resource=s, new={"factor": factor, "level": d.get("level")})
        else:
            raise DomainError("Not found.", code="not_found", status_code=404)
        return Response(supplier_row(s, ctx.has("procurement.supplier.edit")))


class DuplicatesView(FinView):
    permissions = {"GET": "procurement.supplier.view"}

    def get(self, request):
        p = request.query_params
        return Response({"results": svc.duplicates(self.authz.organization, legal_name=p.get("name", ""), tax_id=p.get("tax_id", ""), email=p.get("email", ""),
                                                   phone=p.get("phone", ""))})


# --- contracts, recurring, exceptions, conflicts ---------------------------------------------------------------------
class ContractsView(FinView):
    permissions = {"GET": "procurement.contract.view", "POST": "procurement.contract.manage"}

    def get(self, request):
        today = timezone.localdate()
        qs = ProcurementContract.objects.filter(organization=self.authz.organization).select_related("supplier", "owner", "category")
        return Response({"results": [{"id": str(c.pk), "number": c.number, "title": c.title, "supplier": str(c.supplier), "type": c.contract_type, "start": c.start_date,
                                      "end": c.end_date, "value": c.value, "status": c.status, "days_left": (c.end_date - today).days, "auto_renew": c.auto_renew,
                                      "notice_days": c.notice_period_days, "owner": c.owner.full_name if c.owner_id else None, "decision": c.renewal_decision,
                                      "decision_note": c.decision_note, "orders_value": c.orders.filter(status__in=svc.COMMITTED).aggregate(t=Sum("total"))["t"] or 0,
                                      "obligations": [{"id": str(o.pk), "kind": o.kind, "title": o.title, "due": o.due_on, "status": o.status}
                                                      for o in c.obligations.all()]} for c in qs[:300]]})

    def post(self, request):
        ctx, d = self.authz, request.data
        s = _get(Supplier.objects.filter(organization=ctx.organization), d.get("supplier_id"))
        start, end = parse_date(str(d.get("start_date") or "")), parse_date(str(d.get("end_date") or ""))
        if not start or not end or end < start:
            raise DomainError("Enter a valid start and end date.", code="validation_error")
        from apps.finance import ledger

        c = ProcurementContract.objects.create(organization=ctx.organization, number=ledger.next_number(ctx.organization, "contract"), supplier=s,
                                               title=str(d.get("title", ""))[:200] or f"Agreement with {s}", contract_type=d.get("contract_type") or "supply",
                                               start_date=start, end_date=end, value=svc.dec(d.get("value") or 0), payment_terms_days=int(d.get("payment_terms_days") or 30),
                                               auto_renew=bool(d.get("auto_renew")), notice_period_days=int(d.get("notice_period_days") or 30),
                                               scope=str(d.get("scope", ""))[:4000], slas=str(d.get("slas", ""))[:4000], pricing_terms=str(d.get("pricing_terms", ""))[:4000],
                                               penalties=str(d.get("penalties", ""))[:4000], insurance_expiry=parse_date(str(d.get("insurance_expiry") or "")) or None,
                                               owner=request.user)
        ContractObligation.objects.create(contract=c, kind="renewal", title="Renewal decision due", due_on=end - timedelta(days=c.notice_period_days), owner=request.user)
        if c.insurance_expiry:
            ContractObligation.objects.create(contract=c, kind="insurance", title="Supplier insurance expires", due_on=c.insurance_expiry, owner=request.user)
        record(request, "procurement.contract.created", category="data", module="procurement", resource=c, new={"value": c.value, "end": str(end)})
        return Response({"id": str(c.pk), "number": c.number}, status=status.HTTP_201_CREATED)


class ContractActionView(FinView):
    permissions = {"POST": "procurement.contract.manage"}

    def post(self, request, pk, action):
        ctx, d = self.authz, request.data
        c = _get(ProcurementContract.objects.filter(organization=ctx.organization), pk)
        if action == "decision":
            svc.renewal_decision(request, ctx, c, str(d.get("decision", "")), str(d.get("note", "")))
        elif action == "obligation":
            ContractObligation.objects.create(contract=c, kind=d.get("kind") or "deliverable", title=str(d.get("title", ""))[:200],
                                              due_on=parse_date(str(d.get("due_on") or "")) or None, owner=request.user)
        elif action == "obligation-done":
            ContractObligation.objects.filter(contract=c, pk=d.get("obligation_id")).update(status=d.get("status") or "done")
        else:
            raise DomainError("Not found.", code="not_found", status_code=404)
        return Response({"ok": True})


class RecurringView(FinView):
    permissions = {"GET": "procurement.order.view", "POST": "procurement.order.create"}

    def get(self, request):
        qs = RecurringPurchase.objects.filter(organization=self.authz.organization).select_related("supplier", "contract", "category", "owner", "last_request")
        return Response({"results": [{"id": str(r.pk), "number": r.number, "title": r.title, "supplier": str(r.supplier), "contract": r.contract.number if r.contract_id else None,
                                      "frequency": r.frequency, "amount": r.expected_amount, "next": r.next_date, "active": r.is_active,
                                      "last_request": r.last_request.number if r.last_request_id else None, "owner": r.owner.full_name} for r in qs]})

    def post(self, request):
        ctx, d = self.authz, request.data
        if d.get("run"):
            return Response({"created": svc.run_recurring(ctx.organization)})
        from apps.finance import ledger

        s = _get(Supplier.objects.filter(organization=ctx.organization), d.get("supplier_id"))
        cat = _get(ProcurementCategory.objects.filter(organization=ctx.organization), d.get("category_id"))
        nd = parse_date(str(d.get("next_date") or ""))
        if nd is None:
            raise DomainError("Enter the next purchase date.", code="validation_error")
        r = RecurringPurchase.objects.create(organization=ctx.organization, number=ledger.next_number(ctx.organization, "recurring"), title=str(d.get("title", ""))[:200],
                                             supplier=s, category=cat, contract=ProcurementContract.objects.filter(organization=ctx.organization, pk=d.get("contract_id")).first()
                                             if d.get("contract_id") else None, frequency=d.get("frequency") or "monthly", expected_amount=svc.dec(d.get("expected_amount")),
                                             next_date=nd, owner=request.user, department=ctx.employee.department if ctx.employee else None)
        return Response({"id": str(r.pk), "number": r.number}, status=status.HTTP_201_CREATED)


class ExceptionsView(FinView):
    permissions = {"GET": "procurement.exception.view", "POST": "procurement.exception.manage"}

    def get(self, request):
        qs = ProcurementException.objects.filter(organization=self.authz.organization).select_related("owner", "resolved_by")
        if k := request.query_params.get("kind"):
            qs = qs.filter(kind=k)
        st = request.query_params.get("status", "open")
        if st != "all":
            qs = qs.filter(status__in=[st] if st != "open" else ["open", "pending_approval"])
        return Response({"results": [{"id": str(x.pk), "number": x.number, "kind": x.kind, "kind_label": x.get_kind_display(), "label": x.source_label,
                                      "description": x.description, "amount": x.amount, "status": x.status, "detected": x.detected, "reason": x.reason,
                                      "resolution": x.resolution, "owner": x.owner.full_name if x.owner_id else None, "created_at": x.created_at,
                                      "approval_id": str(x.approval_id) if x.approval_id else None} for x in qs[:300]],
                         "kinds": [{"value": v, "label": lbl} for v, lbl in ProcurementException.Kind.choices]})

    def post(self, request):
        n = svc.detect(self.authz.organization)
        return Response({"new_flags": n})


class ExceptionActionView(FinView):
    permissions = {"POST": "procurement.exception.manage"}

    def post(self, request, pk, action):
        ctx, d = self.authz, request.data
        x = _get(ProcurementException.objects.filter(organization=ctx.organization), pk)
        if action == "submit":
            svc.submit_exception(request, ctx, x, str(d.get("reason", "")))
        elif action == "resolve":
            if not str(d.get("resolution", "")).strip():
                raise DomainError("Record the resolution.", code="reason_required")
            x.status, x.resolution, x.resolved_by = d.get("status") if d.get("status") in ("resolved", "rejected") else "resolved", str(d["resolution"])[:500], request.user
            x.save()
            record(request, "procurement.exception.resolved", category="data", module="procurement", resource=x, new={"status": x.status})
        else:
            raise DomainError("Not found.", code="not_found", status_code=404)
        return Response({"status": x.status})


class ConflictsView(FinView):
    def get(self, request):
        ctx = self.authz
        qs = ConflictDeclaration.objects.filter(organization=ctx.organization).select_related("declarant", "supplier", "reviewed_by")
        if not ctx.has("procurement.exception.approve"):
            qs = qs.filter(declarant=request.user)
        return Response({"results": [{"id": str(c.pk), "declarant": c.declarant.full_name, "supplier": str(c.supplier) if c.supplier_id else c.supplier_name,
                                      "kind": c.kind, "kind_label": c.get_kind_display(), "description": c.description, "status": c.status, "decision": c.decision,
                                      "reviewed_by": c.reviewed_by.full_name if c.reviewed_by_id else None, "at": c.created_at} for c in qs[:300]],
                         "can_review": ctx.has("procurement.exception.approve")})

    def post(self, request):
        ctx, d = self.authz, request.data
        if d.get("kind") not in ConflictDeclaration.Kind.values or len(str(d.get("description", "")).strip()) < 10:
            raise DomainError("Choose the kind of conflict and describe it.", code="validation_error")
        c = ConflictDeclaration.objects.create(organization=ctx.organization, declarant=request.user, kind=d["kind"], description=str(d["description"])[:4000],
                                               supplier=Supplier.objects.filter(organization=ctx.organization, pk=d.get("supplier_id")).first() if d.get("supplier_id") else None,
                                               supplier_name=str(d.get("supplier_name", ""))[:200])
        from apps.access.authz import holders_of
        from apps.workspace.notify import notify_many

        notify_many([u for u in holders_of("procurement.exception.approve", ctx.organization) if u.pk != request.user.pk][:10], "workflow",
                    f"Conflict of interest declared by {request.user.full_name}", link="/procurement/conflicts", module="procurement")
        record(request, "procurement.conflict.declared", category="data", module="procurement", resource=c, sensitive=True)
        return Response({"id": str(c.pk)}, status=status.HTTP_201_CREATED)


class ConflictDetailView(FinView):
    permissions = {"PATCH": "procurement.exception.approve"}

    def patch(self, request, pk):
        c = _get(ConflictDeclaration.objects.filter(organization=self.authz.organization), pk)
        if c.declarant_id == request.user.pk:
            raise DomainError("Someone else reviews your declaration.", code="self_change_denied", status_code=403)
        if request.data.get("status") not in ("reviewed", "mitigated") or not str(request.data.get("decision", "")).strip():
            raise DomainError("Record the decision.", code="validation_error")
        c.status, c.decision, c.reviewed_by = request.data["status"], str(request.data["decision"])[:300], request.user
        c.save()
        record(request, "procurement.conflict.reviewed", category="data", module="procurement", resource=c, sensitive=True, new={"status": c.status})
        return Response({"status": c.status})


# --- analytics & settings -------------------------------------------------------------------------------------------
class AnalyticsView(FinView):
    permissions = {"GET": "procurement.analytics.view"}

    def get(self, request):
        ctx = self.authz
        s = ctx.require("procurement.analytics.view")
        if not s.org_wide:
            raise DomainError("Company-wide spend analytics need organization-wide access.", code="scope_restricted", status_code=403)
        today = timezone.localdate()
        f = parse_date(request.query_params.get("from", "") or "") or today.replace(month=1, day=1)
        t = parse_date(request.query_params.get("to", "") or "") or today
        data = svc.analytics(ctx.organization, f, t)
        if request.query_params.get("export") == "csv":
            ctx.require("procurement.analytics.export")
            dim = request.query_params.get("by", "by_supplier")
            record(request, f"procurement.analytics.export.{dim}", category="export", module="procurement")
            return _csv(data.get(dim, []), f"spend-{dim}")
        return Response(data)


class SupplierPerformanceView(FinView):
    permissions = {"GET": "procurement.supplier.view"}

    def get(self, request):
        rows = []
        for s in Supplier.objects.filter(organization=self.authz.organization, status="active"):
            sc = svc.supplier_scorecard(s)
            rows.append({"id": str(s.pk), "name": str(s), "code": s.code, "preference": s.preference, "risk": s.risk_level, **sc})
        return Response({"results": sorted(rows, key=lambda r: -(r["overall"] or 0))})


class SettingsView(FinView):
    permissions = {"GET": "procurement.settings.view", "PATCH": "procurement.settings.configure", "POST": "procurement.settings.configure"}
    FIELDS = ("rfq_required_above", "min_quotes", "emergency_max_amount", "capex_threshold", "match_tolerance_pct", "match_tolerance_amount", "receiver_not_buyer",
              "requester_not_buyer", "split_window_days", "concentration_threshold_pct", "block_unapproved_suppliers", "code_of_conduct", "gift_policy",
              "anti_bribery_policy")

    def get(self, request):
        p = svc.policy(self.authz.organization)
        return Response({"policy": {f: getattr(p, f) for f in self.FIELDS},
                         "categories": [{"id": str(c.pk), "code": c.code, "name": c.name, "parent": c.parent.code if c.parent_id else None, "expenditure": c.expenditure,
                                         "account": c.finance_account_key, "budget_category": c.budget_category, "match": c.match_mode, "inventory": c.is_inventory,
                                         "service": c.is_service, "rfq_above": c.rfq_required_above, "active": c.is_active}
                                        for c in ProcurementCategory.objects.filter(organization=self.authz.organization).select_related("parent")],
                         "templates": [{"key": k, "name": n, "category": c, "type": t} for k, n, c, t, *_ in TEMPLATES]})

    def patch(self, request):
        p = svc.policy(self.authz.organization)
        before = {f: str(getattr(p, f)) for f in self.FIELDS}
        for f in self.FIELDS:
            if f in request.data:
                cur = getattr(p, f)
                val = request.data[f]
                setattr(p, f, bool(val) if isinstance(cur, bool) else int(val) if isinstance(cur, int) else svc.dec(val) if not isinstance(cur, str) else str(val)[:4000])
        p.save()
        record(request, "procurement.policy.changed", category="config", module="procurement", old=before, new={f: str(getattr(p, f)) for f in self.FIELDS})
        return Response({"saved": True})

    def post(self, request):  # new category
        d = request.data
        org = self.authz.organization
        code = str(d.get("code", "")).upper().strip()
        if not code or not str(d.get("name", "")).strip() or ProcurementCategory.objects.filter(organization=org, code=code).exists():
            raise DomainError("Enter a unique code and a name.", code="validation_error")
        c = ProcurementCategory.objects.create(organization=org, code=code[:30], name=str(d["name"])[:120],
                                               parent=ProcurementCategory.objects.filter(organization=org, pk=d.get("parent_id")).first() if d.get("parent_id") else None,
                                               expenditure=d.get("expenditure") or "opex", finance_account_key=d.get("finance_account_key") or "general_expense",
                                               budget_category=str(d.get("budget_category", ""))[:40], match_mode=d.get("match_mode") or "three_way",
                                               is_service=bool(d.get("is_service")), is_inventory=bool(d.get("is_inventory")))
        record(request, "procurement.category.create", category="config", module="procurement", resource=c)
        return Response({"id": str(c.pk)}, status=status.HTTP_201_CREATED)
