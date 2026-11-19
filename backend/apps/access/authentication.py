"""
DRF authentication for /api/v1/os/*.

- OSJWTAuthentication: a normal Click access token is NOT enough. The token must carry `os_sid`, the session must
  be live (not revoked, not past its absolute expiry) and the account active. Checked on every request, so
  "log out all devices", suspension and revocation take effect immediately rather than when the token expires.
- ServiceKeyAuthentication: `Authorization: ClickKey <prefix>.<secret>` for service accounts (machine-to-machine).
"""

import hmac
from datetime import timedelta

from django.utils import timezone
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import OSAccount, OSSession, ServiceAccount

SEEN_EVERY = timedelta(seconds=60)


class OSJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result
        sid = token.get("os_sid")
        if not sid:
            raise exceptions.AuthenticationFailed("Sign in to Click Business OS.", code="os_session_required")
        session = OSSession.objects.filter(pk=sid, user=user).first()
        if session is None or not session.is_live:
            raise exceptions.AuthenticationFailed("Your session has ended. Please sign in again.", code="session_expired")
        account = OSAccount.objects.filter(user=user).only("status").first()
        if account is None or account.status != OSAccount.Status.ACTIVE:
            raise exceptions.AuthenticationFailed("This account can’t use Click Business OS right now.", code="account_inactive")
        now = timezone.now()
        if now - session.last_seen_at > SEEN_EVERY:
            OSSession.objects.filter(pk=session.pk).update(last_seen_at=now)
        request.os_session = session
        return user, token


class ServiceKeyAuthentication(BaseAuthentication):
    keyword = "ClickKey"

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith(self.keyword + " "):
            return None
        raw = header[len(self.keyword) + 1:].strip()
        prefix, _, secret = raw.partition(".")
        account = ServiceAccount.objects.select_related("user", "organization").filter(key_prefix=prefix).first()
        if account is None or not secret or not hmac.compare_digest(account.key_hash, ServiceAccount.hash_secret(secret)):
            raise exceptions.AuthenticationFailed("Invalid service key.", code="invalid_service_key")
        if not account.is_usable or not account.user.is_active:
            raise exceptions.AuthenticationFailed("This service key is revoked or expired.", code="service_key_inactive")
        ServiceAccount.objects.filter(pk=account.pk).update(last_used_at=timezone.now())
        request.os_service_account = account
        return account.user, None

    def authenticate_header(self, request):
        return self.keyword
