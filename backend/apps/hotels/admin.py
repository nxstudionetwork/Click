"""Click. Hotels in the Django admin — today's Business OS surface: destinations, amenities, property approval
(listing), rooms and rates, inventory, offers, bookings and review moderation."""

from django.contrib import admin

from . import booking
from .models import (
    Amenity, Destination, HotelBooking, HotelImage, HotelOffer, HotelProperty, HotelReview, Landmark, RatePlan, RoomInventory, RoomType, StatusEvent,
)


class LandmarkInline(admin.TabularInline):
    model = Landmark
    extra = 0


@admin.register(Destination)
class DestinationAdmin(admin.ModelAdmin):
    list_display = ["name", "region", "kind", "parent", "position", "is_active"]
    list_editable = ["position", "is_active"]
    prepopulated_fields = {"slug": ["name"]}
    inlines = [LandmarkInline]


@admin.register(Amenity)
class AmenityAdmin(admin.ModelAdmin):
    list_display = ["name", "scope", "filterable", "position"]
    list_editable = ["filterable", "position"]


class RoomInline(admin.TabularInline):
    model = RoomType
    extra = 0
    fields = ["name", "room_class", "beds", "max_adults", "max_children", "max_occupancy", "size_sqm", "total_units", "is_active"]


class ImageInline(admin.TabularInline):
    model = HotelImage
    extra = 0
    fields = ["category", "room_type", "caption", "position"]


@admin.register(HotelProperty)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ["__str__", "destination", "property_type", "star_rating", "is_listed", "rating_average", "rating_count"]
    list_editable = ["is_listed"]
    list_filter = ["property_type", "destination", "is_listed"]
    search_fields = ["partner__business_name", "area"]
    filter_horizontal = ["amenities"]
    readonly_fields = ["rating_average", "rating_count"]
    inlines = [RoomInline, ImageInline]


class RateInline(admin.TabularInline):
    model = RatePlan
    extra = 0


@admin.register(RoomType)
class RoomTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "property", "room_class", "total_units", "is_active"]
    list_filter = ["room_class"]
    filter_horizontal = ["amenities"]
    inlines = [RateInline]


@admin.register(RoomInventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ["room_type", "date", "units", "closed", "price_override"]
    list_filter = ["closed"]
    date_hierarchy = "date"


@admin.register(HotelOffer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ["title", "kind", "percent", "property", "starts_at", "ends_at", "is_active"]
    list_filter = ["kind", "is_active"]


class EventInline(admin.TabularInline):
    model = StatusEvent
    extra = 0
    readonly_fields = ["to", "note", "created_at"]


@admin.register(HotelBooking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ["number", "property", "check_in", "check_out", "status", "payment_status", "total"]
    list_filter = ["status", "payment_status"]
    search_fields = ["number", "guest_name"]
    readonly_fields = ["number", "customer", "nightly", "room_total", "discount", "tax", "total", "refunded"]
    inlines = [EventInline]


@admin.register(HotelReview)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ["property", "overall", "is_published", "created_at"]
    list_editable = ["is_published"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        booking.recompute(obj.property)
