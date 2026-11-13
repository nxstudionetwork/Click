"""
/api/v1/partner/* — the Click Partner App surface.

Every view resolves the partner from request.user; no URL or body ever names
a partner, so Partner A cannot address Partner B's data.
"""

from django.db.models import Prefetch
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import PartnerCategory, PartnerType
from .serializers import (
    ChooseCategorySerializer, LocationSerializer, PartnerSerializer, PartnerTypeSerializer, ProfileSerializer,
)


class PartnerCatalogView(APIView):
    """Partner types and categories with their onboarding configuration (public reference data)."""

    authentication_classes: list = []
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        types = PartnerType.objects.filter(is_active=True).prefetch_related(
            Prefetch("categories", queryset=PartnerCategory.objects.select_related("partner_type").order_by("sort_order", "name"))
        )
        response = Response({"types": PartnerTypeSerializer(types, many=True).data})
        response["Cache-Control"] = "public, max-age=300"
        return response


class PartnerView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def partner_response(self, partner):
        data = PartnerSerializer(partner, context={"request": self.request}).data if partner else None
        return Response({"partner": data, "onboardingStep": services.onboarding_step(partner)})


class PartnerMeView(PartnerView):
    def get(self, request):
        return self.partner_response(services.owned_partner(request.user))


class OnboardingView(PartnerView):
    throttle_scope = "partner_onboarding"


class ChooseCategoryView(OnboardingView):
    def post(self, request):
        s = ChooseCategorySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        partner = services.choose_category(request.user, s.validated_data["partner_type"], s.validated_data["category"])
        return self.partner_response(partner)


class ProfileView(OnboardingView):
    def patch(self, request):
        s = ProfileSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return self.partner_response(services.save_profile(request.user, s.validated_data))


class LocationView(OnboardingView):
    def patch(self, request):
        s = LocationSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return self.partner_response(services.save_location(request.user, s.validated_data))


class SubmitView(OnboardingView):
    def post(self, request):
        return self.partner_response(services.submit(request.user))


# --- Partner Home / operations ---------------------------------------------------------------------------------
# Every view resolves the partner from request.user (require_owned_partner) and only reads that partner's links.

from django.conf import settings  # noqa: E402
from rest_framework import serializers  # noqa: E402

from apps.core.api.exceptions import DomainError  # noqa: E402

from . import notifications as partner_notifications  # noqa: E402
from . import workspace  # noqa: E402
from .models import PartnerNotification  # noqa: E402


def _onboarded_partner(request):
    partner = services.require_owned_partner(request.user)
    if not partner.is_onboarded:
        raise DomainError("Finish setting up your Partner profile first.", code="onboarding_incomplete", status_code=409)
    return partner


class HomeView(APIView):
    """GET /partner/home: the whole operations dashboard in one request (sections fail independently)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(workspace.build_home(_onboarded_partner(request)))


class AvailabilitySerializer(serializers.Serializer):
    available = serializers.BooleanField()


class AvailabilityView(PartnerView):
    """POST /partner/availability {available}: persisted, audited, and applied to the customer-facing records."""

    throttle_scope = "partner_onboarding"

    def post(self, request):
        _onboarded_partner(request)
        s = AvailabilitySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        partner = workspace.set_availability(request.user, s.validated_data["available"])
        return Response({**self.partner_response(partner).data,
                         "availability": workspace.availability_state(partner, workspace.provider_for(partner))})


class WorkView(APIView):
    """GET /partner/work?view=: the Work page list for the partner's workspace."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(workspace.build_work(_onboarded_partner(request), request.query_params.get("view", "")[:30]))


class WorkActionView(APIView):
    """POST /partner/work/<kind>/<id>/<action> {reason?}: the server checks ownership and the transition itself."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "partner_onboarding"

    def post(self, request, kind, pk, action):
        partner = _onboarded_partner(request)
        payload = request.data if isinstance(request.data, dict) else {}
        return Response(workspace.perform(partner, kind, str(pk), action, payload, request.user))


class EarningsView(APIView):
    """GET /partner/earnings?days=7|30: daily totals and recent completed work."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        days = 30 if request.query_params.get("days") == "30" else 7
        return Response(workspace.build_earnings(_onboarded_partner(request), days))


class NotificationListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        partner = services.require_owned_partner(request.user)
        items = partner.notifications.all()[:50]
        return Response({
            "unread": partner_notifications.unread_count(partner),
            "results": [{"id": str(n.id), "category": n.category, "title": n.title, "body": n.body, "link_path": n.link_path,
                         "read": n.read_at is not None, "created_at": n.created_at.isoformat()} for n in items],
        })


class NotificationReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk=None):
        partner = services.require_owned_partner(request.user)
        if pk is not None and not partner.notifications.filter(pk=pk).exists():
            raise DomainError("Notification not found.", code="not_found", status_code=404)
        partner_notifications.mark_read(partner, pk)
        return Response({"unread": partner_notifications.unread_count(partner)})


class DevPartnerLoginView(APIView):
    """
    DEVELOPMENT ONLY (404 unless DEBUG and CLICK_DEV_LOGIN): GET lists the seeded test partners, POST {code} signs in
    as one of them. Lets every category's Home be tested without real SMS. Never present in production.
    """

    authentication_classes: list = []
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth_session"

    def _partners(self):
        if not (settings.DEBUG and settings.CLICK_DEV_LOGIN_ENABLED):
            raise DomainError("Not found.", code="not_found", status_code=404)
        from devseed.partners import TEST_PARTNER_EMAIL_DOMAIN

        from .models import Partner

        return (Partner.objects.filter(memberships__user__email__endswith=TEST_PARTNER_EMAIL_DOMAIN, memberships__role="owner",
                                       partner_code__isnull=False)
                .select_related("category").order_by("partner_code"))

    def get(self, request):
        return Response({"enabled": True, "partners": [
            {"code": p.partner_code, "name": p.business_name, "category": p.category.name} for p in self._partners()]})

    def post(self, request):
        from apps.users.views import _session_response

        partner = self._partners().filter(partner_code=str(request.data.get("code", ""))).first()
        if partner is None:
            raise DomainError("Test partner not found. Run `python manage.py seed_dev_data`.", code="dev_partner_missing", status_code=409)
        user = partner.memberships.get(role="owner").user
        return _session_response(user)
