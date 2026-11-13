"""
Products a store sells. For restaurants these form the menu; for retail sellers they are marketplace listings.

The marketplace layer adds a global category tree (ShopCategory), brands, category-specific attribute
definitions with per-product values (so specs and filters never need new columns), purchasable variants with
their own price and stock, a photo gallery, and time-boxed deals. A product always belongs to one seller (Store);
the same item from two sellers is two listings, each with its own price, stock and fulfilment.
"""

from django.contrib.postgres.indexes import GinIndex, OpClass
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Upper

from apps.core.models import BaseModel
from apps.stores.models import Store


class Brand(BaseModel):
    """A brand sold on Click. Shopping. Listing a brand implies no partnership with it."""

    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True)
    description = models.CharField(max_length=300, blank=True)
    logo_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        indexes = [GinIndex(OpClass(Upper("name"), name="gin_trgm_ops"), name="catalog_brand_name_trgm")]

    def __str__(self) -> str:
        return self.name


class ShopCategory(BaseModel):
    """The shopping taxonomy (two levels today, e.g. Fashion > Men's Clothing). Database-driven, never hard-coded."""

    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="children")
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=90, unique=True)
    description = models.CharField(max_length=200, blank=True)
    image_url = models.URLField(blank=True, help_text="Real category photo (optional; the app shows the icon otherwise).")
    icon = models.CharField(max_length=30, blank=True, help_text="UI icon name from the Click icon set.")
    synonyms = models.CharField(max_length=300, blank=True, help_text="Comma-separated words that mean this category in search.")
    position = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "name"]
        verbose_name_plural = "shop categories"

    def __str__(self) -> str:
        return f"{self.parent.name} / {self.name}" if self.parent_id else self.name

    def lineage_ids(self) -> list:
        """This category and its parent (attribute definitions on a parent apply to its children)."""
        return [self.id] + ([self.parent_id] if self.parent_id else [])


