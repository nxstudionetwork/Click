"""
Click. Groceries: a marketplace of local grocery vendors. It reuses the shared Click. records — a vendor's storefront
is a `stores.Store` (store_type=grocery), each listing is a `catalog.Product` owned by exactly one store (its own
price, MRP, stock and availability), carts are the shared cart (BASKET mode: one sub-basket per store) and orders are
the shared orders (one order per store, same status machine and payments).

What this app adds:
  GroceryCategory        the grocery category registry (ordering controlled from the admin, never alphabetical)
  GroceryItem            the canonical product (name, brand, pack size) that different stores list at their own
                         prices; it is what makes "same product, same size" price comparison possible
  GroceryStoreSettings   a vendor's delivery configuration (radius, fees, fast/standard/scheduled modes, slots)
  StoreHours             a vendor's weekly operating hours
  GroceryOrderDetails    per-order delivery mode, slot and substitution preference
  StockAlert             "notify me" for an out-of-stock listing or an unavailable store
  ShoppingList(+Item)    a customer's list, matched against nearby stores by "Find everything"
"""

from decimal import Decimal

from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile
from apps.stores.models import Store


class GroceryCategory(BaseModel):
    class Section(models.TextChoices):
        FRESH = "fresh", "Fresh Near You"
        ESSENTIALS = "essentials", "Everyday Essentials"
        DAIRY = "dairy", "Dairy & Breakfast"
        SNACKS = "snacks", "Snacks & Beverages"
        HOME = "home", "Home Essentials"
        PERSONAL = "personal", "Personal Care"
        MORE = "more", "More to discover"

    name = models.CharField(max_length=60)
    slug = models.SlugField(max_length=70, unique=True)
    section = models.CharField(max_length=12, choices=Section.choices, help_text="Home section this category feeds.")
    icon = models.CharField(max_length=30, blank=True, help_text="Icon name from the Click icon set.")
    image_url = models.URLField(max_length=400, blank=True, help_text="Licensed category photo (optional).")
    synonyms = models.CharField(max_length=300, blank=True, help_text="Comma-separated search words, e.g. 'veggies, sabzi'.")
    position = models.PositiveSmallIntegerField(default=100, help_text="Merchandising order (lower first).")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "name"]
        verbose_name_plural = "grocery categories"

    def __str__(self) -> str:
        return self.name


class GroceryItem(BaseModel):
    """A product independent of who sells it, e.g. "Golden Harvest Basmati Rice, 5 kg"."""

    class Unit(models.TextChoices):
        GRAM = "g", "g"
        KILOGRAM = "kg", "kg"
        MILLILITRE = "ml", "ml"
        LITRE = "l", "L"
        PIECE = "pc", "piece"
        PACK = "pack", "pack"
        DOZEN = "dozen", "dozen"

    category = models.ForeignKey(GroceryCategory, on_delete=models.PROTECT, related_name="items")
    name = models.CharField(max_length=150)
    brand = models.CharField(max_length=80, blank=True, help_text="Empty for loose produce.")
    size_value = models.DecimalField(max_digits=8, decimal_places=2)
    size_unit = models.CharField(max_length=6, choices=Unit.choices)
    description = models.TextField(blank=True)
    ingredients = models.TextField(blank=True)
    nutrition = models.JSONField(default=dict, blank=True, help_text='Per 100 g/ml, e.g. {"Energy": "350 kcal"}.')
    dietary = models.CharField(max_length=12, blank=True, help_text="veg / non_veg / vegan, only when known.")
    attributes = models.JSONField(default=list, blank=True, help_text='Tags such as ["organic", "sugar-free"].')
    image_url = models.URLField(max_length=400, blank=True)
    image_credit = models.CharField(max_length=200, blank=True, help_text="Licence credit for image_url.")
    image_source = models.URLField(max_length=400, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category__position", "name"]
        constraints = [models.UniqueConstraint(fields=["name", "brand", "size_value", "size_unit"], name="groceries_item_identity")]
        indexes = [models.Index(fields=["category", "is_active"], name="groceries_item_cat_idx")]

    def __str__(self) -> str:
        return f"{self.brand + ' ' if self.brand else ''}{self.name} {self.size_label}"

    @property
    def size_label(self) -> str:
        v = self.size_value.normalize()
        v = f"{v:f}".rstrip(".")
        if self.size_unit == self.Unit.PIECE:
            return f"{v} pc"
        if self.size_unit in (self.Unit.PACK, self.Unit.DOZEN):
            return f"{v} {self.get_size_unit_display()}" if v != "1" else f"1 {self.get_size_unit_display()}"
        return f"{v} {self.get_size_unit_display()}"

    def unit_basis(self):
        """(base quantity, base label) for a per-unit price: grams/ml per kg/L, pieces per piece."""
        to_base = {"g": (Decimal(1), "kg", 1000), "kg": (Decimal(1000), "kg", 1000), "ml": (Decimal(1), "L", 1000),
                   "l": (Decimal(1000), "L", 1000), "pc": (Decimal(1), "pc", 1), "dozen": (Decimal(12), "pc", 1)}
        if self.size_unit not in to_base:
            return None
        factor, label, per = to_base[self.size_unit]
        return self.size_value * factor, label, per


class GroceryStoreSettings(BaseModel):
    """How a vendor delivers. Fees and ETAs shown to customers are always computed from these values."""

    store = models.OneToOneField(Store, on_delete=models.CASCADE, related_name="grocery")
    is_independent = models.BooleanField(default=False, help_text="Independent local business (not a chain) — 'Local Store' badge.")
    cover_url = models.URLField(max_length=400, blank=True)
    about = models.CharField(max_length=400, blank=True)
    address_line = models.CharField(max_length=200, blank=True)
    support_phone = models.CharField(max_length=20, blank=True)
    policies = models.CharField(max_length=400, blank=True, help_text="Substitution, freshness and return terms.")
    freshness_note = models.CharField(max_length=160, blank=True, help_text="Vendor's own freshness promise, if any.")

    delivery_radius_km = models.DecimalField(max_digits=4, decimal_places=1, default=Decimal("5.0"))
    base_km = models.DecimalField(max_digits=4, decimal_places=1, default=Decimal("2.0"), help_text="Distance included in the base fee.")
    per_km_fee = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("6.00"))
    prep_minutes = models.PositiveSmallIntegerField(default=10, help_text="Typical picking/packing time.")
    minutes_per_km = models.DecimalField(max_digits=4, decimal_places=1, default=Decimal("4.0"))
    max_active_orders = models.PositiveSmallIntegerField(default=8, help_text="Orders the store can pack at once before ETAs grow.")

    fast_enabled = models.BooleanField(default=True)
    fast_radius_km = models.DecimalField(max_digits=4, decimal_places=1, default=Decimal("3.0"))
    fast_surcharge = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("15.00"))
    standard_enabled = models.BooleanField(default=True)
    standard_window_minutes = models.PositiveSmallIntegerField(default=120, help_text="Standard delivery arrives within this window.")
    scheduled_enabled = models.BooleanField(default=True)
    slot_minutes = models.PositiveSmallIntegerField(default=60)
    slot_capacity = models.PositiveSmallIntegerField(default=6, help_text="Orders per slot.")
    slot_days = models.PositiveSmallIntegerField(default=2, help_text="Days ahead customers can schedule.")
    slot_lead_minutes = models.PositiveSmallIntegerField(default=45, help_text="Earliest slot starts at least this far ahead.")

    class Meta:
        verbose_name_plural = "grocery store settings"


