from django.contrib import admin

from . import reviews
from .models import ProductReview, ShopCampaign


@admin.register(ShopCampaign)
class ShopCampaignAdmin(admin.ModelAdmin):
    list_display = ["title", "kind", "priority", "starts_at", "ends_at", "is_active"]
    list_filter = ["kind", "is_active"]
    search_fields = ["title", "subtitle"]
    autocomplete_fields = ["category"]


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    """Moderation: hiding a review removes it from the product page and its rating; nothing is deleted."""

    list_display = ["product", "customer", "rating", "status", "verified_purchase", "created_at"]
    list_filter = ["status", "rating", "verified_purchase"]
    search_fields = ["product__name", "body", "customer__user__email"]
    readonly_fields = ["product", "customer", "order_item", "rating", "title", "body", "variant_label", "verified_purchase"]
    actions = ["hide", "publish"]

    def _set(self, queryset, status):
        ids = set(queryset.values_list("product_id", flat=True))
        queryset.update(status=status)
        for pid in ids:
            reviews.recompute(pid)

    @admin.action(description="Hide (moderation)")
    def hide(self, request, queryset):
        self._set(queryset, ProductReview.Status.HIDDEN)

    @admin.action(description="Publish")
    def publish(self, request, queryset):
        self._set(queryset, ProductReview.Status.PUBLISHED)
