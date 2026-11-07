from django.contrib import admin

from .models import Order, OrderItem, OrderStatusEvent


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["product", "product_name", "unit_price", "quantity", "line_total", "note"]


class OrderStatusEventInline(admin.TabularInline):
    model = OrderStatusEvent
    extra = 0
    readonly_fields = ["from_status", "to_status", "actor", "note", "created_at"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["number", "store", "customer", "status", "total", "created_at"]
    list_filter = ["status", "store__store_type"]
    search_fields = ["number", "customer__user__email", "store__name"]
    readonly_fields = [f.name for f in Order._meta.fields]
    inlines = [OrderItemInline, OrderStatusEventInline]
