"""Products a store sells. For restaurants these form the menu."""

from django.db import models
from django.db.models import F, Q

from apps.core.models import BaseModel
from apps.stores.models import Store


class MenuCategory(BaseModel):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="menu_categories")
    name = models.CharField(max_length=80)
    position = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "name"]
        constraints = [models.UniqueConstraint(fields=["store", "name"], name="catalog_menu_category_unique")]
        verbose_name_plural = "menu categories"

    def __str__(self) -> str:
        return f"{self.store.name} / {self.name}"


class Product(BaseModel):
    class Dietary(models.TextChoices):
        VEG = "veg", "Vegetarian"
        NON_VEG = "non_veg", "Non-vegetarian"
        VEGAN = "vegan", "Vegan"
        UNSPECIFIED = "unspecified", "Unspecified"

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="products")
    category = models.ForeignKey(MenuCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    image_url = models.URLField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Original price when discounted (shown struck out)."
    )
    brand = models.CharField(max_length=80, blank=True)
    unit_label = models.CharField(max_length=40, blank=True, help_text="e.g. '1 kg', '500 ml', 'Pack of 6'.")
    stock_quantity = models.PositiveIntegerField(
        null=True, blank=True, help_text="Tracked inventory. Null = not tracked (made to order)."
    )
    dietary = models.CharField(max_length=12, choices=Dietary.choices, default=Dietary.UNSPECIFIED)
    is_available = models.BooleanField(default=True, help_text="Temporarily out of stock when false.")
    is_active = models.BooleanField(default=True, help_text="Hidden from customers when false.")
    is_featured = models.BooleanField(default=False)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "name"]
        indexes = [models.Index(fields=["store", "is_active", "is_available"], name="catalog_product_store_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(price__gte=0), name="catalog_product_price_non_negative"),
            models.CheckConstraint(
                condition=Q(compare_at_price__isnull=True) | Q(compare_at_price__gt=F("price")),
                name="catalog_product_compare_at_above_price",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def in_stock(self) -> bool:
        return self.stock_quantity is None or self.stock_quantity > 0

    @property
    def is_orderable(self) -> bool:
        return self.is_active and self.is_available and self.in_stock
