"""
One notification service for the whole Business OS.

    notify(user, "approval_request", "Expense ₹12,000 needs your approval", link="/approvals/<id>", module="finance")

In-app delivery always happens (the inbox is the record). Other channels are pluggable: list dotted paths in
CLICK_OS_NOTIFICATION_CHANNELS (e.g. "apps.workspace.notify.EmailChannel"); with none configured nothing else is
attempted. A channel failing never blocks the in-app notification. Recipients' mutes are respected except for
essential types (security, approval requests).
"""

import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils.module_loading import import_string

from .models import WorkNotification

logger = logging.getLogger(__name__)


class Channel:
    key = "base"

    def send(self, notification: WorkNotification) -> bool:  # pragma: no cover - interface
        raise NotImplementedError


class EmailChannel(Channel):
    """Uses Django's configured email backend (EMAIL_HOST …). Only for recipients with an email address."""

    key = "email"

    def send(self, n):
        from django.core.mail import send_mail

        email = n.recipient.email
        if not email:
            return False
        send_mail(f"[Click Business OS] {n.title}", f"{n.body}\n\n{n.link_path}", None, [email], fail_silently=False)
        return True


def _channels() -> list[Channel]:
    out = []
    for path in getattr(settings, "CLICK_OS_NOTIFICATION_CHANNELS", []):
        try:
            out.append(import_string(path)())
        except ImportError:
            logger.error("notify.channel_missing", extra={"channel": path})
    return out


def _muted(user, type_: str) -> bool:
    if type_ in WorkNotification.ESSENTIAL:
        return False
    acct = getattr(user, "os_account", None)
    prefs = (acct.preferences or {}).get("notifications", {}) if acct else {}
    return type_ in prefs.get("muted", [])


def notify(user, type_: str, title: str, *, body: str = "", link: str = "", module: str = "", priority: str = "normal",
           dedupe_key: str = "") -> WorkNotification | None:
    if user is None or _muted(user, type_):
        return None
    try:
        with transaction.atomic():
            n = WorkNotification.objects.create(recipient=user, type=type_, title=title[:160], body=body[:500], link_path=link[:200],
                                                module=module, priority=priority, channels=["in_app"], dedupe_key=dedupe_key[:120])
    except IntegrityError:  # same dedupe key already delivered
        return None
    delivered = ["in_app"]
    for ch in _channels():
        try:
            if ch.send(n):
                delivered.append(ch.key)
        except Exception:
            logger.exception("notify.channel_failed", extra={"channel": ch.key})
    if len(delivered) > 1:
        WorkNotification.objects.filter(pk=n.pk).update(channels=delivered)
    return n


def notify_many(users, type_: str, title: str, **kw) -> int:
    return sum(1 for u in users if notify(u, type_, title, **kw))
