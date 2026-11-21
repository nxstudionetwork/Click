from django.contrib import admin

from .models import Prescription, RefillReminder


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ("reference", "pharmacy", "status", "created_at", "reviewed_at")
    list_filter = ("status",)
    search_fields = ("reference",)
    readonly_fields = ("customer", "file", "file_name", "file_type", "reviewed_by", "order")


admin.site.register(RefillReminder)
