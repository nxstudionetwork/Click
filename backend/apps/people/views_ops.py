"""People & HR API, part 2: talent, workforce (attendance & leave), performance, learning, pay, engagement, requests, cases, lifecycle."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import status
from rest_framework.response import Response

from apps.access.api import OSView
from apps.access.crud import ScopedDetail, ScopedList
from apps.audit.services import record
from apps.core.api.exceptions import DomainError
from apps.core.api.pagination import DefaultPagination
from apps.users.models import User
from apps.workspace.notify import notify, notify_many

from . import models as m
from . import serializers as s
from . import services as svc
from .services import can_on, employee_of, employees_q, is_self, related_q, require_on


def _emp(ctx, pk) -> m.Employee:
    e = m.Employee.objects.filter(organization=ctx.organization, pk=pk).select_related("org_unit", "department", "team", "manager", "user").first()
    if e is None:
        raise DomainError("Not found.", code="not_found", status_code=404)
    return e


def _date(v, field):
    d = parse_date(str(v or ""))
    if d is None:
        raise DomainError("Enter a valid date.", code="validation_error", details={field: ["Enter a valid date."]})
    return d


def _paginate(view, qs, fn):
    pg = DefaultPagination()
    page = pg.paginate_queryset(qs, view.request, view=view)
    return pg.get_paginated_response([fn(x) for x in page])


# =============================================================================================================
# Positions & workforce planning
# =============================================================================================================
class PositionList(ScopedList):
    model, serializer_class = m.Position, s.PositionSerializer
    perms = {"view": "people.position.view", "create": "people.position.create", "export": "people.position.view"}
    scope_fields = {"unit": "org_unit", "department": "department"}
    search_fields, filters = ("title", "code"), {"department": "department_id", "status": "status", "location": "org_unit_id"}
    select_related, audit_prefix = ("department", "org_unit", "reporting_manager"), "people.position"

    def perform_create(self, ser):
        return ser.save(organization=self.authz.organization, created_by=self.request.user)


class PositionDetail(ScopedDetail):
    model, serializer_class = m.Position, s.PositionSerializer
    perms = {"view": "people.position.view", "edit": "people.position.edit", "delete": "people.position.delete"}
    scope_fields = PositionList.scope_fields
    audit_prefix = "people.position"


class PositionSubmitView(OSView):
    permissions = {"POST": "people.position.create"}

    def post(self, request, pk):
        ctx = self.authz
        pos = m.Position.objects.filter(organization=ctx.organization, pk=pk).filter(
            ctx.scope("people.position.create").q(unit="org_unit", department="department", organization=None)).first()
        if pos is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        svc.submit_position(request, ctx, pos)
        return Response(s.PositionSerializer(pos, context={"authz": ctx}).data)


class HeadcountList(ScopedList):
    model, serializer_class = m.HeadcountPlan, s.HeadcountPlanSerializer
    perms = {"view": "people.workforce.view", "create": "people.workforce.manage"}
    scope_fields = {"unit": "org_unit", "department": "department"}
    filters, audit_prefix = {"period": "period", "department": "department_id"}, "people.headcount"


class HeadcountDetail(ScopedDetail):
    model, serializer_class = m.HeadcountPlan, s.HeadcountPlanSerializer
    perms = {"view": "people.workforce.view", "edit": "people.workforce.manage", "delete": "people.workforce.manage"}
    scope_fields, audit_prefix = HeadcountList.scope_fields, "people.headcount"


class WorkforceSummaryView(OSView):
    permissions = {"GET": "people.workforce.view"}

    def get(self, request):
        ctx = self.authz
        from apps.organization.models import Department

        period = request.query_params.get("period", "")
        rows = []
        pos_q = ctx.scope("people.position.view").q(unit="org_unit", department="department", organization=None)
        for d in Department.objects.filter(organization=ctx.organization, is_active=True):
            current = m.Employee.objects.filter(organization=ctx.organization, department=d, status__in=m.Employee.WORKING).filter(
                employees_q(ctx, "people.workforce.view")).count()
            positions = m.Position.objects.filter(department=d, status__in=["approved", "open", "filled"]).filter(pos_q)
            approved = sum(p.headcount for p in positions)
            plan = m.HeadcountPlan.objects.filter(department=d, period=period).first() if period else m.HeadcountPlan.objects.filter(department=d).order_by("-period").first()
            if current or approved or plan:
                rows.append({"department": d.name, "department_id": str(d.pk), "current": current, "approved": approved,
                             "open": max(0, approved - current), "planned": plan.planned if plan else None, "period": plan.period if plan else None})
        return Response({"results": rows, "periods": sorted(set(m.HeadcountPlan.objects.filter(organization=ctx.organization).values_list("period", flat=True)))})


# =============================================================================================================
# Recruitment
# =============================================================================================================
class OpeningList(ScopedList):
    model, serializer_class = m.JobOpening, s.OpeningSerializer
    perms = {"view": "people.recruitment.view", "create": "people.recruitment.create"}
    scope_fields = {"unit": "position__org_unit", "department": "position__department"}
    search_fields, filters = ("title", "code"), {"status": "status", "position": "position_id"}
    select_related, audit_prefix = ("position__department", "position__org_unit", "hiring_manager", "recruiter"), "people.opening"

    def post(self, request):
        pos = m.Position.objects.filter(pk=request.data.get("position"), organization=self.authz.organization).first()
        if pos is None or pos.status not in ("approved", "open"):
            raise DomainError("Openings need an approved position.", code="position_not_approved", status_code=409)
        resp = super().post(request)
        m.Position.objects.filter(pk=pos.pk).update(status="open")
        return resp

    def perform_create(self, ser):
        return ser.save(organization=self.authz.organization, opened_on=timezone.localdate())


class OpeningDetail(ScopedDetail):
    model, serializer_class = m.JobOpening, s.OpeningSerializer
    perms = {"view": "people.recruitment.view", "edit": "people.recruitment.edit", "delete": "people.recruitment.manage"}
    scope_fields, audit_prefix = OpeningList.scope_fields, "people.opening"


class PipelineView(OSView):
    permissions = {"GET": "people.recruitment.view"}

    def get(self, request, pk):
        ctx = self.authz
        o = m.JobOpening.objects.filter(pk=pk, organization=ctx.organization).select_related("position").first()
        if o is None or not ctx.can("people.recruitment.view", **{k: v for k, v in {"unit": o.position.org_unit_id, "department": o.position.department_id}.items() if v}):
            raise DomainError("Not found.", code="not_found", status_code=404)
        apps = o.applications.select_related("candidate").prefetch_related("interviews__feedback", "offers")
        data = s.ApplicationSerializer(apps, many=True).data
        cols = [{"stage": st, "label": m.Application.Stage(st).label, "items": [a for a in data if a["stage"] == st]}
                for st in m.Application.PIPELINE + ["rejected", "withdrawn"]]
        return Response({"opening": s.OpeningSerializer(o).data, "columns": cols, "can_manage": ctx.has("people.recruitment.edit")})


class CandidateList(ScopedList):
    model, serializer_class = m.Candidate, s.CandidateSerializer
    perms = {"view": "people.candidate.view", "create": "people.recruitment.create"}
    scope_fields = {}
    search_fields, filters = ("full_name", "email", "code", "current_title"), {"talent_pool": "talent_pool", "source": "source"}
    audit_prefix = "people.candidate"

    def get_queryset(self):
        self.authz.require("people.candidate.view")
        return self.base_queryset()


class CandidateDetail(ScopedDetail):
    model, serializer_class = m.Candidate, s.CandidateSerializer
    perms = {"view": "people.candidate.view", "edit": "people.candidate.edit", "delete": "people.recruitment.manage"}
    scope_fields, audit_prefix = {}, "people.candidate"

    def get_queryset(self):
        self.authz.require("people.candidate.view")
        return self.base_queryset()


class ApplicationsView(OSView):
    permissions = {"POST": "people.recruitment.edit"}

    def post(self, request):
        ctx = self.authz
        o = m.JobOpening.objects.filter(pk=request.data.get("opening_id"), organization=ctx.organization, status="open").first()
        c = m.Candidate.objects.filter(pk=request.data.get("candidate_id"), organization=ctx.organization).first()
        if o is None or c is None:
            raise DomainError("Choose an open opening and a candidate.", code="validation_error")
        if m.Application.objects.filter(candidate=c, opening=o).exists():
            raise DomainError("This candidate already applied to this opening.", code="duplicate_application", status_code=409)
        a = m.Application.objects.create(organization=ctx.organization, candidate=c, opening=o)
        m.ApplicationEvent.objects.create(application=a, to_stage="applied", by=request.user)
        record(request, "people.application.create", category="data", module="people", resource=a)
        return Response(s.ApplicationSerializer(a).data, status=status.HTTP_201_CREATED)


class ApplicationMoveView(OSView):
    permissions = {"POST": "people.recruitment.edit"}

    def post(self, request, pk):
        ctx = self.authz
        a = m.Application.objects.filter(pk=pk, organization=ctx.organization).select_related("candidate", "opening").first()
        if a is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        to = request.data.get("stage")
        if to not in m.Application.Stage.values or to in ("accepted", "onboarding"):
            raise DomainError("Accepted and onboarding follow from the offer; choose another stage.", code="validation_error")
        if to == "rejected" and not str(request.data.get("reason", "")).strip():
            raise DomainError("Give a reason for rejecting.", code="reason_required")
        frm = a.stage
        a.stage, a.stage_changed_at = to, timezone.now()
        a.rejection_reason = str(request.data.get("reason", ""))[:200] if to == "rejected" else ""
        a.save()
        m.ApplicationEvent.objects.create(application=a, from_stage=frm, to_stage=to, by=request.user, note=str(request.data.get("note", ""))[:300])
        record(request, "people.application.move", category="data", module="people", resource=a, old={"stage": frm}, new={"stage": to})
        return Response(s.ApplicationSerializer(a).data)


class ApplicationHistoryView(OSView):
    permissions = {"GET": "people.recruitment.view"}

    def get(self, request, pk):
        a = m.Application.objects.filter(pk=pk, organization=self.authz.organization).first()
        if a is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        return Response({"events": [{"from": e.from_stage, "to": e.to_stage, "by": e.by.full_name if e.by_id else None, "note": e.note, "at": e.created_at}
                                    for e in a.events.select_related("by")]})


class InterviewsView(OSView):
    """GET: interviews on my panel (interviewers see only what they need). POST: schedule (recruiters)."""

    def get(self, request):
        ctx = self.authz
        qs = m.Interview.objects.filter(panel=request.user).select_related("application__candidate", "application__opening").prefetch_related("feedback")
        if request.query_params.get("all") == "true":
            ctx.require("people.recruitment.view")
            qs = m.Interview.objects.filter(application__organization=ctx.organization).select_related("application__candidate", "application__opening")
        return Response({"results": [self._row(i, request.user) for i in qs.order_by("-scheduled_at")[:100]]})

    @staticmethod
    def _row(i, user):
        mine = next((f for f in i.feedback.all() if f.interviewer_id == user.pk), None)
        c = i.application.candidate
        return {"id": str(i.pk), "round": i.round_name, "kind": i.kind, "at": i.scheduled_at, "duration": i.duration_minutes, "location": i.location,
                "status": i.status, "criteria": i.criteria, "opening": i.application.opening.title,
                "candidate": {"name": c.full_name, "current_title": c.current_title, "experience_years": c.experience_years, "skills": c.skills[:8]},
                "my_feedback": {"rating": mine.rating, "recommendation": mine.recommendation, "notes": mine.notes, "scores": mine.scores} if mine else None}

    def post(self, request):
        ctx = self.authz
        ctx.require("people.recruitment.edit")
        a = m.Application.objects.filter(pk=request.data.get("application_id"), organization=ctx.organization).first()
        when = parse_datetime(str(request.data.get("scheduled_at") or ""))
        panel = list(User.objects.filter(pk__in=request.data.get("panel_ids") or [], os_account__organization=ctx.organization, os_account__status="active"))
        if a is None or when is None or not panel:
            raise DomainError("Choose the application, a time and at least one interviewer.", code="validation_error")
        i = m.Interview.objects.create(application=a, round_name=str(request.data.get("round_name") or "Interview")[:80],
                                       kind=request.data.get("kind") if request.data.get("kind") in m.Interview.Kind.values else "video",
                                       scheduled_at=when, duration_minutes=int(request.data.get("duration_minutes") or 45),
                                       location=str(request.data.get("location", ""))[:200], criteria=request.data.get("criteria") or [])
        i.panel.set(panel)
        if a.stage in ("applied", "screening", "shortlisted"):
            a.stage, a.stage_changed_at = "interview", timezone.now()
            a.save(update_fields=["stage", "stage_changed_at", "updated_at"])
        notify_many(panel, "task_assigned", f"Interview: {a.candidate.full_name}", body=f"{i.round_name} · {when:%d %b %H:%M}", link="/people/interviews", module="people")
        record(request, "people.interview.schedule", category="data", module="people", resource=i)
        return Response({"id": str(i.pk)}, status=status.HTTP_201_CREATED)


class InterviewFeedbackView(OSView):
    def post(self, request, pk):
        i = m.Interview.objects.filter(pk=pk, panel=request.user).first()
        if i is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        rec = request.data.get("recommendation")
        if rec not in m.InterviewFeedback.Recommendation.values:
            raise DomainError("Choose a recommendation.", code="validation_error")
        rating = request.data.get("rating")
        f, _ = m.InterviewFeedback.objects.update_or_create(interview=i, interviewer=request.user, defaults={
            "recommendation": rec, "rating": int(rating) if rating else None, "scores": request.data.get("scores") or {},
            "notes": str(request.data.get("notes", ""))[:4000]})
        if all(i.feedback.filter(interviewer=u).exists() for u in i.panel.all()):
            i.status = "completed"
            i.save(update_fields=["status", "updated_at"])
        record(request, "people.interview.feedback", category="data", module="people", resource=i)
        return Response({"saved": True})


class InterviewDetailView(OSView):
    permissions = {"GET": "people.recruitment.view"}

    def get(self, request, pk):
        i = m.Interview.objects.filter(pk=pk, application__organization=self.authz.organization).prefetch_related("feedback__interviewer", "panel").first()
        if i is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        return Response({"id": str(i.pk), "round": i.round_name, "at": i.scheduled_at, "status": i.status,
                         "panel": [u.full_name for u in i.panel.all()],
                         "feedback": [{"interviewer": f.interviewer.full_name, "rating": f.rating, "recommendation": f.recommendation, "notes": f.notes,
                                       "scores": f.scores} for f in i.feedback.all()]})


def _offer_row(o: m.Offer, ctx) -> dict:
    pos = o.application.opening.position
    show_pay = ctx.can("people.offer.view", **{k: v for k, v in {"unit": pos.org_unit_id, "department": pos.department_id}.items() if v})
    return {"id": str(o.pk), "code": o.code, "candidate": o.application.candidate.full_name, "opening": o.application.opening.title,
            "joining_date": o.joining_date, "status": o.status, "expires_on": o.expires_on, "approval_id": str(o.approval_id) if o.approval_id else None,
            "designation": o.designation.name if o.designation_id else None, "benefits": o.benefits,
            **({"base_annual": o.base_annual, "variable_annual": o.variable_annual, "joining_bonus": o.joining_bonus, "currency": o.currency} if show_pay else {})}


class OffersView(OSView):
    permissions = {"GET": "people.offer.view", "POST": "people.offer.create"}

    def get(self, request):
        ctx = self.authz
        qs = m.Offer.objects.filter(organization=ctx.organization).select_related("application__candidate", "application__opening__position", "designation")
        return Response({"results": [_offer_row(o, ctx) for o in qs[:200]]})

    def post(self, request):
        ctx, d = self.authz, request.data
        a = m.Application.objects.filter(pk=d.get("application_id"), organization=ctx.organization).select_related("opening__position").first()
        if a is None or a.stage in ("rejected", "withdrawn"):
            raise DomainError("Choose an active application.", code="validation_error")
        try:
            base = Decimal(str(d.get("base_annual")))
        except (InvalidOperation, TypeError):
            raise DomainError("Enter the annual base pay.", code="validation_error", details={"baseAnnual": ["Required."]})
        o = m.Offer.objects.create(organization=ctx.organization, application=a, joining_date=_date(d.get("joining_date"), "joiningDate"), base_annual=base,
                                   variable_annual=Decimal(str(d.get("variable_annual") or 0)), joining_bonus=Decimal(str(d.get("joining_bonus") or 0)),
                                   designation=m.Designation.objects.filter(pk=d.get("designation_id"), organization=ctx.organization).first() if d.get("designation_id") else None,
                                   benefits=str(d.get("benefits", ""))[:500], expires_on=parse_date(str(d.get("expires_on") or "")) or None, created_by=request.user)
        if a.stage != "offer":
            a.stage, a.stage_changed_at = "offer", timezone.now()
            a.save(update_fields=["stage", "stage_changed_at", "updated_at"])
        record(request, "people.offer.create", category="financial", module="people", resource=o, sensitive=True)
        if d.get("submit"):
            svc.submit_offer(request, ctx, o)
        return Response(_offer_row(o, ctx), status=status.HTTP_201_CREATED)


class OfferActionView(OSView):
    def post(self, request, pk, action):
        ctx = self.authz
        o = m.Offer.objects.filter(pk=pk, organization=ctx.organization).select_related("application__candidate", "application__opening__position").first()
        if o is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        if action == "submit":
            svc.submit_offer(request, ctx, o)
        elif action == "release":
            ctx.require("people.offer.create")
            if o.status != "approved":
                raise DomainError("Only approved offers can be released.", code="invalid_state", status_code=409)
            o.status = "released"
            o.save(update_fields=["status", "updated_at"])
        elif action == "respond":
            ctx.require("people.offer.create")
            if request.data.get("response") == "accepted":
                emp = svc.accept_offer(request, ctx, o, work_email=str(request.data.get("work_email", "")).strip(), invite=bool(request.data.get("invite", True)))
                return Response(_offer_row(o, ctx) | {"employee_id": str(emp.pk)})
            if o.status != "released":
                raise DomainError("Only released offers can be declined.", code="invalid_state", status_code=409)
            o.status, o.responded_on = "declined", timezone.localdate()
            o.save(update_fields=["status", "responded_on", "updated_at"])
        elif action == "withdraw":
            ctx.require("people.offer.create")
            o.status = "withdrawn"
            o.save(update_fields=["status", "updated_at"])
        else:
            raise DomainError("Not found.", code="not_found", status_code=404)
        record(request, f"people.offer.{action}", category="data", module="people", resource=o)
        return Response(_offer_row(o, ctx))


class OnboardingView(OSView):
    permissions = {"GET": "people.onboarding.view", "POST": "people.onboarding.manage"}

    def get(self, request):
        ctx = self.authz
        kind = request.query_params.get("kind", "onboarding")
        qs = m.LifecyclePlan.objects.filter(employee__organization=ctx.organization, kind=kind).filter(related_q(ctx, "people.onboarding.view")) \
            .select_related("employee", "template")
        if request.query_params.get("status") != "all":
            qs = qs.filter(status="in_progress")
        return Response({"results": [{"id": str(p.pk), "employee": {"id": str(p.employee_id), "name": p.employee.display_name},
                                      "template": p.template.name if p.template_id else None, "started_on": p.started_on, "status": p.status,
                                      "joined_on": p.employee.joined_on, **svc.plan_progress(p)} for p in qs[:100]]})

    def post(self, request):
        ctx = self.authz
        e = _emp(ctx, request.data.get("employee_id"))
        require_on(ctx, "people.onboarding.manage", e)
        kind = request.data.get("kind") if request.data.get("kind") in ("onboarding", "offboarding") else "onboarding"
        tpl = m.ChecklistTemplate.objects.filter(pk=request.data.get("template_id"), organization=ctx.organization, kind=kind).first() if request.data.get("template_id") else None
        plan = svc.start_plan(request, e, kind, tpl)
        if plan is None:
            raise DomainError("Create a checklist template first (HR settings).", code="no_template", status_code=409)
        record(request, f"people.{kind}.start", category="data", module="people", resource=e)
        return Response({"id": str(plan.pk)}, status=status.HTTP_201_CREATED)


# =============================================================================================================
# Attendance
# =============================================================================================================
def _att(r):
    return {"date": r.date, "check_in": r.check_in, "check_out": r.check_out, "status": r.status, "mode": r.mode, "late": r.late,
            "early": r.early_departure, "worked_minutes": r.worked_minutes, "source": r.source, "note": r.note}


class MyAttendanceView(OSView):
    def get(self, request):
        ctx = self.authz
        e = employee_of(ctx)
        y, mo = int(request.query_params.get("year") or timezone.localdate().year), int(request.query_params.get("month") or timezone.localdate().month)
        start = timezone.localdate().replace(year=y, month=mo, day=1)
        end = (start + timedelta(days=32)).replace(day=1)
        recs = m.AttendanceRecord.objects.filter(employee=e, date__gte=start, date__lt=end)
        today = m.AttendanceRecord.objects.filter(employee=e, date=timezone.localdate()).first()
        return Response({"today": _att(today) if today else None, "records": [_att(r) for r in recs],
                         "holidays": [{"date": d, "name": n} for d, n in svc.holidays_between(e, start, end - timedelta(days=1)).items()],
                         "working_days": sorted(svc.working_weekdays(e)), "schedule": e.schedule.name if e.schedule_id else "Standard (Mon–Fri)",
                         "corrections": [{"id": str(c.pk), "date": c.date, "status": c.status, "reason": c.reason, "approval_id": str(c.approval_id) if c.approval_id else None}
                                         for c in e.attendance_corrections.all()[:20]],
                         "can_check_in": ctx.has("people.attendance.create")})


class CheckView(OSView):
    def post(self, request, action):
        ctx = self.authz
        e = employee_of(ctx)
        rec = svc.check_in(request, ctx, e, request.data.get("mode", "office")) if action == "in" else svc.check_out(request, ctx, e)
        record(request, f"people.attendance.check_{action}", category="data", module="people", resource=e)
        return Response(_att(rec))


class TeamAttendanceView(OSView):
    permissions = {"GET": "people.attendance.view"}

    def get(self, request):
        ctx = self.authz
        day = parse_date(request.query_params.get("date", "") or "") or timezone.localdate()
        emps = m.Employee.objects.filter(organization=ctx.organization, status__in=m.Employee.WORKING).filter(employees_q(ctx, "people.attendance.view")) \
            .select_related("designation", "org_unit")
        recs = {r.employee_id: r for r in m.AttendanceRecord.objects.filter(employee__in=emps, date=day)}
        away = set(m.LeaveRequest.objects.filter(employee__in=emps, status="approved", start_date__lte=day, end_date__gte=day).values_list("employee_id", flat=True))
        rows = [{"employee": {"id": str(e.pk), "name": e.display_name, "designation": getattr(e.designation, "name", None)},
                 "record": _att(recs[e.pk]) if e.pk in recs else None, "on_leave": e.pk in away} for e in emps[:300]]
        exc = svc.attendance_exceptions(ctx.organization, emps, day)
        return Response({"date": day, "results": rows, "exceptions": [{"employee": x["employee"].display_name, "employee_id": str(x["employee"].pk),
                                                                       "kind": x["kind"], "label": x["label"]} for x in exc]})


class CorrectionView(OSView):
    def post(self, request):
        ctx = self.authz
        e = _emp(ctx, request.data.get("employee_id")) if request.data.get("employee_id") else employee_of(ctx)
        d = _date(request.data.get("date"), "date")
        tz = timezone.get_current_timezone()

        def at(v):
            if not v:
                return None
            t = datetime.strptime(str(v)[:5], "%H:%M").time() if len(str(v)) <= 8 else None
            return datetime.combine(d, t, tzinfo=tz) if t else parse_datetime(str(v))

        c = svc.submit_correction(request, ctx, e, d, at(request.data.get("check_in")), at(request.data.get("check_out")), str(request.data.get("reason", "")))
        return Response({"id": str(c.pk), "status": c.status, "approval_id": str(c.approval_id)}, status=status.HTTP_201_CREATED)


# =============================================================================================================
# Leave
# =============================================================================================================
class LeaveTypesView(OSView):
    """Leave types that apply to me (or to an employee HR is acting for)."""

    def get(self, request):
        ctx = self.authz
        e = _emp(ctx, request.query_params["employee"]) if request.query_params.get("employee") else employee_of(ctx)
        if not (is_self(ctx, e) or can_on(ctx, "people.leave.manage", e)):
            raise DomainError("Not found.", code="not_found", status_code=404)
        return Response({"results": s.LeaveTypeSerializer(svc.eligible_types(e), many=True).data})


class MyLeaveView(OSView):
    def get(self, request):
        from .views import _tab_leave

        ctx = self.authz
        e = employee_of(ctx)
        data = _tab_leave(ctx, e)
        yr = timezone.localdate().year
        data["holidays"] = [{"date": h.date, "name": h.name, "optional": h.optional, "calendar": h.calendar.name}
                            for h in m.Holiday.objects.filter(calendar__in=svc.calendars_for(e), date__year=yr).select_related("calendar")]
        return Response(data)


class LeavePreviewView(OSView):
    def get(self, request):
        ctx = self.authz
        e = _emp(ctx, request.query_params["employee"]) if request.query_params.get("employee") else employee_of(ctx)
        start, end = _date(request.query_params.get("start"), "start"), _date(request.query_params.get("end"), "end")
        days = svc.working_days(e, start, end, request.query_params.get("half", ""))
        return Response({"days": str(days.normalize()) if days == days.to_integral() else str(days), "holidays": [{"date": d, "name": n} for d, n in svc.holidays_between(e, start, end).items()]})


class LeaveRequestsView(OSView):
    def post(self, request):
        ctx = self.authz
        d = request.data
        e = _emp(ctx, d.get("employee_id")) if d.get("employee_id") else employee_of(ctx)
        lt = m.LeaveType.objects.filter(pk=d.get("leave_type_id"), organization=ctx.organization, is_active=True).first()
        if lt is None:
            raise DomainError("Choose a leave type.", code="validation_error", details={"leaveTypeId": ["Required."]})
        lr = svc.submit_leave(request, ctx, e, lt, _date(d.get("start_date"), "startDate"), _date(d.get("end_date") or d.get("start_date"), "endDate"),
                              d.get("half_day", "") if d.get("half_day") in ("first", "second") else "", str(d.get("reason", "")))
        return Response(s.LeaveRequestSerializer(lr).data, status=status.HTTP_201_CREATED)


class LeaveCancelView(OSView):
    def post(self, request, pk):
        ctx = self.authz
        lr = m.LeaveRequest.objects.filter(pk=pk, employee__organization=ctx.organization).select_related("employee", "leave_type", "approval").first()
        if lr is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        lr = svc.cancel_leave(request, ctx, lr)
        return Response(s.LeaveRequestSerializer(lr).data)


class TeamLeaveView(OSView):
    permissions = {"GET": "people.leave.view"}

    def get(self, request):
        ctx = self.authz
        start = parse_date(request.query_params.get("from", "") or "") or timezone.localdate() - timedelta(days=7)
        end = parse_date(request.query_params.get("to", "") or "") or start + timedelta(days=45)
        qs = m.LeaveRequest.objects.filter(employee__organization=ctx.organization, status__in=["approved", "pending"], start_date__lte=end,
                                           end_date__gte=start).filter(related_q(ctx, "people.leave.view")).select_related("employee", "leave_type")
        today = timezone.localdate()
        return Response({"from": start, "to": end, "results": s.LeaveRequestSerializer(qs.order_by("start_date")[:500], many=True).data,
                         "away_today": qs.filter(status="approved", start_date__lte=today, end_date__gte=today).count()})


class BalanceAdjustView(OSView):
    permissions = {"POST": "people.leave.manage"}

    def post(self, request, pk):
        ctx = self.authz
        b = m.LeaveBalance.objects.filter(pk=pk, employee__organization=ctx.organization).select_related("employee").first()
        if b is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        require_on(ctx, "people.leave.manage", b.employee)
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            raise DomainError("Give a reason for the adjustment.", code="reason_required")
        before = str(b.adjusted)
        b.adjusted += Decimal(str(request.data.get("days") or 0))
        b.save(update_fields=["adjusted", "updated_at"])
        record(request, "people.leave.balance_adjust", category="data", module="people", resource=b.employee, old={"adjusted": before},
               new={"adjusted": str(b.adjusted), "reason": reason})
        return Response({"available": b.available})


class HolidayView(OSView):
    permissions = {"POST": "people.schedule.manage", "DELETE": "people.schedule.manage"}

    def post(self, request):
        cal = m.HolidayCalendar.objects.filter(pk=request.data.get("calendar"), organization=self.authz.organization).first()
        if cal is None:
            raise DomainError("Choose a calendar.", code="validation_error")
        h = m.Holiday.objects.create(calendar=cal, date=_date(request.data.get("date"), "date"), name=str(request.data.get("name", ""))[:80] or "Holiday",
                                     optional=bool(request.data.get("optional")))
        record(request, "people.holiday.create", category="config", module="people", resource=h)
        return Response(s.HolidaySerializer(h).data, status=status.HTTP_201_CREATED)

    def delete(self, request, pk=None):
        h = m.Holiday.objects.filter(pk=pk, calendar__organization=self.authz.organization).first()
        if h is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        h.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# =============================================================================================================
# Performance
# =============================================================================================================
class CycleList(ScopedList):
    model, serializer_class = m.ReviewCycle, s.ReviewCycleSerializer
    perms = {"view": "people.performance.view", "create": "people.performance.manage"}
    scope_fields, audit_prefix = {}, "people.review_cycle"

    def get_queryset(self):
        return self.base_queryset()  # cycle names and dates aren't sensitive


class CycleDetail(ScopedDetail):
    model, serializer_class = m.ReviewCycle, s.ReviewCycleSerializer
    perms = {"view": "people.performance.view", "edit": "people.performance.manage", "delete": "people.performance.manage"}
    scope_fields, audit_prefix = {}, "people.review_cycle"

    def get_queryset(self):
        return self.base_queryset()

    def require_on(self, code, obj):
        self.authz.require(code)


class CycleLaunchView(OSView):
    """Creates self and manager reviews (and peer requests when enabled) for every working employee in the caller's scope."""

    permissions = {"POST": "people.performance.manage"}

    def post(self, request, pk):
        ctx = self.authz
        c = m.ReviewCycle.objects.filter(pk=pk, organization=ctx.organization).first()
        if c is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        emps = m.Employee.objects.filter(organization=ctx.organization, status__in=m.Employee.WORKING).filter(employees_q(ctx, "people.performance.manage")) \
            .select_related("manager__user", "user")
        n = 0
        with transaction.atomic():
            for e in emps:
                if e.user_id:
                    _, made = m.Review.objects.get_or_create(cycle=c, employee=e, reviewer=e.user, kind="self", defaults={"due_on": c.self_review_due})
                    n += made
                if e.manager_id and e.manager.user_id:
                    _, made = m.Review.objects.get_or_create(cycle=c, employee=e, reviewer=e.manager.user, kind="manager", defaults={"due_on": c.manager_review_due})
                    n += made
            c.status = "active"
            c.save(update_fields=["status", "updated_at"])
        users = User.objects.filter(hr_reviews_to_write__cycle=c, hr_reviews_to_write__status="pending").distinct()
        notify_many(list(users), "deadline", f"{c.name}: reviews are open", body=f"Self reviews due {c.self_review_due or 'soon'}", link="/people/performance", module="people")
        record(request, "people.review_cycle.launch", category="data", module="people", resource=c, metadata={"reviews": n})
        return Response({"reviews_created": n, "status": c.status})


