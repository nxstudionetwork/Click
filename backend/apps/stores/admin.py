from django.contrib import admin

from .models import Store, StoreCategory, StoreOffer


class StoreOfferInline(admin.TabularInline):
    model = StoreOffer
    extra = 0


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ["name", "store_type", "status", "is_accepting_orders", "paused_until", "city", "rating_average"]
    list_filter = ["store_type", "status", "city"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ["name"]}
    filter_horizontal = ["categories"]
    inlines = [StoreOfferInline]


@admin.register(StoreCategory)
class StoreCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "store_type", "position"]
    list_filter = ["store_type"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(StoreOffer)
class StoreOfferAdmin(admin.ModelAdmin):
    """Click review of partner-created offers: customers see an offer only after approval."""

    list_display = ["title", "store", "discount_type", "discount_value", "review_status", "is_active", "starts_at", "ends_at"]
    list_filter = ["review_status", "created_by_partner", "discount_type"]
    search_fields = ["title", "store__name"]
    actions = ["approve", "reject"]

    @admin.action(description="Approve (customers can see and use it)")
    def approve(self, request, queryset):
        from apps.orders.restaurant import review_offer

        for offer in queryset.select_related("store"):
            review_offer(offer, True)
        self.message_user(request, f"{queryset.count()} offer(s) approved.")

    @admin.action(description="Reject")
    def reject(self, request, queryset):
        from apps.orders.restaurant import review_offer

        for offer in queryset.select_related("store"):
            review_offer(offer, False, "Click couldn’t approve these terms. Edit and submit again.")
        self.message_user(request, f"{queryset.count()} offer(s) rejected.")
