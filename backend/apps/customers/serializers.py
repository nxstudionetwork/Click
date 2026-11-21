
from django.db import transaction
from rest_framework import serializers

from apps.core.api.exceptions import DomainError

from .models import MAX_ADDRESSES, Address



class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            "id", "label", "recipient_name", "phone", "line1", "line2", "landmark",
            "city", "state", "postal_code", "country", "latitude", "longitude", "delivery_instructions", "is_default", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_phone(self, value):
        from apps.identity.phone import MESSAGE, parse_indian_mobile

        phone = parse_indian_mobile(value)
        if not phone:
            raise serializers.ValidationError(MESSAGE)
        return phone

    def validate_country(self, value):
        return value.upper()

    @transaction.atomic
    def save(self, **kwargs):
        customer = kwargs.get("customer") or self.instance.customer
        if self.instance is None:
            type(customer).objects.select_for_update().get(pk=customer.pk)  # serialize concurrent adds
            if customer.addresses.count() >= MAX_ADDRESSES:
                raise DomainError(f"You can save up to {MAX_ADDRESSES} addresses. Remove one to add another.", code="address_limit")
        make_default = self.validated_data.get("is_default")
        if make_default is None and self.instance is None:
            make_default = not customer.addresses.exists()
            self.validated_data["is_default"] = make_default
        if make_default:
            customer.addresses.select_for_update().filter(is_default=True).update(is_default=False)
        return super().save(**kwargs)
