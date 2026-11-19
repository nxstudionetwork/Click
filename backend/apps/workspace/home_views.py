"""
Home / Command Center API.

    GET  os/home                          summary + context + layout (cheap); widgets load separately
    GET  os/home/widgets/<key>            one widget (?unit=&period=&start=&end=)
    PUT  os/home/layout                   {layout:[{key,size,period,pinned}], hidden:[...]}
    POST os/home/layout/reset
    POST os/home/views                    save current layout as a named view {name}
    POST os/home/views/<id>/activate      a saved view, a preset ("preset:executive") or "default"
    DELETE os/home/views/<id>
    PUT  os/home/context                  {unitId|null}
    PUT  os/home/pulse                    {metrics:[...]}
    PUT  os/home/quick-actions            {pins:[...]}
    POST os/home/quick-actions/<key>/used
    GET  os/alerts · POST os/alerts/<id>/<acknowledge|resolve|reopen|assign>
    GET/POST os/announcements · PATCH os/announcements/<id> · POST os/announcements/<id>/<acknowledge|dismiss>
    POST os/help/report
"""

import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.response import Response

from apps.access.api import OSView
from apps.access.authz import holders_of, load_context
from apps.audit.services import record
from apps.core.api.exceptions import DomainError
from apps.organization.models import OrgUnit
from apps.users.models import User

from . import alerts as alerts_mod
from . import periods, pulse, widgets
from .announcements import payload as ann_payload
from .announcements import _in_audience, visible_for
from .context import context_options, quick_actions
from .models import Alert, Announcement, AnnouncementAck
from .notify import notify, notify_many


def _prefs(account) -> dict:
    p = dict(account.preferences or {})
    p["home"] = dict(p.get("home") or {})
    return p


def _save_home(request, account, prefs: dict, action: str, metadata: dict | None = None):
    account.preferences = prefs
    account.save(update_fields=["preferences", "updated_at"])
    record(request, f"home.{action}", category="config", module="home", metadata=metadata or {})


def _unit_param(ctx, request):
    """The location the person chose (query or saved), validated against what they may view."""
    opts = context_options(ctx)
    uid = request.query_params.get("unit") or opts["selected"]
    if not uid:
        return None
    if uid not in {u["id"] for u in opts["units"]}:
        raise DomainError("You don’t have access to that location.", code="permission_denied", status_code=403)
    return OrgUnit.objects.filter(pk=uid).first()


def _summary(ctx) -> dict:
    from apps.workflows.models import Task
    from apps.workflows.selectors import inbox_for

    from .calendar import upcoming

    now = timezone.now()
    local = timezone.localtime(now)
    end_today = local.replace(hour=23, minute=59, second=59)
    t = Task.objects.filter(assignee=ctx.user, status__in=["open", "in_progress"]).exclude(snoozed_until__gt=now)
    inbox = inbox_for(ctx)
    vis = alerts_mod.visible(ctx)
    return {"date": local.date(), "weekday": local.strftime("%A"), "tasks_open": t.count(), "tasks_due_today": t.filter(due_at__gte=now, due_at__lte=end_today).count(),
            "tasks_overdue": t.filter(due_at__lt=now).count(), "approvals_waiting": len(inbox),
            "approvals_overdue": sum(1 for r in inbox if r.due_at and r.due_at < now),
            "alerts_important": sum(1 for a in vis if a.severity in ("critical", "high")),
            "alerts_critical": sum(1 for a in vis if a.severity == "critical"),
            "deadlines_week": len(upcoming(ctx, days=7, start=now))}


