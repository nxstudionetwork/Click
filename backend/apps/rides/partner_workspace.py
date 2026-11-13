"""Partner Home workspace for drivers: ride requests, the active trip, trips, earnings and performance (Click. Ride)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.core.api.exceptions import DomainError
from apps.partners.workspace.base import Action, Metric, Provider, QuickAction, WorkItem, day_bounds, money, pct

from . import services
from .matching import LOCATION_FRESH_FOR
from .models import Ride, RideDriverOffer, RideStatus

ACTIVE = [RideStatus.DRIVER_ASSIGNED, RideStatus.DRIVER_ARRIVED, RideStatus.IN_PROGRESS]
NEXT_STEP = {
    RideStatus.DRIVER_ASSIGNED: Action("arrived", "I’ve arrived at pickup", "primary"),
    RideStatus.DRIVER_ARRIVED: Action("start", "Start trip", "primary", confirm="Start the trip only once the rider is in your vehicle."),
    RideStatus.IN_PROGRESS: Action("complete", "Complete trip", "primary"),
}
STEP_STATUS = {"arrived": RideStatus.DRIVER_ARRIVED, "start": RideStatus.IN_PROGRESS, "complete": RideStatus.COMPLETED}


def _payment(ride: Ride) -> str:
    return f"Cash · collect ₹{ride.total:.0f}" if ride.payment_method == "cash" else "Paid with Click. Wallet"


def _rider(ride: Ride) -> str:
    if ride.passenger_name:
        return ride.passenger_name.split()[0]
    name = (ride.customer.user.full_name or "").strip()
    return name.split()[0] if name else "Rider"


def _place(label: str, address: str) -> str:
    return f"{label} · {address}" if address and address != label else label


class RidesProvider(Provider):
    kind = "rides"

    def _rides(self):
        return Ride.objects.filter(driver=self.partner).select_related("ride_type", "customer__user")

    # --- availability / location ---------------------------------------------------------------
    def can_go_unavailable(self) -> str:
        if self._rides().filter(status__in=ACTIVE).exists():
            return "Finish your current trip before going offline."
        return ""

    def on_availability_changed(self, is_available: bool) -> None:
        if not is_available:
            services.withdraw_offers(self.partner)

    def location_state(self):
        from .models import DriverLocation

        loc = DriverLocation.objects.filter(driver=self.partner).first()
        if loc is None:
            return {"reported_at": None, "fresh": False}
        return {"reported_at": loc.reported_at.isoformat(), "fresh": timezone.now() - loc.reported_at <= LOCATION_FRESH_FOR}

    # --- items -----------------------------------------------------------------------------------
    def _offer_item(self, offer: RideDriverOffer) -> WorkItem:
        r = offer.ride
        return WorkItem(
            kind="ride", id=str(r.id), ref=r.number, title=f"{r.pickup_label} → {r.drop_label}",
            subtitle=f"{r.ride_type.name} · {offer.distance_km:.1f} km to pickup",
            status="request", status_label="New ride request", tone="urgent", at=offer.created_at, amount=r.total,
            fields=[("Pickup", _place(r.pickup_label, r.pickup_address)), ("Drop", _place(r.drop_label, r.drop_address)),
                    ("Trip", f"{r.distance_km:.1f} km · about {r.duration_minutes} min"),
                    ("To pickup", f"{offer.distance_km:.1f} km away"), ("Payment", _payment(r))],
            actions=[Action("accept", "Accept", "primary"), Action("decline", "Decline", "secondary")],
        )

    def _trip_item(self, r: Ride) -> WorkItem:
        going_to_pickup = r.status in (RideStatus.DRIVER_ASSIGNED, RideStatus.DRIVER_ARRIVED)
        step = NEXT_STEP.get(r.status)
        actions = []
        if step:
            confirm = step.confirm
            if step.key == "complete":
                confirm = (f"Confirm you’ve dropped the rider and collected ₹{r.total:.0f} in cash." if r.payment_method == "cash"
                           else "Confirm you’ve dropped the rider at the destination.")
            actions.append(Action(step.key, step.label, "primary", confirm=confirm))
        tone = {"completed": "success", "cancelled": "muted", "no_driver": "muted"}.get(r.status, "active")
        return WorkItem(
            kind="ride", id=str(r.id), ref=r.number, title=f"{r.pickup_label} → {r.drop_label}",
            subtitle=f"{r.ride_type.name} · {_rider(r)}", status=r.status, status_label=r.get_status_display().replace(
                "Driver on the way", "Heading to pickup").replace("Driver has arrived", "Waiting for rider"),
            tone=tone, at=r.completed_at or r.started_at or r.driver_assigned_at or r.created_at, amount=r.total,
            fields=[("Rider", _rider(r)), ("Pickup", _place(r.pickup_label, r.pickup_address)),
                    ("Drop", _place(r.drop_label, r.drop_address)), ("Trip", f"{r.distance_km:.1f} km · about {r.duration_minutes} min"),
                    ("Payment", _payment(r))],
            actions=actions if r.status in ACTIVE else [],
            navigate=({"lat": float(r.pickup_lat), "lng": float(r.pickup_lng), "label": r.pickup_label} if going_to_pickup
                      else {"lat": float(r.drop_lat), "lng": float(r.drop_lng), "label": r.drop_label}) if r.status in ACTIVE else None,
        )

    def _pending_offers(self):
        return (RideDriverOffer.objects.filter(driver=self.partner, response="pending", ride__status=RideStatus.SEARCHING)
                .select_related("ride", "ride__ride_type").order_by("created_at"))

    # --- Home sections ---------------------------------------------------------------------------
    def action_required(self):
        return [self._offer_item(o) for o in self._pending_offers()[:10]]

    def active(self):
        return [self._trip_item(r) for r in self._rides().filter(status__in=ACTIVE).order_by("driver_assigned_at")]

    def _completed(self, start, end):
        return self._rides().filter(status=RideStatus.COMPLETED, completed_at__gte=start, completed_at__lt=end)

    def metrics(self, day):
        from apps.partners.workspace import online_seconds

        start, end = day_bounds(day)
        agg = self._completed(start, end).aggregate(n=Count("id"), total=Sum("total"), km=Sum("distance_km"))
        secs = online_seconds(self.partner, start, end)
        h, m = divmod(secs // 60, 60)
        return {
            "trips": Metric("trips", "Trips", agg["n"], str(agg["n"]), "Completed today"),
            "earnings": Metric("earnings", "Earnings", money(agg["total"]), f"₹{(agg['total'] or 0):,.0f}", "Gross fares"),
            "distance": Metric("distance", "Distance", float(agg["km"] or 0), f"{(agg['km'] or 0):.1f} km", "On completed trips"),
            "online_time": Metric("online_time", "Online time", secs, f"{h}h {m:02d}m" if h else f"{m}m", "From your online log"),
        }

    def earnings(self, start, end):
        agg = self._completed(start, end).aggregate(total=Sum("total"), n=Count("id"))
        return agg["total"] or Decimal("0"), agg["n"]

    def earnings_note(self):
        return "Gross fares from completed trips. Click commission and payouts aren’t set up yet, so nothing is deducted here."

    def earnings_count_label(self):
        return "trips completed"

    def earnings_recent(self, start, end, limit=20):
        return [{"ref": r.number, "title": f"{r.pickup_label} → {r.drop_label}", "amount": money(r.total),
                 "at": r.completed_at.isoformat(), "detail": "Cash" if r.payment_method == "cash" else "Click. Wallet"}
                for r in self._completed(start, end).order_by("-completed_at")[:limit]]

    def performance(self):
        since = timezone.now() - timedelta(days=30)
        rating = self.partner.ride_ratings.aggregate(avg=Avg("stars"), n=Count("id"))
        offers = self.partner.ride_offers.filter(created_at__gte=since).aggregate(
            accepted=Count("id", filter=Q(response="accepted")), declined=Count("id", filter=Q(response="declined")))
        trips = self._rides().filter(driver_assigned_at__gte=since).aggregate(
            done=Count("id", filter=Q(status=RideStatus.COMPLETED)), lost=Count("id", filter=Q(status=RideStatus.CANCELLED)))
        acc = pct(offers["accepted"], offers["accepted"] + offers["declined"])
        comp = pct(trips["done"], trips["done"] + trips["lost"])
        return {
            "rating": Metric("rating", "Rating", float(rating["avg"]) if rating["avg"] else None,
                             f"{rating['avg']:.1f}★" if rating["avg"] else "No ratings yet", f"{rating['n']} ratings"),
            "acceptance_rate": Metric("acceptance_rate", "Acceptance", acc, f"{acc}%" if acc is not None else "—",
                                      "Requests accepted, last 30 days"),
            "completion_rate": Metric("completion_rate", "Completion", comp, f"{comp}%" if comp is not None else "—",
                                      "Assigned trips completed, last 30 days"),
        }

    def activity(self, limit=8):
        return [{"id": str(r.id), "title": f"{r.get_status_display()} · {r.number}", "body": f"{r.pickup_label} → {r.drop_label}",
                 "at": r.updated_at.isoformat(), "amount": money(r.total) if r.status == RideStatus.COMPLETED else None,
                 "tone": "success" if r.status == RideStatus.COMPLETED else "muted" if r.status == RideStatus.CANCELLED else "active"}
                for r in self._rides().order_by("-updated_at")[:limit]]

    def quick_actions(self):
        n = self._pending_offers().count()
        active = self._rides().filter(status__in=ACTIVE).count()
        return {
            "requests": QuickAction("requests", "Requests", "bell", "/work?view=requests", n),
            "active": QuickAction("active", "Active trip", "ride", "/work?view=active", active),
            "trips": QuickAction("trips", "Trips", "history", "/work?view=trips"),
            "earnings": QuickAction("earnings", "Earnings", "wallet", "/earnings"),
        }

    def context_line(self, action_items, active, is_available):
        if active:
            return f"You’re on a trip to {active[0].title.split(' → ')[-1]}."
        if action_items:
            n = len(action_items)
            return f"{n} ride request{'s' if n != 1 else ''} waiting for you."
        return "You’re online. New ride requests near you will appear here." if is_available else \
            "You’re offline. Go online to start receiving ride requests."

    # --- Work page / actions ------------------------------------------------------------------------
    def views(self):
        return [{"key": "requests", "label": "Requests", "count": self._pending_offers().count()},
                {"key": "active", "label": "Active", "count": self._rides().filter(status__in=ACTIVE).count()},
                {"key": "trips", "label": "Trips", "count": None}]

    def work(self, view, limit=50):
        if view == "requests":
            return self.action_required()
        if view == "active":
            return self.active()
        return [self._trip_item(r) for r in self._rides().exclude(status__in=ACTIVE).order_by("-updated_at")[:limit]]

    def perform(self, kind, item_id, action, payload, actor):
        if kind != "ride":
            raise DomainError("Unknown work item.", code="unknown_item", status_code=404)
        if action == "accept":
            ride = services.driver_accept(get_object_or_404(Ride, pk=item_id), self.partner)
        elif action == "decline":
            ride = services.driver_decline(get_object_or_404(Ride, pk=item_id), self.partner)
            return None
        elif action in STEP_STATUS:
            ride = services.driver_step(get_object_or_404(Ride, pk=item_id), self.partner, STEP_STATUS[action])
        else:
            raise DomainError("Unknown action.", code="unknown_action")
        return self._trip_item(self._rides().get(pk=ride.pk))
