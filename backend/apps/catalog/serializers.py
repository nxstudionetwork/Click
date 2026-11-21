from rest_framework import serializers

from .models import MenuCategory, Product
from .pricing import attach_deals, price_of


LOW_STOCK_THRESHOLD = 5


class ProductOptionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    price_delta = serializers.DecimalField(max_digits=10, decimal_places=2)
    is_available = serializers.BooleanField()


class ProductOptionGroupSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    min_select = serializers.IntegerField()
    max_select = serializers.IntegerField()
    options = serializers.SerializerMethodField()

    def get_options(self, g):
        return ProductOptionSerializer(g.options.all(), many=True).data


class DealAwareListSerializer(serializers.ListSerializer):
    """Loads the active deal of every product in the list with one query before pricing them."""

    def to_representation(self, data):
        items = list(data.all() if hasattr(data, "all") else data)
        attach_deals(items)
        return super().to_representation(items)


class ProductSerializer(serializers.ModelSerializer):
    """Contract mirrored by `Product` in packages/api/src/types.ts. Prices come from apps.catalog.pricing."""

    price = serializers.SerializerMethodField()
    compare_at_price = serializers.SerializerMethodField()

    store_id = serializers.UUIDField(read_only=True)
    category_id = serializers.UUIDField(read_only=True, allow_null=True)
    is_available = serializers.SerializerMethodField()
    discount_percent = serializers.SerializerMethodField()
    low_stock = serializers.SerializerMethodField()
    # Customisation steps (size, add-ons). Empty for products without options. Prefetch `option_groups__options`.
    option_groups = ProductOptionGroupSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "store_id", "category_id", "name", "description", "image_url", "price", "compare_at_price",
            "discount_percent", "brand", "unit_label", "dietary", "is_available", "low_stock", "is_featured",
            "option_groups", "shop_category_id", "has_variants", "requires_prescription", "store_type",
        ]
        list_serializer_class = DealAwareListSerializer

    shop_category_id = serializers.UUIDField(read_only=True, allow_null=True)
    store_type = serializers.CharField(source="store.store_type", read_only=True)
    has_variants = serializers.SerializerMethodField()

    def get_has_variants(self, p) -> bool:
        return any(v.is_active for v in p.variants.all())

    def get_price(self, p) -> str:
        return f"{price_of(p).price:.2f}"

    def get_compare_at_price(self, p) -> str | None:
        ref = price_of(p).reference
        return f"{ref:.2f}" if ref else None

    def get_is_available(self, p) -> bool:
        return p.is_available and p.in_stock

    def get_discount_percent(self, p) -> int | None:
        return price_of(p).discount_percent

    def get_low_stock(self, p) -> bool:
        # Exact stock counts are not exposed to customers, only a scarcity hint.
        return p.stock_quantity is not None and 0 < p.stock_quantity <= LOW_STOCK_THRESHOLD


class ProductStoreSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.SlugField()
    name = serializers.CharField()
    store_type = serializers.CharField()
    image_url = serializers.CharField()
    is_open = serializers.BooleanField()
    currency = serializers.CharField()
    delivery_time_min = serializers.IntegerField()
    delivery_time_max = serializers.IntegerField()


class ProductWithStoreSerializer(ProductSerializer):
    store = ProductStoreSerializer(read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)

    class Meta(ProductSerializer.Meta):
        fields = ProductSerializer.Meta.fields + ["store", "category_name"]


class MenuCategorySerializer(serializers.ModelSerializer):
    products = ProductSerializer(many=True, read_only=True, source="visible_products")

    class Meta:
        model = MenuCategory
        fields = ["id", "name", "products"]
