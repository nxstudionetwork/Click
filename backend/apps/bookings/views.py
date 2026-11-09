from django.db.models import Count, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import DomainError
from apps.core.api.permissions import IsCustomer

from . import engagement, services, showtime
from .models import Booking, ConcessionItem, Event, ShowReview
from .serializers import (BookingSerializer, CreateBookingSerializer, EventSerializer, HoldInputSerializer, QuoteInputSerializer,
                          ReviewInputSerializer, ShowSerializer)

PUBLIC_STATUSES = [Event.Status.NOW_SHOWING, Event.Status.COMING_SOON]


def public_events():
    next_show = services.bookable_shows().filter(event=OuterRef("pk")).order_by("starts_at").values("starts_at")[:1]
    return Event.objects.filter(status__in=PUBLIC_STATUSES).annotate(next_show_at=Subquery(next_show))


# --- legacy event endpoints (kept for existing clients and Buddy) --------------------------------------------

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
        shows = services.bookable_shows().filter(event=event).order_by("starts_at")
        if city := request.query_params.get("city"):
            shows = shows.filter(venue__city__iexact=city)
        shows = list(shows[:200])
        booked, held = showtime._seat_counts([s.id for s in shows])
        data = []
        for s in shows:
            s.seats_left = max(s.capacity - booked.get(s.id, 0) - held.get(s.id, 0), 0)
            data.append(ShowSerializer(s).data)
        return Response({**EventSerializer(event).data, "shows": data})


# --- Showtime discovery (public; personal touches when signed in) --------------------------------------------

class Public(APIView):
    permission_classes = [permissions.AllowAny]


class ShowtimeHomeView(Public):
    """GET /showtime/home?lat=&lng= -> featured, highlights and only the sections with real content."""

    def get(self, request):
        lat, lng = showtime._coords(request.query_params)
        return Response(showtime.home(request, lat, lng))


class ShowtimeSearchView(Public):
    throttle_scope = "search"

    def get(self, request):
        return Response(showtime.search(request.query_params, request))


class ShowtimeSuggestView(Public):
    def get(self, request):
        return Response(showtime.suggest(request.query_params.get("q", "")))


class ShowtimeCinemasView(Public):
    def get(self, request):
        lat, lng = showtime._coords(request.query_params)
        return Response({"results": showtime.cinemas_near(lat, lng, limit=50), "location_used": lat is not None})


class ShowtimeTitleView(Public):
    """GET /showtime/titles/<slug>?date=&format=&language=&lat=&lng= (only that day's showtimes are loaded)."""

    def get(self, request, slug):
        return Response(showtime.title_detail(slug, request, request.query_params))


class ShowtimeReviewsView(Public):
    PAGE = 10

    def get(self, request, slug):
        event = get_object_or_404(showtime.public_titles(), slug=slug)
        qs = ShowReview.objects.filter(event=event, status=ShowReview.Status.PUBLISHED).select_related("customer__user")
        page = int(request.query_params.get("page", "1")) if str(request.query_params.get("page", "1")).isdigit() else 1
        total = qs.count()
        items = qs[(page - 1) * self.PAGE: page * self.PAGE]
        return Response({"results": [showtime.review_card(r) for r in items], "count": total, "page": page, "has_more": page * self.PAGE < total})


