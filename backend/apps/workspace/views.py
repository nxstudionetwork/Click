"""Business OS workspace API: context, profile, security, home, notifications, search, calendar, modules, AI."""

from django.conf import settings
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.access import registry, security
from apps.access.api import OSView
from apps.access.authz import holders_of
from apps.access.models import OSAccount, OSSession
from apps.access.serializers import SessionSerializer
from apps.access.sessions import revoke, revoke_all
from apps.audit.models import AuditEvent
from apps.audit.services import record
from apps.core.api.exceptions import DomainError

from . import ai, calendar as cal, search as search_mod, widgets
from .context import build_context, module_payload
from .models import WorkNotification
from .notify import notify, notify_many

LANGUAGES = {"en": "English", "hi": "हिन्दी", "te": "తెలుగు", "ta": "தமிழ்", "kn": "ಕನ್ನಡ"}


def _valid_tz(tz: str) -> bool:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        ZoneInfo(tz)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


class ContextView(OSView):
    def get(self, request):
        return Response(build_context(self.authz, request))


class ProfileView(OSView):
    def patch(self, request):
        account, user = self.authz.account, request.user
        before = {"full_name": user.full_name, "timezone": account.timezone, "language": account.language}
        name = request.data.get("full_name")
        if name is not None:
            name = " ".join(str(name).split())
            if len(name) < 2:
                raise DomainError("Enter your name.", code="validation_error", details={"fullName": ["Enter your name."]})
            user.full_name = name[:150]
            user.save(update_fields=["full_name", "updated_at"])
        tz = request.data.get("timezone")
        if tz is not None:
            if tz and not _valid_tz(tz):
                raise DomainError("Choose a valid time zone.", code="validation_error", details={"timezone": ["Unknown time zone."]})
            account.timezone = tz
        lang = request.data.get("language")
        if lang is not None:
            if lang not in LANGUAGES:
                raise DomainError("Choose a supported language.", code="validation_error", details={"language": ["Unsupported."]})
            account.language = lang
        account.save(update_fields=["timezone", "language", "updated_at"])
        record(request, "profile.update", category="data", module="identity", resource=account,
               old=before, new={"full_name": user.full_name, "timezone": account.timezone, "language": account.language})
        return Response(build_context(self.authz, request))


class PreferencesView(OSView):
    """PATCH {notifications: {muted: [...]}, home: {hidden: [...], order: [...]}, appearance: {...}}"""

    def patch(self, request):
        account = self.authz.account
        prefs = dict(account.preferences or {})
        if "notifications" in request.data:
            muted = [t for t in (request.data["notifications"] or {}).get("muted", [])
                     if t in WorkNotification.Type.values and t not in WorkNotification.ESSENTIAL]
            prefs["notifications"] = {"muted": muted}
        if "home" in request.data:
            home = request.data["home"] or {}
            keys = set(widgets.WIDGETS)
            prefs["home"] = {"hidden": [k for k in home.get("hidden", []) if k in keys], "order": [k for k in home.get("order", []) if k in keys]}
        if "appearance" in request.data:
            a = request.data["appearance"] or {}
            prefs["appearance"] = {"theme": a.get("theme") if a.get("theme") in {"light", "dark", "system"} else "system",
                                   "density": a.get("density") if a.get("density") in {"comfortable", "compact"} else "comfortable"}
        account.preferences = prefs
        account.save(update_fields=["preferences", "updated_at"])
        return Response(build_context(self.authz, request))


class AvatarView(OSView):
    parser_classes = [MultiPartParser]

    def post(self, request):
        from apps.users.images import encode_avatar

        account = self.authz.account
        content = encode_avatar(request.FILES.get("image"))
        if account.avatar:
            account.avatar.delete(save=False)
        account.avatar.save(content.name, content, save=True)
        return Response(build_context(self.authz, request), status=status.HTTP_201_CREATED)

    def delete(self, request):
        account = self.authz.account
        if account.avatar:
            account.avatar.delete(save=True)
        return Response(build_context(self.authz, request))


