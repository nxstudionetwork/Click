from django.db.models import Count, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.permissions import IsCustomer

from . import services
from .models import Booking, Event, Show
from .serializers import BookingSerializer, CreateBookingSerializer, EventSerializer, SeatMapSerializer, ShowSerializer

PUBLIC_STATUSES = [Event.Status.NOW_SHOWING, Event.Status.COMING_SOON]


def public_events():
    next_show = services.bookable_shows().filter(event=OuterRef("pk")).order_by("starts_at").values("starts_at")[:1]
    return Event.objects.filter(status__in=PUBLIC_STATUSES).annotate(next_show_at=Subquery(next_show))


class EventListView(generics.ListAPIView):
    """GET /api/v1/events?kind=movie&status=now_showing&city=Bengaluru&search=..."""

    serializer_class = EventSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = public_events()
        p = self.request.query_params
        if (kind := p.get("kind")) in Event.Kind.values:
            qs = qs.filter(kind=kind)
        if (st := p.get("status")) in PUBLIC_STATUSES:
            qs = qs.filter(status=st)
        if city := p.get("city"):
            qs = qs.filter(shows__venue__city__iexact=city, shows__starts_at__gt=timezone.now()).distinct()
        if search := p.get("search", "").strip()[:100]:
            qs = qs.filter(Q(title__icontains=search) | Q(genres__icontains=search) | Q(cast__icontains=search))
        return qs


class EventDetailView(APIView):
    """GET /api/v1/events/<slug> -> event + upcoming bookable shows (with seats left)."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        event = get_object_or_404(public_events(), slug=slug)
        shows = (
            services.bookable_shows().filter(event=event)
            .annotate(sold=Count("booked_seats", filter=Q(booked_seats__is_active=True)))
            .order_by("starts_at")
        )
        if city := request.query_params.get("city"):
            shows = shows.filter(venue__city__iexact=city)
        show_data = []
        for s in shows[:200]:
            s.seats_left = s.rows * s.seats_per_row - s.sold
            show_data.append(ShowSerializer(s).data)
        return Response({**EventSerializer(event).data, "shows": show_data})


class ShowSeatMapView(generics.RetrieveAPIView):
    serializer_class = SeatMapSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return services.bookable_shows()


def customer_bookings(request):
    return (Booking.objects.filter(customer=request.user.customer_profile)
            .select_related("show__event", "show__venue").prefetch_related("seats", "payments"))


class BookingListCreateView(generics.ListAPIView):
    permission_classes = [IsCustomer]
    serializer_class = BookingSerializer

    def get_throttles(self):
        self.throttle_scope = "order_placement" if self.request.method == "POST" else None
        return super().get_throttles()

    def get_queryset(self):
        qs = customer_bookings(self.request)
        when = self.request.query_params.get("when")
        if when == "upcoming":
            qs = qs.filter(status=Booking.Status.CONFIRMED, show__starts_at__gte=timezone.now()).order_by("show__starts_at")
        elif when == "past":
            qs = qs.filter(Q(show__starts_at__lt=timezone.now()) | Q(status=Booking.Status.CANCELLED))
        return qs

    def post(self, request):
        s = CreateBookingSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        booking, created = services.create_booking(customer=request.user.customer_profile, **s.validated_data)
        return Response(BookingSerializer(customer_bookings(request).get(pk=booking.pk)).data,
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class BookingDetailView(generics.RetrieveAPIView):
    permission_classes = [IsCustomer]
    serializer_class = BookingSerializer

    def get_queryset(self):
        return customer_bookings(self.request)


class BookingCancelView(APIView):
    permission_classes = [IsCustomer]

    def post(self, request, pk):
        booking = get_object_or_404(customer_bookings(request), pk=pk)
        services.cancel_booking(booking)
        return Response(BookingSerializer(customer_bookings(request).get(pk=pk)).data)
