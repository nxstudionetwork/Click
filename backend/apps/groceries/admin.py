from django.contrib import admin

from .models import GroceryCategory, GroceryItem, GroceryOrderDetails, GroceryStoreSettings, ShoppingList, StockAlert, StoreHours


@admin.register(GroceryCategory)
class GroceryCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "section", "position", "is_active"]
    list_editable = ["position", "is_active"]
    list_filter = ["section", "is_active"]
    prepopulated_fields = {"slug": ["name"]}
    search_fields = ["name", "synonyms"]


@admin.register(GroceryItem)
class GroceryItemAdmin(admin.ModelAdmin):
    list_display = ["name", "brand", "size_value", "size_unit", "category", "is_active"]
    list_filter = ["category", "is_active"]
    search_fields = ["name", "brand"]


class StoreHoursInline(admin.TabularInline):
    model = StoreHours
    extra = 0


@admin.register(GroceryStoreSettings)
class GroceryStoreSettingsAdmin(admin.ModelAdmin):
    list_display = ["store", "is_independent", "delivery_radius_km", "fast_enabled", "scheduled_enabled"]
    list_filter = ["is_independent", "fast_enabled", "scheduled_enabled"]
    search_fields = ["store__name"]


@admin.register(StoreHours)
class StoreHoursAdmin(admin.ModelAdmin):
    list_display = ["store", "weekday", "opens_at", "closes_at"]
    list_filter = ["weekday"]
    search_fields = ["store__name"]


@admin.register(GroceryOrderDetails)
class GroceryOrderDetailsAdmin(admin.ModelAdmin):
    list_display = ["order", "delivery_mode", "slot_start", "substitution"]
    list_filter = ["delivery_mode", "substitution"]
    readonly_fields = [f.name for f in GroceryOrderDetails._meta.fields]


admin.site.register(StockAlert)
admin.site.register(ShoppingList)
