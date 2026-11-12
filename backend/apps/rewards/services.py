from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify

from .models import RewardTransaction


def points_for_amount(amount) -> int:
    """CLICK_REWARD_POINTS_PER_100 points per 100 currency units of item subtotal."""
    return int(amount * settings.CLICK_REWARD_POINTS_PER_100 // 100)


def award_for_delivered_order(order) -> RewardTransaction | None:
    points = points_for_amount(order.subtotal)
    if points <= 0:
        return None
    try:
        with transaction.atomic():
            txn = RewardTransaction.objects.create(
                customer=order.customer, kind=RewardTransaction.Kind.EARN, points=points, order=order,
                description=f"Order {order.number}",
                expires_at=timezone.now() + timedelta(days=settings.CLICK_REWARD_EXPIRY_DAYS),
            )
    except IntegrityError:  # already awarded
        return None
    notify(order.customer, NotificationCategory.REWARDS, f"You earned {points} Click points",
           f"For order {order.number}.", "/rewards")
    return txn


def award_points(customer, amount, reference: str, description: str) -> RewardTransaction | None:
    """Points on a completed booking (travel, experiences…), once per reference, by the same rule as orders."""
    points = points_for_amount(amount)
    if points <= 0:
        return None
    try:
        with transaction.atomic():
            txn = RewardTransaction.objects.create(customer=customer, kind=RewardTransaction.Kind.EARN, points=points, reference=reference,
                                                   description=description[:200],
                                                   expires_at=timezone.now() + timedelta(days=settings.CLICK_REWARD_EXPIRY_DAYS))
    except IntegrityError:  # already awarded
        return None
    notify(customer, NotificationCategory.REWARDS, f"You earned {points} Click points", f"For {description}.", "/rewards")
    return txn


def balance(customer) -> dict:
    qs = RewardTransaction.objects.filter(customer=customer)
    earned = qs.filter(points__gt=0).aggregate(s=Sum("points"))["s"] or 0
    used = -(qs.filter(points__lt=0).aggregate(s=Sum("points"))["s"] or 0)
    return {"balance": earned - used, "earned": earned, "used": used}
