"""Referral rules (amounts and caps from settings, so Business OS can own them later)."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify

from .models import Referral, ReferralCode


def code_for(customer) -> ReferralCode:
    obj, _ = ReferralCode.objects.get_or_create(customer=customer)
    return obj


def lookup(code: str) -> ReferralCode | None:
    code = (code or "").strip().upper()
    if not 4 <= len(code) <= 12:
        return None
    return ReferralCode.objects.select_related("customer__user").filter(code=code, customer__user__is_active=True).first()


def attach(referee, code: str) -> Referral | None:
    """At signup only. An invalid or own code is simply ignored (signup never fails because of a code)."""
    rc = lookup(code)
    if rc is None or rc.customer_id == referee.id:
        return None
    try:
        with transaction.atomic():
            r = Referral.objects.create(referrer=rc.customer, referee=referee)
    except IntegrityError:
        return None
    notify(rc.customer, NotificationCategory.REWARDS, "Someone joined with your code",
           f"You’ll both get points when their first order is delivered.", "/referrals")
    return r


def qualify(order) -> bool:
    """Called when an order is delivered: the referee's first delivered order rewards both, once."""
    from apps.rewards.models import RewardTransaction as R

    r = Referral.objects.select_related("referrer__user", "referee").filter(referee=order.customer, status=Referral.Status.JOINED).first()
    if r is None or order.customer.orders.filter(status="delivered").exclude(pk=order.pk).exists():
        return False
    if not r.referrer.user.is_active:
        r.status, r.reason = Referral.Status.NOT_ELIGIBLE, "Referrer account closed"
        r.save(update_fields=["status", "reason", "updated_at"])
        return False
    month = timezone.now() - timedelta(days=30)
    if Referral.objects.filter(referrer=r.referrer, status=Referral.Status.REWARDED, rewarded_at__gte=month).count() >= settings.CLICK_REFERRAL_MONTHLY_CAP:
        r.status, r.reason = Referral.Status.NOT_ELIGIBLE, "Monthly referral limit reached"
        r.save(update_fields=["status", "reason", "updated_at"])
        return False
    expires = timezone.now() + timedelta(days=settings.CLICK_REWARD_EXPIRY_DAYS)
    try:
        with transaction.atomic():
            R.objects.create(customer=r.referrer, kind=R.Kind.EARN, points=settings.CLICK_REFERRAL_REFERRER_POINTS, reference=f"referral:{r.id}:referrer",
                             description="Referral reward", expires_at=expires)
            R.objects.create(customer=r.referee, kind=R.Kind.EARN, points=settings.CLICK_REFERRAL_REFEREE_POINTS, reference=f"referral:{r.id}:referee",
                             description="Welcome reward for joining with a referral", expires_at=expires)
            r.status, r.rewarded_at = Referral.Status.REWARDED, timezone.now()
            r.save(update_fields=["status", "rewarded_at", "updated_at"])
    except IntegrityError:
        return False
    notify(r.referrer, NotificationCategory.REWARDS, f"+{settings.CLICK_REFERRAL_REFERRER_POINTS} points — your referral ordered", "Thanks for spreading the word.", "/referrals")
    notify(r.referee, NotificationCategory.REWARDS, f"+{settings.CLICK_REFERRAL_REFEREE_POINTS} welcome points", "For joining Click. with a friend’s code.", "/rewards")
    return True
