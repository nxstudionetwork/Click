"""
Account deletion (Profile → Security). Never a plain DELETE:

1. GET  /me/delete       what would block it right now (orders / bookings in progress, money left in Click. Wallet or
                         on gift cards) — the customer resolves those first.
2. POST /auth/otp/request {phone: their own verified phone}  (a fresh code proves it's really them)
3. POST /me/delete {token: "<challenge>.<code>", reason}
       → re-verified, re-checked, then in one transaction: the account is deactivated, personal data is removed
         (name, email, phone, photo, addresses, saved searches, notification preferences), every sign-in is ended.
         Orders, payments, invoices, refunds and support requests are kept as legal and tax records, linked only to
         the anonymised account.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import DomainError

from .otp import PhoneOtpVerifier
from .providers import IdentityError

audit = logging.getLogger("click.audit")

ACTIVE = {
    "orders": ("awaiting_payment", "placed", "confirmed", "preparing", "ready", "packed", "shipped", "out_for_delivery"),
    "rides": ("scheduled", "searching", "driver_assigned", "driver_arrived", "in_progress"),
    "parcels": ("scheduled", "searching", "assigned", "at_pickup", "picked_up", "in_transit", "arriving"),
}


def blockers(user) -> list[dict]:
    c = getattr(user, "customer_profile", None)
    if c is None:
        return []
    out = []
    n = c.orders.filter(status__in=ACTIVE["orders"]).count()
    if n:
        out.append({"code": "active_orders", "message": f"{n} order{'s are' if n > 1 else ' is'} still in progress.", "link": "/orders"})
    if c.rides.filter(status__in=ACTIVE["rides"]).exists():
        out.append({"code": "active_ride", "message": "You have a ride in progress.", "link": "/rides"})
    if c.parcels.filter(status__in=ACTIVE["parcels"]).exists():
        out.append({"code": "active_parcel", "message": "A parcel is still on its way.", "link": "/parcels/history"})
    upcoming = (c.hotel_bookings.filter(status__in=["confirmed", "pending_payment"]).count() + c.travel_bookings.filter(status__in=["confirmed", "pending_payment"]).count()
                + c.experience_bookings.filter(status__in=["confirmed", "pending_payment"]).count())
    if upcoming:
        out.append({"code": "upcoming_bookings", "message": f"{upcoming} upcoming booking{'s' if upcoming > 1 else ''}. Use or cancel them first.", "link": "/bookings/mine"})
    from apps.wallet.services import balance

    b = balance(c)
    if b > 0:
        out.append({"code": "wallet_balance", "message": f"₹{b:,.2f} is still in Click. Wallet. Spend it first, or contact support.", "link": "/wallet"})
    from apps.giftcards.models import GiftCard
    from apps.giftcards.services import balance as gift_balance

    left = sum((gift_balance(g) for g in GiftCard.objects.filter(holder=c, status="active")), 0)
    if left:
        out.append({"code": "gift_cards", "message": f"₹{left:,.2f} is left on your gift cards.", "link": "/gift-cards/mine"})
    return out


@transaction.atomic
def delete_account(user, reason: str = "") -> None:
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

    c = getattr(user, "customer_profile", None)
    if c is not None:
        c.addresses.all().delete()
        c.search_history.all().delete()
        c.wishlist_items.all().delete()
        c.refill_reminders.all().delete()
        if getattr(c, "avatar", None):
            try:
                c.avatar.delete(save=False)
            except Exception:  # noqa: BLE001 — a missing file must not block deletion
                pass
        from apps.activity.services import record

        record(c, "account.deleted", {"reason": reason[:200]})
    if getattr(user, "avatar", None):
        try:
            user.avatar.delete(save=False)
        except Exception:  # noqa: BLE001
            pass
    for t in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=t)
    user.external_identities.all().delete()
    user.full_name, user.email, user.phone, user.phone_verified, user.is_active = "Deleted customer", None, "", False, False
    user.set_unusable_password()
    user.save()
    audit.info("account.deleted", extra={"user_id": str(user.id), "at": timezone.now().isoformat()})


class DeleteAccountView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "auth"

    def get(self, request):
        return Response({"blockers": blockers(request.user), "phone": request.user.phone if request.user.phone_verified else "",
                         "keeps": "Orders, payments, invoices, refunds and support requests are kept as legal records, without your name or contact details."})

    def post(self, request):
        user = request.user
        if not (user.phone and user.phone_verified):
            raise DomainError("Your account has no verified phone. Contact support to delete it.", code="reverify_unavailable")
        try:
            identity = PhoneOtpVerifier().verify(str(request.data.get("token") or ""))
        except IdentityError as e:
            raise DomainError("That code isn’t valid. Request a new one.", code=e.public_code or "invalid_code", status_code=401)
        if identity.phone_number != user.phone:
            raise DomainError("Verify with the phone number on this account.", code="invalid_code", status_code=401)
        if b := blockers(user):
            raise DomainError("Some things need finishing before your account can be deleted.", code="deletion_blocked", details={"blockers": b})
        delete_account(user, str(request.data.get("reason") or ""))
        response = Response({"deleted": True})
        from django.conf import settings

        response.delete_cookie(settings.AUTH_REFRESH_COOKIE["name"], path=settings.AUTH_REFRESH_COOKIE.get("path", "/"))
        return response
