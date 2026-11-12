"""
Development seed for Wallet cashback, Rewards (catalog, missions, a campaign) — never loaded in production. Values are
sample business rules in the shape Click. would configure them. Also tidies wallet rows left by older seeds (an
unlabelled test credit becomes the opening balance; promo credit gets the promo bucket and an expiry).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal as D

from django.utils import timezone

CATALOG = [  # title, points, value, valid days, min tier
    ("₹50 Click. Wallet credit", 500, "50", 90, ""), ("₹100 Click. Wallet credit", 1000, "100", 90, ""),
    ("₹250 Click. Wallet credit", 2400, "250", 90, ""), ("₹500 Click. Wallet credit", 4600, "500", 120, "silver"),
    ("₹1,000 Click. Wallet credit", 8800, "1000", 180, "gold"),
]
MISSIONS = [  # code, title, description, metric, target, points, service, days (None = no end)
    ("first-ride", "First Ride", "Complete your first Click. ride", "rides", 1, 100, "ride", None),
    ("food-explorer", "Food Explorer", "Order from 3 different restaurants", "restaurants", 3, 300, "food", 30),
    ("click-traveller", "Click. Traveller", "Complete a journey with Click. Travel", "travel", 1, 500, "travel", None),
    ("weekend-stay", "Weekend Away", "Complete a hotel stay", "stays", 1, 400, "hotels", None),
    ("click-explorer", "Click. Explorer", "Use 4 different Click. services", "services_used", 4, 500, "explore", 60),
    ("complete-profile", "Complete your profile", "Add your name, email and an address", "profile", 1, 50, "profile", None),
    ("shop-and-earn", "Regular", "Complete 5 orders", "orders", 5, 200, "shop", 30),
]


def seed_money(profile, log) -> None:
    from apps.rewards.models import RewardCampaign, RewardCatalogItem, RewardMission
    from apps.wallet.models import CashbackOffer, WalletTransaction as T

    now = timezone.now()
    T.objects.filter(description__icontains="MOCK DATA").update(kind=T.Kind.ADJUSTMENT, bucket="cash", description="Opening balance")
    T.objects.filter(kind=T.Kind.PROMO, expires_at__isnull=True).update(bucket="promo", expires_at=now + timedelta(days=60))
    for i, (title, pts, value, days, tier) in enumerate(CATALOG):
        RewardCatalogItem.objects.update_or_create(title=title, defaults=dict(
            points_cost=pts, value=D(value), credit_valid_days=days, min_tier=tier, position=i, is_active=True,
            description="Added to your Click. Wallet as promotional credit as soon as you redeem.",
            terms=f"Credit is valid for {days} days, is spent before your cash balance and can’t be withdrawn. Points aren’t refunded once redeemed."))
    for i, (code, title, desc, metric, target, pts, service, days) in enumerate(MISSIONS):
        RewardMission.objects.update_or_create(code=code, defaults=dict(
            title=title, description=desc, metric=metric, target=target, points=pts, service=service, position=i, is_active=True,
            starts_at=None, ends_at=now + timedelta(days=days) if days else None))
    RewardCampaign.objects.update_or_create(title="Double points on Food", defaults=dict(
        description="2× points on delivered Food orders", service="food", multiplier=D("2.0"), starts_at=now - timedelta(days=1),
        ends_at=now + timedelta(days=10), is_active=True))
    for title, service, pct, cap, minimum in [("5% cashback on Shop with Click. Wallet", "shop", 5, "150", "500"),
                                              ("10% cashback on Travel with Click. Wallet", "travel", 10, "200", "1000")]:
        CashbackOffer.objects.update_or_create(title=title, defaults=dict(
            service=service, percent=pct, max_cashback=D(cap), min_amount=D(minimum), wallet_payment_only=True, credit_valid_days=60,
            starts_at=now - timedelta(days=2), ends_at=now + timedelta(days=45), is_active=True))
    log(f"money: {len(CATALOG)} reward catalog items, {len(MISSIONS)} missions, 1 points campaign, 2 cashback offers")
