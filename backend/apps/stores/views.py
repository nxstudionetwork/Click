from django.db.models import Prefetch, Q
from django.utils import timezone
from rest_framework import generics, permissions
from rest_framework.response import Response

from apps.core.api.permissions import IsCustomer

from .geo import NearQuerySerializer, with_distance
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


SORTS = {
    "popular": ("-rating_count", "-rating_average", "name"),
    "rating": ("-rating_average", "-rating_count", "name"),
    "new": ("-created_at", "name"),
    "eta": ("delivery_time_min", "delivery_time_max", "-rating_average"),
    "price_low": ("price_level", "-rating_average", "name"),
    "price_high": ("-price_level", "-rating_average", "name"),
}


class StoreListView(generics.ListAPIView):
    """GET /api/v1/stores?type=restaurant&category=pizza&search=...

    Location: `lat`, `lng` (and optional `radius` km, default 10) return only stores with known coordinates
    inside the radius, each with `distanceKm`, nearest first.
    Filters: `veg=true` (no non-vegetarian items), `min_rating=4`, `offers=true` (has a live offer),
    `max_price=1..4` (price level). Sort: `popular|rating|new|eta|price_low|price_high|distance`.
    """

    serializer_class = StoreSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = public_stores()
        params = self.request.query_params
        near = None
        if "lat" in params or "lng" in params:
            s = NearQuerySerializer(data=params)
            s.is_valid(raise_exception=True)
            near = s.validated_data
            qs = with_distance(qs, near["lat"], near["lng"]).filter(distance_km__lte=near["radius"])
        sort = params.get("sort")
        if sort in SORTS:
            qs = qs.order_by(*SORTS[sort])
        elif near and sort in (None, "", "distance"):
            qs = qs.order_by("distance_km", "name")
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
        if params.get("veg") == "true":
            from apps.catalog.models import Product

            qs = qs.exclude(pk__in=Product.objects.filter(dietary="non_veg", is_active=True).values("store_id"))
        if (min_rating := _number(params.get("min_rating"), 0, 5)) is not None:
            qs = qs.filter(rating_average__gte=min_rating)
        if (max_price := _number(params.get("max_price"), 1, 4)) is not None:
            qs = qs.filter(price_level__lte=max_price)
        if params.get("offers") == "true":
            qs = qs.filter(offers__in=active_offers())
        return qs.distinct()


def _number(raw, lo, hi):
    """A query number within [lo, hi], or None when absent or invalid (invalid filters are ignored, not guessed)."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    return v if lo <= v <= hi else None


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


class RecommendedStoresView(generics.GenericAPIView):
    """GET /customer/recommendations/stores?type=restaurant[&lat&lng&radius] — rule-based picks with a reason each."""

    permission_classes = [IsCustomer]

    def get(self, request):
        from .recommendations import recommend_stores

        store_type = request.query_params.get("type", StoreType.RESTAURANT)
        if store_type not in StoreType.values:
            store_type = StoreType.RESTAURANT
        near = None
        if "lat" in request.query_params or "lng" in request.query_params:
            s = NearQuerySerializer(data=request.query_params)
            s.is_valid(raise_exception=True)
            near = s.validated_data
        picks = recommend_stores(request.user.customer_profile, store_type, limit=10, near=near)
        ctx = self.get_serializer_context()
        return Response({"results": [{"store": StoreSerializer(p["store"], context=ctx).data, "reason": p["reason"]} for p in picks]})
