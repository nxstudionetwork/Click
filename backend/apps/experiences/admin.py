from django.contrib import admin

from .models import Attraction, AttractionImage, Closure, ExperienceBooking, ExperienceOffer, ExperienceReview, Offering, Price


class OfferingInline(admin.StackedInline):
    model = Offering
    extra = 0


class ImageInline(admin.TabularInline):
    model = AttractionImage
    extra = 0


class ClosureInline(admin.TabularInline):
    model = Closure
    extra = 0


@admin.register(Attraction)
class AttractionAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "group", "city", "bookable", "verified_provider", "provider", "is_listed", "rating_average")
    list_filter = ("group", "kind", "bookable", "is_listed", "city")
    search_fields = ("name", "city", "deity")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [OfferingInline, ImageInline, ClosureInline]


class PriceInline(admin.TabularInline):
    model = Price
    extra = 0


@admin.register(Offering)
class OfferingAdmin(admin.ModelAdmin):
    list_display = ("name", "attraction", "kind", "booking_model", "capacity", "is_active")
    list_filter = ("kind", "booking_model", "is_active")
    inlines = [PriceInline]


@admin.register(ExperienceBooking)
class ExperienceBookingAdmin(admin.ModelAdmin):
    list_display = ("number", "title", "customer", "visit_date", "slot_time", "status", "payment_status", "total")
    list_filter = ("status", "payment_status", "attraction__group")
    search_fields = ("number", "entry_code", "customer__user__phone_number")
    readonly_fields = [f.name for f in ExperienceBooking._meta.fields]


admin.site.register(ExperienceOffer)
admin.site.register(ExperienceReview)