def _review_row(r, user):
    return {"id": str(r.pk), "cycle": r.cycle.name, "employee": {"id": str(r.employee_id), "name": r.employee.display_name}, "kind": r.kind,
            "kind_label": r.get_kind_display(), "status": r.status, "due_on": r.due_on, "rating": r.rating, "strengths": r.strengths,
            "improvements": r.improvements, "comments": r.comments, "submitted_at": r.submitted_at, "mine": r.reviewer_id == user.pk}


class MyReviewsView(OSView):
    def get(self, request):
        qs = m.Review.objects.filter(reviewer=request.user).select_related("cycle", "employee").order_by("status", "due_on")
        return Response({"results": [_review_row(r, request.user) for r in qs[:100]]})


class ReviewView(OSView):
    def patch(self, request, pk):
        r = m.Review.objects.filter(pk=pk, reviewer=request.user).select_related("cycle", "employee").first()
        if r is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        if r.status == "submitted":
            raise DomainError("This review was already submitted.", code="already_submitted", status_code=409)
        if r.cycle.status != "active":
            raise DomainError("This review cycle isn’t open.", code="cycle_closed", status_code=409)
        d = request.data
        for f in ("strengths", "improvements", "comments"):
            if f in d:
                setattr(r, f, str(d[f])[:3000])
        if "rating" in d:
            if d["rating"] is not None and int(d["rating"]) not in range(1, 6):
                raise DomainError("Rating must be 1 to 5.", code="validation_error")
            r.rating = int(d["rating"]) if d["rating"] is not None else None
        if d.get("submit"):
            if r.kind != "peer" and r.rating is None:
                raise DomainError("Give a rating before submitting.", code="validation_error")
            r.status, r.submitted_at = "submitted", timezone.now()
            record(request, "people.review.submit", category="data", module="people", resource=r.employee, metadata={"kind": r.kind, "cycle": r.cycle.name})
            if r.kind == "manager" and r.employee.user_id:
                notify(r.employee.user, "workflow", f"Your manager submitted your {r.cycle.name} review", link="/people/performance", module="people")
        r.save()
        return Response(_review_row(r, request.user))


