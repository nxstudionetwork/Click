"""
Partner Home: one common framework, category-specific content.

    Partner → category → resolved Home configuration (catalog.py) → workspace provider → real domain data

PROVIDERS maps a workspace key to the provider class that reads that domain. Adding a category is a catalogue
change; adding a new kind of work (parcels, stays, services) is one provider registered here.
"""

from __future__ import annotations

from datetime import timedelta
from importlib import import_module

from django.db import transaction
from django.utils import timezone

from apps.core.api.exceptions import ConflictError

from ..models import Partner, PartnerAvailabilityEvent
from .base import Provider, day_bounds, local_today, money, run_section

PROVIDERS: dict[str, str] = {
    "rides": "apps.rides.partner_workspace.RidesProvider",
    "orders": "apps.orders.partner_workspace.OrdersProvider",
    "venue": "apps.bookings.partner_workspace.VenueProvider",
    "parcels": "apps.parcels.partner_workspace.ParcelsProvider",
    "services": "apps.professionals.partner_workspace.ServicesProvider",
    "events": "apps.eventhub.partner_workspace.EventsProvider",
    "hotels": "apps.hotels.partner_workspace.HotelsProvider",
    "upcoming": "apps.partners.workspace.upcoming.UpcomingProvider",
}
CAN_OPERATE = {Partner.Status.VERIFIED, Partner.Status.ACTIVE}


def home_config(partner: Partner) -> dict:
    from ..services import configuration_for

    return configuration_for(partner.category)["home"]


def provider_for(partner: Partner) -> Provider:
    config = home_config(partner)
    path = PROVIDERS.get(config.get("workspace") or "upcoming", PROVIDERS["upcoming"])
    module, name = path.rsplit(".", 1)
    return getattr(import_module(module), name)(partner, config)


# --- availability ------------------------------------------------------------------------------------------------

def availability_state(partner: Partner, provider: Provider) -> dict:
    status = provider.config.get("status") or {}
    connection, message = provider.connection()
    blocked = ""
    if partner.status not in CAN_OPERATE:
        blocked = ("You can change this once Click verifies your account."
                   if partner.status in (Partner.Status.VERIFICATION_PENDING, Partner.Status.PROFILE_COMPLETED)
                   else "Your account can’t take work right now.")
    elif connection == "upcoming":
        service = (provider.config.get("upcoming") or {}).get("service") or "this service"
        blocked = f"You can switch to “{status.get('on', 'On')}” once {service} launches."
    elif connection == "not_connected":
        blocked = message
    is_on = bool(partner.is_available) and not blocked
    return {
        "is_on": is_on,
        "label": status.get("on" if is_on else "off", "On" if is_on else "Off"),
        "on_label": status.get("on", "On"), "off_label": status.get("off", "Off"),
        "turn_on": status.get("turn_on", "Turn on"), "turn_off": status.get("turn_off", "Turn off"),
        "hint": "" if blocked else status.get("on_hint" if is_on else "off_hint", ""),
        "can_change": not blocked,
        "blocked_reason": blocked,
        "confirm_off": status.get("confirm_off", ""),
        "since": _last_change(partner),
    }


def _last_change(partner: Partner):
    event = partner.availability_events.order_by("-created_at").first()
    return event.created_at.isoformat() if event else None


def set_availability(user, available: bool) -> Partner:
    from ..services import owned_partner, require_owned_partner

    with transaction.atomic():
        partner = require_owned_partner(user, for_update=True)
        provider = provider_for(partner)
        state = availability_state(partner, provider)
        if not state["can_change"]:
            raise ConflictError(state["blocked_reason"], code="availability_not_allowed")
        if not available and (reason := provider.can_go_unavailable()):
            raise ConflictError(reason, code="availability_not_allowed")
        if partner.is_available != available:
            partner.is_available = available
            partner.save(update_fields=["is_available", "updated_at"])
            PartnerAvailabilityEvent.objects.create(partner=partner, is_available=available, actor=user)
            provider.on_availability_changed(available)
    return owned_partner(user)


def online_seconds(partner: Partner, start, end) -> int:
    """Seconds the partner was switched on within [start, end), from the availability log only (never assumed)."""
    end = min(end, timezone.now())
    if end <= start:
        return 0
    before = partner.availability_events.filter(created_at__lt=start).order_by("-created_at").first()
    on_since = start if before and before.is_available else None
    total = 0.0
    for e in partner.availability_events.filter(created_at__gte=start, created_at__lt=end).order_by("created_at"):
        if e.is_available and on_since is None:
            on_since = e.created_at
        elif not e.is_available and on_since is not None:
            total += (e.created_at - on_since).total_seconds()
            on_since = None
    if on_since is not None:
        total += (end - on_since).total_seconds()
    return int(total)


# --- Home ------------------------------------------------------------------------------------------------------

def _greeting_name(partner: Partner) -> str:
    from ..services import configuration_for

    individual = configuration_for(partner.category)["identity"]["individual"]
    name = (getattr(partner.profile, "contact_name", "") or "").strip()
    if individual and name:
        return name.split()[0]
    return partner.business_name or "Partner"


