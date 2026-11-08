from rest_framework import serializers

from apps.payments.models import PaymentMethod
from apps.payments.serializers import PaymentSerializer

from .models import ROW_LETTERS, BookedSeat, Booking, Event, Show, Venue
from .services import MAX_SEATS, can_cancel


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


class VenueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Venue
        fields = ["id", "slug", "name", "kind", "city", "locality", "address"]


class EventSerializer(serializers.ModelSerializer):
    """Contract mirrored by `ClickEvent` in packages/api/src/types.ts."""

    languages = serializers.SerializerMethodField()
    genres = serializers.SerializerMethodField()
    next_show_at = serializers.DateTimeField(read_only=True, allow_null=True, default=None)

    class Meta:
        model = Event
        fields = ["id", "slug", "kind", "status", "title", "tagline", "description", "poster_url", "languages", "genres",
                  "certification", "duration_minutes", "release_date", "cast", "rating_average", "rating_count", "next_show_at"]

    def get_languages(self, e) -> list[str]:
        return _split(e.languages)

    def get_genres(self, e) -> list[str]:
        return _split(e.genres)


class ShowSerializer(serializers.ModelSerializer):
    venue = VenueSerializer(read_only=True)
    seats_left = serializers.IntegerField(read_only=True, default=None)

    class Meta:
        model = Show
        fields = ["id", "starts_at", "language", "format", "screen", "price", "premium_price", "currency", "venue", "seats_left"]


class SeatMapSerializer(ShowSerializer):
    event = EventSerializer(read_only=True)
    layout = serializers.SerializerMethodField()

    class Meta(ShowSerializer.Meta):
        fields = ShowSerializer.Meta.fields + ["event", "layout"]

    def get_layout(self, show):
        taken = set(BookedSeat.objects.filter(show=show, is_active=True).values_list("label", flat=True))
        rows = []
        for i in range(show.rows):
            letter = ROW_LETTERS[i]
            tier = "premium" if i >= show.rows - show.premium_rows else "standard"
            rows.append({"row": letter, "tier": tier, "seats": [
                {"label": f"{letter}{n}", "available": f"{letter}{n}" not in taken} for n in range(1, show.seats_per_row + 1)
            ]})
        return {"rows": rows, "max_per_booking": MAX_SEATS}


class BookedSeatSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookedSeat
        fields = ["label", "tier", "price"]


class BookingSerializer(serializers.ModelSerializer):
    show = ShowSerializer(read_only=True)
    event = EventSerializer(source="show.event", read_only=True)
    seats = serializers.SerializerMethodField()
    payments = PaymentSerializer(many=True, read_only=True)
    can_cancel = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = ["id", "reference", "status", "event", "show", "seats", "subtotal", "convenience_fee", "tax", "total",
                  "currency", "payments", "can_cancel", "created_at", "cancelled_at"]

    def get_seats(self, b):
        return BookedSeatSerializer(b.seats.all(), many=True).data

    def get_can_cancel(self, b) -> bool:
        return can_cancel(b)


class CreateBookingSerializer(serializers.Serializer):
    show_id = serializers.UUIDField()
    seats = serializers.ListField(child=serializers.CharField(max_length=4), min_length=1, max_length=MAX_SEATS)
    payment_method = serializers.ChoiceField(choices=[PaymentMethod.PAY_AT_VENUE, PaymentMethod.WALLET])
    idempotency_key = serializers.UUIDField()
