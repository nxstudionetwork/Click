"""
Every change to a Click. Wallet balance goes through here — server side, inside a transaction that locks the customer's
row, so two payments can never spend the same rupees. Nothing in the API lets a client set a balance.

  pay        spends promotional credit first (soonest-expiring lot first, never an expired one), then cash; one
             ledger line per lot / bucket, so refunds and expiries stay exact
  refund     returns money to where it came from: the cash part as cash, the promo part as promo credit with a
             fresh validity (it can't turn into cash). Once per payment (`refund`) or per approved return
  credit     promotional credit / cashback / rewards conversion — a lot with an expiry, idempotent by `reference`
  expire     the unspent part of an expired lot leaves the balance as an "expired" line
  top-up     intent with the payment provider → the provider's signed confirmation is verified → cash credit, once
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.core.api.exceptions import ConflictError, DomainError
from apps.customers.models import CustomerProfile
from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify

from .models import WalletAccount, WalletTopUp, WalletTransaction as T

ZERO = Decimal("0.00")
METHOD_LABEL = {"upi": "UPI", "card": "card", "netbanking": "net banking"}


def money(x) -> Decimal:
    return Decimal(x).quantize(Decimal("0.01"))


# --- reading ---------------------------------------------------------------------------------------------------------

def balance(customer) -> Decimal:
    """Spendable balance = the ledger sum minus promo credit that has expired but not yet been swept."""
    total = T.objects.filter(customer=customer).aggregate(s=Sum("amount"))["s"] or ZERO
    return money(total - sum((r for _, r in _expired_unswept(customer)), ZERO))


def lots(customer, include_expired: bool = False) -> list[tuple[T, Decimal]]:
    """Promo credit lots with their unspent remainder, soonest expiry first."""
    qs = (T.objects.filter(customer=customer, bucket=T.Bucket.PROMO, amount__gt=0)
          .annotate(used=Sum("consumptions__amount")).order_by("expires_at", "created_at"))
    now = timezone.now()
    out = []
    for lot in qs:
        remaining = money(lot.amount + (lot.used or ZERO))
        if remaining <= 0:
            continue
        if not include_expired and lot.expires_at and lot.expires_at <= now:
            continue
        out.append((lot, remaining))
    return out


def _expired_unswept(customer) -> list[tuple[T, Decimal]]:
    now = timezone.now()
    return [(lot, r) for lot, r in lots(customer, include_expired=True) if lot.expires_at and lot.expires_at <= now]


def breakdown(customer) -> dict:
    cash = T.objects.filter(customer=customer, bucket=T.Bucket.CASH).aggregate(s=Sum("amount"))["s"] or ZERO
    live = lots(customer)
    by_kind: dict[str, Decimal] = {}
    for lot, r in live:
        by_kind[lot.kind] = by_kind.get(lot.kind, ZERO) + r
    soon = timezone.now() + timedelta(days=settings.CLICK_WALLET_EXPIRING_SOON_DAYS)
    return {"cash": money(cash), "promo": money(sum((r for _, r in live), ZERO)), "by_kind": {k: money(v) for k, v in by_kind.items()},
            "expiring": [(lot, r) for lot, r in live if lot.expires_at and lot.expires_at <= soon]}


def account(customer) -> WalletAccount:
    acc, _ = WalletAccount.objects.get_or_create(customer=customer)
    return acc


def limits() -> dict:
    return {"min_topup": money(settings.CLICK_WALLET_MIN_TOPUP), "max_topup": money(settings.CLICK_WALLET_MAX_TOPUP),
            "daily_topup": money(settings.CLICK_WALLET_DAILY_TOPUP_LIMIT), "monthly_topup": money(settings.CLICK_WALLET_MONTHLY_TOPUP_LIMIT),
            "max_balance": money(settings.CLICK_WALLET_MAX_BALANCE)}


def _ensure_active(customer, action: str) -> None:
    acc = account(customer)
    if acc.status != WalletAccount.Status.ACTIVE:
        raise DomainError(f"Your Click. Wallet is {acc.get_status_display().lower()}, so {action} isn’t available. "
                          f"{acc.status_reason or 'Contact Click. Support for help.'}", code="wallet_restricted", status_code=403)


def _lock(customer) -> None:
    # Serialize all wallet writes per customer so concurrent payments can't overspend.
    CustomerProfile.objects.select_for_update().get(pk=customer.pk)


# --- spending and refunds --------------------------------------------------------------------------------------------

@transaction.atomic
def pay(customer, amount: Decimal, payment, description: str) -> list[T]:
    _lock(customer)
    _ensure_active(customer, "paying with it")
    sweep_expired(customer)
    amount = money(amount)
    available = balance(customer)
    if available < amount:
        raise DomainError("Not enough balance in your Click. Wallet.", code="insufficient_wallet_balance",
                          details={"balance": str(available), "required": str(amount)})
    left, out = amount, []
    for lot, remaining in lots(customer):
        if left <= 0:
            break
        use = min(left, remaining)
        out.append(T.objects.create(customer=customer, kind=T.Kind.PAYMENT, bucket=T.Bucket.PROMO, amount=-use, payment=payment, lot=lot,
                                    description=description))
        left -= use
    if left > 0:
        out.append(T.objects.create(customer=customer, kind=T.Kind.PAYMENT, bucket=T.Bucket.CASH, amount=-left, payment=payment,
                                    description=description))
    if amount >= Decimal(settings.CLICK_WALLET_DEBIT_NOTIFY_FROM):
        notify(customer, NotificationCategory.WALLET, f"₹{amount:,.2f} paid from your Click. Wallet", description, f"/wallet/activity/{out[0].id}")
    return out


def _spent(payment) -> tuple[Decimal, Decimal]:
    rows = T.objects.filter(payment=payment)
    cash = -(rows.filter(kind=T.Kind.PAYMENT, bucket=T.Bucket.CASH).aggregate(s=Sum("amount"))["s"] or ZERO)
    promo = -(rows.filter(kind=T.Kind.PAYMENT, bucket=T.Bucket.PROMO).aggregate(s=Sum("amount"))["s"] or ZERO)
    cash -= rows.filter(kind=T.Kind.REFUND, bucket=T.Bucket.CASH).aggregate(s=Sum("amount"))["s"] or ZERO
    promo -= rows.filter(kind=T.Kind.REFUND, bucket=T.Bucket.PROMO).aggregate(s=Sum("amount"))["s"] or ZERO
    return money(cash), money(promo)


def _credit_refund(customer, amount: Decimal, payment, description: str) -> T:
    """Cash spent comes back as cash; promo spent comes back as promo credit (it never becomes cash)."""
    cash_left, promo_left = _spent(payment)
    amount = money(amount)
    to_cash = min(amount, max(ZERO, cash_left)) if payment else amount
    to_promo = amount - to_cash
    first = None
    if to_cash > 0:
        first = T.objects.create(customer=customer, kind=T.Kind.REFUND, bucket=T.Bucket.CASH, amount=to_cash, payment=payment, description=description)
    if to_promo > 0:
        lot = T.objects.create(customer=customer, kind=T.Kind.REFUND, bucket=T.Bucket.PROMO, amount=to_promo, payment=payment,
                               description=f"{description} (promotional credit)",
                               expires_at=timezone.now() + timedelta(days=settings.CLICK_WALLET_PROMO_REFUND_DAYS))
        first = first or lot
    notify(customer, NotificationCategory.WALLET, f"₹{amount:,.2f} refunded to your Click. Wallet", description, f"/wallet/activity/{first.id}")
    return first


@transaction.atomic
def refund(customer, amount: Decimal, payment, description: str) -> T | None:
    _lock(customer)
    if T.objects.filter(payment=payment, kind=T.Kind.REFUND).exists():
        return None
    return _credit_refund(customer, amount, payment, description)


@transaction.atomic
def refund_return(customer, amount: Decimal, payment, description: str) -> T:
    """Credit an approved item return. Callers lock the return request, so each return is refunded once; unlike
    `refund` this allows several partial refunds against one order payment."""
    _lock(customer)
    return _credit_refund(customer, amount, payment, description)


# --- promotional credit ----------------------------------------------------------------------------------------------

@transaction.atomic
def credit_promo(customer, kind: str, amount: Decimal, reference: str, description: str, valid_days: int, created_by=None,
                 announce: bool = True) -> T | None:
    """Promo credit / cashback / rewards conversion as a lot with an expiry. Idempotent by `reference`."""
    _lock(customer)
    amount = money(amount)
    if amount <= 0:
        return None
    try:
        with transaction.atomic():
            txn = T.objects.create(customer=customer, kind=kind, bucket=T.Bucket.PROMO, amount=amount, reference=reference, description=description[:200],
                                   expires_at=timezone.now() + timedelta(days=valid_days), created_by=created_by)
    except IntegrityError:
        return None
    if not announce:  # the caller sends its own, more specific notification
        return txn
    word = {"cashback": "Cashback", "reward": "Rewards credit", "promo": "Promotional credit"}.get(kind, "Credit")
    notify(customer, NotificationCategory.WALLET, f"{word} of ₹{amount:,.2f} added to your Click. Wallet",
           f"{description}. Valid until {txn.expires_at.astimezone(_tz()):%d %b %Y}.", f"/wallet/activity/{txn.id}")
    return txn


def _tz():
    from zoneinfo import ZoneInfo

    return ZoneInfo(settings.CLICK_LOCAL_TIMEZONE)


def sweep_expired(customer=None) -> int:
    """Moves the unspent part of expired promo lots out of the balance (one 'expired' line per lot)."""
    n = 0
    customers = [customer] if customer else CustomerProfile.objects.filter(
        wallet_transactions__bucket=T.Bucket.PROMO, wallet_transactions__expires_at__lte=timezone.now()).distinct()
    for c in customers:
        for lot, remaining in _expired_unswept(c):
            T.objects.create(customer=c, kind=T.Kind.EXPIRY, bucket=T.Bucket.PROMO, amount=-remaining, lot=lot,
                             description=f"Expired: {lot.description}"[:200])
            notify(c, NotificationCategory.WALLET, f"₹{remaining:,.2f} promotional credit expired", lot.description[:200], "/wallet")
            n += 1
    return n


def remind_expiring() -> int:
    """One reminder per lot when it enters the expiring-soon window (idempotent via the notification link)."""
    from apps.notifications.models import Notification

    n = 0
    soon = timezone.now() + timedelta(days=settings.CLICK_WALLET_EXPIRING_SOON_DAYS)
    for c in CustomerProfile.objects.filter(wallet_transactions__bucket=T.Bucket.PROMO, wallet_transactions__expires_at__lte=soon,
                                            wallet_transactions__expires_at__gt=timezone.now()).distinct():
        for lot, remaining in lots(c):
            if lot.expires_at and lot.expires_at <= soon:
                link = f"/wallet/activity/{lot.id}"
                if not Notification.objects.filter(customer=c, link_path=link, title__startswith="Credit expiring").exists():
                    notify(c, NotificationCategory.WALLET, f"Credit expiring: ₹{remaining:,.2f}",
                           f"{lot.description} expires on {lot.expires_at.astimezone(_tz()):%d %b}. Use it on an eligible Click. service.", link)
                    n += 1
    return n


# --- cashback --------------------------------------------------------------------------------------------------------

def award_cashback(customer, service: str, amount: Decimal, reference: str, label: str, paid_with_wallet: bool) -> T | None:
    """Best eligible live cashback offer for a completed purchase, credited once per purchase."""
    from .models import CashbackOffer

    now = timezone.now()
    best, value = None, ZERO
    for o in CashbackOffer.objects.filter(Q(service=service) | Q(service="any"), is_active=True, starts_at__lte=now, ends_at__gt=now):
        if amount < o.min_amount or (o.wallet_payment_only and not paid_with_wallet):
            continue
        v = min(money(amount * o.percent / 100), o.max_cashback)
        if v > value:
            best, value = o, v
    if best is None or value <= 0:
        return None
    return credit_promo(customer, T.Kind.CASHBACK, value, f"cashback:{reference}", f"{best.title} · {label}", best.credit_valid_days)


# --- top-ups ---------------------------------------------------------------------------------------------------------

def topup_available() -> bool:
    from . import providers

    return providers.current() is not None


@transaction.atomic
def start_topup(customer, amount: Decimal, method: str, idempotency_key: str) -> tuple[WalletTopUp, dict]:
    from apps.payments.models import Payment

    from . import providers

    prov = providers.current()
    if prov is None:
        raise DomainError("Adding money isn’t available yet: no payment provider is connected.", code="topup_unavailable", status_code=503)
    if method not in prov.methods:
        raise DomainError("That payment method isn’t available for adding money.", code="payment_method_unavailable")
    existing = WalletTopUp.objects.filter(customer=customer, idempotency_key=idempotency_key).first()
    if existing:
        return existing, prov.client_data(existing)
    _lock(customer)
    _ensure_active(customer, "adding money")
    amount = money(amount)
    lim = limits()
    if amount < lim["min_topup"] or amount > lim["max_topup"]:
        raise DomainError(f"Add between ₹{lim['min_topup']:,.0f} and ₹{lim['max_topup']:,.0f} at a time.", code="topup_amount")
    now = timezone.now()
    done = WalletTopUp.objects.filter(customer=customer, status__in=[WalletTopUp.Status.SUCCEEDED, WalletTopUp.Status.PENDING])
    today = done.filter(created_at__gte=now - timedelta(days=1)).aggregate(s=Sum("amount"))["s"] or ZERO
    month = done.filter(created_at__gte=now - timedelta(days=30)).aggregate(s=Sum("amount"))["s"] or ZERO
    if today + amount > lim["daily_topup"]:
        raise DomainError(f"That would pass your daily add-money limit of ₹{lim['daily_topup']:,.0f} (₹{max(ZERO, lim['daily_topup'] - today):,.0f} left).", code="topup_daily_limit")
    if month + amount > lim["monthly_topup"]:
        raise DomainError(f"That would pass your 30-day add-money limit of ₹{lim['monthly_topup']:,.0f}.", code="topup_monthly_limit")
    if balance(customer) + amount > lim["max_balance"]:
        raise DomainError(f"Your wallet can hold up to ₹{lim['max_balance']:,.0f}.", code="topup_max_balance")
    t = WalletTopUp.objects.create(customer=customer, amount=amount, method=method, provider=prov.name, idempotency_key=idempotency_key)
    t.payment = Payment.objects.create(wallet_topup=t, method=method, amount=amount, currency=t.currency, provider=prov.name)
    t.provider_reference = prov.create_intent(t)
    t.save(update_fields=["payment", "provider_reference", "updated_at"])
    return t, prov.client_data(t)


@transaction.atomic
def apply_provider_result(provider_reference: str, outcome: str, amount: Decimal, reason: str = "") -> WalletTopUp:
    """Called only after the provider's signature is verified. Idempotent: a replayed or late event changes nothing."""
    from apps.payments.models import Payment

    t = WalletTopUp.objects.select_for_update(of=("self",)).select_related("payment", "customer").filter(provider_reference=provider_reference).first()
    if t is None:
        raise DomainError("Unknown payment reference.", code="unknown_reference", status_code=404)
    if t.status in (WalletTopUp.Status.SUCCEEDED, WalletTopUp.Status.FAILED, WalletTopUp.Status.EXPIRED):
        return t  # already settled: duplicate callback
    if outcome == "succeeded":
        if money(amount) != t.amount:
            raise ConflictError("The confirmed amount doesn’t match the top-up.", code="amount_mismatch")
        _lock(t.customer)
        txn = T.objects.create(customer=t.customer, kind=T.Kind.TOPUP, bucket=T.Bucket.CASH, amount=t.amount, payment=t.payment,
                               description=f"Money added by {METHOD_LABEL.get(t.method, t.method.upper())}")
        t.status, t.wallet_transaction, t.completed_at = WalletTopUp.Status.SUCCEEDED, txn, timezone.now()
        t.payment.status = Payment.Status.CAPTURED
        notify(t.customer, NotificationCategory.WALLET, f"₹{t.amount:,.2f} added to your Click. Wallet",
               f"Paid by {t.method.upper()} · ref {t.provider_reference}.", f"/wallet/activity/{txn.id}")
    elif outcome == "pending":
        t.status = WalletTopUp.Status.PENDING
    else:
        t.status, t.failure_reason, t.completed_at = WalletTopUp.Status.FAILED, reason[:200] or "Payment declined", timezone.now()
        t.payment.status = Payment.Status.FAILED
        notify(t.customer, NotificationCategory.WALLET, "Adding money didn’t go through",
               f"₹{t.amount:,.2f} by {t.method.upper()}: {t.failure_reason}. Your wallet didn’t change.", "/wallet")
    t.payment.provider_reference = t.provider_reference
    t.payment.save(update_fields=["status", "provider_reference", "updated_at"])
    t.save(update_fields=["status", "wallet_transaction", "completed_at", "failure_reason", "updated_at"])
    return t


def expire_topups() -> int:
    from apps.payments.models import Payment

    n = 0
    for t in WalletTopUp.objects.filter(status=WalletTopUp.Status.CREATED, created_at__lte=timezone.now() - timedelta(minutes=30)):
        t.status = WalletTopUp.Status.EXPIRED
        t.save(update_fields=["status", "updated_at"])
        Payment.objects.filter(pk=t.payment_id).update(status=Payment.Status.CANCELLED)
        n += 1
    return n
