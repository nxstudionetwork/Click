"""Module 4 — Finance: GTV vs revenue, double entry, settlements, approvals, SoD, periods, AP/AR, expenses, budgets,
and the security tests the spec asks for."""

import uuid
from datetime import timedelta
from decimal import Decimal as D

import pytest
from django.test import RequestFactory
from django.utils import timezone

from apps.access.authz import load_context
from apps.access.tests import os_seed, signed_in  # noqa: F401
from apps.core.api.exceptions import DomainError
from apps.finance import ledger, platform, reports, services
from apps.finance.ledger import Line
from apps.finance.models import (Account, BankAccount, ExpenseCategory, FinancePayment, FinancialPeriod, Invoice, Journal, PartnerAgreement,
                                 SettlementBatch, TransactionBreakdown)
from apps.orders.models import Order
from apps.partners.models import Partner, PartnerCategory, PartnerStore, PartnerType
from apps.payments.models import Payment
from apps.users.models import User
from conftest import make_customer, make_store

F = "/api/v1/os/finance"


def user(email):
    return User.objects.get(email=email)


def req_for(u):
    r = RequestFactory().post("/")
    r.user = u
    return r


def make_partner(name="Spice Route"):
    ptype, _ = PartnerType.objects.get_or_create(slug="food", defaults={"name": "Food"})
    pcat, _ = PartnerCategory.objects.get_or_create(slug="restaurant", defaults={"name": "Restaurant", "partner_type": ptype})
    return Partner.objects.create(partner_type=ptype, category=pcat, status=Partner.Status.ACTIVE, business_name=name,
                                  partner_code=f"CLK-PT-{uuid.uuid4().hex[:6].upper()}")


def platform_payment(partner=None, *, subtotal="1000", delivery="40", tax="50", discount="0", method="upi", status="captured"):
    cust = make_customer(f"c{uuid.uuid4().hex[:8]}@example.com")
    store = make_store(f"Store {uuid.uuid4().hex[:6]}")
    if partner is not None:
        PartnerStore.objects.create(partner=partner, store=store)
    total = D(subtotal) + D(delivery) + D(tax) - D(discount)
    order = Order.objects.create(customer=cust.customer_profile, store=store, status="delivered", delivery_address={}, subtotal=D(subtotal),
                                 delivery_fee=D(delivery), tax=D(tax), discount=D(discount), total=total, idempotency_key=uuid.uuid4())
    return Payment.objects.create(order=order, method=method, status=status, amount=total, provider_reference=f"gw-{uuid.uuid4().hex[:10]}")


def entity(org):
    return ledger.default_entity(org)


# --- GTV vs revenue -------------------------------------------------------------------------------------------------
def test_marketplace_payment_is_not_click_revenue(os_seed):
    p = make_partner()
    pay = platform_payment(p)
    out = platform.sync(os_seed)
    assert out["sales"] >= 1
    b = TransactionBreakdown.objects.get(payment=pay, kind="sale")
    # default agreement: 15% commission, 18% tax on fees, delivery fee to Click, UPI fee 0%
    assert (b.gross, b.commission, b.fee_tax, b.click_revenue, b.partner_share) == (D("1090"), D("150"), D("27"), D("190"), D("873"))
    assert b.partner_share + b.click_revenue + b.fee_tax == b.gross
    assert b.journal.status == "posted" and b.journal.lines.count() >= 4
    e = entity(os_seed)
    pl = reports.profit_and_loss(e, timezone.localdate() - timedelta(days=1), timezone.localdate())
    assert pl["revenue"] == D("190")  # not 1090
    assert ledger.key_balance(e, "partner_payable") == D("873")
    assert platform.sync(os_seed)["sales"] == 0  # idempotent
    assert reports.trial_balance(e, timezone.localdate())["balanced"]


