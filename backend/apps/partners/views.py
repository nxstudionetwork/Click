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