class OnboardingView(OSView):
    """First sign-in. People confirm what HR holds; they can't change their own department, designation, location or access."""

    def post(self, request):
        ctx, account, user = self.authz, self.authz.account, request.user
        name = " ".join(str(request.data.get("full_name", user.full_name)).split())
        if len(name) < 2:
            raise DomainError("Enter your name.", code="validation_error", details={"fullName": ["Enter your name."]})
        tz = request.data.get("timezone") or ctx.organization.timezone
        if not _valid_tz(tz):
            raise DomainError("Choose a valid time zone.", code="validation_error", details={"timezone": ["Unknown time zone."]})
        lang = request.data.get("language") or "en"
        if lang not in LANGUAGES:
            lang = "en"
        user.full_name = name[:150]
        user.save(update_fields=["full_name", "updated_at"])
        prefs = dict(account.preferences or {})
        muted = [t for t in ((request.data.get("notifications") or {}).get("muted", []))
                 if t in WorkNotification.Type.values and t not in WorkNotification.ESSENTIAL]
        prefs["notifications"] = {"muted": muted}
        account.preferences, account.timezone, account.language = prefs, tz, lang
        account.onboarding_completed_at = timezone.now()
        account.save(update_fields=["preferences", "timezone", "language", "onboarding_completed_at", "updated_at"])
        note = str(request.data.get("correction_note", "")).strip()[:500]
        if note and ctx.employee:
            emp = ctx.employee
            hr = holders_of("people.employee.edit", ctx.organization, unit=emp.org_unit_id, department=emp.department_id) \
                if emp.org_unit_id or emp.department_id else holders_of("people.employee.edit", ctx.organization)
            notify_many([u for u in hr if u.pk != user.pk], "workflow", f"Profile correction requested by {name}",
                        body=note, link=f"/people/{emp.pk}", module="people")
        record(request, "identity.onboarding.completed", category="data", module="identity", resource=account,
               metadata={"correction_requested": bool(note)})
        return Response(build_context(ctx, request))


class PasswordView(OSView):
    def post(self, request):
        user = request.user
        if not user.check_password(request.data.get("current_password") or ""):
            record(request, "security.password.change", category="security", outcome="failure")
            raise DomainError("Your current password is incorrect.", code="validation_error", details={"currentPassword": ["Incorrect."]})
        new = request.data.get("new_password") or ""
        try:
            password_validation.validate_password(new, user)
        except ValidationError as e:
            raise DomainError(" ".join(e.messages), code="validation_error", details={"newPassword": e.messages})
        user.set_password(new)
        user.save(update_fields=["password", "updated_at"])
        OSAccount.objects.filter(user=user).update(password_changed_at=timezone.now())
        ended = revoke_all(user, "password_changed", except_id=getattr(request, "os_session", None) and request.os_session.pk)
        record(request, "security.password.change", category="security", metadata={"other_sessions_ended": ended})
        notify(user, "security", "Your password was changed", body="Other devices were signed out.", link="/settings/security")
        return Response({"other_sessions_ended": ended})


class MfaSetupView(OSView):
    def post(self, request):
        account = self.authz.account
        if account.mfa_enabled:
            raise DomainError("Two-step verification is already on.", code="mfa_already_enabled", status_code=409)
        secret = security.new_totp_secret()
        account.mfa_pending_secret = security.encrypt(secret)
        account.save(update_fields=["mfa_pending_secret", "updated_at"])
        label = request.user.email or request.user.full_name or str(request.user.pk)
        return Response({"secret": secret, "otpauth_uri": security.otpauth_uri(secret, label)})


