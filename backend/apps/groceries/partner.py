"""
Vendor catalogue API (Partner App). A partner manages only the listings of storefronts it operates
(apps.partners.PartnerStore); any other store's listing is a 404. Every change goes through the same Product rows the
Customer App reads, so price, stock and freshness changes show to customers immediately.
"""

from decimal import Decimal

from django.shortcuts import get_object_or_404
from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Product
from apps.core.api.exceptions import DomainError
from apps.stores.models import Store, StoreType

from .catalog import cards


def partner_listings(request):
    from apps.partners.views import _onboarded_partner

    partner = _onboarded_partner(request)
    stores = Store.objects.filter(partner_link__partner=partner, store_type=StoreType.GROCERY)
    return Product.objects.filter(store__in=stores, grocery_item__isnull=False).select_related("store", "grocery_item", "grocery_item__category")


class ListingUpdateSerializer(serializers.Serializer):
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"), required=False)
    mrp = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    stock = serializers.IntegerField(min_value=0, max_value=100000, required=False, allow_null=True)
    is_available = serializers.BooleanField(required=False)
    received_on = serializers.DateField(required=False, allow_null=True)


class PartnerListingsView(APIView):
    """GET /partner/grocery/listings — this partner's grocery listings (own storefronts only)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        rows = partner_listings(request).order_by("grocery_item__category__position", "grocery_item__name")[:500]
        data = cards(rows)
        for d, p in zip(data, rows):
            d["stock"] = p.stock_quantity
        return Response({"results": data})


class PartnerListingDetailView(APIView):
    """PATCH /partner/grocery/listings/<id> {price?, mrp?, stock?, isAvailable?, receivedOn?}"""

    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        p = get_object_or_404(partner_listings(request), pk=pk)
        s = ListingUpdateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        price = v.get("price", p.price)
        mrp = v["mrp"] if "mrp" in v else p.compare_at_price
        if mrp is not None and mrp <= price:
            raise DomainError("MRP must be higher than the selling price (or empty).", code="validation_error",
                              details={"mrp": ["Enter an MRP above the price, or leave it empty."]})
        p.price, p.compare_at_price = price, mrp
        if "stock" in v:
            p.stock_quantity = v["stock"]
        if "is_available" in v:
            p.is_available = v["is_available"]
        if "received_on" in v:
            p.received_on = v["received_on"]
        p.save()
        out = cards([p])[0]
        out["stock"] = p.stock_quantity
        return Response(out)
