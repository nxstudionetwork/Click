"""POST /analytics/events {events: [{name, props, at}], session, platform} — batched, allow-listed, best effort."""

import re
from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import EVENTS, AnalyticsEvent

SAFE = re.compile(r"^[\w\-.:]{1,64}$")


def _clean(name: str, props) -> dict:
    out = {}
    for k in EVENTS[name]:
        v = (props or {}).get(k) if isinstance(props, dict) else None
        if isinstance(v, bool) or v is None:
            continue
        if isinstance(v, (int, float)):
            out[k] = v
        elif isinstance(v, str) and SAFE.match(v):  # identifiers and codes only — never free text
            out[k] = v
    return out


class EventsView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "search"

    def post(self, request):
        u = request.user
        customer = u.customer_profile if u and u.is_authenticated and hasattr(u, "customer_profile") else None
        session = str(request.data.get("session") or "")[:40]
        platform = str(request.data.get("platform") or "")[:12]
        now = timezone.now()
        rows = []
        for e in (request.data.get("events") or [])[:20]:
            name = str((e or {}).get("name") or "")
            if name not in EVENTS:
                continue
            at = parse_datetime(str(e.get("at") or "")) or now
            if not now - timedelta(days=1) <= at <= now + timedelta(minutes=5):
                at = now
            rows.append(AnalyticsEvent(name=name, customer=customer, session=session if SAFE.match(session or "x") else "", platform=platform,
                                       props=_clean(name, e.get("props")), occurred_at=at))
        AnalyticsEvent.objects.bulk_create(rows)
        return Response({"accepted": len(rows)}, status=status.HTTP_202_ACCEPTED)
