from django.contrib import admin

from . import engagement
from .models import (Booking, BookingConcession, ConcessionItem, Credit, Event, Screen, SeatHold, Show, ShowFeature, ShowInterest, ShowOffer,
                     ShowReview, Venue)


class CreditInline(admin.TabularInline):
    model = Credit
    extra = 0


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["title", "kind", "status", "release_date", "rating_average", "rating_count"]
    list_filter = ["kind", "status"]
    search_fields = ["title"]
    prepopulated_fields = {"slug": ["title"]}
    readonly_fields = ["rating_average", "rating_count"]
    inlines = [CreditInline]


class ScreenInline(admin.TabularInline):
    model = Screen
    extra = 0


class ConcessionInline(admin.TabularInline):
    model = ConcessionItem
    extra = 0


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "city", "locality"]
    search_fields = ["name", "locality"]
    prepopulated_fields = {"slug": ["name"]}
    inlines = [ScreenInline, ConcessionInline]


@admin.register(Show)
class ShowAdmin(admin.ModelAdmin):
    list_display = ["event", "venue", "screen_ref", "starts_at", "format", "language", "status"]
    list_filter = ["status", "venue", "format"]
    autocomplete_fields = ["event"]


class BookingConcessionInline(admin.TabularInline):
    model = BookingConcession
    extra = 0
    readonly_fields = ["name", "unit_price", "quantity", "line_total"]


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ["reference", "customer", "show", "status", "total", "checked_in_at", "created_at"]
    list_filter = ["status"]
    search_fields = ["reference", "customer__user__email"]
    inlines = [BookingConcessionInline]


@admin.register(ShowOffer)
class ShowOfferAdmin(admin.ModelAdmin):
    list_display = ["title", "discount_type", "discount_value", "venue", "event", "payment_method", "ends_at", "is_active"]
    list_filter = ["is_active", "discount_type"]


@admin.register(ShowFeature)
class ShowFeatureAdmin(admin.ModelAdmin):
    list_display = ["event", "headline", "priority", "starts_at", "ends_at", "is_active"]
    autocomplete_fields = ["event"]


@admin.register(ShowReview)
class ShowReviewAdmin(admin.ModelAdmin):
    """Moderation: hiding removes a review from the title page and its rating; nothing is deleted."""

    list_display = ["event", "customer", "rating", "status", "created_at"]
    list_filter = ["status", "rating"]
    search_fields = ["event__title", "body"]
    readonly_fields = ["event", "customer", "booking", "rating", "body"]
    actions = ["hide", "publish"]

    def _set(self, queryset, status):
        ids = set(queryset.values_list("event_id", flat=True))
        queryset.update(status=status)
        for eid in ids:
            engagement.recompute_rating(eid)

    @admin.action(description="Hide (moderation)")
    def hide(self, request, queryset):
        self._set(queryset, ShowReview.Status.HIDDEN)

    @admin.action(description="Publish")
    def publish(self, request, queryset):
        self._set(queryset, ShowReview.Status.PUBLISHED)


admin.site.register(ShowInterest)
admin.site.register(SeatHold)
