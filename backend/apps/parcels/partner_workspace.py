"""Partner Home workspace for delivery partners (Parcel & Logistics partners, Delivery Riders): Click. Parcel jobs."""

from __future__ import annotations

from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.core.api.exceptions import DomainError
from apps.partners.workspace.base import Action, Metric, Provider, QuickAction, WorkItem, day_bounds, money

from . import matching, services
from .models import ParcelJobOffer, ParcelOrder, ParcelStatus as S

ACTIVE = [S.ASSIGNED, S.AT_PICKUP, S.PICKED_UP, S.IN_TRANSIT, S.ARRIVING]


def _route(p: ParcelOrder) -> str:
    return f"{p.pickup_label} → {p.drop_label}"


def _payment(p: ParcelOrder) -> str:
    return f"Cash · collect ₹{p.total:.0f} at pickup" if p.payment_method == "cash" else "Prepaid (Click Wallet)"


def _package(p: ParcelOrder) -> str:
    return f"{p.category.label} · {p.get_size_display()} · {p.weight_kg:.1f} kg"


class ParcelsProvider(Provider):
    kind = "parcels"

    def _jobs(self):
        return ParcelOrder.objects.filter(partner=self.partner).select_related("service", "vehicle", "category").prefetch_related("stops")

    def can_go_unavailable(self) -> str:
        return "Finish your current delivery first." if self._jobs().filter(status__in=ACTIVE).exists() else ""

    def on_availability_changed(self, is_available: bool) -> None:
        if is_available:
            matching.refresh_for(self.partner)
        else:
            ParcelJobOffer.objects.filter(partner=self.partner, response="pending").update(response="expired")

    def location_state(self):
        from apps.rides.matching import LOCATION_FRESH_FOR
        from apps.rides.models import DriverLocation

        loc = DriverLocation.objects.filter(driver=self.partner).first()
        if loc is None:
            return {"reported_at": None, "fresh": False}
        return {"reported_at": loc.reported_at.isoformat(), "fresh": timezone.now() - loc.reported_at <= LOCATION_FRESH_FOR}

    def _offers(self):
        matching.refresh_for(self.partner)
        return (ParcelJobOffer.objects.filter(partner=self.partner, response="pending", parcel__status=S.SEARCHING)
                .select_related("parcel", "parcel__service", "parcel__vehicle", "parcel__category").order_by("created_at"))

    def _offer_item(self, o: ParcelJobOffer) -> WorkItem:
        p = o.parcel
        return WorkItem(
            kind="parcel", id=str(p.id), ref=p.number, title=_route(p), subtitle=f"{p.service.name} · {o.distance_km:.1f} km to pickup",
            status="request", status_label="New delivery request", tone="urgent", at=o.created_at, amount=p.total,
            fields=[("Pickup", p.pickup_label), ("Drop", p.drop_label), ("Package", _package(p)),
                    ("Trip", f"{p.distance_km:.1f} km{f' · {p.stops.count()} stops' if p.stops.exists() else ''}"), ("Payment", _payment(p))],
            actions=[Action("accept", "Accept", "primary"), Action("decline", "Decline", "secondary")],
        )

    def _job_item(self, p: ParcelOrder) -> WorkItem:
        step = {
            S.ASSIGNED: Action("arrived", "I’ve reached pickup", "primary"),
            S.AT_PICKUP: Action("pickup", "Confirm pickup with PIN", "primary", needs_reason=True,
                                confirm=(f"Enter the sender’s 4-digit pickup PIN in the box. Collect ₹{p.total:.0f} in cash first."
                                         if p.payment_method == "cash" else "Enter the sender’s 4-digit pickup PIN in the box.")),
            S.IN_TRANSIT: (Action("stop", "Complete next stop", "primary") if p.stops.filter(completed_at__isnull=True).exists()
                           else Action("near", "I’m near the drop", "primary")),
            S.ARRIVING: Action("deliver", "Confirm delivery with PIN", "primary", needs_reason=True,
                               confirm="Enter the recipient’s 4-digit delivery PIN in the box."),
        }.get(p.status)
        actions = [step] if step else []
        if p.status == S.IN_TRANSIT and not p.stops.filter(completed_at__isnull=True).exists():
            actions.append(Action("deliver", "Deliver with PIN", "secondary", needs_reason=True, confirm="Enter the recipient’s delivery PIN."))
        if p.status in (S.AT_PICKUP, S.IN_TRANSIT, S.ARRIVING):
            actions.append(Action("fail", "Report a problem", "danger", needs_reason=True,
                                  confirm="This ends the delivery as failed and tells the customer why."))
        tone = {"delivered": "success", "cancelled": "muted", "failed": "muted"}.get(p.status, "active")
        going_to_pickup = p.status in (S.ASSIGNED, S.AT_PICKUP)
        return WorkItem(
            kind="parcel", id=str(p.id), ref=p.number, title=_route(p), subtitle=f"{p.service.name} · {p.vehicle.name}",
            status=p.status, status_label=p.get_status_display(), tone=tone,
            at=p.delivered_at or p.picked_up_at or p.assigned_at or p.created_at, amount=p.total,
            fields=[("Pickup", f"{p.pickup_label} · {p.pickup_name} · {p.pickup_phone}"),
                    ("Drop", f"{p.drop_label} · {p.drop_name} · {p.drop_phone}"),
                    *[(f"Stop {s.position}", f"{s.label}{' · done' if s.completed_at else ''}") for s in p.stops.all()],
                    ("Package", _package(p)), ("Payment", _payment(p))],
            actions=actions if p.status in ACTIVE else [],
            navigate=({"lat": float(p.pickup_lat), "lng": float(p.pickup_lng), "label": p.pickup_label} if going_to_pickup
                      else {"lat": float(p.drop_lat), "lng": float(p.drop_lng), "label": p.drop_label}) if p.status in ACTIVE else None,
        )

    def action_required(self):
        return [self._offer_item(o) for o in self._offers()[:10]]

    def active(self):
        return [self._job_item(p) for p in self._jobs().filter(status__in=ACTIVE).order_by("assigned_at")]

    def metrics(self, day):
        start, end = day_bounds(day)
        done = self._jobs().filter(status=S.DELIVERED, delivered_at__gte=start, delivered_at__lt=end)
        total = done.aggregate(t=Sum("total"))["t"] or 0
        return {
            "deliveries": Metric("deliveries", "Deliveries", self._jobs().filter(assigned_at__gte=start, assigned_at__lt=end).count(), ""),
            "completed": Metric("completed", "Completed", done.count(), ""),
            "earnings": Metric("earnings", "Delivery value", float(total), money(total), "Total of delivered jobs (payout rules not set yet)."),
            "pending": Metric("pending", "Active", self._jobs().filter(status__in=ACTIVE).count(), ""),
        }

    def earnings(self, start, end):
        done = self._jobs().filter(status=S.DELIVERED, delivered_at__gte=start, delivered_at__lt=end)
        return (done.aggregate(t=Sum("total"))["t"] or 0), done.count()

    def earnings_note(self):
        return "Shows the value of delivered jobs. Partner payout rates aren’t configured yet."

    def earnings_count_label(self):
        return "deliveries"

    def activity(self, limit=8):
        return [{"id": str(p.id), "title": f"{p.get_status_display()} · {p.number}", "body": _route(p), "at": p.updated_at.isoformat(),
                 "amount": money(p.total) if p.status == S.DELIVERED else None,
                 "tone": "success" if p.status == S.DELIVERED else "active"} for p in self._jobs().order_by("-updated_at")[:limit]]

    def quick_actions(self):
        return {"requests": QuickAction("requests", "Requests", "bell", "/work?view=requests", self._offers().count()),
                "active": QuickAction("active", "Active", "parcel", "/work?view=active", self._jobs().filter(status__in=ACTIVE).count()),
                "earnings": QuickAction("earnings", "Earnings", "wallet", "/earnings")}

    def context_line(self, action_items, active, is_available):
        if active:
            return f"Delivering {active[0].ref}: {active[0].status_label.lower()}."
        if action_items:
            return f"{len(action_items)} delivery request{'s' if len(action_items) != 1 else ''} near you."
        return ("You’re available. Delivery requests near you will appear here." if is_available
                else "You’re unavailable. Go available to receive delivery requests.")

    def views(self):
        return [{"key": "requests", "label": "Requests", "count": self._offers().count()},
                {"key": "active", "label": "Active", "count": self._jobs().filter(status__in=ACTIVE).count()},
                {"key": "history", "label": "History", "count": None}]

    def work(self, view, limit=50):
        if view == "requests":
            return self.action_required()
        if view == "active":
            return self.active()
        return [self._job_item(p) for p in self._jobs().exclude(status__in=ACTIVE).order_by("-updated_at")[:limit]]

    def perform(self, kind, item_id, action, payload, actor):
        if kind != "parcel":
            raise DomainError("Unknown work item.", code="unknown_item", status_code=404)
        parcel = get_object_or_404(ParcelOrder, pk=item_id)
        if action == "accept":
            parcel = services.partner_accept(parcel, self.partner)
        elif action == "decline":
            services.partner_decline(parcel, self.partner)
            return None
        else:
            # The PIN arrives in the action's text box (`reason`) or as `code`.
            data = {**payload, "code": payload.get("code") or payload.get("reason")}
            parcel = services.partner_step(parcel, self.partner, action, data)
        return self._job_item(self._jobs().get(pk=parcel.pk))

