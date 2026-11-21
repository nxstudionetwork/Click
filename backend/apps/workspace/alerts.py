"""
Alerts & Exceptions. Detectors look at live data and raise, refresh or auto-resolve alerts; modules register their
own detectors (People & HR registers document expiries, probation endings …).

    @detector("payments.failed", category="finance", permission="finance.overview.view")
    def failed_payments(org) -> list[Found]: ...

Visibility: personal alerts (subject_user) go only to that person; others need the detector's permission —
organization-wide when the data is platform-wide, or a scope covering the alert's unit when it has one.
Detectors run at most every RUN_EVERY seconds per organization (Home triggers them; `manage.py os_detect_alerts`
runs them from a scheduler).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Callable

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.utils import timezone

from .models import Alert

logger = logging.getLogger(__name__)
RUN_EVERY = 120


@dataclass
class Found:
    subject: str
    severity: str
    title: str
    detail: str = ""
    link: str = ""
    action: str = ""
    org_unit_id: object = None
    due_on: object = None
    risk: bool = False
    metric: Decimal | None = None
    subject_user_id: object = None


@dataclass
class Detector:
    key: str
    category: str
    source: str
    permission: str
    fn: Callable
    org_wide_only: bool = True
    notify_critical: bool = True
    extra: dict = field(default_factory=dict)


DETECTORS: dict[str, Detector] = {}


def detector(key: str, *, category: str, source: str, permission: str, org_wide_only: bool = True):
    def deco(fn):
        DETECTORS[key] = Detector(key, category, source, permission, fn, org_wide_only)
        return fn
    return deco


def run(org, *, force: bool = False) -> int:
    ck = f"os:alerts:last-run:{org.pk}"
    if not force and cache.get(ck):
        return 0
    cache.set(ck, timezone.now().isoformat(), RUN_EVERY)
    n = 0
    for d in DETECTORS.values():
        try:
            n += _apply(org, d, d.fn(org))
        except Exception:  # one detector failing never blocks the others (or Home)
            logger.exception("alerts.detector_failed", extra={"detector": d.key})
    cache.set(f"os:alerts:last-success:{org.pk}", timezone.now().isoformat(), 86400)
    return n


def _apply(org, d: Detector, found: list[Found]) -> int:
    now = timezone.now()
    keys = set()
    created = 0
    for f in found:
        key = f"{d.key}:{f.subject}"[:160]
        keys.add(key)
        fields = dict(detector=d.key, category=d.category, severity=f.severity, title=f.title[:200], detail=f.detail[:500],
                      source=d.source, link_path=f.link[:200], recommended_action=f.action[:240], permission=d.permission,
                      org_wide_only=d.org_wide_only, org_unit_id=f.org_unit_id, is_risk=f.risk, due_on=f.due_on, metric=f.metric,
                      subject_user_id=f.subject_user_id, last_seen_at=now)
        a = Alert.objects.filter(organization=org, key=key).exclude(status=Alert.Status.RESOLVED).first()
        if a:
            Alert.objects.filter(pk=a.pk).update(**fields)
            continue
        try:
            with transaction.atomic():
                a = Alert.objects.create(organization=org, key=key, **fields)
            created += 1
            if f.severity == "critical":
                _notify_new(org, d, a)
        except IntegrityError:
            pass
    # Conditions that cleared resolve their alerts automatically.
    Alert.objects.filter(organization=org, detector=d.key).exclude(status=Alert.Status.RESOLVED).exclude(key__in=keys) \
        .update(status=Alert.Status.RESOLVED, resolved_at=now)
    return created


def _notify_new(org, d: Detector, a: Alert) -> None:
    from apps.access.authz import holders_of

    from .notify import notify, notify_many

    if a.subject_user_id:
        notify(a.subject_user, "security" if a.category == "security" else "business", a.title, body=a.detail,
               link="/home", priority="critical", dedupe_key=f"alert:{a.pk}")
        return
    if not d.permission:
        return
    target = {"unit": a.org_unit_id} if a.org_unit_id and not a.org_wide_only else {}
    users = holders_of(d.permission, org, **target)
    notify_many(users[:50], "business" if a.category not in ("security", "technology") else "system", a.title, body=a.detail,
                link=a.link_path or "/home", priority="critical", dedupe_key=f"alert:{a.pk}")


def visible(ctx, qs=None):
    """Open/acknowledged alerts this person may see, most severe first."""
    qs = qs if qs is not None else Alert.objects.filter(organization=ctx.organization).exclude(status=Alert.Status.RESOLVED)
    out = []
    for a in qs.select_related("owner", "org_unit")[:500]:
        if a.subject_user_id:
            if a.subject_user_id == ctx.user.pk:
                out.append(a)
            continue
        if not a.permission:
            continue
        scope = ctx.scope(a.permission)
        if scope.is_empty:
            continue
        if a.org_wide_only and not scope.org_wide:
            continue
        if not a.org_wide_only and a.org_unit_id and not scope.covers(unit=a.org_unit_id):
            continue
        out.append(a)
    return sorted(out, key=lambda a: (Alert.SEVERITY_RANK.get(a.severity, 9), a.status != "open", -a.last_seen_at.timestamp()))


def payload(a: Alert) -> dict:
    return {"id": str(a.pk), "category": a.category, "severity": a.severity, "title": a.title, "detail": a.detail, "source": a.source,
            "path": a.link_path, "recommended_action": a.recommended_action, "status": a.status,
            "owner": {"id": str(a.owner_id), "full_name": a.owner.full_name} if a.owner_id else None,
            "first_seen_at": a.first_seen_at, "last_seen_at": a.last_seen_at, "due_on": a.due_on, "is_risk": a.is_risk,
            "personal": bool(a.subject_user_id), "location": a.org_unit.name if a.org_unit_id else None}


def personal(user, organization, *, key: str, severity: str, title: str, detail: str = "", action: str = "", link: str = "") -> None:
    """Raise an alert only one person sees (their own account security)."""
    k = f"personal:{key}:{user.pk}"[:160]
    try:
        with transaction.atomic():
            Alert.objects.update_or_create(
                organization=organization, key=k, status=Alert.Status.OPEN,
                defaults=dict(detector="personal", category="security", severity=severity, title=title, detail=detail, source="Your account",
                              link_path=link, recommended_action=action, subject_user=user, permission="", last_seen_at=timezone.now()))
    except IntegrityError:
        pass


# ---------------------------------------------------------------------------------------------------------------
# Core detectors (platform data). Each one is cheap: counts over indexed recent rows.
# ---------------------------------------------------------------------------------------------------------------
@detector("payments.failed", category="finance", source="Payments", permission="finance.overview.view")
def _failed_payments(org):
    from apps.payments.models import Payment

    since = timezone.now() - timedelta(hours=24)
    agg = Payment.objects.filter(status=Payment.Status.FAILED, created_at__gte=since).aggregate(n=Count("id"), s=Sum("amount"))
    n = agg["n"] or 0
    if not n:
        return []
    return [Found("24h", "critical" if n >= 20 else "high" if n >= 5 else "medium", f"{n} payment{'s' if n != 1 else ''} failed in the last 24 hours",
                  detail=f"Total ₹{(agg['s'] or 0):,.0f} not collected.", link="/m/payments",
                  action="Check the payment gateway status and contact affected customers if the failures continue.", metric=Decimal(n))]


@detector("orders.stale", category="operations", source="Orders", permission="operations.order.view")
def _stale_orders(org):
    from apps.orders.models import Order

    cutoff = timezone.now() - timedelta(minutes=45)
    n = Order.objects.filter(status__in=["placed", "confirmed"], created_at__lt=cutoff, created_at__gte=timezone.now() - timedelta(days=2)).count()
    if not n:
        return []
    return [Found("waiting", "high" if n >= 5 else "medium", f"{n} order{'s' if n != 1 else ''} waiting over 45 minutes",
                  detail="Placed or confirmed but not yet being prepared.", link="/m/operations",
                  action="Contact the stores involved; reassign or cancel orders that can’t be fulfilled.", metric=Decimal(n))]


@detector("partners.verification_backlog", category="partner", source="Partners", permission="partners.verification.view")
def _verification_backlog(org):
    from apps.partners.models import Partner

    cutoff = timezone.now() - timedelta(days=3)
    n = Partner.objects.filter(status=Partner.Status.VERIFICATION_PENDING, updated_at__lt=cutoff).count()
    if not n:
        return []
    return [Found("pending", "medium" if n < 10 else "high", f"{n} partner application{'s' if n != 1 else ''} waiting more than 3 days for verification",
                  link="/m/partners", action="Review the oldest applications first.", metric=Decimal(n))]


@detector("partners.documents_expiring", category="compliance", source="Partner documents", permission="partners.verification.view")
def _partner_docs(org):
    from apps.partners.models import PartnerDocument

    today = timezone.now().date()
    soon = PartnerDocument.objects.filter(status="verified", expires_on__gte=today, expires_on__lte=today + timedelta(days=30)).count()
    expired = PartnerDocument.objects.filter(status="verified", expires_on__lt=today, expires_on__gte=today - timedelta(days=90)).count()
    out = []
    if expired:
        out.append(Found("expired", "high", f"{expired} verified partner document{'s' if expired != 1 else ''} expired",
                         detail="Partners with an expired required document can’t operate.", link="/m/partners",
                         action="Ask the partners for renewed documents.", risk=True, metric=Decimal(expired)))
    if soon:
        out.append(Found("30d", "medium", f"{soon} partner document{'s' if soon != 1 else ''} expire within 30 days", link="/m/partners",
                         action="Send renewal reminders.", risk=True, due_on=today + timedelta(days=30), metric=Decimal(soon)))
    return out


@detector("support.urgent_open", category="support", source="Support", permission="cx.ticket.view")
def _urgent_tickets(org):
    from apps.support.models import SupportTicket

    cutoff = timezone.now() - timedelta(hours=4)
    n = SupportTicket.objects.filter(priority="urgent", created_at__lt=cutoff).exclude(status__in=["resolved", "closed"]).count()
    if not n:
        return []
    return [Found("urgent", "critical" if n >= 5 else "high", f"{n} urgent support request{'s' if n != 1 else ''} open over 4 hours",
                  link="/m/cx", action="Escalate to the support lead and reply to the customers.", metric=Decimal(n))]


@detector("security.failed_logins", category="security", source="Sign-in audit", permission="identity.user.view")
def _failed_logins(org):
    from apps.audit.models import AuditEvent

    since = timezone.now() - timedelta(hours=1)
    n = AuditEvent.objects.filter(organization=org, action="auth.login", outcome="failure", created_at__gte=since).count()
    locked = AuditEvent.objects.filter(organization=org, action="auth.account_locked", created_at__gte=timezone.now() - timedelta(hours=24)).count()
    out = []
    if n >= 10:
        out.append(Found("1h", "critical" if n >= 50 else "high", f"{n} failed Business OS sign-ins in the last hour",
                         detail="Could be password guessing.", link="/settings/audit", action="Check the audit trail for the accounts and networks involved."))
    if locked:
        out.append(Found("locked", "medium", f"{locked} account{'s' if locked != 1 else ''} locked after failed sign-ins today",
                         link="/settings/users?locked=true", action="Confirm with the people involved before unlocking."))
    return out


@detector("security.privileged_grants", category="security", source="Access audit", permission="access.role.view")
def _privileged_grants(org):
    from apps.audit.models import AuditEvent

    since = timezone.now() - timedelta(hours=24)
    rows = AuditEvent.objects.filter(organization=org, action="access.role.assigned", created_at__gte=since,
                                     new_value__role__in=["os-admin", "executive", "hr-manager", "finance-head"])
    n = rows.count()
    if not n:
        return []
    return [Found("24h", "medium", f"{n} privileged role assignment{'s' if n != 1 else ''} in the last 24 hours",
                  detail="Administrator, executive, HR or finance head roles were granted.", link="/settings/audit?category=access",
                  action="Confirm each grant was expected.")]


@detector("technology.health", category="technology", source="System health", permission="system.health.view")
def _health(org):
    from django.conf import settings
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    out = []
    ex = MigrationExecutor(connection)
    pending = ex.migration_plan(ex.loader.graph.leaf_nodes())
    if pending:
        out.append(Found("migrations", "high", f"{len(pending)} database migration{'s' if len(pending) != 1 else ''} not applied",
                         link="/settings/system", action="Run the migrations before the next deploy."))
    if not settings.DEBUG and not settings.CLICK_SMS_PROVIDER:
        out.append(Found("sms", "medium", "No SMS provider configured", detail="Phone sign-in and SMS notifications are unavailable.",
                         link="/settings/integrations", action="Configure CLICK_SMS_PROVIDER."))
    return out
