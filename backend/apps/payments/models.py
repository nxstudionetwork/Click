"""
Payments are separate records (not columns on Order) so an order can have
multiple attempts, refunds and providers. Cash on delivery, pay at venue and
Click Wallet are enabled; online gateways plug in later.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel


class PaymentMethod(models.TextChoices):
    CASH_ON_DELIVERY = "cash_on_delivery", "Cash on delivery"
    PAY_AT_VENUE = "pay_at_venue", "Pay at venue"
    WALLET = "wallet", "Click Wallet"
    CASH = "cash", "Cash to driver / delivery partner"


PAYMENT_TARGETS = ("order", "booking", "ride", "parcel", "service_booking", "event_booking", "hotel_booking")


def _exactly_one(fields) -> Q:
    """Exactly one of `fields` is set (new payable entities add a column and a name here, and bump the constraint)."""
    out = Q()
    for f in fields:
        q = Q(**{f"{f}__isnull": False})
        for o in fields:
            if o != f:
                q &= Q(**{f"{o}__isnull": True})
        out |= q
    return out


class Payment(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        AUTHORIZED = "authorized", "Authorized"
        CAPTURED = "captured", "Captured"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, null=True, blank=True, related_name="payments")
    booking = models.ForeignKey("bookings.Booking", on_delete=models.PROTECT, null=True, blank=True, related_name="payments")
    ride = models.ForeignKey("rides.Ride", on_delete=models.PROTECT, null=True, blank=True, related_name="payments")
    parcel = models.ForeignKey("parcels.ParcelOrder", on_delete=models.PROTECT, null=True, blank=True, related_name="payments")
    service_booking = models.ForeignKey("professionals.ServiceBooking", on_delete=models.PROTECT, null=True, blank=True, related_name="payments")
    event_booking = models.ForeignKey("eventhub.EventBooking", on_delete=models.PROTECT, null=True, blank=True, related_name="payments")
    hotel_booking = models.ForeignKey("hotels.HotelBooking", on_delete=models.PROTECT, null=True, blank=True, related_name="payments")
    method = models.CharField(max_length=30, choices=PaymentMethod.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default=settings.CLICK_DEFAULT_CURRENCY)
    provider = models.CharField(max_length=40, default="internal")
    provider_reference = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["provider", "provider_reference"], name="payments_provider_ref_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gte=0), name="payments_amount_non_negative"),
            # Exactly one target: an order, a show booking, a ride, a parcel, a service booking, an event booking or a hotel booking.
            models.CheckConstraint(condition=_exactly_one(PAYMENT_TARGETS), name="payments_exactly_one_target_v6"),
        ]
