"""Partner Home workspace for travel operators (Click. Travel): today's departures, passengers to board, upcoming runs,
delays and operator cancellations. Every action goes through the travel domain (`booking.operator_update`), so travellers
are notified and refunded exactly as the Customer App describes."""

from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.core.api.exceptions import ConflictError, DomainError
from apps.partners.workspace.base import (
    Action, Metric, Provider, QuickAction, WorkItem, WorkspaceUnavailable, day_bounds, money,
)

from . import booking, engine
from .models import ACTIVE, BookingStatus as S, Journey, Passenger, TravelBooking

DELAYS = {"delay_15": 15, "delay_30": 30, "delay_60": 60}


class TravelProvider(Provider):
    kind = "travel"

    def _operators(self):
        from .models import Operator

        return Operator.objects.filter(partner=self.partner, status="active")

    def connection(self):
        if not self._operators().exists():
            return "not_connected", ("Your Click. Travel operator listing isn’t connected yet. Once Click verifies your permits and "
                                     "sets up your routes, timetables and fares, departures and bookings will appear here.")
        return "live", ""

    def _require(self):
        if not self._operators().exists():
            raise WorkspaceUnavailable(self.connection()[1])

    def _journeys(self):
        return Journey.objects.filter(service__operator__in=self._operators()).select_related("service__operator")

    def _bookings(self):
        return TravelBooking.objects.filter(journey__service__operator__in=self._operators())

    # --- items -------------------------------------------------------------------------------------------------
    def _departure(self, j: Journey) -> WorkItem:
        svc = j.service
        first = svc.stops.order_by("seq").first()
        last = svc.stops.order_by("-seq").first()
        departs = engine.at(j.date, first, "depart") if first and first.depart else None
        bookings = TravelBooking.objects.filter(journey=j, status__in=ACTIVE)
        pax = Passenger.objects.filter(journey=j, holds_seat=True, booking__status__in=ACTIVE)
        seats = pax.count()
        capacity = sum(fc.capacity for fc in svc.classes.all())
        boarded = pax.filter(boarded_at__isnull=False).count()
        actions = []
        if j.status != Journey.Status.CANCELLED and departs and departs > timezone.now() - timedelta(hours=2):
            for key, minutes in DELAYS.items():
                if j.delay_minutes != minutes:
                    actions.append(Action(key, f"Running {minutes} min late", confirm=f"Every traveller on this run is told it leaves about {minutes} minutes late."))
                    break
            if j.delay_minutes:
                actions.append(Action("on_time", "Back on time", confirm="Travellers are told the run is back on schedule."))
            actions.append(Action("cancel_run", "Cancel run", "danger", needs_reason=True,
                                  confirm=f"{bookings.count()} booking{'s' if bookings.count() != 1 else ''} will be cancelled and refunded in full."))
        label = j.get_status_display() + (f" · {j.delay_minutes} min late" if j.delay_minutes and j.status != Journey.Status.CANCELLED else "")
        return WorkItem(
            kind="journey", id=str(j.id), ref=f"{svc.number} · {j.date:%d %b}",
            title=f"{first.place.name if first else ''} → {last.place.name if last else ''}".strip(" →") or (svc.name or svc.number),
            subtitle=f"{svc.operator.name} · {svc.get_bus_type_display() if svc.bus_type else svc.get_mode_display()}" + (" · AC" if svc.ac else ""),
            status=j.status, status_label=label,
            tone="muted" if j.status == Journey.Status.CANCELLED else "urgent" if j.delay_minutes else "active",
            at=departs, fields=[("Seats sold", f"{seats} of {capacity}"), ("Boarded", f"{boarded} of {seats}" if seats else "—"),
                                ("Bookings", str(bookings.count())), ("Notice", j.notice)],
            actions=actions, link=f"/work?view=passengers&journey={j.id}",
        )

    def _booking(self, b: TravelBooking) -> WorkItem:
        pax = list(b.passengers.filter(holds_seat=True))
        boarded = sum(1 for p in pax if p.boarded_at)
        actions = []
        if b.status == S.CONFIRMED and pax and boarded < len(pax) and b.departs_at - timedelta(hours=3) <= timezone.now() <= b.departs_at + timedelta(hours=6):
            actions.append(Action("board", "Mark boarded", "primary", confirm=f"Confirm {len(pax) - boarded} traveller(s) on {b.pnr or b.number} have boarded."))
        state = ("Boarded" if pax and boarded == len(pax) and b.status == S.CONFIRMED else b.get_status_display())
        return WorkItem(
            kind="travel_booking", id=str(b.id), ref=b.pnr or b.number,
            title=", ".join(p.name for p in pax[:3]) + (f" +{len(pax) - 3}" if len(pax) > 3 else "") or b.number,
            subtitle=f"{b.from_label} → {b.to_label} · {b.departs_at.astimezone(engine.tz()):%d %b, %I:%M %p}",
            status=b.status, status_label=state,
            tone="success" if state == "Boarded" else "active" if b.status == S.CONFIRMED else "muted",
            at=b.departs_at, amount=b.total,
            fields=[("Seats", ", ".join(p.seat for p in pax if p.seat) or "Assigned at boarding"), ("Class", b.class_name),
                    ("Travellers", str(len(pax))), ("Contact", b.contact_phone if b.status == S.CONFIRMED else "")],
            actions=actions,
        )

    # --- Home sections -----------------------------------------------------------------------------------------
    def action_required(self):
        self._require()
        t = engine.today()
        return [self._departure(j) for j in self._journeys().filter(date=t).exclude(status=Journey.Status.CANCELLED)
                .annotate(n=Count("bookings", filter=Q(bookings__status__in=ACTIVE))).filter(n__gt=0).order_by("service__number")]

    def active(self):
        self._require()
        now = timezone.now()
        rows = self._bookings().filter(status=S.CONFIRMED, departs_at__lte=now + timedelta(hours=1), departs_at__gte=now - timedelta(hours=1))
        return [self._booking(b) for b in rows.order_by("departs_at")[:20]]

    def incoming(self):
        self._require()
        t = engine.today()
        rows = self._journeys().filter(date__gt=t, date__lte=t + timedelta(days=2)).exclude(status=Journey.Status.CANCELLED)
        rows = rows.annotate(n=Count("bookings", filter=Q(bookings__status__in=ACTIVE))).filter(n__gt=0).order_by("date")[:10]
        return [self._departure(j) for j in rows]

    def metrics(self, day):
        self._require()
        start, end = day_bounds(day)
        today_runs = self._journeys().filter(date=day).exclude(status=Journey.Status.CANCELLED)
        pax = Passenger.objects.filter(journey__in=today_runs, holds_seat=True, booking__status__in=ACTIVE)
        sold = self._bookings().filter(status__in=[S.CONFIRMED, S.COMPLETED], confirmed_at__gte=start, confirmed_at__lt=end)
        value = sold.aggregate(t=Sum("total"))["t"] or 0
        return {
            "departures": Metric("departures", "Departures today", today_runs.count(), str(today_runs.count())),
            "passengers": Metric("passengers", "Travelling today", pax.count(), str(pax.count())),
            "seats_sold": Metric("seats_sold", "Bookings today", sold.count(), str(sold.count()), "Tickets confirmed today, any date of travel."),
            "revenue": Metric("revenue", "Booked today", float(value), money(value), "Ticket value confirmed today."),
        }

    def earnings(self, start, end):
        if not self._operators().exists():
            return 0, 0
        qs = self._bookings().filter(status=S.COMPLETED, arrives_at__gte=start, arrives_at__lt=end)
        return (qs.aggregate(t=Sum("total"))["t"] or 0), qs.count()

    def earnings_note(self):
        return "Value of completed journeys. Click’s commission and your payouts appear in Payouts once your settlement terms are set."

    def earnings_count_label(self):
        return "bookings"

    def earnings_recent(self, start, end, limit=20):
        qs = self._bookings().filter(status=S.COMPLETED, arrives_at__gte=start, arrives_at__lt=end).order_by("-arrives_at")[:limit]
        return [{"ref": b.pnr or b.number, "title": f"{b.from_label} → {b.to_label}", "amount": money(b.total),
                 "at": b.arrives_at.isoformat(), "detail": f"{b.passengers.filter(holds_seat=True).count()} traveller(s)"} for b in qs]

    def quick_actions(self):
        if not self._operators().exists():
            return {}
        return {"today": QuickAction("today", "Today", "bus", "/work?view=today", len(self.action_required())),
                "upcoming": QuickAction("upcoming", "Upcoming", "history", "/work?view=upcoming"),
                "earnings": QuickAction("earnings", "Earnings", "wallet", "/earnings")}

    def context_line(self, action_items, active, is_available):
        if active:
            return f"{len(active)} booking{'s' if len(active) != 1 else ''} boarding now."
        if action_items:
            return f"{len(action_items)} departure{'s' if len(action_items) != 1 else ''} with travellers today."
        return "Bookings are open." if is_available else "Bookings are closed. Customers can’t book new seats."

    def activity(self, limit=8):
        rows = self._bookings().exclude(status=S.PENDING_PAYMENT).order_by("-updated_at")[:limit]
        return [{"id": str(b.id), "title": f"{b.get_status_display()} · {b.pnr or b.number}", "body": f"{b.from_label} → {b.to_label}",
                 "amount": money(b.total), "at": b.updated_at.isoformat(),
                 "tone": "success" if b.status == S.COMPLETED else "muted" if b.status == S.CANCELLED else "info"} for b in rows]

    # --- Work page ---------------------------------------------------------------------------------------------
    def views(self):
        if not self._operators().exists():
            return []
        return [{"key": "today", "label": "Today", "count": len(self.action_required())},
                {"key": "boarding", "label": "Boarding", "count": len(self.active()) or None},
                {"key": "upcoming", "label": "Upcoming", "count": None},
                {"key": "history", "label": "History", "count": None}]

    def work(self, view, limit=50):
        if not self._operators().exists():
            return []
        t = engine.today()
        if view in ("today", "requests"):
            return self.action_required()
        if view in ("boarding", "active"):
            today = self._bookings().filter(status=S.CONFIRMED, journey__date=t).order_by("departs_at")
            return [self._booking(b) for b in today[:limit]]
        if view == "upcoming":
            rows = self._journeys().filter(date__gt=t, date__lte=t + timedelta(days=14)).order_by("date", "service__number")[:limit]
            return [self._departure(j) for j in rows]
        return [self._booking(b) for b in self._bookings().exclude(status=S.PENDING_PAYMENT).order_by("-departs_at")[:limit]]

    @transaction.atomic
    def perform(self, kind, item_id, action, payload, actor):
        self._require()
        if kind == "journey":
            j = get_object_or_404(self._journeys(), pk=item_id)
            if j.status == Journey.Status.CANCELLED:
                raise ConflictError("This run is already cancelled.", code="invalid_transition")
            if action in DELAYS:
                booking.operator_update(j, Journey.Status.DELAYED, DELAYS[action], j.notice)
            elif action == "on_time":
                booking.operator_update(j, Journey.Status.SCHEDULED, 0, j.notice)
            elif action == "cancel_run":
                reason = str(payload.get("reason") or "").strip()
                if len(reason) < 3:
                    raise DomainError("Tell travellers why the run is cancelled.", code="reason_required")
                booking.operator_update(j, Journey.Status.CANCELLED, 0, reason)
            else:
                raise DomainError("Unknown action.", code="unknown_action")
            return self._departure(Journey.objects.select_related("service__operator").get(pk=j.pk))
        if kind == "travel_booking":
            b = get_object_or_404(self._bookings().select_for_update(), pk=item_id)
            if action != "board":
                raise DomainError("Unknown action.", code="unknown_action")
            if b.status != S.CONFIRMED:
                raise ConflictError(f"This booking is {b.get_status_display().lower()}.", code="invalid_transition")
            now = timezone.now()
            if not (b.departs_at - timedelta(hours=3) <= now <= b.departs_at + timedelta(hours=6)):
                raise ConflictError("Boarding opens 3 hours before departure.", code="too_early")
            b.passengers.filter(holds_seat=True, boarded_at__isnull=True).update(boarded_at=now, updated_at=now)
            return self._booking(b)
        raise DomainError("Unknown work item.", code="unknown_item", status_code=404)

    # --- availability --------------------------------------------------------------------------------------------
    # Applied in apps.travel.booking._resolve: a closed operator's journeys can't be booked.
