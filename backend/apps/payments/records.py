"""
Read side of Payments for the customer: every Payment belongs to exactly one Click. thing (order, ride, parcel, booking,
wallet top-up…), so ownership is always resolved through that target on the server — a customer only ever sees
payments for their own records. Also the methods Click. can genuinely take today.
"""

from __future__ import annotations

from django.db.models import Q

from .models import Payment, PaymentMethod

# target field → (service key, label, customer path on the target, reference field, link builder)
TARGETS = {
    "order": ("orders", "Order", "order__customer", lambda p: p.order.number, lambda p: f"/orders/{p.order_id}"),
    "booking": ("shows", "Show tickets", "booking__customer", lambda p: p.booking.reference, lambda p: f"/tickets/{p.booking_id}"),
    "ride": ("ride", "Ride", "ride__customer", lambda p: p.ride.number, lambda p: f"/rides/{p.ride_id}"),
    "parcel": ("parcel", "Parcel", "parcel__customer", lambda p: p.parcel.number, lambda p: f"/parcels/{p.parcel_id}"),
    "service_booking": ("services", "Service booking", "service_booking__customer", lambda p: p.service_booking.number,
                        lambda p: f"/services/bookings/{p.service_booking_id}"),
    "event_booking": ("events", "Event booking", "event_booking__customer", lambda p: p.event_booking.number, lambda p: f"/events/bookings/{p.event_booking_id}"),
    "hotel_booking": ("hotels", "Hotel booking", "hotel_booking__customer", lambda p: p.hotel_booking.number, lambda p: f"/hotels/bookings/{p.hotel_booking_id}"),
    "travel_booking": ("travel", "Travel booking", "travel_booking__customer", lambda p: p.travel_booking.number,
                       lambda p: f"/travel/bookings/{p.travel_booking_id}"),
    "experience_booking": ("bookings", "Booking", "experience_booking__customer", lambda p: p.experience_booking.number,
                           lambda p: f"/bookings/r/{p.experience_booking_id}"),
    "wallet_topup": ("wallet", "Wallet top-up", "wallet_topup__customer", lambda p: p.wallet_topup.provider_reference or str(p.wallet_topup_id)[:8].upper(),
                     lambda p: f"/wallet/activity/{p.wallet_topup.wallet_transaction_id}" if p.wallet_topup.wallet_transaction_id else "/wallet"),
}
ORDER_SERVICE = {"restaurant": ("food", "Food order"), "grocery": ("groceries", "Grocery order"), "retail": ("shop", "Shop order")}

# What Click. can take today (no card / UPI checkout gateway is connected; UPI / card / net banking are used for wallet
# top-ups through the payment provider when one is configured).
METHODS = [
    {"code": PaymentMethod.WALLET, "label": "Click. Wallet", "description": "Pay instantly from your balance. Refunds come back here.",
     "where": "Food, Groceries, Shop, Ride, Parcel, Services, Shows, Events, Hotels, Travel, Bookings", "can_default": True},
    {"code": PaymentMethod.CASH_ON_DELIVERY, "label": "Cash on delivery", "description": "Pay the delivery partner in cash or by UPI when it arrives.",
     "where": "Food, Groceries, Shop", "can_default": True},
    {"code": PaymentMethod.CASH, "label": "Cash to the driver / partner", "description": "Pay at the end of the ride or delivery.",
     "where": "Ride, Parcel", "can_default": False},
    {"code": PaymentMethod.PAY_AT_VENUE, "label": "Pay at the venue / property", "description": "Nothing is charged online.",
     "where": "Shows, Hotels (where the property allows it)", "can_default": False},
]


def owned(customer):
    q = Q()
    for _, (_, _, path, _, _) in TARGETS.items():
        q |= Q(**{path: customer})
    return Payment.objects.filter(q)


def target_field(p: Payment) -> str:
    return next(f for f in TARGETS if getattr(p, f"{f}_id"))


def describe(p: Payment) -> dict:
    f = target_field(p)
    service, label, _, ref, link = TARGETS[f]
    if f == "order":
        service, label = ORDER_SERVICE.get(p.order.store.store_type, ("orders", "Order"))
        label = f"{label} · {p.order.store.name}"
    return {"service": service, "label": label, "reference": ref(p), "link": link(p), "target": f}


OFFLINE = {"cash_on_delivery": "Pay on delivery", "cash": "Pay in cash", "pay_at_venue": "Pay at venue"}


def status_of(p: Payment) -> tuple[str, str]:
    """Customer-facing status (refunds are read from the wallet ledger, never assumed)."""
    if p.status == Payment.Status.CAPTURED:
        refunded = sum((t.amount for t in p.wallet_transactions.all() if t.kind == "refund"), 0)
        if refunded and refunded < p.amount:
            return "partly_refunded", "Partly refunded"
        return "successful", "Successful"
    if p.status == Payment.Status.PENDING and p.method in OFFLINE:
        return "pay_later", OFFLINE[p.method]
    return {"pending": ("pending", "Pending"), "authorized": ("pending", "Processing"), "failed": ("failed", "Failed"),
            "cancelled": ("cancelled", "Cancelled"), "refunded": ("refunded", "Refunded")}[p.status]


def with_relations(qs):
    return qs.select_related("order__store", "booking", "ride", "parcel", "service_booking", "event_booking", "hotel_booking", "travel_booking",
                             "experience_booking", "wallet_topup").prefetch_related("wallet_transactions")
