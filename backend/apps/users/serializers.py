from django.contrib.auth import password_validation
from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()
    customer_code = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "phone", "phone_verified", "roles", "customer_code", "avatar_url", "created_at"]
        read_only_fields = ["id", "email", "phone", "phone_verified", "roles", "customer_code", "avatar_url", "created_at"]

    avatar_url = serializers.SerializerMethodField()

    def get_avatar_url(self, user) -> str | None:
        profile = getattr(user, "customer_profile", None)
        return profile.avatar.url if profile and profile.avatar else None

    def validate_full_name(self, v):
        v = " ".join(v.split())
        if len(v) < 2:
            raise serializers.ValidationError("Enter your name.")
        return v

    def get_customer_code(self, user) -> str | None:
        profile = getattr(user, "customer_profile", None)
        return profile.customer_code if profile else None

    def get_roles(self, user) -> list[str]:
        roles = []
        if hasattr(user, "customer_profile"):
            roles.append("customer")
        if user.partner_memberships.filter(is_active=True).exists():
            roles.append("partner")
        if user.is_staff:
            roles.append("staff")
        return roles


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate(self, attrs):
        password_validation.validate_password(attrs["password"], User(email=attrs["email"], full_name=attrs.get("full_name", "")))
        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

