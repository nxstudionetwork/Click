from rest_framework import serializers

from apps.payments.models import PaymentMethod
from apps.payments.serializers import PaymentSerializer

from .models import CUSTOMER_CANCELLABLE, Order, OrderItem, OrderStatusEvent


class OrderItemSerializer(serializers.ModelSerializer):
    product_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = OrderItem
        fields = ["id", "product_id", "product_name", "options_summary", "unit_price", "quantity", "line_total", "note"]


class OrderStatusEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusEvent
        fields = ["from_status", "to_status", "note", "created_at"]


class OrderStoreSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.SlugField()
    name = serializers.CharField()
    store_type = serializers.CharField()
    image_url = serializers.CharField()


class OrderSummarySerializer(serializers.ModelSerializer):
    store = OrderStoreSerializer(read_only=True)
    item_count = serializers.SerializerMethodField()
    item_names = serializers.SerializerMethodField()
    line_count = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ["id", "number", "status", "store", "total", "currency", "item_count", "item_names", "line_count", "payment_status", "created_at"]

    def get_item_count(self, order) -> int:
        return sum(i.quantity for i in order.items.all())

    def get_item_names(self, order) -> list[str]:
        return [i.product_name for i in order.items.all()][:3]

    def get_line_count(self, order) -> int:
        return len(order.items.all())

    def get_payment_status(self, order) -> str | None:
        payments = list(order.payments.all())
        return payments[0].status if payments else None


class OrderDetailSerializer(OrderSummarySerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    events = OrderStatusEventSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    can_cancel = serializers.SerializerMethodField()
    review = serializers.SerializerMethodField()
    can_review = serializers.SerializerMethodField()

    class Meta(OrderSummarySerializer.Meta):
        fields = OrderSummarySerializer.Meta.fields + [
            "items", "events", "payments", "delivery_address", "customer_note", "subtotal", "delivery_fee",
            "tax", "discount", "offer_title", "estimated_delivery_at", "cancelled_at", "delivered_at", "can_cancel",
            "review", "can_review",
        ]

    def get_review(self, order):
        r = getattr(order, "review", None) if hasattr(order, "review") else None
        return {"rating": r.rating, "comment": r.comment, "created_at": r.created_at.isoformat()} if r else None

    def get_can_review(self, order) -> bool:
        return order.status == "delivered" and not hasattr(order, "review")

    def get_can_cancel(self, order) -> bool:
        return order.status in CUSTOMER_CANCELLABLE


class PlaceOrderSerializer(serializers.Serializer):
    address_id = serializers.UUIDField()
    payment_method = serializers.ChoiceField(choices=[PaymentMethod.CASH_ON_DELIVERY, PaymentMethod.WALLET])
    idempotency_key = serializers.UUIDField()
    customer_note = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class ReviewSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class CancelOrderSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
