from django.contrib import admin, messages

from . import booking
from .models import FareClass, Journey, Operator, Passenger, Place, PriceAlert, Service, Stop, TravelBooking, TravelOffer


@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "code", "city", "state", "is_active")
    list_filter = ("kind", "is_active")
    search_fields = ("name", "code", "aliases")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Operator)
class OperatorAdmin(admin.ModelAdmin):
    list_display = ("name", "mode", "code", "source", "status", "rating_average", "rating_count")
    list_filter = ("mode", "source", "status")
    search_fields = ("name", "code")


class StopInline(admin.TabularInline):
    model = Stop
    extra = 0


class FareClassInline(admin.TabularInline):
    model = FareClass
    extra = 0


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("number", "name", "operator", "mode", "vehicle", "is_active")
    list_filter = ("mode", "is_active", "operator")
    search_fields = ("number", "name")
    inlines = [StopInline, FareClassInline]


def _update(request, qs, status, delay=0, notice=""):
    n = sum(booking.operator_update(j, status, delay, notice) for j in qs)
    messages.success(request, f"Updated {qs.count()} run(s); {n} booking(s) notified.")


@admin.register(Journey)
class JourneyAdmin(admin.ModelAdmin):
    list_display = ("service", "date", "status", "delay_minutes", "notice")
    list_filter = ("status", "service__mode")
    date_hierarchy = "date"
    actions = ["delay_30", "cancel_run", "back_on_schedule"]

    @admin.action(description="Running 30 minutes late (notify travellers)")
    def delay_30(self, request, qs):
        _update(request, qs, Journey.Status.DELAYED, 30)

    @admin.action(description="Cancelled by operator (full refunds, notify travellers)")
    def cancel_run(self, request, qs):
        _update(request, qs, Journey.Status.CANCELLED)

    @admin.action(description="Back on schedule")
    def back_on_schedule(self, request, qs):
        _update(request, qs, Journey.Status.SCHEDULED, 0, "Back on schedule.")


class PassengerInline(admin.TabularInline):
    model = Passenger
    extra = 0
    fields = ("position", "name", "age", "gender", "seat", "seat_status", "queue", "fare", "holds_seat")
    readonly_fields = fields
    can_delete = False


@admin.register(TravelBooking)
class TravelBookingAdmin(admin.ModelAdmin):
    list_display = ("number", "pnr", "mode", "customer", "service_label", "departs_at", "status", "payment_status", "total")
    list_filter = ("mode", "status", "payment_status")
    search_fields = ("number", "pnr", "customer__user__phone_number")
    readonly_fields = [f.name for f in TravelBooking._meta.fields]
    inlines = [PassengerInline]


admin.site.register(TravelOffer)
admin.site.register(PriceAlert)
