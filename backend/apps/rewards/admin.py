from django.contrib import admin

from .models import RewardTransaction


@admin.register(RewardTransaction)
class RewardTransactionAdmin(admin.ModelAdmin):
    list_display = ["customer", "kind", "points", "description", "created_at"]
    list_filter = ["kind"]
    readonly_fields = ["customer", "kind", "points", "order", "description", "expires_at"]