class MfaConfirmView(OSView):
    def post(self, request):
        account = self.authz.account
        secret = security.decrypt(account.mfa_pending_secret)
        counter = security.verify_totp(secret, str(request.data.get("code", "")))
        if not secret or counter is None:
            raise DomainError("That code didn’t match. Check your authenticator app’s time and try the newest code.", code="invalid_code")
        codes, hashes = security.new_recovery_codes()
        account.mfa_secret, account.mfa_pending_secret = account.mfa_pending_secret, ""
        account.mfa_enabled_at, account.mfa_last_counter, account.recovery_codes = timezone.now(), counter, hashes
        account.save()
        account.bump_access()
        record(request, "security.mfa.enabled", category="security", resource=account)
        notify(request.user, "security", "Two-step verification is on", link="/settings/security")
        return Response({"recovery_codes": codes})


class MfaDisableView(OSView):
    def post(self, request):
        account, user = self.authz.account, request.user
        if not account.mfa_enabled:
            raise DomainError("Two-step verification is already off.", code="mfa_not_enabled", status_code=409)
        if any(r.requires_mfa for r in self.authz.roles):
            raise DomainError("Your role requires two-step verification, so it can’t be turned off.", code="mfa_required_by_role", status_code=403)
        if not user.check_password(request.data.get("password") or ""):
            raise DomainError("Your password is incorrect.", code="validation_error", details={"password": ["Incorrect."]})
        if security.verify_totp(security.decrypt(account.mfa_secret), str(request.data.get("code", "")), last_counter=account.mfa_last_counter) is None:
            raise DomainError("That code didn’t work.", code="invalid_code")
        account.mfa_secret, account.mfa_enabled_at, account.recovery_codes = "", None, []
        account.save(update_fields=["mfa_secret", "mfa_enabled_at", "recovery_codes", "updated_at"])
        account.bump_access()
        record(request, "security.mfa.disabled", category="security", resource=account)
        notify(user, "security", "Two-step verification was turned off", link="/settings/security", priority="important")
        return Response(status=status.HTTP_204_NO_CONTENT)


class RecoveryCodesView(OSView):
    def post(self, request):
        account = self.authz.account
        if not account.mfa_enabled:
            raise DomainError("Turn on two-step verification first.", code="mfa_not_enabled", status_code=409)
        if not request.user.check_password(request.data.get("password") or ""):
            raise DomainError("Your password is incorrect.", code="validation_error", details={"password": ["Incorrect."]})
        codes, hashes = security.new_recovery_codes()
        account.recovery_codes = hashes
        account.save(update_fields=["recovery_codes", "updated_at"])
        record(request, "security.mfa.recovery_regenerated", category="security", resource=account)
        return Response({"recovery_codes": codes})


class SessionsView(OSView):
    def get(self, request):
        qs = OSSession.objects.filter(user=request.user, revoked_at__isnull=True, expires_at__gt=timezone.now())
        return Response({"results": SessionSerializer(qs, many=True, context={"request": request}).data})


class SessionDetailView(OSView):
    def delete(self, request, pk):
        s = OSSession.objects.filter(pk=pk, user=request.user).first()
        if s is None:
            raise DomainError("Session not found.", code="not_found", status_code=404)
        revoke(s, "signed_out_remotely")
        record(request, "auth.session.revoked", category="security", metadata={"session": str(s.pk), "device": s.device_label})
        return Response(status=status.HTTP_204_NO_CONTENT)


class LogoutAllView(OSView):
    def post(self, request):
        n = revoke_all(request.user, "logout_all")
        record(request, "auth.logout_all", category="security", metadata={"sessions": n})
        return Response({"sessions_ended": n})


class MyActivityView(OSView):
    """The signed-in person's own audit trail (sign-ins, security changes) — always visible to them."""

    def get(self, request):
        qs = AuditEvent.objects.filter(actor=request.user).order_by("-created_at")[:50]
        return Response({"results": [{"id": str(e.pk), "action": e.action, "category": e.category, "outcome": e.outcome, "ip": e.ip,
                                      "metadata": e.metadata, "created_at": e.created_at} for e in qs]})


