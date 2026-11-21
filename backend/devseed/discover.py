"""Development-only sponsored campaigns for Discover, promoting real partner listings (never loaded in production)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal as D

from django.utils import timezone


def seed_discover(log) -> None:
    from apps.discover.models import AdCampaign, DiscoverConfig
    from apps.hotels.models import HotelProperty
    from apps.partners.models import PartnerStore

    now = timezone.now()
    if not DiscoverConfig.objects.exists():
        DiscoverConfig.objects.create()
    n = 0
    for ps in PartnerStore.objects.select_related("partner", "store").filter(partner__status="active")[:3]:
        s = ps.store
        service = {"restaurant": "food", "grocery": "groceries", "retail": "shop"}.get(s.store_type, "shop")
        AdCampaign.objects.update_or_create(partner=ps.partner, name=f"{s.name} · Discover", defaults=dict(
            placement="feed", pricing="cpc", max_bid=D("6.00"), daily_budget=D("300"), total_budget=D("5000"), status="active",
            starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=30), target_type="store", target_id=s.id, services=[service],
            headline="", frequency_cap=3))
        AdCampaign.objects.update_or_create(partner=ps.partner, name=f"{s.name} · Search", defaults=dict(
            placement="search", pricing="cpc", max_bid=D("4.00"), daily_budget=D("200"), total_budget=D("3000"), status="active",
            starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=30), target_type="store", target_id=s.id, services=[service], frequency_cap=5))
        n += 2
    for h in HotelProperty.objects.filter(is_listed=True).select_related("partner")[:2]:
        AdCampaign.objects.update_or_create(partner=h.partner, name=f"{h.partner.business_name} · Discover", defaults=dict(
            placement="feed", pricing="cpm", max_bid=D("80.00"), daily_budget=D("250"), total_budget=D("4000"), status="active",
            starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=21), target_type="hotel", target_id=h.id, services=["hotels"], frequency_cap=2))
        n += 1
    log(f"discover: {n} sponsored campaigns for real partner listings")
