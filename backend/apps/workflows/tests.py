"""Approval engine: scope, limits, levels, segregation of duties, delegation, history, notifications; tasks."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.access.tests import login, os_seed, signed_in  # noqa: F401  (fixture re-export)
from apps.users.models import User
from apps.workflows.engine import escalate_overdue
from apps.workflows.models import ApprovalRequest, ApprovalStep, Task
from apps.workspace.models import WorkNotification


def _req(title):
    return ApprovalRequest.objects.get(title=title)


def test_inbox_respects_scope_and_limit(os_seed):
    karthik = signed_in("karthik.reddy@click.dev")
    titles = {r["title"] for r in karthik.get("/api/v1/os/approvals").json()["results"]}
    assert titles == {"Client visit travel — Hyderabad"}  # Delhi is outside his region, ₹68,000 is above his limit
    priya = signed_in("priya.menon@click.dev")
    assert len(priya.get("/api/v1/os/approvals").json()["results"]) == 3
    # Restricted records are a plain 404, never a 403 that confirms they exist
    assert karthik.get(f"/api/v1/os/approvals/{_req('Delhi branch printer replacement').pk}").status_code == 404


def test_approve_flow_notifies_and_audits(os_seed):
    req = _req("Client visit travel — Hyderabad")
    karthik = signed_in("karthik.reddy@click.dev")
    r = karthik.post(f"/api/v1/os/approvals/{req.pk}/approve", {"comment": "OK"}, format="json")
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert WorkNotification.objects.filter(recipient__email="divya.patel@click.dev", type="approval_result").exists()
    assert karthik.post(f"/api/v1/os/approvals/{req.pk}/approve", format="json").status_code in (403, 409)
    from apps.audit.models import AuditEvent

    assert AuditEvent.objects.filter(action="approval.approved", resource_id=str(req.pk)).exists()


def test_two_levels_above_threshold(os_seed):
    req = _req("Partner meet-up venue booking")
    assert req.steps.count() == 2
    priya = signed_in("priya.menon@click.dev")
    assert priya.post(f"/api/v1/os/approvals/{req.pk}/approve", format="json").json()["status"] == "pending"
    assert priya.post(f"/api/v1/os/approvals/{req.pk}/approve", format="json").json()["status"] == "approved"


def test_reject_needs_reason_and_requester_cannot_approve(os_seed):
    req = _req("Client visit travel — Hyderabad")
    divya = signed_in("divya.patel@click.dev")
    r = divya.post(f"/api/v1/os/approvals/{req.pk}/approve", format="json")
    assert r.status_code == 403
    arjun = signed_in("arjun.kumar@click.dev")
    assert arjun.post(f"/api/v1/os/approvals/{req.pk}/reject", format="json").json()["error"]["code"] == "reason_required"
    r = arjun.post(f"/api/v1/os/approvals/{req.pk}/reject", {"comment": "Use the travel desk"}, format="json")
    assert r.json()["status"] == "rejected" and any(h["kind"] == "rejected" for h in r.json()["history"])


def test_submit_creates_request_and_requester_can_cancel(os_seed):
    divya = signed_in("divya.patel@click.dev")
    keys = {p["key"] for p in divya.get("/api/v1/os/approvals/policies").json()["results"]}
    assert "finance.expense" in keys
    r = divya.post("/api/v1/os/approvals", {"policyKey": "finance.expense", "title": "Taxi to warehouse", "amount": "850"}, format="json")
    assert r.status_code == 201, r.content
    assert divya.post(f"/api/v1/os/approvals/{r.json()['id']}/cancel", format="json").json()["status"] == "cancelled"
    r = divya.post("/api/v1/os/approvals", {"policyKey": "finance.expense", "title": "No amount"}, format="json")
    assert r.json()["error"]["code"] == "amount_required"


def test_delegation_lets_a_colleague_decide(os_seed):
    karthik = signed_in("karthik.reddy@click.dev")
    rohit_user = User.objects.get(email="rohit.gupta@click.dev")
    r = karthik.post("/api/v1/os/approvals/delegations", {"delegateId": str(rohit_user.pk),
                                                          "endsAt": (timezone.now() + timedelta(days=3)).isoformat()}, format="json")
    assert r.status_code == 201, r.content
    rohit = signed_in("rohit.gupta@click.dev")
    inbox = rohit.get("/api/v1/os/approvals").json()["results"]
    assert [i["title"] for i in inbox] == ["Client visit travel — Hyderabad"]
    r = rohit.post(f"/api/v1/os/approvals/{inbox[0]['id']}/approve", format="json")
    assert r.json()["status"] == "approved"
    assert r.json()["steps"][0]["onBehalfOf"]["fullName"] == "Karthik Reddy"


def test_escalation_marks_overdue_steps(os_seed):
    ApprovalStep.objects.filter(status="pending").update(due_at=timezone.now() - timedelta(hours=1))
    assert escalate_overdue() >= 3
    assert WorkNotification.objects.filter(type="deadline", priority="critical").exists()
    assert escalate_overdue() == 0


def test_tasks_assignment_needs_permission(os_seed):
    divya = signed_in("divya.patel@click.dev")
    arjun_user = User.objects.get(email="arjun.kumar@click.dev")
    r = divya.post("/api/v1/os/tasks", {"title": "Do my thing", "assigneeId": str(arjun_user.pk)}, format="json")
    assert r.status_code == 403
    arjun = signed_in("arjun.kumar@click.dev")
    divya_user = User.objects.get(email="divya.patel@click.dev")
    r = arjun.post("/api/v1/os/tasks", {"title": "Stock count", "assigneeId": str(divya_user.pk), "priority": "high"}, format="json")
    assert r.status_code == 201
    assert WorkNotification.objects.filter(recipient=divya_user, type="task_assigned").exists()
    t = Task.objects.get(title="Stock count")
    assert divya.patch(f"/api/v1/os/tasks/{t.pk}", {"status": "done"}, format="json").json()["status"] == "done"
    rohit = signed_in("rohit.gupta@click.dev")
    assert rohit.patch(f"/api/v1/os/tasks/{t.pk}", {"status": "open"}, format="json").status_code == 404
    _ = pytest
