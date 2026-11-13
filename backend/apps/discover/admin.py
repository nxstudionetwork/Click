"""Until Business OS has its advertiser screens, Click. operations review and approve campaigns here."""

from django.contrib import admin

from .models import AdCampaign, AdEvent, DiscoverConfig


@admin.register(AdCampaign)
class AdCampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "partner", "placement", "pricing", "max_bid", "daily_budget", "spent", "total_budget", "status", "starts_at", "ends_at")
    list_filter = ("status", "placement", "pricing", "target_type")
    search_fields = ("name", "partner__business_name", "partner__partner_code")
    readonly_fields = ("spent",)


@admin.register(AdEvent)
class AdEventAdmin(admin.ModelAdmin):
    list_display = ("campaign", "kind", "placement", "cost", "created_at")
    list_filter = ("kind", "placement")
    readonly_fields = [f.name for f in AdEvent._meta.fields]


admin.site.register(DiscoverConfig)
