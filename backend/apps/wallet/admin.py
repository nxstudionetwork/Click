from django.contrib import admin

from .models import WalletTransaction


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    """Interim internal tool (Business OS later). Staff can issue promo credit or adjustments; entries are immutable."""

    list_display = ["customer", "kind", "amount", "description", "created_by", "created_at"]
    list_filter = ["kind"]
    search_fields = ["customer__user__email", "description"]
    fields = ["customer", "kind", "amount", "description"]
    autocomplete_fields = ["customer"]

    def get_readonly_fields(self, request, obj=None):
        return self.fields if obj else []

    def has_delete_permission(self, request, obj=None):
        return False

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == "kind":
            kwargs["choices"] = [("promo", "Promotional credit"), ("adjustment", "Adjustment")]
        return super().formfield_for_choice_field(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
            super().save_model(request, obj, form, change)