def test_click_funded_discount_and_click_funded_refund(os_seed):
    p = make_partner("Biryani House")
    PartnerAgreement.objects.create(organization=os_seed, partner=p, code="AGR-T1", commission_pct=D("10"), tax_on_fees_pct=D("0"),
                                    promo_funding="click", refund_responsibility="click", effective_from=timezone.localdate() - timedelta(days=30),
                                    status="active")
    pay = platform_payment(p, subtotal="500", delivery="0", tax="0", discount="100", method="card")
    platform.sync(os_seed)
    b = TransactionBreakdown.objects.get(payment=pay, kind="sale")
    assert b.gross == D("400") and b.discount_click == D("100") and b.commission == D("50")
    assert b.partner_share == D("450")  # partner gets the full merchandise value minus commission; Click pays the promotion
    assert b.gateway_fee == D("8.00") and b.click_net == D("50") - D("8") - D("100")
    pay.status = "refunded"
    pay.save()
    platform.sync(os_seed)
    r = TransactionBreakdown.objects.get(payment=pay, kind="refund")
    assert r.partner_share == 0  # Click bears the refund: partner keeps its share
    e = entity(os_seed)
    assert ledger.key_balance(e, "refund_cost") == D("450")
    assert reports.trial_balance(e, timezone.localdate())["balanced"]


def test_partner_funded_refund_is_recovered_at_settlement(os_seed):
    p = make_partner("Tandoor Co")
    a = platform_payment(p)
    b2 = platform_payment(p)
    b2.status = "refunded"
    b2.save()
    platform.sync(os_seed)
    priya = user("priya.menon@click.dev")
    batch = platform.create_batch(req_for(priya), load_context(priya), timezone.localdate())
    line = batch.lines.get(partner=p)
    assert line.net_payable == D("873") and line.refunds == D("-873")  # second sale refunded and recovered
    assert TransactionBreakdown.objects.filter(payment=a, kind="sale").first().settlement_status == "in_batch"


def test_wallet_topup_is_a_liability(os_seed):
    from apps.wallet.models import WalletTopUp

    cust = make_customer("wallet@example.com")
    t = WalletTopUp.objects.create(customer=cust.customer_profile, amount=D("500"), method="upi", provider="internal", idempotency_key="k1")
    Payment.objects.create(wallet_topup=t, method="upi", status="captured", amount=D("500"), provider_reference="gw-top")
    platform.sync(os_seed)
    e = entity(os_seed)
    assert ledger.key_balance(e, "stored_value") == D("500")
    assert reports.profit_and_loss(e, timezone.localdate() - timedelta(days=1), timezone.localdate())["revenue"] == 0


# --- settlements & SoD ----------------------------------------------------------------------------------------------
def test_settlement_approval_payment_and_statement(os_seed):
    p = make_partner("Dosa Point")
    platform_payment(p)
    platform_payment(p, subtotal="2000", delivery="0", tax="100")
    platform.sync(os_seed)
    priya = signed_in("priya.menon@click.dev")
    r = priya.post(f"{F}/settlements", {"periodTo": timezone.localdate().isoformat()}, format="json")
    assert r.status_code == 201, r.content
    batch = SettlementBatch.objects.get(pk=r.json()["id"])
    assert batch.status == "pending_approval"
    assert priya.post(f"/api/v1/os/approvals/{batch.approval_id}/approve", {"comment": "ok"}, format="json").status_code == 403  # own batch
    assert signed_in("ananya.rao@click.dev").post(f"/api/v1/os/approvals/{batch.approval_id}/approve", {"comment": "ok"}, format="json").status_code == 200
    batch.refresh_from_db()
    assert batch.status == "approved"
    bank = BankAccount.objects.filter(entity__organization=os_seed, account_type="current").first()
    # the preparer can't release the money, and a settlement executive can't either (no execute permission)
    assert priya.post(f"{F}/settlements/{batch.pk}/pay", {"bankAccountId": str(bank.pk)}, format="json").status_code == 403
    anita = signed_in("anita.desai@click.dev")
    assert anita.post(f"{F}/settlements/{batch.pk}/pay", {"bankAccountId": str(bank.pk), "reference": "NEFT123"}, format="json").status_code == 200
    e = entity(os_seed)
    assert ledger.key_balance(e, "partner_payable") == 0
    st = priya.get(f"{F}/statements?partner={p.pk}&from={timezone.localdate() - timedelta(days=2)}&to={timezone.localdate()}").json()
    assert st["closingBalance"] == "0.00" and D(st["payments"]) == batch.net_payable
    assert D(st["check"]["openingPlusMovements"]) == D(st["closingBalance"])


