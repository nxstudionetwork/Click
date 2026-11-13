"""Discover API: the feed (public; personal sections when signed in), sponsored event tracking, hide an ad."""

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import DomainError
from apps.core.api.permissions import IsCustomer

from . import engine
from .models import AdCampaign, AdHide


def _customer(request):
    u = request.user
    return u.customer_profile if u and u.is_authenticated and hasattr(u, "customer_profile") else None


class FeedView(APIView):
    """GET /discover?city=&service="""

    permission_classes = [permissions.AllowAny]
    throttle_scope = "search"

    def get(self, request):
        qp = request.query_params
        return Response(engine.feed(_customer(request), engine.viewer_key(request), city=qp.get("city", ""), service=qp.get("service", "")))


class EventView(APIView):
    """POST /discover/events {token, kind: impression|click} — counted once per served card; charges the campaign."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = "search"

    def post(self, request):
        ok = engine.track(str(request.data.get("token") or ""), str(request.data.get("kind") or ""), engine.viewer_key(request))
        return Response({"counted": ok}, status=status.HTTP_202_ACCEPTED)


class HideView(APIView):
    """POST /customer/discover/hide {campaign} — never show this ad to me again."""

    permission_classes = [IsCustomer]

    def post(self, request):
        c = AdCampaign.objects.filter(pk=request.data.get("campaign")).first()
        if c is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        AdHide.objects.get_or_create(customer=request.user.customer_profile, campaign=c)
        return Response({"hidden": True})
