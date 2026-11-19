"""Module 5 — Procurement: the full need → request → budget → approval → RFQ → quotes → negotiation → award → PO →
receipt → invoice → three-way match → Finance chain, plus SoD, supplier controls, exceptions and security tests."""

from decimal import Decimal as D

import pytest
from django.utils import timezone

from apps.access.models import Role, RoleAssignment
from apps.access.tests import os_seed, signed_in  # noqa: F401
from apps.finance import ledger
from apps.finance.models import BudgetCommitment, FixedAsset, Invoice
from apps.procurement.models import (Award, ProcurementCategory, ProcurementException, PurchaseOrder, PurchaseRequest, Quotation, SourcingEvent, Supplier,
                                     SupplierBankChange)
from apps.users.models import User

P = "/api/v1/os/procurement"


def approve(email, approval_id, ok=200):
    r = signed_in(email).post(f"/api/v1/os/approvals/{approval_id}/approve", {"comment": "ok"}, format="json")
    assert r.status_code == ok, r.content
    return r


def cat(org, code):
    return ProcurementCategory.objects.get(organization=org, code=code)


def sup(org, name):
    return Supplier.objects.get(organization=org, legal_name__startswith=name)


def new_pr(client, org, *, title="Laptops for operations", qty=2, price="60000", code="TECH-HW", submit=True, **extra):
    body = {"title": title, "categoryId": str(cat(org, code).pk), "justification": "New joiners in Hyderabad need laptops from day one.",
            "lines": [{"description": "Business laptop", "quantity": qty, "estimatedUnitCost": price}], "submit": submit, **extra}
    r = client.post(f"{P}/requests", body, format="json")
    assert r.status_code == 201, r.content
    return PurchaseRequest.objects.get(pk=r.json()["id"])