# --- ledger controls ------------------------------------------------------------------------------------------------
def test_unbalanced_and_closed_period_postings_are_refused(os_seed):
    e = entity(os_seed)
    with pytest.raises(DomainError) as x:
        ledger.post(e, date=timezone.localdate(), description="bad", lines=[Line("cash", debit=D("10")), Line("general_expense", credit=D("9"))])
    assert x.value.error_code == "journal_unbalanced"
    with pytest.raises(DomainError) as x:
        ledger.post(e, date=timezone.localdate(), description="bad", lines=[Line("no_such_key", debit=D("10")), Line("cash", credit=D("10"))])
    assert x.value.error_code == "missing_account_mapping"
    last = timezone.localdate().replace(day=1) - timedelta(days=1)
    p = ledger.period_for(e, last)
    p.status = "closed"
    p.save()
    with pytest.raises(DomainError) as x:
        ledger.post(e, date=last, description="late", lines=[Line("cash", debit=D("10")), Line("general_expense", credit=D("10"))])
    assert x.value.error_code == "period_closed"


def test_manual_journal_four_eyes_and_reversal(os_seed):
    suresh = signed_in("suresh.pillai@click.dev")
    e = entity(os_seed)
    acc = {a.system_key: str(a.pk) for a in Account.objects.filter(entity=e)}
    bad = {"date": timezone.localdate().isoformat(), "description": "Accrue rent", "kind": "accrual",
           "lines": [{"accountId": acc["rent"], "debit": "50000"}, {"accountId": acc["ap"], "credit": "40000"}]}
    assert suresh.post(f"{F}/journals", bad, format="json").json()["error"]["code"] == "journal_unbalanced"
    bad["lines"][1]["credit"] = "50000"
    r = suresh.post(f"{F}/journals", bad, format="json")
    assert r.status_code == 201 and r.json()["status"] == "pending_approval"
    j = Journal.objects.get(pk=r.json()["id"])
    assert not j.number
    assert suresh.post(f"/api/v1/os/approvals/{j.approval_id}/approve", {"comment": "me"}, format="json").status_code == 403
    anita = signed_in("anita.desai@click.dev")
    assert anita.post(f"/api/v1/os/approvals/{j.approval_id}/approve", {"comment": "ok"}, format="json").status_code == 200
    j.refresh_from_db()
    assert j.status == "posted" and j.number.startswith("JV-")
    assert anita.post(f"{F}/journals/{j.pk}/reverse", {"reason": ""}, format="json").status_code == 400
    r = anita.post(f"{F}/journals/{j.pk}/reverse", {"reason": "Rent was already billed"}, format="json")
    assert r.status_code == 201
    j.refresh_from_db()
    assert j.status == "reversed" and ledger.key_balance(e, "rent") == 0


def test_period_close_checklist_and_controlled_reopen(os_seed):
    anita = signed_in("anita.desai@click.dev")
    e = entity(os_seed)
    p = ledger.period_for(e, timezone.localdate())
    r = anita.post(f"{F}/periods/{p.pk}/close", {}, format="json")
    assert r.status_code == 409 and r.json()["error"]["code"] == "close_checklist_open"
    assert anita.post(f"{F}/periods/{p.pk}/close", {"overrideReason": "Dev month, nothing to reconcile"}, format="json").status_code == 200
    p.refresh_from_db()
    assert p.status == "closed"
    with pytest.raises(DomainError):
        ledger.post(e, date=timezone.localdate(), description="x", lines=[Line("cash", debit=D("1")), Line("general_expense", credit=D("1"))])
    suresh = signed_in("suresh.pillai@click.dev")
    r = suresh.post(f"{F}/periods/{p.pk}/reopen", {"reason": "Missed a supplier bill from the 3rd"}, format="json")
    assert r.status_code == 201
    assert anita.post(f"/api/v1/os/approvals/{r.json()['approvalId']}/approve", {"comment": "ok"}, format="json").status_code == 200
    p.refresh_from_db()
    assert p.status == "open" and p.reopen_reason and p.reopened_by.email == "anita.desai@click.dev"


