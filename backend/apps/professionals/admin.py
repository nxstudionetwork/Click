from django.contrib import admin

from . import lifecycle
from .models import (
    ProviderAvailability, ProviderCertificate, ProviderJobPrice, ProviderPortfolio, ProviderProfile, ProviderService, ServiceBooking,
    ServiceCategory, ServiceJob, ServiceNeed, ServiceOffer, ServiceQuote, ServiceReview, ServiceStatusEvent,
)


class JobInline(admin.TabularInline):
    model = ServiceJob
    extra = 0
    fields = ["name", "slug", "pricing", "price", "min_hours", "inspection_fee", "duration_minutes", "instant", "schedulable", "position", "is_active"]


@admin.register(ServiceCategory)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "profession", "group", "position", "is_active"]
    list_editable = ["position", "is_active"]
    list_filter = ["group", "is_active"]
    inlines = [JobInline]


class ServiceInline(admin.TabularInline):
    model = ProviderService
    extra = 0


class HoursInline(admin.TabularInline):
    model = ProviderAvailability
    extra = 0


class CertInline(admin.TabularInline):
    model = ProviderCertificate
    extra = 0


class PriceInline(admin.TabularInline):
    model = ProviderJobPrice
    extra = 0


@admin.register(ProviderProfile)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ["partner", "category", "experience_years", "rating_average", "rating_count", "jobs_completed", "is_listed"]
    list_filter = ["category", "is_listed"]
    readonly_fields = ["rating_average", "rating_count", "jobs_completed"]
    inlines = [ServiceInline, HoursInline, PriceInline, CertInline]


class EventInline(admin.TabularInline):
    model = ServiceStatusEvent
    extra = 0
    readonly_fields = ["from_status", "to_status", "note", "created_at"]


class QuoteInline(admin.TabularInline):
    model = ServiceQuote
    extra = 0
    readonly_fields = ["amount", "note", "status", "decided_at"]


@admin.register(ServiceBooking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ["number", "customer", "job", "provider", "mode", "status", "agreed_amount", "total", "created_at"]
    list_filter = ["status", "mode", "category"]
    search_fields = ["number"]
    inlines = [QuoteInline, EventInline]


@admin.register(ServiceReview)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ["provider", "overall", "status", "created_at"]
    list_filter = ["status"]
    actions = ["hide", "publish"]

    @admin.action(description="Hide selected reviews")
    def hide(self, request, qs):
        for r in qs:
            r.status = "hidden"
            r.save(update_fields=["status", "updated_at"])
            lifecycle.recompute(r.provider_id)

    @admin.action(description="Publish selected reviews")
    def publish(self, request, qs):
        for r in qs:
            r.status = "published"
            r.save(update_fields=["status", "updated_at"])
            lifecycle.recompute(r.provider_id)


@admin.register(ServiceNeed)
class NeedAdmin(admin.ModelAdmin):
    list_display = ["text", "customer", "status", "created_at"]
    list_filter = ["status"]
    list_editable = ["status"]


admin.site.register(ServiceOffer)
admin.site.register(ProviderPortfolio)