class ShowSeatMapView(APIView):
    """GET /shows/<id> -> the screen's real seat layout with live states (booked, held, yours, unavailable)."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, pk):
        return Response(showtime.seat_map(pk, showtime.customer_of(request)))


# --- customer: holds, quote, booking -------------------------------------------------------------------------

def hold_payload(hold) -> dict:
    return {"id": str(hold.id), "show_id": str(hold.show_id), "expires_at": hold.expires_at.isoformat(),
            "seats": [{"label": s.label, "tier": s.tier, "price": f"{s.price:.2f}"} for s in hold.seats.all()]}


class HoldsView(APIView):
    """POST /customer/showtime/holds {showId, seats} -> seats held for a few minutes (replaces your earlier hold)."""

    permission_classes = [IsCustomer]

    def post(self, request):
        s = HoldInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        hold = services.create_hold(customer=request.user.customer_profile, **s.validated_data)
        hold = services.active_hold(request.user.customer_profile, hold.id)
        return Response(hold_payload(hold), status=status.HTTP_201_CREATED)


class HoldDetailView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request, pk):
        return Response(hold_payload(services.active_hold(request.user.customer_profile, pk)))

    def delete(self, request, pk):
        services.release_hold(request.user.customer_profile, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


def money(v) -> str:
    return f"{v:.2f}"


class QuoteView(APIView):
    """
    POST /customer/showtime/quote {holdId, concessions?, offerId?, paymentMethod?} -> the bill the server will charge,
    the venue's food & drinks menu and offers (each with whether it applies and why not).
    """

    permission_classes = [IsCustomer]

    def post(self, request):
        s = QuoteInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        hold = services.active_hold(request.user.customer_profile, d["hold_id"])
        show = hold.show
        seats = services.hold_seats(hold)
        concessions = services.resolve_concessions(show, [{"id": c["id"], "quantity": c["quantity"]} for c in d["concessions"]])
        from .models import ShowOffer

        offer = ShowOffer.objects.filter(pk=d.get("offer_id")).first() if d.get("offer_id") else None
        q = services.quote(show, seats, concessions, offer=offer, payment_method=d.get("payment_method"))
        tickets = q.tickets
        offers = []
        for o in services.active_offers(show).select_related("venue"):
            problem = services.offer_problem(o, show, tickets, len(seats), d.get("payment_method"))
            offers.append({"id": str(o.id), "title": o.title, "description": o.description, "payment_method": o.payment_method,
                           "problem": problem, "saving": None if problem else money(services.offer_discount(o, tickets))})
        menu = [{"id": str(i.id), "name": i.name, "description": i.description, "category": i.category, "category_label": i.get_category_display(),
                 "price": money(i.price), "is_veg": i.is_veg, "image_url": i.image_url}
                for i in ConcessionItem.objects.filter(venue=show.venue, is_available=True)]
        return Response({
            "hold": hold_payload(hold),
            "lines": {"tickets": money(q.tickets), "convenience_fee": money(q.convenience_fee), "concessions": money(q.concessions_total),
                      "tax": money(q.tax), "discount": money(q.discount), "total": money(q.total)},
            "offer": {"id": str(q.offer.id), "title": q.offer.title} if q.offer else None,
            "offer_problem": services.offer_problem(offer, show, tickets, len(seats), d.get("payment_method")) if offer and not q.offer else None,
            "concessions": [{"id": str(i.id), "name": i.name, "quantity": n, "line_total": money(lt)} for i, n, lt in q.concessions],
            "menu": menu, "offers": offers, "currency": show.currency,
        })


def customer_bookings(request):
    return (Booking.objects.filter(customer=request.user.customer_profile)
            .select_related("show__event", "show__venue", "show__screen_ref").prefetch_related("seats", "payments", "concessions"))


class BookingListCreateView(generics.ListAPIView):
    """GET /customer/bookings?when=upcoming|past|cancelled (My Tickets); POST books from a hold."""

    permission_classes = [IsCustomer]
    serializer_class = BookingSerializer

    def get_throttles(self):
        self.throttle_scope = "order_placement" if self.request.method == "POST" else None
        return super().get_throttles()

    def get_queryset(self):
        qs = customer_bookings(self.request)
        when = self.request.query_params.get("when")
        now = timezone.now()
        if when == "upcoming":
            qs = qs.filter(status=Booking.Status.CONFIRMED, show__starts_at__gte=now - timezone.timedelta(hours=3)).order_by("show__starts_at")
        elif when == "past":
            qs = qs.filter(Q(show__starts_at__lt=now) | Q(status=Booking.Status.CANCELLED))
        elif when == "completed":
            qs = qs.filter(status=Booking.Status.CONFIRMED, show__starts_at__lt=now).order_by("-show__starts_at")
        elif when == "cancelled":
            qs = qs.filter(status=Booking.Status.CANCELLED)
        return qs

    def post(self, request):
        s = CreateBookingSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = dict(s.validated_data)
        d["concessions"] = [{"id": c["id"], "quantity": c["quantity"]} for c in d.get("concessions", [])]
        booking, created = services.create_booking(customer=request.user.customer_profile, **d)
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


# --- customer: interest and reviews --------------------------------------------------------------------------

class InterestView(APIView):
    """POST/DELETE /customer/showtime/titles/<slug>/interest ("I'm interested": one notification when booking opens)."""

    permission_classes = [IsCustomer]

    def _event(self, slug):
        return get_object_or_404(showtime.public_titles(), slug=slug)

    def post(self, request, slug):
        event = self._event(slug)
        engagement.set_interest(request.user.customer_profile, event, True)
        return Response({"interested": True, "interest_count": event.interests.count()}, status=status.HTTP_201_CREATED)

    def delete(self, request, slug):
        event = self._event(slug)
        engagement.set_interest(request.user.customer_profile, event, False)
        return Response({"interested": False, "interest_count": event.interests.count()})


class MyReviewView(APIView):
    permission_classes = [IsCustomer]

    def _save(self, request, slug, create):
        event = get_object_or_404(showtime.public_titles(), slug=slug)
        s = ReviewInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        r = engagement.save_review(request.user.customer_profile, event, create=create, **s.validated_data)
        r = ShowReview.objects.select_related("customer__user").get(pk=r.pk)
        return Response(showtime.review_card(r), status=status.HTTP_201_CREATED if create else status.HTTP_200_OK)

    def post(self, request, slug):
        return self._save(request, slug, True)

    def patch(self, request, slug):
        return self._save(request, slug, False)

    def delete(self, request, slug):
        engagement.delete_review(request.user.customer_profile, get_object_or_404(showtime.public_titles(), slug=slug))
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- partner: ticket check-in --------------------------------------------------------------------------------

class TicketVerifyView(APIView):
    """POST /partner/tickets/verify {code}: the operating venue scans a Click. ticket (first scan checks it in)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from apps.partners.services import require_owned_partner

        code = str(request.data.get("code", ""))[:600]
        if not code:
            raise DomainError("Scan or enter a ticket code.", code="code_required")
        return Response(engagement.verify_ticket(code, require_owned_partner(request.user)))
