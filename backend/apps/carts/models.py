"""
Server-side cart: one per customer, holding items from a single store.
Prices are never stored here; they are always read live from Product and
snapshotted only when an order is placed.
"""

from django.db import models
from django.db.models import Q

from apps.catalog.models import Product, ProductOption
from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile
from apps.stores.models import Store, StoreOffer

MAX_ITEM_QUANTITY = 50


class Cart(BaseModel):
    customer = models.OneToOneField(CustomerProfile, on_delete=models.CASCADE, related_name="cart")
    store = models.ForeignKey(Store, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    # Chosen offer; re-validated on every price calculation and at order placement (never trusted as-is).
    offer = models.ForeignKey(StoreOffer, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")


class CartItem(BaseModel):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="+")
    quantity = models.PositiveSmallIntegerField()
    note = models.CharField(max_length=200, blank=True)
    # Chosen customisations. `options_key` (sorted option ids) keeps one line per product + choice combination.
    options = models.ManyToManyField(ProductOption, blank=True, related_name="+")
    options_key = models.CharField(max_length=400, blank=True, default="")

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["cart", "product", "options_key"], name="carts_item_product_options_unique"),
            models.CheckConstraint(condition=Q(quantity__gte=1, quantity__lte=MAX_ITEM_QUANTITY), name="carts_item_quantity_range"),
        ]
