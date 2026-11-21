"""People & HR API, part 1: HR home, module navigation, directory, People 360, org chart, self-service, import, analytics."""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Avg, Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.access.api import OSView
from apps.access.crud import ScopedDetail, ScopedList
from apps.audit.services import record
from apps.core.api.exceptions import DomainError
from apps.core.api.pagination import DefaultPagination
from apps.organization.models import Department, OrgUnit, Team

from . import models as m
from . import serializers as s
from .services import (attendance_exceptions, balance, can_on, eligible_types, employees_q, is_self, on_leave_today, plan_progress,
                       target)

SECTIONS = [
    ("people", "People", [("directory", "Employee directory", "/people/directory", "people.directory.view"),
                          ("org_chart", "Org chart", "/people/org-chart", "people.directory.view")]),
    ("talent", "Talent", [("recruitment", "Recruitment", "/people/recruitment", "people.recruitment.view"),
                          ("candidates", "Candidates", "/people/candidates", "people.candidate.view"),
                          ("positions", "Positions & workforce", "/people/positions", "people.position.view"),
                          ("interviews", "My interviews", "/people/interviews", None),
                          ("onboarding", "Onboarding", "/people/onboarding", "people.onboarding.view")]),
    ("workforce", "Workforce", [("attendance", "Attendance", "/people/attendance", "people.attendance.create|people.attendance.view"),
                                ("leave", "Leave & holidays", "/people/leave", "people.leave.create|people.leave.view")]),
    ("performance", "Performance", [("performance", "Goals & reviews", "/people/performance", None),
                                    ("feedback", "Feedback & recognition", "/people/engagement?tab=recognition", None)]),
    ("learning", "Learning", [("learning", "Learning & skills", "/people/learning", None)]),
    ("compensation", "Compensation & benefits", [("compensation", "Compensation & payroll", "/people/compensation", "people.payroll.view"),
                                                 ("benefits", "Benefits", "/people/compensation?tab=benefits", "people.benefit.view")]),
    ("experience", "Employee experience", [("me", "My HR", "/people/me", None), ("requests", "HR requests", "/people/requests", None),
                                           ("engagement", "Surveys & engagement", "/people/engagement", None)]),
    ("lifecycle", "Employee lifecycle", [("lifecycle", "Promotions, transfers & exits", "/people/lifecycle", "people.lifecycle.view|people.offboarding.view"),
                                         ("cases", "Employee relations", "/people/cases", "people.case.view")]),
    ("analytics", "Analytics", [("analytics", "HR analytics", "/people/analytics", "people.analytics.view")]),
    ("admin", "Administration", [("settings", "HR settings", "/people/settings", "people.settings.view|people.settings.configure")]),
]


def _allowed(ctx, perm: str | None) -> bool:
    return perm is None or any(ctx.has(p) for p in perm.split("|"))


class NavView(OSView):
    def get(self, request):
        ctx = self.authz
        out = []
        for key, label, items in SECTIONS:
            vis = [{"key": k, "label": lbl, "path": path} for k, lbl, path, perm in items if _allowed(ctx, perm) and (ctx.employee or perm)]
            if vis:
                out.append({"key": key, "label": label, "items": vis})
        return Response({"sections": out, "has_employee_record": ctx.employee is not None, "is_manager": ctx.is_manager})


def _emp_or_404(ctx, pk, code="people.directory.view") -> m.Employee:
    e = m.Employee.objects.filter(organization=ctx.organization, pk=pk).select_related(
        "designation", "department", "team", "org_unit", "manager", "job_level", "user", "schedule", "position").first()
    if e is None or not (is_self(ctx, e) or can_on(ctx, code, e)):
        raise DomainError("Not found.", code="not_found", status_code=404)
    return e