def test_full_procure_to_pay_chain(os_seed):
    arjun = signed_in("arjun.kumar@click.dev")
    pr = new_pr(arjun, os_seed)
    assert pr.status == "submitted" and pr.budget_check["status"] in ("ok", "no_budget")
    assert arjun.post(f"/api/v1/os/approvals/{pr.approval_id}/approve", {"comment": "me"}, format="json").status_code == 403  # own request
    approve("kabir.malhotra@click.dev", pr.approval_id)  # manager-level (procurement manager within limit)
    approve("priya.menon@click.dev", pr.approval_id)     # finance level (≥ 1,00,000)
    pr.refresh_from_db()
    assert pr.status == "approved"

    pooja = signed_in("pooja.shah@click.dev")
    dell, lenovo = sup(os_seed, "Dell"), sup(os_seed, "Lenovo")
    r = pooja.post(f"{P}/sourcing", {"kind": "rfq", "purchaseRequestId": str(pr.pk), "supplierIds": [str(dell.pk), str(lenovo.pk)],
                                     "responseDeadline": (timezone.now() + timezone.timedelta(days=3)).isoformat()}, format="json")
    assert r.status_code == 201, r.content
    ev = SourcingEvent.objects.get(pk=r.json()["id"])
    assert pooja.post(f"{P}/sourcing/{ev.pk}/publish").status_code == 200
    for s, price, days in ((dell, "59000", 7), (lenovo, "57000", 12)):
        r = pooja.post(f"{P}/sourcing/{ev.pk}/quote", {"supplierId": str(s.pk), "deliveryDays": days, "warrantyMonths": 36, "paymentTermsDays": 30,
                                                       "validUntil": (timezone.localdate() + timezone.timedelta(days=10)).isoformat(),
                                                       "lines": [{"unitPrice": price, "taxRate": "18"}]}, format="json")
        assert r.status_code == 201, r.content
    dq = Quotation.objects.get(event=ev, supplier=dell)
    assert pooja.post(f"{P}/quotations/{dq.pk}/score", {"scores": {"quality": 95, "support": 90, "compliance": 100}}, format="json").status_code == 200
    r = pooja.post(f"{P}/quotations/{dq.pk}/negotiate", {"changes": {"lines": [{"lineId": str(dq.lines.first().pk), "unitPrice": "56500"}]},
                                                         "note": "Matched Lenovo's price with Dell's faster delivery."}, format="json")
    assert r.status_code == 201
    dq.refresh_from_db()
    assert dq.status == "superseded" and not dq.is_current  # the original quote is preserved, never overwritten
    new = Quotation.objects.get(pk=r.json()["id"])
    detail = pooja.get(f"{P}/sourcing/{ev.pk}").json()
    assert detail["comparison"]["rows"][0]["supplier"].startswith("Dell") and len(detail["negotiations"]) == 1
    body = {"quotationId": str(new.pk), "reason": "Best weighted score: equal price after negotiation and 7-day delivery."}
    r = pooja.post(f"{P}/sourcing/{ev.pk}/award", body, format="json")
    assert r.status_code == 409 and r.json()["error"]["code"] == "insufficient_quotes"  # policy: 3 quotes above the RFQ threshold
    r = pooja.post(f"{P}/sourcing/{ev.pk}/award", {**body, "exceptionReason": "Only two authorised laptop distributors serve Hyderabad."}, format="json")
    assert r.status_code == 201, r.content
    assert ProcurementException.objects.filter(kind="no_competitive_quotes", source_id=ev.pk).exists()
    a = Award.objects.get(pk=r.json()["id"])
    assert a.savings_method == "negotiated" and a.savings == D("5000.00")  # pre-tax: (59,000 - 56,500) x 2
    approve("kabir.malhotra@click.dev", a.approval_id)
    po = PurchaseOrder.objects.get(award=a)
    assert po.status == "draft" and po.created_by.email == "pooja.shah@click.dev"
    assert pooja.post(f"{P}/orders/{po.pk}/submit").status_code == 200
    po.refresh_from_db()
    approve("kabir.malhotra@click.dev", po.approval_id)
    po.refresh_from_db()
    assert po.status == "approved" and po.versions.filter(version=1).exists()
    assert BudgetCommitment.objects.filter(source_type="procurement.order", source_id=str(po.pk)).exists() or not pr.budget_id
    assert pooja.post(f"{P}/orders/{po.pk}/send").status_code == 200
    assert pooja.post(f"{P}/orders/{po.pk}/confirm", {"result": "accepted"}, format="json").status_code == 200

    ravi = signed_in("ravi.kumar@click.dev")
    ln = po.lines.first()
    assert ravi.post(f"{P}/orders/{po.pk}/receive", {"lines": [{"lineId": str(ln.pk), "receivedQty": 3}]}, format="json").json()["error"]["code"] == "over_receipt"
    assert ravi.post(f"{P}/orders/{po.pk}/receive", {"lines": [{"lineId": str(ln.pk), "receivedQty": 1}]}, format="json").status_code == 201
    po.refresh_from_db()
    assert po.status == "partially_received"  # never auto-completed
    assert FixedAsset.objects.filter(source_type="procurement.grn_line", status="draft").exists()  # capex → asset register

    suresh = signed_in("suresh.pillai@click.dev")
    r = suresh.post(f"{P}/orders/{po.pk}/invoice", {"supplierInvoiceNumber": "DL-INV-1", "lines": [{"lineId": str(ln.pk), "quantity": 2, "unitPrice": "56500"}]},
                    format="json")
    assert r.status_code == 201 and r.json()["match"] == "exception"  # 2 billed, 1 received
    bad = Invoice.objects.get(pk=r.json()["id"])
    assert suresh.post(f"/api/v1/os/finance/invoices/{bad.pk}/submit", {}, format="json").json()["error"]["code"] == "match_exception"
    suresh.post(f"/api/v1/os/finance/invoices/{bad.pk}/void", {"reason": "Wrong quantity"}, format="json")
    r = suresh.post(f"{P}/orders/{po.pk}/invoice", {"supplierInvoiceNumber": "DL-INV-2"}, format="json")
    assert r.status_code == 201 and r.json()["match"] == "matched", r.content
    good = Invoice.objects.get(pk=r.json()["id"])
    assert suresh.post(f"/api/v1/os/finance/invoices/{good.pk}/submit", {}, format="json").status_code == 200
    good.refresh_from_db()
    approve("priya.menon@click.dev", good.approval_id)
    po.refresh_from_db()
    assert po.lines.first().invoiced_qty == 1 and po.status in ("partially_invoiced", "invoiced")
    trace = arjun.get(f"{P}/requests/{pr.pk}").json()["trace"]
    assert trace["orders"] and trace["receipts"] and trace["sourcing"]  # need → request → sourcing → PO → receipt


def test_receiver_must_not_be_the_buyer(os_seed):
    from apps.access.authz import load_context
    from apps.procurement import services as svc
    from django.test import RequestFactory
    from apps.core.api.exceptions import DomainError

    kabir = User.objects.get(email="kabir.malhotra@click.dev")
    pr = PurchaseRequest.objects.filter(organization=os_seed, title__startswith="Laptops").first()
    pr.status = "approved"
    pr.save()
    req = RequestFactory().post("/")
    req.user = kabir
    ctx = load_context(kabir)
    po = svc._create_po(os_seed, supplier=sup(os_seed, "Dell"), category=pr.category, created_by=kabir, pr=pr,
                        lines=svc._po_lines_from([{"description": "Laptop", "quantity": D("1"), "unit_price": D("60000")}], pr.category))
    po.status = "approved"
    po.save()
    with pytest.raises(DomainError) as e:
        svc.receive(req, ctx, po, [{"line_id": str(po.lines.first().pk), "received_qty": 1}])
    assert e.value.error_code == "sod_blocked"


