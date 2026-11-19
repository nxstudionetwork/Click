"""Time periods for Home widgets: today, yesterday, this/last week, this/last month, quarter, year, custom."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils.dateparse import parse_date

from apps.core.api.exceptions import DomainError

CHOICES = {
    "today": "Today", "yesterday": "Yesterday", "this_week": "This week", "last_week": "Last week", "this_month": "This month",
    "last_month": "Last month", "quarter": "This quarter", "year": "This year", "last_30_days": "Last 30 days", "custom": "Custom range",
}


@dataclass(frozen=True)
class Period:
    key: str
    label: str
    start: datetime
    end: datetime  # exclusive
    prev_start: datetime
    prev_end: datetime
    bucket: str  # day | month

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "start": self.start, "end": self.end,
                "previous_start": self.prev_start, "previous_end": self.prev_end, "bucket": self.bucket}


def _tz(tz_name: str | None):
    try:
        return ZoneInfo(tz_name or settings.CLICK_LOCAL_TIMEZONE)
    except Exception:
        return ZoneInfo("UTC")


def _at(d: date, tz) -> datetime:
    return datetime.combine(d, time.min, tzinfo=tz)


def resolve(key: str | None, *, start: str | None = None, end: str | None = None, tz_name: str | None = None) -> Period:
    key = key if key in CHOICES else "last_30_days"
    tz = _tz(tz_name)
    today = datetime.now(tz).date()
    if key == "today":
        s, e = today, today + timedelta(days=1)
    elif key == "yesterday":
        s, e = today - timedelta(days=1), today
    elif key == "this_week":
        s = today - timedelta(days=today.weekday())
        e = today + timedelta(days=1)
    elif key == "last_week":
        s = today - timedelta(days=today.weekday() + 7)
        e = s + timedelta(days=7)
    elif key == "this_month":
        s, e = today.replace(day=1), today + timedelta(days=1)
    elif key == "last_month":
        e = today.replace(day=1)
        s = (e - timedelta(days=1)).replace(day=1)
    elif key == "quarter":
        s = today.replace(month=3 * ((today.month - 1) // 3) + 1, day=1)
        e = today + timedelta(days=1)
    elif key == "year":
        s, e = today.replace(month=1, day=1), today + timedelta(days=1)
    elif key == "custom":
        s, e = parse_date(start or ""), parse_date(end or "")
        if not s or not e or e < s:
            raise DomainError("Choose a valid custom date range.", code="validation_error")
        if (e - s).days > 731:
            raise DomainError("Custom ranges can be at most two years.", code="validation_error")
        e = e + timedelta(days=1)
    else:  # last_30_days
        s, e = today - timedelta(days=29), today + timedelta(days=1)
    length = e - s
    # Partial periods (this week/month/quarter/year, today) compare with the same elapsed length just before.
    ps, pe = s - length, s
    label = CHOICES[key] if key != "custom" else f"{s:%d %b %Y} – {(e - timedelta(days=1)):%d %b %Y}"
    return Period(key, label, _at(s, tz), _at(e, tz), _at(ps, tz), _at(pe, tz), "month" if length.days > 92 else "day")
