from django.contrib import admin

from .models import SupportTicket


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ["reference", "customer", "category", "status", "created_at"]
    list_filter = ["status", "category"]
    search_fields = ["reference", "customer__user__email", "subject"]
