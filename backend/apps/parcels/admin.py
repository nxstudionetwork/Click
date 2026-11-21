from django.contrib import admin

from .models import (
    ParcelCategory, ParcelJobOffer, ParcelOrder, ParcelProof, ParcelRule, ParcelService, ParcelServiceArea, ParcelStatusEvent,
    ParcelStop, ParcelVehicle, SavedRecipient,
)


@admin.register(ParcelServiceArea)
class AreaAdmin(admin.ModelAdmin):
    list_display = ["name", "city", "radius_km", "is_active"]


@admin.register(ParcelService)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "price_multiplier", "max_distance_km", "open_hour", "close_hour", "is_active", "position"]
    filter_horizontal = ["vehicles"]


@admin.register(ParcelVehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "max_weight_kg", "base_fare", "per_km", "minimum_fare", "is_active", "position"]


@admin.register(ParcelCategory)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["label", "code", "is_allowed", "requires_value", "position"]
    list_editable = ["is_allowed", "requires_value", "position"]


@admin.register(ParcelRule)
class RuleAdmin(admin.ModelAdmin):
    list_display = ["text", "kind", "service", "is_active", "position"]


class StopInline(admin.TabularInline):
    model = ParcelStop
    extra = 0


class EventInline(admin.TabularInline):
    model = ParcelStatusEvent
    extra = 0
    readonly_fields = ["from_status", "to_status", "note", "actor", "created_at"]


class ProofInline(admin.TabularInline):
    model = ParcelProof
    extra = 0
    readonly_fields = ["kind", "method", "partner", "lat", "lng", "location_reported_at", "created_at"]


@admin.register(ParcelOrder)
class ParcelAdmin(admin.ModelAdmin):
    list_display = ["number", "customer", "mode", "service", "vehicle", "status", "total", "partner", "created_at"]
    list_filter = ["status", "service", "vehicle", "mode"]
    search_fields = ["number", "pickup_label", "drop_label"]
    readonly_fields = ["number", "pickup_pin", "delivery_pin", "idempotency_key"]
    inlines = [StopInline, EventInline, ProofInline]


admin.site.register(SavedRecipient)
admin.site.register(ParcelJobOffer)