class HomeView(OSView):
    def get(self, request):
        ctx = self.authz
        alerts_mod.run(ctx.organization)
        unit = _unit_param(ctx, request)
        layout, active = widgets.layout_for(ctx)
        allowed = widgets.available(ctx)
        shown = {r["key"] for r in layout}
        prefs = widgets._home_prefs(ctx)  # noqa: SLF001
        ex = widgets.presets_for(ctx)
        return Response({
            "summary": _summary(ctx),
            "context": {**context_options(ctx), "unit": {"id": str(unit.pk), "name": unit.name, "type_label": unit.get_unit_type_display()} if unit else None},
            "layout": [widgets.meta(ctx, r["key"], r) for r in layout],
            "available": [widgets.meta(ctx, k) | {"visible": k in shown} for k in allowed],
            "views": {"active": active, "saved": [{"id": v["id"], "name": v["name"], "preset": False} for v in prefs.get("views", [])], "presets": ex},
            "can_executive": any(v["id"] == "preset:executive" for v in ex),
            "is_manager": ctx.is_manager,
            "periods": [{"key": k, "label": v} for k, v in periods.CHOICES.items()],
            "pulse": {"available": [{"key": k, "label": pulse.METRICS[k].label} for k in pulse.available(ctx)], "selected": pulse.chosen(ctx)},
            "generated_at": timezone.now(),
        })


class WidgetView(OSView):
    def get(self, request, key):
        ctx = self.authz
        if key not in widgets.WIDGETS or key not in widgets.available(ctx):
            raise DomainError("Not found.", code="not_found", status_code=404)
        w = widgets.WIDGETS[key]
        unit = _unit_param(ctx, request) if w.unit_aware else None
        per = None
        if w.periods:
            row = next((r for r in widgets.layout_for(ctx)[0] if r["key"] == key), None)
            per = periods.resolve(request.query_params.get("period") or (row or {}).get("period") or "last_30_days",
                                  start=request.query_params.get("start"), end=request.query_params.get("end"),
                                  tz_name=ctx.account.timezone if ctx.account else None)
        out = widgets.render_one(ctx, key, widgets.Params(unit=unit, period=per))
        if key in ("finance_snapshot", "security_overview"):  # sensitive summaries: viewing is audited
            record(request, "home.sensitive_widget.view", category="data", module="home", metadata={"widget": key})
        return Response(out)


class LayoutView(OSView):
    def put(self, request):
        ctx, acct = self.authz, self.authz.account
        allowed = set(widgets.available(ctx))
        rows, seen = [], set()
        for r in request.data.get("layout") or []:
            k = r.get("key")
            if k in allowed and k not in seen:
                seen.add(k)
                rows.append({"key": k, "size": r.get("size") if r.get("size") in widgets.SIZES else widgets.WIDGETS[k].size,
                             "period": r.get("period") if r.get("period") in periods.CHOICES else None, "pinned": bool(r.get("pinned"))})
        refused = [k for k in allowed if widgets.is_mandatory(ctx, k) and k not in seen]
        prefs = _prefs(acct)
        prefs["home"].update({"layout": rows, "hidden": [k for k in allowed if k not in seen and k not in refused]})
        active = prefs["home"].get("active_view")
        if active and not active.startswith("preset:"):  # editing while a saved view is active updates that view
            for v in prefs["home"].get("views", []):
                if v["id"] == active:
                    v["layout"] = rows
        else:
            prefs["home"]["active_view"] = None
        _save_home(request, acct, prefs, "layout.update", {"widgets": [r["key"] for r in rows]})
        return Response({"saved": True, "kept_mandatory": refused})

    patch = put  # same operation; the shared HTTP client sends PATCH


class LayoutResetView(OSView):
    def post(self, request):
        acct = self.authz.account
        prefs = _prefs(acct)
        for k in ("layout", "hidden", "active_view", "pulse"):
            prefs["home"].pop(k, None)
        _save_home(request, acct, prefs, "layout.reset")
        return Response({"reset": True})


class ViewsView(OSView):
    def post(self, request):
        ctx, acct = self.authz, self.authz.account
        name = str(request.data.get("name", "")).strip()[:60]
        if len(name) < 2:
            raise DomainError("Name the view.", code="validation_error", details={"name": ["Name the view."]})
        prefs = _prefs(acct)
        views = prefs["home"].get("views", [])
        if len(views) >= 12:
            raise DomainError("You can keep up to 12 saved views.", code="limit_reached")
        layout, _ = widgets.layout_for(ctx)
        v = {"id": secrets.token_hex(4), "name": name, "layout": layout}
        prefs["home"]["views"] = views + [v]
        prefs["home"]["active_view"] = v["id"]
        _save_home(request, acct, prefs, "view.create", {"name": name})
        return Response({"id": v["id"], "name": name}, status=status.HTTP_201_CREATED)