def test_supplier_controls(os_seed):
    pooja = signed_in("pooja.shah@click.dev")
    r = pooja.post(f"{P}/suppliers", {"legalName": "Dell Technologies India Private Limited"}, format="json")
    assert r.status_code == 409 and r.json()["error"]["code"] == "possible_duplicate"
    r = pooja.post(f"{P}/suppliers", {"legalName": "Metro Furniture Works", "taxId": "36AAAAA9999A1Z5", "email": "sales@metrofurniture.example"}, format="json")
    assert r.status_code == 201
    s = Supplier.objects.get(pk=r.json()["id"])
    assert pooja.post(f"{P}/suppliers/{s.pk}/submit").json()["error"]["code"] == "verification_incomplete"
    # bank details go through an approved change — buyers can't even request one
    assert pooja.post(f"{P}/suppliers/{s.pk}/bank-change", {"accountNumber": "123456789012", "ifsc": "HDFC0000123", "reason": "new", "evidence": "x"},
                      format="json").status_code == 403
    kabir = signed_in("kabir.malhotra@click.dev")
    RoleAssignment.objects.create(user=User.objects.get(email="kabir.malhotra@click.dev"), role=Role.objects.get(key="procurement-director"))
    kabir = signed_in("kabir.malhotra@click.dev")
    r = kabir.post(f"{P}/suppliers/{s.pk}/bank-change", {"accountNumber": "123456789012", "ifsc": "HDFC0000123", "reason": "New supplier account",
                                                          "evidence": "Cancelled cheque + call-back to listed number"}, format="json")
    assert r.status_code == 201
    bc = SupplierBankChange.objects.get(pk=r.json()["id"])
    assert kabir.post(f"/api/v1/os/approvals/{bc.approval_id}/approve", {"comment": "me"}, format="json").status_code == 403  # requester can't approve
    approve("priya.menon@click.dev", bc.approval_id, ok=404)  # not in the chain: no supplier-bank authority, so the request stays hidden
    s.refresh_from_db()
    assert s.bank_last4 == ""  # nothing changes without approval
    for check in ("legal_name", "tax_registration"):
        assert pooja.post(f"{P}/suppliers/{s.pk}/verify", {"check": check, "status": "verified"}, format="json").status_code == 200
    assert pooja.post(f"{P}/suppliers/{s.pk}/verify", {"check": "bank_account", "status": "verified"}, format="json").status_code == 400  # no bank yet
    # blocked suppliers can't be invited or ordered from
    lenovo = sup(os_seed, "Lenovo")
    assert kabir.post(f"{P}/suppliers/{lenovo.pk}/preference", {"preference": "blocked", "reasonCategory": "quality", "note": ""}, format="json").status_code == 400
    assert kabir.post(f"{P}/suppliers/{lenovo.pk}/preference", {"preference": "blocked", "reasonCategory": "quality", "note": "Repeated DOA units"},
                      format="json").status_code == 200
    ev = SourcingEvent.objects.filter(organization=os_seed).first()
    assert pooja.post(f"{P}/sourcing/{ev.pk}/invite", {"supplierIds": [str(lenovo.pk)]}, format="json").json()["error"]["code"] == "supplier_blocked"


def test_emergency_single_source_and_split_controls(os_seed):
    divya = signed_in("divya.patel@click.dev")
    r = divya.post(f"{P}/requests", {"title": "Generator rental", "categoryId": str(cat(os_seed, "OPS-FLD").pk), "requestType": "emergency",
                                     "justification": "Power failure at the Hyderabad branch.", "emergencyReason": "Grid down for 3 days, cold chain at risk",
                                     "lines": [{"description": "Generator", "quantity": 1, "estimatedUnitCost": "500000"}], "submit": True}, format="json")
    assert r.status_code == 409 and r.json()["error"]["code"] == "emergency_limit"
    pr = new_pr(divya, os_seed, title="Generator rental", code="OPS-FLD", qty=1, price="40000", requestType="emergency",
                emergencyReason="Grid down for 3 days, cold chain at risk")
    assert pr.is_emergency and pr.post_review == "pending"
    assert ProcurementException.objects.filter(kind="emergency_purchase", source_id=str(pr.pk)).exists()
    r = divya.post(f"{P}/requests", {"title": "Special software", "categoryId": str(cat(os_seed, "TECH-SW").pk), "justification": "Needed for compatibility work.",
                                     "singleSource": True, "lines": [{"description": "Licence", "quantity": 1, "estimatedUnitCost": "5000"}], "submit": True}, format="json")
    assert r.status_code == 400  # single source needs a reason and justification
    for i in range(3):  # three requests just below the RFQ threshold
        new_pr(divya, os_seed, title=f"Chairs batch {i}", code="OFF-STAT", qty=1, price="45000")
    assert ProcurementException.objects.filter(kind="split_purchase", detected=True).exists()


