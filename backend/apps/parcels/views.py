"""Click. Parcel API. Options are public; everything about a parcel is scoped to its customer (others get 404)."""

from __future__ import annotations

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import DomainError
from apps.core.api.permissions import IsCustomer

from . import pricing, services
from .models import ACTIVE_STATUSES, ParcelCategory, ParcelOrder, ParcelRule, ParcelService, ParcelStatus, ParcelVehicle, SavedRecipient
from .serializers import BookInput, QuoteInput, RecipientSerializer, parcel_detail, parcel_summary, shared_view


def _owned(request):
    return (ParcelOrder.objects.filter(customer=request.user.customer_profile)
            .select_related("service", "vehicle", "category", "partner__profile", "store")
            .prefetch_related("stops", "events", "proofs", "payments", "support_tickets"))


class OptionsView(APIView):
    """GET /parcels/options?lat&lng — services, vehicles (with configured capacities), contents, sizes, rules, coverage."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        area = None
        try:
            point = (float(request.query_params["lat"]), float(request.query_params["lng"]))
            area = pricing.area_for(point)
            located = True
        except (KeyError, ValueError):
            located = False
        services_ = ParcelService.objects.filter(is_active=True).prefetch_related("vehicles")
        return Response({
            "coverage": {"checked": located, "available": area is not None, "area": area.name if area else None},
            "services": [{"code": s.code, "name": s.name, "description": s.description, "allow_stops": s.allow_stops,
                          "max_stops": s.max_stops, "cash_allowed": s.cash_allowed, "cancellation_fee": f"{s.cancellation_fee:.2f}",
                          "max_distance_km": f"{s.max_distance_km:.0f}", "hours": f"{s.open_hour}:00–{s.close_hour}:00",
                          "vehicles": [v.code for v in s.vehicles.all() if v.is_active]} for s in services_],
            "vehicles": [{"code": v.code, "name": v.name, "description": v.description, "icon": v.icon,
                          "capacity": {"max_kg": f"{v.max_weight_kg:.0f}", "max_cm": [v.max_length_cm, v.max_width_cm, v.max_height_cm]}}
                         for v in ParcelVehicle.objects.filter(is_active=True)],
            "categories": [{"code": c.code, "label": c.label, "icon": c.icon, "requires_value": c.requires_value,
                            "allowed": c.is_allowed, "note": c.note} for c in ParcelCategory.objects.all()],
            "sizes": [{"code": k, **{x: v[x] for x in ("label", "hint", "max_kg")}, "dims": v["dims"]} for k, v in pricing.SIZES.items()],
            "rules": [{"kind": r.kind, "text": r.text, "service": r.service.code if r.service_id else None}
                      for r in ParcelRule.objects.filter(is_active=True).select_related("service")],
        })


class QuoteView(APIView):
    permission_classes = [IsCustomer]
    throttle_scope = "quote"

    def post(self, request):
        s = QuoteInput(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(services.quote(s.validated_data))


class ParcelListCreateView(APIView):
    """GET /customer/parcels?when=active|past ; POST books (server re-prices, checks the expected total)."""

    permission_classes = [IsCustomer]
    throttle_scope = "order_placement"

    def get(self, request):
        services.dispatch_due()
        qs = _owned(request)
        when = request.query_params.get("when")
        if when == "active":
            qs = qs.filter(status__in=[*ACTIVE_STATUSES, ParcelStatus.SCHEDULED])
        elif when == "past":
            qs = qs.exclude(status__in=[*ACTIVE_STATUSES, ParcelStatus.SCHEDULED])
        return Response({"results": [parcel_summary(p) for p in qs[:50]]})

    def post(self, request):
        s = BookInput(data=request.data)
        s.is_valid(raise_exception=True)
        parcel, created = services.book(request.user.customer_profile, s.validated_data)
        return Response(parcel_detail(_owned(request).get(pk=parcel.pk)), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class ParcelDetailView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request, pk):
        services.dispatch_due()
        return Response(parcel_detail(get_object_or_404(_owned(request), pk=pk)))


class ParcelTrackView(APIView):
    """GET /customer/parcels/track?ref=PCL-XXXX — only the caller's own parcels (anything else is not found)."""

    permission_classes = [IsCustomer]

    def get(self, request):
        ref = request.query_params.get("ref", "").strip().upper()
        p = _owned(request).filter(number=ref).first()
        if p is None:
            raise DomainError("No parcel with that ID in your account.", code="not_found", status_code=404)
        return Response({"id": str(p.id), "number": p.number})


