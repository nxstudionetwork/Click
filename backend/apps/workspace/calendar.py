"""
Calendar foundation: one timeline built from the records that carry dates (task due dates, approval deadlines,
the user's own pending requests). Meetings and events plug in later as another source in SOURCES.
"""

from datetime import timedelta

from django.utils import timezone

from apps.access.authz import AuthContext


def _tasks(ctx, start, end):
    from apps.workflows.models import Task

    for t in Task.objects.filter(assignee=ctx.user, status__in=["open", "in_progress"], due_at__gte=start, due_at__lt=end):
        yield {"id": f"task:{t.pk}", "kind": "task", "title": t.title, "at": t.due_at, "priority": t.priority, "path": f"/tasks?open={t.pk}"}


def _approvals(ctx, start, end):
    from apps.workflows.selectors import inbox_for

    for r in inbox_for(ctx):
        if r.due_at and start <= r.due_at < end:
            yield {"id": f"approval:{r.pk}", "kind": "approval", "title": f"Decide: {r.title}", "at": r.due_at,
                   "priority": "high", "path": f"/approvals/{r.pk}"}


SOURCES: list = [_tasks, _approvals]  # modules append their own sources (People & HR: leave, reviews, holidays …)


def upcoming(ctx: AuthContext, *, days: int = 14, start=None) -> list[dict]:
    start = start or timezone.now() - timedelta(days=1)
    end = start + timedelta(days=days + 1)
    items = [i for src in SOURCES for i in src(ctx, start, end)]
    return sorted(items, key=lambda i: i["at"])


def month(ctx: AuthContext, year: int, month_: int) -> list[dict]:
    start = timezone.now().replace(year=year, month=month_, day=1, hour=0, minute=0, second=0, microsecond=0)
    nxt = (start + timedelta(days=32)).replace(day=1)
    return [i for src in SOURCES for i in src(ctx, start, nxt)]