# --- HR home ----------------------------------------------------------------------------------------------
class HomeView(OSView):
    def get(self, request):
        ctx = self.authz
        if not (ctx.has("people.employee.view") or ctx.has("people.recruitment.view")):
            return Response({"mode": "self", "message": "Your HR workspace is in My HR."})
        from apps.workflows.selectors import inbox_for

        today = timezone.localdate()
        emps = m.Employee.objects.filter(organization=ctx.organization).filter(employees_q(ctx, "people.employee.view"))
        working = emps.filter(status__in=m.Employee.WORKING)
        ids = list(working.values_list("pk", flat=True))
        yr = today - timedelta(days=365)
        leavers = emps.filter(status__in=m.Employee.EXITED, exit_date__gte=yr).count()
        avg_head = max(1, working.count())
        openings = m.JobOpening.objects.filter(organization=ctx.organization, status="open")
        pipeline = dict(m.Application.objects.filter(opening__in=openings).exclude(stage__in=["rejected", "withdrawn"]).values_list("stage").annotate(n=Count("id")))
        hr_inbox = [r for r in inbox_for(ctx) if r.policy.module == "people"]
        birthdays, anniversaries = [], []
        if ctx.has("people.directory.view"):
            for pv in m.EmployeePrivate.objects.filter(employee__in=working, share_birthday=True, date_of_birth__isnull=False).select_related("employee"):
                d = pv.date_of_birth.replace(year=today.year) if not (pv.date_of_birth.month == 2 and pv.date_of_birth.day == 29) else date(today.year, 3, 1)
                if 0 <= (d - today).days <= 7:
                    birthdays.append({"id": str(pv.employee_id), "name": pv.employee.display_name, "on": d})
            for e in working.filter(joined_on__isnull=False, joined_on__lt=today - timedelta(days=300)):
                try:
                    d = e.joined_on.replace(year=today.year)
                except ValueError:
                    continue
                if 0 <= (d - today).days <= 7:
                    anniversaries.append({"id": str(e.pk), "name": e.display_name, "on": d, "years": today.year - e.joined_on.year})
        exc = attendance_exceptions(ctx.organization, emps.filter(employees_q(ctx, "people.attendance.view")) if ctx.has("people.attendance.view") else emps.none(),
                                    today - timedelta(days=1))
        from apps.documents.models import Document

        exp_docs = Document.objects.filter(organization=ctx.organization, resource_type="people.employee", resource_id__in=[str(i) for i in ids],
                                           status="active", expires_on__isnull=False, expires_on__lte=today + timedelta(days=30)).count() \
            if ctx.has("people.document.view") else None
        return Response({
            "mode": "hr", "scope": ctx.scope("people.employee.view").level,
            "metrics": [
                {"key": "total", "label": "Total employees", "value": emps.exclude(status__in=m.Employee.EXITED).count(), "path": "/people/directory"},
                {"key": "active", "label": "Active", "value": working.count(), "path": "/people/directory?status=working"},
                {"key": "joiners", "label": "New joiners · 30d", "value": emps.filter(joined_on__gte=today - timedelta(days=30), joined_on__lte=today).count(),
                 "path": "/people/directory?joined=30"},
                {"key": "on_leave", "label": "On leave today", "value": len(on_leave_today(ctx.organization, ids)), "path": "/people/leave?tab=team"},
                {"key": "open_positions", "label": "Open positions", "value": sum(o.openings for o in openings), "path": "/people/recruitment"},
                {"key": "candidates", "label": "Active candidates", "value": sum(pipeline.values()), "path": "/people/recruitment"},
                {"key": "hr_approvals", "label": "HR approvals waiting on you", "value": len(hr_inbox), "path": "/approvals"},
                {"key": "reviews", "label": "Reviews due", "value": m.Review.objects.filter(employee__in=working, status="pending", cycle__status="active").count(),
                 "path": "/people/performance"},
                *([{"key": "expiring_docs", "label": "Documents expiring · 30d", "value": exp_docs, "path": "/people/directory"}] if exp_docs is not None else []),
                {"key": "attendance_exceptions", "label": "Attendance exceptions (yesterday)", "value": len(exc), "path": "/people/attendance?tab=exceptions"},
                {"key": "probation", "label": "Probation ending · 30d",
                 "value": working.filter(status="probation", probation_end_on__lte=today + timedelta(days=30)).count(), "path": "/people/lifecycle"},
                {"key": "attrition", "label": "Attrition · 12 months", "value": f"{round(leavers / avg_head * 100, 1)}%", "format": "text",
                 "path": "/people/analytics"},
            ],
            "pipeline": [{"stage": st, "label": m.Application.Stage(st).label, "count": pipeline.get(st, 0)} for st in m.Application.PIPELINE],
            "celebrations": {"birthdays": birthdays[:8], "anniversaries": anniversaries[:8],
                             "note": "Birthdays appear only for people who chose to share them."},
            "generated_at": timezone.now(),
        })


