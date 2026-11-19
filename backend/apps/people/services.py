"""
People & HR business rules. Every approval goes through apps.workflows (policies people.*), every change is audited,
every notification uses apps.workspace.notify, and identity/access changes go through apps.access — never copies.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.access.authz import AuthContext, holders_of
from apps.audit.services import record
from apps.core.api.exceptions import DomainError
from apps.workflows import engine
from apps.workflows.hooks import on_decision
from apps.workflows.models import Task
from apps.workspace.notify import notify, notify_many

from .models import (AttendanceCorrection, AttendanceRecord, ChecklistTemplate, CompensationRecord, Employee, EmploymentEvent,
                     Holiday, HolidayCalendar, LeaveBalance, LeaveRequest, LeaveType, LifecycleChange, LifecyclePlan,
                     OffboardingCase, Offer, Position)


# --- scope helpers --------------------------------------------------------------------------------------------
def target(emp: Employee) -> dict:
    t = {"employee": emp.pk, "organization": emp.organization_id}
    if emp.org_unit_id:
        t["unit"] = emp.org_unit_id
    if emp.department_id:
        t["department"] = emp.department_id
    if emp.team_id:
        t["team"] = emp.team_id
    if emp.user_id:
        t["owner"] = emp.user_id
    return t


EMP_FIELDS = dict(unit="org_unit", department="department", team="team", owner="user", employee="pk", organization=None)
REL_FIELDS = dict(unit="employee__org_unit", department="employee__department", team="employee__team", owner="employee__user",
                  employee="employee", organization=None)


def employees_q(ctx: AuthContext, code: str):
    return ctx.scope(code).q(**EMP_FIELDS)


def related_q(ctx: AuthContext, code: str):
    return ctx.scope(code).q(**REL_FIELDS)


def can_on(ctx: AuthContext, code: str, emp: Employee) -> bool:
    return ctx.can(code, **target(emp))


def require_on(ctx: AuthContext, code: str, emp: Employee):
    return ctx.require(code, **target(emp))


def is_self(ctx: AuthContext, emp: Employee) -> bool:
    return bool(emp.user_id and emp.user_id == ctx.user.pk)


def employee_of(ctx: AuthContext) -> Employee:
    if ctx.employee is None:
        raise DomainError("Your account isn’t linked to an employee record. Ask HR.", code="no_employee_record", status_code=409)
    return ctx.employee


def hr_holders(emp: Employee, code: str = "people.employee.edit") -> list:
    t = {k: v for k, v in target(emp).items() if k in ("unit", "department")}
    users = holders_of(code, emp.organization, **t) if t else holders_of(code, emp.organization)
    return [u for u in users if u.pk != emp.user_id]


def _event(request, emp, kind, before=None, after=None, reason="", effective=None, approval=None, sensitive=False):
    EmploymentEvent.objects.create(employee=emp, kind=kind, before=before or {}, after=after or {}, reason=reason[:300],
                                   effective_date=effective or timezone.localdate(), approval=approval, sensitive=sensitive,
                                   created_by=getattr(request, "user", None) if getattr(getattr(request, "user", None), "is_authenticated", False) else None)


# --- calendars & working days -------------------------------------------------------------------------------------
def calendars_for(emp: Employee):
    anc = emp.org_unit.ancestor_ids if emp.org_unit_id and emp.org_unit else []
    return HolidayCalendar.objects.filter(organization=emp.organization).filter(
        (Q(org_unit__isnull=True) | Q(org_unit_id__in=anc)) & (Q(department__isnull=True) | Q(department_id=emp.department_id)))


def holidays_between(emp: Employee, start: date, end: date) -> dict[date, str]:
    return {h.date: h.name for h in Holiday.objects.filter(calendar__in=calendars_for(emp), date__gte=start, date__lte=end, optional=False)}


def working_weekdays(emp: Employee) -> set[int]:
    days = emp.schedule.working_days if emp.schedule_id and emp.schedule and emp.schedule.working_days else None
    return set(days or [1, 2, 3, 4, 5])


def working_days(emp: Employee, start: date, end: date, half: str = "") -> Decimal:
    if end < start:
        raise DomainError("The end date is before the start date.", code="validation_error")
    hol = holidays_between(emp, start, end)
    wk = working_weekdays(emp)
    n, d = 0, start
    while d <= end:
        if d.isoweekday() in wk and d not in hol:
            n += 1
        d += timedelta(days=1)
    if half and start == end and n:
        return Decimal("0.5")
    return Decimal(n)


# --- leave ---------------------------------------------------------------------------------------------------------
def balance(emp: Employee, lt: LeaveType, year: int) -> LeaveBalance:
    b, created = LeaveBalance.objects.get_or_create(employee=emp, leave_type=lt, year=year, defaults={"entitled": lt.annual_quota})
    return b


def eligible_types(emp: Employee):
    return [lt for lt in LeaveType.objects.filter(organization=emp.organization, is_active=True)
            if not lt.worker_types or emp.worker_type in lt.worker_types]


def submit_leave(request, ctx: AuthContext, emp: Employee, lt: LeaveType, start: date, end: date, half: str = "", reason: str = "") -> LeaveRequest:
    if not (is_self(ctx, emp) or can_on(ctx, "people.leave.manage", emp)):
        require_on(ctx, "people.leave.create", emp)
    if lt not in eligible_types(emp):
        raise DomainError("This leave type doesn’t apply to this employee.", code="validation_error")
    if half and (start != end or not lt.allow_half_day):
        raise DomainError("Half days can only be taken for a single day of a leave type that allows them.", code="validation_error")
    if start.year != end.year:
        raise DomainError("Split leave that crosses into a new year into two requests.", code="validation_error")
    days = working_days(emp, start, end, half)
    if days <= 0:
        raise DomainError("Those dates are all weekly offs or holidays.", code="no_working_days")
    overlap = LeaveRequest.objects.filter(employee=emp, status__in=["pending", "approved", "changes_requested"],
                                          start_date__lte=end, end_date__gte=start).exists()
    if overlap:
        raise DomainError("This overlaps another leave request.", code="leave_overlap", status_code=409)
    with transaction.atomic():
        b = LeaveBalance.objects.select_for_update().get(pk=balance(emp, lt, start.year).pk)
        if lt.paid and b.available < days:
            raise DomainError(f"Not enough {lt.name} balance: {b.available} day(s) available, {days} requested.", code="insufficient_balance", status_code=409)
        lr = LeaveRequest.objects.create(employee=emp, leave_type=lt, start_date=start, end_date=end, half_day=half, days=days, reason=reason[:500])
        b.pending += days
        b.save(update_fields=["pending", "updated_at"])
        soon = start <= timezone.localdate() + timedelta(days=3)
        apr = engine.submit(request, "people.leave", title=f"{lt.name}: {emp.display_name}, {start:%d %b}" + (f"–{end:%d %b}" if end != start else ""),
                            amount=days, description=reason, org_unit=emp.org_unit, department=emp.department, resource_type="people.leave",
                            resource_id=str(lr.pk), skip_permission=True, blocking=soon, priority="high" if soon else "normal",
                            due_at=datetime.combine(start, time(9), tzinfo=timezone.get_current_timezone()) if start > timezone.localdate() else None)
        lr.approval = apr
        lr.save(update_fields=["approval", "updated_at"])
    record(request, "people.leave.request", category="data", module="people", resource=lr,
           new={"type": lt.code, "start": start, "end": end, "days": days})
    return lr


@on_decision("people.leave")
def _leave_decided(req, outcome):
    lr = LeaveRequest.objects.select_related("leave_type", "employee").filter(pk=req.resource_id).first()
    if lr is None:
        return
    b = LeaveBalance.objects.select_for_update().get(employee=lr.employee, leave_type=lr.leave_type, year=lr.start_date.year)
    if outcome == "approved" and lr.status in ("pending", "changes_requested"):
        b.pending -= lr.days
        b.used += lr.days
        lr.status = "approved"
    elif outcome in ("rejected", "cancelled") and lr.status in ("pending", "changes_requested"):
        b.pending -= lr.days
        lr.status = outcome
    elif outcome == "changes_requested":
        lr.status = "changes_requested"
    elif outcome == "resubmitted":
        lr.status = "pending"
    b.pending = max(Decimal("0"), b.pending)
    b.save(update_fields=["pending", "used", "updated_at"])
    lr.save(update_fields=["status", "updated_at"])


def cancel_leave(request, ctx, lr: LeaveRequest):
    if not (is_self(ctx, lr.employee) or can_on(ctx, "people.leave.manage", lr.employee)):
        raise DomainError("You can’t cancel this leave.", code="permission_denied", status_code=403)
    if lr.status in ("pending", "changes_requested") and lr.approval and lr.approval.requested_by_id == ctx.user.pk:
        engine.cancel(request, lr.approval, reason="Leave cancelled")
        return LeaveRequest.objects.get(pk=lr.pk)
    if lr.status == "approved":
        if lr.start_date <= timezone.localdate() and not can_on(ctx, "people.leave.manage", lr.employee):
            raise DomainError("Leave that has started can only be cancelled by HR.", code="leave_started", status_code=409)
        with transaction.atomic():
            b = LeaveBalance.objects.select_for_update().get(employee=lr.employee, leave_type=lr.leave_type, year=lr.start_date.year)
            b.used = max(Decimal("0"), b.used - lr.days)
            b.save(update_fields=["used", "updated_at"])
            lr.status = "cancelled"
            lr.save(update_fields=["status", "updated_at"])
        record(request, "people.leave.cancel", category="data", module="people", resource=lr)
        return lr
    raise DomainError("This leave can’t be cancelled now.", code="invalid_state", status_code=409)


def on_leave_today(org, employee_ids=None) -> set:
    today = timezone.localdate()
    qs = LeaveRequest.objects.filter(employee__organization=org, status="approved", start_date__lte=today, end_date__gte=today)
    if employee_ids is not None:
        qs = qs.filter(employee_id__in=employee_ids)
    return set(qs.values_list("employee_id", flat=True))


# --- attendance ------------------------------------------------------------------------------------------------------
def _schedule_bounds(emp: Employee, d: date):
    s = emp.schedule
    if not s or not s.start_time:
        return None, None, 15
    tz = timezone.get_current_timezone()
    end = datetime.combine(d, s.end_time, tzinfo=tz) if s.end_time else None
    return datetime.combine(d, s.start_time, tzinfo=tz), end, s.grace_minutes


def check_in(request, ctx, emp: Employee, mode: str = "office") -> AttendanceRecord:
    if not is_self(ctx, emp):
        raise DomainError("You can only check yourself in.", code="permission_denied", status_code=403)
    require_on(ctx, "people.attendance.create", emp)
    now = timezone.now()
    today = timezone.localdate()
    rec, created = AttendanceRecord.objects.get_or_create(employee=emp, date=today, defaults={"check_in": now, "mode": mode if mode in AttendanceRecord.Mode.values else "office"})
    if not created:
        if rec.check_in:
            raise DomainError("You’ve already checked in today.", code="already_checked_in", status_code=409)
        rec.check_in = now
    start, _end, grace = _schedule_bounds(emp, today)
    rec.late = bool(start and now > start + timedelta(minutes=grace))
    rec.status = "present"
    rec.save()
    return rec


def check_out(request, ctx, emp: Employee) -> AttendanceRecord:
    if not is_self(ctx, emp):
        raise DomainError("You can only check yourself out.", code="permission_denied", status_code=403)
    rec = AttendanceRecord.objects.filter(employee=emp, date=timezone.localdate()).first()
    if rec is None or not rec.check_in:
        raise DomainError("Check in first.", code="not_checked_in", status_code=409)
    if rec.check_out:
        raise DomainError("You’ve already checked out today.", code="already_checked_out", status_code=409)
    now = timezone.now()
    rec.check_out = now
    _s, end, _g = _schedule_bounds(emp, rec.date)
    rec.early_departure = bool(end and now < end - timedelta(minutes=15))
    rec.save()
    return rec


def submit_correction(request, ctx, emp: Employee, d: date, check_in_at, check_out_at, reason: str) -> AttendanceCorrection:
    if not is_self(ctx, emp):
        require_on(ctx, "people.attendance.manage", emp)
    if d > timezone.localdate():
        raise DomainError("You can’t correct a future day.", code="validation_error")
    if not reason.strip():
        raise DomainError("Say why the record needs correcting.", code="validation_error", details={"reason": ["Required."]})
    if check_in_at and check_out_at and check_out_at <= check_in_at:
        raise DomainError("Check-out must be after check-in.", code="validation_error")
    with transaction.atomic():
        c = AttendanceCorrection.objects.create(employee=emp, date=d, check_in=check_in_at, check_out=check_out_at, reason=reason[:300])
        c.approval = engine.submit(request, "people.attendance_correction", title=f"Attendance correction: {emp.display_name}, {d:%d %b}",
                                   amount=1, description=reason, org_unit=emp.org_unit, department=emp.department,
                                   resource_type="people.attendance_correction", resource_id=str(c.pk), skip_permission=True)
        c.save(update_fields=["approval", "updated_at"])
    record(request, "people.attendance.correction_request", category="data", module="people", resource=c, new={"date": d})
    return c


@on_decision("people.attendance_correction")
def _correction_decided(req, outcome):
    c = AttendanceCorrection.objects.select_related("employee").filter(pk=req.resource_id).first()
    if c is None:
        return
    if outcome == "approved":
        rec, _ = AttendanceRecord.objects.get_or_create(employee=c.employee, date=c.date)
        if c.check_in:
            rec.check_in = c.check_in
        if c.check_out:
            rec.check_out = c.check_out
        rec.status, rec.source = "present", "correction"
        rec.note = f"Corrected: {c.reason}"[:200]
        rec.save()
    c.status = {"approved": "approved", "rejected": "rejected", "cancelled": "cancelled", "changes_requested": "changes_requested",
                "resubmitted": "pending"}.get(outcome, c.status)
    c.save(update_fields=["status", "updated_at"])


def attendance_exceptions(org, employees_qs, day: date) -> list[dict]:
    """Missing check-out, late arrival, early departure, or absent on a working day without approved leave."""
    emps = list(employees_qs.filter(status__in=Employee.WORKING).exclude(status="on_leave").select_related("schedule", "org_unit"))
    recs = {r.employee_id: r for r in AttendanceRecord.objects.filter(employee__in=emps, date=day)}
    away = on_leave_today(org, [e.pk for e in emps]) if day == timezone.localdate() else set(
        LeaveRequest.objects.filter(employee__in=emps, status="approved", start_date__lte=day, end_date__gte=day).values_list("employee_id", flat=True))
    out = []
    for e in emps:
        if e.pk in away or day.isoweekday() not in working_weekdays(e) or day in holidays_between(e, day, day):
            continue
        r = recs.get(e.pk)
        if r is None:
            if day < timezone.localdate():
                out.append({"employee": e, "kind": "absent", "label": "No attendance recorded"})
        elif r.check_in and not r.check_out and day < timezone.localdate():
            out.append({"employee": e, "kind": "missing_checkout", "label": "Missing check-out"})
        elif r.late:
            out.append({"employee": e, "kind": "late", "label": "Late arrival"})
        elif r.early_departure:
            out.append({"employee": e, "kind": "early", "label": "Left early"})
    return out


# --- positions, offers, hiring ----------------------------------------------------------------------------------------
def submit_position(request, ctx, pos: Position):
    ctx.require("people.position.create", **({"unit": pos.org_unit_id} if pos.org_unit_id else {}), department=pos.department_id)
    if pos.status not in ("draft", "rejected"):
        raise DomainError("This position has already been submitted.", code="invalid_state", status_code=409)
    budget = (pos.salary_max or Decimal("0")) * pos.headcount
    with transaction.atomic():
        pos.approval = engine.submit(request, "people.position", title=f"New position: {pos.title} ({pos.headcount})",
                                     amount=budget if budget > 0 else None, description=pos.description[:1000], org_unit=pos.org_unit,
                                     department=pos.department, resource_type="people.position", resource_id=str(pos.pk), skip_permission=True)
        pos.status = Position.Status.PENDING
        pos.save(update_fields=["approval", "status", "updated_at"])
    return pos


@on_decision("people.position")
def _position_decided(req, outcome):
    pos = Position.objects.filter(pk=req.resource_id).first()
    if pos:
        pos.status = {"approved": "approved", "rejected": "draft", "cancelled": "draft", "changes_requested": "draft"}.get(outcome, pos.status)
        pos.save(update_fields=["status", "updated_at"])


def submit_offer(request, ctx, offer: Offer):
    app = offer.application
    pos = app.opening.position
    ctx.require("people.offer.create", **({"unit": pos.org_unit_id} if pos.org_unit_id else {}), department=pos.department_id)
    if offer.status not in ("draft", "rejected"):
        raise DomainError("This offer was already submitted.", code="invalid_state", status_code=409)
    total = offer.base_annual + offer.variable_annual + offer.joining_bonus
    with transaction.atomic():
        offer.approval = engine.submit(request, "people.offer", title=f"Offer: {app.candidate.full_name} · {app.opening.title}", amount=total,
                                       org_unit=pos.org_unit, department=pos.department, resource_type="people.offer", resource_id=str(offer.pk),
                                       skip_permission=True, blocking=True, priority="high")
        offer.status = Offer.Status.PENDING
        offer.save(update_fields=["approval", "status", "updated_at"])
    return offer


@on_decision("people.offer")
def _offer_decided(req, outcome):
    o = Offer.objects.filter(pk=req.resource_id).first()
    if o:
        o.status = {"approved": "approved", "rejected": "rejected", "cancelled": "draft", "changes_requested": "draft"}.get(outcome, o.status)
        o.save(update_fields=["status", "updated_at"])


def accept_offer(request, ctx, offer: Offer, *, work_email: str = "", invite: bool = True) -> Employee:
    """Offer accepted → the employee record (pre-onboarding), compensation history, onboarding plan, and (optionally)
    a Business OS invitation through Identity & Access. No second user database is created."""
    from apps.access.models import AccountKind, OSAccount
    from apps.users.models import User

    if offer.status != Offer.Status.RELEASED:
        raise DomainError("Only released offers can be accepted.", code="invalid_state", status_code=409)
    app = offer.application
    pos = app.opening.position
    cand = app.candidate
    with transaction.atomic():
        emp = Employee.objects.create(
            organization=offer.organization, full_name=cand.full_name, work_email=work_email, designation=offer.designation or pos.designation,
            job_level=offer.job_level or pos.job_level, position=pos, department=pos.department, team=pos.team, org_unit=pos.org_unit,
            manager=pos.reporting_manager or app.opening.hiring_manager, status=Employee.Status.PRE_ONBOARDING, worker_type=pos.worker_type,
            employment_type=pos.employment_type, joined_on=offer.joining_date, probation_end_on=offer.joining_date + timedelta(days=180))
        CompensationRecord.objects.create(employee=emp, effective_date=offer.joining_date, currency=offer.currency, base_annual=offer.base_annual,
                                          variable_target=offer.variable_annual, bonus=offer.joining_bonus, reason="hire", approval=offer.approval,
                                          created_by=request.user)
        offer.status, offer.responded_on = Offer.Status.ACCEPTED, timezone.localdate()
        offer.save(update_fields=["status", "responded_on", "updated_at"])
        app.stage, app.hired_employee, app.stage_changed_at = "onboarding", emp, timezone.now()
        app.save(update_fields=["stage", "hired_employee", "stage_changed_at", "updated_at"])
        filled = pos.holders.filter(status__in=Employee.WORKING + ("pre_onboarding",)).count()
        if filled >= pos.headcount:
            pos.status = Position.Status.FILLED
            pos.save(update_fields=["status", "updated_at"])
        _event(request, emp, "hired", after={"position": pos.code, "designation": emp.designation.name if emp.designation else None},
               effective=offer.joining_date, approval=offer.approval)
        start_plan(request, emp, "onboarding")
        if invite and work_email:
            user = User.objects.filter(email__iexact=work_email).first()
            if user is None:
                user = User.objects.create_user(work_email.lower(), None, full_name=emp.full_name)
                user.set_unusable_password()
                user.save(update_fields=["password"])
            if not hasattr(user, "os_account"):
                OSAccount.objects.create(user=user, organization=emp.organization, kind=AccountKind.EMPLOYEE, status=OSAccount.Status.INVITED,
                                         invited_by=request.user, invited_at=timezone.now())
            emp.user = user
            emp.save(update_fields=["user", "updated_at"])
    record(request, "people.offer.accepted", category="data", module="people", resource=emp, new={"offer": offer.code, "position": pos.code})
    notify_many(hr_holders(emp), "workflow", f"New joiner: {emp.full_name}", body=f"Joining {offer.joining_date:%d %b %Y} · {pos.title}",
                link=f"/people/{emp.pk}", module="people")
    return emp


# --- onboarding / offboarding checklists ------------------------------------------------------------------------------
def _owner_user(emp: Employee, owner: str):
    if owner == "employee":
        return emp.user
    if owner == "manager":
        return emp.manager.user if emp.manager_id and emp.manager.user_id else None
    code = {"it": "technology.asset.manage", "finance": "finance.payment.view", "facilities": "operations.sop.manage"}.get(owner, "people.onboarding.manage")
    users = holders_of(code, emp.organization) if code != "people.onboarding.manage" else hr_holders(emp, code)
    return users[0] if users else None


def start_plan(request, emp: Employee, kind: str, template: ChecklistTemplate | None = None) -> LifecyclePlan | None:
    template = template or ChecklistTemplate.objects.filter(organization=emp.organization, kind=kind).filter(
        Q(worker_types=[]) | Q(worker_types__contains=[emp.worker_type])).order_by("-is_default", "name").first()
    if template is None:
        return None
    plan = LifecyclePlan.objects.create(employee=emp, kind=kind, template=template, started_on=timezone.localdate())
    base = emp.joined_on if kind == "onboarding" and emp.joined_on else timezone.localdate()
    fallback = (hr_holders(emp, "people.onboarding.manage") or [getattr(request, "user", None)])[0]
    creator = request.user if getattr(getattr(request, "user", None), "is_authenticated", False) else fallback
    for step in template.steps:
        assignee = _owner_user(emp, step.get("owner", "hr")) or fallback
        if assignee is None:
            continue
        due = datetime.combine(base + timedelta(days=int(step.get("offset_days") or 0)), time(18), tzinfo=timezone.get_current_timezone())
        Task.objects.create(organization=emp.organization, title=f"{step['title']} — {emp.full_name}"[:160], description=step.get("description", "")[:4000],
                            assignee=assignee, created_by=creator or assignee, due_at=due, module="people", priority="normal",
                            link_path=f"/people/{emp.pk}?tab=lifecycle", source_type=f"people.{kind}", source_id=str(plan.pk))
        if assignee.pk != getattr(creator, "pk", None):
            notify(assignee, "task_assigned", f"{kind.capitalize()} task: {step['title']}", body=emp.full_name, link="/tasks", module="people")
    return plan


def plan_progress(plan: LifecyclePlan) -> dict:
    tasks = Task.objects.filter(source_type=f"people.{plan.kind}", source_id=str(plan.pk))
    total, done = tasks.count(), tasks.filter(status="done").count()
    if total and done == total and plan.status == "in_progress":
        plan.status, plan.completed_at = "completed", timezone.now()
        plan.save(update_fields=["status", "completed_at", "updated_at"])
    return {"total": total, "done": done, "pct": int(done / total * 100) if total else 0,
            "tasks": [{"id": str(t.pk), "title": t.title, "status": t.status, "assignee": t.assignee.full_name, "due_at": t.due_at}
                      for t in tasks.select_related("assignee").order_by("due_at")]}


# --- promotions / transfers / salary revisions --------------------------------------------------------------------------
POLICY_FOR_CHANGE = {"promotion": "people.promotion", "transfer": "people.transfer", "salary_revision": "people.salary_revision"}


def submit_change(request, ctx, emp: Employee, kind: str, proposed: dict, compensation: dict, effective: date, reason: str) -> LifecycleChange:
    require_on(ctx, "people.lifecycle.create", emp)
    if compensation:
        require_on(ctx, "people.payroll.manage", emp)
    if kind == "salary_revision" and not compensation:
        raise DomainError("Enter the new salary.", code="validation_error")
    if LifecycleChange.objects.filter(employee=emp, status__in=["pending", "approved"]).exists():
        raise DomainError("This employee already has a pending promotion, transfer or revision.", code="change_pending", status_code=409)
    amount = Decimal(str(compensation.get("base_annual"))) if compensation.get("base_annual") else None
    with transaction.atomic():
        ch = LifecycleChange.objects.create(organization=emp.organization, employee=emp, kind=kind, proposed=proposed, compensation=compensation,
                                            effective_date=effective, reason=reason[:500], requested_by=request.user)
        ch.approval = engine.submit(request, POLICY_FOR_CHANGE[kind], title=f"{LifecycleChange.Kind(kind).label}: {emp.display_name}",
                                    amount=amount, description=reason, org_unit=emp.org_unit, department=emp.department,
                                    resource_type="people.lifecycle", resource_id=str(ch.pk), skip_permission=True)
        ch.save(update_fields=["approval", "updated_at"])
    record(request, f"people.{kind}.request", category="data", module="people", resource=emp, new={"proposed": proposed, "effective": effective},
           sensitive=bool(compensation))
    return ch


def _decided_change(req, outcome):
    ch = LifecycleChange.objects.select_related("employee").filter(pk=req.resource_id).first()
    if ch is None:
        return
    if outcome == "approved":
        ch.status = "approved"
        ch.save(update_fields=["status", "updated_at"])
        if ch.effective_date <= timezone.localdate():
            apply_change(None, ch)
    else:
        ch.status = {"rejected": "rejected", "cancelled": "cancelled", "changes_requested": "changes_requested", "resubmitted": "pending"}.get(outcome, ch.status)
        ch.save(update_fields=["status", "updated_at"])


for _key in POLICY_FOR_CHANGE.values():
    on_decision(_key)(_decided_change)


FIELD_MODELS = {"designation_id": "designation", "job_level_id": "job_level", "department_id": "department", "team_id": "team",
                "org_unit_id": "org_unit", "manager_id": "manager", "position_id": "position"}


def apply_change(request, ch: LifecycleChange):
    emp = ch.employee
    before, after = {}, {}
    for f in FIELD_MODELS:
        if f in ch.proposed and ch.proposed[f]:
            before[f] = str(getattr(emp, f) or "")
            setattr(emp, f, ch.proposed[f])
            after[f] = str(ch.proposed[f])
    with transaction.atomic():
        emp.save()
        if ch.compensation.get("base_annual"):
            CompensationRecord.objects.create(employee=emp, effective_date=ch.effective_date, currency=ch.compensation.get("currency", "INR"),
                                              base_annual=Decimal(str(ch.compensation["base_annual"])),
                                              variable_target=Decimal(str(ch.compensation.get("variable_target") or 0)),
                                              reason="promotion" if ch.kind == "promotion" else "revision", approval=ch.approval,
                                              created_by=ch.requested_by)
        kind = {"promotion": "promoted", "transfer": "transferred", "salary_revision": "compensation_changed"}[ch.kind]
        _event(request, emp, kind, before=before, after=after, reason=ch.reason, effective=ch.effective_date, approval=ch.approval,
               sensitive=ch.kind == "salary_revision")
        ch.status, ch.applied_at = "applied", timezone.now()
        ch.save(update_fields=["status", "applied_at", "updated_at"])
    if ch.kind in ("promotion", "transfer"):
        access_review_task(emp, f"{ch.get_kind_display()} effective {ch.effective_date:%d %b %Y}", requested_by=ch.requested_by)
    if emp.user_id:
        notify(emp.user, "workflow", f"Your {ch.get_kind_display().lower()} is effective", body=f"From {ch.effective_date:%d %b %Y}",
               link="/profile", module="people", priority="important")
    record(request, f"people.{ch.kind}.applied", category="data", module="people", resource=emp, old=before, new=after,
           sensitive=ch.kind == "salary_revision", organization=emp.organization)


def access_review_task(emp: Employee, why: str, requested_by=None):
    """Identity & Access integration: role changes trigger a review by the people who manage access — no duplicate system."""
    admins = holders_of("access.role.assign", emp.organization)
    if not admins:
        return
    acct = getattr(emp.user, "os_account", None) if emp.user_id else None
    for a in admins[:1]:
        Task.objects.create(organization=emp.organization, title=f"Review access for {emp.full_name}"[:160], assignee=a,
                            created_by=requested_by or a, priority="high", module="access", due_at=timezone.now() + timedelta(days=2),
                            description=f"{why}. Check that their roles still match their new responsibilities.",
                            link_path=f"/settings/users/{acct.pk}" if acct else f"/people/{emp.pk}", source_type="people.access_review", source_id=str(emp.pk))
        notify(a, "task_assigned", f"Access review: {emp.full_name}", body=why, link="/tasks", module="access")


# --- offboarding ----------------------------------------------------------------------------------------------------
def submit_offboarding(request, ctx, emp: Employee, kind: str, notice_start: date, last_day: date, reason: str) -> OffboardingCase:
    if kind == "resignation" and is_self(ctx, emp):
        pass  # employees may resign themselves
    else:
        require_on(ctx, "people.offboarding.manage", emp)
    if last_day < notice_start:
        raise DomainError("The last working day is before the notice start.", code="validation_error")
    if OffboardingCase.objects.filter(employee=emp, status__in=["pending", "in_progress"]).exists():
        raise DomainError("An exit is already in progress for this employee.", code="exit_pending", status_code=409)
    with transaction.atomic():
        case = OffboardingCase.objects.create(organization=emp.organization, employee=emp, kind=kind, notice_start=notice_start,
                                              last_working_day=last_day, reason=reason[:500], created_by=request.user)
        case.approval = engine.submit(request, "people.offboarding", title=f"{case.get_kind_display()}: {emp.display_name} (last day {last_day:%d %b})",
                                      description=reason, org_unit=emp.org_unit, department=emp.department, resource_type="people.offboarding",
                                      resource_id=str(case.pk), skip_permission=True, priority="high")
        case.save(update_fields=["approval", "updated_at"])
    record(request, "people.offboarding.request", category="data", module="people", resource=emp, new={"kind": kind, "last_day": last_day})
    return case


@on_decision("people.offboarding")
def _offboarding_decided(req, outcome):
    case = OffboardingCase.objects.select_related("employee").filter(pk=req.resource_id).first()
    if case is None:
        return
    emp = case.employee
    if outcome == "approved":
        case.status = "in_progress"
        emp.status = Employee.Status.NOTICE
        emp.save(update_fields=["status", "updated_at"])
        _event(req, emp, "status_changed", before={"status": "active"}, after={"status": "notice"}, effective=case.notice_start, approval=req)
        start_plan(None, emp, "offboarding")
    elif outcome in ("rejected", "cancelled"):
        case.status = "rejected" if outcome == "rejected" else "cancelled"
    case.save(update_fields=["status", "updated_at"])


def revoke_access(request, emp: Employee, reason: str) -> bool:
    """Identity & Access integration on exit: suspend the OS account, end every session and role. One system, not a copy."""
    from apps.access.models import OSAccount, RoleAssignment
    from apps.access.sessions import revoke_all

    acct = OSAccount.objects.filter(user_id=emp.user_id).first() if emp.user_id else None
    if acct is None:
        return False
    with transaction.atomic():
        acct.status = OSAccount.Status.DEACTIVATED
        acct.save(update_fields=["status", "updated_at"])
        RoleAssignment.objects.filter(user_id=emp.user_id, is_active=True).update(is_active=False)
        revoke_all(acct.user, "employee_exit")
    record(request, "identity.user.deactivated", category="security", module="identity", resource=acct, metadata={"reason": reason},
           organization=emp.organization)
    return True


def complete_offboarding(request, ctx, case: OffboardingCase) -> OffboardingCase:
    require_on(ctx, "people.offboarding.manage", case.employee)
    if case.status != "in_progress":
        raise DomainError("This exit isn’t in progress.", code="invalid_state", status_code=409)
    emp = case.employee
    final = {"resignation": "resigned", "termination": "terminated", "retirement": "retired", "contract_end": "former"}[case.kind]
    with transaction.atomic():
        before = emp.status
        emp.status, emp.exit_date, emp.exit_reason = final, case.last_working_day, case.exit_reason or case.kind
        emp.save(update_fields=["status", "exit_date", "exit_reason", "updated_at"])
        if revoke_access(request, emp, f"{case.get_kind_display()} completed"):
            case.access_revoked_at = timezone.now()
        case.status, case.completed_at = "completed", timezone.now()
        case.save()
        _event(request, emp, "exited", before={"status": before}, after={"status": final}, reason=case.reason, effective=case.last_working_day,
               approval=case.approval)
        if emp.position_id and emp.position.status == "filled":
            Position.objects.filter(pk=emp.position_id).update(status="approved")  # the seat is open again
    record(request, "people.offboarding.completed", category="data", module="people", resource=emp, old={"status": before}, new={"status": final})
    return case


# --- jobs -----------------------------------------------------------------------------------------------------------
def daily_jobs(org) -> dict:
    """Scheduled-change application, probation reminders, document/certification expiry reminders, offer expiry."""
    from apps.documents.models import Document

    from .models import Certification

    today = timezone.localdate()
    out = {"changes_applied": 0, "offers_expired": 0, "reminders": 0, "joiners_activated": 0}
    for ch in LifecycleChange.objects.filter(organization=org, status="approved", effective_date__lte=today).select_related("employee"):
        apply_change(None, ch)
        out["changes_applied"] += 1
    out["offers_expired"] = Offer.objects.filter(organization=org, status="released", expires_on__lt=today).update(status="expired")
    for emp in Employee.objects.filter(organization=org, status="pre_onboarding", joined_on__lte=today):
        emp.status = Employee.Status.PROBATION if emp.probation_end_on else Employee.Status.ACTIVE
        emp.save(update_fields=["status", "updated_at"])
        out["joiners_activated"] += 1
    for days in (30, 7):
        d = today + timedelta(days=days)
        for doc in Document.objects.filter(organization=org, resource_type="people.employee", expires_on=d, status="active"):
            emp = Employee.objects.filter(pk=doc.resource_id).first()
            if emp and emp.user_id:
                out["reminders"] += bool(notify(emp.user, "deadline", f"{doc.title} expires in {days} days", link=f"/people/me?tab=documents",
                                                module="people", dedupe_key=f"docexp:{doc.pk}:{days}"))
        for cert in Certification.objects.filter(employee__organization=org, expires_on=d).select_related("employee"):
            if cert.employee.user_id:
                out["reminders"] += bool(notify(cert.employee.user, "deadline", f"Certification “{cert.name}” expires in {days} days",
                                                link="/people/learning", module="people", dedupe_key=f"certexp:{cert.pk}:{days}"))
    for emp in Employee.objects.filter(organization=org, status="probation", probation_end_on=today + timedelta(days=14)).select_related("manager__user"):
        targets = hr_holders(emp) + ([emp.manager.user] if emp.manager_id and emp.manager.user_id else [])
        out["reminders"] += notify_many(targets, "deadline", f"Probation ends in 14 days: {emp.full_name}", link=f"/people/{emp.pk}",
                                        module="people", dedupe_key=f"probation:{emp.pk}")
    return out

