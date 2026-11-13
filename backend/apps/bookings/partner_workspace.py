"""Partner Home workspace for cinemas and venues: today's shows, seat bookings, occupancy and revenue (apps.bookings)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.partners.workspace.base import (
    Metric, Provider, QuickAction, WorkItem, day_bounds, local_today, money, pct,
)

from apps.partners.workspace.base import BUSINESS_TZ

from .models import Booking, Show, Venue


def _time(dt) -> str:
    from apps.partners.workspace.base import BUSINESS_TZ

    return timezone.localtime(dt, BUSINESS_TZ).strftime("%I:%M %p").lstrip("0")


class VenueProvider(Provider):
    kind = "venue"

    def _venue_ids(self) -> list:
        if not hasattr(self, "_ids"):
            self._ids = list(Venue.objects.filter(partner_link__partner=self.partner).values_list("id", flat=True))
        return self._ids

    def connection(self):
        if self._venue_ids():
            return "live", ""
        return "not_connected", ("Your venue isn’t listed on Click yet. Once Click verifies you and connects your venue, "
                                 "your shows and bookings will appear here.")

    def _shows(self):
        return (Show.objects.filter(venue_id__in=self._venue_ids(), status=Show.Status.SCHEDULED)
                .select_related("event", "venue")
                .annotate(sold=Count("booked_seats", filter=Q(booked_seats__is_active=True))))

    def _bookings(self):
        return Booking.objects.filter(show__venue_id__in=self._venue_ids()).select_related("show__event", "customer__user")

    def _show_item(self, s: Show, tone: str, label: str) -> WorkItem:
        cap = s.rows * s.seats_per_row
        occ = pct(s.sold, cap) or 0
        multi = len(self._venue_ids()) > 1
        return WorkItem(
            kind="show", id=str(s.id), ref=_time(s.starts_at), title=s.event.title,
            subtitle=" · ".join(x for x in [s.screen, s.format, s.language, s.venue.name if multi else ""] if x),
            status=label.lower().replace(" ", "_"), status_label=label, tone=tone, at=s.starts_at,
            fields=[("Starts", _time(s.starts_at)), ("Tickets sold", f"{s.sold} of {cap}"), ("Occupancy", f"{occ}%")],
        )

    def _running(self):
        now = timezone.now()
        out = []
        for s in self._shows().filter(starts_at__lte=now, starts_at__gte=now - timedelta(hours=4)):
            if s.starts_at + timedelta(minutes=s.event.duration_minutes or 150) > now:
                out.append(s)
        return out

    # --- Home sections -------------------------------------------------------------------------------
    def action_required(self):
        now = timezone.now()
        soon = self._shows().filter(starts_at__gt=now, starts_at__lte=now + timedelta(hours=2)).order_by("starts_at")[:5]
        return [self._show_item(s, "urgent", "Starting soon") for s in soon]

    def active(self):
        return [self._show_item(s, "active", "Now showing") for s in self._running()]

    def incoming(self):
        now = timezone.now()
        _, end = day_bounds(local_today())
        later = self._shows().filter(starts_at__gt=now + timedelta(hours=2), starts_at__lt=end).order_by("starts_at")[:8]
        return [self._show_item(s, "info", "Later today") for s in later]

    def metrics(self, day):
        start, end = day_bounds(day)
        shows = list(self._shows().filter(starts_at__gte=start, starts_at__lt=end))
        tickets = sum(s.sold for s in shows)
        capacity = sum(s.rows * s.seats_per_row for s in shows)
        occ = pct(tickets, capacity)
        revenue, _ = self.earnings(start, end)
        return {
            "shows": Metric("shows", "Shows", len(shows), str(len(shows)), "Scheduled today"),
            "tickets": Metric("tickets", "Tickets", tickets, str(tickets), "Seats sold for today"),
            "occupancy": Metric("occupancy", "Occupancy", occ, f"{occ}%" if occ is not None else "—", "Today’s shows"),
            "revenue": Metric("revenue", "Revenue", money(revenue), f"₹{revenue:,.0f}", "Ticket sales booked today"),
        }

    def earnings(self, start, end):
        agg = self._bookings().filter(status=Booking.Status.CONFIRMED, created_at__gte=start, created_at__lt=end).aggregate(
            total=Sum("subtotal"), n=Count("id"))
        return agg["total"] or Decimal("0"), agg["n"]

    def earnings_note(self):
        return "Ticket value of confirmed bookings (Click’s convenience fee excluded). Payouts aren’t set up yet."

    def earnings_count_label(self):
        return "bookings"

    def earnings_recent(self, start, end, limit=20):
        qs = self._bookings().filter(status=Booking.Status.CONFIRMED, created_at__gte=start, created_at__lt=end)
        return [{"ref": b.reference, "title": b.show.event.title, "amount": money(b.subtotal), "at": b.created_at.isoformat(),
                 "detail": f"Show {_time(b.show.starts_at)}"} for b in qs.order_by("-created_at")[:limit]]

    def performance(self):
        now = timezone.now()
        past = list(self._shows().filter(starts_at__gte=now - timedelta(days=7), starts_at__lt=now))
        occ = pct(sum(s.sold for s in past), sum(s.rows * s.seats_per_row for s in past))
        b = self._bookings().filter(created_at__gte=now - timedelta(days=30)).aggregate(
            n=Count("id"), c=Count("id", filter=Q(status=Booking.Status.CANCELLED)))
        canc = pct(b["c"], b["n"])
        return {
            "occupancy_7d": Metric("occupancy_7d", "Occupancy", occ, f"{occ}%" if occ is not None else "—", "Shows in the last 7 days"),
            "cancellation_rate": Metric("cancellation_rate", "Cancellations", canc, f"{canc}%" if canc is not None else "—",
                                        "Bookings cancelled, last 30 days"),
        }

    def activity(self, limit=8):
        return [{"id": str(b.id), "title": f"{'Booking cancelled' if b.status == Booking.Status.CANCELLED else 'New booking'} · {b.reference}",
                 "body": f"{b.show.event.title} · {_time(b.show.starts_at)}", "at": (b.cancelled_at or b.created_at).isoformat(),
                 "amount": money(b.subtotal) if b.status == Booking.Status.CONFIRMED else None,
                 "tone": "muted" if b.status == Booking.Status.CANCELLED else "success"}
                for b in self._bookings().order_by("-updated_at")[:limit]]

    def quick_actions(self):
        start, end = day_bounds(local_today())
        return {
            "shows": QuickAction("shows", "Shows", "film", "/work?view=shows",
                                 self._shows().filter(starts_at__gte=timezone.now(), starts_at__lt=end).count()),
            "bookings": QuickAction("bookings", "Bookings", "ticket", "/work?view=bookings"),
            "earnings": QuickAction("earnings", "Revenue", "chart", "/earnings"),
        }

    def context_line(self, action_items, active, is_available):
        if action_items:
            s = action_items[0]
            return f"Next show: {s.title} at {s.ref}."
        if active:
            return f"{active[0].title} is showing now."
        upcoming = self._shows().filter(starts_at__gt=timezone.now()).order_by("starts_at").first()
        if upcoming:
            local = timezone.localtime(upcoming.starts_at, BUSINESS_TZ)
            day = "today" if local.date() == local_today() else local.strftime("on %a %d %b")
            return f"Your next show, {upcoming.event.title}, starts {day} at {_time(upcoming.starts_at)}."
        return "No upcoming shows scheduled."

    # --- Work page -----------------------------------------------------------------------------------
    def views(self):
        return [{"key": "shows", "label": "Upcoming shows", "count": None}, {"key": "bookings", "label": "Bookings", "count": None}]

    def work(self, view, limit=50):
        if view == "bookings":
            out = []
            for b in self._bookings().prefetch_related("seats").order_by("-created_at")[:limit]:
                seats = [s.label for s in b.seats.all()]
                name = (b.customer.user.full_name or "").split()
                cancelled = b.status == Booking.Status.CANCELLED
                out.append(WorkItem(
                    kind="booking", id=str(b.id), ref=b.reference, title=b.show.event.title,
                    subtitle=f"{timezone.localtime(b.show.starts_at, BUSINESS_TZ).strftime('%a %d %b')} · {_time(b.show.starts_at)}",
                    status=b.status, status_label=b.get_status_display(), tone="muted" if cancelled else "success",
                    at=b.created_at, amount=b.subtotal, currency=b.currency,
                    fields=[("Seats", ", ".join(seats)), ("Customer", name[0] if name else ""), ("Screen", b.show.screen)]))
            return out
        now = timezone.now()
        shows = self._shows().filter(starts_at__gt=now - timedelta(hours=3), starts_at__lt=now + timedelta(days=3)).order_by("starts_at")
        return [self._show_item(s, "info", "Scheduled") for s in shows[:limit]]
