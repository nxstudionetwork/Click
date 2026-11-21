"""Discover ads: only approved campaigns of verified partners for their own open listings, labelled, quality-gated,
budget- and frequency-capped, charged only from signed serve tokens (once), and hideable by the customer."""

from datetime import timedelta
from decimal import Decimal as D

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.discover import engine
from apps.discover.models import AdCampaign, AdEvent
from apps.partners.models import Partner, PartnerStore

pytestmark = pytest.mark.django_db


@pytest.fixture
def campaign(store):
    from apps.partners.catalog import apply_catalog
    from apps.partners.models import PartnerCategory, PartnerType

    if not PartnerType.objects.exists():
        apply_catalog(PartnerType, PartnerCategory)
    p = Partner.objects.create(business_name="Test Kitchen Pvt", status="active", category=(cat := PartnerCategory.objects.first()), partner_type=cat.partner_type)
    Partner.objects.filter(pk=p.pk).update(partner_code="CLK-PT-999001")
    p.refresh_from_db()
    PartnerStore.objects.create(partner=p, store=store)
    store.rating_average, store.rating_count = D("4.5"), 10
    store.save()
    now = timezone.now()
    return AdCampaign.objects.create(partner=p, name="Test", placement="feed", pricing="cpc", max_bid=D("5"), daily_budget=D("100"), total_budget=D("10"),
                                     status="active", starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=1), target_type="store",
                                     target_id=store.id, services=["food"], frequency_cap=2)


def serve(customer, city=""):
    return engine.auction(customer, f"c:{customer.id}" if customer else "a:x", service="food", city=city, placement="feed", slots=3)


def test_only_eligible_campaigns_are_served_and_labelled(campaign, customer, store):
    ads = serve(customer.customer_profile)
    assert len(ads) == 1 and ads[0]["sponsored"] and ads[0]["advertiser"] == "Test Kitchen Pvt" and ads[0]["link"] == f"/stores/{store.slug}"
    for field, value in [("status", "in_review"), ("ends_at", timezone.now() - timedelta(minutes=1))]:
        old = getattr(campaign, field)
        AdCampaign.objects.filter(pk=campaign.pk).update(**{field: value})
        assert serve(customer.customer_profile) == []
        AdCampaign.objects.filter(pk=campaign.pk).update(**{field: old})
    Partner.objects.filter(pk=campaign.partner_id).update(status="suspended")
    assert serve(customer.customer_profile) == []  # unverified / suspended partners never run ads
    Partner.objects.filter(pk=campaign.partner_id).update(status="active")
    store.rating_average = D("2.0")
    store.save()
    assert serve(customer.customer_profile) == []  # below the quality threshold, whatever the bid
    store.rating_average = D("4.5")
    store.save()
    store.is_accepting_orders = False
    store.save()
    assert serve(customer.customer_profile) == []  # a closed listing isn't advertised


def test_charging_is_server_side_once_and_capped(campaign, customer):
    c = customer.customer_profile
    viewer = f"c:{c.id}"
    ad = serve(c)[0]
    assert engine.track(ad["token"], "click", viewer) is False  # no click without a counted impression
    assert engine.track(ad["token"], "impression", "c:someone-else") is False  # token bound to its viewer
    assert engine.track(ad["token"], "impression", viewer) and not engine.track(ad["token"], "impression", viewer)
    assert engine.track(ad["token"], "click", viewer) and not engine.track(ad["token"], "click", viewer)
    campaign.refresh_from_db()
    assert D("0") < campaign.spent <= campaign.max_bid
    assert engine.track("forged", "click", viewer) is False
    ad2 = serve(c)[0]
    engine.track(ad2["token"], "impression", viewer)
    assert serve(c) == []  # frequency cap 2 per day reached
    AdEvent.objects.all().delete()
    AdCampaign.objects.filter(pk=campaign.pk).update(spent=D("10"))
    assert serve(c) == []  # total budget used


def test_customer_can_hide_an_ad(campaign, customer):
    api = APIClient()
    api.force_authenticate(customer)
    assert api.post("/api/v1/customer/discover/hide", {"campaign": str(campaign.id)}).status_code == 200
    assert serve(customer.customer_profile) == []
    feed = api.get("/api/v1/discover").json()
    assert all(not card.get("sponsored") for s in feed["sections"] for card in s["cards"])
