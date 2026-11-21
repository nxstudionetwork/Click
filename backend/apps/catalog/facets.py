"""
Category-aware filters for the service pages (Food, Groceries, Shop, Pharma).

GET /api/v1/catalog/facets?type=restaurant&category=bakery
  -> {"sections": [{"name": "Cakes", "count": 12}, ...], "price_bands": [{"max": 200, "label": "Under ₹200", "count": 9}],
      "veg": true, "items": 41}
GET /api/v1/catalog/dishes?type=restaurant&category=bakery&section=Cakes&max_price=200&veg=1
  -> {"results": [product with store, ...]}

Everything is computed from the live menus of the stores in that category, so Bakery offers "Cakes, Breads, Under
₹200" and Biryani offers "Biryani, Kebabs, Under ₹300" — never a filter that would return nothing.
"""

from collections import Counter

from django.db.models import Q
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import DomainError
from apps.stores.models import StoreType

from .serializers import ProductWithStoreSerializer
from .views import public_products

BAND_CANDIDATES = [100, 150, 200, 300, 500, 1000, 2000]
MAX_SECTIONS = 8


def _products(params):
    store_type = params.get("type", "")
    if store_type not in StoreType.values:
        raise DomainError("Unknown service.", code="invalid_type")
    qs = public_products().filter(store__store_type=store_type, is_available=True)
    category = params.get("category", "").strip()[:60]
    if category:
        qs = qs.filter(store__categories__slug=category)
    return qs.distinct()


class FacetsView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        qs = _products(request.query_params)
        rows = list(qs.values_list("category__name", "price", "dietary"))
        sections = Counter(name.strip() for name, _, _ in rows if name and name.strip())
        prices = sorted(float(p) for _, p, _ in rows)
        bands = []
        for cap in BAND_CANDIDATES:
            n = sum(1 for p in prices if p <= cap)
            # A band is useful only when it narrows the list and still leaves a few items.
            if 3 <= n < len(prices) and (not bands or n > bands[-1]["count"]):
                bands.append({"max": cap, "label": f"Under ₹{cap:,}", "count": n})
            if len(bands) == 3:
                break
        veg = any(d in ("veg", "vegan") for _, _, d in rows)
        return Response({
            "sections": [{"name": n, "count": c} for n, c in sections.most_common(MAX_SECTIONS) if c >= 1],
            "price_bands": bands, "veg": veg, "items": len(rows),
        })


class DishesView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        p = request.query_params
        qs = _products(p)
        if p.get("section"):
            qs = qs.filter(category__name__iexact=p["section"].strip()[:80])
        if p.get("max_price"):
            try:
                qs = qs.filter(price__lte=float(p["max_price"]))
            except ValueError:
                raise DomainError("max_price must be a number.", code="invalid_price")
        if p.get("veg") in ("1", "true"):
            qs = qs.filter(Q(dietary="veg") | Q(dietary="vegan"))
        qs = qs.select_related("store").order_by("-is_featured", "price")[:24]
        return Response({"results": ProductWithStoreSerializer(qs, many=True).data})
