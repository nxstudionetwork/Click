from django.contrib import admin

from .models import ApprovalLevel, ApprovalPolicy, ApprovalRequest, Task


class LevelInline(admin.TabularInline):
    model = ApprovalLevel
    extra = 0


@admin.register(ApprovalPolicy)
class ApprovalPolicyAdmin(admin.ModelAdmin):
    list_display = ("name", "key", "approval_type", "is_active")
    inlines = [LevelInline]


@admin.register(ApprovalRequest)
class ApprovalRequestAdmin(admin.ModelAdmin):
    list_display = ("reference", "title", "amount", "status", "requested_by", "created_at")
    list_filter = ("status",)
    readonly_fields = [f.name for f in ApprovalRequest._meta.fields]


admin.site.register(Task)
