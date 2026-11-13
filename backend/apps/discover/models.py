"""
Click. Discover: sponsored placements beside organic discovery.

AdCampaign      what a partner promotes (one of its own listings), where (placement, services, cities, hours), how it
                pays (pricing model + max bid) and its budget. Only approved campaigns of verified partners run.
AdEvent         an impression / click / conversion of a served placement, deduplicated per serve token; costs are
                charged to the campaign from here (never from the client).
AdHide          a customer hid an ad; it isn't shown to them again.
DiscoverConfig  the knobs Click. operations control: auction weights and thresholds, sponsored density.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile


class AdCampaign(BaseModel):
    class Placement(models.TextChoices):
        FEED = "feed", "Sponsored discovery card"
        TOP = "top", "Sponsored top placement"
        CATEGORY = "category", "Sponsored category placement"
        SEARCH = "search", "Sponsored search result"
        LAUNCH = "launch", "Sponsored launch"
        OFFER = "offer", "Sponsored offer"

    class Pricing(models.TextChoices):
        CPC = "cpc", "Per click"
        CPM = "cpm", "Per 1,000 impressions"
        CPA = "cpa", "Per order / booking"
        FLAT = "flat", "Fixed daily placement"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        IN_REVIEW = "in_review", "In review"
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        REJECTED = "rejected", "Rejected"
        INELIGIBLE = "ineligible", "Ineligible (quality or policy)"
        ENDED = "ended", "Ended"

    class Target(models.TextChoices):
        STORE = "store", "Store / restaurant"
        HOTEL = "hotel", "Hotel"
        ATTRACTION = "attraction", "Place / experience"
        EVENT_PROVIDER = "event_provider", "Event team / venue"
        PROFESSIONAL = "professional", "Service professional"

    partner = models.ForeignKey("partners.Partner", on_delete=models.CASCADE, related_name="ad_campaigns")
    name = models.CharField(max_length=100)
    placement = models.CharField(max_length=10, choices=Placement.choices, default=Placement.FEED)
    pricing = models.CharField(max_length=4, choices=Pricing.choices, default=Pricing.CPC)
    max_bid = models.DecimalField(max_digits=8, decimal_places=2, help_text="₹ per click / per 1,000 impressions / per order, or per day for flat.")
    daily_budget = models.DecimalField(max_digits=10, decimal_places=2)
    total_budget = models.DecimalField(max_digits=12, decimal_places=2)
    spent = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    status_reason = models.CharField(max_length=200, blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    target_type = models.CharField(max_length=16, choices=Target.choices)
    target_id = models.UUIDField(help_text="The partner's own listing being promoted (checked on save).")
    services = models.JSONField(default=list, blank=True, help_text="Discover sections it may appear in: food, groceries, shop, hotels, …")
    cities = models.JSONField(default=list, blank=True, help_text="Empty = everywhere the listing serves.")
    hours = models.JSONField(default=list, blank=True, help_text="Local hours it may run, e.g. [18, 19, 20, 21]. Empty = all day.")
    headline = models.CharField(max_length=80, blank=True, help_text="Short line shown on the card (reviewed).")
    frequency_cap = models.PositiveSmallIntegerField(default=3, help_text="Max impressions per customer per day.")

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(condition=Q(max_bid__gt=0, daily_budget__gt=0, total_budget__gt=0), name="ad_campaign_positive_money")]


class AdEvent(BaseModel):
    class Kind(models.TextChoices):
        IMPRESSION = "impression", "Impression"
        CLICK = "click", "Click"
        CONVERSION = "conversion", "Conversion"

    campaign = models.ForeignKey(AdCampaign, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    serve_id = models.CharField(max_length=40, help_text="The signed serve token's id; one event of each kind per serve.")
    viewer = models.CharField(max_length=64, help_text="Customer id, or a hashed anonymous key.")
    placement = models.CharField(max_length=10)
    cost = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal("0"))

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["serve_id", "kind"], name="ad_event_once_per_serve")]
        indexes = [models.Index(fields=["campaign", "kind", "-created_at"], name="ad_event_campaign_idx"),
                   models.Index(fields=["viewer", "campaign", "-created_at"], name="ad_event_viewer_idx")]


class AdHide(BaseModel):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="hidden_ads")
    campaign = models.ForeignKey(AdCampaign, on_delete=models.CASCADE, related_name="hides")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["customer", "campaign"], name="ad_hide_once")]


class DiscoverConfig(BaseModel):
    """One row (the latest is used). Defaults keep Discover mostly organic."""

    max_sponsored = models.PositiveSmallIntegerField(default=3)
    min_gap = models.PositiveSmallIntegerField(default=4, help_text="Organic cards between two sponsored cards.")
    max_share = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal("0.20"), help_text="Max sponsored share of the feed.")
    min_relevance = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal("0.40"))
    min_quality = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal("0.60"))
    weight_relevance = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("1.00"))
    weight_quality = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("1.00"))
    weight_engagement = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("1.00"))

    @classmethod
    def current(cls) -> "DiscoverConfig":
        return cls.objects.order_by("-created_at").first() or cls()
