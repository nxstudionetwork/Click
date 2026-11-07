"""A customer's saved stores and products. Rows always belong to one customer."""

from django.db import models
from django.db.models import Q

from apps.catalog.models import Product
from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile
from apps.stores.models import Store


class WishlistItem(BaseModel):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="wishlist_items")
    store = models.ForeignKey(Store, on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # Exactly one target per row (new saveable entities add a column + extend this check).
            models.CheckConstraint(
                condition=(Q(store__isnull=False) & Q(product__isnull=True)) | (Q(store__isnull=True) & Q(product__isnull=False)),
                name="wishlists_exactly_one_target",
            ),
            models.UniqueConstraint(fields=["customer", "store"], condition=Q(store__isnull=False), name="wishlists_unique_store"),
            models.UniqueConstraint(fields=["customer", "product"], condition=Q(product__isnull=False), name="wishlists_unique_product"),
        ]
