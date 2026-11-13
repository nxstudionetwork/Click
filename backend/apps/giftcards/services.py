"""Gift card rules. Every balance change locks the card row and is written to the ledger; the frontend never sends a
balance, a value or an owner."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.activity.services import record
from apps.core.api.exceptions import ConflictError, DomainError
from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify

from .models import GiftCard, GiftCardDesign, GiftCardEntry

S = GiftCard.Status


def balance(card: GiftCard) -> Decimal:
    return card.entries.aggregate(s=Sum("amount"))["s"] or Decimal("0")


def _lock(card_id) -> GiftCard:
    return GiftCard.objects.select_for_update().select_related("design").get(pk=card_id)


@transaction.atomic
def purchase(customer, *, design_id, amount: Decimal, recipient_name: str, recipient_phone: str, message: str, delivery: str,
             deliver_on, method: str, idempotency_key: str):
    from apps.payments.models import Payment

    existing = GiftCard.objects.filter(buyer=customer, idempotency_key=idempotency_key).first()
    if existing:
        return existing, None
    design = GiftCardDesign.objects.filter(pk=design_id, is_active=True).first()
    if design is None:
        raise DomainError("This gift card isn’t available.", code="giftcard_unavailable", status_code=404)
    amount = Decimal(amount).quantize(Decimal("0.01"))
    if not design.min_amount <= amount <= design.max_amount:
        raise DomainError(f"Choose an amount between ₹{design.min_amount:,.0f} and ₹{design.max_amount:,.0f}.", code="giftcard_amount")
    today = timezone.localdate()
    if deliver_on and not today <= deliver_on <= today + timedelta(days=90):
        raise DomainError("Choose a delivery date within the next 90 days.", code="giftcard_date")
    if delivery == GiftCard.Delivery.CLICK and not recipient_phone:
        raise DomainError("Add the recipient’s mobile number, or choose to share the code yourself.", code="validation_error")
    card = GiftCard.objects.create(design=design, buyer=customer, recipient_name=recipient_name.strip()[:80], recipient_phone=recipient_phone,
                                   message=message.strip()[:300], delivery=delivery, deliver_on=deliver_on if deliver_on and deliver_on > today else None,
                                   amount=amount, idempotency_key=idempotency_key)
    intent = None
    if method == "wallet":
        from apps.wallet.services import pay

        p = Payment.objects.create(gift_card=card, method="wallet", amount=amount, provider="click_wallet")
        pay(customer, amount, p, f"Gift card for {card.recipient_name}")
        p.status = Payment.Status.CAPTURED
        p.save(update_fields=["status", "updated_at"])
        paid(card)
    elif method in ("upi", "card", "netbanking"):
        from apps.payments.gateway import start_for_gift_card

        intent = start_for_gift_card(card, method)
    else:
        raise DomainError("Choose how to pay.", code="payment_method_unavailable")
    record(customer, "giftcard.bought", {"amount": str(amount), "design": design.title})
    return card, intent


def paid(card: GiftCard) -> None:
    """The purchase payment is confirmed: issue the value and deliver now or on the chosen date."""
    card = _lock(card.pk)
    if card.status != S.AWAITING_PAYMENT:
        return
    try:
        with transaction.atomic():
            GiftCardEntry.objects.create(card=card, kind=GiftCardEntry.Kind.ISSUE, amount=card.amount, description=f"{card.design.title} issued")
    except IntegrityError:
        return
    card.expires_at = timezone.now() + timedelta(days=card.design.validity_days)
    card.status = S.SCHEDULED if card.deliver_on else S.ACTIVE
    card.save(update_fields=["expires_at", "status", "updated_at"])
    notify(card.buyer, NotificationCategory.PAYMENTS, f"Gift card for {card.recipient_name} bought",
           f"₹{card.amount:,.0f} · {'delivers on ' + card.deliver_on.strftime('%d %b') if card.deliver_on else 'ready now'}.", f"/gift-cards/mine/{card.id}")
    if not card.deliver_on:
        deliver(card)


def failed(card: GiftCard) -> None:
    GiftCard.objects.filter(pk=card.pk, status=S.AWAITING_PAYMENT).update(status=S.CANCELLED)


def deliver(card: GiftCard) -> None:
    from apps.users.models import User

    card = _lock(card.pk)
    if card.delivered_at or card.status not in (S.ACTIVE, S.SCHEDULED):
        return
    card.status, card.delivered_at = S.ACTIVE, timezone.now()
    recipient = None
    if card.delivery == GiftCard.Delivery.CLICK and card.recipient_phone:
        u = User.objects.filter(phone=card.recipient_phone, phone_verified=True, is_active=True).select_related("customer_profile").first()
        recipient = getattr(u, "customer_profile", None) if u else None
    if recipient:
        card.holder = recipient
        notify(recipient, NotificationCategory.PAYMENTS, f"{card.buyer.user.full_name.split(' ')[0] or 'Someone'} sent you a Click. gift card",
               f"₹{card.amount:,.0f}{' · ' + card.message[:80] if card.message else ''}", f"/gift-cards/mine/{card.id}")
        record(recipient, "giftcard.received", {"amount": str(card.amount)})
    else:
        notify(card.buyer, NotificationCategory.PAYMENTS, f"Gift card for {card.recipient_name} is ready",
               "Share its code with them; they redeem it in Click. → Gift Cards." if card.delivery == GiftCard.Delivery.SHARE
               else "They aren’t on Click. yet, so share the code with them to redeem.", f"/gift-cards/mine/{card.id}")
    card.save(update_fields=["status", "delivered_at", "holder", "updated_at"])


@transaction.atomic
def redeem(customer, code: str) -> GiftCard:
    code = (code or "").strip().upper().replace(" ", "")
    if len(code) == 16:
        code = "-".join(code[i:i + 4] for i in range(0, 16, 4))
    card = GiftCard.objects.select_for_update().filter(code=code).first()
    if card is None or card.status in (S.AWAITING_PAYMENT, S.CANCELLED):
        raise DomainError("That code isn’t valid. Check it and try again.", code="giftcard_invalid")
    if card.status == S.SCHEDULED:
        raise DomainError(f"This gift card can be redeemed from {card.deliver_on:%d %b}.", code="giftcard_not_yet")
    if card.expires_at and card.expires_at <= timezone.now() or card.status == S.EXPIRED:
        raise DomainError("This gift card has expired.", code="giftcard_expired")
    if card.holder_id and card.holder_id != customer.id:
        raise ConflictError("This gift card has already been redeemed.", code="giftcard_redeemed")
    if card.holder_id != customer.id:
        card.holder = customer
        card.save(update_fields=["holder", "updated_at"])
        record(customer, "giftcard.redeemed", {"amount": str(card.amount)})
        notify(customer, NotificationCategory.PAYMENTS, "Gift card added", f"₹{balance(card):,.0f} to spend on {', '.join(card.design.services).title()}.",
               f"/gift-cards/mine/{card.id}")
    return card


def usable(customer, service: str):
    now = timezone.now()
    out = []
    for c in GiftCard.objects.filter(holder=customer, status=S.ACTIVE, expires_at__gt=now).select_related("design"):
        if service in c.design.services:
            b = balance(c)
            if b > 0:
                out.append((c, b))
    return out


def pay(customer, card_id, amount: Decimal, payment, service: str, description: str) -> None:
    """Spend from a gift card for one payment (the whole amount; no split with another method)."""
    card = _lock(card_id) if GiftCard.objects.filter(pk=card_id, holder=customer).exists() else None
    if card is None:
        raise DomainError("Choose one of your gift cards.", code="giftcard_invalid")
    if card.status != S.ACTIVE or (card.expires_at and card.expires_at <= timezone.now()):
        raise DomainError("This gift card can’t be used now.", code="giftcard_expired")
    if service not in card.design.services:
        raise DomainError(f"This gift card can be used on {', '.join(card.design.services).title()} only.", code="giftcard_service")
    if balance(card) < amount:
        raise DomainError(f"The gift card has ₹{balance(card):,.2f} left — not enough for this order.", code="giftcard_insufficient")
    GiftCardEntry.objects.create(card=card, kind=GiftCardEntry.Kind.SPEND, amount=-amount, payment=payment, description=description[:160])
    if balance(card) == 0:
        GiftCard.objects.filter(pk=card.pk).update(status=S.USED)


def refund(payment, label: str) -> None:
    spent = payment.gift_card_entries.filter(kind=GiftCardEntry.Kind.SPEND).first()
    if spent is None:
        return
    card = _lock(spent.card_id)
    try:
        with transaction.atomic():
            GiftCardEntry.objects.create(card=card, kind=GiftCardEntry.Kind.REFUND, amount=-spent.amount, payment=payment, description=f"Refund for {label}"[:160])
    except IntegrityError:
        return
    if card.status == S.USED:
        card.status = S.ACTIVE
        card.save(update_fields=["status", "updated_at"])
    if card.holder:
        notify(card.holder, NotificationCategory.PAYMENTS, f"₹{-spent.amount:,.2f} back on your gift card", f"Refund for {label}.", f"/gift-cards/mine/{card.id}")


def run_due() -> dict:
    """Scheduled: deliver cards whose date has come, expire cards past their date (run daily)."""
    today, now = timezone.localdate(), timezone.now()
    delivered = expired = 0
    for c in GiftCard.objects.filter(status=S.SCHEDULED, deliver_on__lte=today):
        deliver(c)
        delivered += 1
    # Once per card: the daily run sees it only on the day it enters the 6–7 day window.
    for c in GiftCard.objects.filter(status=S.ACTIVE, holder__isnull=False, expires_at__gt=now + timedelta(days=6),
                                     expires_at__lte=now + timedelta(days=7)).select_related("holder", "design"):
        b = balance(c)
        if b > 0:
            notify(c.holder, NotificationCategory.PAYMENTS, f"₹{b:,.0f} on your gift card expires soon",
                   f"Use it by {timezone.localtime(c.expires_at):%d %b} on {', '.join(c.design.services).title()}.", f"/gift-cards/mine/{c.id}")
    for c in GiftCard.objects.filter(status=S.ACTIVE, expires_at__lte=now):
        with transaction.atomic():
            c = _lock(c.pk)
            b = balance(c)
            if b > 0:
                GiftCardEntry.objects.create(card=c, kind=GiftCardEntry.Kind.EXPIRE, amount=-b, description="Expired")
            c.status = S.EXPIRED
            c.save(update_fields=["status", "updated_at"])
            expired += 1
    return {"delivered": delivered, "expired": expired}
