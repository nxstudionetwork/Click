from django.contrib import admin

from .models import Store, StoreCategory, StoreOffer


class StoreOfferInline(admin.TabularInline):
    model = StoreOffer
    extra = 0


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ["name", "store_type", "status", "is_accepting_orders", "city", "rating_average"]
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