# --- directory ----------------------------------------------------------------------------------------------
class EmployeesView(OSView):
    permissions = {"POST": "people.employee.create"}

    def get(self, request):
        ctx = self.authz
        full = ctx.has("people.employee.view")
        code = "people.employee.view" if full else "people.directory.view"
        ctx.require(code)
        qs = m.Employee.objects.filter(organization=ctx.organization).filter(employees_q(ctx, code)).select_related(
            "designation", "department", "team", "org_unit", "manager", "job_level", "user", "user__os_account")
        p = request.query_params
        st = p.get("status", "working")
        if st == "working":
            qs = qs.filter(status__in=m.Employee.WORKING)
        elif st == "former" and full:
            qs = qs.filter(status__in=m.Employee.EXITED)
        elif st in m.Employee.Status.values and full:
            qs = qs.filter(status=st)
        elif not full:
            qs = qs.filter(status__in=m.Employee.WORKING)
        if q := p.get("q", "").strip():
            qs = qs.filter(Q(full_name__icontains=q) | Q(preferred_name__icontains=q) | Q(employee_id__iexact=q) | Q(work_email__icontains=q))
        for param, field in (("department", "department_id"), ("designation", "designation_id"), ("location", "org_unit_id"), ("manager", "manager_id"),
                             ("team", "team_id"), ("worker_type", "worker_type"), ("employment_type", "employment_type"), ("work_mode", "work_mode")):
            if v := p.get(param):
                qs = qs.filter(**{field: v})
        if bu := p.get("business_unit"):
            unit = OrgUnit.objects.filter(pk=bu, organization=ctx.organization).first()
            qs = qs.filter(org_unit__path__startswith=unit.path) if unit else qs.none()
        if j := p.get("joined"):
            if j.isdigit():
                qs = qs.filter(joined_on__gte=timezone.localdate() - timedelta(days=int(j)))
        if (fr := parse_date(p.get("joined_from", "") or "")):
            qs = qs.filter(joined_on__gte=fr)
        if (to := parse_date(p.get("joined_to", "") or "")):
            qs = qs.filter(joined_on__lte=to)
        sort = {"name": "full_name", "-name": "-full_name", "joined": "joined_on", "-joined": "-joined_on", "id": "employee_id",
                "department": "department__name"}.get(p.get("sort", "name"), "full_name")
        qs = qs.order_by(sort, "full_name")
        ser = s.EmployeeSerializer if full else s.EmployeeDirectorySerializer
        if p.get("export") == "csv":
            ctx.require("people.employee.export")
            record(request, "people.employee.export", category="export", module="people", metadata={"rows": qs.count(), "filters": dict(p)})
            out = io.StringIO()
            wtr = csv.writer(out)
            wtr.writerow(["Employee ID", "Name", "Work email", "Designation", "Department", "Team", "Location", "Manager", "Worker type",
                          "Employment type", "Status", "Joined"])
            for e in qs[:20000]:  # no personal, compensation or case data in exports
                wtr.writerow([e.employee_id, e.full_name, e.work_email, getattr(e.designation, "name", ""), getattr(e.department, "name", ""),
                              getattr(e.team, "name", ""), getattr(e.org_unit, "name", ""), e.manager.full_name if e.manager_id else "",
                              e.get_worker_type_display(), e.get_employment_type_display(), e.get_status_display(), e.joined_on or ""])
            from django.http import HttpResponse

            resp = HttpResponse(out.getvalue(), content_type="text/csv")
            resp["Content-Disposition"] = 'attachment; filename="click-employees.csv"'
            return resp
        pg = DefaultPagination()
        page = pg.paginate_queryset(qs, request, view=self)
        resp = pg.get_paginated_response(ser(page, many=True, context={"authz": ctx, "request": request}).data)
        resp.data["full_record"] = full
        resp.data["can_create"] = ctx.has("people.employee.create")
        resp.data["can_export"] = ctx.has("people.employee.export")
        return resp

    def post(self, request):
        ctx = self.authz
        ser = s.EmployeeSerializer(data=request.data, context={"authz": ctx, "request": request})
        ser.is_valid(raise_exception=True)
        probe = m.Employee(organization=ctx.organization, **{k: v for k, v in ser.validated_data.items()})
        ctx.require("people.employee.create", **{k: v for k, v in target(probe).items() if k in ("unit", "department", "team")})
        if not ser.validated_data.get("full_name"):
            raise DomainError("Enter the employee’s name.", code="validation_error", details={"fullName": ["Required."]})
        with transaction.atomic():
            emp = ser.save(organization=ctx.organization, status=request.data.get("status") if request.data.get("status") in ("pre_onboarding", "active", "probation") else "pre_onboarding")
            m.EmploymentEvent.objects.create(employee=emp, kind="hired", effective_date=emp.joined_on or timezone.localdate(), created_by=request.user,
                                             after={"designation": getattr(emp.designation, "name", None), "department": getattr(emp.department, "name", None)})
        record(request, "people.employee.create", category="data", module="people", resource=emp, org_unit=emp.org_unit,
               new={"employee_id": emp.employee_id, "department": str(emp.department_id), "location": str(emp.org_unit_id)})
        if request.data.get("start_onboarding"):
            from .services import start_plan

            start_plan(request, emp, "onboarding")
        if request.data.get("invite") and emp.work_email:
            self._invite(request, ctx, emp)
        return Response(s.EmployeeSerializer(emp, context={"authz": ctx}).data, status=status.HTTP_201_CREATED)

    @staticmethod
    def _invite(request, ctx, emp):
        """Access lifecycle on joining: an invitation through Identity & Access (no roles until an administrator assigns them)."""
        from apps.access.auth_views import invite_token
        from apps.access.models import OSAccount
        from apps.users.models import User

        if not ctx.has("identity.user.create"):
            return None
        user = User.objects.filter(email__iexact=emp.work_email).first()
        if user is None:
            user = User.objects.create_user(emp.work_email.lower(), None, full_name=emp.full_name)
            user.set_unusable_password()
            user.save(update_fields=["password"])
        if hasattr(user, "os_account"):
            return None
        acct = OSAccount.objects.create(user=user, organization=ctx.organization, status=OSAccount.Status.INVITED, invited_by=request.user,
                                        invited_at=timezone.now())
        emp.user = user
        emp.save(update_fields=["user", "updated_at"])
        record(request, "identity.user.invited", category="security", module="identity", resource=acct, new={"from": "people.employee"})
        return f"/invite/{invite_token(acct)}"


class EmployeeDetailView(OSView):
    def get(self, request, pk):
        ctx = self.authz
        e = _emp_or_404(ctx, pk)
        own = is_self(ctx, e)
        full = own or can_on(ctx, "people.employee.view", e)
        data = (s.EmployeeSerializer if full else s.EmployeeDirectorySerializer)(e, context={"authz": ctx}).data
        tabs = ["overview"]
        rules = [("employment", full), ("contact", own or can_on(ctx, "people.personal.view", e)),
                 ("attendance", own or can_on(ctx, "people.attendance.view", e)), ("leave", own or can_on(ctx, "people.leave.view", e)),
                 ("performance", own or can_on(ctx, "people.performance.view", e)), ("learning", own or can_on(ctx, "people.learning.view", e)),
                 ("compensation", can_on(ctx, "people.payroll.view", e)),  # never self-served without the permission
                 ("documents", own or can_on(ctx, "people.document.view", e)), ("activity", full),
                 ("lifecycle", can_on(ctx, "people.lifecycle.view", e) or can_on(ctx, "people.offboarding.view", e) or can_on(ctx, "people.onboarding.view", e)),
                 ("security", ctx.can("identity.user.view", **{k: v for k, v in {"unit": e.org_unit_id, "department": e.department_id}.items() if v}) and not own)]
        tabs += [t for t, ok in rules if ok]
        data.update({"tabs": tabs, "is_self": own, "full_record": full,
                     "can_edit": can_on(ctx, "people.employee.edit", e), "can_edit_self": own,
                     "actions": {"promote": can_on(ctx, "people.lifecycle.create", e), "offboard": can_on(ctx, "people.offboarding.manage", e),
                                 "feedback": ctx.has("people.feedback.create") and not own, "resign": own and e.is_working,
                                 "upload_document": own or can_on(ctx, "people.document.create", e)},
                     "secondary_managers": [{"id": str(x.pk), "name": x.display_name} for x in e.secondary_managers.all()],
                     "direct_reports": [{"id": str(x.pk), "name": x.display_name, "designation": getattr(x.designation, "name", None)}
                                        for x in e.reports.filter(status__in=m.Employee.WORKING).select_related("designation")[:50]]})
        if not own and full and e.status in ("suspended",) and not ctx.has("people.employee.edit"):
            data["status"] = "active"  # suspension reasons are HR-only; the directory never reveals them
        return Response(data)

    def patch(self, request, pk):
        ctx = self.authz
        e = _emp_or_404(ctx, pk)
        before = s.EmployeeSerializer(e, context={"authz": ctx}).data
        if not can_on(ctx, "people.employee.edit", e):
            if not is_self(ctx, e):
                raise DomainError("You can’t edit this record.", code="permission_denied", status_code=403)
            # Self-service: only these fields; everything else is an HR change.
            allowed = {"preferred_name", "work_phone"}
            bad = [k for k in request.data if k not in allowed]
            if bad:
                raise DomainError("You can update your preferred name and work phone. Raise an HR request for anything else.",
                                  code="protected_fields", status_code=403, details={"fields": bad})
        ser = s.EmployeeSerializer(e, data=request.data, partial=True, context={"authz": ctx})
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            e = ser.save()
            if "secondary_manager_ids" in request.data and can_on(ctx, "people.employee.edit", e):
                e.secondary_managers.set(m.Employee.objects.filter(organization=ctx.organization, pk__in=request.data["secondary_manager_ids"] or []))
            if not is_self(ctx, e) and not can_on(ctx, "people.employee.edit", e):
                raise DomainError("You can’t move this employee outside your scope.", code="permission_denied", status_code=403)
        after = s.EmployeeSerializer(e, context={"authz": ctx}).data
        changed = {k for k in after if before.get(k) != after.get(k)}
        if changed & {"department", "team", "location", "manager", "designation"}:
            from .services import _event, access_review_task

            _event(request, e, "role_changed", before={k: before.get(k) for k in changed}, after={k: after.get(k) for k in changed})
            access_review_task(e, "Organization details changed by HR", requested_by=request.user)
        record(request, "people.employee.update", category="data", module="people", resource=e, org_unit=e.org_unit,
               old={k: before.get(k) for k in changed}, new={k: after.get(k) for k in changed})
        return Response(after)