# --- Notifications -----------------------------------------------------------------
def _notif(n: WorkNotification) -> dict:
    return {"id": str(n.pk), "type": n.type, "type_label": n.get_type_display(), "module": n.module, "title": n.title, "body": n.body,
            "path": n.link_path, "priority": n.priority, "read": n.read_at is not None, "created_at": n.created_at, "channels": n.channels,
            "archived": n.archived_at is not None, "essential": n.type in WorkNotification.ESSENTIAL}


NOTIFICATION_CATEGORIES = {
    "approvals": ["approval_request", "approval_result"], "tasks": ["task_assigned", "deadline", "workflow"],
    "security": ["security"], "business": ["business", "partner", "announcement"], "system": ["system"],
}


class NotificationsView(OSView):
    def get(self, request):
        base = WorkNotification.objects.filter(recipient=request.user)
        qs = base.filter(archived_at__isnull=True) if request.query_params.get("archived") != "true" else base.filter(archived_at__isnull=False)
        if request.query_params.get("unread") == "true":
            qs = qs.filter(read_at__isnull=True)
        if (cat := request.query_params.get("category")) in NOTIFICATION_CATEGORIES:
            qs = qs.filter(type__in=NOTIFICATION_CATEGORIES[cat])
        if t := request.query_params.get("type"):
            qs = qs.filter(type=t)
        from apps.core.api.pagination import DefaultPagination

        paginator = DefaultPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        resp = paginator.get_paginated_response([_notif(n) for n in page])
        unread = base.filter(read_at__isnull=True, archived_at__isnull=True)
        resp.data["unread"] = unread.count()
        resp.data["category_counts"] = {k: unread.filter(type__in=v).count() for k, v in NOTIFICATION_CATEGORIES.items()}
        resp.data["types"] = [{"value": v, "label": label, "essential": v in WorkNotification.ESSENTIAL} for v, label in WorkNotification.Type.choices]
        return resp


class NotificationSummaryView(OSView):
    def get(self, request):
        qs = WorkNotification.objects.filter(recipient=request.user, read_at__isnull=True, archived_at__isnull=True)
        return Response({"unread": qs.count(), "critical": qs.filter(priority="critical").count()})


class NotificationReadView(OSView):
    def post(self, request, pk=None):
        qs = WorkNotification.objects.filter(recipient=request.user, read_at__isnull=True)
        if pk is not None:
            qs = qs.filter(pk=pk)
        n = qs.update(read_at=timezone.now())
        return Response({"updated": n})


class NotificationActionView(OSView):
    """unread · archive (clear) · restore. Essential notifications that are still unread can't be cleared."""

    def post(self, request, pk, action):
        n = WorkNotification.objects.filter(recipient=request.user, pk=pk).first()
        if n is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        if action == "unread":
            n.read_at = None
        elif action == "archive":
            if n.type in WorkNotification.ESSENTIAL and n.read_at is None:
                raise DomainError("Read this notification before clearing it.", code="essential_unread", status_code=409)
            n.archived_at = timezone.now()
            n.read_at = n.read_at or timezone.now()
        elif action == "restore":
            n.archived_at = None
        else:
            raise DomainError("Not found.", code="not_found", status_code=404)
        n.save(update_fields=["read_at", "archived_at", "updated_at"])
        return Response(_notif(n))


class NotificationClearReadView(OSView):
    def post(self, request):
        n = WorkNotification.objects.filter(recipient=request.user, read_at__isnull=False, archived_at__isnull=True).update(archived_at=timezone.now())
        return Response({"cleared": n})


# --- Search / calendar / modules / AI --------------------------------------------------
class SearchView(OSView):
    throttle_scope = "search"

    def get(self, request):
        ctx = self.authz
        types = [t for t in request.query_params.get("type", "").split(",") if t]
        return Response({"query": request.query_params.get("q", ""), "groups": search_mod.search(ctx, request.query_params.get("q", ""), types=types or None,
                                                                                                  limit=20 if types else 6),
                         "types": search_mod.searchable_types(ctx)})


