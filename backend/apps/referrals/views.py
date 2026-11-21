"""Referrals API."""

from django.conf import settings
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import DomainError
from apps.core.api.permissions import IsCustomer

from . import services
from .models import Referral


class MineView(APIView):
    """GET /customer/referrals — your code, link, rules and the people who joined with it (first names only)."""

    permission_classes = [IsCustomer]

    def get(self, request):
        c = request.user.customer_profile
        rc = services.code_for(c)
        rows = Referral.objects.filter(referrer=c).select_related("referee__user")[:50]
        earned = sum(settings.CLICK_REFERRAL_REFERRER_POINTS for r in rows if r.status == Referral.Status.REWARDED)
        return Response({
            "code": rc.code, "link": f"/join/{rc.code}",
            "rules": {"referrer_points": settings.CLICK_REFERRAL_REFERRER_POINTS, "referee_points": settings.CLICK_REFERRAL_REFEREE_POINTS,
                      "monthly_cap": settings.CLICK_REFERRAL_MONTHLY_CAP,
                      "how": "Your friend signs up with your code. When their first order is delivered, you both get Click. points."},
            "referrals": [{"id": str(r.id), "name": ((r.referee.user.full_name or "A friend").split(" ")[0] if r.referee.user.is_active else "A friend"),
                           "status": r.status, "status_label": r.get_status_display(), "reason": r.reason, "joined_at": r.created_at.isoformat()} for r in rows],
            "earned_points": earned,
        })


class CheckView(APIView):
    """GET /referrals/<code> — is this code valid? (For the sign-up screen; shows only the inviter's first name.)"""

    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    def get(self, request, code):
        rc = services.lookup(code)
        if rc is None:
            raise DomainError("That invite code isn’t valid.", code="referral_invalid", status_code=404)
        return Response({"code": rc.code, "inviter": (rc.customer.user.full_name or "A friend").split(" ")[0],
                         "referee_points": settings.CLICK_REFERRAL_REFEREE_POINTS})
