from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

import secrets

from apps.core.models import BaseModel

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_customer_code() -> str:
    """Public, non-sequential Click Customer ID shown to customers and support, e.g. CLK-CS-7K2QXM."""
    return "CLK-CS-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))


class CustomerProfile(BaseModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="customer_profile")
    customer_code = models.CharField(max_length=16, unique=True, default=generate_customer_code, editable=False)
    avatar = models.ImageField(upload_to="avatars/%Y/%m/", blank=True, help_text="Re-encoded WebP, EXIF stripped.")

    def __str__(self) -> str:
        return f"Customer<{self.user.email}>"


MAX_ADDRESSES = 5


class Address(BaseModel):
    class Label(models.TextChoices):
        HOME = "home", "Home"
        WORK = "work", "Work"
        COLLEGE = "college", "College"
        FAMILY = "family", "Family"
        OTHER = "other", "Other"

    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=10, choices=Label.choices, default=Label.HOME)
    recipient_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    line1 = models.CharField(max_length=255)
    line2 = models.CharField(max_length=255, blank=True)
    landmark = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=12)
    country = models.CharField(max_length=2, default="IN", help_text="ISO 3166-1 alpha-2")
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True, validators=[MinValueValidator(-90), MaxValueValidator(90)]
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True, validators=[MinValueValidator(-180), MaxValueValidator(180)]
    )
    delivery_instructions = models.CharField(max_length=200, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_default", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["customer"], condition=Q(is_default=True), name="customers_one_default_address"),
        ]

    def snapshot(self) -> dict:
        """Immutable copy stored on orders so later edits don't rewrite history."""
        fields = ["label", "recipient_name", "phone", "line1", "line2", "landmark", "city", "state", "postal_code", "country", "delivery_instructions"]
        data = {f: getattr(self, f) for f in fields}
        data["latitude"] = str(self.latitude) if self.latitude is not None else None
        data["longitude"] = str(self.longitude) if self.longitude is not None else None
        return data
