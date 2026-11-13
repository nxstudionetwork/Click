from rest_framework import serializers

from apps.catalog.serializers import ProductSerializer
from apps.stores.models import Store

from .models import MAX_ITEM_QUANTITY, Cart, CartItem
from .services import cart_items, compute_totals, offer_discount, offer_problem, seller_groups, unit_price


class CartStoreSerializer(serializers.ModelSerializer):
    is_open = serializers.BooleanField(read_only=True)
    is_verified = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = ["id", "slug", "name", "image_url", "store_type", "delivery_fee", "min_order_amount", "currency", "is_open",
                  "delivery_time_min", "delivery_time_max", "free_delivery_above", "cod_enabled", "is_verified"]

    def get_is_verified(self, s) -> bool:
        return s.verified_at is not None


class CartItemOptionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    price_delta = serializers.DecimalField(max_digits=10, decimal_places=2)


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    options = CartItemOptionSerializer(many=True, read_only=True)
    variant = serializers.SerializerMethodField()
    store_id = serializers.UUIDField(source="product.store_id", read_only=True)
    unit_price = serializers.SerializerMethodField()
    line_total = serializers.SerializerMethodField()
    is_available = serializers.SerializerMethodField()
    price_change = serializers.SerializerMethodField()
    requires_prescription = serializers.BooleanField(source="product.requires_prescription", read_only=True)

    class Meta:
        model = CartItem
        fields = ["id", "product", "store_id", "variant", "options", "quantity", "note", "unit_price", "line_total", "is_available",
                  "price_change", "requires_prescription"]

    def get_variant(self, item):
        v = item.variant
        return {"id": str(v.id), "label": v.label, "options": v.options} if v else None

    def get_is_available(self, item) -> bool:
        ok = item.variant.is_orderable if item.variant else item.product.is_orderable
        return ok and item.product.store.is_open

    def get_price_change(self, item):
        """The live price differs from the one the customer saw when adding: {from, to} until they acknowledge it."""
        from apps.catalog.pricing import price_of

        now = price_of(item.product, item.variant).price
        if item.price_seen is None or now == item.price_seen:
            return None
        return {"from": f"{item.price_seen:.2f}", "to": f"{now:.2f}"}

    def get_unit_price(self, item) -> str:
        return f"{unit_price(item):.2f}"

    def get_line_total(self, item) -> str:
        return f"{unit_price(item) * item.quantity:.2f}"


class CartOfferSerializer(serializers.Serializer):
    """An offer of a seller in the cart, with whether it applies right now (decided by the server)."""

    id = serializers.UUIDField()
    store_id = serializers.UUIDField()
    title = serializers.CharField()
    description = serializers.CharField()
    min_order_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    ends_at = serializers.DateTimeField(allow_null=True)


def _money(v) -> str:
    return f"{v:.2f}"


class CartSerializer(serializers.ModelSerializer):
    """Contract mirrored by `Cart` in packages/api/src/types.ts. `context["address"]` adds delivery estimates."""

    store = CartStoreSerializer(read_only=True)
    items = serializers.SerializerMethodField()
    groups = serializers.SerializerMethodField()
    totals = serializers.SerializerMethodField()
    item_count = serializers.SerializerMethodField()
    offer = serializers.SerializerMethodField()
    offers = serializers.SerializerMethodField()
    prescription = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ["id", "mode", "store", "items", "groups", "item_count", "totals", "offer", "offers", "prescription"]

    def get_prescription(self, cart: Cart):
        """Pharmacy carts: the attached prescription and the customer's prescriptions this pharmacy verified."""
        if not cart.store_id or cart.store.store_type != "pharmacy":
            return None
        from apps.pharma.views import usable

        r = cart.prescription
        u = usable(cart.customer, cart.store_id)
        return {"required": any(i.product.requires_prescription for i in self._items(cart)),
                "attached": {"id": str(r.id), "reference": r.reference, "status": r.status} if r else None,
                "available": {"id": str(u.id), "reference": u.reference} if u else None}

    def _items(self, cart: Cart):
        if not hasattr(self, "_cached_items"):
            self._cached_items = cart_items(cart)
        return self._cached_items

    def _groups(self, cart):
        if not hasattr(self, "_cached_groups"):
            self._cached_groups = seller_groups(cart, self._items(cart)) if self._items(cart) else []
        return self._cached_groups

    def _group_for_store(self, cart, store_id):
        return next((g for g in self._groups(cart) if g.store.id == store_id), None)

    def get_offer(self, cart):
        """The applied offer and, if it no longer applies (e.g. dropped below its minimum), why."""
        if not cart.offer_id:
            return None
        o = cart.offer
        g = self._group_for_store(cart, o.store_id)
        return {**CartOfferSerializer(o).data, "problem": offer_problem(o, g.store if g else None, g.subtotal if g else 0)}

    def get_offers(self, cart):
        """Redeemable offers of the sellers in the cart, each marked applicable or not (with the reason)."""
        from apps.stores.views import active_offers

        out = []
        for g in self._groups(cart):
            for o in active_offers().filter(store_id=g.store.id).exclude(discount_type=""):
                problem = offer_problem(o, g.store, g.subtotal)
                out.append({**CartOfferSerializer(o).data, "problem": problem,
                            "saving": None if problem else _money(offer_discount(o, g.subtotal, g.delivery_fee))})
        return out

    def get_groups(self, cart):
        from apps.shop.delivery import estimate

        address = self.context.get("address")
        out = []
        for g in self._groups(cart):
            est = estimate(g.store, address=address) if address is not None else None
            cod = g.store.cod_enabled and all(i.product.is_cod_available for i in g.items)
            out.append({
                "store": CartStoreSerializer(g.store).data,
                "item_ids": [str(i.id) for i in g.items],
                "subtotal": _money(g.subtotal), "delivery_fee": _money(g.delivery_fee), "tax": _money(g.tax),
                "discount": _money(g.discount), "total": _money(g.total), "offer_title": g.offer.title if g.offer else "",
                "below_minimum": g.subtotal < g.store.min_order_amount,
                "free_delivery_remaining": (_money(g.store.free_delivery_above - g.subtotal)
                                            if g.store.free_delivery_above is not None and g.subtotal < g.store.free_delivery_above else None),
                "cod_available": cod,
                "delivery_estimate": est,
            })
        return out

    def get_items(self, cart):
        return CartItemSerializer(self._items(cart), many=True).data

    def get_item_count(self, cart) -> int:
        return sum(i.quantity for i in self._items(cart))

    def get_totals(self, cart):
        t = compute_totals(cart, self._items(cart))
        return {k: _money(v) for k, v in t.__dict__.items()}


class AddCartItemSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    variant_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    quantity = serializers.IntegerField(min_value=1, max_value=MAX_ITEM_QUANTITY, default=1)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    option_ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list, max_length=20)


class ApplyOfferSerializer(serializers.Serializer):
    offer_id = serializers.UUIDField()


class UpdateCartItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1, max_value=MAX_ITEM_QUANTITY, required=False)
    acknowledge_price = serializers.BooleanField(required=False, default=False, help_text="The customer saw the new price.")
    note = serializers.CharField(max_length=200, required=False, allow_blank=True)
