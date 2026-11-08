"""
Authentication endpoints shared by all Click apps.

Access token: returned in the JSON body, short-lived, kept in memory client-side.
Refresh token: httpOnly cookie scoped to /api/v1/auth/, rotated on every use and
blacklisted after rotation/logout. Cookie-reading endpoints require the custom
`X-Click-Client` header, which cross-site forms cannot send without a CORS
preflight, as CSRF defence in depth on top of SameSite.
"""

import logging

from django.conf import settings
from django.contrib.auth import authenticate
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.api.exceptions import DomainError
from apps.customers.models import CustomerProfile

from . import firebase
from .models import AuthIdentity, User
from .serializers import FirebaseSessionSerializer, LoginSerializer, RegisterSerializer, UserSerializer

audit = logging.getLogger("click.audit")


def _set_refresh_cookie(response: Response, refresh: RefreshToken) -> None:
    cfg = settings.AUTH_REFRESH_COOKIE
    response.set_cookie(
        cfg["name"],
        str(refresh),
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        secure=cfg["secure"],
        samesite=cfg["samesite"],
        path=cfg["path"],
        domain=cfg["domain"],
    )


def _clear_refresh_cookie(response: Response) -> None:
    cfg = settings.AUTH_REFRESH_COOKIE
    response.delete_cookie(cfg["name"], path=cfg["path"], domain=cfg["domain"], samesite=cfg["samesite"])


def _session_response(user: User, status_code=status.HTTP_200_OK) -> Response:
    refresh = RefreshToken.for_user(user)
    response = Response({"user": UserSerializer(user).data, "access": str(refresh.access_token)}, status=status_code)
    _set_refresh_cookie(response, refresh)
    return response


def _require_client_header(request) -> None:
    if not request.headers.get("X-Click-Client"):
        raise DomainError("Missing client header.", code="client_header_required", status_code=403)


class AuthView(APIView):
    authentication_classes: list = []
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"


class RegisterView(AuthView):
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            user = User.objects.create_user(data["email"], data["password"], full_name=data.get("full_name", ""))
            CustomerProfile.objects.create(user=user)
        audit.info("user.registered", extra={"user_id": str(user.id)})
        return _session_response(user, status.HTTP_201_CREATED)


class LoginView(AuthView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request, username=serializer.validated_data["email"].lower(), password=serializer.validated_data["password"]
        )
        if user is None:
            audit.info("auth.login_failed")
            raise DomainError("Incorrect email or password.", code="invalid_credentials", status_code=401)
        return _session_response(user)


class FirebaseSessionView(AuthView):
    """
    Exchange a Firebase ID token (phone sign-in) for a Click session.

    The token is verified server-side; the Firebase UID inside it, never a
    client-supplied value, finds or creates the Click user. A returning
    partner gets the same user (and therefore the same Partner) every time.
    """

    def post(self, request):
        serializer = FirebaseSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            claims = firebase.verify_id_token(serializer.validated_data["id_token"])
        except firebase.FirebaseUnavailable:
            raise DomainError(
                "We couldn’t verify your number right now. Please try again shortly.",
                code="phone_auth_unavailable", status_code=503,
            )
        except firebase.FirebaseAuthError as exc:
            audit.info("auth.firebase_rejected", extra={"reason": exc.code})
            message = (
                "Your verification expired. Please request a new code."
                if exc.code == "token_expired"
                else "We couldn’t verify your number. Please try again."
            )
            raise DomainError(message, code="phone_verification_failed", status_code=401)

        user, created = _user_for_firebase(claims)
        if not user.is_active:
            raise DomainError("This account is disabled. Contact Click support.", code="account_disabled", status_code=403)
        audit.info("auth.firebase_login", extra={"user_id": str(user.id), "new_user": created})
        return _session_response(user, status.HTTP_201_CREATED if created else status.HTTP_200_OK)


def _user_for_firebase(claims: "firebase.FirebaseClaims") -> tuple[User, bool]:
    now = timezone.now()
    provider = AuthIdentity.Provider.FIREBASE
    for _ in range(2):
        identity = (
            AuthIdentity.objects.select_related("user").filter(provider=provider, subject=claims.uid).first()
        )
        if identity:
            changes = {"last_verified_at": now}
            if identity.phone_number != claims.phone_number:
                changes["phone_number"] = claims.phone_number
            AuthIdentity.objects.filter(pk=identity.pk).update(**changes)
            user = identity.user
            if user.phone != claims.phone_number:
                user.phone = claims.phone_number
                user.save(update_fields=["phone", "updated_at"])
            return user, False
        try:
            with transaction.atomic():
                user = User.objects.create_phone_user(claims.phone_number)
                AuthIdentity.objects.create(
                    user=user, provider=provider, subject=claims.uid,
                    phone_number=claims.phone_number, last_verified_at=now,
                )
            return user, True
        except IntegrityError:
            # A concurrent first sign-in for the same UID won the race; load it.
            continue
    raise DomainError("We couldn’t sign you in. Please try again.", code="identity_conflict", status_code=409)


class RefreshView(AuthView):
    def post(self, request):
        _require_client_header(request)
        raw = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE["name"])
        if not raw:
            raise DomainError("Not signed in.", code="not_authenticated", status_code=401)
        try:
            old = RefreshToken(raw)
            user = User.objects.get(id=old["user_id"], is_active=True)
            old.blacklist()
        except (TokenError, User.DoesNotExist, KeyError):
            response = Response(
                {"error": {"code": "session_expired", "message": "Your session has expired. Please sign in again."}},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            _clear_refresh_cookie(response)
            return response
        return _session_response(user)


class LogoutView(AuthView):
    def post(self, request):
        _require_client_header(request)
        raw = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE["name"])
        if raw:
            try:
                RefreshToken(raw).blacklist()
            except TokenError:
                pass
        response = Response(status=status.HTTP_204_NO_CONTENT)
        _clear_refresh_cookie(response)
        return response


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