class AttributeDefinition(BaseModel):
    """A specification a category's products can have, e.g. Electronics -> Battery life (hours)."""

    class Kind(models.TextChoices):
        CHOICE = "choice", "One of a list"
        NUMBER = "number", "Number"
        TEXT = "text", "Free text"
        BOOLEAN = "boolean", "Yes / no"

    category = models.ForeignKey(ShopCategory, on_delete=models.CASCADE, related_name="attributes")
    code = models.SlugField(max_length=40)
    name = models.CharField(max_length=60)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.CHOICE)
    unit = models.CharField(max_length=20, blank=True)
    is_filterable = models.BooleanField(default=True)
    is_comparable = models.BooleanField(default=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "name"]
        constraints = [models.UniqueConstraint(fields=["category", "code"], name="catalog_attribute_code_unique")]

    def __str__(self) -> str:
        return f"{self.category.name}: {self.name}"


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

    # Marketplace (retail listings). Optional for menus and groceries.
    shop_category = models.ForeignKey(ShopCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    brand_ref = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    highlights = models.JSONField(default=list, blank=True, help_text="Short key points shown on the product page.")
    # Maintained by the review service from published reviews only (never edited by hand).
    rating_average = models.DecimalField(max_digits=2, decimal_places=1, default=0)
    rating_count = models.PositiveIntegerField(default=0)
    # Units on non-cancelled orders; maintained by order placement and cancellation (feeds Best Sellers).
    units_sold = models.PositiveIntegerField(default=0)
    return_days = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Return window after delivery; empty = not returnable.")
    replacement_only = models.BooleanField(default=False, help_text="Returns are replaced, not refunded.")
    warranty = models.CharField(max_length=120, blank=True, help_text="e.g. '1 year manufacturer warranty'.")
    is_cod_available = models.BooleanField(default=True, help_text="Cash on delivery allowed for this item.")

    # Pharma (pharmacy listings): prescription-only items can be ordered only with a prescription that pharmacy verified.
    requires_prescription = models.BooleanField(default=False)
    composition = models.CharField(max_length=200, blank=True, help_text="Salt / composition and strength, e.g. 'Paracetamol 500 mg'.")
    pack_size = models.CharField(max_length=60, blank=True)
    manufacturer = models.CharField(max_length=120, blank=True)
    health_category = models.CharField(max_length=20, blank=True, help_text="Pharma aisle code (apps.pharma.views.CATEGORIES).")
    max_per_order = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Quantity limit per order (e.g. for medicines).")

    # Groceries: the canonical product this listing sells (same item + size across stores), freshness and weighing.
    grocery_item = models.ForeignKey("groceries.GroceryItem", on_delete=models.SET_NULL, null=True, blank=True, related_name="listings")
    received_on = models.DateField(null=True, blank=True, help_text="Date the vendor received this stock (fresh produce).")
    variable_weight = models.BooleanField(default=False, help_text="Weighed at packing; the customer never pays more than shown.")

    class Meta:
        ordering = ["position", "name"]
        indexes = [
            models.Index(fields=["store", "is_active", "is_available"], name="catalog_product_store_idx"),
            models.Index(fields=["shop_category", "is_active"], name="catalog_product_shopcat_idx"),
            models.Index(fields=["-created_at"], name="catalog_product_recent_idx"),
            models.Index(fields=["-units_sold"], name="catalog_product_sold_idx"),
            models.Index(fields=["grocery_item", "is_active"], name="catalog_product_gitem_idx"),
            GinIndex(OpClass(Upper("name"), name="gin_trgm_ops"), name="catalog_product_name_trgm"),
        ]
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

    def save(self, *args, **kwargs):
        if self.brand_ref_id and not self.brand:
            self.brand = self.brand_ref.name
        super().save(*args, **kwargs)


class ProductAttributeValue(BaseModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="attribute_values")
    definition = models.ForeignKey(AttributeDefinition, on_delete=models.CASCADE, related_name="values")
    value = models.CharField(max_length=120, help_text="Display value; for numbers the plain number.")
    number = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["definition__position"]
        constraints = [models.UniqueConstraint(fields=["product", "definition"], name="catalog_attribute_value_unique")]
        indexes = [models.Index(fields=["definition", "value"], name="catalog_attr_value_idx")]


class ProductVariant(BaseModel):
    """A purchasable version of a product (e.g. Black / M) with its own price and stock."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    options = models.JSONField(help_text='Axis -> value, e.g. {"Color": "Black", "Size": "M"}.')
    options_key = models.CharField(max_length=200, editable=False)
    sku = models.CharField(max_length=60, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    stock_quantity = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "created_at"]
        constraints = [
            models.UniqueConstraint(fields=["product", "options_key"], name="catalog_variant_options_unique"),
            models.CheckConstraint(condition=Q(price__gte=0), name="catalog_variant_price_non_negative"),
            models.CheckConstraint(condition=Q(compare_at_price__isnull=True) | Q(compare_at_price__gt=F("price")),
                                   name="catalog_variant_compare_at_above_price"),
        ]

    def __str__(self) -> str:
        return f"{self.product.name} ({self.label})"

    # PostgreSQL JSONB does not keep key order, so axes are shown in this order (others alphabetically after).
    AXIS_ORDER = ["Color", "Size", "Storage", "Pack"]

    @classmethod
    def ordered_axes(cls, names) -> list:
        return sorted(names, key=lambda n: (cls.AXIS_ORDER.index(n) if n in cls.AXIS_ORDER else len(cls.AXIS_ORDER), n))

    @staticmethod
    def key_for(options: dict) -> str:
        return "|".join(f"{k}={options[k]}" for k in sorted(options))

    @property
    def label(self) -> str:
        opts = self.options or {}
        return " · ".join(str(opts[k]) for k in self.ordered_axes(opts))

    @property
    def in_stock(self) -> bool:
        return self.stock_quantity is None or self.stock_quantity > 0

    @property
    def is_orderable(self) -> bool:
        return self.is_active and self.in_stock and self.product.is_active and self.product.is_available

    def save(self, *args, **kwargs):
        self.options_key = self.key_for(self.options or {})
        super().save(*args, **kwargs)


class ProductImage(BaseModel):
    """
    A gallery photo. Uploads (admin today, Partner App later) are re-encoded to WebP renditions in the configured
    media storage (`renditions` = {width: storage path}); `url` is for images already hosted elsewhere.
    Image bytes never go into PostgreSQL.
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    url = models.URLField(blank=True)
    renditions = models.JSONField(default=dict, blank=True, editable=False)
    width = models.PositiveIntegerField(null=True, blank=True, editable=False)
    height = models.PositiveIntegerField(null=True, blank=True, editable=False)
    alt = models.CharField(max_length=160, blank=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "created_at"]


class ProductDeal(BaseModel):
    """A time-boxed price cut on a listing, applied by the server at pricing time (never by the client)."""

    class Kind(models.TextChoices):
        LIMITED = "limited", "Limited-time deal"
        FLASH = "flash", "Flash deal"
        PRICE_DROP = "price_drop", "Price drop"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="deals")
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.LIMITED)
    percent_off = models.PositiveSmallIntegerField()
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    quantity_limit = models.PositiveIntegerField(null=True, blank=True, help_text="Units available at the deal price.")
    units_sold = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["ends_at"]
        indexes = [models.Index(fields=["product", "is_active", "ends_at"], name="catalog_deal_active_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(percent_off__gte=1, percent_off__lte=90), name="catalog_deal_percent_range"),
            models.CheckConstraint(condition=Q(ends_at__gt=F("starts_at")), name="catalog_deal_window"),
        ]

    def __str__(self) -> str:
        return f"{self.percent_off}% off {self.product.name}"

    @property
    def remaining(self) -> int | None:
        return None if self.quantity_limit is None else max(self.quantity_limit - self.units_sold, 0)


class ProductOptionGroup(BaseModel):
    """A customisation step for a product, e.g. "Size" (choose 1) or "Add-ons" (up to 3)."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="option_groups")
    name = models.CharField(max_length=60)
    min_select = models.PositiveSmallIntegerField(default=0, help_text="0 = optional; 1 = a choice is required.")
    max_select = models.PositiveSmallIntegerField(default=1)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "name"]
        constraints = [
            models.UniqueConstraint(fields=["product", "name"], name="catalog_option_group_unique"),
            models.CheckConstraint(condition=Q(max_select__gte=1) & Q(max_select__gte=F("min_select")), name="catalog_option_group_bounds"),
        ]

    def __str__(self) -> str:
        return f"{self.product.name}: {self.name}"


class ProductOption(BaseModel):
    """One choice inside a group. `price_delta` is added to the product price (never set by the client)."""

    group = models.ForeignKey(ProductOptionGroup, on_delete=models.CASCADE, related_name="options")
    name = models.CharField(max_length=60)
    price_delta = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_available = models.BooleanField(default=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "name"]
        constraints = [
            models.UniqueConstraint(fields=["group", "name"], name="catalog_option_unique"),
            models.CheckConstraint(condition=Q(price_delta__gte=0), name="catalog_option_price_non_negative"),
        ]

    def __str__(self) -> str:
        return self.name
