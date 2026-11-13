"""
Safety Center API. Shows what is happening right now (an active ride, a parcel on its way, a professional coming
today, a stay or journey under way) with the safety actions that really work for it, the customer's safety reports
(support requests flagged as safety cases), and account protection: how many sign-ins are active and signing out of
every other device. The emergency number comes from settings (CLICK_EMERGENCY_NUMBER, India's 112 by default).
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.permissions import IsCustomer

from .models import SupportTicket



def _sessions(user):
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

    now = timezone.now()
    live = OutstandingToken.objects.filter(user=user, expires_at__gt=now).exclude(id__in=BlacklistedToken.objects.values("token_id"))
    return live


class SafetyView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        c = request.user.customer_profile
        now = timezone.now()
        rides = [{"id": str(r.id), "number": r.number, "title": f"{r.pickup_label} → {r.drop_label}", "status": r.get_status_display(),
                  "driver": r.driver.business_name if r.driver_id else None, "link": f"/rides/{r.id}"}
                 for r in c.rides.exclude(status__in=["completed", "cancelled", "no_driver", "expired"]).select_related("driver").order_by("-created_at")[:3]]
        parcels = [{"id": str(p.id), "number": p.number, "title": f"{p.pickup_label} → {p.drop_label}", "status": p.get_status_display(),
                    "link": f"/parcels/{p.id}"}
                   for p in c.parcels.exclude(status__in=["delivered", "cancelled", "failed", "returned", "no_partner"]).order_by("-created_at")[:3]]
        services = []
        for b in c.service_bookings.exclude(status__in=["completed", "paid", "cancelled", "unassigned"]).select_related("provider__partner", "category").order_by("-created_at")[:3]:
            p = b.provider
            services.append({"id": str(b.id), "number": b.number, "title": b.category.name, "status": b.get_status_display(), "link": f"/services/bookings/{b.id}",
                             "professional": p.partner.business_name if p else None, "verified": bool(p and p.partner.partner_code),
                             "rating": f"{p.rating_average}" if p and p.rating_count else None, "jobs": p.jobs_completed if p else None})
        trips = [{"id": str(b.id), "title": f"{b.from_stop.place.name} → {b.to_stop.place.name}", "status": b.get_status_display(), "pnr": b.pnr, "link": f"/travel/bookings/{b.id}"}
                 for b in c.travel_bookings.filter(status="confirmed", departs_at__lte=now + timedelta(hours=24), arrives_at__gte=now - timedelta(hours=6))
                 .select_related("from_stop__place", "to_stop__place")[:2]]
        stays = [{"id": str(b.id), "title": b.property.partner.business_name, "status": b.get_status_display(), "link": f"/hotels/bookings/{b.id}"}
                 for b in c.hotel_bookings.filter(status__in=["confirmed", "checked_in"], check_in__lte=now.date(), check_out__gte=now.date())
                 .select_related("property__partner")[:2]]
        reports = [{"id": str(t.id), "reference": t.reference, "subject": t.subject, "status": t.status, "status_label": t.get_status_display(),
                    "priority": t.priority, "created_at": t.created_at.isoformat()}
                   for t in SupportTicket.objects.filter(customer=c, is_safety=True).order_by("-created_at")[:10]]
        return Response({
            "emergency_number": settings.CLICK_EMERGENCY_NUMBER,
            "support": {"email": settings.CLICK_SUPPORT_EMAIL, "phone": settings.CLICK_SUPPORT_PHONE,
                        "phone_callable": settings.CLICK_SUPPORT_PHONE.replace("+", "").isdigit()},
            "active": {"rides": rides, "parcels": parcels, "services": services, "trips": trips, "stays": stays},
            "reports": reports,
            "sessions": {"active": _sessions(request.user).count()},
        })


class SignOutOthersView(APIView):
    """POST /customer/safety/sign-out-others — ends every other sign-in (their refresh tokens are revoked)."""

    permission_classes = [IsCustomer]

    def post(self, request):
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
        from rest_framework_simplejwt.tokens import RefreshToken

        current_jti = None
        raw = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE["name"])
        if raw:
            try:
                current_jti = RefreshToken(raw)["jti"]
            except Exception:  # noqa: BLE001 — an unreadable cookie just means nothing is kept
                current_jti = None
        n = 0
        for t in _sessions(request.user):
            if t.jti != current_jti:
                BlacklistedToken.objects.get_or_create(token=t)
                n += 1
        from apps.activity.services import record

        record(request.user.customer_profile, "account.signed_out_others", {"sessions": n})
        return Response({"signed_out": n, "active": _sessions(request.user).count()})
