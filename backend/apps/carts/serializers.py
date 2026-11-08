from rest_framework import serializers

from apps.catalog.serializers import ProductSerializer
from apps.stores.models import Store

from .models import MAX_ITEM_QUANTITY, Cart, CartItem
from .services import compute_totals, offer_discount, offer_problem, unit_price


class CartStoreSerializer(serializers.ModelSerializer):
    is_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = Store
        fields = ["id", "slug", "name", "image_url", "delivery_fee", "min_order_amount", "currency", "is_open",
                  "delivery_time_min", "delivery_time_max"]


class CartItemOptionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    price_delta = serializers.DecimalField(max_digits=10, decimal_places=2)


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    options = CartItemOptionSerializer(many=True, read_only=True)
    unit_price = serializers.SerializerMethodField()
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ["id", "product", "options", "quantity", "note", "unit_price", "line_total"]

    def get_unit_price(self, item) -> str:
        return f"{unit_price(item):.2f}"

    def get_line_total(self, item) -> str:
        return f"{unit_price(item) * item.quantity:.2f}"


class CartOfferSerializer(serializers.Serializer):
    """An offer of the cart's store, with whether it applies right now (decided by the server)."""

    id = serializers.UUIDField()
    title = serializers.CharField()
    description = serializers.CharField()
    min_order_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    ends_at = serializers.DateTimeField(allow_null=True)


class CartSerializer(serializers.ModelSerializer):
    store = CartStoreSerializer(read_only=True)
    items = serializers.SerializerMethodField()
    totals = serializers.SerializerMethodField()
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ["id", "store", "items", "item_count", "totals", "offer", "offers"]

    offer = serializers.SerializerMethodField()
    offers = serializers.SerializerMethodField()

    def _items(self, cart: Cart):
        if not hasattr(self, "_cached_items"):
            self._cached_items = list(
                cart.items.select_related("product").prefetch_related("options", "product__option_groups__options").order_by("created_at")
            )
        return self._cached_items

    def _subtotal(self, cart):
        return compute_totals(cart, self._items(cart)).subtotal

    def get_offer(self, cart):
        """The applied offer and, if it no longer applies (e.g. cart dropped below its minimum), why."""
        if not cart.offer_id:
            return None
        o = cart.offer
        return {**CartOfferSerializer(o).data, "problem": offer_problem(o, cart.store, self._subtotal(cart))}

    def get_offers(self, cart):
        """Redeemable offers of the cart's store, each marked applicable or not (with the reason)."""
        if not cart.store_id or not self._items(cart):
            return []
        from apps.stores.views import active_offers

        subtotal = self._subtotal(cart)
        totals = compute_totals(cart, self._items(cart))
        out = []
        for o in active_offers().filter(store_id=cart.store_id).exclude(discount_type=""):
            problem = offer_problem(o, cart.store, subtotal)
            out.append({**CartOfferSerializer(o).data, "problem": problem,
                        "saving": None if problem else f"{offer_discount(o, subtotal, totals.delivery_fee):.2f}"})
        return out

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
    option_ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list, max_length=20)


class ApplyOfferSerializer(serializers.Serializer):
    offer_id = serializers.UUIDField()


class UpdateCartItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1, max_value=MAX_ITEM_QUANTITY)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True)
