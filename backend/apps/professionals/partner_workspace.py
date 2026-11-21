"""Partner Home workspace for service professionals (Click. Services): job requests, active jobs, history, earnings."""

from __future__ import annotations

from django.db.models import Sum
from django.shortcuts import get_object_or_404

from apps.core.api.exceptions import DomainError
from apps.partners.workspace.base import Action, Metric, Provider, QuickAction, WorkItem, WorkspaceUnavailable, day_bounds, money

from . import engine, lifecycle
from .models import BookingStatus as S, ProviderProfile, ServiceBooking, ServiceJobOffer

WORKING = [S.CONFIRMED, S.ON_THE_WAY, S.ARRIVED, S.QUOTE_PENDING, S.IN_PROGRESS, S.COMPLETED]


def _when(b: ServiceBooking) -> str:
    if b.mode == "now":
        return "As soon as possible"
    t = engine.local(b.scheduled_start)
    return t.strftime("%a %d %b, %I:%M %p").replace(" 0", " ")


def _price(b: ServiceBooking) -> str:
    if b.total is not None:
        return f"₹{b.total:,.2f} total"
    if b.agreed_amount is not None:
        return f"{engine.price_label(b.pricing, b.unit_price)} · agreed ₹{b.agreed_amount:,.0f}"
    return "Quote after inspection" + (f" · inspection fee ₹{b.inspection_fee:,.0f} if declined" if b.inspection_fee else "")


