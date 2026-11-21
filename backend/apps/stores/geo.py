"""Distance between stores and a customer's point, computed in PostgreSQL (no PostGIS needed at this scale).

Stores without coordinates are never treated as "near": proximity is only claimed when both points are known.
"""

from django.db.models import F, FloatField, QuerySet, Value
from django.db.models.functions import ASin, Cast, Cos, Power, Radians, Sin, Sqrt
from rest_framework import serializers

EARTH_RADIUS_KM = 6371.0
DEFAULT_RADIUS_KM = 10.0
MAX_RADIUS_KM = 50.0


class NearQuerySerializer(serializers.Serializer):
    """Validates `lat`, `lng` and optional `radius` (km) query parameters."""

    lat = serializers.FloatField(min_value=-90, max_value=90)
    lng = serializers.FloatField(min_value=-180, max_value=180)
    radius = serializers.FloatField(min_value=0.5, max_value=MAX_RADIUS_KM, default=DEFAULT_RADIUS_KM)


def with_distance(qs: QuerySet, lat: float, lng: float) -> QuerySet:
    """Annotate `distance_km` (haversine) and drop stores without coordinates."""
    s_lat = Radians(Cast(F("latitude"), FloatField()))
    s_lng = Radians(Cast(F("longitude"), FloatField()))
    p_lat = Radians(Value(lat, output_field=FloatField()))
    p_lng = Radians(Value(lng, output_field=FloatField()))
    a = Power(Sin((s_lat - p_lat) / 2), 2) + Cos(p_lat) * Cos(s_lat) * Power(Sin((s_lng - p_lng) / 2), 2)
    return qs.filter(latitude__isnull=False, longitude__isnull=False).annotate(
        distance_km=Value(2 * EARTH_RADIUS_KM, output_field=FloatField()) * ASin(Sqrt(a))
    )
