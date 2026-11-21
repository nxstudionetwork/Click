from django.contrib import admin

from .models import Referral, ReferralCode


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ("referrer", "referee", "status", "created_at", "rewarded_at")
    list_filter = ("status",)


admin.site.register(ReferralCode)
