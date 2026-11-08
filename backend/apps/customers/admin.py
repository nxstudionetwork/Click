from django.contrib import admin

from .models import Address, CustomerProfile


class AddressInline(admin.TabularInline):
    model = Address
    extra = 0


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "created_at"]
    search_fields = ["user__email"]  # required for wallet admin autocomplete
    inlines = [AddressInline]
