"""
Business OS sign-in.

    POST os/auth/identify     {identifier, accessType}         → {flowToken, methods}
    POST os/auth/password     {flowToken, password}             → authenticated | mfa_required
    POST os/auth/mfa          {mfaToken, code}                  → authenticated   (TOTP or a recovery code)
    POST os/auth/refresh      (cookie)                          → {access, user}
    POST os/auth/logout       (cookie)                          → 204
    GET/POST os/auth/invite   {token[, password]}               → invitation details / activate + sign in
    GET/POST os/auth/dev-personas                               → DEVELOPMENT ONLY (404 unless DEBUG)

No hidden admin password or backdoor: administrators are ordinary accounts whose roles grant administration
permissions. Unknown identifiers get the same answers as known ones until a password is checked.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.services import record
from apps.core.api.exceptions import DomainError
from apps.people.models import Employee
from apps.users.models import User
from apps.workspace.notify import notify

from . import registry, security
from .authz import load_context
from .models import AccountKind, OSAccount, OSSession
from .serializers import session_user_payload
from .sessions import clear_cookie, issue_refresh, revoke, set_cookie, start_session

logger = logging.getLogger(__name__)

ACCESS_TYPES = {"employee", "administrator", "partner", "other"}
FLOW_TTL, MFA_TTL, INVITE_TTL = 600, 300, 7 * 24 * 3600
_DUMMY_HASH = make_password("click-os-timing-equaliser")
GENERIC = "Those sign-in details didn’t work. Check them and try again."


class PublicAuthView(APIView):
    authentication_classes: list = []
    permission_classes = [permissions.AllowAny]
    throttle_scope = "os_auth"


def _require_client_header(request):
    if not request.headers.get("X-Click-Client"):
        raise DomainError("Missing client header.", code="client_header_required", status_code=403)


def resolve_identifier(identifier: str) -> User | None:
    ident = (identifier or "").strip()
    if not ident:
        return None
    if "@" in ident:
        return User.objects.filter(Q(email__iexact=ident) | Q(employee__work_email__iexact=ident)).first()
    emp = Employee.objects.select_related("user").filter(employee_id__iexact=ident, user__isnull=False).first()
    if emp:
        return emp.user
    digits = "".join(c for c in ident if c.isdigit() or c == "+")
    if len(digits) >= 8:
        return User.objects.filter(phone=digits, phone_verified=True).first()
    return None


def _check_access_type(account: OSAccount, access_type: str) -> None:
    wanted = {"employee": AccountKind.EMPLOYEE, "administrator": AccountKind.EMPLOYEE,
              "partner": AccountKind.PARTNER, "other": AccountKind.EXTERNAL}[access_type]
    labels = {"employee": "Employee", "administrator": "Administrator", "partner": "Partner / Business", "other": "authorized account"}
    ok = account.kind == wanted
    if ok and access_type == "administrator":
        ctx = load_context(account.user)
        ok = ctx.is_admin or any(registry.is_admin_code(c) for c in ctx.mfa_blocked)
    if not ok:
        raise DomainError(f"This account doesn’t have {labels[access_type]} access. Choose how you’re signing in and try again.",
                          code="access_type_mismatch", status_code=403)


def _fail(request, account: OSAccount | None, user: User | None, reason: str):
    if account is not None:
        account.failed_attempts += 1
        fields = ["failed_attempts", "updated_at"]
        if account.failed_attempts >= settings.CLICK_OS_MAX_FAILED_LOGINS:
            account.locked_until = timezone.now() + timedelta(minutes=settings.CLICK_OS_LOCKOUT_MINUTES)
            account.failed_attempts = 0
            fields.append("locked_until")
            notify(user, "security", "Your Click Business OS account was locked",
                   body=f"Too many failed sign-in attempts. It unlocks automatically in {settings.CLICK_OS_LOCKOUT_MINUTES} minutes.",
                   link="/settings/security", priority="critical")
            record(request, "auth.account_locked", category="security", actor=user, organization=account.organization, outcome="failure")
        account.save(update_fields=fields)
    record(request, "auth.login", category="auth", actor=user, organization=account.organization if account else None,
           outcome="failure", metadata={"reason": reason})


def _ensure_not_locked(account: OSAccount):
    if account.is_locked:
        mins = max(1, int((account.locked_until - timezone.now()).total_seconds() // 60) + 1)
        raise DomainError(f"Too many attempts. Try again in about {mins} minute{'s' if mins != 1 else ''}.", code="account_locked", status_code=423)


def _ensure_active(account: OSAccount):
    if account.status == OSAccount.Status.INVITED:
        raise DomainError("Finish setting up your account from your invitation link first.", code="account_invited", status_code=403)
    if account.status != OSAccount.Status.ACTIVE:
        raise DomainError("This account is suspended. Contact your Click administrator.", code="account_suspended", status_code=403)


class IdentifyView(PublicAuthView):
    def post(self, request):
        identifier = str(request.data.get("identifier", "")).strip()
        access_type = request.data.get("access_type", "employee")
        if not identifier:
            raise DomainError("Enter your work email or employee ID.", code="identifier_required")
        if access_type not in ACCESS_TYPES:
            raise DomainError("Choose how you’re accessing Click Business OS.", code="access_type_invalid")
        user = resolve_identifier(identifier)
        token = security.sign("flow", {"u": str(user.pk) if user else None, "t": access_type})
        # Same answer for unknown identifiers: methods come from configuration, not the account.
        return Response({"flow_token": token, "access_type": access_type, "methods": settings.CLICK_OS_AUTH_METHODS,
                         "sso": None})


class PasswordView(PublicAuthView):
    def post(self, request):
        flow = security.unsign("flow", request.data.get("flow_token"), FLOW_TTL)
        if not flow:
            raise DomainError("Your sign-in took too long. Start again.", code="flow_expired", status_code=400)
        password = request.data.get("password") or ""
        user = User.objects.filter(pk=flow["u"], is_active=True).first() if flow.get("u") else None
        account = OSAccount.objects.select_related("organization").filter(user=user).first() if user else None
        if account is None:
            make_password(password)  # equal timing for unknown identifiers
            _fail(request, None, user, "unknown_account")
            raise DomainError(GENERIC, code="invalid_credentials", status_code=401)
        _ensure_not_locked(account)
        if not user.check_password(password):
            _fail(request, account, user, "bad_password")
            raise DomainError(GENERIC, code="invalid_credentials", status_code=401)
        _ensure_active(account)
        _check_access_type(account, flow["t"])
        if account.mfa_enabled:
            return Response({"status": "mfa_required", "mfa_token": security.sign("mfa", {"u": str(user.pk), "t": flow["t"]}),
                             "methods": ["totp", "recovery_code"]})
        return start_session(request, user, account, mfa_verified=False, method="password")


class MfaView(PublicAuthView):
    def post(self, request):
        payload = security.unsign("mfa", request.data.get("mfa_token"), MFA_TTL)
        if not payload:
            raise DomainError("Your verification step expired. Sign in again.", code="flow_expired", status_code=400)
        account = OSAccount.objects.select_related("organization", "user").filter(user_id=payload["u"]).first()
        if account is None or not account.mfa_enabled:
            raise DomainError("Sign in again.", code="flow_expired", status_code=400)
        user = account.user
        _ensure_not_locked(account)
        _ensure_active(account)
        code = str(request.data.get("code", "")).strip()
        counter = security.verify_totp(security.decrypt(account.mfa_secret), code, last_counter=account.mfa_last_counter)
        method = "totp"
        if counter is not None:
            account.mfa_last_counter = counter
            account.save(update_fields=["mfa_last_counter", "updated_at"])
        else:
            h = security.hash_code(code)
            if code and h in (account.recovery_codes or []):
                account.recovery_codes = [c for c in account.recovery_codes if c != h]
                account.save(update_fields=["recovery_codes", "updated_at"])
                method = "recovery_code"
                notify(user, "security", "A recovery code was used to sign in",
                       body=f"{len(account.recovery_codes)} recovery codes left. Generate new ones in Settings → Security.",
                       link="/settings/security", priority="important")
            else:
                _fail(request, account, user, "bad_mfa_code")
                raise DomainError("That code didn’t work. Use the current code from your authenticator app.", code="invalid_code", status_code=401)
        return start_session(request, user, account, mfa_verified=True, method=f"password+{method}")


class RefreshView(PublicAuthView):
    throttle_scope = "auth_session"

    def post(self, request):
        _require_client_header(request)
        raw = request.COOKIES.get(settings.CLICK_OS_REFRESH_COOKIE["name"])

        def expired():
            r = Response({"error": {"code": "session_expired", "message": "Your session has ended. Please sign in again."}},
                         status=status.HTTP_401_UNAUTHORIZED)
            clear_cookie(r)
            return r

        if not raw:
            return Response({"error": {"code": "not_authenticated", "message": "Not signed in."}}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            old = RefreshToken(raw)
            session = OSSession.objects.select_related("user").get(pk=old["os_sid"], user_id=old["user_id"])
        except (TokenError, KeyError, OSSession.DoesNotExist, ValueError, ValidationError):
            return expired()
        account = OSAccount.objects.filter(user=session.user).first()
        if not session.is_live or not session.user.is_active or account is None or account.status != OSAccount.Status.ACTIVE:
            revoke(session, "refresh_denied")
            return expired()
        try:
            old.blacklist()
        except TokenError:
            return expired()
        refresh = issue_refresh(session.user, session)
        response = Response({"access": str(refresh.access_token), "user": session_user_payload(session.user)})
        set_cookie(response, refresh, session)
        return response


class LogoutView(PublicAuthView):
    throttle_scope = "auth_session"

    def post(self, request):
        _require_client_header(request)
        raw = request.COOKIES.get(settings.CLICK_OS_REFRESH_COOKIE["name"])
        if raw:
            try:
                tok = RefreshToken(raw, verify=False)
                session = OSSession.objects.filter(pk=tok.get("os_sid")).select_related("user").first()
                if session:
                    request.os_session = session
                    revoke(session, "logout")
                    record(request, "auth.logout", category="auth", actor=session.user)
            except (TokenError, ValueError, ValidationError):
                pass
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_cookie(response)
        return response


# --- invitations ---------------------------------------------------------------
def invite_token(account: OSAccount) -> str:
    return security.sign("invite", {"a": str(account.pk), "v": account.invited_at.isoformat() if account.invited_at else ""})


def _invited_account(token: str) -> OSAccount:
    data = security.unsign("invite", token, INVITE_TTL)
    account = OSAccount.objects.select_related("user", "organization").filter(pk=data["a"]).first() if data else None
    if (account is None or account.status != OSAccount.Status.INVITED
            or (account.invited_at.isoformat() if account.invited_at else "") != data.get("v")):
        raise DomainError("This invitation link is invalid or has expired. Ask your administrator for a new one.",
                          code="invite_invalid", status_code=400)
    return account


class InviteView(PublicAuthView):
    def get(self, request):
        account = _invited_account(request.query_params.get("token", ""))
        return Response({"full_name": account.user.full_name, "email": account.user.email,
                         "organization": account.organization.name, "kind": account.kind})

    def post(self, request):
        account = _invited_account(request.data.get("token", ""))
        user = account.user
        password = request.data.get("password") or ""
        try:
            password_validation.validate_password(password, user)
        except ValidationError as e:
            raise DomainError(" ".join(e.messages), code="weak_password")
        user.set_password(password)
        user.save(update_fields=["password", "updated_at"])
        account.status = OSAccount.Status.ACTIVE
        account.password_changed_at = timezone.now()
        account.save(update_fields=["status", "password_changed_at", "updated_at"])
        record(request, "identity.invite.accepted", category="security", actor=user, organization=account.organization, resource=account)
        return start_session(request, user, account, mfa_verified=False, method="invite")


# --- development only ----------------------------------------------------------
class DevPersonasView(PublicAuthView):
    """DEVELOPMENT ONLY: seeded personas (`python manage.py seed_os_dev`). 404 unless DEBUG and CLICK_OS_DEV_LOGIN."""

    throttle_scope = "auth_session"

    def _guard(self):
        if not (settings.DEBUG and settings.CLICK_OS_DEV_LOGIN):
            raise DomainError("Not found.", code="not_found", status_code=404)

    def _personas(self):
        return OSAccount.objects.select_related("user").filter(preferences__dev_persona__isnull=False,
                                                                status=OSAccount.Status.ACTIVE).order_by("created_at")

    def get(self, request):
        self._guard()
        return Response({"results": [{"user_id": str(a.user_id), "full_name": a.user.full_name, "email": a.user.email,
                                      "persona": a.preferences.get("dev_persona"), "kind": a.kind} for a in self._personas()]})

    def post(self, request):
        self._guard()
        account = self._personas().filter(user_id=request.data.get("user_id")).first()
        if account is None:
            raise DomainError("Run `python manage.py seed_os_dev` first.", code="dev_persona_missing", status_code=409)
        logger.warning("auth.os_dev_login", extra={"user_id": str(account.user_id)})
        return start_session(request, account.user, account, mfa_verified=False, method="dev_persona")
