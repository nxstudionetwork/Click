"""Announcements: who sees them (audience), when (start/end), acknowledgement, and what can't be dismissed."""

from django.db.models import Q
from django.utils import timezone

from .models import Announcement, AnnouncementAck


def _in_audience(ctx, a: Announcement) -> bool:
    aud = a.audience or {}
    if not aud or aud.get("all"):
        return True
    emp = ctx.employee
    role_keys = {r.key for r in ctx.roles}
    if aud.get("roles") and role_keys & set(aud["roles"]):
        return True
    if aud.get("kinds") and ctx.kind in aud["kinds"]:
        return True
    if emp is None:
        return False
    if aud.get("departments") and emp.department_id and str(emp.department_id) in {str(x) for x in aud["departments"]}:
        return True
    if aud.get("units") and emp.org_unit_id:
        anc = set(emp.org_unit.ancestor_ids) if emp.org_unit else set()
        if anc & {str(x) for x in aud["units"]}:
            return True
    return False


def visible_for(ctx, *, include_dismissed: bool = False) -> list[Announcement]:
    now = timezone.now()
    qs = Announcement.objects.filter(organization=ctx.organization, is_published=True, starts_at__lte=now).filter(
        Q(ends_at__isnull=True) | Q(ends_at__gt=now)).select_related("created_by")
    acks = {a.announcement_id: a for a in AnnouncementAck.objects.filter(user=ctx.user, announcement__in=qs)}
    out = []
    for a in qs[:100]:
        if not _in_audience(ctx, a):
            continue
        ack = acks.get(a.pk)
        if ack and ack.dismissed and a.priority != "critical" and not include_dismissed:
            continue
        a._ack = ack  # noqa: SLF001
        out.append(a)
    rank = {"critical": 0, "important": 1, "normal": 2}
    return sorted(out, key=lambda a: (rank.get(a.priority, 3), bool(getattr(a, "_ack", None)), -a.starts_at.timestamp()))


def payload(a: Announcement, ctx=None) -> dict:
    ack = getattr(a, "_ack", None)
    return {"id": str(a.pk), "title": a.title, "body": a.body, "category": a.category, "category_label": a.get_category_display(),
            "priority": a.priority, "starts_at": a.starts_at, "ends_at": a.ends_at, "requires_ack": a.requires_ack,
            "acknowledged": bool(ack and ack.acknowledged_at), "acknowledged_at": ack.acknowledged_at if ack else None,
            "dismissed": bool(ack and ack.dismissed), "can_dismiss": a.priority != "critical" and not (a.requires_ack and not (ack and ack.acknowledged_at)),
            "author": a.created_by.full_name if a.created_by_id else None, "audience": a.audience}
