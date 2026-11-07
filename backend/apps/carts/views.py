from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.permissions import IsCustomer

from . import services
from .models import Cart, CartItem
from .serializers import AddCartItemSerializer, CartSerializer, UpdateCartItemSerializer


def _cart_response(customer, code=status.HTTP_200_OK):
    cart = Cart.objects.select_related("store").get(pk=services.get_or_create_cart(customer).pk)
    return Response(CartSerializer(cart).data, status=code)


class CartView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        return _cart_response(request.user.customer_profile)

    def delete(self, request):
        services.clear_cart(services.get_or_create_cart(request.user.customer_profile))
        return _cart_response(request.user.customer_profile)


class CartItemsView(APIView):
    permission_classes = [IsCustomer]

    def post(self, request):
        s = AddCartItemSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        customer = request.user.customer_profile
        services.add_item(customer, **s.validated_data)
        return _cart_response(customer, status.HTTP_201_CREATED)


class CartItemDetailView(APIView):
    permission_classes = [IsCustomer]

    def _get_item(self, request, item_id) -> CartItem:
        # Scoped to the requester's cart: other customers' items are a 404.
        return get_object_or_404(CartItem.objects.select_related("cart", "product"), pk=item_id, cart__customer=request.user.customer_profile)

    def patch(self, request, item_id):
        s = UpdateCartItemSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.update_item(self._get_item(request, item_id), **s.validated_data)
        return _cart_response(request.user.customer_profile)

    def delete(self, request, item_id):
        services.remove_item(self._get_item(request, item_id))
        return _cart_response(request.user.customer_profile)
