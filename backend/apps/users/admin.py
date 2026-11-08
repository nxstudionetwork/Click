from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import AuthIdentity, User


class AuthIdentityInline(admin.TabularInline):
    model = AuthIdentity
    extra = 0
    can_delete = False
    fields = ["provider", "subject", "phone_number", "last_verified_at", "created_at"]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [AuthIdentityInline]
    ordering = ["-created_at"]
    list_display = ["email", "phone", "full_name", "is_staff", "is_active", "created_at"]
    search_fields = ["email", "full_name", "phone"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("full_name", "phone")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),)