def _tab_employment(ctx, e):
    from .services import working_weekdays

    return {"record": s.EmployeeSerializer(e, context={"authz": ctx}).data,
            "schedule": {"name": e.schedule.name, "start": e.schedule.start_time, "end": e.schedule.end_time} if e.schedule_id else None,
            "working_days": sorted(working_weekdays(e)), "position": {"id": str(e.position_id), "code": e.position.code, "title": e.position.title} if e.position_id else None}


def _tab_contact(ctx, e):
    pv, _ = m.EmployeePrivate.objects.get_or_create(employee=e)
    if not is_self(ctx, e):
        record(None, "people.personal.view", category="data", actor=ctx.user, organization=ctx.organization, module="people", resource=e, sensitive=True)
    return {"work_email": e.work_email, "work_phone": e.work_phone, "private": s.PrivateSerializer(pv).data,
            "can_edit": is_self(ctx, e) or can_on(ctx, "people.personal.edit", e)}


def _tab_attendance(ctx, e):
    today = timezone.localdate()
    start = today.replace(day=1)
    recs = m.AttendanceRecord.objects.filter(employee=e, date__gte=start - timedelta(days=60)).order_by("-date")
    month = [r for r in recs if r.date >= start]
    return {"summary": {"present": sum(1 for r in month if r.status == "present"), "late": sum(1 for r in month if r.late),
                        "early": sum(1 for r in month if r.early_departure), "remote": sum(1 for r in month if r.mode == "remote"),
                        "missing_checkout": sum(1 for r in month if r.check_in and not r.check_out and r.date < today)},
            "records": [{"date": r.date, "check_in": r.check_in, "check_out": r.check_out, "status": r.status, "mode": r.mode, "late": r.late,
                         "early": r.early_departure, "worked_minutes": r.worked_minutes, "source": r.source} for r in recs[:62]],
            "corrections": [{"id": str(c.pk), "date": c.date, "status": c.status, "reason": c.reason} for c in e.attendance_corrections.all()[:20]]}


def _tab_leave(ctx, e):
    yr = timezone.localdate().year
    bals = [balance(e, lt, yr) for lt in eligible_types(e)]
    return {"year": yr, "balances": [{"type": b.leave_type.name, "type_id": str(b.leave_type_id), "color": b.leave_type.color, "paid": b.leave_type.paid,
                                      "entitled": b.entitled + b.carried + b.adjusted, "used": b.used, "pending": b.pending, "available": b.available}
                                     for b in bals],
            "requests": s.LeaveRequestSerializer(e.leave_requests.select_related("leave_type", "employee")[:40], many=True).data}


def _tab_performance(ctx, e):
    own = is_self(ctx, e)
    reviews = []
    for r in e.reviews.select_related("cycle", "reviewer").order_by("-cycle__starts_on"):
        if r.status != "submitted":
            continue
        if own and r.kind == "peer" and not r.cycle.peer_visible_to_employee:
            continue
        reviews.append({"id": str(r.pk), "cycle": r.cycle.name, "kind": r.get_kind_display(), "rating": r.rating,
                        "reviewer": r.reviewer.full_name if not (own and r.kind == "peer") else "A colleague",
                        "strengths": r.strengths, "improvements": r.improvements, "comments": r.comments, "submitted_at": r.submitted_at})
    fb = e.feedback_received.select_related("author")
    if own:
        fb = fb.exclude(visibility="manager_only")
    return {"goals": s.GoalSerializer(e.goals.all(), many=True).data, "reviews": reviews,
            "feedback": [{"id": str(f.pk), "kind": f.kind, "badge": f.badge, "body": f.body, "author": f.author.full_name if f.author_id else None,
                          "visibility": f.visibility, "at": f.created_at} for f in fb[:30]],
            "development": [{"id": str(d.pk), "career_goal": d.career_goal, "target_role": d.target_role, "skill_gaps": d.skill_gaps,
                             "actions": d.actions, "status": d.status} for d in e.development_plans.all()]}


