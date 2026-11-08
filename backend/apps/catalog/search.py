"""
Global customer search across the Click catalogue.

GET /api/v1/search?q=<text>&scope=all|restaurant|grocery|retail|products|events
-> {"query", "stores": [...], "products": [...], "events": [...]}

Backed by indexed relational queries today; the response shape is stable so
it can move to a dedicated search engine later without frontend changes.
Rides and services join the scopes as those domains launch.
"""

from django.db.models import Q
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import DomainError
from apps.stores.models import StoreType
from apps.stores.serializers import StoreSerializer
from apps.stores.views import public_stores

from .serializers import ProductWithStoreSerializer
from .views import public_products

SCOPES = {"all", "products", "events", *StoreType.values}
LIMIT = 20


class SearchView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        q = request.query_params.get("q", "").strip()[:100]
        scope = request.query_params.get("scope", "all")
        if scope not in SCOPES:
            raise DomainError("Unknown search scope.", code="invalid_scope")
        if len(q) < 2:
            return Response({"query": q, "stores": [], "products": [], "events": []})

        stores, products = [], []
        events = []
        if scope in ("all", "events"):
            from apps.bookings.serializers import EventSerializer
            from apps.bookings.views import public_events

            ev = public_events().filter(Q(title__icontains=q) | Q(genres__icontains=q) | Q(cast__icontains=q))
            events = EventSerializer(ev[:LIMIT], many=True).data
        if scope == "events":
            return Response({"query": q, "stores": [], "products": [], "events": events})
        if scope != "products":
            qs = public_stores().filter(Q(name__icontains=q) | Q(categories__name__icontains=q) | Q(description__icontains=q))
            if scope in StoreType.values:
                qs = qs.filter(store_type=scope)
            stores = StoreSerializer(qs.distinct().order_by("-is_accepting_orders", "-rating_average")[:LIMIT], many=True).data
        product_qs = public_products().filter(Q(name__icontains=q) | Q(brand__icontains=q) | Q(category__name__icontains=q))
        if scope in StoreType.values:
            product_qs = product_qs.filter(store__store_type=scope)
        products = ProductWithStoreSerializer(product_qs.order_by("-is_featured", "name")[:LIMIT], many=True).data
        return Response({"query": q, "stores": stores, "products": products, "events": events})
