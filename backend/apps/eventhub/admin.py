"""Click. Events in the Django admin — today's Business OS surface: registries, provider review (listing / featuring),
venues, packages, plans, quotes, bookings and review moderation."""

from django.contrib import admin

from . import lifecycle
from .models import (
    ChecklistItem, Enquiry, EventBooking, EventPackage, EventPlan, EventProvider, EventReview, EventService, EventType, Message, Milestone,
    PackageAddon, PortfolioItem, ProviderBlockedDate, Quote, StatusEvent, VenueDetails,
)


@admin.register(EventType)
class EventTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "group", "position", "in_planner", "is_active"]
    list_editable = ["position", "in_planner", "is_active"]
    list_filter = ["group", "is_active"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(EventService)
class EventServiceAdmin(admin.ModelAdmin):
    list_display = ["name", "group", "position", "is_active"]
    list_editable = ["position", "is_active"]
    list_filter = ["group"]
    prepopulated_fields = {"slug": ["name"]}


class VenueInline(admin.StackedInline):
    model = VenueDetails
    extra = 0


class BlockedInline(admin.TabularInline):
    model = ProviderBlockedDate
    extra = 0


class PortfolioInline(admin.TabularInline):
    model = PortfolioItem
    extra = 0
    fields = ["caption", "event_type", "position"]


@admin.register(EventProvider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ["__str__", "kind", "area", "is_listed", "is_featured", "rating_average", "rating_count", "events_completed"]
    list_editable = ["is_listed", "is_featured"]
    list_filter = ["kind", "is_listed", "is_featured"]
    search_fields = ["partner__business_name", "area"]
    filter_horizontal = ["services", "event_types"]
    readonly_fields = ["rating_average", "rating_count", "events_completed"]
    inlines = [VenueInline, BlockedInline, PortfolioInline]
    actions = ["recompute"]

    @admin.action(description="Recompute ratings and counts from bookings")
    def recompute(self, request, qs):
        for p in qs:
            lifecycle.recompute(p)


class AddonInline(admin.TabularInline):
    model = PackageAddon
    extra = 0


@admin.register(EventPackage)
class PackageAdmin(admin.ModelAdmin):
    list_display = ["name", "provider", "basis", "price", "min_guests", "max_guests", "is_active"]
    list_filter = ["basis", "is_active"]
    filter_horizontal = ["services", "event_types"]
    inlines = [AddonInline]


class ChecklistInline(admin.TabularInline):
    model = ChecklistItem
    extra = 0


@admin.register(EventPlan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ["number", "event_type", "date", "guests", "status", "created_at"]
    list_filter = ["status", "event_type"]
    search_fields = ["number"]
    readonly_fields = ["number", "customer"]
    inlines = [ChecklistInline]


class QuoteInline(admin.TabularInline):
    model = Quote
    extra = 0
    readonly_fields = ["version", "amount", "status"]


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0


@admin.register(Enquiry)
class EnquiryAdmin(admin.ModelAdmin):
    list_display = ["plan", "provider", "status", "created_at"]
    list_filter = ["status"]
    inlines = [QuoteInline, MessageInline]


class MilestoneInline(admin.TabularInline):
    model = Milestone
    extra = 0


class StatusInline(admin.TabularInline):
    model = StatusEvent
    extra = 0
    readonly_fields = ["to", "note", "created_at"]


@admin.register(EventBooking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ["number", "provider", "event_date", "status", "payment_status", "total"]
    list_filter = ["status", "payment_status"]
    search_fields = ["number"]
    readonly_fields = ["number", "customer", "plan", "quote", "package", "lines", "subtotal", "tax", "total", "refunded"]
    inlines = [MilestoneInline, StatusInline]


@admin.register(EventReview)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ["provider", "overall", "is_published", "created_at"]
    list_editable = ["is_published"]
    list_filter = ["is_published", "overall"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        lifecycle.recompute(obj.provider)
