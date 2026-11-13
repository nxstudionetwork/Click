from rest_framework import serializers

from apps.payments.models import PaymentMethod
from apps.payments.serializers import PaymentSerializer

from .models import BookedSeat, Booking, BookingConcession, Event, Show, Venue
from .services import MAX_CONCESSION_QTY, MAX_SEATS, can_cancel, cancellation_terms


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


class VenueSerializer(serializers.ModelSerializer):
    latitude = serializers.FloatField(allow_null=True, read_only=True)
    longitude = serializers.FloatField(allow_null=True, read_only=True)

    class Meta:
        model = Venue
        fields = ["id", "slug", "name", "kind", "city", "locality", "address", "latitude", "longitude", "facilities"]


class EventSerializer(serializers.ModelSerializer):
    """Contract mirrored by `ClickEvent` in packages/api/src/types.ts."""

    languages = serializers.SerializerMethodField()
    genres = serializers.SerializerMethodField()
    next_show_at = serializers.DateTimeField(read_only=True, allow_null=True, default=None)

    class Meta:
        model = Event
        fields = ["id", "slug", "kind", "status", "title", "tagline", "description", "poster_url", "backdrop_url", "trailer_url",
                  "languages", "genres", "certification", "duration_minutes", "release_date", "cast", "rating_average", "rating_count",
                  "next_show_at"]

    def get_languages(self, e) -> list[str]:
        return _split(e.languages)

    def get_genres(self, e) -> list[str]:
        return _split(e.genres)


class ShowSerializer(serializers.ModelSerializer):
    venue = VenueSerializer(read_only=True)
    seats_left = serializers.IntegerField(read_only=True, default=None)
    screen = serializers.SerializerMethodField()

    class Meta:
        model = Show
        fields = ["id", "starts_at", "language", "format", "screen", "price", "premium_price", "currency", "venue", "seats_left"]

    def get_screen(self, s) -> str:
        return s.screen_ref.name if s.screen_ref_id else s.screen


class BookedSeatSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookedSeat
        fields = ["label", "tier", "price"]


class BookingConcessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingConcession
        fields = ["name", "unit_price", "quantity", "line_total"]


class BookingSerializer(serializers.ModelSerializer):
    """A Showtime ticket. `ticketCode` (signed, venue-verifiable) is only given for confirmed, unfinished bookings."""

    show = ShowSerializer(read_only=True)
    event = EventSerializer(source="show.event", read_only=True)
    seats = serializers.SerializerMethodField()
    concessions = BookingConcessionSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    can_cancel = serializers.SerializerMethodField()
    cancellation = serializers.SerializerMethodField()
    ticket_code = serializers.SerializerMethodField()
    state = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = ["id", "reference", "status", "state", "event", "show", "seats", "concessions", "subtotal", "convenience_fee",
                  "concessions_total", "tax", "discount", "offer_title", "total", "currency", "payments", "can_cancel", "cancellation",
                  "ticket_code", "checked_in_at", "created_at", "cancelled_at"]

    def get_seats(self, b):
        return BookedSeatSerializer(b.seats.all(), many=True).data

    def get_can_cancel(self, b) -> bool:
        return can_cancel(b)

    def get_cancellation(self, b):
        return cancellation_terms(b) if b.status == Booking.Status.CONFIRMED else None

    def get_state(self, b) -> str:
        """upcoming | completed | cancelled (for My Tickets)."""
        from datetime import timedelta

        from django.utils import timezone

        if b.status == Booking.Status.CANCELLED:
            return "cancelled"
        end = b.show.starts_at + timedelta(minutes=b.show.event.duration_minutes or 150)
        return "completed" if end < timezone.now() else "upcoming"

    def get_ticket_code(self, b):
        from .engagement import ticket_code

        return ticket_code(b) if self.get_state(b) == "upcoming" else None


class ConcessionInputSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=0, max_value=MAX_CONCESSION_QTY)


PAYMENT_CHOICES = [PaymentMethod.PAY_AT_VENUE, PaymentMethod.WALLET]


class CreateBookingSerializer(serializers.Serializer):
    """Book from a seat hold (Showtime) or, for older clients, from a show and seat labels."""

    hold_id = serializers.UUIDField(required=False)
    show_id = serializers.UUIDField(required=False)
    seats = serializers.ListField(child=serializers.CharField(max_length=4), min_length=1, max_length=MAX_SEATS, required=False)
    concessions = ConcessionInputSerializer(many=True, required=False, default=list)
    offer_id = serializers.UUIDField(required=False, allow_null=True)
    payment_method = serializers.ChoiceField(choices=PAYMENT_CHOICES)
    idempotency_key = serializers.UUIDField()

    def validate(self, attrs):
        if not attrs.get("hold_id") and not (attrs.get("show_id") and attrs.get("seats")):
            raise serializers.ValidationError("Give a seat hold, or a show and seats.")
        return attrs


class HoldInputSerializer(serializers.Serializer):
    show_id = serializers.UUIDField()
    seats = serializers.ListField(child=serializers.CharField(max_length=4), min_length=1, max_length=MAX_SEATS)


class QuoteInputSerializer(serializers.Serializer):
    hold_id = serializers.UUIDField()
    concessions = ConcessionInputSerializer(many=True, required=False, default=list)
    offer_id = serializers.UUIDField(required=False, allow_null=True)
    payment_method = serializers.ChoiceField(choices=PAYMENT_CHOICES, required=False, allow_null=True)


class ReviewInputSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    body = serializers.CharField(max_length=1500, required=False, allow_blank=True, default="")
