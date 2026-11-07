"""
Server-side cart: one per customer, holding items from a single store.
Prices are never stored here; they are always read live from Product and
snapshotted only when an order is placed.
"""

from django.db import models
from django.db.models import Q

from apps.catalog.models import Product
from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile
from apps.stores.models import Store

MAX_ITEM_QUANTITY = 50


class Cart(BaseModel):
    customer = models.OneToOneField(CustomerProfile, on_delete=models.CASCADE, related_name="cart")
    store = models.ForeignKey(Store, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")


class CartItem(BaseModel):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="+")
    quantity = models.PositiveSmallIntegerField()
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["cart", "product"], name="carts_item_product_unique"),
            models.CheckConstraint(condition=Q(quantity__gte=1, quantity__lte=MAX_ITEM_QUANTITY), name="carts_item_quantity_range"),
        ]