def _tab_learning(ctx, e):
    return {"enrollments": [{"id": str(x.pk), "course": x.course.title, "course_id": str(x.course_id), "mandatory": x.course.mandatory, "status": x.status,
                             "due_on": x.due_on, "completed_at": x.completed_at} for x in e.enrollments.select_related("course")],
            "skills": [{"id": str(x.pk), "skill": x.skill.name, "skill_id": str(x.skill_id), "category": x.skill.category, "proficiency": x.proficiency,
                        "source": x.source, "assessed_on": x.assessed_on} for x in e.skills.select_related("skill")],
            "certifications": [{"id": str(c.pk), "name": c.name, "provider": c.provider, "issued_on": c.issued_on, "expires_on": c.expires_on,
                                "verification": c.verification, "credential_id": c.credential_id} for c in e.certifications.all()]}


def _tab_compensation(ctx, e):
    record(None, "people.compensation.view", category="financial", actor=ctx.user, organization=ctx.organization, module="people", resource=e, sensitive=True)
    return {"history": [{"id": str(c.pk), "effective_date": c.effective_date, "currency": c.currency, "base_annual": c.base_annual,
                         "allowances": c.allowances, "variable_target": c.variable_target, "bonus": c.bonus, "reason": c.get_reason_display(), "note": c.note}
                        for c in e.compensation.all()],
            "benefits": [{"id": str(b.pk), "plan": b.plan.name, "kind": b.plan.kind, "enrolled_on": b.enrolled_on, "status": b.status}
                         for b in e.benefits.select_related("plan")],
            "can_manage": can_on(ctx, "people.payroll.manage", e)}


def _tab_activity(ctx, e):
    sens = can_on(ctx, "people.payroll.view", e)
    return {"events": [{"id": str(x.pk), "kind": x.get_kind_display(), "effective_date": x.effective_date, "before": x.before if not x.sensitive or sens else {},
                        "after": x.after if not x.sensitive or sens else {}, "reason": x.reason, "by": x.created_by.full_name if x.created_by_id else "System"}
                       for x in e.events.select_related("created_by") if not x.sensitive or sens]}


def _tab_lifecycle(ctx, e):
    from .serializers import OffboardingSerializer

    class _V:  # serializer target context
        authz = ctx

        @staticmethod
        def target_for(obj):
            from .services import target

            return target(obj.employee)

    return {"plans": [{"id": str(p.pk), "kind": p.kind, "status": p.status, "started_on": p.started_on, **plan_progress(p)} for p in e.lifecycle_plans.all()],
            "changes": [{"id": str(c.pk), "kind": c.get_kind_display(), "status": c.status, "effective_date": c.effective_date, "reason": c.reason,
                         "approval_id": str(c.approval_id) if c.approval_id else None} for c in e.lifecycle_changes.all()],
            "offboarding": OffboardingSerializer(e.offboarding_cases.all(), many=True, context={"view": _V, "authz": ctx}).data}


def _tab_security(ctx, e):
    acct = getattr(e.user, "os_account", None) if e.user_id else None
    if acct is None:
        return {"account": None, "message": "No Business OS account yet."}
    return {"account": {"id": str(acct.pk), "status": acct.status, "kind": acct.kind, "mfa_enabled": acct.mfa_enabled, "last_login_at": acct.last_login_at,
                        "roles": [a.role.name for a in e.user.role_assignments.filter(is_active=True).select_related("role")]},
            "path": f"/settings/users/{acct.pk}"}


TABS = {"employment": (_tab_employment, "people.employee.view"), "contact": (_tab_contact, "people.personal.view"),
        "attendance": (_tab_attendance, "people.attendance.view"), "leave": (_tab_leave, "people.leave.view"),
        "performance": (_tab_performance, "people.performance.view"), "learning": (_tab_learning, "people.learning.view"),
        "compensation": (_tab_compensation, "people.payroll.view"), "activity": (_tab_activity, "people.employee.view"),
        "lifecycle": (_tab_lifecycle, None), "security": (_tab_security, "identity.user.view")}
SELF_ALLOWED = {"employment", "contact", "attendance", "leave", "performance", "learning", "activity"}


class EmployeeTabView(OSView):
    def get(self, request, pk, tab):
        ctx = self.authz
        if tab not in TABS:
            raise DomainError("Not found.", code="not_found", status_code=404)
        e = _emp_or_404(ctx, pk)
        fn, code = TABS[tab]
        own = is_self(ctx, e)
        if tab == "lifecycle":
            ok = any(can_on(ctx, c, e) for c in ("people.lifecycle.view", "people.offboarding.view", "people.onboarding.view"))
        elif tab == "security":
            ok = not own and ctx.can("identity.user.view", **{k: v for k, v in {"unit": e.org_unit_id, "department": e.department_id}.items() if v})
        else:
            ok = (own and tab in SELF_ALLOWED) or can_on(ctx, code, e)
        if not ok:
            if code in ctx.mfa_blocked:
                raise DomainError("Turn on two-step verification to see this. Go to Settings → Security.", code="mfa_required", status_code=403)
            raise DomainError("You don’t have access to this part of the profile.", code="permission_denied", status_code=403)
        return Response(fn(ctx, e))


