"""
Provider-agnostic phone sign-in.

1. The client completes OTP with the configured provider (Firebase today) and
   sends the provider's credential: POST /auth/identity/exchange {provider, token}
2. The backend verifies it server-side and resolves the Click customer:
     existing -> Click session (same access token + httpOnly refresh cookie as before)
     new      -> {status: "profile_required", signupToken} (signed, 20 min)
3. New customers finish: POST /auth/identity/signup {signupToken, fullName, email, addresses[]}

The provider credential is used once; everything after uses Click's own session.
"""

import logging

from rest_framework import serializers, status
from rest_framework.response import Response

from apps.activity.services import record
from apps.core.api.exceptions import DomainError
from apps.customers.models import MAX_ADDRESSES
from apps.users.views import AuthView, _session_response

from . import services
from .providers import IdentityError, get_verifier

logger = logging.getLogger(__name__)


class ExchangeSerializer(serializers.Serializer):
    provider = serializers.CharField(max_length=32)
    token = serializers.CharField(max_length=8192)


class SignupSerializer(serializers.Serializer):
    signup_token = serializers.CharField(max_length=2048)
    full_name = serializers.CharField(min_length=2, max_length=150)
    email = serializers.EmailField(max_length=254)
    addresses = serializers.ListField(child=serializers.DictField(), min_length=1, max_length=MAX_ADDRESSES)

    def validate_full_name(self, v):
        return " ".join(v.split())

    def validate_email(self, v):
        return v.strip().lower()


class IdentityExchangeView(AuthView):
    def post(self, request):
        s = ExchangeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            identity = get_verifier(s.validated_data["provider"]).verify(s.validated_data["token"])
        except IdentityError as e:
            logger.info("identity exchange rejected: %s", e.reason)
            raise DomainError("We couldn’t verify your phone. Please try again.", code="identity_invalid", status_code=401)
        user = services.resolve_user(identity)
        if user:
            if hasattr(user, "customer_profile"):
                record(user.customer_profile, "account.login", {"provider": identity.provider})
            response = _session_response(user)
            response.data["status"] = "authenticated"
            return response
        return Response({"status": "profile_required", "signup_token": services.issue_signup_token(identity),
                         "phone_number": identity.phone_number, "expires_in": services.SIGNUP_MAX_AGE})


class IdentitySignupView(AuthView):
    def post(self, request):
        s = SignupSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        identity = services.read_signup_token(s.validated_data["signup_token"])
        user, created = services.complete_signup(identity, full_name=s.validated_data["full_name"], email=s.validated_data["email"],
                                                 addresses=s.validated_data["addresses"])
        response = _session_response(user, status.HTTP_201_CREATED if created else status.HTTP_200_OK)
        response.data["status"] = "authenticated"
        return response


class PartnerSignupSerializer(serializers.Serializer):
    signup_token = serializers.CharField(max_length=2048)


class IdentityPartnerSignupView(AuthView):
    """Click Partner: turn a verified phone (signup token from /exchange) into a phone-only Click account."""

    def post(self, request):
        s = PartnerSignupSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        identity = services.read_signup_token(s.validated_data["signup_token"])
        user, created = services.complete_partner_signup(identity)
        response = _session_response(user, status.HTTP_201_CREATED if created else status.HTTP_200_OK)
        response.data["status"] = "authenticated"
        return response
