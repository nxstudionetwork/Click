import re

from rest_framework import serializers

from apps.core.api.casing import to_camel

from . import services
from .models import Partner, PartnerAddress, PartnerCategory, PartnerType


def _client_configuration(config: dict) -> dict:
    """Field keys are data values, so camelCase them here to match the camelCase details payload."""
    fields = [{**f, "key": to_camel(f["key"])} for f in config["fields"]]
    return {**config, "fields": fields}


class PartnerCategorySerializer(serializers.ModelSerializer):
    configuration = serializers.SerializerMethodField()

    class Meta:
        model = PartnerCategory
        fields = ["slug", "name", "description", "icon", "image_url", "configuration"]

    def get_configuration(self, category) -> dict:
        return _client_configuration(services.configuration_for(category))


class PartnerTypeSerializer(serializers.ModelSerializer):
    tagline = serializers.SerializerMethodField()
    categories = serializers.SerializerMethodField()

    class Meta:
        model = PartnerType
        fields = ["slug", "name", "description", "icon", "image_url", "tagline", "categories"]

    def get_tagline(self, ptype) -> str:
        return (ptype.configuration or {}).get("tagline", "")

    def get_categories(self, ptype) -> list:
        active = [c for c in ptype.categories.all() if c.is_active]
        return PartnerCategorySerializer(active, many=True).data


class PartnerAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = PartnerAddress
        fields = [
            "line1", "line2", "landmark", "city", "state", "postal_code", "country",
            "latitude", "longitude", "service_area", "service_radius_km",
        ]


class PartnerSerializer(serializers.ModelSerializer):
    """The owner's private view of their own partner."""

    partner_type = serializers.SerializerMethodField()
    category = PartnerCategorySerializer()
    status_label = serializers.CharField(source="get_status_display")
    is_verified = serializers.SerializerMethodField()
    onboarding_step = serializers.SerializerMethodField()
    profile = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()
    verified_phone = serializers.SerializerMethodField()

    class Meta:
        model = Partner
        fields = [
            "partner_code", "status", "status_label", "is_verified", "onboarding_step", "partner_type", "category",
            "business_name", "is_available", "verified_phone", "profile", "address", "profile_completed_at", "created_at",
        ]

    def get_partner_type(self, partner) -> dict:
        t = partner.partner_type
        return {"slug": t.slug, "name": t.name, "icon": t.icon}

    def get_is_verified(self, partner) -> bool:
        return partner.status in (Partner.Status.VERIFIED, Partner.Status.ACTIVE)

    def get_onboarding_step(self, partner) -> str:
        return services.onboarding_step(partner)

    def get_profile(self, partner) -> dict:
        p = partner.profile
        return {"contact_name": p.contact_name, "email": p.email, "description": p.description, "details": p.details}

    def get_address(self, partner):
        address = services.primary_address(partner)
        return PartnerAddressSerializer(address).data if address else None

    def get_verified_phone(self, partner) -> str:
        return self.context["request"].user.phone


class ChooseCategorySerializer(serializers.Serializer):
    partner_type = serializers.SlugField(max_length=60)
    category = serializers.SlugField(max_length=60)


class ProfileSerializer(serializers.Serializer):
    business_name = serializers.CharField(min_length=2, max_length=150)
    contact_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(max_length=254, required=False, allow_blank=True)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True)
    details = serializers.DictField(required=False, default=dict)

    def validate_business_name(self, value):
        value = " ".join(value.split())
        if len(value) < 2:
            raise serializers.ValidationError("Enter at least 2 characters.")
        return value

    def validate_contact_name(self, value):
        return " ".join(value.split())

    def validate_email(self, value):
        return value.strip().lower()


POSTAL_CODE_IN = r"^[1-9][0-9]{5}$"


class LocationSerializer(serializers.Serializer):
    line1 = serializers.CharField(min_length=3, max_length=255)
    line2 = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    landmark = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    city = serializers.CharField(min_length=2, max_length=100)
    state = serializers.CharField(min_length=2, max_length=100)
    postal_code = serializers.CharField(max_length=12)
    country = serializers.ChoiceField(choices=[("IN", "India")], default="IN")
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=-90, max_value=90,
                                        required=False, allow_null=True, default=None)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=-180, max_value=180,
                                         required=False, allow_null=True, default=None)
    service_area = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    service_radius_km = serializers.IntegerField(min_value=1, max_value=500, required=False, allow_null=True, default=None)

    def validate_postal_code(self, value):
        value = value.strip().replace(" ", "")
        if not re.match(POSTAL_CODE_IN, value):
            raise serializers.ValidationError("Enter a valid 6-digit PIN code.")
        return value

    def to_internal_value(self, data):
        # Coordinates arrive from the browser with many decimals; store 6 (~11 cm).
        if isinstance(data, dict):
            data = dict(data)
            for key in ("latitude", "longitude"):
                if isinstance(data.get(key), (int, float)):
                    data[key] = round(float(data[key]), 6)
        values = super().to_internal_value(data)
        for key in ("line1", "line2", "landmark", "city", "state", "service_area"):
            values[key] = " ".join(values[key].split())
        return values

    def validate(self, attrs):
        if (attrs["latitude"] is None) != (attrs["longitude"] is None):
            raise serializers.ValidationError({"latitude": ["Provide both latitude and longitude, or neither."]})
        return attrs
