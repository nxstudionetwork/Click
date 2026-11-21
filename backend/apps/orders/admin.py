from django.contrib import admin, messages

from apps.core.api.exceptions import DomainError

from . import returns
from .models import CheckoutGroup, Order, OrderItem, OrderStatusEvent, ReturnRequest


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["product", "variant", "product_name", "options_summary", "unit_price", "quantity", "line_total", "note",
                       "return_days", "deal_percent"]


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


@admin.register(CheckoutGroup)
class CheckoutGroupAdmin(admin.ModelAdmin):
    list_display = ["number", "customer", "total", "created_at"]
    search_fields = ["number", "customer__user__email"]
    readonly_fields = [f.name for f in CheckoutGroup._meta.fields]


@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = ["item", "customer", "kind", "reason", "quantity", "status", "refund_amount", "created_at"]
    list_filter = ["status", "kind", "reason"]
    search_fields = ["item__order__number", "item__product_name", "customer__user__email"]
    readonly_fields = ["item", "customer", "kind", "reason", "details", "quantity", "status", "refund_amount", "resolved_at"]
    actions = ["approve", "reject", "replacement_sent"]

    def _run(self, request, queryset, fn, done):
        n = 0
        for ret in queryset:
            try:
                fn(ret)
                n += 1
            except DomainError as e:
                self.message_user(request, f"{ret}: {e}", messages.WARNING)
        if n:
            self.message_user(request, f"{n} request(s) {done}.")

    @admin.action(description="Approve (refund returns to the Click Wallet)")
    def approve(self, request, queryset):
        self._run(request, queryset, lambda r: returns.resolve(r, approve=True), "approved")

    @admin.action(description="Reject")
    def reject(self, request, queryset):
        self._run(request, queryset, lambda r: returns.resolve(r, approve=False), "rejected")

    @admin.action(description="Mark replacement as sent")
    def replacement_sent(self, request, queryset):
        self._run(request, queryset, returns.mark_replaced, "marked as sent")
