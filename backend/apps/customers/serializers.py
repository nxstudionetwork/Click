import re

from django.db import transaction
from rest_framework import serializers

from .models import Address

PHONE_RE = re.compile(r"^\+?[0-9 \-]{7,20}$")


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            "id", "label", "recipient_name", "phone", "line1", "line2", "landmark",
            "city", "state", "postal_code", "country", "latitude", "longitude", "is_default", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_phone(self, value):
        if not PHONE_RE.match(value):
            raise serializers.ValidationError("Enter a valid phone number.")
        return value

    def validate_country(self, value):
        return value.upper()

    @transaction.atomic
    def save(self, **kwargs):
        customer = kwargs.get("customer") or self.instance.customer
        make_default = self.validated_data.get("is_default")
        if make_default is None and self.instance is None:
            make_default = not customer.addresses.exists()
            self.validated_data["is_default"] = make_default
        if make_default:
            customer.addresses.select_for_update().filter(is_default=True).update(is_default=False)
        return super().save(**kwargs)
