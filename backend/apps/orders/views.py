from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.carts.serializers import CartSerializer
from apps.core.api.permissions import IsCustomer
from apps.stores.models import StoreType

from . import services
from . import returns
from .models import CheckoutGroup, Order, OrderItem
from .serializers import (CancelOrderSerializer, CheckoutSerializer, OrderDetailSerializer, OrderSummarySerializer, PlaceOrderSerializer,
                          ReturnRequestInputSerializer, ReviewSerializer)


DETAIL = ("items__returns", "events", "payments")


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
        order = customer_orders(request).prefetch_related(*DETAIL).get(pk=order.pk)
        return Response(OrderDetailSerializer(order).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class OrderDetailView(generics.RetrieveAPIView):
    permission_classes = [IsCustomer]
    serializer_class = OrderDetailSerializer

    def get_queryset(self):
        return customer_orders(self.request).prefetch_related(*DETAIL)


class OrderCancelView(APIView):
    permission_classes = [IsCustomer]

    def post(self, request, pk):
        s = CancelOrderSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        order = get_object_or_404(customer_orders(request), pk=pk)
        services.cancel_by_customer(order, user=request.user, reason=s.validated_data["reason"])
        order = customer_orders(request).prefetch_related(*DETAIL).get(pk=pk)
        return Response(OrderDetailSerializer(order).data)


class OrderReorderView(APIView):
    """POST /customer/orders/<id>/reorder — replaces the cart with this order's still-available items."""

    permission_classes = [IsCustomer]

    def post(self, request, pk):
        order = get_object_or_404(customer_orders(request), pk=pk)
        cart, skipped = services.reorder(order, customer=request.user.customer_profile)
        return Response({"cart": CartSerializer(cart).data, "skipped": skipped})


class OrderReviewView(APIView):
    """POST /customer/orders/<id>/review {rating 1-5, comment} for a delivered order (once)."""

    permission_classes = [IsCustomer]

    def post(self, request, pk):
        order = get_object_or_404(customer_orders(request), pk=pk)
        s = ReviewSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.submit_review(order, customer=request.user.customer_profile, **s.validated_data)
        order.refresh_from_db()
        return Response(OrderDetailSerializer(order).data, status=status.HTTP_201_CREATED)


class CheckoutView(APIView):
    """
    POST /customer/checkout: place the whole cart. A marketplace (Shopping) cart becomes one order per seller under
    one checkout; a food or grocery cart becomes one order. Same body as POST /customer/orders.
    """

    permission_classes = [IsCustomer]
    throttle_scope = "order_placement"

    def post(self, request):
        s = PlaceOrderSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        checkout, orders, created = services.place_checkout(customer=request.user.customer_profile, **s.validated_data)
        orders = customer_orders(request).prefetch_related("items", "payments").filter(pk__in=[o.pk for o in orders]).order_by("created_at")
        data = {"checkout": CheckoutSerializer(checkout).data if checkout else None, "orders": OrderSummarySerializer(orders, many=True).data}
        return Response(data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class CheckoutDetailView(APIView):
    """GET /customer/checkouts/<id>: a marketplace checkout and its per-seller orders (owner only)."""

    permission_classes = [IsCustomer]

    def get(self, request, pk):
        checkout = get_object_or_404(CheckoutGroup, pk=pk, customer=request.user.customer_profile)
        orders = customer_orders(request).prefetch_related("items", "payments").filter(checkout=checkout).order_by("created_at")
        return Response({"checkout": CheckoutSerializer(checkout).data, "orders": OrderSummarySerializer(orders, many=True).data})


class ReturnRequestView(APIView):
    """POST /customer/orders/<id>/items/<item_id>/return {kind, reason, details?, quantity?} (delivered, within window)."""

    permission_classes = [IsCustomer]

    def post(self, request, pk, item_id):
        order = get_object_or_404(customer_orders(request), pk=pk)
        item = get_object_or_404(OrderItem, pk=item_id, order=order)
        s = ReturnRequestInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        returns.request_return(customer=request.user.customer_profile, item=item, **s.validated_data)
        order = customer_orders(request).prefetch_related(*DETAIL).get(pk=pk)
        return Response(OrderDetailSerializer(order).data, status=status.HTTP_201_CREATED)
