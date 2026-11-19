"""Maps API for the apps: place search, current-location address and road route preview. Signed-in users only."""

from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import DomainError

from . import providers


def _point(params, lat_key="lat", lng_key="lng"):
    try:
        lat, lng = float(params.get(lat_key)), float(params.get(lng_key))
    except (TypeError, ValueError):
        return None
    return (lat, lng) if -90 <= lat <= 90 and -180 <= lng <= 180 else None


class GeoView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "geo"


class SearchView(GeoView):
    """GET /geo/search?q=&lat=&lng= — places in India, nearest first when a point is given."""

    def get(self, request):
        results = providers.search(request.query_params.get("q", ""), _point(request.query_params))
        return Response({"results": [p.as_dict() for p in results], "enabled": providers.geocoder_enabled()})


class ReverseView(GeoView):
    """GET /geo/reverse?lat=&lng= — readable address for a point (the device's current location)."""

    def get(self, request):
        point = _point(request.query_params)
        if not point:
            raise DomainError("Send a valid lat and lng.", code="invalid_point")
        place = providers.reverse(*point)
        return Response({"place": place.as_dict() if place else None, "enabled": providers.geocoder_enabled()})


class RouteSerializer(serializers.Serializer):
    points = serializers.ListField(child=serializers.ListField(child=serializers.FloatField(), min_length=2, max_length=2),
                                   min_length=2, max_length=6)


class RouteView(GeoView):
    """POST /geo/route {points: [[lat, lng], ...]} — road distance, duration and line to draw."""

    def post(self, request):
        s = RouteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        route = providers.road_route([tuple(p) for p in s.validated_data["points"]])
        if not route:
            return Response({"route": None, "enabled": providers.router_enabled()})
        return Response({"route": {"distance_km": route.distance_km, "duration_min": route.duration_min, "geometry": route.geometry},
                         "enabled": True})