class ViewDetailView(OSView):
    def post(self, request, view_id):  # activate
        ctx, acct = self.authz, self.authz.account
        prefs = _prefs(acct)
        if view_id == "default":
            prefs["home"]["active_view"] = None
        elif view_id.startswith("preset:"):
            if not any(p["id"] == view_id for p in widgets.presets_for(ctx)):
                raise DomainError("That view isn’t available for your access.", code="permission_denied", status_code=403)
            prefs["home"]["active_view"] = view_id
        elif any(v["id"] == view_id for v in prefs["home"].get("views", [])):
            prefs["home"]["active_view"] = view_id
        else:
            raise DomainError("Not found.", code="not_found", status_code=404)
        _save_home(request, acct, prefs, "view.activate", {"view": view_id})
        return Response({"active": prefs["home"]["active_view"]})

    def delete(self, request, view_id):
        acct = self.authz.account
        prefs = _prefs(acct)
        before = prefs["home"].get("views", [])
        prefs["home"]["views"] = [v for v in before if v["id"] != view_id]
        if len(before) == len(prefs["home"]["views"]):
            raise DomainError("Not found.", code="not_found", status_code=404)
        if prefs["home"].get("active_view") == view_id:
            prefs["home"]["active_view"] = None
        _save_home(request, acct, prefs, "view.delete", {"view": view_id})
        return Response(status=status.HTTP_204_NO_CONTENT)


class ContextView(OSView):
    def put(self, request):
        ctx, acct = self.authz, self.authz.account
        uid = request.data.get("unit_id")
        if uid and uid not in {u["id"] for u in context_options(ctx)["units"]}:
            raise DomainError("You don’t have access to that location.", code="permission_denied", status_code=403)
        prefs = _prefs(acct)
        prefs["home"]["context_unit"] = uid or None
        _save_home(request, acct, prefs, "context.change", {"unit": uid})
        return Response({"selected": uid or None})

    patch = put  # same operation; the shared HTTP client sends PATCH


class PulseView(OSView):
    def put(self, request):
        ctx, acct = self.authz, self.authz.account
        avail = set(pulse.available(ctx))
        keys = [k for k in (request.data.get("metrics") or []) if k in avail][:12]
        prefs = _prefs(acct)
        prefs["home"]["pulse"] = keys
        _save_home(request, acct, prefs, "pulse.update", {"metrics": keys})
        return Response({"selected": pulse.chosen(ctx)})

    patch = put  # same operation; the shared HTTP client sends PATCH


class QuickActionsView(OSView):
    def put(self, request):
        ctx, acct = self.authz, self.authz.account
        allowed = {a["key"] for a in quick_actions(ctx)}
        pins = [k for k in (request.data.get("pins") or []) if k in allowed][:8]
        prefs = _prefs(acct)
        prefs["home"]["quick_pins"] = pins
        _save_home(request, acct, prefs, "quick_actions.pin", {"pins": pins})
        return Response({"pins": pins})

    patch = put  # same operation; the shared HTTP client sends PATCH


class QuickActionUsedView(OSView):
    def post(self, request, key):
        if key not in {a["key"] for a in quick_actions(self.authz)}:
            raise DomainError("Not found.", code="not_found", status_code=404)
        record(request, "home.quick_action", category="data", module="home", metadata={"action": key})
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- alerts ------------------------------------------------------------------------------------------------
class AlertsView(OSView):
    def get(self, request):
        ctx = self.authz
        alerts_mod.run(ctx.organization)
        rows = alerts_mod.visible(ctx)
        if (sev := request.query_params.get("severity")) in Alert.Severity.values:
            rows = [a for a in rows if a.severity == sev]
        if (cat := request.query_params.get("category")):
            rows = [a for a in rows if a.category == cat]
        if request.query_params.get("risk") == "true":
            rows = [a for a in rows if a.is_risk or a.severity == "critical"]
        return Response({"results": [alerts_mod.payload(a) for a in rows], "categories": sorted({a.category for a in rows})})