class CalendarView(OSView):
    def get(self, request):
        ctx = self.authz
        try:
            y, m = int(request.query_params.get("year", 0)), int(request.query_params.get("month", 0))
        except ValueError:
            y = m = 0
        if 2000 <= y <= 2100 and 1 <= m <= 12:
            items = cal.month(ctx, y, m)
        else:
            items = cal.upcoming(ctx, days=30)
        return Response({"results": sorted(items, key=lambda i: i["at"]), "sources": ["Tasks", "Approval deadlines"]})


class ModulesView(OSView):
    def get(self, request):
        ctx = self.authz
        return Response({"results": [module_payload(ctx, m) for m in registry.MODULES
                                     if (m.always_visible and ctx.kind != "partner") or ctx.sees_in_navigation(m)]})


class ModuleDetailView(OSView):
    def get(self, request, key):
        ctx = self.authz
        m = registry.MODULE_BY_KEY.get(key)
        if m is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        if not (m.always_visible or ctx.has_module(key)):
            raise DomainError("You don’t have access to this module.", code="permission_denied", status_code=403)
        return Response(module_payload(ctx, m))


class AIView(OSView):
    throttle_scope = "ai"

    def get(self, request):
        ctx = self.authz
        p = ai.provider()
        return Response({"available": bool(p) and ctx.has("ai.assistant.view"), "provider": p.name if p else None,
                         "tools": [{"key": t.key, "label": t.label} for t in ai.allowed_tools(ctx)] if p else []})

    def post(self, request):
        q = str(request.data.get("question", "")).strip()
        if not q:
            raise DomainError("Ask a question.", code="question_required")
        result = ai.ask(self.authz, q)
        record(request, "ai.query", category="data", module="ai", outcome="denied" if result.get("denied") else "success",
               metadata={"tool": result.get("tool"), "chars": len(q)})
        return Response(result)


# --- People directory (People & HR owns the record; this is the shared read view) -----------
class EmployeeView(OSView):
    permissions = {"GET": "people.directory.view"}

    def get(self, request, pk):
        from apps.people.models import Employee

        ctx = self.authz
        emp = ctx.scope("people.directory.view").filter(Employee.objects.select_related("designation", "department", "team", "org_unit", "manager", "user"),
                                                        unit="org_unit", department="department", team="team", owner="user").filter(pk=pk).first()
        if emp is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        data = {"id": str(emp.pk), "full_name": emp.full_name, "employee_id": emp.employee_id,
                "designation": emp.designation.name if emp.designation else None,
                "department": emp.department.name if emp.department else None, "team": emp.team.name if emp.team else None,
                "location": emp.org_unit.name if emp.org_unit else None, "work_email": emp.work_email,
                "manager": {"id": str(emp.manager.pk), "full_name": emp.manager.full_name} if emp.manager else None,
                "status": emp.status, "full_record": False}
        if ctx.can("people.employee.view", unit=emp.org_unit_id, department=emp.department_id, team=emp.team_id, owner=emp.user_id):
            data.update({"full_record": True, "employment_type": emp.employment_type, "joined_on": emp.joined_on,
                         "has_account": bool(emp.user_id and hasattr(emp.user, "os_account"))})
        return Response(data)


