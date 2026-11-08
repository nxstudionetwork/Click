"""
A Store is any partner storefront a customer can order from. Restaurants,
grocery and retail shops share this model and differ by `store_type`, so
discovery, carts and orders work identically across verticals.
Partner ownership (PartnerMembership) is added in Phase 5.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.core.models import BaseModel


class StoreType(models.TextChoices):
    RESTAURANT = "restaurant", "Restaurant"
    GROCERY = "grocery", "Grocery"
    RETAIL = "retail", "Retail"


class StoreCategory(BaseModel):
    """Discovery taxonomy, e.g. 'Pizza' for restaurants or 'Dairy' for grocery."""

    store_type = models.CharField(max_length=20, choices=StoreType.choices)
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["store_type", "position", "name"]
        constraints = [models.UniqueConstraint(fields=["store_type", "slug"], name="stores_category_type_slug_unique")]
        verbose_name_plural = "store categories"

    def __str__(self) -> str:
        return self.name


class Store(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        CLOSED = "closed", "Permanently closed"

    store_type = models.CharField(max_length=20, choices=StoreType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    is_accepting_orders = models.BooleanField(default=True, help_text="Partner-controlled availability toggle.")
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, unique=True)
    description = models.TextField(blank=True)
    image_url = models.URLField(blank=True)
    categories = models.ManyToManyField(StoreCategory, related_name="stores", blank=True)

    city = models.CharField(max_length=100)
    locality = models.CharField(max_length=120, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    rating_average = models.DecimalField(max_digits=2, decimal_places=1, default=Decimal("0.0"))
    rating_count = models.PositiveIntegerField(default=0)
    price_level = models.PositiveSmallIntegerField(default=2, help_text="1 (budget) to 4 (premium)")
    delivery_time_min = models.PositiveSmallIntegerField(default=25, help_text="minutes")
    delivery_time_max = models.PositiveSmallIntegerField(default=40, help_text="minutes")
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default=settings.CLICK_DEFAULT_CURRENCY)

    class Meta:
        ordering = ["-rating_average", "name"]
        indexes = [
            models.Index(fields=["store_type", "status"], name="stores_type_status_idx"),
            models.Index(fields=["city", "store_type"], name="stores_city_type_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(rating_average__gte=0, rating_average__lte=5), name="stores_rating_range"),
            models.CheckConstraint(condition=Q(price_level__gte=1, price_level__lte=4), name="stores_price_level_range"),
            models.CheckConstraint(condition=Q(delivery_time_min__lte=F("delivery_time_max")), name="stores_delivery_window"),
            models.CheckConstraint(condition=Q(delivery_fee__gte=0, min_order_amount__gte=0), name="stores_non_negative_fees"),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_open(self) -> bool:
        return self.status == self.Status.ACTIVE and self.is_accepting_orders


class StoreOffer(BaseModel):
    """
    A store promotion. With a `discount_type` it can be applied at checkout (the server computes the discount);
    without one it is display-only (e.g. "Buy 3 books, get 1 free" until that rule type exists).
    """

    class DiscountType(models.TextChoices):
        NONE = "", "Display only"
        PERCENT = "percent", "Percent off"
        FLAT = "flat", "Flat amount off"
        FREE_DELIVERY = "free_delivery", "Free delivery"

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="offers")
    title = models.CharField(max_length=80)
    description = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    discount_type = models.CharField(max_length=16, choices=DiscountType.choices, blank=True, default="")
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Percent (0–100) or amount.")
    max_discount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Cap for percent offers.")
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    @property
    def is_redeemable(self) -> bool:
        return bool(self.discount_type)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["store", "is_active"], name="stores_offer_active_idx")]
