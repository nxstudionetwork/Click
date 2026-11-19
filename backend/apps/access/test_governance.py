"""Module 3 — Identity & Access governance: requests, packages, SoD, reviews, emergency access, analysis tools, versions,
lifecycle jobs, and the bypass attempts the spec asks to test."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.access import governance as gov
from apps.access.authz import load_context
from apps.access.models import (AccessPackage, AccessRequest, EmergencyAccess, OSAccount, Role, RoleAssignment, SoDException, SoDRule)
from apps.access.tests import os_seed, signed_in  # noqa: F401
from apps.core.api.exceptions import DomainError
from apps.users.models import User
from apps.workflows.models import ApprovalRequest

A = "/api/v1/os/access"


def acct(email):
    return OSAccount.objects.get(user__email=email)


def approve(client, req_id):
    r = client.post(f"/api/v1/os/approvals/{req_id}/approve", {"comment": "ok"}, format="json")
    assert r.status_code == 200, r.content
    return r


def test_access_request_manager_then_admin_provisions(os_seed):
    divya = signed_in("divya.patel@click.dev")
    roles = divya.get(f"{A}/requestable").json()["roles"]
    bm = next(r for r in roles if r["name"].startswith("Branch Manager"))
    r = divya.post(f"{A}/requests", {"roleId": bm["id"], "reason": "Covering the branch while Arjun is on leave next month."}, format="json")
    assert r.status_code == 201, r.content
    ar = AccessRequest.objects.get(pk=r.json()["id"])
    # requester can't approve their own request
    assert divya.post(f"/api/v1/os/approvals/{ar.approval_id}/approve", {"comment": "me"}, format="json").status_code == 403
    approve(signed_in("arjun.kumar@click.dev"), ar.approval_id)      # manager (reports scope)
    approve(signed_in("vikram.shah@click.dev"), ar.approval_id)      # access administrator
    ar.refresh_from_db()
    assert ar.status == "provisioned" and ar.assignment_ids
    assert load_context(User.objects.get(email="divya.patel@click.dev")).has("finance.expense.approve")


def test_access_request_blocked_when_no_approver_holds_it(os_seed):
    divya = signed_in("divya.patel@click.dev")
    fh = Role.objects.get(key="finance-head")
    r = divya.post(f"{A}/requests", {"roleId": str(fh.pk), "reason": "I would like to see all the finance numbers please."}, format="json")
    ar = AccessRequest.objects.get(pk=r.json()["id"])
    approve(signed_in("arjun.kumar@click.dev"), ar.approval_id)
    approve(signed_in("vikram.shah@click.dev"), ar.approval_id)
    ar.refresh_from_db()
    assert ar.status == "blocked" and "approvers" in ar.outcome_note
    assert not RoleAssignment.objects.filter(user__email="divya.patel@click.dev", role=fh).exists()


def test_reason_required_and_no_duplicates(os_seed):
    divya = signed_in("divya.patel@click.dev")
    bm = Role.objects.get(key="branch-manager")
    assert divya.post(f"{A}/requests", {"roleId": str(bm.pk), "reason": "pls"}, format="json").status_code == 400
    ok = {"roleId": str(bm.pk), "reason": "Covering the branch for two weeks in December."}
    assert divya.post(f"{A}/requests", ok, format="json").status_code == 201
    assert divya.post(f"{A}/requests", ok, format="json").status_code == 409


def test_employee_cannot_use_admin_tools_or_direct_api(os_seed):
    divya = signed_in("divya.patel@click.dev")
    karthik = acct("karthik.reddy@click.dev")
    for url in (f"{A}/who-has?code=finance.expense.approve", f"{A}/effective/{karthik.pk}", f"{A}/privileged", f"{A}/hygiene", f"{A}/sod",
                f"{A}/security", f"{A}/compare?roles=a,b"):
        assert divya.get(url).status_code == 403, url
    assert divya.post(f"{A}/simulate", {"accountId": str(karthik.pk), "code": "finance.expense.approve"}, format="json").status_code == 403
    me = divya.get(f"{A}/me")
    assert me.status_code == 200 and any(p["code"] == "access.request.create" for p in me.json()["permissions"])
    assert divya.get(f"{A}/home").json()["mode"] == "self"


def test_effective_access_simulator_and_who_has(os_seed):
    admin = signed_in("vikram.shah@click.dev")
    karthik = acct("karthik.reddy@click.dev")
    eff = admin.get(f"{A}/effective/{karthik.pk}").json()
    exp = next(p for p in eff["permissions"] if p["code"] == "finance.expense.approve")
    assert exp["scope"] == "units" and "finance-manager" in exp["sources"]
    assert {"type": "expense", "label": "Expense", "limit": "50000.00"} in eff["approvalAuthority"]
    sim = lambda amount: admin.post(f"{A}/simulate", {"accountId": str(karthik.pk), "code": "finance.expense.approve",  # noqa: E731
                                                      "approvalType": "expense", "amount": amount}, format="json").json()
    assert sim(40000)["allowed"] is True
    denied = sim(60000)
    assert denied["allowed"] is False and "limit" in denied["reasons"][-1]
    divya = acct("divya.patel@click.dev")
    assert admin.post(f"{A}/simulate", {"accountId": str(divya.pk), "code": "finance.expense.approve"}, format="json").json()["allowed"] is False
    who = {r["name"] for r in admin.get(f"{A}/who-has?code=finance.expense.approve").json()["results"]}
    assert {"Priya Menon", "Karthik Reddy"} <= who and "Divya Patel" not in who


def test_role_comparison_and_matrix(os_seed):
    admin = signed_in("vikram.shah@click.dev")
    fm, fh = Role.objects.get(key="finance-manager"), Role.objects.get(key="finance-head")
    cmp = admin.get(f"{A}/compare?roles={fm.pk},{fh.pk}").json()
    row = next(r for r in cmp["rows"] if r["code"] == "finance.expense.approve")
    assert row["values"] == ["region", "organization"] and row["differs"]
    mx = admin.get(f"{A}/matrix?module=finance").json()
    assert mx["rows"] and any(mx["rows"][0]["actions"].values())


def test_sod_exception_flow(os_seed):
    org = os_seed
    rule = SoDRule.objects.get(organization=org, key="create-and-approve-po")
    rule.severity = "exception"
    rule.save()
    divya = User.objects.get(email="divya.patel@click.dev")
    codes = ["procurement.order.create", "procurement.order.approve"]
    with pytest.raises(DomainError) as e:
        gov.check_sod(org, divya, codes)
    assert e.value.error_code == "sod_exception_required"
    with pytest.raises(DomainError):  # a reason alone is not enough: someone with SoD authority must approve
        gov.check_sod(org, divya, codes, exception_reason="small team", actor_ctx=load_context(User.objects.get(email="arjun.kumar@click.dev")))
    sec = User.objects.get(email="rahul.verma@click.dev")
    RoleAssignment.objects.create(user=sec, role=Role.objects.get(key="security-admin"))
    gov.check_sod(org, divya, codes, exception_reason="Two-person team in Hyderabad until Q2", actor_ctx=load_context(sec))
    assert SoDException.objects.filter(user=divya, rule=rule).exists()
    rule.severity = "block"
    rule.save()
    SoDException.objects.all().update(revoked_at=timezone.now())
    with pytest.raises(DomainError) as e:
        gov.check_sod(org, divya, codes, exception_reason="x", actor_ctx=load_context(sec))
    assert e.value.error_code == "sod_blocked"


def test_access_review_remove_and_self_certification_denied(os_seed):
    admin = signed_in("vikram.shah@click.dev")
    bm = Role.objects.get(key="branch-manager")
    r = admin.post(f"{A}/reviews", {"name": "Q4 branch managers", "roleIds": [str(bm.pk)]}, format="json")
    assert r.status_code == 201, r.content
    rahul = signed_in("rahul.verma@click.dev")  # Arjun's manager reviews Arjun
    items = rahul.get(f"{A}/reviews").json()["mine"]
    item = next(i for i in items if i["user"] == "Arjun Kumar")
    arjun = signed_in("arjun.kumar@click.dev")
    assert arjun.post(f"{A}/review-items/{item['id']}/decide", {"decision": "keep"}, format="json").status_code == 403
    assert rahul.post(f"{A}/review-items/{item['id']}/decide", {"decision": "remove"}, format="json").status_code == 400  # reason needed
    assert rahul.post(f"{A}/review-items/{item['id']}/decide", {"decision": "remove", "comment": "Moving to Delhi"}, format="json").status_code == 200
    assert not load_context(User.objects.get(email="arjun.kumar@click.dev")).has("procurement.request.approve")


def test_emergency_access_lifecycle(os_seed):
    rahul_u = User.objects.get(email="rahul.verma@click.dev")
    RoleAssignment.objects.create(user=rahul_u, role=Role.objects.get(key="it-admin"))  # IT can break glass; security reviews
    rahul = signed_in("rahul.verma@click.dev")
    os_admin = Role.objects.get(key="os-admin")
    assert rahul.post(f"{A}/emergency", {"roleId": str(os_admin.pk), "reason": "short", "hours": 2}, format="json").status_code == 400
    fh = Role.objects.get(key="finance-head")
    assert rahul.post(f"{A}/emergency", {"roleId": str(fh.pk), "reason": "x" * 30, "hours": 2}, format="json").status_code == 400  # not eligible
    r = rahul.post(f"{A}/emergency", {"roleId": str(os_admin.pk), "reason": "Production incident INC-42: locked out admins", "hours": 99},
                   format="json")
    assert r.status_code == 201, r.content
    ea = EmergencyAccess.objects.get(pk=r.json()["id"])
    assert ea.ends_at <= timezone.now() + timedelta(hours=gov.EMERGENCY_MAX_HOURS, minutes=1)
    assert load_context(rahul_u).has("identity.user.manage")
    assert rahul.post(f"{A}/emergency/{ea.pk}/review", {"note": "reviewing my own"}, format="json").status_code == 403
    gov.run_jobs(now=ea.ends_at + timedelta(minutes=1))
    ea.refresh_from_db()
    assert ea.status == "ended" and not load_context(rahul_u).has("identity.user.manage")
    vikram = signed_in("vikram.shah@click.dev")
    assert vikram.post(f"{A}/emergency/{ea.pk}/review", {"note": "Checked actions in audit: password resets only."}, format="json").status_code == 200


def test_temporary_access_and_account_expiry_jobs(os_seed):
    divya = User.objects.get(email="divya.patel@click.dev")
    a = RoleAssignment.objects.create(user=divya, role=Role.objects.get(key="recruiter"), valid_until=timezone.now() + timedelta(hours=1))
    assert load_context(divya).has("people.candidate.view")
    out = gov.run_jobs(now=timezone.now() + timedelta(hours=2))
    a.refresh_from_db()
    assert out["temporary_expired"] >= 1 and a.is_active is False
    acc = acct("rohit.gupta@click.dev")
    acc.expires_at = timezone.now() - timedelta(minutes=1)
    acc.save()
    gov.run_jobs()
    acc.refresh_from_db()
    assert acc.status == "expired"


def test_role_versions_record_changes(os_seed):
    admin = signed_in("vikram.shah@click.dev")
    src = Role.objects.get(key="os-admin")
    r = admin.post(f"/api/v1/os/admin/roles/{src.pk}/duplicate")
    assert r.status_code == 201, r.content
    rid = r.json()["id"]
    grants = [g for g in r.json()["grants"] if g["code"] != "audit.event.export"]
    assert admin.patch(f"/api/v1/os/admin/roles/{rid}", {"grants": grants, "changeReason": "Auditors export, not admins"},
                       format="json").status_code == 200
    v = admin.get(f"{A}/roles/{rid}/versions").json()
    assert v["current"] == 2 and ["audit.event.export", "organization"] in v["results"][0]["changes"]["removed"]
    assert v["results"][0]["reason"] == "Auditors export, not admins"


def test_package_assign_and_self_change_denied(os_seed):
    admin = signed_in("vikram.shah@click.dev")
    r = admin.post(f"{A}/packages", {"name": "Identity desk", "roleIds": [str(Role.objects.get(key="identity-admin").pk)], "maxDays": 30},
                   format="json")
    assert r.status_code == 201, r.content
    pkg = r.json()["id"]
    rohit = acct("rohit.gupta@click.dev")
    assert admin.post(f"{A}/packages/{pkg}/assign", {"accountId": str(rohit.pk)}, format="json").status_code == 201
    a = RoleAssignment.objects.get(user=rohit.user, role__key="identity-admin")
    assert a.valid_until and a.valid_until <= timezone.now() + timedelta(days=30, minutes=1)
    me = acct("vikram.shah@click.dev")
    assert admin.post(f"{A}/packages/{pkg}/assign", {"accountId": str(me.pk)}, format="json").status_code == 403
    assert AccessPackage.objects.filter(key="identity-desk").exists()


def test_home_and_governance_lists(os_seed):
    admin = signed_in("vikram.shah@click.dev")
    h = admin.get(f"{A}/home").json()
    assert h["mode"] == "admin" and h["identity"]["total"] >= 14 and "mfaCoveragePct" in h["security"]
    assert admin.get(f"{A}/privileged").json()["results"]
    hy = admin.get(f"{A}/hygiene").json()
    assert "orphaned" in hy and "unusedRoles" in hy
    nav = admin.get(f"{A}/nav").json()["sections"]
    assert any(s["key"] == "governance" for s in nav)
    assert not ApprovalRequest.objects.filter(policy__key="access.request").exists()