# --- AP / AR --------------------------------------------------------------------------------------------------------
def test_bill_approval_payment_sod_and_duplicates(os_seed):
    suresh = signed_in("suresh.pillai@click.dev")
    body = {"kind": "vendor_bill", "partyName": "Office Mart", "partyType": "supplier", "partyId": "SUP-X", "supplierInvoiceNumber": "OM-77",
            "lines": [{"description": "Chairs", "quantity": 4, "unitPrice": "5000", "accountKey": "office"}]}
    r = suresh.post(f"{F}/invoices", body, format="json")
    assert r.status_code == 201, r.content
    assert suresh.post(f"{F}/invoices", body, format="json").json()["error"]["code"] == "duplicate_invoice"
    inv = Invoice.objects.get(pk=r.json()["id"])
    assert suresh.post(f"{F}/invoices/{inv.pk}/submit", {}, format="json").status_code == 200
    inv.refresh_from_db()
    priya = signed_in("priya.menon@click.dev")
    assert priya.post(f"/api/v1/os/approvals/{inv.approval_id}/approve", {"comment": "ok"}, format="json").status_code == 200
    inv.refresh_from_db()
    e = entity(os_seed)
    assert inv.status == "issued" and inv.number.startswith("BILL-") and ledger.key_balance(e, "ap") == D("20000")
    r = suresh.post(f"{F}/payments", {"invoiceId": str(inv.pk)}, format="json")
    assert r.status_code == 201, r.content
    pay = FinancePayment.objects.get(pk=r.json()["id"])
    assert priya.post(f"/api/v1/os/approvals/{pay.approval_id}/approve", {"comment": "ok"}, format="json").status_code == 200
    assert suresh.post(f"{F}/payments/{pay.pk}/execute", {}, format="json").status_code == 403
    bank = BankAccount.objects.filter(entity=e, account_type="current").first()
    assert signed_in("anita.desai@click.dev").post(f"{F}/payments/{pay.pk}/execute", {"bankAccountId": str(bank.pk)}, format="json").status_code == 200
    inv.refresh_from_db()
    assert inv.status == "paid" and ledger.key_balance(e, "ap") == 0
    with pytest.raises(DomainError):  # cannot pay a fully paid bill again
        services.create_outgoing(req_for(user("suresh.pillai@click.dev")), load_context(user("suresh.pillai@click.dev")), invoice=inv)


def test_credit_note_never_edits_the_invoice(os_seed):
    priya_u = user("priya.menon@click.dev")
    ctx = load_context(priya_u)
    ar_before = ledger.key_balance(entity(os_seed), "ar")
    inv = services.create_invoice(req_for(priya_u), ctx, {"partyName": "Ad Buyer", "party_name": "Ad Buyer", "lines": [
        {"description": "Banner", "quantity": 1, "unit_price": "10000", "account_key": "advertising_revenue"}]}, kind="customer_invoice")
    services.issue_invoice(req_for(priya_u), ctx, inv)
    note = services.create_note(req_for(priya_u), ctx, inv, kind="credit_note", amount="4000", reason="Campaign ran 6 of 10 days")
    signed_in("anita.desai@click.dev")  # controller approves credit notes
    from apps.workflows import engine

    engine.decide(req_for(user("anita.desai@click.dev")), note.approval, "approve", comment="ok")
    note.refresh_from_db()
    inv.refresh_from_db()
    assert note.status == "issued" and note.number.startswith("CN-") and inv.total == D("10000") and inv.amount_paid == D("4000")
    assert ledger.key_balance(entity(os_seed), "ar") - ar_before == D("6000")


