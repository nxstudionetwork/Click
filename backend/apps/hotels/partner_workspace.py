"""Partner Home workspace for hotels, resorts, homestays and serviced apartments (Click. Hotels): arrivals, in-house
guests, departures, upcoming reservations. Inventory (units, closures, nightly prices) has its own partner endpoint."""

from __future__ import annotations

from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.core.api.exceptions import ConflictError, DomainError
from apps.partners.workspace.base import Action, Metric, Provider, QuickAction, WorkItem, WorkspaceUnavailable, day_bounds, money

from . import booking, engine
from .models import BookingStatus as S, HotelBooking, HotelProperty, StatusEvent


class HotelsProvider(Provider):
    kind = "hotels"

    def _p(self) -> HotelProperty | None:
        if not hasattr(self, "_prop"):
            self._prop = HotelProperty.objects.filter(partner=self.partner).first()
        return self._prop

    def connection(self):
        if self._p() is None:
            return "not_connected", ("Your Click. Hotels listing isn’t set up yet. Once Click verifies your property and its rooms, rates and "
                                     "policies, reservations will appear here.")
        return "live", ""

    def _bookings(self):
        return HotelBooking.objects.filter(property=self._p()).select_related("customer__user")

    def _item(self, b: HotelBooking) -> WorkItem:
        t = engine.today()
        actions = []
        if b.status == S.CONFIRMED and b.check_in <= t < b.check_out and not b.checked_in_at:
            actions.append(Action("check_in", "Guest arrived", "primary"))
        if b.status == S.CONFIRMED and b.checked_in_at:
            if b.payment_status == HotelBooking.PaymentStatus.AT_PROPERTY:
                actions.append(Action("paid_at_property", "Payment collected", "primary", confirm=f"Confirm you collected ₹{b.total:,.2f}."))
            actions.append(Action("check_out", "Check out", "secondary" if actions else "primary", confirm="Confirm the guest has checked out."))
        state = ("In house" if b.checked_in_at and b.status == S.CONFIRMED else "Arriving today" if b.check_in == t and b.status == S.CONFIRMED
                 else b.get_status_display())
        return WorkItem(
            kind="hotel_booking", id=str(b.id), ref=b.number, title=f"{b.guest_name} · {b.room_name}",
            subtitle=f"{b.check_in:%d %b} – {b.check_out:%d %b} · {b.nights} night{'s' if b.nights > 1 else ''}", status=b.status, status_label=state,
            tone="urgent" if state == "Arriving today" else "active" if b.status == S.CONFIRMED else "success" if b.status == S.COMPLETED else "muted",
            at=b.confirmed_at or b.created_at, amount=b.total,
            fields=[("Guests", f"{b.adults} adult{'s' if b.adults > 1 else ''}{f', {b.children} children' if b.children else ''} · {b.rooms} room{'s' if b.rooms > 1 else ''}"),
                    ("Rate", f"{b.rate_name} · {b.get_meal_plan_display()}"), ("Payment", b.get_payment_status_display()),
                    ("Phone", b.guest_phone), ("Requests", b.special_requests)],
            actions=actions,
        )

    def action_required(self):
        if self._p() is None:
            raise WorkspaceUnavailable(self.connection()[1])
        t = engine.today()
        return [self._item(b) for b in self._bookings().filter(status=S.CONFIRMED, check_in__lte=t, check_out__gte=t).order_by("check_in")]

    def active(self):
        if self._p() is None:
            return []
        return [self._item(b) for b in self._bookings().filter(status__in=[S.CONFIRMED, S.PENDING_PAYMENT], check_in__gt=engine.today()).order_by("check_in")[:30]]

    def metrics(self, day):
        if self._p() is None:
            return {}
        t = engine.today()
        live = self._bookings().filter(status=S.CONFIRMED)
        start, end = day_bounds(day)
        rev = self._bookings().filter(status__in=[S.CONFIRMED, S.COMPLETED], confirmed_at__gte=start, confirmed_at__lt=end).aggregate(t=Sum("total"))["t"] or 0
        return {"arrivals": Metric("arrivals", "Arrivals today", live.filter(check_in=t).count(), ""),
                "in_house": Metric("in_house", "In house", live.filter(checked_in_at__isnull=False).count(), ""),
                "departures": Metric("departures", "Departures today", live.filter(check_out=t).count(), ""),
                "revenue": Metric("revenue", "Booked today", float(rev), money(rev), "Value of reservations confirmed today (payout rules not set yet).")}

    def earnings(self, start, end):
        qs = self._bookings().filter(status=S.COMPLETED, updated_at__gte=start, updated_at__lt=end) if self._p() else HotelBooking.objects.none()
        return (qs.aggregate(t=Sum("total"))["t"] or 0), qs.count()

    def earnings_note(self):
        return "Shows the value of completed stays. Partner payout rates aren’t configured yet."

    def earnings_count_label(self):
        return "stays"

    def quick_actions(self):
        if self._p() is None:
            return {}
        return {"arrivals": QuickAction("arrivals", "Today", "bell", "/work?view=today", len(self.action_required())),
                "in_house": QuickAction("in_house", "Upcoming", "hotel", "/work?view=upcoming", self._bookings().filter(status=S.CONFIRMED, check_in__gt=engine.today()).count()),
                "earnings": QuickAction("earnings", "Earnings", "wallet", "/earnings")}

    def context_line(self, action_items, active, is_available):
        if action_items:
            return f"{len(action_items)} guest{'s' if len(action_items) != 1 else ''} arriving or staying today."
        return "Accepting bookings." if is_available else "Not accepting new bookings."

    def views(self):
        if self._p() is None:
            return []
        return [{"key": "today", "label": "Today", "count": len(self.action_required())},
                {"key": "upcoming", "label": "Upcoming", "count": None}, {"key": "history", "label": "History", "count": None}]

    def work(self, view, limit=50):
        if self._p() is None:
            return []
        if view in ("today", "requests"):
            return self.action_required()
        if view in ("upcoming", "active"):
            return self.active()
        return [self._item(b) for b in self._bookings().exclude(status__in=[S.CONFIRMED, S.PENDING_PAYMENT]).order_by("-check_in")[:limit]]

    def perform(self, kind, item_id, action, payload, actor):
        if kind != "hotel_booking" or self._p() is None:
            raise DomainError("Unknown work item.", code="unknown_item", status_code=404)
        b = get_object_or_404(HotelBooking, pk=item_id, property=self._p())
        if action == "check_in":
            if b.status != S.CONFIRMED or b.checked_in_at or not (b.check_in <= engine.today() < b.check_out):
                raise ConflictError("This guest can’t be checked in now.", code="invalid_transition")
            b.checked_in_at = timezone.now()
            b.save(update_fields=["checked_in_at", "updated_at"])
            StatusEvent.objects.create(booking=b, to=S.CONFIRMED, note="Checked in")
        elif action == "paid_at_property":
            from apps.payments.models import Payment, PaymentMethod

            if b.payment_status != HotelBooking.PaymentStatus.AT_PROPERTY:
                raise ConflictError("Nothing is due at the property.", code="not_payable")
            Payment.objects.create(hotel_booking=b, method=PaymentMethod.PAY_AT_VENUE, amount=b.total, currency=b.currency, status=Payment.Status.CAPTURED)
            b.payment_status = HotelBooking.PaymentStatus.PAID
            b.save(update_fields=["payment_status", "updated_at"])
            StatusEvent.objects.create(booking=b, to=S.CONFIRMED, note="Paid at the property")
        elif action == "check_out":
            if not b.checked_in_at:
                raise ConflictError("Check the guest in first.", code="invalid_transition")
            if b.payment_status == HotelBooking.PaymentStatus.AT_PROPERTY:
                raise ConflictError("Record the payment first.", code="not_paid")
            booking.check_out(b)
        else:
            raise DomainError("Unknown action.", code="unknown_action")
        return self._item(HotelBooking.objects.get(pk=b.pk))
