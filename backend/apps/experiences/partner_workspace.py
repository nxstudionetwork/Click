"""Partner Home workspace for attractions, temples and experience providers (Click. Bookings): today's visitors, entry
verification, upcoming bookings and booked value. Check-in uses the same rules as the gate scanner (`booking.check_in`)."""

from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404

from apps.core.api.exceptions import DomainError
from apps.partners.workspace.base import (
    Action, Metric, Provider, QuickAction, WorkItem, WorkspaceUnavailable, day_bounds, money,
)

from . import booking
from .models import Attraction, BookingStatus as S, ExperienceBooking


class ExperiencesProvider(Provider):
    kind = "experiences"

    def _places(self):
        return Attraction.objects.filter(provider=self.partner)

    def connection(self):
        if not self._places().filter(bookable=True).exists():
            return "not_connected", ("Your place isn’t bookable on Click. Bookings yet. Once Click verifies you as the operator and "
                                     "publishes your tickets and time slots, visitors and check-ins will appear here.")
        return "live", ""

    def _require(self):
        if self.connection()[0] != "live":
            raise WorkspaceUnavailable(self.connection()[1])

    def _bookings(self):
        return ExperienceBooking.objects.filter(attraction__provider=self.partner).select_related("attraction", "offering")

    def _item(self, b: ExperienceBooking) -> WorkItem:
        t = booking.today()
        actions = []
        if b.status == S.CONFIRMED and b.visit_date == t and not b.checked_in_at:
            actions.append(Action("check_in", "Verify entry", "primary",
                                  confirm=f"Confirm {b.visitors} visitor(s) on {b.number} are at the entrance with code {b.entry_code}."))
        state = ("Checked in" if b.checked_in_at else "Visiting today" if b.visit_date == t and b.status == S.CONFIRMED
                 else b.get_status_display())
        return WorkItem(
            kind="experience_booking", id=str(b.id), ref=b.number, title=f"{b.lead_name} · {b.visitors} visitor{'s' if b.visitors != 1 else ''}",
            subtitle=f"{b.title} · {b.visit_date:%d %b}" + (f", {b.slot_time:%I:%M %p}" if b.slot_time else ""),
            status=b.status, status_label=state,
            tone="success" if b.checked_in_at else "urgent" if state == "Visiting today" else "active" if b.status == S.CONFIRMED else "muted",
            at=b.confirmed_at or b.created_at, amount=b.total,
            fields=[("Tickets", ", ".join(f"{line.get('qty')} × {line.get('label')}" for line in (b.lines or []))),
                    ("Entry code", b.entry_code if b.status == S.CONFIRMED else ""), ("Pickup", b.pickup_point)],
            actions=actions,
        )

    def action_required(self):
        self._require()
        t = booking.today()
        return [self._item(b) for b in self._bookings().filter(status=S.CONFIRMED, visit_date=t, checked_in_at__isnull=True)
                .order_by("slot_time", "created_at")[:50]]

    def active(self):
        return []

    def incoming(self):
        self._require()
        t = booking.today()
        return [self._item(b) for b in self._bookings().filter(status=S.CONFIRMED, visit_date__gt=t, visit_date__lte=t + timedelta(days=2))
                .order_by("visit_date", "slot_time")[:10]]

    def metrics(self, day):
        self._require()
        start, end = day_bounds(day)
        visiting = self._bookings().filter(status__in=[S.CONFIRMED, S.COMPLETED], visit_date=day)
        booked = self._bookings().filter(status__in=[S.CONFIRMED, S.COMPLETED], confirmed_at__gte=start, confirmed_at__lt=end)
        value = booked.aggregate(t=Sum("total"))["t"] or 0
        visitors = visiting.aggregate(n=Sum("visitors"))["n"] or 0
        checked = visiting.filter(checked_in_at__isnull=False).aggregate(n=Sum("visitors"))["n"] or 0
        upcoming = self._bookings().filter(status=S.CONFIRMED, visit_date__gt=day).count()
        return {
            "visits": Metric("visits", "Visitors today", visitors, str(visitors)),
            "checked_in": Metric("checked_in", "Checked in", checked, f"{checked} of {visitors}" if visitors else "0"),
            "upcoming": Metric("upcoming", "Upcoming bookings", upcoming, str(upcoming)),
            "revenue": Metric("revenue", "Booked today", float(value), money(value), "Ticket value confirmed today."),
        }

    def earnings(self, start, end):
        if self.connection()[0] != "live":
            return 0, 0
        qs = self._bookings().filter(status__in=[S.CONFIRMED, S.COMPLETED], checked_in_at__gte=start, checked_in_at__lt=end)
        return (qs.aggregate(t=Sum("total"))["t"] or 0), qs.count()

    def earnings_note(self):
        return "Ticket value of visits verified at your entrance. Payout terms appear in Payouts once agreed with Click."

    def earnings_count_label(self):
        return "visits"

    def quick_actions(self):
        if self.connection()[0] != "live":
            return {}
        return {"today": QuickAction("today", "Today", "ticket", "/work?view=today", len(self.action_required())),
                "check_in": QuickAction("check_in", "Verify entry", "check", "/check-in"),
                "earnings": QuickAction("earnings", "Earnings", "wallet", "/earnings")}

    def context_line(self, action_items, active, is_available):
        if action_items:
            return f"{len(action_items)} booking{'s' if len(action_items) != 1 else ''} visiting today, not yet checked in."
        return "Bookings are open." if is_available else "Bookings are closed. Visitors can’t book new tickets."

    def activity(self, limit=8):
        rows = self._bookings().exclude(status=S.PENDING_PAYMENT).order_by("-updated_at")[:limit]
        return [{"id": str(b.id), "title": f"{'Checked in' if b.checked_in_at else b.get_status_display()} · {b.number}",
                 "body": b.title, "amount": money(b.total), "at": b.updated_at.isoformat(),
                 "tone": "success" if b.checked_in_at else "muted" if b.status == S.CANCELLED else "info"} for b in rows]

    def views(self):
        if self.connection()[0] != "live":
            return []
        return [{"key": "today", "label": "Today", "count": len(self.action_required())},
                {"key": "upcoming", "label": "Upcoming", "count": None}, {"key": "history", "label": "History", "count": None}]

    def work(self, view, limit=50):
        if self.connection()[0] != "live":
            return []
        t = booking.today()
        if view in ("today", "requests"):
            return [self._item(b) for b in self._bookings().filter(status__in=[S.CONFIRMED, S.COMPLETED], visit_date=t).order_by("slot_time")[:limit]]
        if view == "upcoming":
            return [self._item(b) for b in self._bookings().filter(status=S.CONFIRMED, visit_date__gt=t).order_by("visit_date", "slot_time")[:limit]]
        return [self._item(b) for b in self._bookings().exclude(status=S.PENDING_PAYMENT).order_by("-visit_date")[:limit]]

    @transaction.atomic
    def perform(self, kind, item_id, action, payload, actor):
        self._require()
        if kind != "experience_booking" or action != "check_in":
            raise DomainError("Unknown action.", code="unknown_action")
        b = get_object_or_404(self._bookings(), pk=item_id)
        return self._item(booking.check_in(self.partner, b.entry_code))
