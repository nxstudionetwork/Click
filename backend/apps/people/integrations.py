"""
How People & HR plugs into the Business OS foundation (loaded from PeopleConfig.ready()). Nothing here copies a
shared system: it registers into the Home widget engine, alerts, calendar, search, Business AI and document access.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from apps.documents import access as doc_access
from apps.workspace import alerts as alerts_mod
from apps.workspace import ai as ai_mod
from apps.workspace import calendar as cal_mod
from apps.workspace import search as search_mod
from apps.workspace import widgets as w

from .models import (Candidate, Certification, Employee, Enrollment, HRRequest, Interview, JobOpening, LeaveRequest, Position, Review)
from .services import can_on, employees_q, on_leave_today, related_q


def _emps(ctx, code="people.employee.view", unit=None):
    qs = Employee.objects.filter(organization=ctx.organization).filter(employees_q(ctx, code))
    if unit is not None:
        qs = qs.filter(org_unit__path__startswith=unit.path)
    return qs


def _brief(e: Employee) -> dict:
    return {"id": str(e.pk), "full_name": e.display_name, "employee_id": e.employee_id,
            "designation": e.designation.name if e.designation_id else None, "path": f"/people/{e.pk}"}


# =============================================================================================================
# Home widgets (logic lives here, in the module)
# =============================================================================================================
def people_overview(ctx, p):
    qs = _emps(ctx, unit=p.unit)
    by = dict(qs.values_list("status").annotate(n=Count("id")))
    working = sum(by.get(s, 0) for s in Employee.WORKING)
    d30 = timezone.localdate() - timedelta(days=30)
    away = len(on_leave_today(ctx.organization, list(qs.values_list("pk", flat=True))))
    open_pos = Position.objects.filter(organization=ctx.organization, status__in=["approved", "open"])
    if ctx.has("people.position.view"):
        open_pos = open_pos.filter(ctx.scope("people.position.view").q(unit="org_unit", department="department", organization=None))
        open_n = sum(max(0, p_.headcount - p_.holders.filter(status__in=Employee.WORKING).count()) for p_ in open_pos[:200])
    else:
        open_n = None
    return {"scope": ctx.scope("people.employee.view").level, "metrics": [
        {"key": "working", "label": "Employees", "value": working, "format": "number", "path": "/people/directory"},
        {"key": "joiners", "label": "Joined · 30 days", "value": qs.filter(joined_on__gte=d30).count(), "format": "number", "path": "/people/directory?joined=30"},
        {"key": "away", "label": "On leave today", "value": away, "format": "number", "path": "/people/leave?tab=team"},
        {"key": "pre", "label": "Joining soon", "value": by.get("pre_onboarding", 0), "format": "number", "path": "/people/onboarding"},
        {"key": "notice", "label": "Serving notice", "value": by.get("notice", 0), "format": "number", "path": "/people/lifecycle"},
        *([{"key": "open", "label": "Open positions", "value": open_n, "format": "number", "path": "/people/positions"}] if open_n is not None else []),
    ]}


def new_joiners(ctx, p):
    today = timezone.localdate()
    qs = _emps(ctx, unit=p.unit).filter(joined_on__gte=today - timedelta(days=30), joined_on__lte=today + timedelta(days=30)).select_related("designation", "department")
    return {"items": [_brief(e) | {"joined_on": e.joined_on, "department": e.department.name if e.department_id else None,
                                   "upcoming": e.joined_on > today} for e in qs.order_by("joined_on")[:10]]}


def pending_leave(ctx, p):
    from apps.workflows.selectors import inbox_for

    mine = [r for r in inbox_for(ctx) if r.policy.key == "people.leave"]
    ids = [r.resource_id for r in mine]
    lr = {str(x.pk): x for x in LeaveRequest.objects.filter(pk__in=ids).select_related("employee", "leave_type")}
    items = []
    for r in mine[:10]:
        x = lr.get(r.resource_id)
        if x:
            items.append({"id": str(r.pk), "employee": x.employee.display_name, "type": x.leave_type.name, "start": x.start_date, "end": x.end_date,
                          "days": str(x.days), "path": f"/approvals/{r.pk}", "starts_soon": x.start_date <= timezone.localdate() + timedelta(days=3)})
    team_pending = LeaveRequest.objects.filter(status="pending").filter(related_q(ctx, "people.leave.view")).count() if ctx.has("people.leave.view") else None
    return {"items": items, "waiting_on_me": len(mine), "pending_in_scope": team_pending}


def open_positions(ctx, p):
    qs = Position.objects.filter(organization=ctx.organization, status__in=["approved", "open", "pending_approval"]).filter(
        ctx.scope("people.position.view").q(unit="org_unit", department="department", organization=None)).select_related("department")
    rows = []
    for pos in qs[:30]:
        filled = pos.holders.filter(status__in=Employee.WORKING + ("pre_onboarding",)).count()
        if filled < pos.headcount or pos.status == "pending_approval":
            apps = sum(o.applications.exclude(stage__in=["rejected", "withdrawn"]).count() for o in pos.openings.all())
            rows.append({"id": str(pos.pk), "code": pos.code, "title": pos.title, "department": pos.department.name, "open": pos.headcount - filled,
                         "status": pos.status, "candidates": apps, "path": f"/people/positions?open={pos.pk}"})
    return {"items": rows[:8], "total": len(rows)}


def upcoming_reviews(ctx, p):
    qs = Review.objects.filter(reviewer=ctx.user, status="pending", cycle__status="active").select_related("employee", "cycle")
    return {"items": [{"id": str(r.pk), "employee": r.employee.display_name if r.kind != "self" else "Your self review", "kind": r.get_kind_display(),
                       "cycle": r.cycle.name, "due_on": r.due_on, "overdue": bool(r.due_on and r.due_on < timezone.localdate()),
                       "path": f"/people/performance?review={r.pk}"} for r in qs.order_by("due_on")[:8]], "total": qs.count()}


def document_expiries(ctx, p):
    from apps.documents.models import Document

    today = timezone.localdate()
    emp_ids = [str(x) for x in _emps(ctx, "people.document.view", p.unit).values_list("pk", flat=True)[:5000]]
    docs = Document.objects.filter(organization=ctx.organization, resource_type="people.employee", resource_id__in=emp_ids, status="active",
                                   expires_on__isnull=False, expires_on__lte=today + timedelta(days=60)).order_by("expires_on")
    certs = Certification.objects.filter(employee_id__in=emp_ids, expires_on__isnull=False, expires_on__lte=today + timedelta(days=60)).select_related("employee")
    names = {str(pk): n for pk, n in Employee.objects.filter(pk__in=[d.resource_id for d in docs[:20]]).values_list("pk", "full_name")}
    items = [{"kind": "document", "title": d.title, "employee": names.get(d.resource_id, ""),
              "employee_id": d.resource_id, "expires_on": d.expires_on, "expired": d.expires_on < today,
              "path": f"/people/{d.resource_id}?tab=documents"} for d in docs[:10] if d.sensitivity != "restricted" or ctx.has("people.document_restricted.view")]
    items += [{"kind": "certification", "title": c.name, "employee": c.employee.display_name, "employee_id": str(c.employee_id),
               "expires_on": c.expires_on, "expired": c.expires_on < today, "path": f"/people/{c.employee_id}?tab=learning"} for c in certs[:10]]
    items.sort(key=lambda i: i["expires_on"])
    return {"items": items[:10], "total": len(items)}


def attendance_exceptions_widget(ctx, p):
    from .services import attendance_exceptions

    day = timezone.localdate() - timedelta(days=1)
    rows = attendance_exceptions(ctx.organization, _emps(ctx, "people.attendance.view", p.unit), day)
    today_late = attendance_exceptions(ctx.organization, _emps(ctx, "people.attendance.view", p.unit), timezone.localdate())
    rows = [r for r in rows] + [r for r in today_late if r["kind"] == "late"]
    return {"date": day, "items": [_brief(r["employee"]) | {"kind": r["kind"], "label": r["label"]} for r in rows[:10]], "total": len(rows),
            "counts": {k: sum(1 for r in rows if r["kind"] == k) for k in ("absent", "missing_checkout", "late", "early")}}


def probation_ending(ctx, p):
    today = timezone.localdate()
    qs = _emps(ctx, unit=p.unit).filter(status="probation", probation_end_on__lte=today + timedelta(days=30)).order_by("probation_end_on")
    return {"items": [_brief(e) | {"ends_on": e.probation_end_on, "overdue": e.probation_end_on < today} for e in qs[:10]], "total": qs.count()}


def training_due(ctx, p):
    today = timezone.localdate()
    own = Q(employee__user=ctx.user)
    scope = related_q(ctx, "people.learning.view") if ctx.has("people.learning.view") else Q(pk__in=[])
    qs = Enrollment.objects.filter(Q(own) | scope).exclude(status="completed").filter(due_on__isnull=False, due_on__lte=today + timedelta(days=14)) \
        .select_related("course", "employee")
    return {"items": [{"id": str(e.pk), "course": e.course.title, "employee": e.employee.display_name, "mine": e.employee.user_id == ctx.user.pk,
                       "due_on": e.due_on, "overdue": e.due_on < today, "mandatory": e.course.mandatory, "path": "/people/learning"}
                      for e in qs.order_by("due_on")[:10]], "total": qs.count()}


STAFF = ("employee", "external")
for _wd in (
    w.Widget("people_overview", "People", "m", "awareness", people_overview, permission="people.employee.view", source="People & HR", unit_aware=True, audience=STAFF),
    w.Widget("new_joiners", "New joiners", "m", "awareness", new_joiners, permission="people.employee.view", source="People & HR", unit_aware=True, audience=STAFF),
    w.Widget("pending_leave", "Pending leave", "m", "action", pending_leave, permission=("people.leave.approve", "people.leave.view"),
             source="People & HR", audience=STAFF),
    w.Widget("open_positions", "Open positions", "m", "awareness", open_positions, permission="people.position.view", source="People & HR", audience=STAFF),
    w.Widget("upcoming_reviews", "Reviews to write", "m", "action", upcoming_reviews, source="People & HR", audience=("employee",)),
    w.Widget("document_expiries", "Document & certification expiries", "m", "attention", document_expiries, permission="people.document.view",
             source="People & HR", unit_aware=True, audience=STAFF),
    w.Widget("attendance_exceptions", "Attendance exceptions", "m", "attention", attendance_exceptions_widget, permission="people.attendance.view",
             source="People & HR", unit_aware=True, audience=STAFF),
    w.Widget("probation_ending", "Probation ending", "m", "action", probation_ending, permission="people.employee.view", source="People & HR",
             unit_aware=True, audience=STAFF),
    w.Widget("training_due", "Training due", "m", "action", training_due, source="People & HR", audience=("employee",)),
):
    w.register(_wd)


# =============================================================================================================
# Priorities, my work, briefing, team, calendar
# =============================================================================================================
def _priorities(ctx):
    today = timezone.localdate()
    out = []
    for r in Review.objects.filter(reviewer=ctx.user, status="pending", cycle__status="active", due_on__isnull=False, due_on__lte=today + timedelta(days=3)) \
            .select_related("employee")[:5]:
        overdue = r.due_on < today
        out.append({"kind": "review", "title": f"{r.get_kind_display()}: {r.employee.display_name}" if r.kind != "self" else "Your self review",
                    "reason": "Review overdue" if overdue else "Review due soon", "score": 84 if overdue else 72, "path": f"/people/performance?review={r.pk}",
                    "due_at": None, "severity": "high"})
    for e in Enrollment.objects.filter(employee__user=ctx.user, course__mandatory=True, due_on__lte=today + timedelta(days=3)).exclude(status="completed") \
            .select_related("course")[:3]:
        out.append({"kind": "training", "title": e.course.title, "reason": "Mandatory training due", "score": 71, "path": "/people/learning",
                    "due_at": None, "severity": "high"})
    return out


def _my_work(ctx):
    out = []
    n = Review.objects.filter(reviewer=ctx.user, status="pending", cycle__status="active").count()
    if n:
        out.append({"kind": "reviews", "label": "Reviews to write", "count": n, "path": "/people/performance"})
    n = Interview.objects.filter(panel=ctx.user, status="scheduled", scheduled_at__gte=timezone.now() - timedelta(hours=2)).count()
    if n:
        out.append({"kind": "interviews", "label": "Interviews on your panel", "count": n, "path": "/people/interviews"})
    n = HRRequest.objects.filter(assignee=ctx.user, status__in=["open", "in_progress"]).count()
    if n:
        out.append({"kind": "hr_requests", "label": "HR requests assigned to you", "count": n, "path": "/people/requests?view=assigned"})
    return out


def _briefing(ctx):
    lines = []
    today = timezone.localdate()
    if ctx.has("people.document.view"):
        n = Certification.objects.filter(employee__in=_emps(ctx, "people.document.view"), expires_on__gte=today, expires_on__lte=today + timedelta(days=7)).count()
        if n:
            lines.append({"text": f"{n} employee certification{'s' if n != 1 else ''} expire this week.", "source": "People & HR", "path": "/people/learning"})
    if ctx.has("people.employee.view"):
        n = _emps(ctx).filter(status="probation", probation_end_on__gte=today, probation_end_on__lte=today + timedelta(days=14)).count()
        if n:
            lines.append({"text": f"{n} probation period{'s' if n != 1 else ''} end in the next two weeks.", "source": "People & HR", "path": "/people/lifecycle"})
    if ctx.is_manager:
        away = on_leave_today(ctx.organization, ctx.direct_report_ids)
        if away:
            lines.append({"text": f"{len(away)} of your direct reports {'is' if len(away) == 1 else 'are'} on leave today.", "source": "People & HR",
                          "path": "/people/leave?tab=team"})
    return lines


def _team_away(ctx, members):
    return on_leave_today(ctx.organization, [m.pk for m in members])


def _cal_people(ctx, start, end):
    from .services import calendars_for

    emp = ctx.employee
    tz = timezone.get_current_timezone()
    from datetime import datetime, time

    def at(d):
        return datetime.combine(d, time(9), tzinfo=tz)

    if emp is not None:
        for lr in LeaveRequest.objects.filter(employee=emp, status__in=["approved", "pending"], end_date__gte=start.date(), start_date__lt=end.date()):
            yield {"id": f"leave:{lr.pk}", "kind": "leave", "title": f"Your {lr.leave_type.name.lower()}" + (" (pending)" if lr.status == "pending" else ""),
                   "at": at(max(lr.start_date, start.date())), "priority": "normal", "path": "/people/leave"}
        from .models import Holiday

        for h in Holiday.objects.filter(calendar__in=calendars_for(emp), date__gte=start.date(), date__lt=end.date()):
            yield {"id": f"holiday:{h.pk}", "kind": "holiday", "title": h.name + (" (optional)" if h.optional else ""), "at": at(h.date),
                   "priority": "low", "path": "/people/leave?tab=holidays"}
    for r in Review.objects.filter(reviewer=ctx.user, status="pending", due_on__gte=start.date(), due_on__lt=end.date()).select_related("employee"):
        yield {"id": f"review:{r.pk}", "kind": "review", "title": f"Review due: {r.employee.display_name}", "at": at(r.due_on), "priority": "high",
               "path": "/people/performance"}
    for iv in Interview.objects.filter(panel=ctx.user, status="scheduled", scheduled_at__gte=start, scheduled_at__lt=end).select_related("application__candidate"):
        yield {"id": f"interview:{iv.pk}", "kind": "interview", "title": f"Interview: {iv.application.candidate.full_name} ({iv.round_name})",
               "at": iv.scheduled_at, "priority": "high", "path": "/people/interviews"}
    if ctx.is_manager:
        for lr in LeaveRequest.objects.filter(employee_id__in=ctx.direct_report_ids, status="approved", end_date__gte=start.date(),
                                              start_date__lt=end.date()).select_related("employee"):
            yield {"id": f"teamleave:{lr.pk}", "kind": "team_leave", "title": f"{lr.employee.display_name} on leave", "at": at(max(lr.start_date, start.date())),
                   "priority": "low", "path": "/people/leave?tab=team"}


w.PRIORITY_SOURCES.append(_priorities)
w.MY_WORK_SOURCES.append(_my_work)
w.BRIEFING_SOURCES.append(_briefing)
w.TEAM_SOURCES.append(_team_away)
cal_mod.SOURCES.append(_cal_people)


# =============================================================================================================
# Alerts (scoped to the employee's location, not platform-wide)
# =============================================================================================================
@alerts_mod.detector("people.documents_expiring", category="people", source="People & HR", permission="people.document.view", org_wide_only=False)
def _doc_expiry(org):
    from apps.documents.models import Document

    today = timezone.localdate()
    out = []
    emps = {str(e.pk): e for e in Employee.objects.filter(organization=org, status__in=Employee.WORKING).select_related("org_unit")}
    for d in Document.objects.filter(organization=org, resource_type="people.employee", status="active", expires_on__isnull=False,
                                     expires_on__lte=today + timedelta(days=30)):
        e = emps.get(d.resource_id)
        if e is None:
            continue
        expired = d.expires_on < today
        out.append(alerts_mod.Found(f"{d.pk}", "high" if expired else "medium",
                                    f"{e.full_name}: {d.title} {'expired' if expired else 'expires'} {d.expires_on:%d %b %Y}",
                                    link=f"/people/{e.pk}?tab=documents", action="Request a renewed document from the employee.",
                                    org_unit_id=e.org_unit_id, due_on=d.expires_on, risk=True))
    return out


@alerts_mod.detector("people.probation_overdue", category="people", source="People & HR", permission="people.employee.edit", org_wide_only=False)
def _probation(org):
    today = timezone.localdate()
    return [alerts_mod.Found(f"{e.pk}", "medium", f"Probation ended without a decision: {e.full_name}", link=f"/people/{e.pk}",
                             action="Confirm the employee or extend probation.", org_unit_id=e.org_unit_id, due_on=e.probation_end_on)
            for e in Employee.objects.filter(organization=org, status="probation", probation_end_on__lt=today)]


@alerts_mod.detector("people.certifications_expiring", category="people", source="People & HR", permission="people.learning.view", org_wide_only=False)
def _cert_expiry(org):
    today = timezone.localdate()
    return [alerts_mod.Found(f"{c.pk}", "high" if c.expires_on < today else "low",
                             f"{c.employee.full_name}: {c.name} certification {'expired' if c.expires_on < today else 'expires'} {c.expires_on:%d %b}",
                             link=f"/people/{c.employee_id}?tab=learning", action="Plan the renewal.", org_unit_id=c.employee.org_unit_id,
                             due_on=c.expires_on, risk=c.expires_on < today)
            for c in Certification.objects.filter(employee__organization=org, employee__status__in=Employee.WORKING,
                                                  expires_on__lte=today + timedelta(days=30), expires_on__gte=today - timedelta(days=60)).select_related("employee")]


# =============================================================================================================
# Global search (permission + scope filtered in the database)
# =============================================================================================================
def _s_candidates(ctx, q, n):
    qs = Candidate.objects.filter(organization=ctx.organization).filter(Q(full_name__icontains=q) | Q(code__iexact=q) | Q(email__icontains=q))
    return [{"id": str(c.pk), "title": c.full_name, "subtitle": f"{c.code} · Candidate", "path": f"/people/candidates/{c.pk}"} for c in qs[:n]]


def _s_positions(ctx, q, n):
    qs = Position.objects.filter(organization=ctx.organization).filter(ctx.scope("people.position.view").q(unit="org_unit", department="department",
                                                                                                         organization=None))
    qs = qs.filter(Q(title__icontains=q) | Q(code__iexact=q)).select_related("department")
    return [{"id": str(p.pk), "title": p.title, "subtitle": f"{p.code} · {p.department.name} · {p.get_status_display()}",
             "path": f"/people/positions?open={p.pk}"} for p in qs[:n]]


def _s_openings(ctx, q, n):
    qs = JobOpening.objects.filter(organization=ctx.organization, title__icontains=q)
    if not ctx.has("people.recruitment.view"):
        qs = qs.filter(internal=True, status="open")  # employees see internal opportunities only
    return [{"id": str(o.pk), "title": o.title, "subtitle": f"{o.code} · {o.get_status_display()}",
             "path": f"/people/recruitment/{o.pk}" if ctx.has("people.recruitment.view") else "/people/me?tab=jobs"} for o in qs[:n]]


def _s_departments(ctx, q, n):
    from apps.organization.models import Department, Team

    out = [{"id": str(d.pk), "title": d.name, "subtitle": f"Department · {d.code}", "path": f"/people/directory?department={d.pk}"}
           for d in Department.objects.filter(organization=ctx.organization, name__icontains=q)[:n]]
    out += [{"id": str(t.pk), "title": t.name, "subtitle": f"Team · {t.department.name}", "path": f"/people/directory?team={t.pk}"}
            for t in Team.objects.filter(department__organization=ctx.organization, name__icontains=q).select_related("department")[:n]]
    return out[:n]


def _s_requests(ctx, q, n):
    cond = Q(employee__user=ctx.user)
    if ctx.has("people.request.manage"):
        cond |= related_q(ctx, "people.request.manage")
    qs = HRRequest.objects.filter(organization=ctx.organization).filter(cond).filter(Q(subject__icontains=q) | Q(code__iexact=q))
    return [{"id": str(r.pk), "title": r.subject, "subtitle": f"{r.code} · {r.get_status_display()}", "path": f"/people/requests?open={r.pk}"}
            for r in qs[:n]]


def _s_documents(ctx, q, n):
    from apps.documents.models import Document

    rows = Document.objects.filter(organization=ctx.organization, resource_type="people.employee", status="active", title__icontains=q)[:60]
    out = []
    for d in rows:
        if doc_access.allowed(ctx, d.resource_type, d.resource_id, "view", d):
            out.append({"id": str(d.pk), "title": d.title, "subtitle": f"Employee document · {d.category}", "path": f"/people/{d.resource_id}?tab=documents"})
        if len(out) >= n:
            break
    return out


for _p in (
    search_mod.Provider("candidate", "Candidates", "people.candidate.view", _s_candidates),
    search_mod.Provider("position", "Positions", "people.position.view", _s_positions),
    search_mod.Provider("opening", "Job openings", None, _s_openings),
    search_mod.Provider("department", "Departments & teams", "people.directory.view", _s_departments),
    search_mod.Provider("hr_request", "HR requests", None, _s_requests),
    search_mod.Provider("document", "Documents", "people.document.view", _s_documents),
):
    search_mod.PROVIDERS[_p.type] = _p


# =============================================================================================================
# Business AI tools (inherit permissions; compensation and cases are never answered)
# =============================================================================================================
def _ai_sensitive(ctx, q):
    return {"answer": "Business AI doesn’t answer questions about salaries, disciplinary matters or HR cases, even when you have access. "
                      "Open People & HR to see that information, where access is checked and audited.", "denied": True}


def _ai_headcount(ctx, q):
    rows = list(_emps(ctx).filter(status__in=Employee.WORKING).values_list("department__name").annotate(n=Count("id")).order_by("-n"))
    if not rows:
        return {"answer": "There are no employees within your access."}
    txt = "; ".join(f"{d or 'No department'}: {n}" for d, n in rows[:10])
    return {"answer": f"Employees by department (within your access): {txt}."}


def _ai_certs(ctx, q):
    today = timezone.localdate()
    end = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    cs = Certification.objects.filter(employee__in=_emps(ctx, "people.learning.view"), expires_on__gte=today, expires_on__lt=end).select_related("employee")
    if not cs:
        return {"answer": "No certifications within your access expire this month."}
    return {"answer": f"{len(cs)} certification{'s' if len(cs) != 1 else ''} expire this month.",
            "items": [{"title": c.name, "subtitle": f"{c.employee.display_name} · {c.expires_on:%d %b}", "path": f"/people/{c.employee_id}?tab=learning"} for c in cs[:8]]}


def _ai_leave(ctx, q):
    d = pending_leave(ctx, w.Params())
    if not d["items"]:
        return {"answer": "No leave requests are waiting for your approval."}
    return {"answer": f"{d['waiting_on_me']} leave request{'s' if d['waiting_on_me'] != 1 else ''} waiting for your approval.",
            "items": [{"title": f"{i['employee']} · {i['type']}", "subtitle": f"{i['start']:%d %b} – {i['end']:%d %b} ({i['days']} days)", "path": i["path"]}
                      for i in d["items"]]}


def _ai_pipeline(ctx, q):
    from .models import Application

    qs = Application.objects.filter(organization=ctx.organization, opening__status="open").exclude(stage__in=["rejected", "withdrawn"])
    by = dict(qs.values_list("stage").annotate(n=Count("id")))
    if not by:
        return {"answer": "No active candidates in open hiring pipelines."}
    order = [s for s in Application.PIPELINE if by.get(s)]
    return {"answer": "Hiring pipeline: " + ", ".join(f"{by[s]} {s}" for s in order) + "."}


def _ai_positions(ctx, q):
    d = open_positions(ctx, w.Params())
    if not d["items"]:
        return {"answer": "No unfilled positions within your access."}
    return {"answer": f"{d['total']} position{'s' if d['total'] != 1 else ''} not yet filled.",
            "items": [{"title": i["title"], "subtitle": f"{i['code']} · {i['open']} open · {i['candidates']} candidates", "path": i["path"]} for i in d["items"]]}


ai_mod.EXTRA_TOOLS += [
    ai_mod.Tool("hr_sensitive", "Compensation and HR cases", None, ("salary", "salaries", "payroll", "payslip", "ctc", "compensation", "disciplinary",
                                                                     "grievance", "investigation", "hr case"), _ai_sensitive),
    ai_mod.Tool("hr_headcount", "Headcount by department", "people.employee.view", ("how many employees", "headcount", "employees in", "staff in"), _ai_headcount),
    ai_mod.Tool("hr_certs", "Certification expiries", "people.learning.view", ("certification", "certifications expiring", "certs"), _ai_certs),
    ai_mod.Tool("hr_leave", "Pending leave approvals", "people.leave.approve", ("leave approval", "pending leave", "leave requests"), _ai_leave),
    ai_mod.Tool("hr_pipeline", "Hiring pipeline", "people.recruitment.view", ("hiring pipeline", "recruitment", "candidates", "pipeline"), _ai_pipeline),
    ai_mod.Tool("hr_positions", "Unfilled positions", "people.position.view", ("unfilled", "open positions", "vacancies", "positions remain"), _ai_positions),
]


# =============================================================================================================
# Document access (central document store; People decides who sees employee and candidate files)
# =============================================================================================================
@doc_access.register("people.employee")
def _employee_docs(ctx, resource_id, action, document=None):
    emp = Employee.objects.filter(pk=resource_id, organization=ctx.organization).first() if resource_id else None
    if emp is None:
        return False
    own = bool(emp.user_id and emp.user_id == ctx.user.pk)
    restricted = bool(document is not None and document.sensitivity == "restricted")
    if action == "view":
        if own:
            return True
        if restricted:
            return can_on(ctx, "people.document_restricted.view", emp)
        return can_on(ctx, "people.document.view", emp)
    if action == "upload":
        return own or can_on(ctx, "people.document.create", emp)
    if action == "upload_restricted":
        return own or can_on(ctx, "people.document_restricted.create", emp)
    if action in ("verify", "archive"):
        return can_on(ctx, "people.document.verify", emp) and not own
    return False


@doc_access.register("people.candidate")
def _candidate_docs(ctx, resource_id, action, document=None):
    if action == "view":
        return ctx.has("people.candidate.view")
    if action in ("upload", "upload_restricted"):
        return ctx.has("people.recruitment.edit")
    return ctx.has("people.recruitment.manage")

