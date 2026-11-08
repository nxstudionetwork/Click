from rest_framework import serializers

from .models import Store, StoreCategory, StoreOffer


class StoreCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreCategory
        fields = ["id", "name", "slug", "store_type"]


class StoreOfferSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreOffer
        fields = ["id", "title", "description", "ends_at"]


class OfferStoreSerializer(serializers.ModelSerializer):
    is_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = Store
        fields = ["id", "slug", "name", "store_type", "image_url", "is_open"]


class OfferWithStoreSerializer(StoreOfferSerializer):
    store = OfferStoreSerializer(read_only=True)

    class Meta(StoreOfferSerializer.Meta):
        fields = StoreOfferSerializer.Meta.fields + ["store"]


class StoreSerializer(serializers.ModelSerializer):
    """Contract mirrored by `Store` in packages/api/src/types.ts."""

    categories = StoreCategorySerializer(many=True, read_only=True)
    offers = serializers.SerializerMethodField()
    is_open = serializers.BooleanField(read_only=True)
    # Present only for location queries (`lat`/`lng`); null otherwise. Never guessed.
    distance_km = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = [
            "id", "slug", "name", "store_type", "description", "image_url", "categories", "city", "locality",
            "rating_average", "rating_count", "price_level", "delivery_time_min", "delivery_time_max",
            "delivery_fee", "min_order_amount", "currency", "is_open", "offers", "distance_km",
        ]

    def get_distance_km(self, store):
        d = getattr(store, "distance_km", None)
        return None if d is None else round(d, 1)

    def get_offers(self, store):
        # Uses the prefetched, already-filtered `active_offers` when available.
        offers = getattr(store, "active_offers", None)
        if offers is None:
            offers = store.offers.filter(is_active=True)
        return StoreOfferSerializer(offers, many=True).data
