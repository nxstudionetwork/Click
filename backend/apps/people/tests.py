"""People & HR: IDs, directory vs record, People 360 privacy, self-service limits, manager scope, leave, attendance,
recruitment → hire → onboarding, promotion, offboarding → access revocation, documents, cases, surveys, import, AI."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.access.models import OSAccount
from apps.access.tests import os_seed, signed_in  # noqa: F401
from apps.people import models as m
from apps.users.models import User
from apps.workflows.models import ApprovalRequest, Task

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


def emp(email):
    return m.Employee.objects.get(work_email=email)


def next_weekday(n=7):
    d = timezone.localdate() + timedelta(days=n)
    while d.isoweekday() > 5:
        d += timedelta(days=1)
    return d


def test_os_ids_are_their_own_namespace(os_seed):
    ids = list(m.Employee.objects.values_list("employee_id", flat=True))
    assert ids and all(i.startswith("EMP-") for i in ids)  # never the apps' CL-CU- / CLK-PT- / CLK- namespaces
    e = m.Employee.objects.create(organization=os_seed, full_name="New Person")
    assert e.employee_id.startswith("EMP-") and e.employee_id > max(i for i in ids if i != e.employee_id)
    p = m.Position.objects.first()
    assert p.code.startswith("POS-") and m.Candidate.objects.first().code.startswith("CAN-")


def test_directory_vs_employee_record_and_export(os_seed):
    divya = signed_in("divya.patel@click.dev")
    r = divya.get("/api/v1/os/people/employees").json()
    assert r["fullRecord"] is False and "joinedOn" not in r["results"][0] and "employmentType" not in r["results"][0]
    assert divya.get("/api/v1/os/people/employees", {"export": "csv"}).status_code == 403
    hr = signed_in("sneha.iyer@click.dev")
    r = hr.get("/api/v1/os/people/employees", {"q": "divya"}).json()
    assert r["fullRecord"] and r["results"][0]["joinedOn"]
    csv_resp = hr.get("/api/v1/os/people/employees", {"export": "csv"})
    assert csv_resp.status_code == 200 and b"Employee ID" in csv_resp.content and b"date_of_birth" not in csv_resp.content.lower()


def test_people_360_tabs_follow_permissions(os_seed):
    arjun_rec = emp("arjun.kumar@click.dev")
    divya = signed_in("divya.patel@click.dev")
    d = divya.get(f"/api/v1/os/people/employees/{arjun_rec.pk}").json()
    assert d["tabs"] == ["overview"] and d["fullRecord"] is False
    for tab in ("employment", "contact", "compensation", "leave", "performance"):
        assert divya.get(f"/api/v1/os/people/employees/{arjun_rec.pk}/{tab}").status_code == 403, tab
    me = divya.get(f"/api/v1/os/people/employees/{emp('divya.patel@click.dev').pk}").json()
    assert {"employment", "contact", "leave", "attendance", "performance", "learning", "documents"} <= set(me["tabs"])
    assert "compensation" not in me["tabs"]  # pay is never self-served without the payroll permission
    # Manager sees reports' leave and attendance, not their pay or private contact details
    arjun = signed_in("arjun.kumar@click.dev")
    dv = emp("divya.patel@click.dev")
    t = arjun.get(f"/api/v1/os/people/employees/{dv.pk}").json()["tabs"]
    assert {"leave", "attendance", "performance"} <= set(t) and not {"compensation", "contact"} & set(t)


def test_compensation_needs_mfa_when_enforced(os_seed, settings):
    settings.CLICK_OS_SENSITIVE_REQUIRES_MFA = True
    hr = signed_in("sneha.iyer@click.dev")
    r = hr.get(f"/api/v1/os/people/employees/{emp('divya.patel@click.dev').pk}/compensation")
    assert r.status_code == 403 and r.json()["error"]["code"] == "mfa_required"


def test_self_service_cannot_change_protected_fields(os_seed):
    me = emp("divya.patel@click.dev")
    c = signed_in("divya.patel@click.dev")
    r = c.patch(f"/api/v1/os/people/employees/{me.pk}", {"departmentId": str(m.Employee.objects.get(work_email="priya.menon@click.dev").department_id)}, format="json")
    assert r.status_code == 403 and r.json()["error"]["code"] == "protected_fields"
    assert c.patch(f"/api/v1/os/people/employees/{me.pk}", {"preferredName": "Divs"}, format="json").json()["preferredName"] == "Divs"
    assert c.patch(f"/api/v1/os/people/employees/{me.pk}/contact", {"personalPhone": "+919000000001"}, format="json").status_code == 200


def test_scope_hr_business_partner_region(os_seed):
    imran = signed_in("imran.sheikh@click.dev")  # HR BP anchored in Hyderabad → South region
    names = {e["fullName"] for e in imran.get("/api/v1/os/people/employees").json()["results"]}
    assert "Divya Patel" in names and "Rohit Gupta" not in names  # Delhi is another region
    rohit = emp("rohit.gupta@click.dev")
    assert imran.get(f"/api/v1/os/people/employees/{rohit.pk}/employment").status_code == 403


def test_leave_manager_approval_and_balance(os_seed):
    lk = emp("lakshmi.rao@click.dev")
    lr = m.LeaveRequest.objects.get(employee=lk)  # seeded: 2 days annual leave
    bal = m.LeaveBalance.objects.get(employee=lk, leave_type=lr.leave_type, year=lr.start_date.year)
    assert bal.pending == lr.days
    arjun = signed_in("arjun.kumar@click.dev")  # her manager (implicit people-manager role)
    inbox = arjun.get("/api/v1/os/approvals").json()["results"]
    item = next(i for i in inbox if i["policy"]["key"] == "people.leave")
    assert item["amountUnit"] == "days"
    rohit = signed_in("rohit.gupta@click.dev")
    assert rohit.get(f"/api/v1/os/approvals/{item['id']}").status_code == 404
    assert arjun.post(f"/api/v1/os/approvals/{item['id']}/approve", format="json").json()["status"] == "approved"
    bal.refresh_from_db()
    lr.refresh_from_db()
    assert lr.status == "approved" and bal.used == lr.days and bal.pending == 0


def test_leave_rules_holidays_overlap_balance_and_hr_level(os_seed):
    c = signed_in("divya.patel@click.dev")
    me = emp("divya.patel@click.dev")
    al = m.LeaveType.objects.get(code="AL")
    mon = next_weekday(14)
    while mon.isoweekday() != 1:
        mon += timedelta(days=1)
    cal = m.HolidayCalendar.objects.get(name="Click corporate holidays")
    m.Holiday.objects.create(calendar=cal, date=mon, name="Test holiday")
    pv = c.get("/api/v1/os/people/leave/preview", {"start": mon.isoformat(), "end": (mon + timedelta(days=1)).isoformat()}).json()
    assert pv["days"] == "1"  # the holiday doesn't count
    r = c.post("/api/v1/os/people/leave/requests", {"leaveTypeId": str(al.pk), "startDate": (mon + timedelta(days=1)).isoformat(),
                                                    "endDate": (mon + timedelta(days=1)).isoformat()}, format="json")
    assert r.status_code == 201
    r = c.post("/api/v1/os/people/leave/requests", {"leaveTypeId": str(al.pk), "startDate": mon.isoformat(),
                                                    "endDate": (mon + timedelta(days=2)).isoformat()}, format="json")
    assert r.json()["error"]["code"] == "leave_overlap"
    sl = m.LeaveType.objects.get(code="SL")
    far = timezone.localdate().replace(year=timezone.localdate().year + 1, month=3, day=2)  # inside one year
    r = c.post("/api/v1/os/people/leave/requests", {"leaveTypeId": str(sl.pk), "startDate": far.isoformat(), "endDate": (far + timedelta(days=20)).isoformat()}, format="json")
    assert r.json()["error"]["code"] == "insufficient_balance"
    long_start = far + timedelta(days=60)
    r = c.post("/api/v1/os/people/leave/requests", {"leaveTypeId": str(al.pk), "startDate": long_start.isoformat(),
                                                    "endDate": (long_start + timedelta(days=9)).isoformat()}, format="json")
    apr = ApprovalRequest.objects.get(pk=r.json()["approvalId"])
    assert apr.steps.count() == 2  # 6+ days also needs HR
    assert c.post(f"/api/v1/os/people/leave/requests/{r.json()['id']}/cancel").json()["status"] == "cancelled"
    assert m.LeaveBalance.objects.get(employee=me, leave_type=al, year=long_start.year).pending == 0  # cancelled request released
    assert m.LeaveBalance.objects.get(employee=me, leave_type=al, year=(mon + timedelta(days=1)).year).pending == Decimal("1")


def test_attendance_check_in_out_and_correction(os_seed):
    c = signed_in("rohit.gupta@click.dev")
    assert c.post("/api/v1/os/people/attendance/check-in", {"mode": "remote"}, format="json").status_code == 200
    assert c.post("/api/v1/os/people/attendance/check-in", format="json").json()["error"]["code"] == "already_checked_in"
    assert c.post("/api/v1/os/people/attendance/check-out", format="json").json()["checkOut"]
    y = timezone.localdate() - timedelta(days=1)
    r = c.post("/api/v1/os/people/attendance/corrections", {"date": y.isoformat(), "checkIn": "09:30", "checkOut": "18:30", "reason": "Forgot to check in"}, format="json")
    assert r.status_code == 201
    rahul = signed_in("rahul.verma@click.dev")  # Rohit's manager
    assert rahul.post(f"/api/v1/os/approvals/{r.json()['approvalId']}/approve", format="json").json()["status"] == "approved"
    rec = m.AttendanceRecord.objects.get(employee=emp("rohit.gupta@click.dev"), date=y)
    assert rec.source == "correction" and rec.check_in and rec.check_out


def test_recruitment_offer_hire_onboarding_and_access(os_seed):
    neha, sneha = signed_in("neha.joshi@click.dev"), signed_in("sneha.iyer@click.dev")
    opening = m.JobOpening.objects.first()
    pipe = neha.get(f"/api/v1/os/people/openings/{opening.pk}/pipeline").json()
    app = next(a for col in pipe["columns"] for a in col["items"] if col["stage"] == "interview")
    assert neha.post(f"/api/v1/os/people/applications/{app['id']}/move", {"stage": "rejected"}, format="json").json()["error"]["code"] == "reason_required"
    assert neha.post(f"/api/v1/os/people/applications/{app['id']}/move", {"stage": "selected"}, format="json").json()["stage"] == "selected"
    r = neha.post("/api/v1/os/people/offers", {"applicationId": app["id"], "joiningDate": (timezone.localdate() + timedelta(days=20)).isoformat(),
                                               "baseAnnual": "1200000", "submit": True}, format="json")
    assert r.status_code == 201, r.content
    offer = m.Offer.objects.get(pk=r.json()["id"])
    assert offer.status == "pending_approval"
    assert sneha.post(f"/api/v1/os/approvals/{offer.approval_id}/approve", format="json").json()["status"] == "approved"
    assert neha.post(f"/api/v1/os/people/offers/{offer.pk}/release").json()["status"] == "released"
    r = neha.post(f"/api/v1/os/people/offers/{offer.pk}/respond", {"response": "accepted", "workEmail": "aditya.varma@click.dev"}, format="json")
    new = m.Employee.objects.get(pk=r.json()["employeeId"])
    assert new.status == "pre_onboarding" and new.employee_id.startswith("EMP-") and new.position_id == opening.position_id
    assert new.compensation.get().base_annual == Decimal("1200000")
    assert Task.objects.filter(source_type="people.onboarding").count() >= 5
    acct = OSAccount.objects.get(user=new.user)
    assert acct.status == "invited" and not new.user.role_assignments.exists()  # access is provisioned, never granted silently


def test_promotion_applies_and_triggers_access_review(os_seed):
    sneha, imran = signed_in("sneha.iyer@click.dev"), signed_in("imran.sheikh@click.dev")
    dv = emp("divya.patel@click.dev")
    mgr = m.Designation.objects.get(code="MGR")
    r = sneha.post("/api/v1/os/people/changes", {"employeeId": str(dv.pk), "kind": "promotion", "designation_id": str(mgr.pk),
                                                 "effectiveDate": timezone.localdate().isoformat(), "reason": "Strong year"}, format="json")
    assert r.status_code == 201, r.content
    assert sneha.post(f"/api/v1/os/approvals/{r.json()['approvalId']}/approve", format="json").status_code == 403  # segregation of duties
    assert imran.post(f"/api/v1/os/approvals/{r.json()['approvalId']}/approve", format="json").json()["status"] == "approved"
    dv.refresh_from_db()
    assert dv.designation_id == mgr.pk and dv.events.filter(kind="promoted").exists()
    assert Task.objects.filter(source_type="people.access_review", source_id=str(dv.pk)).exists()


def test_offer_above_hiring_limit_cannot_be_approved(os_seed):
    neha, sneha = signed_in("neha.joshi@click.dev"), signed_in("sneha.iyer@click.dev")
    app = m.Application.objects.filter(stage="shortlisted").first()
    r = neha.post("/api/v1/os/people/offers", {"applicationId": str(app.pk), "joiningDate": (timezone.localdate() + timedelta(days=20)).isoformat(),
                                               "baseAnnual": "2200000", "submit": True}, format="json")
    offer = m.Offer.objects.get(pk=r.json()["id"])
    assert sneha.post(f"/api/v1/os/approvals/{offer.approval_id}/approve", format="json").status_code == 403  # ₹22L > HR's ₹15L hiring limit
    assert signed_in("ananya.rao@click.dev").post(f"/api/v1/os/approvals/{offer.approval_id}/approve", format="json").json()["status"] == "approved"


def test_resignation_offboarding_revokes_access(os_seed):
    divya = signed_in("divya.patel@click.dev")
    last = timezone.localdate() + timedelta(days=30)
    r = divya.post("/api/v1/os/people/offboarding", {"kind": "resignation", "lastWorkingDay": last.isoformat(), "reason": "Moving cities"}, format="json")
    assert r.status_code == 201, r.content
    case = m.OffboardingCase.objects.get(pk=r.json()["id"])
    imran, sneha = signed_in("imran.sheikh@click.dev"), signed_in("sneha.iyer@click.dev")
    assert imran.post(f"/api/v1/os/approvals/{case.approval_id}/approve", format="json").json()["status"] == "approved"
    case.refresh_from_db()
    assert case.status == "in_progress" and emp("divya.patel@click.dev").status == "notice"
    assert Task.objects.filter(source_type="people.offboarding").exists()
    # Exit interview answers are HR-only
    sneha.patch(f"/api/v1/os/people/offboarding/{case.pk}", {"exitFeedback": "Great team", "rehireEligible": True}, format="json")
    assert "exitFeedback" not in divya.get(f"/api/v1/os/people/offboarding/{case.pk}").json()
    assert sneha.post(f"/api/v1/os/people/offboarding/{case.pk}/complete").status_code == 200
    e = emp("divya.patel@click.dev")
    assert e.status == "resigned" and e.exit_date == last
    assert OSAccount.objects.get(user=e.user).status == "deactivated"
    assert divya.get("/api/v1/os/me/context").status_code == 401  # sessions ended immediately
    assert not e.user.role_assignments.filter(is_active=True).exists()


def test_employee_documents_privacy(os_seed):
    dv = emp("divya.patel@click.dev")
    divya = signed_in("divya.patel@click.dev")
    up = lambda c, sens, title: c.post("/api/v1/os/documents", {"resource_type": "people.employee", "resource_id": str(dv.pk), "title": title,  # noqa: E731
                                                                   "category": "id", "sensitivity": sens, "file": SimpleUploadedFile("a.pdf", PDF)}, format="multipart")
    assert up(divya, "confidential", "Address proof").status_code == 201
    assert up(divya, "restricted", "PAN card").status_code == 201
    bad = divya.post("/api/v1/os/documents", {"resource_type": "people.employee", "resource_id": str(dv.pk), "title": "x",
                                              "file": SimpleUploadedFile("a.pdf", b"MZ\x90\x00not a pdf")}, format="multipart")
    assert bad.json()["error"]["code"] == "file_type"
    q = {"resource_type": "people.employee", "resource_id": str(dv.pk)}
    assert len(divya.get("/api/v1/os/documents", q).json()["results"]) == 2
    arjun = signed_in("arjun.kumar@click.dev")  # manager: confidential yes, restricted no
    assert {d["title"] for d in arjun.get("/api/v1/os/documents", q).json()["results"]} == {"Address proof"}
    assert signed_in("rohit.gupta@click.dev").get("/api/v1/os/documents", q).status_code == 404
    hr = signed_in("sneha.iyer@click.dev")
    docs = hr.get("/api/v1/os/documents", q).json()["results"]
    pan = next(d for d in docs if d["title"] == "PAN card")
    assert hr.get(f"/api/v1/os/documents/{pan['id']}/download").status_code == 200
    from apps.audit.models import AuditEvent

    assert AuditEvent.objects.filter(action="documents.download", resource_id=pan["id"], sensitive=True).exists()
    assert divya.post(f"/api/v1/os/documents/{pan['id']}/verify").status_code == 403  # nobody verifies their own documents


def test_hr_cases_are_strictly_restricted(os_seed):
    sneha = signed_in("sneha.iyer@click.dev")
    dv = emp("divya.patel@click.dev")
    r = sneha.post("/api/v1/os/people/cases", {"employee": str(dv.pk), "kind": "grievance", "summary": "Shift allocation concern"}, format="json")
    assert r.status_code == 201 and r.json()["code"].startswith("HRC-")
    for who in ("arjun.kumar@click.dev", "divya.patel@click.dev", "imran.sheikh@click.dev"):
        c = signed_in(who)
        assert c.get("/api/v1/os/people/cases").status_code == 403, who
        assert c.get(f"/api/v1/os/people/cases/{r.json()['id']}").status_code == 403, who
    assert sneha.delete(f"/api/v1/os/people/cases/{r.json()['id']}").status_code == 405


def test_hr_request_desk(os_seed):
    divya = signed_in("divya.patel@click.dev")
    r = divya.post("/api/v1/os/people/requests", {"category": "employment_letter", "subject": "Employment letter for visa"}, format="json")
    assert r.status_code == 201 and r.json()["code"].startswith("HRQ-")
    sneha = signed_in("sneha.iyer@click.dev")
    assert any(x["id"] == r.json()["id"] for x in sneha.get("/api/v1/os/people/requests", {"view": "queue"}).json()["results"])
    sneha.post(f"/api/v1/os/people/requests/{r.json()['id']}/comments", {"body": "Check visa template", "internal": True}, format="json")
    assert not divya.get(f"/api/v1/os/people/requests/{r.json()['id']}").json()["comments"]  # internal HR notes stay internal
    assert divya.patch(f"/api/v1/os/people/requests/{r.json()['id']}", {"status": "resolved"}, format="json").status_code == 403


def test_anonymous_survey(os_seed):
    sneha = signed_in("sneha.iyer@click.dev")
    s = sneha.post("/api/v1/os/people/surveys", {"title": "Pulse", "questions": [{"text": "How are you?", "type": "scale"}],
                                                 "anonymous": True, "opensOn": timezone.localdate().isoformat(), "status": "open"}, format="json").json()
    for who in ("divya.patel@click.dev", "rohit.gupta@click.dev"):
        c = signed_in(who)
        assert c.post(f"/api/v1/os/people/surveys/{s['id']}/respond", {"answers": {"q1": 4}}, format="json").status_code == 201
    again = signed_in("divya.patel@click.dev").post(f"/api/v1/os/people/surveys/{s['id']}/respond", {"answers": {"q1": 5}}, format="json")
    assert again.json()["error"]["code"] == "already_answered"
    assert not m.SurveyResponse.objects.filter(survey_id=s["id"], respondent__isnull=False).exists()
    assert sneha.get(f"/api/v1/os/people/surveys/{s['id']}/results").json()["suppressed"] is True  # fewer than 3 answers


def test_import_preview_commit_and_no_silent_overwrite(os_seed):
    sneha = signed_in("sneha.iyer@click.dev")
    csv_data = ("employee_id,full_name,department_code,location_code,manager_employee_id\n"
                ",Asha Kiran,OPS,HYD-BR,EMP-000008\nEMP-000009,Divya Override,OPS,HYD-BR,\n,Bad Dept,NOPE,HYD-BR,\n")
    f = lambda: SimpleUploadedFile("e.csv", csv_data.encode())  # noqa: E731
    pv = sneha.post("/api/v1/os/people/employees/import", {"file": f(), "mode": "preview"}, format="multipart").json()
    assert pv["errors"] == 2 and {r["action"] for r in pv["rows"]} == {"create", "error"}
    r = sneha.post("/api/v1/os/people/employees/import", {"file": f(), "mode": "commit"}, format="multipart")
    assert r.json()["error"]["code"] == "import_invalid" and not m.Employee.objects.filter(full_name="Asha Kiran").exists()
    ok = sneha.post("/api/v1/os/people/employees/import", {"file": SimpleUploadedFile("e.csv", b"full_name,department_code,manager_employee_id\nAsha Kiran,OPS,EMP-000008\n"),
                                                          "mode": "commit"}, format="multipart")
    assert ok.status_code == 201 and m.Employee.objects.get(full_name="Asha Kiran").manager.full_name == "Arjun Kumar"
    assert signed_in("divya.patel@click.dev").post("/api/v1/os/people/employees/import", {"file": f()}, format="multipart").status_code == 403


def test_hr_home_widgets_and_ai_tools(os_seed):
    sneha = signed_in("sneha.iyer@click.dev")
    home = sneha.get("/api/v1/os/home").json()
    assert {"people_overview", "probation_ending", "document_expiries"} <= {w["key"] for w in home["layout"]}
    pe = sneha.get("/api/v1/os/home/widgets/probation_ending").json()["data"]
    assert any(i["fullName"] == "Lakshmi Rao" for i in pe["items"])
    hr_home = sneha.get("/api/v1/os/people/home").json()
    assert hr_home["mode"] == "hr" and any(x["key"] == "attrition" for x in hr_home["metrics"])
    assert any(b["name"] == "Divya Patel" for b in hr_home["celebrations"]["birthdays"])  # she chose to share it
    ans = sneha.post("/api/v1/os/ai", {"question": "How many employees are in each department?"}, format="json").json()
    assert ans["tool"] == "hr_headcount" and "Operations" in ans["answer"]
    emp_ans = signed_in("divya.patel@click.dev").post("/api/v1/os/ai", {"question": "How many employees are in Technology?"}, format="json").json()
    assert emp_ans.get("denied") is True
    assert signed_in("divya.patel@click.dev").get("/api/v1/os/people/home").json()["mode"] == "self"


def test_performance_cycle_reviews(os_seed):
    divya = signed_in("divya.patel@click.dev")
    mine = divya.get("/api/v1/os/people/reviews/mine").json()["results"]
    self_rev = next(r for r in mine if r["kind"] == "self")
    assert divya.patch(f"/api/v1/os/people/reviews/{self_rev['id']}", {"submit": True}, format="json").json()["error"]["code"] == "validation_error"
    r = divya.patch(f"/api/v1/os/people/reviews/{self_rev['id']}", {"rating": 4, "strengths": "Ownership", "submit": True}, format="json").json()
    assert r["status"] == "submitted"
    goals = divya.get("/api/v1/os/people/goals").json()["results"]
    assert any(g["level"] == "company" for g in goals) and any(g["level"] == "employee" and g["parent"] for g in goals)
    rohit = signed_in("rohit.gupta@click.dev")
    assert not any(g["level"] == "employee" for g in rohit.get("/api/v1/os/people/goals").json()["results"])


@pytest.mark.parametrize("url", ["/api/v1/os/people/compensation", "/api/v1/os/people/payroll/inputs", "/api/v1/os/people/analytics",
                                 "/api/v1/os/people/cases", "/api/v1/os/people/settings/leave-types"])
def test_employee_cannot_reach_hr_admin_apis(os_seed, url):
    assert signed_in("divya.patel@click.dev").get(url).status_code == 403
