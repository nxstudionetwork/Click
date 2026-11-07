from rest_framework import serializers

from .models import MenuCategory, Product


LOW_STOCK_THRESHOLD = 5


class ProductSerializer(serializers.ModelSerializer):
    """Contract mirrored by `Product` in packages/api/src/types.ts."""

    store_id = serializers.UUIDField(read_only=True)
    category_id = serializers.UUIDField(read_only=True, allow_null=True)
    is_available = serializers.SerializerMethodField()
    discount_percent = serializers.SerializerMethodField()
    low_stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "store_id", "category_id", "name", "description", "image_url", "price", "compare_at_price",
            "discount_percent", "brand", "unit_label", "dietary", "is_available", "low_stock", "is_featured",
        ]

    def get_is_available(self, p) -> bool:
        return p.is_available and p.in_stock

    def get_discount_percent(self, p) -> int | None:
        if not p.compare_at_price:
            return None
        return int(round((1 - p.price / p.compare_at_price) * 100))

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
