from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.carts.serializers import CartSerializer
from apps.core.api.permissions import IsCustomer
from apps.stores.models import StoreType

from . import services
from .models import Order
from .serializers import CancelOrderSerializer, OrderDetailSerializer, OrderSummarySerializer, PlaceOrderSerializer


def customer_orders(request):
    # Ownership isolation for every customer order endpoint.
    return Order.objects.filter(customer=request.user.customer_profile).select_related("store")


class OrderListCreateView(generics.ListAPIView):
    permission_classes = [IsCustomer]
    serializer_class = OrderSummarySerializer

    def get_throttles(self):
        self.throttle_scope = "order_placement" if self.request.method == "POST" else None
        return super().get_throttles()

    def get_queryset(self):
        qs = customer_orders(self.request).prefetch_related("items", "payments")
        if (store_type := self.request.query_params.get("type")) in StoreType.values:
            qs = qs.filter(store__store_type=store_type)
        return qs

    def post(self, request):
        s = PlaceOrderSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        order, created = services.place_order(customer=request.user.customer_profile, **s.validated_data)
        order = customer_orders(request).prefetch_related("items", "events", "payments").get(pk=order.pk)
        return Response(OrderDetailSerializer(order).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class OrderDetailView(generics.RetrieveAPIView):
    permission_classes = [IsCustomer]
    serializer_class = OrderDetailSerializer

    def get_queryset(self):
        return customer_orders(self.request).prefetch_related("items", "events", "payments")


class OrderCancelView(APIView):
    permission_classes = [IsCustomer]

    def post(self, request, pk):
        s = CancelOrderSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        order = get_object_or_404(customer_orders(request), pk=pk)
        services.cancel_by_customer(order, user=request.user, reason=s.validated_data["reason"])
        order = customer_orders(request).prefetch_related("items", "events", "payments").get(pk=pk)
        return Response(OrderDetailSerializer(order).data)


class OrderReorderView(APIView):
    """POST /customer/orders/<id>/reorder — replaces the cart with this order's still-available items."""

    permission_classes = [IsCustomer]

    def post(self, request, pk):
        order = get_object_or_404(customer_orders(request), pk=pk)
        cart, skipped = services.reorder(order, customer=request.user.customer_profile)
        return Response({"cart": CartSerializer(cart).data, "skipped": skipped})
