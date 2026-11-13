from django import forms
from django.contrib import admin

from apps.core.api.exceptions import DomainError

from . import images
from .models import (AttributeDefinition, Brand, MenuCategory, Product, ProductAttributeValue, ProductDeal, ProductImage,
                     ProductVariant, ShopCategory)


class ProductImageForm(forms.ModelForm):
    upload = forms.ImageField(required=False, help_text="JPG, PNG or WebP up to 8 MB. Stored as WebP renditions.")

    class Meta:
        model = ProductImage
        fields = ["upload", "url", "alt", "position"]

    def clean(self):
        data = super().clean()
        if not data.get("upload") and not data.get("url") and not self.instance.renditions:
            raise forms.ValidationError("Upload a photo or give its URL.")
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        upload = self.cleaned_data.get("upload")
        if upload:
            if obj.renditions:
                images.delete_files(obj)
            try:
                images.store_upload(obj, upload)
            except DomainError as e:
                raise forms.ValidationError(str(e))
        if commit:
            obj.save()
        return obj


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    form = ProductImageForm
    extra = 0


class VariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    fields = ["options", "sku", "price", "compare_at_price", "stock_quantity", "is_active", "position"]


class AttributeValueInline(admin.TabularInline):
    model = ProductAttributeValue
    extra = 0
    autocomplete_fields = ["definition"]


class DealInline(admin.TabularInline):
    model = ProductDeal
    extra = 0
    readonly_fields = ["units_sold"]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "store", "shop_category", "brand", "price", "rating_average", "units_sold", "is_available", "is_active"]
    list_filter = ["is_available", "is_active", "dietary", "store__store_type", "shop_category"]
    search_fields = ["name", "store__name", "brand"]
    autocomplete_fields = ["store", "brand_ref", "shop_category"]
    readonly_fields = ["rating_average", "rating_count", "units_sold"]
    inlines = [ProductImageInline, VariantInline, AttributeValueInline, DealInline]


@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "store", "position", "is_active"]
    search_fields = ["name", "store__name"]


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_active"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ["name"]}


class AttributeDefinitionInline(admin.TabularInline):
    model = AttributeDefinition
    extra = 0


@admin.register(ShopCategory)
class ShopCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "parent", "position", "is_active"]
    list_filter = ["parent"]
    search_fields = ["name", "synonyms"]
    prepopulated_fields = {"slug": ["name"]}
    inlines = [AttributeDefinitionInline]


@admin.register(AttributeDefinition)
class AttributeDefinitionAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "kind", "is_filterable", "is_comparable"]
    search_fields = ["name", "category__name"]


@admin.register(ProductDeal)
class ProductDealAdmin(admin.ModelAdmin):
    list_display = ["product", "kind", "percent_off", "starts_at", "ends_at", "quantity_limit", "units_sold", "is_active"]
    list_filter = ["kind", "is_active"]
    autocomplete_fields = ["product"]
