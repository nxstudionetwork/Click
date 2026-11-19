"""
Business Pulse metrics. Each metric declares who may see it, how to compute it for a period (value, previous value,
trend series) and where it drills down to. Roles choose which metrics their Home shows (Role.home_config.pulse);
people can override that; permissions always win.

Money is never blended: "Gross transaction value" is what customers paid through the platform (GMV). Click revenue,
commission, partner earnings and platform fees are separate metrics, reported as unavailable until the Finance and
settlement modules record them per commercial model.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate, TruncMonth

from apps.access.authz import AuthContext

from .periods import Period


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    permissions: tuple[str, ...]  # any one of these
    compute: Callable  # (ctx, period, unit) -> dict(value, previous, series, note?)
    fmt: str = "number"  # number | money | percent
    drill: str = ""
    source: str = ""
    org_wide: bool = True  # platform-wide data needs an organization-wide grant
    unit_aware: bool = False  # can be narrowed to the selected location
    point_in_time: bool = False  # "now" values: no period comparison
    good_when: str = "up"  # up | down (for colouring)
    description: str = ""


def _series(qs, field: str, period: Period, *, agg="count", value_field: str = "amount"):
    trunc = TruncMonth if period.bucket == "month" else TruncDate
    rows = qs.filter(**{f"{field}__gte": period.start, f"{field}__lt": period.end}).annotate(b=trunc(field)).values("b")
    rows = rows.annotate(v=Count("id") if agg == "count" else Sum(value_field)).order_by("b")
    return [{"t": r["b"].isoformat() if r["b"] else None, "v": str(r["v"] or 0)} for r in rows]


def _count(qs, field, period: Period):
    cur = qs.filter(**{f"{field}__gte": period.start, f"{field}__lt": period.end}).count()
    prev = qs.filter(**{f"{field}__gte": period.prev_start, f"{field}__lt": period.prev_end}).count()
    return {"value": cur, "previous": prev, "series": _series(qs, field, period)}


def _sum(qs, field, period: Period, value_field="amount"):
    cur = qs.filter(**{f"{field}__gte": period.start, f"{field}__lt": period.end}).aggregate(s=Sum(value_field))["s"] or Decimal("0")
    prev = qs.filter(**{f"{field}__gte": period.prev_start, f"{field}__lt": period.prev_end}).aggregate(s=Sum(value_field))["s"] or Decimal("0")
    return {"value": str(cur.quantize(Decimal("0.01"))), "previous": str(prev.quantize(Decimal("0.01"))),
            "series": _series(qs, field, period, agg="sum", value_field=value_field)}


# --- computations -------------------------------------------------------------------------------------------
def gmv(ctx, p, unit):
    from apps.payments.models import Payment

    return _sum(Payment.objects.filter(status=Payment.Status.CAPTURED), "created_at", p)


def orders(ctx, p, unit):
    from apps.orders.models import Order

    return _count(Order.objects.exclude(status="awaiting_payment"), "created_at", p)


def bookings(ctx, p, unit):
    from apps.bookings.models import Booking
    from apps.experiences.models import ExperienceBooking
    from apps.hotels.models import HotelBooking
    from apps.professionals.models import ServiceBooking
    from apps.travel.models import TravelBooking

    parts = [_count(m.objects.all(), "created_at", p) for m in (Booking, HotelBooking, TravelBooking, ExperienceBooking, ServiceBooking)]
    series: dict = {}
    for part in parts:
        for pt in part["series"]:
            series[pt["t"]] = series.get(pt["t"], 0) + int(pt["v"])
    return {"value": sum(x["value"] for x in parts), "previous": sum(x["previous"] for x in parts),
            "series": [{"t": k, "v": str(v)} for k, v in sorted(series.items(), key=lambda kv: kv[0] or "")],
            "note": "Showtime, hotels, travel, experiences and home services."}


def rides(ctx, p, unit):
    from apps.rides.models import Ride

    return _count(Ride.objects.all(), "created_at", p)


def new_customers(ctx, p, unit):
    from apps.customers.models import CustomerProfile

    return _count(CustomerProfile.objects.all(), "created_at", p)


def active_partners(ctx, p, unit):
    from apps.partners.models import Partner

    return {"value": Partner.objects.filter(status=Partner.Status.ACTIVE).count(), "previous": None, "series": []}


def partner_applications(ctx, p, unit):
    from apps.partners.models import Partner

    return _count(Partner.objects.exclude(status=Partner.Status.DRAFT), "created_at", p)


def failed_payments(ctx, p, unit):
    from apps.payments.models import Payment

    return _count(Payment.objects.filter(status=Payment.Status.FAILED), "created_at", p)


def refunds(ctx, p, unit):
    from apps.payments.models import Payment

    return _sum(Payment.objects.filter(status=Payment.Status.REFUNDED), "updated_at", p)


def open_tickets(ctx, p, unit):
    from apps.support.models import SupportTicket

    base = SupportTicket.objects.all()
    new = _count(base, "created_at", p)
    return {**new, "value": base.exclude(status__in=["resolved", "closed"]).count(), "previous": None,
            "note": f"{new['value']} new in the period."}


def operational_issues(ctx, p, unit):
    from datetime import timedelta

    from django.utils import timezone

    from apps.orders.models import Order

    n = Order.objects.filter(status__in=["placed", "confirmed"], created_at__lt=timezone.now() - timedelta(minutes=45),
                             created_at__gte=timezone.now() - timedelta(days=2)).count()
    return {"value": n, "previous": None, "series": [], "note": "Orders waiting over 45 minutes right now."}


def my_approvals(ctx, p, unit):
    from apps.workflows.selectors import inbox_for

    return {"value": len(inbox_for(ctx)), "previous": None, "series": []}


def expenses(ctx, p, unit):
    from apps.workflows.models import ApprovalRequest

    scope = ctx.scope("finance.expense.view")
    qs = ApprovalRequest.objects.filter(organization=ctx.organization, policy__key="finance.expense").exclude(status="cancelled")
    qs = qs.filter(scope.q(unit="org_unit", department="department", owner="requested_by", organization=None))
    if unit is not None:
        qs = qs.filter(org_unit__path__startswith=unit.path)
    out = _sum(qs, "created_at", p)
    out["note"] = "Expense claims raised in Business OS (approved and pending)."
    return out


def headcount(ctx, p, unit):
    from apps.people.models import Employee

    scope = ctx.scope("people.employee.view")
    qs = Employee.objects.filter(organization=ctx.organization).filter(
        scope.q(unit="org_unit", department="department", team="team", owner="user", employee="pk", organization=None))
    if unit is not None:
        qs = qs.filter(org_unit__path__startswith=unit.path)
    active = qs.filter(status__in=["active", "probation", "confirmed", "on_leave", "notice"]).count()
    joiners = qs.filter(joined_on__gte=p.start.date(), joined_on__lt=p.end.date()).count()
    return {"value": active, "previous": None, "series": [], "note": f"{joiners} joined in the period."}


METRICS: dict[str, Metric] = {m.key: m for m in (
    Metric("gmv", "Gross transaction value", ("analytics.business.view", "finance.overview.view"), gmv, "money", "/finance/platform", "Payments",
           description="What customers paid through Click (GMV). Not Click revenue."),
    Metric("orders", "Orders", ("analytics.business.view", "operations.order.view"), orders, drill="/m/operations", source="Orders"),
    Metric("bookings", "Bookings", ("analytics.business.view", "services.booking.view"), bookings, drill="/m/services", source="Bookings"),
    Metric("rides", "Rides", ("analytics.business.view", "operations.order.view"), rides, drill="/m/operations", source="Rides"),
    Metric("customers", "New customers", ("analytics.business.view", "sales.customer.view"), new_customers, drill="/m/sales", source="Customers"),
    Metric("partners", "Active partners", ("analytics.business.view", "partners.partner.view"), active_partners, drill="/m/partners",
           source="Partners", point_in_time=True),
    Metric("partner_apps", "Partner applications", ("partners.partner.view",), partner_applications, drill="/m/partners", source="Partners"),
    Metric("failed_payments", "Failed payments", ("finance.overview.view", "payments.transaction.view"), failed_payments,
           drill="/m/payments", source="Payments", good_when="down"),
    Metric("refunds", "Refunds", ("finance.overview.view", "payments.refund.view"), refunds, "money", "/m/payments", "Payments", good_when="down"),
    Metric("open_tickets", "Open support requests", ("cx.ticket.view",), open_tickets, drill="/m/cx", source="Support", point_in_time=True,
           good_when="down"),
    Metric("operational_issues", "Operational issues", ("operations.order.view",), operational_issues, drill="/m/operations",
           source="Orders", point_in_time=True, good_when="down"),
    Metric("approvals", "Waiting for my approval", (), my_approvals, drill="/approvals", source="Approvals", org_wide=False, point_in_time=True,
           good_when="down"),
    Metric("expenses", "Expense claims", ("finance.expense.view",), expenses, "money", "/approvals?box=all", "Approvals",
           org_wide=False, unit_aware=True),
    Metric("headcount", "Active employees", ("people.employee.view",), headcount, drill="/people/directory", source="People & HR",
           org_wide=False, unit_aware=True, point_in_time=True),
)}

DEFAULT_ORDER = ["gmv", "orders", "bookings", "customers", "partners", "open_tickets", "operational_issues", "approvals", "expenses",
                 "headcount", "failed_payments", "refunds", "rides", "partner_apps"]


def allowed(ctx: AuthContext, m: Metric) -> bool:
    if not m.permissions:
        return True
    for code in m.permissions:
        s = ctx.scope(code)
        if not s.is_empty and (s.org_wide or not m.org_wide):
            return True
    return False


def available(ctx: AuthContext) -> list[str]:
    return [k for k in DEFAULT_ORDER if allowed(ctx, METRICS[k])]


def chosen(ctx: AuthContext) -> list[str]:
    avail = available(ctx)
    prefs = ((ctx.account.preferences or {}).get("home") or {}).get("pulse") if ctx.account else None
    if prefs:
        picked = [k for k in prefs if k in avail]
        if picked:
            return picked
    order: list[str] = []
    for role in sorted({r.pk: r for r in ctx.roles}.values(), key=lambda r: (r.priority, r.name)):
        order += [k for k in ((role.home_config or {}).get("pulse") or []) if k not in order]
    order = [k for k in order if k in avail] or avail
    return order[:8]


def compute(ctx: AuthContext, keys: list[str], period: Period, unit=None) -> list[dict]:
    out = []
    for k in keys:
        m = METRICS[k]
        if not allowed(ctx, m):
            continue
        try:
            r = m.compute(ctx, period, unit if m.unit_aware else None)
            err = None
        except Exception:  # one metric failing doesn't blank the pulse
            import logging

            logging.getLogger(__name__).exception("pulse.metric_failed", extra={"metric": k})
            r, err = {"value": None, "previous": None, "series": []}, "Couldn’t load this figure."
        prev = r.get("previous")
        delta = None
        if prev not in (None, "", 0, "0", "0.00") and r.get("value") is not None and not m.point_in_time:
            try:
                delta = round((float(r["value"]) - float(prev)) / float(prev) * 100, 1)
            except (ZeroDivisionError, ValueError):
                delta = None
        out.append({"key": k, "label": m.label, "format": m.fmt, "value": r.get("value"), "previous": prev if not m.point_in_time else None,
                    "delta_pct": delta, "series": r.get("series", []), "drill": m.drill, "source": m.source, "note": r.get("note", ""),
                    "description": m.description, "point_in_time": m.point_in_time, "good_when": m.good_when, "error": err,
                    "location_applied": bool(unit is not None and m.unit_aware), "platform_wide": m.org_wide})
    return out
