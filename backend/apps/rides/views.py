from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import DomainError
from apps.core.api.permissions import IsCustomer
from apps.partners.services import require_owned_partner

from . import services
from .models import DriverLocation, Ride, RideOffer
from .pricing import active_offers
from .serializers import (
    DriverLocationSerializer, RateSerializer, RequestRideSerializer, RideOfferSerializer, RideSerializer,
    RideSummarySerializer, SafetySerializer, TripSerializer, fare_dict,
)


def _places(data) -> tuple:
    p = lambda d: services.Place(d["label"], d.get("address", ""), d["lat"], d["lng"])  # noqa: E731
    return p(data["pickup"]), [p(s) for s in data.get("stops", [])], p(data["drop"])


def customer_rides(request):
    # Ownership isolation: customers only ever see their own rides.
    return (Ride.objects.filter(customer=request.user.customer_profile)
            .select_related("ride_type", "driver", "driver__profile", "driver__ride_location")
            .prefetch_related("stops", "events", "payments"))


class PlacesView(APIView):
    """GET /customer/rides/places?q= — saved addresses, recent ride places and Click places (all with coordinates)."""

    permission_classes = [IsCustomer]

    def get(self, request):
        return Response({"results": services.search_places(request.user.customer_profile, request.query_params.get("q", ""))})


class QuoteView(APIView):
    """POST /customer/rides/quote — estimated route, upfront fare and pickup ETA per ride type."""

    permission_classes = [IsCustomer]
    throttle_scope = "quote"

    def post(self, request):
        s = TripSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        offer = RideOffer.objects.filter(pk=s.validated_data.get("offer_id")).first() if s.validated_data.get("offer_id") else None
        q = services.quote(*_places(s.validated_data), offer=offer)
        return Response({
            "distance_km": f"{q['route'].distance_km:.1f}",
            "estimate_basis": q["route"].basis,
            "options": [{
                "ride_type": {"code": o["ride_type"].code, "name": o["ride_type"].name, "description": o["ride_type"].description,
                              "icon": o["ride_type"].icon, "seats": o["ride_type"].seats},
                "duration_minutes": o["duration_minutes"], "pickup_eta_minutes": o["pickup_eta_minutes"], "available": o["available"],
                "fare": fare_dict(o["fare"]), "offer_problem": o["offer_problem"],
            } for o in q["options"]],
            "offers": RideOfferSerializer(active_offers(), many=True).data,
        })


class RideListCreateView(generics.ListAPIView):
    """GET /customer/rides (history) · POST /customer/rides (book; idempotent; fare computed here)."""

    permission_classes = [IsCustomer]
    serializer_class = RideSummarySerializer

    def get_queryset(self):
        return customer_rides(self.request)

    def post(self, request):
        s = RequestRideSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        pickup, stops, drop = _places(d)
        ride, created = services.request_ride(
            customer=request.user.customer_profile, ride_type_code=d["ride_type"], pickup=pickup, drop=drop, stops=stops,
            payment_method=d["payment_method"], idempotency_key=d["idempotency_key"], offer_id=d.get("offer_id"),
            scheduled_for=d.get("scheduled_for"), passenger_name=d["passenger_name"], passenger_phone=d["passenger_phone"],
        )
        ride = customer_rides(request).get(pk=ride.pk)
        return Response(RideSerializer(ride).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class RideDetailView(generics.RetrieveAPIView):
    permission_classes = [IsCustomer]
    serializer_class = RideSerializer

    def get_queryset(self):
        return customer_rides(self.request)


class RideCancelView(APIView):
    permission_classes = [IsCustomer]

    def post(self, request, pk):
        ride = get_object_or_404(customer_rides(request), pk=pk)
        services.cancel_by_customer(ride, str(request.data.get("reason", ""))[:200])
        return Response(RideSerializer(customer_rides(request).get(pk=pk)).data)


class RideRateView(APIView):
    permission_classes = [IsCustomer]

    def post(self, request, pk):
        ride = get_object_or_404(customer_rides(request), pk=pk)
        s = RateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.rate(ride, **s.validated_data)
        return Response(RideSerializer(customer_rides(request).get(pk=pk)).data, status=status.HTTP_201_CREATED)


class RideSafetyView(APIView):
    """POST /customer/rides/<id>/safety — records SOS / share / report for Click's safety team."""

    permission_classes = [IsCustomer]

    def post(self, request, pk):
        ride = get_object_or_404(customer_rides(request), pk=pk)
        s = SafetySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.safety_event(ride, s.validated_data["kind"], s.validated_data["note"])
        return Response({"recorded": True}, status=status.HTTP_201_CREATED)


# --- Partner (driver) API -----------------------------------------------------------------------

class DriverView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def driver(self, request):
        partner = require_owned_partner(request.user)
        if partner.partner_type.slug != "transport":
            raise DomainError("Only Click drivers can do this.", code="not_a_driver", status_code=403)
        return partner


class DriverOffersView(DriverView):
    """GET /partner/rides/offers — rides offered to this driver that are still open."""

    def get(self, request):
        driver = self.driver(request)
        rides = Ride.objects.filter(driver_offers__driver=driver, driver_offers__response="pending", status="searching").select_related("ride_type")
        return Response({"results": RideSummarySerializer(rides, many=True).data})


class DriverAcceptView(DriverView):
    def post(self, request, pk):
        ride = services.driver_accept(get_object_or_404(Ride, pk=pk), self.driver(request))
        return Response(RideSummarySerializer(ride).data)


class DriverStatusView(DriverView):
    """POST /partner/rides/<id>/status {status: driver_arrived|in_progress|completed} — only for the assigned driver."""

    def post(self, request, pk):
        ride = services.driver_step(get_object_or_404(Ride, pk=pk), self.driver(request), str(request.data.get("status", "")))
        return Response(RideSummarySerializer(ride).data)


class DriverLocationView(DriverView):
    """POST /partner/driver/location {lat, lng} — the Partner App reports the driver's position."""

    def post(self, request):
        driver = self.driver(request)
        s = DriverLocationSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        DriverLocation.objects.update_or_create(driver=driver, defaults={**s.validated_data, "reported_at": timezone.now()})
        return Response({"ok": True})