def _goal_visible_q(ctx):
    q = Q(level__in=["company", "business_unit", "department", "team"]) | Q(employee__user=ctx.user)
    if ctx.has("people.goal.view"):
        q |= Q(employee__isnull=False) & related_q(ctx, "people.goal.view")
    return q


class GoalsView(OSView):
    def get(self, request):
        ctx = self.authz
        qs = m.Goal.objects.filter(organization=ctx.organization).filter(_goal_visible_q(ctx)).select_related("employee")
        p = request.query_params
        if p.get("employee"):
            qs = qs.filter(employee_id=p["employee"])
        if p.get("level"):
            qs = qs.filter(level=p["level"])
        if p.get("parent"):
            qs = qs.filter(parent_id=None if p["parent"] == "none" else p["parent"])
        if p.get("cycle"):
            qs = qs.filter(cycle_id=p["cycle"])
        return Response({"results": s.GoalSerializer(qs[:300], many=True).data})

    def post(self, request):
        ctx = self.authz
        ser = s.GoalSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        emp = v.get("employee")
        if v["level"] == "employee":
            emp = emp or employee_of(ctx)
            if not (is_self(ctx, emp) or can_on(ctx, "people.goal.create", emp)):
                raise DomainError("You can set goals for yourself and the people in your scope.", code="permission_denied", status_code=403)
        else:
            ctx.require("people.performance.manage")
        g = ser.save(organization=ctx.organization, owner=request.user, employee=emp if v["level"] == "employee" else None)
        record(request, "people.goal.create", category="data", module="people", resource=g)
        return Response(s.GoalSerializer(g).data, status=status.HTTP_201_CREATED)


