from django.contrib import admin, messages

from . import services
from .models import (
    Partner, PartnerAddress, PartnerCategory, PartnerMembership, PartnerProfile, PartnerStatusEvent, PartnerType,
    PartnerVerification,
)


class CategoryInline(admin.TabularInline):
    model = PartnerCategory
    extra = 0
    fields = ["name", "slug", "icon", "sort_order", "is_active"]


@admin.register(PartnerType)
class PartnerTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "sort_order", "is_active"]
    inlines = [CategoryInline]


@admin.register(PartnerCategory)
class PartnerCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "partner_type", "sort_order", "is_active"]
    list_filter = ["partner_type", "is_active"]


class ProfileInline(admin.StackedInline):
    model = PartnerProfile
    can_delete = False


class AddressInline(admin.StackedInline):
    model = PartnerAddress
    extra = 0


class MembershipInline(admin.TabularInline):
    model = PartnerMembership
    extra = 0
    raw_id_fields = ["user"]


class VerificationInline(admin.TabularInline):
    model = PartnerVerification
    extra = 0
    readonly_fields = ["status", "submitted_at", "reviewed_at", "reviewed_by", "reviewer_note"]
    can_delete = False


class StatusEventInline(admin.TabularInline):
    model = PartnerStatusEvent
    extra = 0
    readonly_fields = ["from_status", "to_status", "actor", "note", "created_at"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = ["partner_code", "business_name", "category", "status", "created_at"]
    list_filter = ["status", "partner_type", "category"]
    search_fields = ["partner_code", "business_name", "memberships__user__phone"]
    readonly_fields = ["partner_code", "status", "profile_completed_at"]
    inlines = [ProfileInline, AddressInline, MembershipInline, VerificationInline, StatusEventInline]
    actions = ["approve_verification", "reject_verification"]

    def _review(self, request, queryset, approve):
        done = 0
        for partner in queryset:
            try:
                services.review_verification(partner, approve=approve, reviewer=request.user)
                done += 1
            except Exception as exc:  # report and continue with the rest
                self.message_user(request, f"{partner}: {exc}", messages.WARNING)
        self.message_user(request, f"{done} partner(s) updated.")

    @admin.action(description="Approve verification (marks Verified)")
    def approve_verification(self, request, queryset):
        self._review(request, queryset, True)

    @admin.action(description="Reject verification")
    def reject_verification(self, request, queryset):
        self._review(request, queryset, False)
