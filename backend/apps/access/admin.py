"""Interim inspection only. Day-to-day identity and access administration happens in Business OS (audited there)."""

from django.contrib import admin

from .models import OSAccount, OSSession, Permission, Role, RoleAssignment, ServiceAccount


@admin.register(OSAccount)
class OSAccountAdmin(admin.ModelAdmin):
    list_display = ("user", "kind", "status", "last_login_at", "mfa_enabled_at")
    list_filter = ("kind", "status")
    search_fields = ("user__email", "user__full_name")
    exclude = ("mfa_secret", "mfa_pending_secret", "recovery_codes")
    raw_id_fields = ("user", "invited_by", "partner")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "key", "audience", "is_system", "requires_mfa")


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "sensitive", "is_active")
    search_fields = ("code",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(RoleAssignment)
class RoleAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "org_unit", "department", "is_active", "valid_until")
    raw_id_fields = ("user", "granted_by")


@admin.register(OSSession)
class OSSessionAdmin(admin.ModelAdmin):
    list_display = ("user", "device_label", "ip", "last_seen_at", "expires_at", "revoked_at")
    readonly_fields = [f.name for f in OSSession._meta.fields]


@admin.register(ServiceAccount)
class ServiceAccountAdmin(admin.ModelAdmin):
    list_display = ("name", "key_prefix", "last_used_at", "revoked_at")
    exclude = ("key_hash",)
