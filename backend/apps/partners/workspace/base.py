"""
The contract every Partner Home workspace implements.

A workspace turns one Click domain (rides, store orders, venue bookings, …) into the partner's operational view:
the work that needs action now, active work, incoming requests, today's numbers, earnings, performance, recent
activity and the actions the partner may take. Providers read the domain's own tables; nothing here keeps a copy,
so the Customer App, Partner App and Business OS always see the same state.

Every method receives the partner resolved from the signed-in user (never from client input) and must only return
that partner's records.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Callable
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from apps.core.api.exceptions import DomainError

log = logging.getLogger("click.partner_home")

# Partners work in local business days. The platform runs in UTC; "today" for a partner is their business day.
BUSINESS_TZ = ZoneInfo(getattr(settings, "CLICK_BUSINESS_TIME_ZONE", "Asia/Kolkata"))


def local_today(now: datetime | None = None) -> date:
    return timezone.localtime(now or timezone.now(), BUSINESS_TZ).date()


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=BUSINESS_TZ)
    return start, start + timedelta(days=1)


def money(value: Decimal | int | float | None) -> str:
    return f"{Decimal(value or 0):.2f}"


def pct(numerator: int, denominator: int) -> int | None:
    return round(numerator * 100 / denominator) if denominator else None


@dataclass
class Action:
    """Something the partner can do to a work item. The server re-checks every action when it is performed."""

    key: str
    label: str
    style: str = "secondary"  # primary | secondary | danger
    confirm: str = ""  # confirmation text for consequential actions (shown before the request is sent)
    needs_reason: bool = False

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "style": self.style, "confirm": self.confirm, "needs_reason": self.needs_reason}


@dataclass
class WorkItem:
    """One unit of work, in a shape every Home module and the Work page render the same way."""

    kind: str
    id: str
    ref: str
    title: str
    status: str
    status_label: str
    tone: str = "info"  # urgent | active | info | success | muted (always paired with status text)
    subtitle: str = ""
    at: datetime | None = None
    amount: Decimal | None = None
    currency: str = "INR"
    fields: list[tuple[str, str]] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    navigate: dict | None = None  # {"lat", "lng", "label"} for drivers
    link: str = ""

    def as_dict(self) -> dict:
        return {
            "kind": self.kind, "id": self.id, "ref": self.ref, "title": self.title, "subtitle": self.subtitle,
            "status": self.status, "status_label": self.status_label, "tone": self.tone,
            "at": self.at.isoformat() if self.at else None,
            "amount": money(self.amount) if self.amount is not None else None, "currency": self.currency,
            "fields": [{"label": k, "value": v} for k, v in self.fields if v not in (None, "")],
            "actions": [a.as_dict() for a in self.actions], "navigate": self.navigate, "link": self.link,
        }


@dataclass
class Metric:
    key: str
    label: str
    value: Any
    display: str
    hint: str = ""

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "value": self.value, "display": self.display, "hint": self.hint}


@dataclass
class QuickAction:
    key: str
    label: str
    icon: str
    to: str
    count: int | None = None

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "icon": self.icon, "to": self.to, "count": self.count}


class WorkspaceUnavailable(Exception):
    """Raised by a provider when the partner isn't connected yet (e.g. no storefront linked); the message is user-safe."""


class Provider:
    """Base workspace. Subclasses override what their domain supports; defaults are honest empty answers."""

    kind = "base"

    def __init__(self, partner, home_config: dict):
        self.partner = partner
        self.config = home_config

    # --- connection --------------------------------------------------------------------------
    def connection(self) -> tuple[str, str]:
        """("live" | "not_connected" | "upcoming", user-facing message)."""
        return "live", ""

    def location_state(self) -> dict | None:
        """For live-location workspaces: {"reported_at", "fresh"} of the last position the app reported."""
        return None

    # --- availability ------------------------------------------------------------------------
    def can_go_unavailable(self) -> str:
        """Empty when the partner may switch off now, otherwise the reason (e.g. an active trip)."""
        return ""

    def on_availability_changed(self, is_available: bool) -> None:
        """Apply the toggle to the customer-facing records (e.g. a store stops accepting orders)."""

    # --- Home sections -----------------------------------------------------------------------
    def action_required(self) -> list[WorkItem]:
        return []

    def active(self) -> list[WorkItem]:
        return []

    def incoming(self) -> list[WorkItem]:
        return []

    def metrics(self, day: date) -> dict[str, Metric]:
        return {}

    def earnings(self, start: datetime, end: datetime) -> tuple[Decimal, int]:
        """(amount, count) for completed work in [start, end)."""
        return Decimal("0"), 0

    def earnings_note(self) -> str:
        return ""

    def earnings_count_label(self) -> str:
        """What the earnings count counts, e.g. "trips completed" or "orders"."""
        return "completed"

    def performance(self) -> dict[str, Metric]:
        return {}

    def activity(self, limit: int = 8) -> list[dict]:
        return []

    def quick_actions(self) -> dict[str, QuickAction]:
        return {}

    def context_line(self, action_items: list[WorkItem], active: list[WorkItem], is_available: bool) -> str:
        return ""

    # --- Work page and actions ---------------------------------------------------------------
    def views(self) -> list[dict]:
        """[{key, label, count}] for the Work page tabs."""
        return []

    def work(self, view: str, limit: int = 50) -> list[WorkItem]:
        return []

    def perform(self, kind: str, item_id: str, action: str, payload: dict, actor) -> WorkItem | None:
        raise DomainError("This action isn't available for your account.", code="action_not_supported", status_code=400)

    def earnings_recent(self, start: datetime, end: datetime, limit: int = 20) -> list[dict]:
        return []


def run_section(name: str, fn: Callable[[], Any]) -> dict:
    """Each Home section fails on its own: one broken module never hides the rest of the dashboard."""
    try:
        return {"status": "ok", "data": fn()}
    except WorkspaceUnavailable as exc:
        return {"status": "unavailable", "message": str(exc)}
    except Exception:  # noqa: BLE001 - logged with traceback; the client gets a safe message
        log.exception("partner_home.section_failed", extra={"section": name})
        return {"status": "error", "message": "This section couldn’t load. Try again in a moment."}
