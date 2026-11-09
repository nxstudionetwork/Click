from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.activity.services import record
from apps.catalog.serializers import ProductWithStoreSerializer
from apps.catalog.views import public_products
from apps.core.api.permissions import IsCustomer
from apps.stores.serializers import StoreSerializer
from apps.stores.views import public_stores

from .models import WishlistItem


class WishlistItemSerializer(serializers.ModelSerializer):
    kind = serializers.SerializerMethodField()
    store = StoreSerializer(read_only=True)
    product = ProductWithStoreSerializer(read_only=True)

    class Meta:
        model = WishlistItem
        fields = ["id", "kind", "store", "product", "created_at"]

    def get_kind(self, item) -> str:
        return "store" if item.store_id else "product"


class AddWishlistSerializer(serializers.Serializer):
    store_id = serializers.UUIDField(required=False)
    product_id = serializers.UUIDField(required=False)

    def validate(self, attrs):
        if bool(attrs.get("store_id")) == bool(attrs.get("product_id")):
            raise serializers.ValidationError("Provide exactly one of storeId or productId.")
        return attrs


def _items(customer):
    return (
        WishlistItem.objects.filter(customer=customer)
        .select_related("product__store", "product__category", "store")
        .prefetch_related("store__categories", "store__offers", "product__variants", "product__option_groups__options")
    )


class WishlistView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        return Response(WishlistItemSerializer(_items(request.user.customer_profile), many=True).data)

    def post(self, request):
        s = AddWishlistSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        customer = request.user.customer_profile
        if store_id := s.validated_data.get("store_id"):
            target = {"store": get_object_or_404(public_stores(), pk=store_id)}
        else:
            target = {"product": get_object_or_404(public_products(), pk=s.validated_data["product_id"])}
        item, created = WishlistItem.objects.get_or_create(customer=customer, **target)
        if created:
            record(customer, "wishlist.added", obj=next(iter(target.values())))
        item = _items(customer).get(pk=item.pk)
        return Response(WishlistItemSerializer(item).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class WishlistItemView(APIView):
    permission_classes = [IsCustomer]

    def delete(self, request, pk):
        get_object_or_404(WishlistItem, pk=pk, customer=request.user.customer_profile).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
