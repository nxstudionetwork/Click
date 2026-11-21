"""
    from apps.audit.services import record
    record(request, "finance.invoice.update", category="financial", resource=invoice, old=before, new=after)

Only changed keys are stored for old/new; secrets are masked; recording never breaks the business action.
"""

import logging
from decimal import Decimal
from uuid import UUID

from django.db import transaction

from .models import AuditEvent

logger = logging.getLogger("click.audit")

MASK_KEYS = ("password", "secret", "token", "otp", "code_hash", "recovery", "mfa_secret", "key_hash")


def _clean(value):
    if isinstance(value, dict):
        return {k: ("•••" if any(m in k.lower() for m in MASK_KEYS) else _clean(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def diff(old: dict | None, new: dict | None) -> tuple[dict | None, dict | None]:
    if old is None or new is None:
        return (_clean(old), _clean(new))
    keys = {k for k in set(old) | set(new) if old.get(k) != new.get(k)}
    return _clean({k: old.get(k) for k in keys}), _clean({k: new.get(k) for k in keys})


def client_ip(request) -> str | None:
    if request is None:
        return None
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR")) or None


def record(request, action: str, *, category: str, actor=None, organization=None, module: str = "", resource=None,
           resource_type: str = "", resource_id: str = "", resource_label: str = "", old=None, new=None,
           org_unit=None, sensitive: bool = False, outcome: str = "success", metadata: dict | None = None) -> AuditEvent | None:
    try:
        user = actor if actor is not None else getattr(request, "user", None)
        user = user if (user is not None and getattr(user, "is_authenticated", False)) else None
        service = getattr(request, "os_service_account", None)
        if organization is None and user is not None:
            acct = getattr(user, "os_account", None)
            organization = acct.organization if acct else (service.organization if service else None)
        if resource is not None:
            resource_type = resource_type or resource._meta.label_lower
            resource_id = resource_id or str(resource.pk)
            resource_label = resource_label or str(resource)[:200]
        old_v, new_v = diff(old, new)
        session = getattr(request, "os_session", None)
        with transaction.atomic():  # savepoint: a failed audit insert can't poison the caller's transaction
            event = AuditEvent.objects.create(
                organization=organization, actor=user,
                actor_label=(user.full_name or user.email or user.phone or str(user.pk))[:200] if user else "",
                actor_kind="service" if service else ("user" if user else "anonymous"),
                action=action, category=category, module=module or action.split(".")[0],
                resource_type=resource_type, resource_id=str(resource_id), resource_label=resource_label[:200],
                old_value=old_v, new_value=new_v, org_unit=org_unit, sensitive=sensitive, outcome=outcome,
                ip=client_ip(request), user_agent=(request.META.get("HTTP_USER_AGENT", "")[:300] if request is not None else ""),
                session_id=session.pk if session else None, metadata=_clean(metadata or {}),
            )
        logger.info(action, extra={"audit_id": str(event.pk), "outcome": outcome})
        return event
    except Exception:  # auditing must never take the business action down with it
        logger.exception("audit.record_failed", extra={"action": action})
        return None