def test_budget_override_needs_a_reason(os_seed):
    vikram = signed_in("vikram.shah@click.dev")  # Technology department: ₹12,00,000 budget
    r = vikram.post(f"{P}/requests", {"title": "Servers", "categoryId": str(cat(os_seed, "TECH-HW").pk), "justification": "Capacity for the festive season peak.",
                                      "lines": [{"description": "Server", "quantity": 5, "estimatedUnitCost": "300000"}], "submit": True}, format="json")
    assert r.status_code == 409 and r.json()["error"]["code"] == "budget_insufficient"
    pr = PurchaseRequest.objects.filter(title="Servers").first()
    r = vikram.post(f"{P}/requests/{pr.pk}/submit", {"budgetOverrideReason": "Board approved festive capacity plan"}, format="json")
    assert r.status_code == 200
    assert ProcurementException.objects.filter(kind="budget_exceeded", source_id=str(pr.pk)).exists()


def test_amendment_creates_a_new_version(os_seed):
    from apps.access.authz import load_context
    from apps.procurement import services as svc
    from django.test import RequestFactory

    pooja_u = User.objects.get(email="pooja.shah@click.dev")
    pr = PurchaseRequest.objects.filter(organization=os_seed, title__startswith="Laptops").first()
    po = svc._create_po(os_seed, supplier=sup(os_seed, "Kalpana"), category=cat(os_seed, "OFF-STAT"), created_by=pooja_u, pr=pr,
                        lines=svc._po_lines_from([{"description": "Paper", "quantity": D("10"), "unit_price": D("300")}], cat(os_seed, "OFF-STAT")))
    pooja = signed_in("pooja.shah@click.dev")
    assert pooja.post(f"{P}/orders/{po.pk}/amend", {"reason": "x", "changes": {}}, format="json").status_code == 409  # drafts aren't amended
    assert pooja.post(f"{P}/orders/{po.pk}/submit").status_code == 200
    po.refresh_from_db()
    approve("kabir.malhotra@click.dev", po.approval_id)
    r = pooja.post(f"{P}/orders/{po.pk}/amend", {"reason": "Supplier price revision", "changes": {"lines": [{"lineId": str(po.lines.first().pk), "quantity": 12}]}},
                   format="json")
    assert r.status_code == 201
    approve("kabir.malhotra@click.dev", r.json()["approvalId"])
    po.refresh_from_db()
    assert po.version == 2 and po.lines.first().quantity == 12 and po.versions.count() == 2
    assert po.versions.get(version=1).snapshot["lines"][0]["quantity"] == "10.000"


def test_procurement_access_boundaries(os_seed):
    divya = signed_in("divya.patel@click.dev")
    assert divya.get(f"{P}/home").json()["mode"] == "self"
    for url in ("orders", "sourcing", "suppliers", "analytics", "exceptions", "contracts", "settings"):
        assert divya.get(f"{P}/{url}").status_code == 403, url
    assert divya.get(f"{P}/requests").status_code == 200  # her own requests
    ev = SourcingEvent.objects.filter(organization=os_seed).first()
    assert divya.get(f"{P}/sourcing/{ev.pk}").status_code == 403
    groups = divya.get("/api/v1/os/search?q=QT-000001").json()["groups"]
    assert not any(g["type"] in ("quotation", "purchase_order", "supplier") for g in groups)
    ai = divya.post("/api/v1/os/ai", {"question": "which suppliers are high concentration risks"}, format="json").json()
    assert "%" not in ai["answer"]
    ravi = signed_in("ravi.kumar@click.dev")  # receiving can't see quotations or pricing comparisons
    assert ravi.get(f"{P}/sourcing/{ev.pk}").status_code == 403
    analyst = User.objects.get(email="farah.khan@click.dev")  # auditor: read-only procurement
    r = signed_in("farah.khan@click.dev").post(f"{P}/orders", {}, format="json")
    assert r.status_code == 403 and analyst