def _off(message: str) -> dict:
    return {"status": "unavailable", "message": message}


def _items(section: dict) -> dict:
    if section["status"] != "ok":
        return section
    return {**section, "data": [i.as_dict() for i in section["data"]]}


def build_home(partner: Partner) -> dict:
    """Everything Partner Home renders, in one request. Each section succeeds or fails on its own."""
    from ..notifications import unread_count

    provider = provider_for(partner)
    config = provider.config
    connection, connection_message = provider.connection()
    live = connection == "live"
    today = local_today()
    start, end = day_bounds(today)
    week_start, _ = day_bounds(today - timedelta(days=today.weekday()))

    action = run_section("action_required", provider.action_required) if live else _off(connection_message)
    active = run_section("active", provider.active) if live else _off(connection_message)
    incoming = run_section("incoming", provider.incoming) if live else _off(connection_message)
    availability = availability_state(partner, provider)

    def metrics():
        values = provider.metrics(today)
        return [values[k].as_dict() for k in config.get("metrics", []) if k in values]

    def earnings():
        amount, count = provider.earnings(start, end)
        week, week_count = provider.earnings(week_start, end)
        return {"label": config.get("earnings_label", "Today’s earnings"), "today": money(amount), "today_count": count,
                "week": money(week), "week_count": week_count, "currency": "INR", "note": provider.earnings_note(),
                "count_label": provider.earnings_count_label()}

    def performance():
        values = provider.performance()
        return [values[k].as_dict() for k in config.get("performance", []) if k in values]

    def quick_actions():
        values = provider.quick_actions()
        return [values[k].as_dict() for k in config.get("quick_actions", []) if k in values]

    if connection == "upcoming":
        context = "Your Partner profile is ready."
    elif connection == "not_connected":
        context = "Your Partner profile is ready. One step left: Click connects your listing."
    elif action["status"] == "ok" and active["status"] == "ok":
        context = provider.context_line(action["data"], active["data"], availability["is_on"])
    else:
        context = ""

    quick = run_section("quick_actions", quick_actions) if live else {"status": "ok", "data": []}
    return {
        "generated_at": timezone.now().isoformat(),
        "workspace": {"kind": provider.kind, "state": connection, "message": connection_message,
                      "work_noun": config.get("work_noun", "work"), "location": config.get("location", "business"),
                      "live_location": provider.location_state() if live else None},
        "greeting_name": _greeting_name(partner),
        "context": context,
        "availability": availability,
        "action_required": _items(action),
        "active": _items(active),
        "incoming": _items(incoming),
        "metrics": run_section("metrics", metrics) if live else _off(connection_message),
        "earnings": run_section("earnings", earnings) if live else _off(connection_message),
        "performance": run_section("performance", performance) if live else _off(connection_message),
        "activity": run_section("activity", provider.activity) if live else _off(connection_message),
        "quick_actions": quick["data"] if quick["status"] == "ok" else [],
        "notifications": {"unread": unread_count(partner)},
    }


def build_work(partner: Partner, view: str) -> dict:
    provider = provider_for(partner)
    connection, message = provider.connection()
    if connection != "live":
        return {"state": connection, "message": message, "views": [], "view": "", "items": []}
    views = provider.views()
    keys = [v["key"] for v in views]
    view = view if view in keys else (keys[0] if keys else "")
    return {"state": connection, "message": "", "views": views, "view": view,
            "items": [i.as_dict() for i in provider.work(view)]}


def build_earnings(partner: Partner, days: int) -> dict:
    provider = provider_for(partner)
    config = provider.config
    label = (config.get("earnings_label") or "Earnings").replace("Today’s ", "")
    connection, message = provider.connection()
    if connection != "live":
        return {"state": connection, "message": message, "label": label.capitalize(), "currency": "INR",
                "total": "0.00", "count": 0, "days": [], "recent": [], "note": ""}
    today = local_today()
    series = []
    total = 0
    for offset in range(days - 1, -1, -1):
        d = today - timedelta(days=offset)
        s, e = day_bounds(d)
        amount, count = provider.earnings(s, e)
        total += amount
        series.append({"date": d.isoformat(), "amount": money(amount), "count": count})
    range_start, _ = day_bounds(today - timedelta(days=days - 1))
    _, range_end = day_bounds(today)
    return {
        "state": "live", "message": "", "label": label.capitalize(), "currency": "INR", "total": money(total),
        "count": sum(x["count"] for x in series), "count_label": provider.earnings_count_label(), "days": series,
        "recent": provider.earnings_recent(range_start, range_end), "note": provider.earnings_note(),
    }


def perform(partner: Partner, kind: str, item_id: str, action: str, payload: dict, actor) -> dict:
    provider = provider_for(partner)
    if provider.connection()[0] != "live":
        raise ConflictError("Your workspace isn’t live yet.", code="workspace_not_live")
    item = provider.perform(kind, item_id, action, payload or {}, actor)
    return {"ok": True, "item": item.as_dict() if item else None}
