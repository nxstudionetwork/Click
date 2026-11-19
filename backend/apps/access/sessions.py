"""
Business OS sessions. Separate refresh cookie (`click_os_refresh`, path /api/v1/os/auth/) from the customer/partner
apps, idle timeout (refresh lifetime) plus an absolute maximum, and a server-side session row the access token
points to (`os_sid`) so revocation is immediate.
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.services import client_ip, record

from .models import OSAccount, OSSession


def _device_label(ua: str) -> str:
    ua_l = ua.lower()
    browser = next((b for k, b in (("edg/", "Edge"), ("chrome/", "Chrome"), ("firefox/", "Firefox"), ("safari/", "Safari")) if k in ua_l), "Browser")
    os_name = next((o for k, o in (("windows", "Windows"), ("android", "Android"), ("iphone", "iPhone"), ("ipad", "iPad"),
                                   ("mac os", "macOS"), ("linux", "Linux")) if k in ua_l), "Unknown device")
    return f"{browser} on {os_name}"


def issue_refresh(user, session: OSSession) -> RefreshToken:
    now = timezone.now()
    lifetime = min(timedelta(minutes=settings.CLICK_OS_IDLE_MINUTES), session.expires_at - now)
    refresh = RefreshToken.for_user(user)
    refresh["os_sid"] = str(session.pk)
    refresh.set_exp(lifetime=max(lifetime, timedelta(seconds=1)))
    # OutstandingToken was written with the default expiry; keep it in step for blacklist cleanup.
    OutstandingToken.objects.filter(jti=refresh["jti"]).update(expires_at=now + lifetime)
    session.refresh_jti = refresh["jti"]
    session.last_seen_at = now
    session.save(update_fields=["refresh_jti", "last_seen_at", "updated_at"])
    return refresh


def set_cookie(response: Response, refresh: RefreshToken, session: OSSession) -> None:
    cfg = settings.CLICK_OS_REFRESH_COOKIE
    response.set_cookie(cfg["name"], str(refresh), max_age=int((session.expires_at - timezone.now()).total_seconds()),
                        httponly=True, secure=cfg["secure"], samesite=cfg["samesite"], path=cfg["path"], domain=cfg["domain"])


def clear_cookie(response: Response) -> None:
    cfg = settings.CLICK_OS_REFRESH_COOKIE
    response.delete_cookie(cfg["name"], path=cfg["path"], domain=cfg["domain"], samesite=cfg["samesite"])


def blacklist_jti(jti: str) -> None:
    tok = OutstandingToken.objects.filter(jti=jti).first()
    if tok:
        BlacklistedToken.objects.get_or_create(token=tok)


def revoke(session: OSSession, reason: str) -> None:
    if session.revoked_at is None:
        session.revoked_at = timezone.now()
        session.revoke_reason = reason
        session.save(update_fields=["revoked_at", "revoke_reason", "updated_at"])
    if session.refresh_jti:
        blacklist_jti(session.refresh_jti)


def revoke_all(user, reason: str, *, except_id=None) -> int:
    n = 0
    for s in OSSession.objects.filter(user=user, revoked_at__isnull=True).exclude(pk=except_id):
        revoke(s, reason)
        n += 1
    return n


def start_session(request, user, account: OSAccount, *, mfa_verified: bool, method: str) -> Response:
    from apps.workspace.notify import notify

    from .serializers import session_user_payload

    now = timezone.now()
    ua = request.META.get("HTTP_USER_AGENT", "")[:300]
    ip = client_ip(request)
    known_device = OSSession.objects.filter(user=user, user_agent=ua).exists()
    had_sessions = OSSession.objects.filter(user=user).exists()
    session = OSSession.objects.create(
        user=user, user_agent=ua, ip=ip, device_label=_device_label(ua), mfa_verified=mfa_verified,
        expires_at=now + timedelta(hours=settings.CLICK_OS_SESSION_MAX_HOURS),
    )
    refresh = issue_refresh(user, session)
    OSAccount.objects.filter(pk=account.pk).update(last_login_at=now, last_login_ip=ip, failed_attempts=0, locked_until=None)
    request.os_session = session
    record(request, "auth.login", category="auth", actor=user, organization=account.organization, resource=account,
           resource_label=str(user), metadata={"method": method, "mfa": mfa_verified, "device": session.device_label})
    if had_sessions and not known_device:  # suspicious-login signal: a device this account never used
        notify(user, "security", "New sign-in to Click Business OS",
               body=f"{session.device_label} · {ip or 'unknown network'}. If this wasn’t you, sign out of all devices and change your password.",
               link="/settings/security", priority="important")
        record(request, "auth.login.new_device", category="security", actor=user, organization=account.organization,
               metadata={"device": session.device_label})
    response = Response({"status": "authenticated", "access": str(refresh.access_token), "user": session_user_payload(user),
                         "session": {"id": str(session.pk), "expiresAt": session.expires_at}}, status=status.HTTP_200_OK)
    set_cookie(response, refresh, session)
    return response