class ServicesProvider(Provider):
    kind = "services"

    def _pro(self) -> ProviderProfile | None:
        if not hasattr(self, "_p"):
            self._p = ProviderProfile.objects.filter(partner=self.partner).select_related("category").first()
        return self._p

    def connection(self):
        if self._pro() is None:
            return "not_connected", ("Your Click. Services profile isn’t set up yet. Once Click verifies you and sets up your "
                                     "profile and services, job requests will appear here.")
        return "live", ""

    def _jobs(self):
        return ServiceBooking.objects.filter(provider=self._pro()).select_related("job", "category", "customer__user")

    def can_go_unavailable(self) -> str:
        return "Finish your current job first." if self._pro() and self._jobs().filter(status__in=engine.ON_JOB).exists() else ""

    def on_availability_changed(self, is_available: bool) -> None:
        if not is_available and self._pro():
            ServiceJobOffer.objects.filter(provider=self._pro(), response="pending", booking__mode="now").update(response="expired")

    def _offers(self):
        lifecycle.expire_due()
        return (ServiceJobOffer.objects.filter(provider=self._pro(), response="pending", booking__status=S.REQUESTED)
                .select_related("booking__job", "booking__category").order_by("created_at"))

    def _customer(self, b: ServiceBooking) -> str:
        n = (b.customer.user.full_name or "").strip()
        return n.split()[0] if n else "Customer"

    def _offer_item(self, o: ServiceJobOffer) -> WorkItem:
        b = o.booking
        return WorkItem(
            kind="service", id=str(b.id), ref=b.number, title=f"{b.job.name}", status="request", status_label="New job request", tone="urgent",
            subtitle=f"{_when(b)}{f' · {o.distance_km:.1f} km away' if o.distance_km is not None else ''}", at=o.created_at, amount=b.agreed_amount,
            fields=[("When", _when(b)), ("Area", b.address.get("line2") or b.address.get("city", "")), ("Work", b.description or b.job.name),
                    ("Price", _price(b)), ("Photos", f"{b.attachments.count()} attached" if b.attachments.exists() else "None")],
            actions=[Action("accept", "Accept", "primary"), Action("decline", "Decline", "secondary")],
        )

    def _job_item(self, b: ServiceBooking) -> WorkItem:
        steps = {
            S.CONFIRMED: [Action("on_the_way", "I’m on my way", "primary")],
            S.ON_THE_WAY: [Action("arrived", "I’ve arrived", "primary")],
            S.ARRIVED: ([Action("quote", "Send quote", "primary", needs_reason=True, confirm="Type the total amount and what it covers, e.g. “1450 replace tap and pipe”. Work starts only after the customer approves.")]
                        if b.pricing == "quote" and b.agreed_amount is None else
                        [Action("start", "Start work", "primary"), Action("quote", "Quote extra work", "secondary", needs_reason=True,
                                                                         confirm="Type the new total and why. The customer must approve it.")]),
            S.QUOTE_PENDING: [],
            S.IN_PROGRESS: [Action("complete", "Mark work complete", "primary", needs_reason=b.pricing == "hourly",
                                   confirm="Enter the hours worked." if b.pricing == "hourly" else "Confirm the job is done."),
                            Action("quote", "Quote extra work", "secondary", needs_reason=True, confirm="Type the new total and why. The customer must approve it.")],
            S.COMPLETED: [Action("cash_received", "Cash received", "secondary", confirm=f"Confirm you received ₹{b.total or 0:,.2f} in cash.")]
                        if b.payment_method == "cash" else [],
        }.get(b.status, [])
        tone = {"paid": "success", "cancelled": "muted", "unassigned": "muted", "completed": "info", "quote_pending": "info"}.get(b.status, "active")
        on_way = b.status in (S.CONFIRMED, S.ON_THE_WAY)
        return WorkItem(
            kind="service", id=str(b.id), ref=b.number, title=b.job.name, subtitle=f"{_when(b)} · {self._customer(b)}", status=b.status,
            status_label=b.get_status_display(), tone=tone, at=b.completed_at or b.started_at or b.accepted_at or b.created_at,
            amount=b.total or b.agreed_amount,
            fields=[("Customer", self._customer(b)), ("Address", ", ".join(x for x in [b.address.get("line1"), b.address.get("line2"), b.address.get("city")] if x)),
                    ("Work", b.description or b.job.name), ("Price", _price(b)),
                    *([("Quote", f"₹{q.amount:,.0f} · {q.get_status_display().lower()}")] if (q := b.quotes.first()) else [])],
            actions=steps, navigate={"lat": float(b.lat), "lng": float(b.lng), "label": b.address.get("line1", "")} if on_way else None,
        )

    def action_required(self):
        if self._pro() is None:
            raise WorkspaceUnavailable(self.connection()[1])
        return [self._offer_item(o) for o in self._offers()[:10]]

    def active(self):
        return [self._job_item(b) for b in self._jobs().filter(status__in=WORKING).order_by("scheduled_start", "accepted_at")] if self._pro() else []

    def metrics(self, day):
        if self._pro() is None:
            return {}
        start, end = day_bounds(day)
        paid = self._jobs().filter(status=S.PAID, paid_at__gte=start, paid_at__lt=end)
        total = paid.aggregate(t=Sum("total"))["t"] or 0
        p = self._pro()
        return {"jobs": Metric("jobs", "Jobs today", self._jobs().filter(accepted_at__gte=start, accepted_at__lt=end).count(), ""),
                "completed": Metric("completed", "Completed", paid.count(), ""),
                "earnings": Metric("earnings", "Job value", float(total), money(total), "Paid jobs (payout rules not set yet)."),
                "rating": Metric("rating", "Rating", float(p.rating_average), f"{p.rating_average:.1f}" if p.rating_count else "—",
                                 f"{p.rating_count} reviews" if p.rating_count else "No reviews yet")}

    def earnings(self, start, end):
        paid = self._jobs().filter(status=S.PAID, paid_at__gte=start, paid_at__lt=end) if self._pro() else ServiceBooking.objects.none()
        return (paid.aggregate(t=Sum("total"))["t"] or 0), paid.count()

    def earnings_note(self):
        return "Shows the value of paid jobs. Partner payout rates aren’t configured yet."

    def earnings_count_label(self):
        return "jobs"

    def activity(self, limit=8):
        if self._pro() is None:
            return []
        return [{"id": str(b.id), "title": f"{b.get_status_display()} · {b.number}", "body": b.job.name, "at": b.updated_at.isoformat(),
                 "amount": money(b.total) if b.status == S.PAID and b.total else None, "tone": "success" if b.status == S.PAID else "active"}
                for b in self._jobs().order_by("-updated_at")[:limit]]

    def quick_actions(self):
        if self._pro() is None:
            return {}
        return {"requests": QuickAction("requests", "Requests", "bell", "/work?view=requests", self._offers().count()),
                "active": QuickAction("active", "Jobs", "wrench", "/work?view=active", self._jobs().filter(status__in=WORKING).count()),
                "earnings": QuickAction("earnings", "Earnings", "wallet", "/earnings")}

    def context_line(self, action_items, active, is_available):
        if active:
            return f"Next: {active[0].title} · {active[0].status_label.lower()}."
        if action_items:
            return f"{len(action_items)} job request{'s' if len(action_items) != 1 else ''} waiting for you."
        return "You’re available. New job requests near you will appear here." if is_available else "You’re unavailable. Go available to get job requests."

    def views(self):
        if self._pro() is None:
            return []
        return [{"key": "requests", "label": "Requests", "count": self._offers().count()},
                {"key": "active", "label": "Jobs", "count": self._jobs().filter(status__in=WORKING).count()},
                {"key": "history", "label": "History", "count": None}]

    def work(self, view, limit=50):
        if self._pro() is None:
            return []
        if view == "requests":
            return self.action_required()
        if view == "active":
            return self.active()
        return [self._job_item(b) for b in self._jobs().exclude(status__in=WORKING).order_by("-updated_at")[:limit]]

    def perform(self, kind, item_id, action, payload, actor):
        if kind != "service" or self._pro() is None:
            raise DomainError("Unknown work item.", code="unknown_item", status_code=404)
        b = get_object_or_404(ServiceBooking, pk=item_id)
        if action == "accept":
            b = lifecycle.accept(b, self._pro())
        elif action == "decline":
            lifecycle.decline(b, self._pro())
            return None
        else:
            b = lifecycle.step(b, self._pro(), action, payload)
        return self._job_item(self._jobs().get(pk=b.pk))