class GoalDetailView(OSView):
    def patch(self, request, pk):
        ctx = self.authz
        g = m.Goal.objects.filter(pk=pk, organization=ctx.organization).select_related("employee").first()
        if g is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        ok = (g.employee_id and (is_self(ctx, g.employee) or can_on(ctx, "people.goal.edit", g.employee))) or (not g.employee_id and ctx.has("people.performance.manage"))
        if not ok:
            raise DomainError("You can’t edit this goal.", code="permission_denied", status_code=403)
        ser = s.GoalSerializer(g, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        g = ser.save()
        return Response(s.GoalSerializer(g).data)


class FeedbackView(OSView):
    def get(self, request):
        ctx = self.authz
        if request.query_params.get("wall") == "true":
            qs = m.Feedback.objects.filter(organization=ctx.organization, kind="recognition", visibility="public").select_related("employee", "author")
        else:
            qs = m.Feedback.objects.filter(organization=ctx.organization, author=request.user).select_related("employee", "author")
        return Response({"results": [{"id": str(f.pk), "kind": f.kind, "badge": f.badge, "body": f.body, "to": f.employee.display_name, "to_id": str(f.employee_id),
                                      "from": f.author.full_name if f.author_id else None, "at": f.created_at, "visibility": f.visibility} for f in qs[:100]]})

    def post(self, request):
        ctx = self.authz
        ctx.require("people.feedback.create")
        e = _emp(ctx, request.data.get("employee_id"))
        if is_self(ctx, e):
            raise DomainError("You can’t give feedback to yourself.", code="validation_error")
        kind = request.data.get("kind") if request.data.get("kind") in m.Feedback.Kind.values else "feedback"
        vis = request.data.get("visibility") if request.data.get("visibility") in m.Feedback.Visibility.values else ("public" if kind == "recognition" else "private")
        if kind == "note":
            require_on(ctx, "people.performance.review", e)
            vis = "manager_only"
        body = str(request.data.get("body", "")).strip()
        if len(body) < 3:
            raise DomainError("Write a few words.", code="validation_error")
        f = m.Feedback.objects.create(organization=ctx.organization, author=request.user, employee=e, kind=kind, visibility=vis, body=body[:2000],
                                      badge=str(request.data.get("badge", ""))[:40])
        if e.user_id and vis != "manager_only":
            notify(e.user, "workflow", f"{request.user.full_name} {'recognised you' if kind == 'recognition' else 'shared feedback'}", body=body[:200],
                   link="/people/performance", module="people")
        return Response({"id": str(f.pk)}, status=status.HTTP_201_CREATED)


# =============================================================================================================
# Learning
# =============================================================================================================
class CourseList(ScopedList):
    model, serializer_class = m.Course, s.CourseSerializer
    perms = {"view": "people.directory.view", "create": "people.learning.manage"}
    scope_fields, search_fields, audit_prefix = {}, ("title", "provider"), "people.course"

    def get_queryset(self):
        return self.base_queryset().filter(is_active=True) if not self.authz.has("people.learning.manage") else self.base_queryset()


class CourseDetail(ScopedDetail):
    model, serializer_class = m.Course, s.CourseSerializer
    perms = {"view": "people.directory.view", "edit": "people.learning.manage", "delete": "people.learning.manage"}
    scope_fields, audit_prefix = {}, "people.course"

    def get_queryset(self):
        return self.base_queryset()

    def require_on(self, code, obj):
        self.authz.require(code)


class EnrollView(OSView):
    def post(self, request):
        ctx = self.authz
        c = m.Course.objects.filter(pk=request.data.get("course_id"), organization=ctx.organization).first()
        if c is None:
            raise DomainError("Choose a course.", code="validation_error")
        ids = request.data.get("employee_ids") or []
        if not ids:  # self-enrol
            e = employee_of(ctx)
            ids = [str(e.pk)]
        due = parse_date(str(request.data.get("due_on") or "")) or None
        n = 0
        for e in m.Employee.objects.filter(organization=ctx.organization, pk__in=ids):
            if not is_self(ctx, e):
                require_on(ctx, "people.learning.assign", e)
            _, made = m.Enrollment.objects.get_or_create(course=c, employee=e, defaults={"due_on": due, "assigned_by": request.user})
            n += made
            if made and e.user_id and not is_self(ctx, e):
                notify(e.user, "task_assigned", f"Training assigned: {c.title}", body=f"Due {due:%d %b}" if due else "", link="/people/learning", module="people")
        return Response({"enrolled": n}, status=status.HTTP_201_CREATED)


class EnrollmentView(OSView):
    def patch(self, request, pk):
        ctx = self.authz
        x = m.Enrollment.objects.filter(pk=pk, employee__organization=ctx.organization).select_related("employee").first()
        if x is None or not (is_self(ctx, x.employee) or can_on(ctx, "people.learning.manage", x.employee)):
            raise DomainError("Not found.", code="not_found", status_code=404)
        st = request.data.get("status")
        if st in m.Enrollment.Status.values:
            x.status = st
            x.completed_at = timezone.now() if st == "completed" else None
        x.save()
        return Response({"status": x.status})


class SkillList(ScopedList):
    model, serializer_class = m.Skill, s.SkillSerializer
    perms = {"view": "people.directory.view", "create": "people.learning.manage"}
    scope_fields, search_fields, audit_prefix = {}, ("name",), "people.skill"

    def get_queryset(self):
        return self.base_queryset()


class EmployeeSkillView(OSView):
    """PUT {skill_id, proficiency, evidence}. Self-ratings stay labelled self-assessed; managers/HR record assessed ratings."""

    def put(self, request, pk):
        ctx = self.authz
        e = _emp(ctx, pk)
        own = is_self(ctx, e)
        if not (own or can_on(ctx, "people.learning.verify", e) or can_on(ctx, "people.performance.review", e)):
            raise DomainError("You can’t rate this person’s skills.", code="permission_denied", status_code=403)
        sk = m.Skill.objects.filter(pk=request.data.get("skill_id"), organization=ctx.organization).first()
        lvl = int(request.data.get("proficiency") or 0)
        if sk is None or lvl not in range(1, 6):
            raise DomainError("Choose a skill and a level from 1 to 5.", code="validation_error")
        obj, _ = m.EmployeeSkill.objects.update_or_create(employee=e, skill=sk, defaults={
            "proficiency": lvl, "source": "self" if own else ("assessment" if request.data.get("assessment") else "manager"),
            "assessed_by": None if own else request.user, "assessed_on": timezone.localdate(), "evidence": str(request.data.get("evidence", ""))[:300]})
        return Response({"id": str(obj.pk), "source": obj.source})

    patch = put


class CertificationsView(OSView):
    def post(self, request, pk):
        ctx = self.authz
        e = _emp(ctx, pk)
        if not (is_self(ctx, e) or can_on(ctx, "people.learning.manage", e)):
            raise DomainError("Not found.", code="not_found", status_code=404)
        name = str(request.data.get("name", "")).strip()
        if not name:
            raise DomainError("Name the certification.", code="validation_error")
        c = m.Certification.objects.create(employee=e, name=name[:160], provider=str(request.data.get("provider", ""))[:80],
                                           credential_id=str(request.data.get("credential_id", ""))[:80],
                                           issued_on=parse_date(str(request.data.get("issued_on") or "")) or None,
                                           expires_on=parse_date(str(request.data.get("expires_on") or "")) or None)
        record(request, "people.certification.create", category="data", module="people", resource=e, new={"name": c.name})
        return Response({"id": str(c.pk)}, status=status.HTTP_201_CREATED)


class CertificationVerifyView(OSView):
    def post(self, request, pk):
        ctx = self.authz
        c = m.Certification.objects.filter(pk=pk, employee__organization=ctx.organization).select_related("employee").first()
        if c is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        require_on(ctx, "people.learning.verify", c.employee)
        if is_self(ctx, c.employee):
            raise DomainError("You can’t verify your own certification.", code="permission_denied", status_code=403)
        c.verification = "verified" if request.data.get("verified", True) else "rejected"
        c.verified_by = request.user
        c.save(update_fields=["verification", "verified_by", "updated_at"])
        return Response({"verification": c.verification})


class CertificationsListView(OSView):
    def get(self, request):
        ctx = self.authz
        qs = m.Certification.objects.filter(employee__organization=ctx.organization).select_related("employee")
        qs = qs.filter(Q(employee__user=request.user) | (related_q(ctx, "people.learning.view") if ctx.has("people.learning.view") else Q(pk__in=[])))
        if request.query_params.get("expiring") == "true":
            qs = qs.filter(expires_on__lte=timezone.localdate() + timedelta(days=60))
        return Response({"results": [{"id": str(c.pk), "name": c.name, "provider": c.provider, "employee": c.employee.display_name, "employee_id": str(c.employee_id),
                                      "issued_on": c.issued_on, "expires_on": c.expires_on, "verification": c.verification,
                                      "mine": c.employee.user_id == request.user.pk} for c in qs.order_by("expires_on")[:300]]})


# =============================================================================================================
# Compensation, benefits, payroll integration (restricted)
# =============================================================================================================
class CompensationOverviewView(OSView):
    permissions = {"GET": "people.payroll.view"}

    def get(self, request):
        ctx = self.authz
        emps = m.Employee.objects.filter(organization=ctx.organization, status__in=m.Employee.WORKING).filter(employees_q(ctx, "people.payroll.view"))
        latest = {}
        for c in m.CompensationRecord.objects.filter(employee__in=emps).order_by("employee_id", "-effective_date"):
            latest.setdefault(c.employee_id, c)
        record(request, "people.compensation.overview", category="financial", module="people", sensitive=True, metadata={"employees": len(latest)})
        names = {e.pk: e for e in emps.select_related("department", "designation")}
        rows = [{"employee": {"id": str(pk), "name": names[pk].display_name}, "department": getattr(names[pk].department, "name", None),
                 "designation": getattr(names[pk].designation, "name", None), "currency": c.currency, "base_annual": c.base_annual,
                 "variable_target": c.variable_target, "effective_date": c.effective_date} for pk, c in latest.items() if pk in names]
        return Response({"results": rows, "missing": [names[pk].display_name for pk in names if pk not in latest][:50],
                         "payroll_provider": settings.CLICK_PAYROLL_PROVIDER or None})


class PayrollInputsView(OSView):
    """Integration-ready payroll inputs for a month: attendance, paid/unpaid leave and current pay. No payroll is
    calculated here — Finance / the payroll provider stays the authoritative source for payments."""

    permissions = {"GET": "people.payroll.export"}

    def get(self, request):
        ctx = self.authz
        today = timezone.localdate()
        y, mo = int(request.query_params.get("year") or today.year), int(request.query_params.get("month") or today.month)
        start = today.replace(year=y, month=mo, day=1)
        end = (start + timedelta(days=32)).replace(day=1)
        emps = m.Employee.objects.filter(organization=ctx.organization).filter(Q(status__in=m.Employee.WORKING) | Q(exit_date__gte=start)).filter(
            employees_q(ctx, "people.payroll.export")).select_related("department")
        rows = []
        for e in emps:
            att = m.AttendanceRecord.objects.filter(employee=e, date__gte=start, date__lt=end)
            leaves = m.LeaveRequest.objects.filter(employee=e, status="approved", start_date__lt=end, end_date__gte=start).select_related("leave_type")
            paid = sum((lr.days for lr in leaves if lr.leave_type.paid), Decimal("0"))
            unpaid = sum((lr.days for lr in leaves if not lr.leave_type.paid), Decimal("0"))
            comp = e.compensation.filter(effective_date__lt=end).first()
            rows.append({"employee_id": e.employee_id, "name": e.full_name, "department": getattr(e.department, "name", ""),
                         "working_days": str(svc.working_days(e, start, end - timedelta(days=1))), "present_days": att.filter(status="present").count(),
                         "paid_leave_days": str(paid), "unpaid_leave_days": str(unpaid), "base_annual": str(comp.base_annual) if comp else "",
                         "currency": comp.currency if comp else "", "status": e.status, "exit_date": e.exit_date or ""})
        record(request, "people.payroll.inputs_export", category="export", module="people", sensitive=True, metadata={"month": f"{y}-{mo:02d}", "rows": len(rows)})
        if request.query_params.get("export") == "csv":
            out = io.StringIO()
            w = csv.DictWriter(out, fieldnames=list(rows[0].keys()) if rows else ["employee_id"])
            w.writeheader()
            w.writerows(rows)
            resp = HttpResponse(out.getvalue(), content_type="text/csv")
            resp["Content-Disposition"] = f'attachment; filename="payroll-inputs-{y}-{mo:02d}.csv"'
            return resp
        return Response({"month": f"{y}-{mo:02d}", "results": rows,
                         "note": "Inputs only. Payroll is calculated by the payroll provider / Finance, which stays the authoritative record of payments."})


class SalaryRevisionView(OSView):
    def post(self, request, pk):
        ctx = self.authz
        e = _emp(ctx, pk)
        require_on(ctx, "people.payroll.manage", e)
        ch = svc.submit_change(request, ctx, e, "salary_revision", {}, {"base_annual": str(request.data.get("base_annual")),
                                                                        "variable_target": str(request.data.get("variable_target") or 0),
                                                                        "currency": request.data.get("currency", "INR")},
                               _date(request.data.get("effective_date"), "effectiveDate"), str(request.data.get("reason", "")))
        return Response({"id": str(ch.pk), "status": ch.status, "approval_id": str(ch.approval_id)}, status=status.HTTP_201_CREATED)


class BenefitList(ScopedList):
    model, serializer_class = m.BenefitPlan, s.BenefitPlanSerializer
    perms = {"view": "people.benefit.view", "create": "people.benefit.manage"}
    scope_fields, audit_prefix = {}, "people.benefit"

    def get_queryset(self):
        self.authz.require("people.benefit.view")
        return self.base_queryset()


class BenefitDetail(ScopedDetail):
    model, serializer_class = m.BenefitPlan, s.BenefitPlanSerializer
    perms = {"view": "people.benefit.view", "edit": "people.benefit.manage", "delete": "people.benefit.manage"}
    scope_fields, audit_prefix = {}, "people.benefit"

    def get_queryset(self):
        self.authz.require("people.benefit.view")
        return self.base_queryset()

    def require_on(self, code, obj):
        self.authz.require(code)


class BenefitEnrollView(OSView):
    permissions = {"POST": "people.benefit.manage"}

    def post(self, request, pk):
        ctx = self.authz
        plan = m.BenefitPlan.objects.filter(pk=pk, organization=ctx.organization, is_active=True).first()
        e = _emp(ctx, request.data.get("employee_id"))
        if plan is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        if plan.worker_types and e.worker_type not in plan.worker_types:
            raise DomainError("This plan doesn’t apply to this worker type.", code="not_eligible")
        require_on(ctx, "people.benefit.manage", e)
        b, _ = m.EmployeeBenefit.objects.update_or_create(employee=e, plan=plan, defaults={"enrolled_on": timezone.localdate(), "status": "active",
                                                                                          "details": str(request.data.get("details", ""))[:300]})
        record(request, "people.benefit.enroll", category="data", module="people", resource=e, new={"plan": plan.name})
        return Response({"id": str(b.pk)}, status=status.HTTP_201_CREATED)


# =============================================================================================================
# Engagement
# =============================================================================================================
class SurveyList(ScopedList):
    model, serializer_class = m.Survey, s.SurveySerializer
    perms = {"view": "people.engagement.manage", "create": "people.engagement.manage"}
    scope_fields, audit_prefix = {}, "people.survey"

    def get_queryset(self):
        self.authz.require("people.engagement.manage")
        return self.base_queryset()

    def perform_create(self, ser):
        return ser.save(organization=self.authz.organization, created_by=self.request.user)


class SurveyDetail(ScopedDetail):
    model, serializer_class = m.Survey, s.SurveySerializer
    perms = {"view": "people.engagement.manage", "edit": "people.engagement.manage", "delete": "people.engagement.manage"}
    scope_fields, audit_prefix = {}, "people.survey"

    def get_queryset(self):
        self.authz.require("people.engagement.manage")
        return self.base_queryset()

    def require_on(self, code, obj):
        self.authz.require(code)


class OpenSurveysView(OSView):
    def get(self, request):
        ctx = self.authz
        today = timezone.localdate()
        done = set(m.SurveyParticipation.objects.filter(user=request.user).values_list("survey_id", flat=True))
        qs = m.Survey.objects.filter(organization=ctx.organization, status="open", opens_on__lte=today).filter(Q(closes_on__isnull=True) | Q(closes_on__gte=today))
        return Response({"results": [{"id": str(x.pk), "title": x.title, "description": x.description, "anonymous": x.anonymous, "closes_on": x.closes_on,
                                      "questions": x.questions, "answered": x.pk in done} for x in qs]})


class SurveyRespondView(OSView):
    def post(self, request, pk):
        ctx = self.authz
        x = m.Survey.objects.filter(pk=pk, organization=ctx.organization, status="open").first()
        if x is None:
            raise DomainError("This survey is closed.", code="not_found", status_code=404)
        answers = {q["id"]: request.data.get("answers", {}).get(q["id"]) for q in x.questions}
        with transaction.atomic():
            _, made = m.SurveyParticipation.objects.get_or_create(survey=x, user=request.user)
            if not made:
                raise DomainError("You’ve already answered this survey.", code="already_answered", status_code=409)
            m.SurveyResponse.objects.create(survey=x, respondent=None if x.anonymous else request.user, answers=answers,
                                            department=ctx.employee.department if ctx.employee else None)
        return Response({"thanks": True}, status=status.HTTP_201_CREATED)


class SurveyResultsView(OSView):
    permissions = {"GET": "people.engagement.manage"}

    def get(self, request, pk):
        x = m.Survey.objects.filter(pk=pk, organization=self.authz.organization).first()
        if x is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        resp = list(x.responses.all())
        if len(resp) < x.min_group:
            return Response({"responses": len(resp), "suppressed": True, "message": f"Results appear once at least {x.min_group} people have answered."})
        out = []
        for q in x.questions:
            vals = [r.answers.get(q["id"]) for r in resp if r.answers.get(q["id"]) not in (None, "")]
            if q["type"] == "scale":
                nums = [float(v) for v in vals if str(v).replace(".", "", 1).isdigit()]
                out.append({"id": q["id"], "text": q["text"], "type": "scale", "average": round(sum(nums) / len(nums), 2) if nums else None, "answers": len(nums)})
            elif q["type"] == "choice":
                counts: dict = {}
                for v in vals:
                    counts[v] = counts.get(v, 0) + 1
                out.append({"id": q["id"], "text": q["text"], "type": "choice", "counts": counts})
            else:
                out.append({"id": q["id"], "text": q["text"], "type": "text", "answers": vals[:200]})
        by_dept = {}
        for r in resp:
            k = r.department.name if r.department_id else "Not set"
            by_dept[k] = by_dept.get(k, 0) + 1
        return Response({"responses": len(resp), "suppressed": False, "questions": out,
                         "by_department": [{"label": k, "value": v if v >= x.min_group else None} for k, v in by_dept.items()]})


# =============================================================================================================
# HR requests (service desk) and employee relations cases
# =============================================================================================================
class HRRequestsView(OSView):
    def get(self, request):
        ctx = self.authz
        view = request.query_params.get("view", "mine")
        qs = m.HRRequest.objects.filter(organization=ctx.organization).select_related("employee", "assignee")
        if view == "queue":
            ctx.require("people.request.manage")
            qs = qs.filter(related_q(ctx, "people.request.manage")).exclude(status="closed")
        elif view == "assigned":
            qs = qs.filter(assignee=request.user).exclude(status="closed")
        else:
            qs = qs.filter(employee__user=request.user)
        if st := request.query_params.get("status"):
            qs = qs.filter(status=st)
        return _paginate(self, qs, lambda r: s.HRRequestSerializer(r).data)

    def post(self, request):
        ctx = self.authz
        e = employee_of(ctx)
        cat = request.data.get("category")
        subj = str(request.data.get("subject", "")).strip()
        if cat not in m.HRRequest.Category.values or len(subj) < 3:
            raise DomainError("Choose a category and add a subject.", code="validation_error")
        r = m.HRRequest.objects.create(organization=ctx.organization, employee=e, category=cat, subject=subj[:160], description=str(request.data.get("description", ""))[:4000])
        notify_many(svc.hr_holders(e, "people.request.manage")[:10], "workflow", f"HR request {r.code}: {r.subject}", body=e.display_name,
                    link=f"/people/requests?view=queue&open={r.pk}", module="people")
        record(request, "people.request.create", category="data", module="people", resource=r)
        return Response(s.HRRequestSerializer(r).data, status=status.HTTP_201_CREATED)


class HRRequestDetailView(OSView):
    def _get(self, ctx, pk):
        r = m.HRRequest.objects.filter(pk=pk, organization=ctx.organization).select_related("employee", "assignee").first()
        if r is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        staff = can_on(ctx, "people.request.manage", r.employee) or r.assignee_id == ctx.user.pk
        if not (staff or is_self(ctx, r.employee)):
            raise DomainError("Not found.", code="not_found", status_code=404)
        return r, staff

    def get(self, request, pk):
        r, staff = self._get(self.authz, pk)
        comments = r.comments.select_related("author") if staff else r.comments.filter(internal=False).select_related("author")
        return Response(s.HRRequestSerializer(r).data | {"comments": [{"author": c.author.full_name if c.author_id else None, "body": c.body, "internal": c.internal,
                                                                       "at": c.created_at} for c in comments], "can_manage": staff})

    def patch(self, request, pk):
        ctx = self.authz
        r, staff = self._get(ctx, pk)
        if not staff:
            raise DomainError("Only HR can update this request.", code="permission_denied", status_code=403)
        before = {"status": r.status, "assignee": str(r.assignee_id) if r.assignee_id else None}
        if request.data.get("status") in m.HRRequest.Status.values:
            r.status = request.data["status"]
            r.resolved_at = timezone.now() if r.status in ("resolved", "closed") else None
        if "assignee_id" in request.data:
            a = User.objects.filter(pk=request.data["assignee_id"], os_account__organization=ctx.organization).first() if request.data["assignee_id"] else None
            r.assignee = a
            if a and a.pk != request.user.pk:
                notify(a, "task_assigned", f"HR request assigned: {r.subject}", link=f"/people/requests?view=assigned&open={r.pk}", module="people")
        if "resolution" in request.data:
            r.resolution = str(request.data["resolution"])[:2000]
        r.save()
        if r.status in ("resolved", "waiting") and before["status"] != r.status and r.employee.user_id:
            notify(r.employee.user, "workflow", f"HR request {r.code} {r.get_status_display().lower()}", body=r.resolution[:200],
                   link=f"/people/requests?open={r.pk}", module="people")
        record(request, "people.request.update", category="data", module="people", resource=r, old=before, new={"status": r.status})
        return Response(s.HRRequestSerializer(r).data)


class HRRequestCommentView(OSView):
    def post(self, request, pk):
        r, staff = HRRequestDetailView._get(self, self.authz, pk)
        body = str(request.data.get("body", "")).strip()
        if not body:
            raise DomainError("Write a comment.", code="validation_error")
        internal = bool(request.data.get("internal")) and staff
        m.HRRequestComment.objects.create(request=r, author=request.user, body=body[:2000], internal=internal)
        if not internal:
            target = r.employee.user if staff else r.assignee
            if target and target.pk != request.user.pk:
                notify(target, "workflow", f"Reply on {r.code}: {r.subject}", body=body[:200], link=f"/people/requests?open={r.pk}", module="people")
        return Response({"saved": True}, status=status.HTTP_201_CREATED)


class CaseList(ScopedList):
    model, serializer_class = m.HRCase, s.HRCaseSerializer
    perms = {"view": "people.case.view", "create": "people.case.manage"}
    scope_fields = {"unit": "employee__org_unit", "department": "employee__department", "team": "employee__team", "employee": "employee"}
    search_fields, filters = ("summary", "code"), {"status": "status", "kind": "kind"}
    select_related, audit_prefix, sensitive_audit = ("employee", "assigned_to"), "people.case", True

    def perform_create(self, ser):
        if ser.validated_data["employee"].user_id == self.request.user.pk:
            raise DomainError("You can’t open a case about yourself here. Raise an HR request instead.", code="validation_error")
        return ser.save(organization=self.authz.organization, opened_by=self.request.user)


class CaseDetail(ScopedDetail):
    model, serializer_class = m.HRCase, s.HRCaseSerializer
    perms = {"view": "people.case.view", "edit": "people.case.manage", "delete": "people.case.manage"}
    scope_fields, audit_prefix, sensitive_audit = CaseList.scope_fields, "people.case", True
    select_related = ("employee", "assigned_to")

    def get(self, request, pk):
        c = self.get_object(pk)
        record(request, "people.case.view", category="data", module="people", resource=c, sensitive=True)
        return Response(self.serializer(c).data | {"notes": [{"author": n.author.full_name if n.author_id else None, "body": n.body, "at": n.created_at}
                                                             for n in c.notes.select_related("author")]})

    def delete(self, request, pk):
        raise DomainError("HR cases are kept for the retention period and can’t be deleted. Close the case instead.", code="not_allowed", status_code=405)


class CaseNoteView(OSView):
    permissions = {"POST": "people.case.manage"}

    def post(self, request, pk):
        c = m.HRCase.objects.filter(pk=pk, organization=self.authz.organization).select_related("employee").first()
        if c is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        require_on(self.authz, "people.case.manage", c.employee)
        m.HRCaseNote.objects.create(case=c, author=request.user, body=str(request.data.get("body", ""))[:4000])
        record(request, "people.case.note", category="data", module="people", resource=c, sensitive=True)
        return Response({"saved": True}, status=status.HTTP_201_CREATED)


# =============================================================================================================
# Promotions, transfers, offboarding
# =============================================================================================================
class ChangesView(OSView):
    permissions = {"GET": "people.lifecycle.view"}

    def get(self, request):
        ctx = self.authz
        qs = m.LifecycleChange.objects.filter(organization=ctx.organization).filter(related_q(ctx, "people.lifecycle.view")).select_related("employee", "requested_by")
        return Response({"results": [{"id": str(c.pk), "employee": {"id": str(c.employee_id), "name": c.employee.display_name}, "kind": c.kind,
                                      "kind_label": c.get_kind_display(), "status": c.status, "effective_date": c.effective_date, "reason": c.reason,
                                      "proposed": c.proposed, "requested_by": c.requested_by.full_name if c.requested_by_id else None,
                                      "approval_id": str(c.approval_id) if c.approval_id else None,
                                      **({"compensation": c.compensation} if can_on(ctx, "people.payroll.view", c.employee) else {})} for c in qs[:200]]})

    def post(self, request):
        ctx = self.authz
        e = _emp(ctx, request.data.get("employee_id"))
        kind = request.data.get("kind")
        if kind not in ("promotion", "transfer"):
            raise DomainError("Choose promotion or transfer.", code="validation_error")
        proposed = {k: request.data.get(k) for k in svc.FIELD_MODELS if request.data.get(k)}
        if not proposed:
            raise DomainError("Choose what changes (designation, level, department, team, location or manager).", code="validation_error")
        comp = request.data.get("compensation") or {}
        ch = svc.submit_change(request, ctx, e, kind, proposed, comp if comp.get("base_annual") else {}, _date(request.data.get("effective_date"), "effectiveDate"),
                               str(request.data.get("reason", "")))
        return Response({"id": str(ch.pk), "status": ch.status, "approval_id": str(ch.approval_id)}, status=status.HTTP_201_CREATED)


class OffboardingList(ScopedList):
    model, serializer_class = m.OffboardingCase, s.OffboardingSerializer
    # Creating is checked by the service: HR for anyone in scope, or the employee resigning themselves.
    perms = {"view": "people.offboarding.view", "create": None}
    scope_fields = {"unit": "employee__org_unit", "department": "employee__department", "team": "employee__team", "employee": "employee"}
    filters, select_related, audit_prefix = {"status": "status"}, ("employee",), "people.offboarding"

    def post(self, request):
        ctx = self.authz
        e = _emp(ctx, request.data.get("employee_id")) if request.data.get("employee_id") else employee_of(ctx)
        kind = request.data.get("kind") if request.data.get("kind") in m.OffboardingCase.Kind.values else "resignation"
        case = svc.submit_offboarding(request, ctx, e, kind, _date(request.data.get("notice_start") or timezone.localdate().isoformat(), "noticeStart"),
                                      _date(request.data.get("last_working_day"), "lastWorkingDay"), str(request.data.get("reason", "")))
        return Response(self.serializer(case).data, status=status.HTTP_201_CREATED)


class OffboardingDetail(ScopedDetail):
    model, serializer_class = m.OffboardingCase, s.OffboardingSerializer
    perms = {"view": "people.offboarding.view", "edit": "people.offboarding.manage", "delete": "people.offboarding.manage"}
    scope_fields, select_related, audit_prefix = OffboardingList.scope_fields, ("employee",), "people.offboarding"
    sensitive_audit = True

    def delete(self, request, pk):
        raise DomainError("Exit records are kept. Cancel the approval instead.", code="not_allowed", status_code=405)


class OffboardingActionView(OSView):
    def post(self, request, pk, action):
        ctx = self.authz
        case = m.OffboardingCase.objects.filter(pk=pk, organization=ctx.organization).select_related("employee", "employee__user", "employee__position").first()
        if case is None or not can_on(ctx, "people.offboarding.view", case.employee):
            raise DomainError("Not found.", code="not_found", status_code=404)
        if action == "complete":
            svc.complete_offboarding(request, ctx, case)
        elif action == "revoke-access":
            require_on(ctx, "people.offboarding.manage", case.employee)
            ctx.require("identity.user.manage")
            if svc.revoke_access(request, case.employee, "Revoked during offboarding"):
                case.access_revoked_at = timezone.now()
                case.save(update_fields=["access_revoked_at", "updated_at"])
        else:
            raise DomainError("Not found.", code="not_found", status_code=404)
        return Response(s.OffboardingSerializer(case, context={"authz": ctx, "view": _OffView(ctx)}).data)


class _OffView:
    def __init__(self, ctx):
        self.authz = ctx

    @staticmethod
    def target_for(obj):
        return svc.target(obj.employee)

