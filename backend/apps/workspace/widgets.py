"""
Home is composed, not hard-coded per role.

    Widget registry (this file)  +  Role.home_widgets (what each role brings)  +  account.preferences.home (hide / order)
      → filtered by each widget's permission → each widget loads independently (one failing never blanks Home).

Business numbers come from the live Click platform tables (orders, payments, partners, support). Platform-wide
figures need an organization-wide grant; a narrower scope gets an honest "not available at your scope" rather
than numbers it isn't entitled to.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Callable

from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.access.authz import AuthContext

logger = logging.getLogger(__name__)


class NotAtScope(Exception):
    pass


@dataclass(frozen=True)
class Widget:
    key: str
    title: str
    size: str  # s | m | l
    permission: str | None
    loader: Callable[[AuthContext], dict]
    description: str = ""


def _org_wide(ctx: AuthContext, code: str):
    if not ctx.scope(code).org_wide:
        raise NotAtScope("These figures cover the whole platform, so they need organization-wide access.")


def _money(v) -> str:
    return str((v or Decimal("0")).quantize(Decimal("0.01")))


# --- personal widgets ------------------------------------------------------------
def my_work(ctx):
    from apps.workflows.models import Task

    now = timezone.now()
    open_q = Task.objects.filter(assignee=ctx.user, status__in=[Task.Status.OPEN, Task.Status.IN_PROGRESS])
    items = list(open_q.order_by("due_at", "-created_at")[:6])
    return {
        "counts": {"open": open_q.count(), "overdue": open_q.filter(due_at__lt=now).count(),
                   "due_week": open_q.filter(due_at__gte=now, due_at__lt=now + timedelta(days=7)).count()},
        "items": [{"id": str(t.pk), "title": t.title, "priority": t.priority, "status": t.status, "due_at": t.due_at,
                   "overdue": bool(t.due_at and t.due_at < now), "path": t.link_path or f"/tasks?open={t.pk}"} for t in items],
    }


def approvals(ctx):
    from apps.workflows.models import ApprovalRequest
    from apps.workflows.selectors import inbox_for

    inbox = inbox_for(ctx)
    mine = ApprovalRequest.objects.filter(requested_by=ctx.user)
    week = timezone.now() - timedelta(days=7)
    return {
        "counts": {"waiting_on_me": len(inbox), "my_pending": mine.filter(status="pending").count(),
                   "approved_week": mine.filter(status="approved", decided_at__gte=week).count(),
                   "rejected_week": mine.filter(status="rejected", decided_at__gte=week).count()},
        "items": [{"id": str(r.pk), "reference": r.reference, "title": r.title, "amount": str(r.amount) if r.amount is not None else None,
                   "currency": r.currency, "requested_by": r.requested_by.full_name, "due_at": r.due_at, "created_at": r.created_at,
                   "path": f"/approvals/{r.pk}"} for r in inbox[:6]],
    }


def notifications(ctx):
    from .models import WorkNotification

    qs = WorkNotification.objects.filter(recipient=ctx.user)
    return {"unread": qs.filter(read_at__isnull=True).count(),
            "items": [{"id": str(n.pk), "type": n.type, "title": n.title, "body": n.body, "priority": n.priority,
                       "path": n.link_path, "created_at": n.created_at, "read": n.read_at is not None} for n in qs[:6]]}


def calendar(ctx):
    from .calendar import upcoming

    return {"items": upcoming(ctx, days=14)[:8]}


def security(ctx):
    acct = ctx.account
    from apps.access.models import OSSession

    live = OSSession.objects.filter(user=ctx.user, revoked_at__isnull=True, expires_at__gt=timezone.now()).count()
    return {"mfa_enabled": acct.mfa_enabled, "active_sessions": live, "last_login_at": acct.last_login_at,
            "recovery_codes_left": len(acct.recovery_codes or []), "mfa_blocked": len(ctx.mfa_blocked)}


# --- business widgets --------------------------------------------------------------
def business_snapshot(ctx):
    _org_wide(ctx, "analytics.business.view")
    from apps.orders.models import Order
    from apps.partners.models import Partner
    from apps.payments.models import Payment
    from apps.customers.models import CustomerProfile
    from apps.support.models import SupportTicket

    now = timezone.now()
    d30 = now - timedelta(days=30)
    d60 = now - timedelta(days=60)
    captured = Payment.objects.filter(status=Payment.Status.CAPTURED)
    rev30 = captured.filter(created_at__gte=d30).aggregate(s=Sum("amount"))["s"]
    rev_prev = captured.filter(created_at__gte=d60, created_at__lt=d30).aggregate(s=Sum("amount"))["s"]
    return {
        "period": "Last 30 days",
        "metrics": [
            {"key": "gmv", "label": "Payments captured", "value": _money(rev30), "previous": _money(rev_prev), "format": "money"},
            {"key": "orders", "label": "Orders", "value": Order.objects.filter(created_at__gte=d30).count(),
             "previous": Order.objects.filter(created_at__gte=d60, created_at__lt=d30).count(), "format": "number"},
            {"key": "partners", "label": "Active partners", "value": Partner.objects.filter(status=Partner.Status.ACTIVE).count(), "format": "number"},
            {"key": "customers", "label": "Customers", "value": CustomerProfile.objects.count(), "format": "number"},
            {"key": "tickets", "label": "Open support tickets",
             "value": SupportTicket.objects.exclude(status__in=["resolved", "closed"]).count(), "format": "number"},
        ],
        "note": "Payments captured is gross platform collection (GMV), not Click revenue. Click’s share depends on each "
                "partner’s commercial model and is reported by Finance once settlements are built.",
    }


def finance_overview(ctx):
    _org_wide(ctx, "finance.overview.view")
    from apps.payments.models import Payment

    now = timezone.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    p = Payment.objects
    agg = lambda qs: _money(qs.aggregate(s=Sum("amount"))["s"])  # noqa: E731
    return {
        "metrics": [
            {"key": "captured_today", "label": "Collected today", "value": agg(p.filter(status="captured", created_at__gte=today)), "format": "money"},
            {"key": "captured_7d", "label": "Collected · 7 days", "value": agg(p.filter(status="captured", created_at__gte=now - timedelta(days=7))), "format": "money"},
            {"key": "refunded_30d", "label": "Refunded · 30 days", "value": agg(p.filter(status="refunded", updated_at__gte=now - timedelta(days=30))), "format": "money"},
            {"key": "pending", "label": "Pending payments", "value": p.filter(status__in=["pending", "authorized"]).count(), "format": "number"},
            {"key": "failed_7d", "label": "Failed · 7 days", "value": p.filter(status="failed", created_at__gte=now - timedelta(days=7)).count(), "format": "number"},
        ],
        "note": "Receivables, payables and the ledger arrive with the Finance module.",
    }


def people_overview(ctx):
    from apps.people.models import Employee

    scope = ctx.scope("people.employee.view")
    qs = scope.filter(Employee.objects.all(), unit="org_unit", department="department", team="team", owner="user")
    by_status = dict(qs.values_list("status").annotate(n=Count("id")))
    return {
        "scope": scope.level,
        "metrics": [
            {"key": "active", "label": "Active employees", "value": by_status.get("active", 0), "format": "number"},
            {"key": "on_leave", "label": "On leave", "value": by_status.get("on_leave", 0), "format": "number"},
            {"key": "joining", "label": "Pre-joining", "value": by_status.get("pre_joining", 0), "format": "number"},
            {"key": "notice", "label": "Serving notice", "value": by_status.get("notice", 0), "format": "number"},
            {"key": "new_30d", "label": "Joined · 30 days",
             "value": qs.filter(joined_on__gte=(timezone.now() - timedelta(days=30)).date()).count(), "format": "number"},
        ],
        "note": "Attendance, leave and hiring figures arrive with the People & HR module.",
    }


def operations_overview(ctx):
    _org_wide(ctx, "operations.order.view")
    from apps.orders.models import Order
    from apps.support.models import SupportTicket

    now = timezone.now()
    active_states = ["placed", "confirmed", "preparing", "ready", "packed", "shipped", "out_for_delivery"]
    stale = Order.objects.filter(status__in=["placed", "confirmed"], created_at__lt=now - timedelta(minutes=45)).count()
    by_status = dict(Order.objects.filter(status__in=active_states).values_list("status").annotate(n=Count("id")))
    return {
        "metrics": [
            {"key": "active_orders", "label": "Active orders", "value": sum(by_status.values()), "format": "number"},
            {"key": "stale", "label": "Waiting > 45 min", "value": stale, "format": "number", "alert": stale > 0},
            {"key": "cancelled_today", "label": "Cancelled today",
             "value": Order.objects.filter(status="cancelled", updated_at__gte=now.replace(hour=0, minute=0, second=0)).count(), "format": "number"},
            {"key": "tickets_urgent", "label": "Urgent tickets open",
             "value": SupportTicket.objects.exclude(status__in=["resolved", "closed"]).filter(priority="urgent").count(), "format": "number"},
        ],
        "breakdown": [{"label": k.replace("_", " ").capitalize(), "value": v} for k, v in sorted(by_status.items())],
    }


def partner_pipeline(ctx):
    _org_wide(ctx, "partners.partner.view")
    from apps.partners.models import Partner

    by_status = dict(Partner.objects.values_list("status").annotate(n=Count("id")))
    order = ["profile_completed", "verification_pending", "verified", "active", "suspended", "rejected"]
    return {"stages": [{"key": s, "label": Partner.Status(s).label, "value": by_status.get(s, 0)} for s in order],
            "total": sum(by_status.values())}


def security_overview(ctx):
    _org_wide(ctx, "identity.user.view")
    from apps.access.models import OSAccount
    from apps.audit.models import AuditEvent

    accts = OSAccount.objects.filter(organization=ctx.organization)
    active = accts.filter(status="active")
    day = timezone.now() - timedelta(hours=24)
    return {
        "metrics": [
            {"key": "active", "label": "Active accounts", "value": active.count(), "format": "number"},
            {"key": "mfa", "label": "With MFA", "value": active.filter(mfa_enabled_at__isnull=False).count(), "format": "number"},
            {"key": "suspended", "label": "Suspended", "value": accts.filter(status="suspended").count(), "format": "number"},
            {"key": "locked", "label": "Locked now", "value": accts.filter(locked_until__gt=timezone.now()).count(), "format": "number"},
            {"key": "failed_24h", "label": "Failed sign-ins · 24h",
             "value": AuditEvent.objects.filter(organization=ctx.organization, action="auth.login", outcome="failure", created_at__gte=day).count(),
             "format": "number"},
        ],
    }


WIDGETS: dict[str, Widget] = {w.key: w for w in (
    Widget("my_work", "My work", "m", None, my_work, "Tasks assigned to you"),
    Widget("approvals", "Approvals", "m", None, approvals, "Waiting on you and your requests"),
    Widget("notifications", "Notifications", "m", None, notifications),
    Widget("calendar", "Coming up", "m", None, calendar, "Deadlines in the next two weeks"),
    Widget("security", "Account security", "s", None, security),
    Widget("business_snapshot", "Business snapshot", "l", "analytics.business.view", business_snapshot),
    Widget("finance_overview", "Finance", "l", "finance.overview.view", finance_overview),
    Widget("people_overview", "People", "m", "people.employee.view", people_overview),
    Widget("operations_overview", "Operations", "m", "operations.order.view", operations_overview),
    Widget("partner_pipeline", "Partner pipeline", "m", "partners.partner.view", partner_pipeline),
    Widget("security_overview", "Security & access", "m", "identity.user.view", security_overview),
)}

BASE_LAYOUT = ["approvals", "my_work", "calendar", "notifications"]


def available(ctx: AuthContext) -> list[str]:
    return [k for k, w in WIDGETS.items() if w.permission is None or ctx.has(w.permission)]


def layout_for(ctx: AuthContext) -> list[str]:
    allowed = set(available(ctx))
    order: list[str] = []
    for role in sorted({r.pk: r for r in ctx.roles}.values(), key=lambda r: (r.priority, r.name)):
        order += [k for k in (role.home_widgets or []) if k not in order]
    order += [k for k in BASE_LAYOUT if k not in order]
    if "security" not in order:
        order.append("security")
    prefs = ((ctx.account.preferences or {}).get("home") or {}) if ctx.account else {}
    custom = [k for k in prefs.get("order", []) if k in allowed]
    order = custom + [k for k in order if k not in custom]
    hidden = set(prefs.get("hidden", []))
    return [k for k in order if k in allowed and k not in hidden]


def render(ctx: AuthContext, keys: list[str]) -> list[dict]:
    out = []
    for key in keys:
        w = WIDGETS[key]
        item = {"key": key, "title": w.title, "size": w.size, "description": w.description, "data": None, "error": None}
        try:
            item["data"] = w.loader(ctx)
        except NotAtScope as e:
            item["error"] = {"code": "not_at_scope", "message": str(e)}
        except Exception:
            logger.exception("home.widget_failed", extra={"widget": key})
            item["error"] = {"code": "widget_failed", "message": "This section couldn’t load. Try again shortly."}
        out.append(item)
    return out
