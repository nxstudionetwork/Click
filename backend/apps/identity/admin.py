from django.contrib import admin

from .models import SignInEvent


@admin.register(SignInEvent)
class SignInEventAdmin(admin.ModelAdmin):
    """Read-only account security log."""

    list_display = ("created_at", "event", "phone", "user", "app", "device", "ip", "method")
    list_filter = ("event", "app", "method")
    search_fields = ("phone", "user__email", "ip")
    readonly_fields = [f.name for f in SignInEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