def health_checks() -> list[dict]:
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    checks = []
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
        checks.append({"key": "database", "label": "Database", "status": "ok", "detail": connection.vendor})
        ex = MigrationExecutor(connection)
        plan = ex.migration_plan(ex.loader.graph.leaf_nodes())
        checks.append({"key": "migrations", "label": "Migrations", "status": "ok" if not plan else "warning",
                       "detail": "Up to date" if not plan else f"{len(plan)} pending"})
    except Exception as e:  # pragma: no cover - reported, not raised
        checks.append({"key": "database", "label": "Database", "status": "error", "detail": type(e).__name__})
    conf = lambda v: "ok" if v else "not_configured"  # noqa: E731
    checks += [
        {"key": "api", "label": "Business OS API", "status": "ok", "detail": "Responding"},
        {"key": "sms", "label": "SMS provider", "status": conf(settings.CLICK_SMS_PROVIDER and settings.CLICK_SMS_PROVIDER != "console"),
         "detail": settings.CLICK_SMS_PROVIDER or "None"},
        {"key": "email", "label": "Email notifications", "status": conf("apps.workspace.notify.EmailChannel" in settings.CLICK_OS_NOTIFICATION_CHANNELS),
         "detail": settings.EMAIL_BACKEND.rsplit(".", 1)[-1]},
        {"key": "payments", "label": "Payment provider", "status": conf(settings.CLICK_PAYMENT_PROVIDER or settings.CLICK_PAYMENT_SANDBOX),
         "detail": settings.CLICK_PAYMENT_PROVIDER or ("Sandbox (test mode)" if settings.CLICK_PAYMENT_SANDBOX else "None")},
        {"key": "ai", "label": "Business AI", "status": conf(settings.CLICK_OS_AI_PROVIDER), "detail": settings.CLICK_OS_AI_PROVIDER.rsplit(".", 1)[-1] or "Off"},
        {"key": "mfa_policy", "label": "MFA for sensitive access", "status": "ok" if settings.CLICK_OS_SENSITIVE_REQUIRES_MFA else "warning",
         "detail": "Enforced" if settings.CLICK_OS_SENSITIVE_REQUIRES_MFA else "Not enforced (development)"},
        {"key": "debug", "label": "Debug mode", "status": "warning" if settings.DEBUG else "ok", "detail": "On" if settings.DEBUG else "Off"},
    ]
    return checks


class SystemHealthView(OSView):
    permissions = {"GET": "system.health.view"}

    def get(self, request):
        live = OSSession.objects.filter(revoked_at__isnull=True, expires_at__gt=timezone.now()).count()
        return Response({"checks": health_checks(), "active_sessions": live, "checked_at": timezone.now(),
                         "session_policy": {"idle_minutes": settings.CLICK_OS_IDLE_MINUTES, "max_hours": settings.CLICK_OS_SESSION_MAX_HOURS,
                                            "max_failed_logins": settings.CLICK_OS_MAX_FAILED_LOGINS, "lockout_minutes": settings.CLICK_OS_LOCKOUT_MINUTES}})


class IntegrationsView(OSView):
    permissions = {"GET": "integrations.integration.view"}

    def get(self, request):
        s = settings
        items = [
            ("payments", "Payment gateway", "Payments & Settlements", s.CLICK_PAYMENT_PROVIDER or ("sandbox" if s.CLICK_PAYMENT_SANDBOX else "")),
            ("sms", "SMS", "Communications", s.CLICK_SMS_PROVIDER if s.CLICK_SMS_PROVIDER != "console" else ""),
            ("email", "Email", "Communications", "django" if "apps.workspace.notify.EmailChannel" in s.CLICK_OS_NOTIFICATION_CHANNELS else ""),
            ("ai", "AI provider", "AI & Automation", s.CLICK_AI_PROVIDER.rsplit(".", 1)[-1] if s.CLICK_AI_PROVIDER else ""),
            ("speech", "Speech-to-text", "AI & Automation", s.CLICK_SPEECH_PROVIDER),
            ("vision", "Image recognition", "AI & Automation", s.CLICK_VISION_PROVIDER),
            ("sso", "Single sign-on (SSO)", "Identity", ""),
            ("maps", "Maps & geocoding", "Supply Chain", ""),
            ("banking", "Banking", "Finance", ""),
            ("accounting", "Accounting export", "Finance", ""),
            ("logistics", "Logistics partners", "Supply Chain", ""),
        ]
        return Response({"results": [{"key": k, "label": label, "area": area, "status": "connected" if v else "not_configured",
                                      "provider": v or None} for k, label, area, v in items],
                         "note": "Connectors are configured on the server (environment), never in the browser. Credentials are not shown here."})
