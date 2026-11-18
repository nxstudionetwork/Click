from django.contrib import admin, messages

from . import services
from .models import (
    Partner, PartnerAddress, PartnerAvailabilityEvent, PartnerCategory, PartnerMembership, PartnerProfile,
    PartnerDocument, PartnerStatusEvent, PartnerStore, PartnerType, PartnerVenue, PartnerVerification,
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


class StoreLinkInline(admin.TabularInline):
    """Connect the storefront(s) this partner operates; their customer orders then appear on Partner Home."""

    model = PartnerStore
    extra = 0
    raw_id_fields = ["store"]


class VenueLinkInline(admin.TabularInline):
    model = PartnerVenue
    extra = 0
    raw_id_fields = ["venue"]


class AvailabilityInline(admin.TabularInline):
    model = PartnerAvailabilityEvent
    extra = 0
    readonly_fields = ["is_available", "actor", "note", "created_at"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class DocumentInline(admin.TabularInline):
    model = PartnerDocument

    extra = 0
    fields = ["key", "number", "expires_on", "status", "review_note", "submitted_at", "reviewed_at"]
    readonly_fields = ["submitted_at", "reviewed_at"]


@admin.register(PartnerDocument)
class PartnerDocumentAdmin(admin.ModelAdmin):
    """Click review of partner documents. Verified documents with an expiry block operating once they expire."""

    list_display = ["partner", "key", "status", "expires_on", "submitted_at"]
    list_filter = ["status", "key"]
    search_fields = ["partner__partner_code", "partner__business_name", "number"]
    actions = ["verify", "reject"]

    @admin.action(description="Verify")
    def verify(self, request, queryset):
        from .documents import review

        for doc in queryset.select_related("partner__category__partner_type"):
            review(doc, True)
        self.message_user(request, f"{queryset.count()} document(s) verified.")

    @admin.action(description="Reject")
    def reject(self, request, queryset):
        from .documents import review

        for doc in queryset.select_related("partner__category__partner_type"):
            review(doc, False, "Click couldn’t verify this document. Submit a clear, valid copy.")
        self.message_user(request, f"{queryset.count()} document(s) rejected.")


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = ["partner_code", "business_name", "partner_type", "category", "status", "granted_capabilities", "is_available",
                    "created_at"]
    list_filter = ["status", "partner_type", "category"]
    search_fields = ["partner_code", "business_name", "memberships__user__phone"]
    readonly_fields = ["partner_code", "status", "profile_completed_at"]
    inlines = [ProfileInline, AddressInline, MembershipInline, StoreLinkInline, VenueLinkInline, VerificationInline, DocumentInline,
               StatusEventInline, AvailabilityInline]
    actions = ["approve_verification", "reject_verification"]

    @admin.display(description="Capabilities")
    def granted_capabilities(self, partner):
        """What Click has granted (category defaults unless staff set an explicit list in `capabilities`)."""
        caps = services.capabilities_of(partner)
        return ", ".join(c["label"] for c in caps) + ("" if partner.capabilities is not None else " (defaults)") if caps else "None"

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
