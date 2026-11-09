"""
Partner notifications. Created from the shared domain events (a customer's order, booking or ride request, a
cancellation, a verification decision) through signals, so the Customer App's code paths stay unchanged and every
notification points at real work. Read state is per partner.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models.signals import post_save
from django.utils import timezone

from .models import Partner, PartnerNotification, PartnerStatusEvent

C = PartnerNotification.Category


def notify_partner(partner: Partner, category: str, title: str, body: str = "", link_path: str = "") -> PartnerNotification:
    if link_path and not link_path.startswith("/"):
        raise ValueError("link_path must be an in-app path")
    return PartnerNotification.objects.create(partner=partner, category=category, title=title[:120], body=body[:300],
                                              link_path=link_path[:200])


def unread_count(partner: Partner) -> int:
    return partner.notifications.filter(read_at__isnull=True).count()


def mark_read(partner: Partner, notification_id=None) -> int:
    qs = partner.notifications.filter(read_at__isnull=True)
    if notification_id is not None:
        qs = qs.filter(pk=notification_id)
    return qs.update(read_at=timezone.now())


# --- receivers -------------------------------------------------------------------------------------------------

def _on_partner_status(sender, instance: PartnerStatusEvent, created, **kwargs):
    if not created:
        return
    copy = {
        Partner.Status.VERIFIED: ("You’re verified", "Click approved your Partner profile."),
        Partner.Status.ACTIVE: ("Your account is active", "You can now receive work through Click."),
        Partner.Status.REJECTED: ("Verification not approved", instance.note or "Contact Click Partner support to resolve it."),
        Partner.Status.SUSPENDED: ("Account suspended", instance.note or "Contact Click Partner support."),
    }.get(instance.to_status)
    if copy:
        notify_partner(instance.partner, C.ACCOUNT, copy[0], copy[1], "/home")


def _on_ride_offer(sender, instance, created, **kwargs):
    if not created:
        return
    ride = instance.ride
    notify_partner(instance.driver, C.WORK, "New ride request",
                   f"{ride.pickup_label} → {ride.drop_label} · ₹{ride.total:.0f}", "/work?view=requests")


def _on_ride_event(sender, instance, created, **kwargs):
    if not created or instance.to_status != "cancelled":
        return
    ride = instance.ride
    if ride.driver_id:
        notify_partner(ride.driver, C.UPDATE, "Ride cancelled", f"{ride.number} was cancelled by the customer.", "/work?view=trips")


def _store_partner(store_id):
    from .models import PartnerStore

    link = PartnerStore.objects.select_related("partner").filter(store_id=store_id).first()
    return link.partner if link else None


def _on_order(sender, instance, created, **kwargs):
    if not created:
        return
    order_id, store_id = instance.pk, instance.store_id

    def send():  # after commit, so the order's items exist and a rolled-back placement never notifies
        from apps.orders.models import Order

        partner = _store_partner(store_id)
        order = Order.objects.filter(pk=order_id).prefetch_related("items").first()
        if partner and order:
            n = sum(i.quantity for i in order.items.all())
            notify_partner(partner, C.WORK, f"New order {order.number}", f"{n} item{'s' if n != 1 else ''} · ₹{order.total:.0f}",
                           "/work?view=new")

    transaction.on_commit(send)


def _on_order_event(sender, instance, created, **kwargs):
    if not created or instance.to_status != "cancelled":
        return
    order = instance.order
    partner = _store_partner(order.store_id)
    if partner and instance.actor_id and instance.actor_id == order.customer.user_id:
        notify_partner(partner, C.UPDATE, f"Order {order.number} cancelled", "The customer cancelled this order.", "/work?view=all")


def _on_booking(sender, instance, created, **kwargs):
    if not created:
        return
    booking_id = instance.pk

    def send():
        from apps.bookings.models import Booking

        from .models import PartnerVenue

        b = Booking.objects.select_related("show__event", "show__venue").prefetch_related("seats").filter(pk=booking_id).first()
        link = PartnerVenue.objects.select_related("partner").filter(venue_id=b.show.venue_id).first() if b else None
        if link:
            seats = len(b.seats.all())
            from .workspace.base import BUSINESS_TZ

            when = timezone.localtime(b.show.starts_at, BUSINESS_TZ).strftime("%d %b, %I:%M %p")
            notify_partner(link.partner, C.WORK, f"New booking {b.reference}",
                           f"{b.show.event.title} · {seats} seat{'s' if seats != 1 else ''} · {when}", "/work?view=bookings")

    transaction.on_commit(send)


def connect() -> None:
    from apps.bookings.models import Booking
    from apps.orders.models import Order, OrderStatusEvent
    from apps.rides.models import RideDriverOffer, RideStatusEvent

    post_save.connect(_on_partner_status, sender=PartnerStatusEvent, dispatch_uid="partners.notify.status")
    post_save.connect(_on_ride_offer, sender=RideDriverOffer, dispatch_uid="partners.notify.ride_offer")
    post_save.connect(_on_ride_event, sender=RideStatusEvent, dispatch_uid="partners.notify.ride_event")
    post_save.connect(_on_order, sender=Order, dispatch_uid="partners.notify.order")
    post_save.connect(_on_order_event, sender=OrderStatusEvent, dispatch_uid="partners.notify.order_event")
    post_save.connect(_on_booking, sender=Booking, dispatch_uid="partners.notify.booking")
