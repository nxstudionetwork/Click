from rest_framework import serializers

from apps.payments.models import PaymentMethod
from apps.payments.serializers import PaymentSerializer

from .models import CUSTOMER_CANCELLABLE, CheckoutGroup, Order, OrderItem, OrderStatusEvent, ReturnRequest
from .returns import return_deadline, return_problem


class ReturnSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    reason_label = serializers.CharField(source="get_reason_display", read_only=True)

    class Meta:
        model = ReturnRequest
        fields = ["id", "kind", "kind_label", "reason", "reason_label", "details", "quantity", "status", "status_label",
                  "refund_amount", "resolution_note", "created_at", "resolved_at"]


class OrderItemSerializer(serializers.ModelSerializer):
    product_id = serializers.UUIDField(read_only=True, allow_null=True)
    variant_id = serializers.UUIDField(read_only=True, allow_null=True)
    returns = ReturnSerializer(many=True, read_only=True)
    return_until = serializers.SerializerMethodField()
    can_return = serializers.SerializerMethodField()
    return_note = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ["id", "product_id", "variant_id", "product_name", "options_summary", "unit_price", "quantity", "line_total", "note",
                  "return_days", "replacement_only", "deal_percent", "returns", "return_until", "can_return", "return_note"]

    def get_return_until(self, item):
        d = return_deadline(item)
        return d.isoformat() if d else None

    def get_can_return(self, item) -> bool:
        return return_problem(item) is None

    def get_return_note(self, item) -> str | None:
        """Why the item can't be returned, only when that's useful to say (returnable items after delivery)."""
        if item.return_days is None:
            return None
        return return_problem(item)


class CheckoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = CheckoutGroup
        fields = ["id", "number", "total", "currency", "created_at"]


class ReturnRequestInputSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=ReturnRequest.Kind.choices)
    reason = serializers.ChoiceField(choices=ReturnRequest.Reason.choices)
    details = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    quantity = serializers.IntegerField(min_value=1, max_value=50, default=1)


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
            "tax", "discount", "offer_title", "estimated_delivery_at", "estimated_delivery_from", "cancelled_at", "delivered_at",
            "can_cancel", "review", "can_review", "checkout", "grocery", "payment_intent",
        ]

    payment_intent = serializers.SerializerMethodField()

    def get_payment_intent(self, order):
        """Online payment state (UPI / card / net banking), read from the payment records — never assumed."""
        from apps.payments.gateway import ONLINE, intent

        p = next((p for p in order.payments.all() if p.method in ONLINE and p.provider_reference), None)
        return intent(p.provider_reference) if p else None

    grocery = serializers.SerializerMethodField()

    def get_grocery(self, order):
        """Groceries: delivery mode/slot, substitution preference and the refund status a cancellation produced."""
        d = getattr(order, "grocery", None) if hasattr(order, "grocery") else None
        if d is None:
            return None
        refunded = [p for p in order.payments.all() if p.status == "refunded"]
        return {
            "delivery_mode": d.delivery_mode, "delivery_mode_label": d.get_delivery_mode_display(),
            "slot_start": d.slot_start.isoformat() if d.slot_start else None, "slot_end": d.slot_end.isoformat() if d.slot_end else None,
            "substitution": d.substitution, "substitution_label": d.get_substitution_display(), "substitution_note": d.substitution_note,
            "distance_km": f"{d.distance_km:.1f}" if d.distance_km is not None else None, "eta_min": d.eta_min, "eta_max": d.eta_max,
            "refund": {"amount": f"{sum(p.amount for p in refunded):.2f}", "to": "Click Wallet", "status": "refunded"} if refunded else None,
            "tracking": "status_only",
        }

    checkout = serializers.SerializerMethodField()

    def get_checkout(self, order):
        c = order.checkout
        return {"id": str(c.id), "number": c.number, "order_count": c.orders.count()} if c else None

    def get_review(self, order):
        r = getattr(order, "review", None) if hasattr(order, "review") else None
        return {"rating": r.rating, "comment": r.comment, "created_at": r.created_at.isoformat()} if r else None

    def get_can_review(self, order) -> bool:
        return order.status == "delivered" and not hasattr(order, "review")

    def get_can_cancel(self, order) -> bool:
        return order.status in CUSTOMER_CANCELLABLE


class PlaceOrderSerializer(serializers.Serializer):
    address_id = serializers.UUIDField()
    payment_method = serializers.ChoiceField(choices=[PaymentMethod.CASH_ON_DELIVERY, PaymentMethod.WALLET, "upi", "card", "netbanking"])
    idempotency_key = serializers.UUIDField()
    customer_note = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class ReviewSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class CancelOrderSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