class StoreHours(BaseModel):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="hours")
    weekday = models.PositiveSmallIntegerField(help_text="0 = Monday … 6 = Sunday")
    opens_at = models.TimeField()
    closes_at = models.TimeField()

    class Meta:
        ordering = ["weekday", "opens_at"]
        constraints = [
            models.CheckConstraint(condition=Q(weekday__lte=6), name="groceries_hours_weekday"),
            models.CheckConstraint(condition=Q(closes_at__gt=models.F("opens_at")), name="groceries_hours_window"),
        ]
        verbose_name_plural = "store hours"


class GroceryOrderDetails(BaseModel):
    class Mode(models.TextChoices):
        FAST = "fast", "Fast delivery"
        STANDARD = "standard", "Standard delivery"
        SCHEDULED = "scheduled", "Scheduled delivery"

    class Substitution(models.TextChoices):
        NONE = "none", "Don't substitute"
        SIMILAR = "similar", "Substitute with a similar item"
        STORE_CHOICE = "store_choice", "Let the store choose within my preference"

    order = models.OneToOneField("orders.Order", on_delete=models.CASCADE, related_name="grocery")
    delivery_mode = models.CharField(max_length=10, choices=Mode.choices)
    slot_start = models.DateTimeField(null=True, blank=True)
    slot_end = models.DateTimeField(null=True, blank=True)
    substitution = models.CharField(max_length=14, choices=Substitution.choices, default=Substitution.NONE)
    substitution_note = models.CharField(max_length=200, blank=True)
    distance_km = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    eta_min = models.PositiveSmallIntegerField(null=True, blank=True)
    eta_max = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["slot_start"], name="groceries_detail_slot_idx")]


class StockAlert(BaseModel):
    """'Notify me': sent once when the listing is back in stock or the store takes orders again."""

    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="stock_alerts")
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, null=True, blank=True, related_name="stock_alerts")
    store = models.ForeignKey(Store, on_delete=models.CASCADE, null=True, blank=True, related_name="stock_alerts")
    notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=(Q(product__isnull=False) & Q(store__isnull=True)) | (Q(product__isnull=True) & Q(store__isnull=False)),
                                   name="groceries_alert_one_target"),
            models.UniqueConstraint(fields=["customer", "product"], condition=Q(product__isnull=False, notified_at__isnull=True),
                                    name="groceries_alert_product_once"),
            models.UniqueConstraint(fields=["customer", "store"], condition=Q(store__isnull=False, notified_at__isnull=True),
                                    name="groceries_alert_store_once"),
        ]


class ShoppingList(BaseModel):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="shopping_lists")
    name = models.CharField(max_length=60, default="My list")

    class Meta:
        ordering = ["-updated_at"]


class ShoppingListItem(BaseModel):
    shopping_list = models.ForeignKey(ShoppingList, on_delete=models.CASCADE, related_name="items")
    text = models.CharField(max_length=80, help_text="What the customer typed, e.g. 'milk'.")
    quantity = models.PositiveSmallIntegerField(default=1)
    item = models.ForeignKey(GroceryItem, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                             help_text="A specific product, when the customer picked one.")
    is_done = models.BooleanField(default=False)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["is_done", "position", "created_at"]
        constraints = [models.CheckConstraint(condition=Q(quantity__gte=1, quantity__lte=50), name="groceries_list_qty")]
