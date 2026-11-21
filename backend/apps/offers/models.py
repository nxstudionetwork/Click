"""
Click. Offers: the central place customers discover, save and claim promotions from every service. The offers themselves
stay in each service (StoreOffer, HotelOffer, ShowOffer, ServiceOffer, RideOffer, TravelOffer, ExperienceOffer,
CashbackOffer, RewardCampaign) — where they are validated and applied at checkout. This app only adds what is the
customer's own: saved offers and claimed coupon codes. An offer is addressed as "<source>:<id>".
"""

from django.db import models

from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile


class OfferSave(BaseModel):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="saved_offers")
    offer_ref = models.CharField(max_length=60)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["customer", "offer_ref"], name="offers_save_unique")]


class OfferClaim(BaseModel):
    """A coupon the customer claimed: it's offered at the matching checkout; the service still validates it there."""

    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="claimed_offers")
    offer_ref = models.CharField(max_length=60)
    service = models.CharField(max_length=20)
    code = models.CharField(max_length=20)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["customer", "offer_ref"], name="offers_claim_unique")]
