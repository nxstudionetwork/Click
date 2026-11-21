"""Writes the account security log (SignInEvent). Recording never blocks or breaks sign-in."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_BROWSERS = [("Edg/", "Edge"), ("OPR/", "Opera"), ("SamsungBrowser", "Samsung Internet"), ("Chrome/", "Chrome"),
             ("CriOS", "Chrome"), ("Firefox/", "Firefox"), ("FxiOS", "Firefox"), ("Safari/", "Safari")]
_SYSTEMS = [("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"), ("Windows", "Windows"), ("Mac OS X", "Mac"),
            ("CrOS", "ChromeOS"), ("Linux", "Linux")]


def describe_device(user_agent: str) -> str:
    ua = user_agent or ""
    if re.search(r"okhttp|Dart|CFNetwork|ClickApp", ua):
        return "Click app"
    browser = next((name for key, name in _BROWSERS if key in ua), "")
    system = next((name for key, name in _SYSTEMS if key in ua), "")
    if browser and system:
        return f"{browser} on {system}"
    return browser or system or "Unknown device"


def client_ip(request) -> str | None:
    return request.META.get("REMOTE_ADDR") or None


def record(request, event: str, *, user=None, phone: str = "", method: str = "phone_otp") -> None:
    from .models import SignInEvent

    try:
        ua = (request.META.get("HTTP_USER_AGENT") or "")[:255]
        SignInEvent.objects.create(user=user, event=event, method=method, phone=(phone or getattr(user, "phone", "") or "")[:16],
                                   app=(request.headers.get("X-Click-Client") or "")[:16], ip=client_ip(request),
                                   device=describe_device(ua)[:80], user_agent=ua)
    except Exception:  # noqa: BLE001 — the security log must never break sign-in
        logger.exception("could not record sign-in event %s", event)


def recent_for(user, limit: int = 10) -> list[dict]:
    from .models import SignInEvent

    rows = SignInEvent.objects.filter(user=user, event__in=["signed_in", "signed_up", "signed_out_others"]).order_by("-created_at")[:limit]
    return [{"id": str(e.id), "event": e.event, "label": e.get_event_display(), "device": e.device or "Unknown device",
             "app": e.app, "method": e.method, "at": e.created_at.isoformat()} for e in rows]
