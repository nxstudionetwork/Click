"""Global Search API: results, suggestions, the customer's recent searches (private) and trending (real counts)."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.permissions import IsCustomer

from . import engine
from .models import SearchHistory

TREND_MIN_SEARCHES = 3  # a query needs this many searches by different customers this week to be "trending"


def _customer(request):
    u = request.user
    return u.customer_profile if u and u.is_authenticated and hasattr(u, "customer_profile") else None


class GlobalSearchView(APIView):
    """GET /search/global?q=&group= — grouped results across Click. (+ your own records when the query is an ID)."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = "search"

    def get(self, request):
        c = _customer(request)
        q = request.query_params.get("q", "")
        data = engine.search(q, c, group=request.query_params.get("group", ""))
        data["mine"] = engine.lookup_id(c, q)
        data["sponsored"] = _sponsored(request, c, data["query"], request.query_params.get("group", ""))
        if c and len(data["query"]) >= 2 and request.query_params.get("record") != "0":
            last = c.search_history.first()
            if not last or last.normalized != data["query"]:
                SearchHistory.objects.create(customer=c, query=q.strip()[:100], normalized=data["query"], results=data["count"] + len(data["mine"]))
        return Response(data)


class SuggestView(APIView):
    """GET /search/suggest?q= — as-you-type: matching entities, category phrases and your recent searches."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = "search"

    def get(self, request):
        c = _customer(request)
        q = engine.normalize(request.query_params.get("q", ""))
        if len(q) < 2:
            return Response({"query": q, "suggestions": [], "recent": _recent(c, ""), "trending": _trending()})
        res = engine.search(q, c, limit=3)
        ents = [h for h in res["top"]] + [h for g in res["groups"] for h in g["results"][:1]]
        seen, out = set(), []
        for h in ents:
            if h["link"] in seen:
                continue
            seen.add(h["link"])
            out.append({"type": h["type"], "title": h["title"], "subtitle": h["subtitle"], "link": h["link"], "group": h["group"]})
        return Response({"query": q, "suggestions": out[:8], "mine": engine.lookup_id(c, q), "recent": _recent(c, q)[:3]})


def _recent(c, q: str) -> list[dict]:
    if c is None:
        return []
    seen, out = set(), []
    for h in c.search_history.filter(normalized__startswith=q)[:40] if q else c.search_history.all()[:40]:
        if h.normalized not in seen:
            seen.add(h.normalized)
            out.append({"id": str(h.id), "query": h.query, "at": h.created_at.isoformat()})
    return out[:8]


def _trending() -> list[str]:
    since = timezone.now() - timedelta(days=7)
    rows = (SearchHistory.objects.filter(created_at__gte=since, results__gt=0).values("normalized")
            .annotate(people=Count("customer", distinct=True)).filter(people__gte=TREND_MIN_SEARCHES).order_by("-people")[:8])
    return [r["normalized"] for r in rows]


class RecentView(APIView):
    """GET /customer/search/recent · DELETE (clear all) · DELETE /customer/search/recent/<id> (one, and its repeats)."""

    permission_classes = [IsCustomer]

    def get(self, request):
        return Response({"results": _recent(request.user.customer_profile, "")})

    def delete(self, request, pk=None):
        c = request.user.customer_profile
        if pk:
            h = c.search_history.filter(pk=pk).first()
            if h:
                c.search_history.filter(normalized=h.normalized).delete()
        else:
            c.search_history.all().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _sponsored(request, customer, q: str, group: str) -> list[dict]:
    """At most one clearly labelled sponsored result, and only if the promoted listing itself matches the search."""
    if len(q) < 3:
        return []
    from apps.discover.engine import auction, viewer_key

    words = [w for w in q.split() if len(w) > 2]
    for ad in auction(customer, viewer_key(request), service=group, city="", placement="search", slots=3):
        text = f"{ad['title']} {ad['subtitle']} {ad.get('headline') or ''}".lower()
        if words and all(w in text for w in words):
            return [ad]
    return []