class CancelInput(serializers.Serializer):
    reason = serializers.CharField(max_length=200)


class ParcelCancelView(APIView):
    permission_classes = [IsCustomer]

    def post(self, request, pk):
        s = CancelInput(data=request.data)
        s.is_valid(raise_exception=True)
        p = get_object_or_404(_owned(request), pk=pk)
        services.cancel_by_customer(p, s.validated_data["reason"], request.user)
        return Response(parcel_detail(_owned(request).get(pk=pk)))


class ParcelRepeatView(APIView):
    """GET /customer/parcels/<id>/repeat — the old booking as a new draft (re-quoted and re-checked before booking)."""

    permission_classes = [IsCustomer]

    def get(self, request, pk):
        p = get_object_or_404(_owned(request), pk=pk)
        place = lambda label, addr, lat, lng, name, phone, ins: {"label": label, "address": addr, "lat": float(lat), "lng": float(lng),  # noqa: E731
                                                                 "name": name, "phone": phone, "instructions": ins}
        return Response({
            "mode": p.mode, "repeat_of": str(p.id), "store_id": str(p.store_id) if p.store_id else None,
            "pickup": place(p.pickup_label, p.pickup_address, p.pickup_lat, p.pickup_lng, p.pickup_name, p.pickup_phone, p.pickup_instructions),
            "drop": {**place(p.drop_label, p.drop_address, p.drop_lat, p.drop_lng, p.drop_name, p.drop_phone, p.drop_instructions),
                     "alt_phone": p.drop_alt_phone},
            "stops": [place(s.label, s.address, s.lat, s.lng, s.contact_name, s.contact_phone, s.instructions) for s in p.stops.all()],
            "package": {"category": p.category.code, "size": p.size, "weight_kg": f"{p.weight_kg}", "length_cm": p.length_cm,
                        "width_cm": p.width_cm, "height_cm": p.height_cm,
                        "declared_value": f"{p.declared_value}" if p.declared_value is not None else None, "notes": p.package_notes},
            "service": p.service.code, "vehicle": p.vehicle.code,
        })


class ParcelShareView(APIView):
    """POST /customer/parcels/<id>/share — a signed link (7 days) showing status only, no phones, PINs or prices."""

    permission_classes = [IsCustomer]

    def post(self, request, pk):
        p = get_object_or_404(_owned(request), pk=pk)
        return Response({"token": services.share_token(p), "expires_in_days": 7})


class SharedTrackingView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, token):
        p = services.from_share_token(token)
        if p is None:
            raise DomainError("This tracking link is invalid or has expired.", code="not_found", status_code=404)
        return Response(shared_view(p))


class RecipientListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsCustomer]
    serializer_class = RecipientSerializer
    pagination_class = None

    def get_queryset(self):
        qs = SavedRecipient.objects.filter(customer=self.request.user.customer_profile)
        if q := self.request.query_params.get("q", "").strip()[:60]:
            qs = qs.filter(Q(name__icontains=q) | Q(label__icontains=q) | Q(phone__icontains=q))
        return qs[:30]

    def perform_create(self, serializer):
        if SavedRecipient.objects.filter(customer=self.request.user.customer_profile).count() >= 50:
            raise DomainError("You can save up to 50 recipients.", code="limit_reached")
        serializer.save(customer=self.request.user.customer_profile)


class RecipientDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsCustomer]
    serializer_class = RecipientSerializer

    def get_queryset(self):
        return SavedRecipient.objects.filter(customer=self.request.user.customer_profile)
