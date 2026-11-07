from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.stores.models import Store

from .models import MenuCategory, Product
from .serializers import MenuCategorySerializer


class StoreMenuView(APIView):
    """GET /api/v1/stores/<slug>/menu -> {"categories": [{..., "products": [...]}]}"""

    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        store = get_object_or_404(Store, slug=slug, status=Store.Status.ACTIVE)
        visible = Product.objects.filter(is_active=True)
        categories = (
            MenuCategory.objects.filter(store=store, is_active=True)
            .prefetch_related(Prefetch("products", queryset=visible, to_attr="visible_products"))
        )
        data = [c for c in MenuCategorySerializer(categories, many=True).data if c["products"]]
        return Response({"store_id": str(store.id), "categories": data})
