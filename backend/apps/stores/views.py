from django.db.models import Prefetch, Q
from django.utils import timezone
from rest_framework import generics, permissions

from .models import Store, StoreCategory, StoreOffer, StoreType
from .serializers import OfferWithStoreSerializer, StoreCategorySerializer, StoreSerializer


def active_offers():
    now = timezone.now()
    return StoreOffer.objects.filter(is_active=True).filter(
        Q(starts_at__isnull=True) | Q(starts_at__lte=now), Q(ends_at__isnull=True) | Q(ends_at__gte=now)
    )


def public_stores():
    return (
        Store.objects.filter(status=Store.Status.ACTIVE)
        .prefetch_related("categories", Prefetch("offers", queryset=active_offers(), to_attr="active_offers"))
    )


class StoreListView(generics.ListAPIView):
    """GET /api/v1/stores?type=restaurant&category=pizza&search=..."""

    serializer_class = StoreSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = public_stores()
        params = self.request.query_params
        store_type = params.get("type")
        if store_type in StoreType.values:
            qs = qs.filter(store_type=store_type)
        if city := params.get("city"):
            qs = qs.filter(city__iexact=city)
        if category := params.get("category"):
            qs = qs.filter(categories__slug=category)
        if search := params.get("search", "").strip()[:100]:
            qs = qs.filter(
                Q(name__icontains=search) | Q(categories__name__icontains=search) | Q(products__name__icontains=search)
            )
        if params.get("open") == "true":
            qs = qs.filter(is_accepting_orders=True)
        return qs.distinct()


class StoreDetailView(generics.RetrieveAPIView):
    serializer_class = StoreSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"

    def get_queryset(self):
        return public_stores()


class StoreCategoryListView(generics.ListAPIView):
    serializer_class = StoreCategorySerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None

    def get_queryset(self):
        qs = StoreCategory.objects.all()
        if (store_type := self.request.query_params.get("type")) in StoreType.values:
            qs = qs.filter(store_type=store_type)
        return qs


class OfferListView(generics.ListAPIView):
    """GET /api/v1/offers?type=restaurant — active offers at active stores."""

    serializer_class = OfferWithStoreSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = active_offers().filter(store__status=Store.Status.ACTIVE).select_related("store")
        if (store_type := self.request.query_params.get("type")) in StoreType.values:
            qs = qs.filter(store__store_type=store_type)
        return qs.order_by("-store__is_accepting_orders", "-created_at")
