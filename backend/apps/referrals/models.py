"""
Click. referrals. A customer shares their code; a new customer who signs up with it is their referral. Rewards are
given only when the new customer's first order is delivered, once, within the monthly cap — all decided here,
never by the app.
"""

from __future__ import annotations

import secrets

from django.db import models

from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(7))


class ReferralCode(BaseModel):
    customer = models.OneToOneField(CustomerProfile, on_delete=models.CASCADE, related_name="referral_code")
    code = models.CharField(max_length=12, unique=True, default=new_code)


class Referral(BaseModel):
    class Status(models.TextChoices):
        JOINED = "joined", "Joined — waiting for their first order"
        REWARDED = "rewarded", "Rewarded"
        NOT_ELIGIBLE = "not_eligible", "Not eligible"

    referrer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="referrals_made")
    referee = models.OneToOneField(CustomerProfile, on_delete=models.CASCADE, related_name="referred_by",
                                   help_text="A customer can be referred once, only when their account is created.")
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.JOINED)
    reason = models.CharField(max_length=160, blank=True)
    rewarded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
