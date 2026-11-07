from rest_framework import serializers

from apps.catalog.serializers import ProductSerializer
from apps.stores.models import Store

from .models import MAX_ITEM_QUANTITY, Cart, CartItem
from .services import compute_totals


class CartStoreSerializer(serializers.ModelSerializer):
    is_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = Store
        fields = ["id", "slug", "name", "image_url", "delivery_fee", "min_order_amount", "currency", "is_open",
                  "delivery_time_min", "delivery_time_max"]


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ["id", "product", "quantity", "note", "line_total"]

    def get_line_total(self, item) -> str:
        return f"{item.product.price * item.quantity:.2f}"


class CartSerializer(serializers.ModelSerializer):
    store = CartStoreSerializer(read_only=True)
    items = serializers.SerializerMethodField()
    totals = serializers.SerializerMethodField()
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ["id", "store", "items", "item_count", "totals"]

    def _items(self, cart: Cart):
        if not hasattr(self, "_cached_items"):
            self._cached_items = list(cart.items.select_related("product").order_by("created_at"))
        return self._cached_items

    def get_items(self, cart):
        return CartItemSerializer(self._items(cart), many=True).data

    def get_item_count(self, cart) -> int:
        return sum(i.quantity for i in self._items(cart))

    def get_totals(self, cart):
        t = compute_totals(cart, self._items(cart))
        return {k: f"{v:.2f}" for k, v in t.__dict__.items()}


class AddCartItemSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, max_value=MAX_ITEM_QUANTITY, default=1)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class UpdateCartItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1, max_value=MAX_ITEM_QUANTITY)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True)
