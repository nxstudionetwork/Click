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
from django.db import transaction
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.api.exceptions import DomainError
from apps.customers.models import CustomerProfile

from .models import User
from .serializers import LoginSerializer, RegisterSerializer, UserSerializer

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


def _require_password_auth():
    if not settings.CLICK_PASSWORD_AUTH_ENABLED:
        raise DomainError("Not found.", code="not_found", status_code=404)


class RegisterView(AuthView):
    """Development/test only. Customers sign up with phone OTP (apps.identity)."""

    def post(self, request):
        _require_password_auth()
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            user = User.objects.create_user(data["email"], data["password"], full_name=data.get("full_name", ""))
            CustomerProfile.objects.create(user=user)
        audit.info("user.registered", extra={"user_id": str(user.id)})
        return _session_response(user, status.HTTP_201_CREATED)


class LoginView(AuthView):
    """Development/test only (password). Customers sign in with phone OTP (apps.identity)."""

    def post(self, request):
        _require_password_auth()
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request, username=serializer.validated_data["email"].lower(), password=serializer.validated_data["password"]
        )
        if user is None:
            audit.info("auth.login_failed")
            raise DomainError("Incorrect email or password.", code="invalid_credentials", status_code=401)
        return _session_response(user)


class RefreshView(AuthView):
    throttle_scope = "auth_session"

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
    throttle_scope = "auth_session"

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


class DevLoginView(AuthView):
    throttle_scope = "auth_session"

    """
    DEVELOPMENT ONLY. GET reports whether dev login is available; POST signs in the seeded
    test customer (see `python manage.py seed_dev_data`). Returns 404 unless DEBUG is on and
    CLICK_DEV_LOGIN is enabled, so it does not exist in production.
    """

    def _test_user(self):
        if not (settings.DEBUG and settings.CLICK_DEV_LOGIN_ENABLED):
            raise DomainError("Not found.", code="not_found", status_code=404)
        return User.objects.filter(email=settings.CLICK_DEV_TEST_CUSTOMER_EMAIL, is_active=True).select_related("customer_profile").first()

    def get(self, request):
        user = self._test_user()
        if not user:
            return Response({"enabled": True, "customer": None, "hint": "Run `python manage.py seed_dev_data` first."})
        return Response({"enabled": True, "customer": {"name": user.full_name, "email": user.email,
                                                       "customer_code": user.customer_profile.customer_code}})

    def post(self, request):
        user = self._test_user()
        if not user:
            raise DomainError("Test customer not found. Run `python manage.py seed_dev_data`.", code="dev_customer_missing", status_code=409)
        audit.warning("auth.dev_login", extra={"user_id": str(user.id)})
        return _session_response(user)


class AvatarView(APIView):
    """POST /me/avatar (multipart `image`) stores a re-encoded square WebP; DELETE removes it."""

    from rest_framework.parsers import MultiPartParser

    parser_classes = [MultiPartParser]
    MAX_BYTES = 5 * 1024 * 1024

    def post(self, request):
        import uuid
        from io import BytesIO

        from django.core.files.base import ContentFile
        from PIL import Image, ImageOps, UnidentifiedImageError

        profile = getattr(request.user, "customer_profile", None)
        upload = request.FILES.get("image")
        if profile is None or upload is None:
            raise DomainError("Choose an image to upload.", code="image_required")
        if upload.size > self.MAX_BYTES:
            raise DomainError("Images must be 5 MB or smaller.", code="image_too_large")
        try:
            img = Image.open(upload)
            if img.format not in {"JPEG", "PNG", "WEBP"}:
                raise DomainError("Use a JPG, PNG or WebP image.", code="image_type")
            if img.width * img.height > 40_000_000:
                raise DomainError("That image is too large.", code="image_too_large")
            img = ImageOps.exif_transpose(img).convert("RGB")  # re-encoding drops EXIF (location etc.)
        except (UnidentifiedImageError, OSError):
            raise DomainError("That file isn’t a valid image.", code="image_invalid")
        img = ImageOps.fit(img, (512, 512), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, "WEBP", quality=82)
        if profile.avatar:
            profile.avatar.delete(save=False)
        profile.avatar.save(f"{uuid.uuid4().hex}.webp", ContentFile(buf.getvalue()), save=True)
        return Response(UserSerializer(request.user).data, status=status.HTTP_201_CREATED)

    def delete(self, request):
        profile = getattr(request.user, "customer_profile", None)
        if profile and profile.avatar:
            profile.avatar.delete(save=True)
        return Response(UserSerializer(request.user).data)
