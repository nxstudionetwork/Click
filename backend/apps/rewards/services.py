"""
The Click. Rewards engine. Points are only ever calculated here, from verified records — never from a client.

  earn       completed order / booking → base points (CLICK_REWARD_POINTS_PER_100 per ₹100) × the customer's tier
             multiplier × the best live campaign multiplier for that service; once per source (unique order / reference)
  lots       earned points expire CLICK_REWARD_EXPIRY_DAYS later; redemptions and expiries use the soonest-expiring
             points first (FIFO), so "expiring soon" is exact
  tiers      by points earned in the last 365 days (CLICK_REWARD_TIERS), each with its earning multiplier
  missions   progress measured from real records since the mission started; completing it awards once
  redeem     catalog item → points deducted and Click. Wallet credit issued in one transaction, idempotent
  reverse    an adjustment linked to the entry it reverses (a refunded order's points come back off)
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.core.api.exceptions import ConflictError, DomainError
from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify

from .models import RewardCampaign, RewardCatalogItem, RewardMission, RewardRedemption, RewardTransaction as R

STORE_SERVICE = {"restaurant": "food", "grocery": "groceries", "retail": "shop"}


def points_for_amount(amount) -> int:
    """CLICK_REWARD_POINTS_PER_100 points per 100 currency units (the base rule, before multipliers)."""
    return int(Decimal(amount) * settings.CLICK_REWARD_POINTS_PER_100 // 100)


# --- tiers -----------------------------------------------------------------------------------------------------------

def tiers() -> list[dict]:
    return [{"code": c, "name": n, "min_points": m, "multiplier": Decimal(x)} for c, n, m, x in settings.CLICK_REWARD_TIERS]


def tier_points(customer) -> int:
    since = timezone.now() - timedelta(days=365)
    return R.objects.filter(customer=customer, kind=R.Kind.EARN, created_at__gte=since).aggregate(s=Sum("points"))["s"] or 0


def tier_of(customer) -> dict:
    pts = tier_points(customer)
    ts = tiers()
    current = [t for t in ts if pts >= t["min_points"]][-1]
    nxt = next((t for t in ts if t["min_points"] > pts), None)
    return {**current, "qualifying_points": pts, "next": nxt, "to_next": (nxt["min_points"] - pts) if nxt else 0}


def campaign_multiplier(service: str) -> tuple[Decimal, RewardCampaign | None]:
    now = timezone.now()
    best = (RewardCampaign.objects.filter(Q(service=service) | Q(service="any"), is_active=True, starts_at__lte=now, ends_at__gt=now)
            .order_by("-multiplier").first())
    return (best.multiplier, best) if best else (Decimal("1"), None)


def preview_points(customer, amount, service: str) -> int:
    """What a purchase of `amount` in `service` would earn now (shown before paying; recomputed when earned)."""
    base = points_for_amount(amount)
    tier_x = tier_of(customer)["multiplier"] if customer else Decimal("1")
    camp_x, _ = campaign_multiplier(service)
    return int(base * tier_x * camp_x)


# --- earning ---------------------------------------------------------------------------------------------------------

def _earn(customer, amount, service: str, description: str, **source) -> R | None:
    base = points_for_amount(amount)
    if base <= 0:
        return None
    t = tier_of(customer)
    camp_x, camp = campaign_multiplier(service)
    points = int(base * t["multiplier"] * camp_x)
    note = description + (f" · {t['name']} ×{t['multiplier']}" if t["multiplier"] > 1 else "") + (f" · {camp.title}" if camp else "")
    try:
        with transaction.atomic():
            txn = R.objects.create(customer=customer, kind=R.Kind.EARN, points=points, description=note[:200],
                                   expires_at=timezone.now() + timedelta(days=settings.CLICK_REWARD_EXPIRY_DAYS), **source)
    except IntegrityError:  # already awarded for this source
        return None
    notify(customer, NotificationCategory.REWARDS, f"You earned {points} Click. points", f"For {description}.", "/rewards")
    _check_tier_upgrade(customer, t)
    return txn


def _check_tier_upgrade(customer, before: dict) -> None:
    after = tier_of(customer)
    if after["min_points"] > before["min_points"]:
        notify(customer, NotificationCategory.REWARDS, f"You’re now {after['name']}",
               f"You earn {after['multiplier']}× points on eligible Click. purchases.", "/rewards")


def award_for_delivered_order(order) -> R | None:
    """Points and any wallet cashback on a delivered order (both once per order)."""
    from apps.payments.models import Payment, PaymentMethod
    from apps.wallet.services import award_cashback

    service = STORE_SERVICE.get(order.store.store_type, "shop")
    txn = _earn(order.customer, order.subtotal, service, f"order {order.number}", order=order)
    paid_wallet = order.payments.filter(method=PaymentMethod.WALLET, status=Payment.Status.CAPTURED).exists()
    award_cashback(order.customer, service, order.total, f"order:{order.id}", f"Order {order.number}", paid_wallet)
    check_missions(order.customer)
    return txn


def award_points(customer, amount, reference: str, description: str, service: str = "any", paid_with_wallet: bool = True) -> R | None:
    """Points on a completed booking (travel, experiences…), once per reference, plus any cashback."""
    from apps.wallet.services import award_cashback

    txn = _earn(customer, amount, service, description, reference=reference)
    award_cashback(customer, service, Decimal(amount), reference, description, paid_with_wallet)
    check_missions(customer)
    return txn


@transaction.atomic
def reverse(entry: R, reason: str) -> R | None:
    """Takes back points that were earned on something later refunded. Linked to the original; never edits it."""
    if entry.kind != R.Kind.EARN or entry.reversals.exists():
        return None
    _lock(entry.customer)
    adj = R.objects.create(customer=entry.customer, kind=R.Kind.ADJUST, points=-entry.points, reverses=entry,
                           description=f"Reversed: {entry.description} ({reason})"[:200])
    notify(entry.customer, NotificationCategory.REWARDS, f"{entry.points} points reversed", reason[:200], "/rewards")
    return adj


def reverse_for_order(order, reason: str) -> R | None:
    entry = R.objects.filter(order=order, kind=R.Kind.EARN).first()
    return reverse(entry, reason) if entry else None


# --- balance, lots, expiry -------------------------------------------------------------------------------------------

def _lock(customer) -> None:
    from apps.customers.models import CustomerProfile

    CustomerProfile.objects.select_for_update().get(pk=customer.pk)


def lots(customer) -> list[tuple[R, int]]:
    """Earned lots with their unused points, FIFO by expiry: all debits (redeem / expire / negative adjust) consume the
    soonest-expiring points first."""
    earns = list(R.objects.filter(customer=customer, points__gt=0).order_by("expires_at", "created_at"))
    used = -(R.objects.filter(customer=customer, points__lt=0).aggregate(s=Sum("points"))["s"] or 0)
    out = []
    for e in earns:
        take = min(used, e.points)
        used -= take
        if e.points - take > 0:
            out.append((e, e.points - take))
    return out


def sweep_expired(customer=None) -> int:
    from apps.customers.models import CustomerProfile

    n = 0
    now = timezone.now()
    customers = [customer] if customer else CustomerProfile.objects.filter(reward_transactions__expires_at__lte=now).distinct()
    for c in customers:
        expired = sum(r for e, r in lots(c) if e.expires_at and e.expires_at <= now)
        if expired > 0:
            R.objects.create(customer=c, kind=R.Kind.EXPIRE, points=-expired, description=f"{expired} points expired")
            notify(c, NotificationCategory.REWARDS, f"{expired} Click. points expired", "Unused points expire after a year.", "/rewards")
            n += 1
    return n


def balance(customer) -> dict:
    sweep_expired(customer)
    qs = R.objects.filter(customer=customer)
    earned = qs.filter(points__gt=0).aggregate(s=Sum("points"))["s"] or 0
    used = -(qs.filter(points__lt=0).aggregate(s=Sum("points"))["s"] or 0)
    soon = timezone.now() + timedelta(days=settings.CLICK_REWARD_EXPIRING_SOON_DAYS)
    live = lots(customer)
    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return {"balance": earned - used, "earned": earned, "used": used,
            "redeemed": -(qs.filter(kind=R.Kind.REDEEM).aggregate(s=Sum("points"))["s"] or 0),
            "expired": -(qs.filter(kind=R.Kind.EXPIRE).aggregate(s=Sum("points"))["s"] or 0),
            "earned_this_month": qs.filter(kind=R.Kind.EARN, created_at__gte=month_start).aggregate(s=Sum("points"))["s"] or 0,
            "expiring": [(e, r) for e, r in live if e.expires_at and e.expires_at <= soon]}


# --- redemption ------------------------------------------------------------------------------------------------------

def item_state(item: RewardCatalogItem, customer, points: int, tier_code: str) -> tuple[bool, str]:
    now = timezone.now()
    if not item.is_active or (item.starts_at and item.starts_at > now) or (item.ends_at and item.ends_at <= now):
        return False, "Currently unavailable"
    if item.min_tier:
        order = [t["code"] for t in tiers()]
        if order.index(tier_code) < order.index(item.min_tier):
            return False, f"For {item.min_tier.title()} members and above"
    if points < item.points_cost:
        return False, f"You need {item.points_cost - points:,} more points"
    return True, ""


@transaction.atomic
def redeem(customer, item_id, idempotency_key: str) -> RewardRedemption:
    from apps.wallet import services as wallet
    from apps.wallet.models import WalletTransaction

    existing = RewardRedemption.objects.filter(customer=customer, idempotency_key=idempotency_key).first()
    if existing:
        return existing
    _lock(customer)
    item = RewardCatalogItem.objects.filter(pk=item_id).first()
    if item is None:
        raise DomainError("That reward isn’t available.", code="reward_unavailable", status_code=404)
    bal = balance(customer)["balance"]
    ok, why = item_state(item, customer, bal, tier_of(customer)["code"])
    if not ok:
        raise ConflictError(why, code="insufficient_points" if "more points" in why else "reward_unavailable",
                            details={"balance": bal, "required": item.points_cost})
    red = RewardRedemption.objects.create(customer=customer, item=item, points=item.points_cost, value=item.value, idempotency_key=idempotency_key)
    red.reward_transaction = R.objects.create(customer=customer, kind=R.Kind.REDEEM, points=-item.points_cost, description=f"Redeemed {item.title}")
    red.wallet_transaction = wallet.credit_promo(customer, WalletTransaction.Kind.REWARD, item.value, f"reward:{red.id}",
                                                 f"Rewards: {item.title}", item.credit_valid_days, announce=False)
    red.save(update_fields=["reward_transaction", "wallet_transaction", "updated_at"])
    w = red.wallet_transaction
    notify(customer, NotificationCategory.REWARDS, f"₹{item.value:,.2f} added to your Click. Wallet",
           f"{item.points_cost:,} points redeemed for {item.title}." + (f" Valid until {w.expires_at.astimezone(wallet._tz()):%d %b %Y}." if w and w.expires_at else ""),
           f"/wallet/activity/{w.id}" if w else "/rewards")
    return red


# --- missions and achievements ---------------------------------------------------------------------------------------

def _metric(customer, metric: str, since) -> int:
    from apps.orders.models import Order

    def after(qs, field="created_at"):
        return qs.filter(**{f"{field}__gte": since}) if since else qs

    delivered = after(Order.objects.filter(customer=customer, status="delivered"))
    if metric == "orders":
        return delivered.count()
    if metric == "restaurants":
        return delivered.filter(store__store_type="restaurant").values("store").distinct().count()
    if metric == "rides":
        return after(customer.rides.filter(status="completed")).count()
    if metric == "travel":
        return after(customer.travel_bookings.filter(status="completed")).count()
    if metric == "stays":
        return after(customer.hotel_bookings.filter(status="completed")).count()
    if metric == "visits":
        return after(customer.experience_bookings.filter(status="completed")).count()
    if metric == "profile":
        u = customer.user
        return int(bool(u.full_name and u.email and customer.addresses.exists()))
    if metric == "services_used":
        used = {STORE_SERVICE.get(t) for t in delivered.values_list("store__store_type", flat=True).distinct()}
        for name, qs in (("ride", customer.rides.filter(status="completed")), ("travel", customer.travel_bookings.filter(status="completed")),
                         ("hotels", customer.hotel_bookings.filter(status="completed")), ("bookings", customer.experience_bookings.filter(status="completed")),
                         ("parcel", customer.parcels.filter(status="delivered")), ("services", customer.service_bookings.filter(status__in=["completed", "paid"]))):
            if after(qs).exists():
                used.add(name)
        return len(used - {None})
    return 0


def missions(customer) -> list[dict]:
    now = timezone.now()
    out = []
    done = set(R.objects.filter(customer=customer, reference__startswith="mission:").values_list("reference", flat=True))
    for m in RewardMission.objects.filter(is_active=True).filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now - timedelta(days=7))):
        progress = min(m.target, _metric(customer, m.metric, m.starts_at))
        completed = f"mission:{m.code}" in done
        expired = bool(m.ends_at and m.ends_at <= now and not completed)
        out.append({"mission": m, "progress": progress, "completed": completed, "expired": expired})
    return out


def check_missions(customer) -> int:
    n = 0
    for row in missions(customer):
        m = row["mission"]
        if row["completed"] or row["expired"] or row["progress"] < m.target:
            continue
        try:
            with transaction.atomic():
                R.objects.create(customer=customer, kind=R.Kind.EARN, points=m.points, reference=f"mission:{m.code}",
                                 description=f"Mission: {m.title}", expires_at=timezone.now() + timedelta(days=settings.CLICK_REWARD_EXPIRY_DAYS))
        except IntegrityError:
            continue
        notify(customer, NotificationCategory.REWARDS, f"Mission complete: {m.title}", f"+{m.points} Click. points.", "/rewards")
        n += 1
    return n


ACHIEVEMENTS = [  # permanent milestones measured from real records (no points; missions carry points)
    ("first_click", "First Click.", "Completed your first Click. order or booking", "services_used", 1),
    ("foodie", "Food Explorer", "Ordered from 5 different restaurants", "restaurants", 5),
    ("regular", "Click. Regular", "10 completed orders", "orders", 10),
    ("road", "Road Warrior", "10 completed rides", "rides", 10),
    ("traveller", "Traveller", "Completed a journey with Click. Travel", "travel", 1),
    ("stayer", "Weekend Away", "Completed a hotel stay", "stays", 1),
    ("explorer", "Click. Explorer", "Used 4 different Click. services", "services_used", 4),
]


def achievements(customer) -> list[dict]:
    cache: dict[str, int] = {}
    out = []
    for code, title, desc, metric, target in ACHIEVEMENTS:
        if metric not in cache:
            cache[metric] = _metric(customer, metric, None)
        out.append({"code": code, "title": title, "description": desc, "progress": min(target, cache[metric]), "target": target,
                    "unlocked": cache[metric] >= target})
    return out


def summary_counts(customer) -> dict:
    return R.objects.filter(customer=customer).aggregate(earn=Count("id", filter=Q(kind="earn")), redeem=Count("id", filter=Q(kind="redeem")))
