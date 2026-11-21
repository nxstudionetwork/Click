"""Partner Home workspace for event teams, specialists and venues (Click. Events): quote requests, bookings, history.

The Home/Work actions take a short text (the shared Action contract); the itemised quote, messages, profile, dates,
packages and portfolio have their own partner endpoints (apps.eventhub.urls.partner) for the Partner App's forms."""

from __future__ import annotations

from django.db.models import Sum
from django.shortcuts import get_object_or_404

from apps.core.api.exceptions import DomainError
from apps.partners.workspace.base import Action, Metric, Provider, QuickAction, WorkItem, WorkspaceUnavailable, day_bounds, money

from . import engine, lifecycle
from .models import ACTIVE, BookingStatus as S, Enquiry, EventBooking, EventProvider


def _date(d) -> str:
    return d.strftime("%a %d %b %Y").replace(" 0", " ") if d else "Flexible"


class EventsProvider(Provider):
    kind = "events"

    def _p(self) -> EventProvider | None:
        if not hasattr(self, "_prov"):
            self._prov = EventProvider.objects.filter(partner=self.partner).first()
        return self._prov

    def connection(self):
        if self._p() is None:
            return "not_connected", ("Your Click. Events profile isn’t set up yet. Once Click verifies you and lists your services, "
                                     "packages and service area, quote requests will appear here.")
        return "live", ""

    def _enquiries(self):
        return (Enquiry.objects.filter(provider=self._p(), status__in=[Enquiry.Status.REQUESTED, Enquiry.Status.REVISION])
                .select_related("plan__event_type", "plan__customer__user", "package").order_by("created_at"))

    def _bookings(self):
        return EventBooking.objects.filter(provider=self._p()).select_related("plan__event_type", "customer__user")

    def _customer(self, user) -> str:
        n = (user.full_name or "").strip()
        return n.split()[0] if n else "Customer"

    def _enquiry_item(self, e: Enquiry) -> WorkItem:
        p = e.plan
        last = e.quotes.first()
        budget = ("Flexible" if p.budget_flexible and p.budget_max is None else
                  f"₹{p.budget_min or 0:,.0f} – ₹{p.budget_max:,.0f}" if p.budget_max is not None else "Not set")
        return WorkItem(
            kind="event_enquiry", id=str(e.id), ref=p.number, title=f"{p.event_type.name} · {p.guests} guests",
            status=e.status, status_label="Changes requested" if e.status == Enquiry.Status.REVISION else "Quote requested", tone="urgent",
            subtitle=f"{_date(p.date)}{' (flexible)' if p.date_flexible else ''} · {p.address.get('line2') or p.address.get('city', '')}", at=e.updated_at,
            fields=[("Customer", self._customer(p.customer.user)), ("Date", _date(p.date) + (f" · {p.date_note}" if p.date_note else "")),
                    ("Guests", str(p.guests)), ("Services", ", ".join(s.name for s in p.services.all())), ("Budget", budget),
                    ("Package", e.package.name if e.package_id else ""), ("Requirements", p.requirements[:300]),
                    ("Photos", f"{p.attachments.count()} attached" if p.attachments.exists() else ""),
                    ("Change request", last.customer_note if last and e.status == Enquiry.Status.REVISION else "")],
            actions=[Action("quote", "Send quote" if e.status == Enquiry.Status.REQUESTED else "Send revised quote", "primary", needs_reason=True,
                            confirm="Type the total before tax and what it covers, e.g. “45000 decoration, stage and lights”. "
                                    "Use Quotes in the app for an itemised quote."),
                     Action("decline", "Not available", "secondary", needs_reason=True, confirm="Tell the customer why (optional).")],
            link=f"/events/enquiries/{e.id}",
        )

    def _booking_item(self, b: EventBooking) -> WorkItem:
        nxt = b.milestones.filter(done_at__isnull=True).exclude(key__in=["event_day", "completed", "payment"]).first()
        steps = {
            S.PAYMENT_PENDING: [],
            S.CONFIRMED: [Action("preparing", "Team assigned", "primary", needs_reason=True, confirm="Who leads the team on the day? (shown to the customer)")],
            S.PREPARING: [Action("start", "Start event", "primary", confirm="Start only on the event day, on site.")],
            S.IN_PROGRESS: [Action("complete", "Event completed", "primary", confirm="Confirm the event is done.")],
        }.get(b.status, [])
        if nxt and b.status in (S.CONFIRMED, S.PREPARING):
            steps.append(Action("milestone", f"Done: {nxt.label}", "secondary", needs_reason=True, confirm="Add a short note for the customer (optional)."))
        tone = {"completed": "success", "cancelled": "muted", "payment_pending": "info"}.get(b.status, "active")
        return WorkItem(
            kind="event_booking", id=str(b.id), ref=b.number, title=b.title, subtitle=f"{_date(b.event_date)} · {self._customer(b.customer.user)}",
            status=b.status, status_label=b.get_status_display(), tone=tone, at=b.confirmed_at or b.created_at, amount=b.total,
            fields=[("Date", _date(b.event_date) + (f", {b.start_time:%I:%M %p}" if b.start_time else "")), ("Guests", str(b.guests)),
                    ("Address", ", ".join(x for x in [b.address.get("line1"), b.address.get("line2"), b.address.get("city")] if x)),
                    ("Services", ", ".join(b.services)), ("Payment", b.get_payment_status_display()), ("Team", b.team_note),
                    ("Next milestone", nxt.label if nxt else "")],
            actions=steps,
        )

    def action_required(self):
        if self._p() is None:
            raise WorkspaceUnavailable(self.connection()[1])
        return [self._enquiry_item(e) for e in self._enquiries()[:10]]

    def active(self):
        return [self._booking_item(b) for b in self._bookings().filter(status__in=ACTIVE).order_by("event_date")] if self._p() else []

    def metrics(self, day):
        if self._p() is None:
            return {}
        start, end = day_bounds(day)
        done = self._bookings().filter(status=S.COMPLETED)
        total = done.filter(completed_at__gte=start, completed_at__lt=end).aggregate(t=Sum("total"))["t"] or 0
        p = self._p()
        return {"requests": Metric("requests", "Quote requests", self._enquiries().count(), ""),
                "upcoming": Metric("upcoming", "Upcoming events", self._bookings().filter(status__in=ACTIVE).count(), ""),
                "earnings": Metric("earnings", "Completed today", float(total), money(total), "Value of events completed (payout rules not set yet)."),
                "rating": Metric("rating", "Rating", float(p.rating_average), f"{p.rating_average:.1f}" if p.rating_count else "—",
                                 f"{p.rating_count} reviews" if p.rating_count else "No reviews yet")}

    def earnings(self, start, end):
        done = self._bookings().filter(status=S.COMPLETED, completed_at__gte=start, completed_at__lt=end) if self._p() else EventBooking.objects.none()
        return (done.aggregate(t=Sum("total"))["t"] or 0), done.count()

    def earnings_note(self):
        return "Shows the value of completed events. Partner payout rates aren’t configured yet."

    def earnings_count_label(self):
        return "events"

    def activity(self, limit=8):
        if self._p() is None:
            return []
        return [{"id": str(b.id), "title": f"{b.get_status_display()} · {b.number}", "body": b.title, "at": b.updated_at.isoformat(),
                 "amount": money(b.total) if b.status == S.COMPLETED else None, "tone": "success" if b.status == S.COMPLETED else "active"}
                for b in self._bookings().order_by("-updated_at")[:limit]]

    def quick_actions(self):
        if self._p() is None:
            return {}
        return {"requests": QuickAction("requests", "Quote requests", "bell", "/work?view=requests", self._enquiries().count()),
                "active": QuickAction("active", "Bookings", "ticket", "/work?view=active", self._bookings().filter(status__in=ACTIVE).count()),
                "earnings": QuickAction("earnings", "Earnings", "wallet", "/earnings")}

    def context_line(self, action_items, active, is_available):
        if action_items:
            return f"{len(action_items)} quote request{'s' if len(action_items) != 1 else ''} waiting for you."
        if active:
            return f"Next: {active[0].title} · {active[0].subtitle}."
        return "Accepting requests. New event enquiries will appear here." if is_available else "Not accepting new enquiries right now."

    def views(self):
        if self._p() is None:
            return []
        return [{"key": "requests", "label": "Requests", "count": self._enquiries().count()},
                {"key": "active", "label": "Bookings", "count": self._bookings().filter(status__in=ACTIVE).count()},
                {"key": "history", "label": "History", "count": None}]

    def work(self, view, limit=50):
        if self._p() is None:
            return []
        if view == "requests":
            return self.action_required()
        if view == "active":
            return self.active()
        return [self._booking_item(b) for b in self._bookings().exclude(status__in=ACTIVE).order_by("-event_date")[:limit]]

    def perform(self, kind, item_id, action, payload, actor):
        p = self._p()
        if p is None:
            raise DomainError("Unknown work item.", code="unknown_item", status_code=404)
        if kind == "event_enquiry":
            e = get_object_or_404(Enquiry, pk=item_id, provider=p)
            text = str(payload.get("reason") or "")
            if action == "quote":
                amount, note = lifecycle.parse_amount(text)
                if amount is None:
                    raise DomainError("Enter the quote total, e.g. “45000 decoration and stage”.", code="validation_error",
                                      details={"reason": ["Enter an amount."]})
                lifecycle.provider_quote(e, p, {"items": [{"label": note or f"{e.plan.event_type.name} services", "amount": amount}]})
            elif action == "decline":
                lifecycle.provider_decline(e, p, text)
                return None
            else:
                raise DomainError("Unknown action.", code="unknown_action")
            return None  # answered: it leaves the requests list
        if kind == "event_booking":
            b = get_object_or_404(EventBooking, pk=item_id, provider=p)
            b = lifecycle.provider_step(b, p, action, payload)
            return self._booking_item(self._bookings().get(pk=b.pk))
        raise DomainError("Unknown work item.", code="unknown_item", status_code=404)