class EmployeeContactView(OSView):
    def get(self, request, pk):
        return EmployeeTabView.get(self, request, pk, "contact")

    def patch(self, request, pk):
        ctx = self.authz
        e = _emp_or_404(ctx, pk)
        if not (is_self(ctx, e) or can_on(ctx, "people.personal.edit", e)):
            raise DomainError("You can’t edit these details.", code="permission_denied", status_code=403)
        pv, _ = m.EmployeePrivate.objects.get_or_create(employee=e)
        ser = s.PrivateSerializer(pv, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        record(request, "people.personal.update", category="data", module="people", resource=e, sensitive=True, metadata={"fields": sorted(request.data.keys())})
        return Response(ser.data)


# --- org chart -----------------------------------------------------------------------------------------------
class OrgChartView(OSView):
    permissions = {"GET": "people.directory.view"}

    def get(self, request):
        ctx = self.authz
        qs = m.Employee.objects.filter(organization=ctx.organization, status__in=m.Employee.WORKING).filter(employees_q(ctx, "people.directory.view"))
        if dept := request.query_params.get("department"):
            qs = qs.filter(department_id=dept)
        rows = list(qs.select_related("designation", "department", "org_unit").values(
            "id", "full_name", "preferred_name", "manager_id", "designation__name", "department__name", "org_unit__name", "employee_id"))
        ids = {r["id"] for r in rows}
        counts: dict = {}
        for r in rows:
            counts[r["manager_id"]] = counts.get(r["manager_id"], 0) + 1
        nodes = [{"id": str(r["id"]), "name": r["preferred_name"] or r["full_name"], "employee_id": r["employee_id"],
                  "designation": r["designation__name"], "department": r["department__name"], "location": r["org_unit__name"],
                  "manager_id": str(r["manager_id"]) if r["manager_id"] in ids else None, "reports": counts.get(r["id"], 0)} for r in rows]
        return Response({"nodes": nodes, "departments": [{"id": str(d.pk), "name": d.name} for d in Department.objects.filter(organization=ctx.organization)]})


# --- self-service ------------------------------------------------------------------------------------------------
class MeView(OSView):
    def get(self, request):
        ctx = self.authz
        e = ctx.employee
        if e is None:
            return Response({"employee": None, "message": "Your account isn’t linked to an employee record yet. Ask HR."})
        today = timezone.localdate()
        att = m.AttendanceRecord.objects.filter(employee=e, date=today).first()
        lv = _tab_leave(ctx, e)
        return Response({
            "employee": s.EmployeeSerializer(e, context={"authz": ctx}).data,
            "today": {"date": today, "check_in": att.check_in if att else None, "check_out": att.check_out if att else None,
                      "late": att.late if att else False, "can_check_in": ctx.has("people.attendance.create")},
            "leave": {"balances": lv["balances"], "upcoming": [r for r in lv["requests"] if r["status"] in ("approved", "pending") and str(r["end_date"]) >= str(today)][:5]},
            "goals": s.GoalSerializer(e.goals.exclude(status__in=["done", "dropped"])[:10], many=True).data,
            "training": [{"id": str(x.pk), "course": x.course.title, "status": x.status, "due_on": x.due_on, "mandatory": x.course.mandatory}
                         for x in e.enrollments.exclude(status="completed").select_related("course")[:10]],
            "requests": s.HRRequestSerializer(e.hr_requests.all()[:10], many=True).data,
            "benefits": [{"plan": b.plan.name, "kind": b.plan.kind, "status": b.status} for b in e.benefits.select_related("plan")],
            "reviews_to_write": m.Review.objects.filter(reviewer=request.user, status="pending", cycle__status="active").count(),
            "internal_jobs": [{"id": str(o.pk), "title": o.title, "code": o.code, "department": o.position.department.name,
                               "location": o.position.org_unit.name if o.position.org_unit_id else None}
                              for o in m.JobOpening.objects.filter(organization=ctx.organization, status="open", internal=True).select_related("position__department", "position__org_unit")[:10]],
            "manager": {"id": str(e.manager_id), "name": e.manager.display_name} if e.manager_id else None,
        })


# --- analytics ----------------------------------------------------------------------------------------------------
K_MIN = 3  # groups smaller than this are suppressed to protect individuals


class AnalyticsView(OSView):
    permissions = {"GET": "people.analytics.view"}

    def get(self, request):
        ctx = self.authz
        today = timezone.localdate()
        emps = m.Employee.objects.filter(organization=ctx.organization).filter(employees_q(ctx, "people.analytics.view"))
        working = emps.filter(status__in=m.Employee.WORKING)
        by = lambda qs, f: [{"label": k or "Not set", "value": v} for k, v in qs.values_list(f).annotate(n=Count("id")).order_by("-n")]  # noqa: E731
        months = []
        for i in range(11, -1, -1):
            start = (today.replace(day=1) - timedelta(days=31 * i)).replace(day=1)
            end = (start + timedelta(days=32)).replace(day=1)
            months.append({"month": start.strftime("%b %Y"), "joined": emps.filter(joined_on__gte=start, joined_on__lt=end).count(),
                           "left": emps.filter(exit_date__gte=start, exit_date__lt=end).count()})
        left_12 = emps.filter(exit_date__gte=today - timedelta(days=365)).count()
        tenure = {"< 1 year": 0, "1–3 years": 0, "3–5 years": 0, "5+ years": 0}
        for jd in working.exclude(joined_on__isnull=True).values_list("joined_on", flat=True):
            y = (today - jd).days / 365
            tenure["< 1 year" if y < 1 else "1–3 years" if y < 3 else "3–5 years" if y < 5 else "5+ years"] += 1
        apps = m.Application.objects.filter(organization=ctx.organization)
        funnel = dict(apps.values_list("stage").annotate(n=Count("id")))
        hired = list(apps.filter(stage__in=["accepted", "onboarding"]).values_list("created_at", "stage_changed_at"))
        tth = round(sum((b - a).days for a, b in hired if a and b) / len(hired), 1) if hired else None
        enr = m.Enrollment.objects.filter(employee__in=working)
        ratings = list(m.Review.objects.filter(employee__in=working, kind="final", status="submitted", rating__isnull=False).values_list("rating").annotate(n=Count("id")))
        perf = [{"label": f"{r} / 5", "value": n if n >= K_MIN else None} for r, n in sorted(ratings)]
        leave = by(m.LeaveRequest.objects.filter(employee__in=working, status="approved", start_date__gte=today - timedelta(days=365)), "leave_type__name")
        att = m.AttendanceRecord.objects.filter(employee__in=working, date__gte=today - timedelta(days=30))
        skills = list(m.EmployeeSkill.objects.filter(employee__in=working).values_list("skill__name").annotate(n=Count("id"), avg=Avg("proficiency")).order_by("-n")[:12])

        def suppress(rows):
            return [r | {"value": r["value"] if r["value"] >= K_MIN else None} for r in rows]

        return Response({
            "scope": ctx.scope("people.analytics.view").level, "as_of": today, "min_group": K_MIN,
            "headcount": {"total": working.count(), "by_department": suppress(by(working, "department__name")),
                          "by_location": suppress(by(working, "org_unit__name")), "by_worker_type": suppress(by(working, "worker_type"))},
            "movement": months,
            "attrition_12m_pct": round(left_12 / max(1, working.count() + left_12) * 100, 1),
            "tenure": [{"label": k, "value": v} for k, v in tenure.items()],
            "recruitment": {"funnel": [{"stage": st, "value": funnel.get(st, 0)} for st in m.Application.PIPELINE], "time_to_hire_days": tth,
                            "rejected": funnel.get("rejected", 0)},
            "attendance_30d": {"records": att.count(), "late": att.filter(late=True).count(), "remote": att.filter(mode="remote").count()},
            "leave_12m": suppress(leave),
            "training": {"assigned": enr.count(), "completed": enr.filter(status="completed").count(),
                         "mandatory_overdue": enr.filter(course__mandatory=True, due_on__lt=today).exclude(status="completed").count()},
            "performance_distribution": perf,
            "skills": [{"label": n, "value": c if c >= K_MIN else None, "avg": round(a, 1) if c >= K_MIN else None} for n, c, a in skills],
            "insights": _insights(working, months, att, enr, today),
        })


def _insights(working, months, att, enr, today):
    out = []
    if len(months) >= 2 and months[-1]["left"] >= 3 and months[-1]["left"] > 2 * max(1, months[-2]["left"]):
        out.append({"kind": "observed", "title": "More exits this month", "what": f"{months[-1]['left']} people left this month vs {months[-2]['left']} last month.",
                    "suggestion": "Review exit interview themes for the affected teams."})
    late = att.filter(late=True).count()
    if att.count() >= 20 and late / att.count() > 0.2:
        out.append({"kind": "observed", "title": "Late arrivals are high", "what": f"{round(late / att.count() * 100)}% of check-ins in the last 30 days were late.",
                    "suggestion": "Check whether schedules match how teams actually work."})
    od = enr.filter(course__mandatory=True, due_on__lt=today).exclude(status="completed").count()
    if od:
        out.append({"kind": "observed", "title": "Mandatory training overdue", "what": f"{od} mandatory course assignment(s) are past due.",
                    "suggestion": "Remind managers of the people concerned."})
    return out


# --- import -----------------------------------------------------------------------------------------------------
IMPORT_COLUMNS = ["employee_id", "full_name", "work_email", "designation_code", "department_code", "location_code", "manager_employee_id",
                  "worker_type", "employment_type", "joined_on"]


class ImportView(OSView):
    """CSV import with preview. Rows are validated first; nothing is written unless every row is valid, and existing
    records are only updated when `allow_updates` is set explicitly (never silently overwritten)."""

    permissions = {"POST": "people.employee.import"}
    parser_classes = [MultiPartParser]

    def post(self, request):
        ctx = self.authz
        f = request.FILES.get("file")
        if f is None or f.size > 2 * 1024 * 1024:
            raise DomainError("Upload a CSV file up to 2 MB.", code="validation_error")
        try:
            text = f.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            raise DomainError("Save the file as UTF-8 CSV.", code="validation_error")
        reader = csv.DictReader(io.StringIO(text))
        missing = [c for c in ("full_name",) if c not in (reader.fieldnames or [])]
        if missing:
            raise DomainError(f"Missing columns: {', '.join(missing)}. Expected: {', '.join(IMPORT_COLUMNS)}.", code="validation_error")
        org = ctx.organization
        desig = {d.code.lower(): d for d in m.Designation.objects.filter(organization=org)}
        depts = {d.code.lower(): d for d in Department.objects.filter(organization=org)}
        units = {u.code.lower(): u for u in OrgUnit.objects.filter(organization=org)}
        existing = {e.employee_id.lower(): e for e in m.Employee.objects.filter(organization=org)}
        allow_updates = str(request.data.get("allow_updates", "")).lower() == "true"
        rows, errors = [], 0
        seen = set()
        for i, r in enumerate(reader, start=2):
            r = {k.strip(): (v or "").strip() for k, v in r.items() if k}
            errs, action = [], "create"
            eid = r.get("employee_id", "")
            if eid:
                if eid.lower() in seen:
                    errs.append("Duplicate employee_id in file")
                seen.add(eid.lower())
                if eid.lower() in existing:
                    action = "update" if allow_updates else "conflict"
                    if not allow_updates:
                        errs.append("Employee already exists (enable updates to change it)")
            if not r.get("full_name"):
                errs.append("full_name is required")
            for col, table in (("designation_code", desig), ("department_code", depts), ("location_code", units)):
                if r.get(col) and r[col].lower() not in table:
                    errs.append(f"Unknown {col.replace('_code', '')}: {r[col]}")
            if r.get("manager_employee_id") and r["manager_employee_id"].lower() not in existing and r["manager_employee_id"].lower() not in seen:
                errs.append("Unknown manager_employee_id")
            if r.get("worker_type") and r["worker_type"] not in m.Employee.WorkerType.values:
                errs.append("Invalid worker_type")
            if r.get("employment_type") and r["employment_type"] not in m.Employee.EmploymentType.values:
                errs.append("Invalid employment_type")
            if r.get("joined_on") and not parse_date(r["joined_on"]):
                errs.append("joined_on must be YYYY-MM-DD")
            unit = units.get(r.get("location_code", "").lower())
            dept = depts.get(r.get("department_code", "").lower())
            if not errs and not ctx.can("people.employee.create", **{k: v for k, v in {"unit": unit and unit.pk, "department": dept and dept.pk}.items() if v}):
                errs.append("Outside your scope")
            errors += bool(errs)
            rows.append({"row": i, "employee_id": eid, "full_name": r.get("full_name", ""), "action": action if not errs else "error", "errors": errs, "_r": r})
        commit = request.data.get("mode") == "commit"
        result = {"rows": [{k: v for k, v in x.items() if k != "_r"} for x in rows[:500]], "total": len(rows), "errors": errors,
                  "creates": sum(1 for x in rows if x["action"] == "create"), "updates": sum(1 for x in rows if x["action"] == "update"), "committed": False}
        if not commit:
            return Response(result)
        if errors:
            raise DomainError("Fix the errors before importing. Nothing was written.", code="import_invalid", details={"errors": errors})
        with transaction.atomic():
            created, by_row = {}, {}
            for x in rows:
                r = x["_r"]
                fields = dict(full_name=r["full_name"], work_email=r.get("work_email", ""), designation=desig.get(r.get("designation_code", "").lower()),
                              department=depts.get(r.get("department_code", "").lower()), org_unit=units.get(r.get("location_code", "").lower()),
                              worker_type=r.get("worker_type") or "employee", employment_type=r.get("employment_type") or "full_time",
                              joined_on=parse_date(r["joined_on"]) if r.get("joined_on") else None)
                if x["action"] == "update":
                    e = existing[r["employee_id"].lower()]
                    for k, v in fields.items():
                        if v not in (None, ""):
                            setattr(e, k, v)
                    e.save()
                else:
                    e = m.Employee.objects.create(organization=org, employee_id=r.get("employee_id") or "", status="active", **fields)
                created[e.employee_id.lower()] = e
                by_row[x["row"]] = e
            for x in rows:
                r = x["_r"]
                if r.get("manager_employee_id"):
                    mgr = created.get(r["manager_employee_id"].lower()) or existing.get(r["manager_employee_id"].lower())
                    e = by_row.get(x["row"])
                    if e and mgr and mgr.pk != e.pk:
                        e.manager = mgr
                        e.save(update_fields=["manager", "updated_at"])
        record(request, "people.employee.import", category="data", module="people", metadata={"created": result["creates"], "updated": result["updates"]})
        result["committed"] = True
        return Response(result, status=status.HTTP_201_CREATED)


# --- settings resources (generic CRUD) ------------------------------------------------------------------------------
def _settings(model, ser, search=("name",)):
    perms = {"view": "people.settings.view", "create": "people.settings.configure", "edit": "people.settings.configure", "delete": "people.settings.configure"}

    # HR configuration is organisation-wide reference data: holding the permission at any scope is enough
    # (several of these models have no location to scope by).
    class L(ScopedList):
        def get_queryset(self):
            self.authz.require(self.perms["view"])
            return self.base_queryset()

        def require_on(self, code, obj):
            self.authz.require(code)

    class D(ScopedDetail):
        def get_queryset(self):
            self.authz.require(self.perms["view"])
            return self.base_queryset()

        def require_on(self, code, obj):
            self.authz.require(code)

    for cls in (L, D):
        cls.model, cls.serializer_class, cls.perms, cls.scope_fields = model, ser, perms, {}
        cls.search_fields, cls.audit_prefix, cls.audit_category = search, f"people.{model._meta.model_name}", "config"
    return L, D


JobLevelList, JobLevelDetail = _settings(m.JobLevel, s.JobLevelSerializer)
DesignationList, DesignationDetail = _settings(m.Designation, s.DesignationSerializer)
ScheduleList, ScheduleDetail = _settings(m.WorkSchedule, s.ScheduleSerializer)
LeaveTypeList, LeaveTypeDetail = _settings(m.LeaveType, s.LeaveTypeSerializer)
CalendarList, CalendarDetail = _settings(m.HolidayCalendar, s.HolidayCalendarSerializer)
ChecklistList, ChecklistDetail = _settings(m.ChecklistTemplate, s.ChecklistTemplateSerializer)


class LookupsView(OSView):
    """Pick-lists for HR forms (names only)."""

    def get(self, request):
        ctx = self.authz
        org = ctx.organization
        return Response({
            "departments": [{"id": str(d.pk), "name": d.name, "code": d.code} for d in Department.objects.filter(organization=org, is_active=True)],
            "teams": [{"id": str(t.pk), "name": t.name, "department_id": str(t.department_id)} for t in Team.objects.filter(department__organization=org)],
            "locations": [{"id": str(u.pk), "name": u.name, "type": u.get_unit_type_display(), "depth": u.depth} for u in OrgUnit.objects.filter(organization=org, is_active=True)],
            "designations": [{"id": str(d.pk), "name": d.name} for d in m.Designation.objects.filter(organization=org, is_active=True)],
            "job_levels": [{"id": str(j.pk), "name": j.name} for j in m.JobLevel.objects.filter(organization=org)],
            "schedules": [{"id": str(x.pk), "name": x.name} for x in m.WorkSchedule.objects.filter(organization=org)],
            "worker_types": [{"value": v, "label": lbl} for v, lbl in m.Employee.WorkerType.choices],
            "employment_types": [{"value": v, "label": lbl} for v, lbl in m.Employee.EmploymentType.choices],
            "work_modes": [{"value": v, "label": lbl} for v, lbl in m.Employee.WorkMode.choices],
            "statuses": [{"value": v, "label": lbl} for v, lbl in m.Employee.Status.choices],
        })

