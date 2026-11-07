from django.contrib import admin

from .models import MenuCategory, Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "store", "category", "price", "is_available", "is_active"]
    list_filter = ["is_available", "is_active", "dietary", "store__store_type"]
    search_fields = ["name", "store__name"]
    autocomplete_fields = ["store"]


@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "store", "position", "is_active"]
    search_fields = ["name", "store__name"]
