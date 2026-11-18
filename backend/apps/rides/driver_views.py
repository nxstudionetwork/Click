"""
/api/v1/partner/driver/* — Driver mode of Click Partner. The driver is resolved from request.user and must be a ride
partner (driver.require_driver); ride ids only ever select among that driver's own rides.
"""

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from . import driver as d


class DriverModeView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "partner_onboarding"

    @staticmethod
    def body(request) -> dict:
        return request.data if isinstance(request.data, dict) else {}


class ProfileView(DriverModeView):
    def get(self, request):
        return Response(d.profile(d.require_driver(request.user)))


class EarningsView(DriverModeView):
    def get(self, request):
        return Response(d.earnings(d.require_driver(request.user)))


class TripsView(DriverModeView):
    def get(self, request):
        return Response(d.trips(d.require_driver(request.user), request.query_params))


class RateRiderView(DriverModeView):
    def post(self, request, pk):
        partner = d.require_driver(request.user)
        body = self.body(request)
        r = d.rate_rider(partner, pk, body.get("stars"), str(body.get("note", "")))
        return Response({"stars": r.stars}, status=201)


class SafetyView(DriverModeView):
    def post(self, request, pk):
        partner = d.require_driver(request.user)
        body = self.body(request)
        return Response(d.safety_report(partner, pk, str(body.get("kind", "")), str(body.get("note", ""))), status=201)
