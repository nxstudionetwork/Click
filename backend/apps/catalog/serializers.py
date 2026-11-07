from rest_framework import serializers

from .models import MenuCategory, Product


class ProductSerializer(serializers.ModelSerializer):
    """Contract mirrored by `Product` in packages/api/src/types.ts."""

    store_id = serializers.UUIDField(read_only=True)
    category_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = Product
        fields = [
            "id", "store_id", "category_id", "name", "description", "image_url", "price",
            "dietary", "is_available", "is_featured",
        ]


class MenuCategorySerializer(serializers.ModelSerializer):
    products = ProductSerializer(many=True, read_only=True, source="visible_products")

    class Meta:
        model = MenuCategory
        fields = ["id", "name", "products"]
