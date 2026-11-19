"""
Home / Command Center widget engine.

    Widget registry (this file + modules calling register())
      + Role defaults (Role.home_widgets, Role.home_config.pulse)
      + the person's layout / saved views (account.preferences.home)
      → filtered by permission and audience → each widget loads on its own (GET /os/home/widgets/<key>)

Every loader receives the AuthContext and the request's parameters (selected location, time period) and must apply
the caller's scope itself; nothing here bypasses authorization. A failing widget returns an error card, never a 500.
Modules plug in without touching Home: People & HR registers its widgets, priority sources, briefing lines and
calendar sources from its AppConfig.ready().
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Callable

from django.core.cache import cache
from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.access.authz import AuthContext

from . import periods as periods_mod

logger = logging.getLogger(__name__)


class NotAtScope(Exception):
    pass


@dataclass
class Params:
    unit: object = None  # OrgUnit or None
    period: periods_mod.Period | None = None


@dataclass(frozen=True)
class Widget:
    key: str
    title: str
    size: str  # s | m | l
    category: str  # action | attention | awareness | insight | decision
    loader: Callable[[AuthContext, Params], dict]
    permission: str | tuple[str, ...] | None = None  # any one of these; None = every account
    org_wide: bool = False  # the permission must be organization-wide (platform-wide data)
    description: str = ""
    source: str = "Business OS"
    refresh: int = 120  # seconds the client should wait before refreshing
    periods: bool = False  # supports the period selector
    unit_aware: bool = False  # narrows to the selected location
    mandatory: Callable[[AuthContext], bool] | None = None  # can't be hidden when this returns True
    audience: tuple[str, ...] = ("employee", "external", "partner")
    requires: Callable[[AuthContext], bool] | None = None  # extra rule (e.g. managers only)
    cache_seconds: int = 0


WIDGETS: dict[str, Widget] = {}
PRIORITY_SOURCES: list[Callable] = []  # fn(ctx) -> list[dict(kind, title, reason, score, path, due_at)]
BRIEFING_SOURCES: list[Callable] = []  # fn(ctx) -> list[dict(text, source)]
INSIGHT_SOURCES: list[Callable] = []  # fn(ctx, period) -> list[insight dict]


def register(w: Widget) -> Widget:
    WIDGETS[w.key] = w
    return w


def _perm_ok(ctx: AuthContext, w: Widget) -> bool:
    if ctx.kind not in w.audience:
        return False
    if w.requires and not w.requires(ctx):
        return False
    if w.permission is None:
        return True
    codes = (w.permission,) if isinstance(w.permission, str) else w.permission
    for code in codes:
        s = ctx.scope(code)
        if not s.is_empty and (s.org_wide or not w.org_wide):
            return True
    return False


def available(ctx: AuthContext) -> list[str]:
    return [k for k, w in WIDGETS.items() if _perm_ok(ctx, w)]


def is_mandatory(ctx: AuthContext, key: str) -> bool:
    w = WIDGETS.get(key)
    return bool(w and w.mandatory and w.mandatory(ctx))


def _org_wide(ctx, code):
    if not ctx.scope(code).org_wide:
        raise NotAtScope("These figures cover the whole platform, so they need organization-wide access.")


def _money(v) -> str:
    return str((v or Decimal("0")).quantize(Decimal("0.01")))


def _person(u):
    return {"id": str(u.pk), "full_name": u.full_name or u.email} if u else None


# =============================================================================================================
# ACTION: priorities, approvals, my work, quick actions
# =============================================================================================================
def priorities(ctx, p):
    from apps.workflows.engine import urgency
    from apps.workflows.models import ApprovalRequest, Task
    from apps.workflows.selectors import inbox_for

    from . import alerts as alerts_mod
    from .models import WorkNotification

    now = timezone.now()
    items = []
    for t in Task.objects.filter(assignee=ctx.user, status__in=["open", "in_progress"]).filter(
            Q(due_at__lt=now + timedelta(days=2)) | Q(priority__in=["urgent", "high"])).exclude(snoozed_until__gt=now)[:30]:
        overdue = bool(t.due_at and t.due_at < now)
        score = 90 + min(9, (now - t.due_at).days) if overdue else (82 if t.priority == "urgent" else 70 if t.due_at else 60)
        items.append({"kind": "task", "title": t.title, "reason": "Overdue task" if overdue else ("Critical task" if t.priority == "urgent" else
                      "Due soon" if t.due_at else "High priority"), "score": score, "path": f"/tasks?open={t.pk}", "due_at": t.due_at,
                      "severity": "critical" if overdue or t.priority == "urgent" else "high"})
    for r in inbox_for(ctx)[:30]:
        flags = urgency(r, now)
        if not flags:
            continue
        score = 95 if "overdue" in flags else 92 if "blocking" in flags else 86 if "high_value" in flags else 76
        reason = {"overdue": "Approval overdue", "blocking": "Approval blocking other work", "high_value": "High-value approval",
                  "due_soon": "Approval due soon", "waiting_long": "Waiting more than 3 days"}[flags[0]]
        items.append({"kind": "approval", "title": r.title, "reason": reason, "score": score, "path": f"/approvals/{r.pk}", "due_at": r.due_at,
                      "severity": "critical" if "overdue" in flags or "blocking" in flags else "high", "flags": flags})
    for r in ApprovalRequest.objects.filter(requested_by=ctx.user, status="changes_requested")[:10]:
        items.append({"kind": "request", "title": r.title, "reason": "Your request needs changes", "score": 74, "path": f"/approvals/{r.pk}",
                      "due_at": None, "severity": "high"})
    for a in alerts_mod.visible(ctx)[:20]:
        if a.severity in ("critical", "high") and (a.owner_id in (None, ctx.user.pk)):
            items.append({"kind": "alert", "title": a.title, "reason": f"{a.get_severity_display()} {a.category} alert", "score": 93 if a.severity == "critical" else 80,
                          "path": a.link_path or "/home", "due_at": None, "severity": a.severity})
    for n in WorkNotification.objects.filter(recipient=ctx.user, type="deadline", read_at__isnull=True, archived_at__isnull=True)[:5]:
        items.append({"kind": "escalation", "title": n.title, "reason": "Escalation", "score": 88, "path": n.link_path, "due_at": None, "severity": "critical"})
    for src in PRIORITY_SOURCES:
        try:
            items += src(ctx)
        except Exception:
            logger.exception("home.priority_source_failed")
    seen, out = set(), []
    for it in sorted(items, key=lambda i: -i["score"]):
        k = (it["kind"], it["path"])
        if k not in seen:
            seen.add(k)
            out.append(it)
    return {"items": out[:8], "total": len(out)}


def approvals(ctx, p):
    from apps.workflows.engine import urgency
    from apps.workflows.models import ApprovalRequest
    from apps.workflows.selectors import inbox_for

    now = timezone.now()
    inbox = inbox_for(ctx)
    if p.unit is not None:
        inbox = [r for r in inbox if r.org_unit_id and r.org_unit and r.org_unit.path.startswith(p.unit.path)]
    rows = []
    for r in inbox:
        steps = list(r.steps.all())
        rows.append({"id": str(r.pk), "reference": r.reference, "title": r.title, "type": r.policy.name, "module": r.policy.module,
                     "amount": str(r.amount) if r.amount is not None else None, "amount_unit": r.policy.amount_unit, "currency": r.currency,
                     "requested_by": r.requested_by.full_name, "priority": r.priority, "due_at": r.due_at, "created_at": r.created_at,
                     "waiting_hours": int((now - r.created_at).total_seconds() // 3600), "stage": r.current_sequence, "levels": len(steps),
                     "stage_name": next((s.name for s in steps if s.sequence == r.current_sequence), ""), "flags": urgency(r, now),
                     "allow_request_changes": r.policy.allow_request_changes, "path": f"/approvals/{r.pk}",
                     "quick": r.policy.amount_unit != "currency" or r.amount is None or "high_value" not in urgency(r, now)})
    mine = ApprovalRequest.objects.filter(requested_by=ctx.user)
    week = now - timedelta(days=7)
    groups = {g: sum(1 for x in rows if g in x["flags"]) for g in ("overdue", "due_soon", "high_value", "blocking")}
    return {"counts": {"waiting_on_me": len(rows), **groups, "my_pending": mine.filter(status="pending").count(),
                       "changes_requested": mine.filter(status="changes_requested").count(),
                       "approved_week": mine.filter(status="approved", decided_at__gte=week).count(),
                       "rejected_week": mine.filter(status="rejected", decided_at__gte=week).count()},
            "items": rows[:8]}


def my_work(ctx, p):
    from apps.workflows.models import Task
    from apps.workflows.selectors import inbox_for

    now = timezone.now()
    end_today = (timezone.localtime(now)).replace(hour=23, minute=59, second=59)
    mine = Task.objects.filter(assignee=ctx.user, status__in=["open", "in_progress"]).select_related("created_by")
    active = mine.exclude(snoozed_until__gt=now)
    follow_ups = Task.objects.filter(created_by=ctx.user, status__in=["open", "in_progress"]).exclude(assignee=ctx.user)
    items = list(active.order_by("due_at", "-created_at")[:8])
    counts = {"open": mine.count(), "overdue": active.filter(due_at__lt=now).count(),
              "due_today": active.filter(due_at__gte=now, due_at__lte=end_today).count(),
              "due_week": active.filter(due_at__gte=now, due_at__lt=now + timedelta(days=7)).count(),
              "follow_ups": follow_ups.count(), "snoozed": mine.filter(snoozed_until__gt=now).count(),
              "approvals": len(inbox_for(ctx))}
    extra = []
    for src in MY_WORK_SOURCES:  # modules add assigned reviews, tickets, interviews …
        try:
            extra += src(ctx)
        except Exception:
            logger.exception("home.my_work_source_failed")
    return {"counts": counts, "assigned": extra,
            "items": [{"id": str(t.pk), "title": t.title, "priority": t.priority, "status": t.status, "due_at": t.due_at,
                       "overdue": bool(t.due_at and t.due_at < now), "from": t.created_by.full_name if t.created_by_id != ctx.user.pk else None,
                       "module": t.module, "path": t.link_path or f"/tasks?open={t.pk}"} for t in items]}


MY_WORK_SOURCES: list[Callable] = []


def quick_actions(ctx, p):
    from .context import quick_actions as qa

    pins = ((ctx.account.preferences or {}).get("home") or {}).get("quick_pins", []) if ctx.account else []
    acts = qa(ctx)
    for a in acts:
        a["pinned"] = a["key"] in pins
    acts.sort(key=lambda a: (not a["pinned"], pins.index(a["key"]) if a["key"] in pins else 99))
    return {"items": acts}


# =============================================================================================================
# ATTENTION: alerts, priority inbox, announcements, risk watch
# =============================================================================================================
def alerts(ctx, p):
    from . import alerts as alerts_mod

    alerts_mod.run(ctx.organization)
    rows = alerts_mod.visible(ctx)
    if p.unit is not None:
        rows = [a for a in rows if a.org_wide_only or not a.org_unit_id or (a.org_unit and a.org_unit.path.startswith(p.unit.path))]
    by = {s: sum(1 for a in rows if a.severity == s) for s in ("critical", "high", "medium", "low")}
    return {"counts": by, "items": [alerts_mod.payload(a) for a in rows[:10]], "total": len(rows)}


def priority_inbox(ctx, p):
    from . import alerts as alerts_mod
    from .models import WorkNotification

    since = timezone.now() - timedelta(days=7)
    out = []
    for n in WorkNotification.objects.filter(recipient=ctx.user, archived_at__isnull=True, created_at__gte=since)[:60]:
        level = "critical" if n.priority == "critical" or (n.type == "security" and n.priority != "normal") else \
            "important" if n.priority == "important" or n.type in ("approval_request", "deadline", "security") else None
        if level and not (n.read_at and level == "important"):
            out.append({"id": f"n:{n.pk}", "level": level, "title": n.title, "body": n.body, "source": n.get_type_display(), "path": n.link_path,
                        "at": n.created_at, "read": n.read_at is not None, "notification_id": str(n.pk)})
    for a in alerts_mod.visible(ctx)[:20]:
        if a.severity in ("critical", "high"):
            out.append({"id": f"a:{a.pk}", "level": "critical" if a.severity == "critical" else "important", "title": a.title, "body": a.detail,
                        "source": a.source, "path": a.link_path, "at": a.last_seen_at, "read": a.status != "open", "alert_id": str(a.pk)})
    out.sort(key=lambda x: (x["level"] != "critical", x["read"], -x["at"].timestamp()))
    return {"items": out[:10], "counts": {"critical": sum(1 for x in out if x["level"] == "critical"),
                                          "important": sum(1 for x in out if x["level"] == "important")}}


def announcements(ctx, p):
    from .announcements import visible_for, payload

    rows = visible_for(ctx)
    return {"items": [payload(a, ctx) for a in rows[:6]], "total": len(rows),
            "can_create": ctx.has("communications.announcement.create")}


def _has_critical_announcement(ctx) -> bool:
    from .announcements import visible_for

    return any(a.priority == "critical" for a in visible_for(ctx))


def risk_watch(ctx, p):
    from . import alerts as alerts_mod

    alerts_mod.run(ctx.organization)
    rows = [a for a in alerts_mod.visible(ctx) if a.is_risk or a.severity == "critical"]
    return {"items": [alerts_mod.payload(a) for a in rows[:10]], "total": len(rows)}


# =============================================================================================================
# AWARENESS: upcoming, recent activity, team
# =============================================================================================================
def upcoming(ctx, p):
    from .calendar import upcoming as up

    now = timezone.localtime()
    today = now.date()
    items = up(ctx, days=7, start=now.replace(hour=0, minute=0, second=0, microsecond=0))
    groups = {"today": [], "tomorrow": [], "this_week": []}
    for i in items:
        d = timezone.localtime(i["at"]).date() if hasattr(i["at"], "tzinfo") and i["at"].tzinfo else i["at"].date()
        key = "today" if d == today else "tomorrow" if d == today + timedelta(days=1) else "this_week"
        groups[key].append(i)
    return {"groups": [{"key": k, "label": {"today": "Today", "tomorrow": "Tomorrow", "this_week": "This week"}[k], "items": v[:8]}
                       for k, v in groups.items()], "total": len(items)}


ACTIVITY_LABELS = {
    "auth.login": "Signed in", "auth.logout": "Signed out", "approval.submitted": "Raised an approval request", "approval.approved": "Approved a request",
    "approval.rejected": "Rejected a request", "approval.changes_requested": "Requested changes", "approval.resubmitted": "Resubmitted a request",
    "workflows.task.create": "Created a task", "workflows.task.update": "Updated a task", "home.layout.update": "Changed Home layout",
    "profile.update": "Updated profile", "documents.upload": "Uploaded a document", "access.role.assigned": "Assigned a role",
    "identity.user.invited": "Invited a user", "home.quick_action": "Used a quick action", "ai.query": "Asked Business AI",
}


def recent_activity(ctx, p):
    from apps.audit.models import AuditEvent

    rows = AuditEvent.objects.filter(actor=ctx.user).exclude(action__in=["auth.session.revoked"]).order_by("-created_at")[:12]
    return {"items": [{"id": str(e.pk), "action": e.action, "label": ACTIVITY_LABELS.get(e.action, e.action.replace(".", " ").replace("_", " ").capitalize()),
                       "resource": e.resource_label if not e.sensitive else "", "outcome": e.outcome, "at": e.created_at} for e in rows]}


def team(ctx, p):
    """Managers only (from the reporting line). Counts and work items — no salary, ratings or private HR data."""
    from apps.people.models import Employee
    from apps.workflows.models import ApprovalRequest, Task

    now = timezone.now()
    members = list(Employee.objects.filter(pk__in=ctx.direct_report_ids).select_related("designation", "user"))
    user_ids = [m.user_id for m in members if m.user_id]
    tasks = Task.objects.filter(assignee_id__in=user_ids)
    open_by = dict(tasks.filter(status__in=["open", "in_progress"]).values_list("assignee_id").annotate(n=Count("id")))
    overdue_by = dict(tasks.filter(status__in=["open", "in_progress"], due_at__lt=now).values_list("assignee_id").annotate(n=Count("id")))
    done_week = tasks.filter(status="done", completed_at__gte=now - timedelta(days=7)).count()
    pending_reqs = ApprovalRequest.objects.filter(requested_by_id__in=user_ids, status="pending")
    on_leave = set()
    for src in TEAM_SOURCES:
        try:
            on_leave |= src(ctx, members)
        except Exception:
            logger.exception("home.team_source_failed")
    return {
        "counts": {"members": len(members), "all_reports": len(ctx.report_ids[0]), "open_tasks": sum(open_by.values()),
                   "overdue": sum(overdue_by.values()), "done_week": done_week, "requests_pending": pending_reqs.count(),
                   "escalations": pending_reqs.filter(due_at__lt=now).count(), "away_today": len(on_leave)},
        "members": [{"id": str(m.pk), "full_name": m.full_name, "designation": m.designation.name if m.designation else None,
                     "open_tasks": open_by.get(m.user_id, 0), "overdue": overdue_by.get(m.user_id, 0), "away": m.pk in on_leave,
                     "path": f"/people/{m.pk}"} for m in members[:12]],
    }


TEAM_SOURCES: list[Callable] = []  # fn(ctx, members) -> set of employee ids away today


# =============================================================================================================
# INSIGHT & DECISION: pulse, insights, opportunities, AI briefing
# =============================================================================================================
def business_pulse(ctx, p):
    from . import pulse

    keys = pulse.chosen(ctx)
    return {"period": p.period.as_dict(), "metrics": pulse.compute(ctx, keys, p.period, p.unit), "available": pulse.available(ctx),
            "selected": keys, "location": p.unit.name if p.unit is not None else None,
            "note": "Gross transaction value is what customers paid through Click, not Click revenue. Platform-wide figures aren’t split by location yet."}


INSIGHT_TEXT = {
    "gmv": ("Customer spend on the platform", "Check which services drove the change before drawing conclusions."),
    "orders": ("Order volume drives partner earnings and support load", "Compare by store category in Operations."),
    "bookings": ("Bookings reflect demand for services and events", "Review capacity with partners if demand keeps rising."),
    "customers": ("New customers indicate acquisition health", "Look at referral and campaign sources."),
    "failed_payments": ("Failed payments are lost sales and frustrated customers", "Check gateway status and failure reasons."),
    "refunds": ("Refunds reduce collections and can signal quality issues", "Review the stores and services with the most refunds."),
    "expenses": ("Spending through expense claims", "Compare with the department budget once Finance is live."),
    "rides": ("Ride demand affects driver availability", "Check driver supply in the busiest areas."),
}


def insights(ctx, p):
    from . import pulse

    out = []
    keys = [k for k in pulse.available(ctx) if k in INSIGHT_TEXT]
    for m in pulse.compute(ctx, keys, p.period, p.unit):
        if m["delta_pct"] is None or m["previous"] in (None, ""):
            continue
        try:
            cur, prev = float(m["value"]), float(m["previous"])
        except (TypeError, ValueError):
            continue
        if max(cur, prev) < 5 or abs(m["delta_pct"]) < 20:  # too small or too little change to mean anything
            continue
        why, step = INSIGHT_TEXT[m["key"]]
        up = m["delta_pct"] > 0
        out.append({"key": m["key"], "kind": "observed", "direction": "up" if up else "down",
                    "good": (up and m["good_when"] == "up") or (not up and m["good_when"] == "down"),
                    "title": f"{m['label']} {'up' if up else 'down'} {abs(m['delta_pct'])}%",
                    "what": f"{m['label']}: {m['value']} vs {m['previous']} in the previous period.", "why": why,
                    "period": p.period.label, "source": m["source"], "next_step": step, "path": m["drill"]})
    for src in INSIGHT_SOURCES:
        try:
            out += src(ctx, p.period)
        except Exception:
            logger.exception("home.insight_source_failed")
    return {"items": out[:8], "period": p.period.label,
            "empty_reason": None if out else "No significant changes (20% or more, on meaningful volume) in this period."}


def opportunities(ctx, p):
    """Observed facts first; any suggestion is labelled as a rule-based suggestion, not a forecast."""
    _org_wide(ctx, "analytics.business.view")
    from apps.orders.models import Order
    from apps.professionals.models import ServiceBooking

    per = p.period
    out = []
    cur = dict(Order.objects.filter(created_at__gte=per.start, created_at__lt=per.end).values_list("store__store_type").annotate(n=Count("id")))
    prev = dict(Order.objects.filter(created_at__gte=per.prev_start, created_at__lt=per.prev_end).values_list("store__store_type").annotate(n=Count("id")))
    for st, n in sorted(cur.items(), key=lambda kv: -kv[1]):
        before = prev.get(st, 0)
        if n >= 10 and before and (n - before) / before >= 0.25:
            out.append({"kind": "growth", "observed": f"{(st or 'Other').capitalize()} orders grew from {before} to {n} ({round((n - before) / before * 100)}%).",
                        "suggestion": "Consider a featured placement or partner onboarding drive for this category.", "source": "Orders",
                        "period": per.label, "path": "/m/marketing"})
    top = (Order.objects.filter(created_at__gte=per.start, created_at__lt=per.end, status="delivered").values("store__name")
           .annotate(n=Count("id")).order_by("-n").first())
    if top and top["n"] >= 10:
        out.append({"kind": "partner", "observed": f"{top['store__name']} completed the most delivered orders ({top['n']}).",
                    "suggestion": "A candidate for a partner spotlight or co-marketing.", "source": "Orders", "period": per.label, "path": "/m/partners"})
    svc = dict(ServiceBooking.objects.filter(created_at__gte=per.start, created_at__lt=per.end).values_list("category__name").annotate(n=Count("id")))
    if svc:
        name, n = max(svc.items(), key=lambda kv: kv[1])
        if n >= 5:
            out.append({"kind": "service", "observed": f"{name} is the most booked home service ({n} bookings).",
                        "suggestion": "Check provider coverage so demand isn’t lost.", "source": "Services", "period": per.label, "path": "/m/services"})
    return {"items": out, "period": per.label,
            "disclaimer": "Observed data comes from Click records. Suggestions are rule-based prompts for discussion, not predictions."}


def ai_briefing(ctx, p):
    from apps.workflows.models import Task
    from apps.workflows.selectors import inbox_for

    from . import alerts as alerts_mod
    from . import pulse

    now = timezone.now()
    lines = []
    inbox = inbox_for(ctx)
    overdue_apr = sum(1 for r in inbox if r.due_at and r.due_at < now)
    if inbox:
        lines.append({"text": f"{len(inbox)} approval{'s' if len(inbox) != 1 else ''} need your decision" + (f", {overdue_apr} overdue." if overdue_apr else "."),
                      "source": "Approvals", "path": "/approvals"})
    t = Task.objects.filter(assignee=ctx.user, status__in=["open", "in_progress"])
    od, today_n = t.filter(due_at__lt=now).count(), t.filter(due_at__gte=now, due_at__lt=now + timedelta(days=1)).count()
    if od or today_n:
        lines.append({"text": f"You have {today_n} task{'s' if today_n != 1 else ''} due in the next 24 hours" + (f" and {od} overdue." if od else "."),
                      "source": "Tasks", "path": "/tasks"})
    crit = [a for a in alerts_mod.visible(ctx) if a.severity in ("critical", "high")]
    if crit:
        lines.append({"text": f"{len(crit)} important alert{'s' if len(crit) != 1 else ''} open: {crit[0].title.lower()}.", "source": crit[0].source,
                      "path": crit[0].link_path or "/home"})
    if "gmv" in pulse.available(ctx):
        y = periods_mod.resolve("yesterday", tz_name=ctx.account.timezone if ctx.account else None)
        m = pulse.compute(ctx, ["gmv", "orders"], y)
        for x in m:
            if x["delta_pct"] is not None:
                lines.append({"text": f"{x['label']} yesterday: {x['value']} ({'+' if x['delta_pct'] >= 0 else ''}{x['delta_pct']}% vs the day before).",
                              "source": x["source"], "path": x["drill"]})
            elif x["value"] not in (None, 0, "0.00"):
                lines.append({"text": f"{x['label']} yesterday: {x['value']} (not enough data to compare).", "source": x["source"], "path": x["drill"]})
    for src in BRIEFING_SOURCES:
        try:
            lines += src(ctx)
        except Exception:
            logger.exception("home.briefing_source_failed")
    return {"lines": lines, "generated_from": "Only records you’re allowed to see. No figures are estimated.",
            "empty": None if lines else "Nothing needs your attention right now, and there isn’t enough new data for a summary yet."}


# =============================================================================================================
# SNAPSHOTS: ecosystem, services, partners, finance, operations, security, system
# =============================================================================================================
def ecosystem(ctx, p):
    _org_wide(ctx, "analytics.business.view")
    from apps.customers.models import CustomerProfile
    from apps.discover.models import AdCampaign
    from apps.orders.models import Order
    from apps.parcels.models import ParcelOrder
    from apps.partners.models import Partner
    from apps.rides.models import Ride
    from apps.stores.models import Store
    from apps.support.models import SupportTicket

    per = p.period
    active_partners = Partner.objects.filter(status=Partner.Status.ACTIVE)
    in_period = lambda m: m.objects.filter(created_at__gte=per.start, created_at__lt=per.end).count()  # noqa: E731
    return {
        "period": per.label,
        "participants": [
            {"key": "customers", "label": "Customers", "value": CustomerProfile.objects.count(), "path": "/m/sales"},
            {"key": "partners", "label": "Active partners", "value": active_partners.count(), "path": "/m/partners"},
            {"key": "merchants", "label": "Live stores & merchants", "value": Store.objects.filter(status="active").count(), "path": "/m/partners"},
            {"key": "drivers", "label": "Drivers & riders", "value": active_partners.filter(partner_type__slug="transport").count(), "path": "/m/services"},
        ],
        "activity": [
            {"key": "orders", "label": "Orders", "value": in_period(Order), "path": "/m/operations"},
            {"key": "rides", "label": "Rides", "value": in_period(Ride), "path": "/m/operations"},
            {"key": "parcels", "label": "Parcel deliveries", "value": in_period(ParcelOrder), "path": "/m/supply_chain"},
            {"key": "support", "label": "Open support cases", "value": SupportTicket.objects.exclude(status__in=["resolved", "closed"]).count(), "path": "/m/cx"},
            {"key": "sponsored", "label": "Active sponsored campaigns", "value": AdCampaign.objects.filter(status="active").count(), "path": "/m/marketing"},
        ],
        "transactions": {
            "platform_gmv": _money(__import__("apps.payments.models", fromlist=["Payment"]).Payment.objects.filter(
                status="captured", created_at__gte=per.start, created_at__lt=per.end).aggregate(s=Sum("amount"))["s"]),
            "classified": False,
            "note": "All platform transactions are shown together as gross value. Partner-fulfilled, Click-operated and Click-owned-inventory "
                    "transactions, commission and partner settlements will be separated once each relationship's commercial model is recorded "
                    "(Partners and Finance modules).",
        },
    }


def services_snapshot(ctx, p):
    from apps.professionals.models import ProviderProfile, ServiceBooking, ServiceReview

    per = p.period
    qs = ServiceBooking.objects.filter(created_at__gte=per.start, created_at__lt=per.end)
    by = dict(qs.values_list("status").annotate(n=Count("id")))
    total = sum(by.values())
    done = by.get("completed", 0) + by.get("paid", 0)
    avg = ServiceReview.objects.filter(created_at__gte=per.start, created_at__lt=per.end).values_list("overall", flat=True)
    ratings = [r for r in avg if r is not None]
    return {"period": per.label, "metrics": [
        {"key": "providers", "label": "Service providers", "value": ProviderProfile.objects.count(), "format": "number"},
        {"key": "requests", "label": "Service bookings", "value": total, "format": "number"},
        {"key": "active", "label": "In progress now", "value": ServiceBooking.objects.filter(status__in=["confirmed", "on_the_way", "arrived", "in_progress"]).count(), "format": "number"},
        {"key": "completion", "label": "Completion rate", "value": f"{round(done / total * 100)}%" if total else "—", "format": "text"},
        {"key": "unassigned", "label": "No professional found", "value": by.get("unassigned", 0), "format": "number", "alert": by.get("unassigned", 0) > 0},
        {"key": "rating", "label": "Average rating", "value": f"{sum(ratings) / len(ratings):.1f}" if ratings else "—", "format": "text"},
    ], "note": "Service revenue and commission arrive with the Click Services and Finance modules.", "path": "/m/services"}


def partner_snapshot(ctx, p):
    from apps.partners.models import Partner, PartnerDocument

    today = timezone.now().date()
    by = dict(Partner.objects.values_list("status").annotate(n=Count("id")))
    order = ["profile_completed", "verification_pending", "verified", "active", "suspended", "rejected"]
    return {"stages": [{"key": s, "label": Partner.Status(s).label, "value": by.get(s, 0)} for s in order],
            "total": sum(by.values()),
            "new_week": Partner.objects.exclude(status="draft").filter(created_at__gte=timezone.now() - timedelta(days=7)).count(),
            "documents_expiring": PartnerDocument.objects.filter(status="verified", expires_on__gte=today, expires_on__lte=today + timedelta(days=30)).count(),
            "documents_pending": PartnerDocument.objects.filter(status="pending").count(), "path": "/m/partners"}


def finance_snapshot(ctx, p):
    _org_wide(ctx, "finance.overview.view")
    from apps.payments.models import Payment
    from apps.workflows.models import ApprovalRequest

    per = p.period
    pay = Payment.objects.filter(created_at__gte=per.start, created_at__lt=per.end)
    s = lambda qs: _money(qs.aggregate(x=Sum("amount"))["x"])  # noqa: E731
    exp = ApprovalRequest.objects.filter(organization=ctx.organization, policy__key="finance.expense", created_at__gte=per.start, created_at__lt=per.end)
    na = "Needs the Finance & settlements modules"
    return {"period": per.label, "lines": [
        {"key": "gtv", "label": "Gross transaction value", "value": s(pay.filter(status="captured")), "available": True,
         "explain": "Everything customers paid through Click."},
        {"key": "refunds", "label": "Refunds", "value": s(Payment.objects.filter(status="refunded", updated_at__gte=per.start, updated_at__lt=per.end)), "available": True},
        {"key": "failed", "label": "Failed payments", "value": pay.filter(status="failed").count(), "available": True, "format": "number"},
        {"key": "pending", "label": "Pending payments", "value": Payment.objects.filter(status__in=["pending", "authorized"]).count(), "available": True, "format": "number"},
        {"key": "click_revenue", "label": "Click revenue", "value": None, "available": False, "explain": na},
        {"key": "commission", "label": "Commission", "value": None, "available": False, "explain": na},
        {"key": "partner_earnings", "label": "Partner earnings", "value": None, "available": False, "explain": na},
        {"key": "platform_fees", "label": "Platform fees", "value": None, "available": False, "explain": na},
        {"key": "net", "label": "Net amount", "value": None, "available": False, "explain": na},
        {"key": "expenses", "label": "Expense claims (Business OS)", "value": s(exp.exclude(status="cancelled")), "available": True,
         "explain": f"{exp.filter(status='approved').count()} approved, {exp.filter(status='pending').count()} pending."},
    ], "note": "Receivables, payables and cash position arrive with the Finance module. Figures are never blended into one “revenue” number."}


def operations_overview(ctx, p):
    _org_wide(ctx, "operations.order.view")
    from apps.orders.models import Order
    from apps.support.models import SupportTicket

    now = timezone.now()
    active_states = ["placed", "confirmed", "preparing", "ready", "packed", "shipped", "out_for_delivery"]
    stale = Order.objects.filter(status__in=["placed", "confirmed"], created_at__lt=now - timedelta(minutes=45), created_at__gte=now - timedelta(days=2)).count()
    by_status = dict(Order.objects.filter(status__in=active_states).values_list("status").annotate(n=Count("id")))
    return {"metrics": [
        {"key": "active_orders", "label": "Active orders", "value": sum(by_status.values()), "format": "number"},
        {"key": "stale", "label": "Waiting > 45 min", "value": stale, "format": "number", "alert": stale > 0},
        {"key": "cancelled_today", "label": "Cancelled today",
         "value": Order.objects.filter(status="cancelled", updated_at__gte=timezone.localtime(now).replace(hour=0, minute=0, second=0)).count(), "format": "number"},
        {"key": "tickets_urgent", "label": "Urgent tickets open",
         "value": SupportTicket.objects.exclude(status__in=["resolved", "closed"]).filter(priority="urgent").count(), "format": "number"},
    ], "breakdown": [{"label": k.replace("_", " ").capitalize(), "value": v} for k, v in sorted(by_status.items())]}


def security_overview(ctx, p):
    _org_wide(ctx, "identity.user.view")
    from apps.access.models import OSAccount
    from apps.audit.models import AuditEvent

    accts = OSAccount.objects.filter(organization=ctx.organization)
    active = accts.filter(status="active")
    day = timezone.now() - timedelta(hours=24)
    return {"metrics": [
        {"key": "active", "label": "Active accounts", "value": active.count(), "format": "number"},
        {"key": "mfa", "label": "With MFA", "value": active.filter(mfa_enabled_at__isnull=False).count(), "format": "number"},
        {"key": "suspended", "label": "Suspended", "value": accts.filter(status="suspended").count(), "format": "number"},
        {"key": "locked", "label": "Locked now", "value": accts.filter(locked_until__gt=timezone.now()).count(), "format": "number"},
        {"key": "failed_24h", "label": "Failed sign-ins · 24h",
         "value": AuditEvent.objects.filter(organization=ctx.organization, action="auth.login", outcome="failure", created_at__gte=day).count(), "format": "number"},
    ]}


def system_status(ctx, p):
    from .views import health_checks

    checks = health_checks()
    last = cache.get(f"os:alerts:last-success:{ctx.organization.pk}")
    return {"checks": [c for c in checks if c["key"] in ("database", "migrations", "payments", "sms", "email", "ai")],
            "jobs": [{"key": "alerts", "label": "Alert detectors", "last_run": last, "status": "ok" if last else "not_run"}],
            "overall": "error" if any(c["status"] == "error" for c in checks) else "warning" if any(c["status"] == "warning" for c in checks) else "ok"}


def security(ctx, p):
    from apps.access.models import OSSession

    acct = ctx.account
    live = OSSession.objects.filter(user=ctx.user, revoked_at__isnull=True, expires_at__gt=timezone.now()).count()
    return {"mfa_enabled": acct.mfa_enabled, "active_sessions": live, "last_login_at": acct.last_login_at,
            "recovery_codes_left": len(acct.recovery_codes or []), "mfa_blocked": len(ctx.mfa_blocked)}


# =============================================================================================================
# Registry
# =============================================================================================================
EVERYONE = ("employee", "external", "partner")
STAFF = ("employee", "external")
for _w in (
    Widget("priorities", "My priorities", "l", "action", priorities, description="What matters most across modules", refresh=60),
    Widget("approvals", "Approval center", "m", "action", approvals, description="Decide without leaving Home", refresh=60, unit_aware=True),
    Widget("alerts", "Alerts & exceptions", "m", "attention", alerts, description="Exceptions that need someone", refresh=60,
           mandatory=lambda ctx: True, unit_aware=True),
    Widget("my_work", "My work", "m", "action", my_work, description="Tasks, follow-ups and assigned work", refresh=60),
    Widget("priority_inbox", "Priority inbox", "m", "attention", priority_inbox, description="Only critical and important events", refresh=60),
    Widget("quick_actions", "Quick actions", "l", "action", quick_actions, audience=STAFF),
    Widget("upcoming", "Upcoming", "m", "awareness", upcoming, description="Today, tomorrow and this week"),
    Widget("announcements", "Announcements", "m", "attention", announcements, mandatory=_has_critical_announcement, refresh=300),
    Widget("recent_activity", "Recent activity", "m", "awareness", recent_activity, description="Your own recent actions"),
    Widget("team", "Team activity", "l", "awareness", team, description="Your reports’ workload", audience=("employee",),
           requires=lambda ctx: ctx.is_manager),
    Widget("ai_briefing", "Business briefing", "m", "insight", ai_briefing, permission="ai.assistant.view", source="Business AI (your data only)",
           refresh=600, audience=STAFF),
    Widget("business_pulse", "Business pulse", "l", "insight", business_pulse, permission=(
        "analytics.business.view", "finance.overview.view", "operations.order.view", "partners.partner.view", "cx.ticket.view",
        "people.employee.view", "finance.expense.view", "services.booking.view", "sales.customer.view"),
        periods=True, unit_aware=True, refresh=300, audience=STAFF, cache_seconds=60),
    Widget("insights", "Business insights", "m", "insight", insights, permission=(
        "analytics.business.view", "finance.overview.view", "operations.order.view", "finance.expense.view", "people.employee.view"),
        periods=True, refresh=900, audience=STAFF, cache_seconds=120),
    Widget("opportunities", "Opportunities", "m", "decision", opportunities, permission="analytics.business.view", org_wide=True,
           periods=True, refresh=1800, audience=STAFF, cache_seconds=300),
    Widget("risk_watch", "Risk watch", "m", "attention", risk_watch, permission=(
        "analytics.business.view", "risk.risk.view", "partners.verification.view", "identity.user.view", "people.document.view",
        "finance.overview.view", "system.health.view"), audience=STAFF),
    Widget("ecosystem", "Click ecosystem", "l", "awareness", ecosystem, permission="analytics.business.view", org_wide=True, periods=True,
           refresh=600, audience=STAFF, cache_seconds=120),
    Widget("services_snapshot", "Click Services", "m", "awareness", services_snapshot, permission=("services.service.view", "services.booking.view"),
           periods=True, audience=STAFF, cache_seconds=120),
    Widget("partner_snapshot", "Partner snapshot", "m", "awareness", partner_snapshot, permission="partners.partner.view", org_wide=True,
           audience=STAFF, cache_seconds=120),
    Widget("finance_snapshot", "Financial snapshot", "l", "insight", finance_snapshot, permission="finance.overview.view", org_wide=True,
           periods=True, audience=STAFF, cache_seconds=60),
    Widget("operations_overview", "Operations", "m", "awareness", operations_overview, permission="operations.order.view", org_wide=True,
           audience=STAFF, refresh=60),
    Widget("security_overview", "Security & access", "m", "attention", security_overview, permission="identity.user.view", org_wide=True,
           audience=STAFF),
    Widget("system_status", "System status", "s", "awareness", system_status, permission="system.health.view", audience=STAFF, refresh=120),
    Widget("security", "Account security", "s", "awareness", security),
):
    register(_w)

# Defaults when a role brings none. Partners get only their own workspace basics.
BASE_LAYOUT = ["priorities", "approvals", "alerts", "my_work", "upcoming", "priority_inbox", "announcements", "quick_actions",
               "recent_activity", "security"]
PARTNER_LAYOUT = ["priorities", "approvals", "alerts", "announcements", "upcoming", "my_work", "recent_activity", "security"]
SIZES = ("s", "m", "l")

PRESET_VIEWS = {
    "daily_work": ("My daily work", ["priorities", "my_work", "approvals", "upcoming", "priority_inbox", "alerts"]),
    "executive": ("Executive view", ["business_pulse", "ecosystem", "priorities", "approvals", "risk_watch", "insights", "opportunities",
                                     "finance_snapshot", "alerts"]),
    "finance": ("Finance overview", ["finance_snapshot", "business_pulse", "approvals", "alerts", "insights"]),
    "branch_ops": ("Branch operations", ["operations_overview", "approvals", "alerts", "team", "my_work", "upcoming"]),
    "partner_monitoring": ("Partner monitoring", ["partner_snapshot", "alerts", "risk_watch", "approvals"]),
    "people": ("People & HR", ["people_overview", "pending_leave", "new_joiners", "document_expiries", "probation_ending", "approvals", "alerts"]),
}


def presets_for(ctx) -> list[dict]:
    """Only views whose business widgets the person can all see."""
    allowed = set(available(ctx))
    out = []
    for key, (name, keys) in PRESET_VIEWS.items():
        business = [k for k in keys if k in WIDGETS and WIDGETS[k].permission is not None]
        if all(k in allowed for k in business) and any(k in allowed for k in keys):
            out.append({"id": f"preset:{key}", "name": name, "preset": True, "widgets": [k for k in keys if k in allowed]})
    return out


def _home_prefs(ctx) -> dict:
    return ((ctx.account.preferences or {}).get("home") or {}) if ctx.account else {}


def default_layout(ctx) -> list[dict]:
    allowed = set(available(ctx))
    order: list[str] = []
    for role in sorted({r.pk: r for r in ctx.roles}.values(), key=lambda r: (r.priority, r.name)):
        order += [k for k in (role.home_widgets or []) if k not in order]
    base = PARTNER_LAYOUT if ctx.kind == "partner" else BASE_LAYOUT
    if ctx.is_manager and "team" not in order:
        order.append("team")
    # Action and attention first, then the role's business widgets, then the rest of the base layout.
    head = [k for k in base[:3] if k not in order]
    order = head + order + [k for k in base[3:] if k not in order]
    return [{"key": k, "size": WIDGETS[k].size, "period": None, "pinned": False} for k in order if k in allowed]


def layout_for(ctx) -> tuple[list[dict], str | None]:
    """(effective layout, active view id). Mandatory widgets are always present; permission always applies."""
    allowed = set(available(ctx))
    prefs = _home_prefs(ctx)
    active = prefs.get("active_view")
    rows = None
    if active and active.startswith("preset:"):
        p = next((v for v in presets_for(ctx) if v["id"] == active), None)
        rows = [{"key": k, "size": WIDGETS[k].size, "period": None, "pinned": False} for k in p["widgets"]] if p else None
    elif active:
        v = next((v for v in prefs.get("views", []) if v.get("id") == active), None)
        rows = v.get("layout") if v else None
    if rows is None:
        rows = prefs.get("layout")
    if not rows:
        rows, active = default_layout(ctx), None
        hidden = set(prefs.get("hidden", []))
        rows = [r for r in rows if r["key"] not in hidden]
    clean, seen = [], set()
    for r in rows:
        k = r.get("key")
        if k in allowed and k not in seen:
            seen.add(k)
            clean.append({"key": k, "size": r.get("size") if r.get("size") in SIZES else WIDGETS[k].size,
                          "period": r.get("period") if r.get("period") in periods_mod.CHOICES else None, "pinned": bool(r.get("pinned"))})
    for k in allowed:  # mandatory widgets can't be removed
        if k not in seen and is_mandatory(ctx, k):
            clean.insert(0, {"key": k, "size": WIDGETS[k].size, "period": None, "pinned": True})
    clean.sort(key=lambda r: not r["pinned"])
    return clean, active


def meta(ctx, key: str, row: dict | None = None) -> dict:
    w = WIDGETS[key]
    return {"key": key, "title": w.title, "size": (row or {}).get("size") or w.size, "category": w.category, "description": w.description,
            "source": w.source, "refresh_seconds": w.refresh, "periods": w.periods, "unit_aware": w.unit_aware,
            "mandatory": is_mandatory(ctx, key), "period": (row or {}).get("period"), "pinned": bool((row or {}).get("pinned"))}


def render_one(ctx, key: str, params: Params) -> dict:
    w = WIDGETS[key]
    out = {"key": key, "title": w.title, "data": None, "error": None, "generated_at": timezone.now(), "source": w.source,
           "refresh_seconds": w.refresh, "live": w.cache_seconds == 0,
           "period": params.period.as_dict() if (w.periods and params.period) else None,
           "location": params.unit.name if (w.unit_aware and params.unit is not None) else None}
    ck = None
    if w.cache_seconds:
        sig = f"{ctx.user.pk}:{ctx.account.access_version if ctx.account else 0}:{key}:{getattr(params.unit, 'pk', '')}:" \
              f"{params.period.key if params.period else ''}:{params.period.start.isoformat() if params.period else ''}"
        ck = "os:widget:" + sig
        hit = cache.get(ck)
        if hit:
            return {**out, **hit, "live": False, "cached": True}
    try:
        out["data"] = w.loader(ctx, params)
        if ck:
            cache.set(ck, {"data": out["data"], "generated_at": out["generated_at"]}, w.cache_seconds)
    except NotAtScope as e:
        out["error"] = {"code": "not_at_scope", "message": str(e)}
    except Exception:
        logger.exception("home.widget_failed", extra={"widget": key})
        out["error"] = {"code": "widget_failed", "message": f"Unable to load {w.title}. Try again shortly."}
    return out


# --- backward-compatible helpers used by AI tools ---------------------------------------------------------
def business_snapshot(ctx):
    from . import pulse

    _org_wide(ctx, "analytics.business.view")
    per = periods_mod.resolve("last_30_days")
    ms = pulse.compute(ctx, [k for k in ("gmv", "orders", "partners", "customers", "open_tickets") if k in pulse.available(ctx)], per)
    return {"period": per.label, "metrics": ms, "note": "Gross transaction value is customer spend through Click, not Click revenue."}


def people_overview_data(ctx):
    from apps.people.models import Employee

    scope = ctx.scope("people.employee.view")
    qs = Employee.objects.filter(organization=ctx.organization).filter(
        scope.q(unit="org_unit", department="department", team="team", owner="user", employee="pk", organization=None))
    by_status = dict(qs.values_list("status").annotate(n=Count("id")))
    return {"metrics": [{"key": k, "label": k.replace("_", " ").capitalize(), "value": v} for k, v in sorted(by_status.items())]}
