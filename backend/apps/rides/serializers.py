from django.db.models import Avg, Count
from django.utils import timezone
from rest_framework import serializers

from .matching import LIVE_FOR
from .models import Ride, RideOffer, RideType


class PlaceSerializer(serializers.Serializer):
    """A point chosen by the customer. Coordinates are range-checked; labels are plain text."""

    label = serializers.CharField(max_length=120)
    address = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lng = serializers.FloatField(min_value=-180, max_value=180)


class TripSerializer(serializers.Serializer):
    pickup = PlaceSerializer()
    drop = PlaceSerializer()
    stops = PlaceSerializer(many=True, required=False, default=list, max_length=2)
    offer_id = serializers.UUIDField(required=False, allow_null=True)


class RequestRideSerializer(TripSerializer):
    ride_type = serializers.SlugField()
    payment_method = serializers.ChoiceField(choices=["cash", "wallet"])
    idempotency_key = serializers.UUIDField()
    scheduled_for = serializers.DateTimeField(required=False, allow_null=True)
    passenger_name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    passenger_phone = serializers.RegexField(r"^\+?[\d\s-]{8,20}$", required=False, allow_blank=True, default="")


class RideTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RideType
        fields = ["code", "name", "description", "icon", "seats"]


class RideOfferSerializer(serializers.ModelSerializer):
    ride_types = serializers.SlugRelatedField(many=True, read_only=True, slug_field="code")

    class Meta:
        model = RideOffer
        fields = ["id", "title", "description", "discount_type", "discount_value", "max_discount", "min_fare", "ride_types", "ends_at"]


def fare_dict(f) -> dict:
    return {k: f"{getattr(f, k):.2f}" for k in ("base", "distance", "time", "fees", "subtotal", "discount", "total")}


def driver_card(ride: Ride) -> dict | None:
    """What a rider needs to identify the driver and vehicle (safety): name, rating, vehicle, colour, plate, location."""
    d = ride.driver
    if d is None:
        return None
    details = getattr(getattr(d, "profile", None), "details", {}) or {}
    stats = d.ride_ratings.aggregate(avg=Avg("stars"), n=Count("id"))
    loc = getattr(d, "ride_location", None)
    location = None
    if loc and ride.status in ("driver_assigned", "driver_arrived", "in_progress"):
        location = {"lat": float(loc.lat), "lng": float(loc.lng), "reported_at": loc.reported_at.isoformat(),
                    "live": timezone.now() - loc.reported_at <= LIVE_FOR}
    name = (getattr(d.profile, "contact_name", "") if hasattr(d, "profile") else "") or d.business_name or "Your driver"
    return {
        "name": name.split()[0] if name else "Your driver",
        "rating": round(stats["avg"], 1) if stats["avg"] else None,
        "rating_count": stats["n"],
        "vehicle_type": details.get("vehicle_type", ""),
        "vehicle_model": details.get("vehicle_model", ""),
        "vehicle_color": details.get("vehicle_color", ""),
        "plate": details.get("vehicle_number", ""),
        "location": location,
    }


class RideSerializer(serializers.ModelSerializer):
    ride_type = RideTypeSerializer(read_only=True)
    pickup = serializers.SerializerMethodField()
    drop = serializers.SerializerMethodField()
    stops = serializers.SerializerMethodField()
    fare = serializers.SerializerMethodField()
    driver = serializers.SerializerMethodField()
    events = serializers.SerializerMethodField()
    payment = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Ride
        fields = [
            "id", "number", "status", "status_label", "ride_type", "pickup", "drop", "stops", "distance_km", "duration_minutes",
            "fare", "offer_title", "currency", "payment_method", "payment", "passenger_name", "scheduled_for", "driver",
            "driver_assigned_at", "started_at", "completed_at", "cancelled_at", "events", "rating", "can_cancel", "created_at",
        ]

    def get_pickup(self, r):
        return {"label": r.pickup_label, "address": r.pickup_address, "lat": float(r.pickup_lat), "lng": float(r.pickup_lng)}

    def get_drop(self, r):
        return {"label": r.drop_label, "address": r.drop_address, "lat": float(r.drop_lat), "lng": float(r.drop_lng)}

    def get_stops(self, r):
        return [{"label": s.label, "address": s.address, "lat": float(s.lat), "lng": float(s.lng)} for s in r.stops.all()]

    def get_fare(self, r):
        subtotal = r.fare_base + r.fare_distance + r.fare_time + r.fare_fees
        return {"base": f"{r.fare_base:.2f}", "distance": f"{r.fare_distance:.2f}", "time": f"{r.fare_time:.2f}", "fees": f"{r.fare_fees:.2f}",
                "subtotal": f"{r.total + r.discount:.2f}", "discount": f"{r.discount:.2f}", "total": f"{r.total:.2f}",
                "minimum_applied": subtotal != r.total + r.discount}

    def get_driver(self, r):
        return driver_card(r)

    def get_events(self, r):
        return [{"to_status": e.to_status, "created_at": e.created_at.isoformat()} for e in r.events.all()]

    def get_payment(self, r):
        p = r.payments.order_by("-created_at").first()
        return {"method": p.method, "status": p.status} if p else None

    def get_rating(self, r):
        rt = getattr(r, "rating", None) if hasattr(r, "rating") else None
        return {"stars": rt.stars, "comment": rt.comment} if rt else None

    def get_can_cancel(self, r) -> bool:
        from .models import CUSTOMER_CANCELLABLE

        return r.status in CUSTOMER_CANCELLABLE


class RideSummarySerializer(serializers.ModelSerializer):
    ride_type = RideTypeSerializer(read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Ride
        fields = ["id", "number", "status", "status_label", "ride_type", "pickup_label", "drop_label", "total", "currency",
                  "payment_method", "scheduled_for", "created_at"]


class RateSerializer(serializers.Serializer):
    stars = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    compliment = serializers.ChoiceField(choices=["", "safe_driving", "clean_vehicle", "on_time", "friendly"], required=False, default="")


class SafetySerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["sos", "share", "report"])
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class DriverLocationSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lng = serializers.FloatField(min_value=-180, max_value=180)
