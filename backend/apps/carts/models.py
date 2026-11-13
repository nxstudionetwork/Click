"""
Server-side cart: one per customer. Prices are never stored here; they are always read live from the catalogue
(apps.catalog.pricing) and snapshotted only when an order is placed.

Two modes behind one Click. cart:
  store        food and groceries: items from a single store (switching stores asks the customer first)
  marketplace  shopping: items from any number of retail sellers; checkout splits it into one order per seller
  basket       groceries: items from one or more local grocery stores; each store is its own sub-basket and
               becomes its own order (own minimum, delivery fee, delivery mode and slot)
"""

from django.db import models
from django.db.models import Q

from apps.catalog.models import Product, ProductOption, ProductVariant
from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile
from apps.stores.models import Store, StoreOffer

MAX_ITEM_QUANTITY = 50


class Cart(BaseModel):
    class Mode(models.TextChoices):
        EMPTY = "", "Empty"
        STORE = "store", "Single store"
        MARKETPLACE = "marketplace", "Marketplace"
        BASKET = "basket", "Grocery basket"

    customer = models.OneToOneField(CustomerProfile, on_delete=models.CASCADE, related_name="cart")
    mode = models.CharField(max_length=12, choices=Mode.choices, blank=True, default="")
    # Single-store mode only; null in marketplace mode (each line knows its seller).
    store = models.ForeignKey(Store, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    # Chosen offer; re-validated on every price calculation and at order placement (never trusted as-is).
    # In marketplace mode it applies to its own seller's part of the cart.
    offer = models.ForeignKey(StoreOffer, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    prescription = models.ForeignKey("pharma.Prescription", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                     help_text="Pharmacy carts: the verified prescription for prescription-only items.")


class CartItem(BaseModel):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="+")
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    quantity = models.PositiveSmallIntegerField()
    note = models.CharField(max_length=200, blank=True)
    # Chosen customisations. `options_key` (sorted option ids) keeps one line per product + choice combination.
    options = models.ManyToManyField(ProductOption, blank=True, related_name="+")
    options_key = models.CharField(max_length=400, blank=True, default="")
    # Groceries: the unit price the customer last saw for this line. A different live price must be acknowledged
    # before checkout (it is never silently charged).
    price_seen = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["cart", "product", "variant", "options_key"], nulls_distinct=False,
                                    name="carts_item_line_unique"),
            models.CheckConstraint(condition=Q(quantity__gte=1, quantity__lte=MAX_ITEM_QUANTITY), name="carts_item_quantity_range"),
        ]