# --- expenses & budgets ---------------------------------------------------------------------------------------------
def test_expense_policy_and_posting(os_seed):
    divya = signed_in("divya.patel@click.dev")
    cat = ExpenseCategory.objects.get(organization=os_seed, key="travel")
    base = {"categoryId": str(cat.pk), "date": timezone.localdate().isoformat(), "purpose": "Client visit Hyderabad", "amount": "30000"}
    r = divya.post(f"{F}/expenses", base, format="json")
    assert r.status_code == 400 and r.json()["error"]["code"] == "receipt_required"
    r = divya.post(f"{F}/expenses", {**base, "hasReceipt": True}, format="json")
    assert r.status_code == 201 and any("limit" in f for f in r.json()["policyFlags"])
    approval = r.json()["approvalId"]
    assert signed_in("karthik.reddy@click.dev").post(f"/api/v1/os/approvals/{approval}/approve", {"comment": "ok"}, format="json").status_code == 200
    assert ledger.key_balance(entity(os_seed), "employee_payable") == D("30000")
    assert divya.get(f"{F}/expenses").json()["results"][0]["status"] == "approved"


def test_budget_check_and_commitment(os_seed):
    from apps.organization.models import Department

    tech = Department.objects.get(organization=os_seed, code="TECH")
    res = services.check_budget(os_seed, "200000", department=tech)
    assert res["found"] and res["status"] == "ok", res
    assert res["available"] == D("1200000"), res
    services.reserve(os_seed, budget_id=res["budget_id"], amount="1100000", source_module="procurement", source_type="test.pr", source_id="1", label="PR test")
    res = services.check_budget(os_seed, "200000", department=tech)
    assert res["status"] == "insufficient" and res["available"] == D("100000") and res["after"] == D("-100000")
    services.release("test.pr", "1")
    assert services.check_budget(os_seed, "200000", department=tech)["status"] == "ok"


# --- security -------------------------------------------------------------------------------------------------------
def test_finance_access_boundaries(os_seed):
    divya = signed_in("divya.patel@click.dev")
    for url in ("journals", "reports?r=pl", "platform", "settlements", "bank-accounts", "accounts"):
        assert divya.get(f"{F}/{url}").status_code == 403, url
    assert divya.get(f"{F}/home").json()["mode"] == "self"
    karthik = signed_in("karthik.reddy@click.dev")  # regional finance manager
    r = karthik.get(f"{F}/reports?r=pl")
    assert r.status_code == 403 and r.json()["error"]["code"] == "scope_restricted"
    assert karthik.get(f"{F}/platform").status_code == 403
    farah = signed_in("farah.khan@click.dev")  # auditor: read-only
    assert farah.get(f"{F}/reports?r=tb").status_code == 200
    assert farah.post(f"{F}/journals", {"date": timezone.localdate().isoformat(), "description": "x", "lines": []}, format="json").status_code == 403
    bank = BankAccount.objects.filter(entity__organization=os_seed, account_type="current").first()
    assert signed_in("ananya.rao@click.dev").post(f"{F}/bank-accounts/{bank.pk}/reveal").status_code == 403  # executive ≠ banking
    assert divya.get("/api/v1/os/search?q=BILL-").json().get("results", []) == [] or all(
        r["type"] not in ("invoice", "journal") for r in divya.get("/api/v1/os/search?q=BILL-").json()["results"])
    ai = divya.post("/api/v1/os/ai", {"question": "finance summary for this month"}, format="json").json()
    assert "Gross transaction value" not in ai["answer"] and "190" not in ai["answer"]


def test_bank_details_are_encrypted_masked_and_audited(os_seed):
    from apps.audit.models import AuditEvent

    bank = BankAccount.objects.filter(entity__organization=os_seed, account_type="current").first()
    assert bank.last4 == "5678" and "50200012345678" not in bank.account_number_enc
    priya = signed_in("priya.menon@click.dev")
    assert priya.get(f"{F}/bank-accounts").json()["results"][0]["masked"].startswith("••••")
    assert priya.post(f"{F}/bank-accounts/{bank.pk}/reveal").json()["accountNumber"] == "50200012345678"
    assert AuditEvent.objects.filter(action="finance.bank.number_viewed", sensitive=True).exists()
