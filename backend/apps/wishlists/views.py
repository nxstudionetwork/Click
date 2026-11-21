from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.activity.services import record
from apps.catalog.serializers import ProductWithStoreSerializer
from apps.catalog.views import public_products
from apps.core.api.permissions import IsCustomer
from apps.stores.serializers import StoreSerializer
from apps.stores.views import public_stores

from .models import WishlistItem


class WishlistItemSerializer(serializers.ModelSerializer):
    kind = serializers.SerializerMethodField()
    store = StoreSerializer(read_only=True)
    product = ProductWithStoreSerializer(read_only=True)

    class Meta:
        model = WishlistItem
        fields = ["id", "kind", "store", "product", "provider", "event_provider", "event_package", "hotel", "travel_route", "attraction", "created_at"]

    provider = serializers.SerializerMethodField()
    event_provider = serializers.SerializerMethodField()
    event_package = serializers.SerializerMethodField()
    hotel = serializers.SerializerMethodField()
    travel_route = serializers.SerializerMethodField()
    attraction = serializers.SerializerMethodField()

    def get_kind(self, item) -> str:
        return ("store" if item.store_id else "product" if item.product_id else "provider" if item.provider_id
                else "event_provider" if item.event_provider_id else "event_package" if item.event_package_id else "hotel" if item.hotel_id
                else "travel_route" if item.travel_route_id else "attraction")

    def get_travel_route(self, item):
        if not item.travel_route_id:
            return None
        from apps.travel.views import place_out

        return {"id": str(item.travel_route_id), "origin": place_out(item.travel_route.origin), "destination": place_out(item.travel_route.destination)}

    def get_attraction(self, item):
        if not item.attraction_id:
            return None
        from apps.experiences.views import card

        return card(item.attraction, saved={}, with_next=False)

    def get_hotel(self, item):
        if not item.hotel_id:
            return None
        from apps.hotels.views import property_card

        return property_card(item.hotel, self.context.get("request"))

    def get_event_provider(self, item):
        if not item.event_provider_id:
            return None
        from apps.eventhub import engine

        return engine.card(item.event_provider, request=self.context.get("request"))

    def get_event_package(self, item):
        if not item.event_package_id:
            return None
        from apps.eventhub import engine

        return engine.package_out(item.event_package, with_provider=True, request=self.context.get("request"))

    def get_provider(self, item):
        if not item.provider_id:
            return None
        from apps.professionals import engine

        return engine.card(item.provider, None, request=self.context.get("request"))


class AddWishlistSerializer(serializers.Serializer):
    store_id = serializers.UUIDField(required=False)
    product_id = serializers.UUIDField(required=False)
    provider_id = serializers.UUIDField(required=False)
    event_provider_id = serializers.UUIDField(required=False)
    event_package_id = serializers.UUIDField(required=False)
    hotel_id = serializers.UUIDField(required=False)
    attraction_id = serializers.UUIDField(required=False)

    def validate(self, attrs):
        if sum(bool(attrs.get(k)) for k in ("store_id", "product_id", "provider_id", "event_provider_id", "event_package_id", "hotel_id", "attraction_id")) != 1:
            raise serializers.ValidationError("Provide exactly one of storeId, productId, providerId, eventProviderId, eventPackageId, hotelId or attractionId.")
        return attrs


def _items(customer):
    return (
        WishlistItem.objects.filter(customer=customer)
        .select_related("product__store", "product__category", "store", "provider__partner__profile", "provider__category",
                        "event_provider__partner", "event_package__provider__partner", "hotel__partner", "hotel__destination",
                        "travel_route__origin__city", "travel_route__destination__city", "attraction")
        .prefetch_related("store__categories", "store__offers", "product__variants", "product__option_groups__options")
    )


class WishlistView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        return Response(WishlistItemSerializer(_items(request.user.customer_profile), many=True, context={"request": request}).data)

    def post(self, request):
        s = AddWishlistSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        customer = request.user.customer_profile
        if store_id := s.validated_data.get("store_id"):
            target = {"store": get_object_or_404(public_stores(), pk=store_id)}
        elif provider_id := s.validated_data.get("provider_id"):
            from apps.professionals.engine import listed

            target = {"provider": get_object_or_404(listed(), pk=provider_id)}
        elif eid := s.validated_data.get("event_provider_id"):
            from apps.eventhub.engine import listed as event_listed

            target = {"event_provider": get_object_or_404(event_listed(), pk=eid)}
        elif kid := s.validated_data.get("event_package_id"):
            from apps.eventhub.models import EventPackage

            target = {"event_package": get_object_or_404(EventPackage.objects.filter(is_active=True, provider__is_listed=True), pk=kid)}
        elif hid := s.validated_data.get("hotel_id"):
            from apps.hotels.models import HotelProperty

            target = {"hotel": get_object_or_404(HotelProperty.objects.filter(is_listed=True), pk=hid)}
        elif aid := s.validated_data.get("attraction_id"):
            from apps.experiences.models import Attraction

            target = {"attraction": get_object_or_404(Attraction.objects.filter(is_listed=True), pk=aid)}
        else:
            target = {"product": get_object_or_404(public_products(), pk=s.validated_data["product_id"])}
        item, created = WishlistItem.objects.get_or_create(customer=customer, **target)
        if created:
            record(customer, "wishlist.added", obj=next(iter(target.values())))
        item = _items(customer).get(pk=item.pk)
        return Response(WishlistItemSerializer(item, context={"request": request}).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class WishlistItemView(APIView):
    permission_classes = [IsCustomer]

    def delete(self, request, pk):
        get_object_or_404(WishlistItem, pk=pk, customer=request.user.customer_profile).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