class AlertActionView(OSView):
    def post(self, request, pk, action):
        ctx = self.authz
        a = next(iter(alerts_mod.visible(ctx, Alert.objects.filter(pk=pk, organization=ctx.organization))), None)
        if a is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        before = {"status": a.status, "owner": str(a.owner_id) if a.owner_id else None}
        if action == "acknowledge":
            a.status = Alert.Status.ACKNOWLEDGED
            a.owner = a.owner or request.user
        elif action == "resolve":
            a.status, a.resolved_at = Alert.Status.RESOLVED, timezone.now()
        elif action == "reopen":
            a.status, a.resolved_at = Alert.Status.OPEN, None
        elif action == "assign":
            owner = User.objects.filter(pk=request.data.get("owner_id"), os_account__organization=ctx.organization, os_account__status="active").first()
            if owner is None:
                raise DomainError("Choose a colleague.", code="validation_error")
            if a.permission and not load_context(owner).has(a.permission):
                raise DomainError("That person can’t see this alert’s source data.", code="validation_error")
            a.owner = owner
            if owner.pk != request.user.pk:
                notify(owner, "business", f"Alert assigned to you: {a.title}", body=a.recommended_action, link=a.link_path or "/home", priority="important")
        else:
            raise DomainError("Not found.", code="not_found", status_code=404)
        a.save()
        record(request, f"alert.{action}", category="data", module="home", resource=a, old=before,
               new={"status": a.status, "owner": str(a.owner_id) if a.owner_id else None})
        return Response(alerts_mod.payload(a))


# --- announcements -------------------------------------------------------------------------------------------
def _clean_audience(ctx, raw) -> dict:
    raw = raw or {}
    out = {}
    if raw.get("units"):
        valid = set(str(x) for x in OrgUnit.objects.filter(organization=ctx.organization, pk__in=raw["units"]).values_list("pk", flat=True))
        out["units"] = [u for u in raw["units"] if str(u) in valid]
    if raw.get("departments"):
        from apps.organization.models import Department

        valid = set(str(x) for x in Department.objects.filter(organization=ctx.organization, pk__in=raw["departments"]).values_list("pk", flat=True))
        out["departments"] = [d for d in raw["departments"] if str(d) in valid]
    if raw.get("roles"):
        out["roles"] = [str(r) for r in raw["roles"]][:20]
    if raw.get("kinds"):
        out["kinds"] = [k for k in raw["kinds"] if k in ("employee", "partner", "external")]
    return out


class AnnouncementsView(OSView):
    permissions = {"POST": "communications.announcement.create"}

    def get(self, request):
        ctx = self.authz
        if request.query_params.get("manage") == "true":
            ctx.require("communications.announcement.view")
            rows = Announcement.objects.filter(organization=ctx.organization).select_related("created_by")[:200]
            return Response({"results": [ann_payload(a) | {"acks": a.acks.filter(acknowledged_at__isnull=False).count(),
                                                          "is_published": a.is_published} for a in rows]})
        return Response({"results": [ann_payload(a, ctx) for a in visible_for(ctx, include_dismissed=True)],
                         "can_create": ctx.has("communications.announcement.create"),
                         "categories": [{"key": k, "label": v} for k, v in Announcement.Category.choices]})

    def post(self, request):
        ctx, d = self.authz, request.data
        title, body = str(d.get("title", "")).strip(), str(d.get("body", "")).strip()
        if len(title) < 3 or len(body) < 3:
            raise DomainError("Add a title and message.", code="validation_error", details={"title": ["Required."], "body": ["Required."]})
        starts = parse_datetime(str(d.get("starts_at") or "")) or timezone.now()
        ends = parse_datetime(str(d.get("ends_at") or "")) if d.get("ends_at") else None
        if ends and ends <= starts:
            raise DomainError("The end must be after the start.", code="validation_error", details={"endsAt": ["Must be after the start."]})
        priority = d.get("priority") if d.get("priority") in Announcement.Priority.values else "normal"
        if priority == "critical":
            ctx.require("communications.announcement.approve")  # critical notices can't be dismissed, so they need more authority
        a = Announcement.objects.create(organization=ctx.organization, title=title[:160], body=body[:4000],
                                        category=d.get("category") if d.get("category") in Announcement.Category.values else "company",
                                        priority=priority, audience=_clean_audience(ctx, d.get("audience")), starts_at=starts, ends_at=ends,
                                        requires_ack=bool(d.get("requires_ack")), created_by=request.user)
        record(request, "communications.announcement.create", category="data", module="communications", resource=a,
               new={"title": a.title, "priority": a.priority, "audience": a.audience})
        if priority != "normal" and starts <= timezone.now() + timedelta(minutes=1):
            from apps.access.models import OSAccount

            users = [acc.user for acc in OSAccount.objects.filter(organization=ctx.organization, status="active").select_related("user", "user__employee")[:2000]]
            targets = [u for u in users if u.pk != request.user.pk and _in_audience(load_context(u), a)]
            notify_many(targets, "announcement", a.title, body=a.body[:300], link="/announcements", priority="important" if priority == "important" else "critical")
        return Response(ann_payload(a), status=status.HTTP_201_CREATED)


