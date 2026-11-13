"""
Click. Shopping marketplace records that are not part of the product itself: merchandising campaigns (the
Shopping hero, controlled from the backend with priority and a date window) and product reviews (verified
purchases only, moderated). Products, variants, deals and attributes live in apps.catalog; carts and orders
are the shared Click. cart and orders.
"""

from django.db import models
from django.db.models import F, Q

from apps.catalog.models import Product, ShopCategory
from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile


class ShopCampaign(BaseModel):
    class Kind(models.TextChoices):
        FESTIVAL = "festival", "Festival"
        ELECTRONICS = "electronics", "Electronics"
        FASHION = "fashion", "Fashion"
        HOME = "home", "Home"
        BEAUTY = "beauty", "Beauty"
        SCHOOL = "school", "Back to school"
        ESSENTIALS = "essentials", "Everyday essentials"
        SEASONAL = "seasonal", "Seasonal"
        PARTNER = "partner", "Partner campaign"

    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.ESSENTIALS)
    eyebrow = models.CharField(max_length=40, blank=True, help_text='Small label, e.g. "Discover something new".')
    title = models.CharField(max_length=80)
    subtitle = models.CharField(max_length=160, blank=True)
    image_url = models.CharField(max_length=300, blank=True, help_text="Approved campaign photo (path or URL).")
    cta_label = models.CharField(max_length=30, default="Shop now")
    cta_path = models.CharField(max_length=200, help_text="In-app destination, e.g. /shopping/c/electronics.")
    category = models.ForeignKey(ShopCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="campaigns",
                                 help_text="Also shown at the top of this category's page.")
    priority = models.PositiveSmallIntegerField(default=0, help_text="Higher shows first.")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-priority", "ends_at"]
        constraints = [models.CheckConstraint(condition=Q(ends_at__gt=F("starts_at")), name="shop_campaign_window")]

    def __str__(self) -> str:
        return self.title


class ProductReview(BaseModel):
    """One review per customer per product, from a delivered purchase. Only published reviews count or show."""

    class Status(models.TextChoices):
        PUBLISHED = "published", "Published"
        HIDDEN = "hidden", "Hidden by moderation"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="product_reviews")
    order_item = models.ForeignKey("orders.OrderItem", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    rating = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=100, blank=True)
    body = models.CharField(max_length=2000, blank=True)
    variant_label = models.CharField(max_length=120, blank=True)
    verified_purchase = models.BooleanField(default=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PUBLISHED)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["product", "status", "-created_at"], name="shop_review_product_idx")]
        constraints = [
            models.UniqueConstraint(fields=["product", "customer"], name="shop_review_one_per_customer"),
            models.CheckConstraint(condition=Q(rating__gte=1, rating__lte=5), name="shop_review_rating_range"),
        ]
