from django.contrib import admin

from .models import Booking, Event, Show, Venue


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["title", "kind", "status", "release_date"]
    list_filter = ["kind", "status"]
    search_fields = ["title"]
    prepopulated_fields = {"slug": ["title"]}


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "city"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Show)
class ShowAdmin(admin.ModelAdmin):
    list_display = ["event", "venue", "starts_at", "status"]
    list_filter = ["status", "venue"]


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ["reference", "customer", "show", "status", "total", "created_at"]
    list_filter = ["status"]
    search_fields = ["reference", "customer__user__email"]