class AnnouncementDetailView(OSView):
    permissions = {"PATCH": "communications.announcement.edit"}

    def patch(self, request, pk):
        ctx = self.authz
        a = Announcement.objects.filter(pk=pk, organization=ctx.organization).first()
        if a is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        before = ann_payload(a)
        d = request.data
        for f in ("title", "body"):
            if f in d and str(d[f]).strip():
                setattr(a, f, str(d[f]).strip())
        if "ends_at" in d:
            a.ends_at = parse_datetime(str(d["ends_at"])) if d["ends_at"] else None
        if "is_published" in d:
            a.is_published = bool(d["is_published"])
        if "audience" in d:
            a.audience = _clean_audience(ctx, d["audience"])
        a.save()
        record(request, "communications.announcement.update", category="data", module="communications", resource=a, old=before, new=ann_payload(a))
        return Response(ann_payload(a))


class AnnouncementActionView(OSView):
    def post(self, request, pk, action):
        ctx = self.authz
        a = next((x for x in visible_for(ctx, include_dismissed=True) if str(x.pk) == str(pk)), None)
        if a is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        ack, _ = AnnouncementAck.objects.get_or_create(announcement=a, user=request.user)
        if action == "acknowledge":
            ack.acknowledged_at = ack.acknowledged_at or timezone.now()
            record(request, "communications.announcement.acknowledge", category="data", module="communications", resource=a)
        elif action == "dismiss":
            if a.priority == "critical":
                raise DomainError("Critical announcements stay on Home until they end.", code="not_dismissable", status_code=409)
            if a.requires_ack and not ack.acknowledged_at:
                raise DomainError("Acknowledge this announcement first.", code="ack_required", status_code=409)
            ack.dismissed = True
        else:
            raise DomainError("Not found.", code="not_found", status_code=404)
        ack.save()
        a._ack = ack  # noqa: SLF001
        return Response(ann_payload(a, ctx))


# --- help ------------------------------------------------------------------------------------------------------
class ReportProblemView(OSView):
    throttle_scope = "uploads"

    def post(self, request):
        ctx = self.authz
        summary = str(request.data.get("summary", "")).strip()
        if len(summary) < 5:
            raise DomainError("Describe the problem in a few words.", code="validation_error", details={"summary": ["Too short."]})
        details = str(request.data.get("details", ""))[:2000]
        page = str(request.data.get("page", ""))[:200]
        from apps.workflows.models import Task

        owners = holders_of("system.settings.configure", ctx.organization) or holders_of("system.health.view", ctx.organization)
        ref = f"BOS-{secrets.token_hex(3).upper()}"
        assignee = owners[0] if owners else None
        if assignee:
            Task.objects.create(organization=ctx.organization, title=f"[{ref}] {summary}"[:160], assignee=assignee, created_by=request.user,
                                description=f"Reported by {request.user.full_name} on {page or 'Business OS'}.\n\n{details}", priority="high",
                                module="system", source_type="help.report", source_id=ref)
            notify_many(owners[:10], "system", f"Problem reported: {summary}"[:160], body=f"{ref} · {request.user.full_name}", link="/tasks",
                        priority="important")
        record(request, "help.report_problem", category="data", module="system", metadata={"reference": ref, "page": page})
        return Response({"reference": ref, "routed": bool(assignee), "support_email": getattr(settings, "CLICK_OS_SUPPORT_EMAIL", "")},
                        status=status.HTTP_201_CREATED)
