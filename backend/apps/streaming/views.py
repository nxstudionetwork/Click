"""
Click. Live API.

Public:   GET /live/home · /live/titles/<slug> · /live/play/<episode> · /live/channels/<slug> · /live/search?q=
Customer: POST /customer/live/progress {episode, position, duration} · POST /customer/live/watchlist/<slug> (toggle)

Signed-in viewers also get continue-watching, their watchlist and per-episode progress. Only active titles, episodes
and live channels are served.
"""

from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.permissions import IsCustomer

from .models import Episode, LiveChannel, Season, StreamTitle, WatchlistItem, WatchProgress


def _customer(request):
    u = request.user
    return getattr(u, "customer_profile", None) if u and u.is_authenticated else None


def _card(t: StreamTitle) -> dict:
    return {"slug": t.slug, "kind": t.kind, "kind_label": t.get_kind_display(), "title": t.title, "genres": [g.strip() for g in t.genres.split(",") if g.strip()],
            "language": t.language, "maturity": t.maturity, "year": t.year, "poster_url": t.poster_url, "backdrop_url": t.backdrop_url,
            "accent": t.accent, "synopsis": t.synopsis[:220], "episodes": getattr(t, "episode_count", None)}


def _episode(e: Episode, progress: dict | None = None) -> dict:
    p = (progress or {}).get(e.id)
    return {"id": str(e.id), "season": e.season.number, "number": e.number, "name": e.name, "synopsis": e.synopsis,
            "duration_seconds": e.duration_seconds, "thumbnail_url": e.thumbnail_url, "released_at": e.released_at.isoformat() if e.released_at else None,
            "progress": {"position_seconds": p.position_seconds, "finished": p.finished} if p else None}


def _channel(c: LiveChannel) -> dict:
    return {"slug": c.slug, "name": c.name, "description": c.description, "category": c.category, "now_playing": c.now_playing,
            "accent": c.accent, "is_live": c.is_live}


def _titles():
    return (StreamTitle.objects.filter(is_active=True)
            .annotate(episode_count=Count("seasons__episodes", filter=Q(seasons__episodes__is_active=True))).filter(episode_count__gt=0))


class HomeView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        titles = list(_titles())
        rails = []
        series = [t for t in titles if t.kind != StreamTitle.Kind.FILM]
        films = [t for t in titles if t.kind == StreamTitle.Kind.FILM]
        if series:
            rails.append({"id": "series", "title": "Series & shows", "items": [_card(t) for t in series]})
        if films:
            rails.append({"id": "films", "title": "Films", "items": [_card(t) for t in films]})
        genres: dict[str, list] = {}
        for t in titles:
            for g in [x.strip() for x in t.genres.split(",") if x.strip()]:
                genres.setdefault(g, []).append(t)
        for g, ts in sorted(genres.items(), key=lambda kv: -len(kv[1]))[:4]:
            if len(ts) >= 2:
                rails.append({"id": f"genre-{g.lower()}", "title": g, "items": [_card(t) for t in ts]})
        c = _customer(request)
        continue_watching, watchlist = [], []
        if c:
            seen = set()
            for p in (WatchProgress.objects.filter(customer=c, finished=False, episode__is_active=True, episode__season__title__is_active=True)
                      .select_related("episode__season__title")[:20]):
                t = p.episode.season.title
                if t.id in seen:
                    continue
                seen.add(t.id)
                continue_watching.append({**_card(t), "episode": _episode(p.episode, {p.episode_id: p}),
                                          "percent": round(100 * p.position_seconds / max(1, p.duration_seconds or p.episode.duration_seconds))})
            watchlist = [_card(w.title) for w in WatchlistItem.objects.filter(customer=c, title__is_active=True).select_related("title")]
        featured = next((t for t in titles if t.is_featured), titles[0] if titles else None)
        return Response({
            "featured": _card(featured) if featured else None,
            "live": [_channel(ch) for ch in LiveChannel.objects.filter(is_live=True)],
            "continue_watching": continue_watching, "watchlist": watchlist, "rails": rails,
        })


class TitleView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        t = get_object_or_404(StreamTitle.objects.filter(is_active=True), slug=slug)
        seasons = t.seasons.prefetch_related(Prefetch("episodes", queryset=Episode.objects.filter(is_active=True).select_related("season")))
        c = _customer(request)
        progress = {}
        if c:
            progress = {p.episode_id: p for p in WatchProgress.objects.filter(customer=c, episode__season__title=t)}
        data = _card(t)
        data["synopsis"] = t.synopsis
        data["credits"] = t.credits
        data["seasons"] = [{"number": s.number, "name": s.name or f"Season {s.number}", "episodes": [_episode(e, progress) for e in s.episodes.all()]}
                           for s in seasons if s.episodes.all()]
        data["in_watchlist"] = bool(c and WatchlistItem.objects.filter(customer=c, title=t).exists())
        # Where to start: the first unfinished episode the viewer began, else the next after the last finished one.
        eps = [e for s in seasons for e in s.episodes.all()]
        resume = next((e for e in eps if progress.get(e.id) and not progress[e.id].finished), None)
        if resume is None:
            done = [i for i, e in enumerate(eps) if progress.get(e.id) and progress[e.id].finished]
            resume = eps[done[-1] + 1] if done and done[-1] + 1 < len(eps) else (eps[0] if eps else None)
        data["play_next"] = _episode(resume, progress) if resume else None
        return Response(data)


class PlayView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, pk):
        e = get_object_or_404(Episode.objects.filter(is_active=True, season__title__is_active=True).select_related("season__title"), pk=pk)
        t = e.season.title
        order = list(Episode.objects.filter(season__title=t, is_active=True).order_by("season__number", "number").values_list("id", flat=True))
        i = order.index(e.id)
        nxt = Episode.objects.filter(pk=order[i + 1]).select_related("season").first() if i + 1 < len(order) else None
        c = _customer(request)
        p = WatchProgress.objects.filter(customer=c, episode=e).first() if c else None
        return Response({"episode": _episode(e, {e.id: p} if p else None), "video_url": e.video_url, "title": _card(t), "credits": t.credits,
                         "next": _episode(nxt) if nxt else None,
                         "resume_at": p.position_seconds if p and not p.finished and p.position_seconds > 5 else 0})


class ChannelView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        ch = get_object_or_404(LiveChannel.objects.all(), slug=slug)
        return Response({**_channel(ch), "stream_url": ch.stream_url if ch.is_live else None})


class SearchView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        q = request.query_params.get("q", "").strip()[:80]
        if len(q) < 2:
            return Response({"results": []})
        ts = _titles().filter(Q(title__icontains=q) | Q(genres__icontains=q) | Q(synopsis__icontains=q) | Q(seasons__episodes__name__icontains=q)).distinct()[:20]
        return Response({"results": [_card(t) for t in ts]})


class ProgressSerializer(serializers.Serializer):
    episode = serializers.UUIDField()
    position = serializers.IntegerField(min_value=0, max_value=60 * 60 * 12)
    duration = serializers.IntegerField(min_value=0, max_value=60 * 60 * 12, required=False, default=0)


class ProgressView(APIView):
    """Saves where the viewer stopped; 95% watched counts as finished."""

    permission_classes = [IsCustomer]
    throttle_scope = "buzz"

    def post(self, request):
        s = ProgressSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        e = get_object_or_404(Episode.objects.filter(is_active=True), pk=s.validated_data["episode"])
        duration = s.validated_data["duration"] or e.duration_seconds
        position = min(s.validated_data["position"], duration or s.validated_data["position"])
        finished = bool(duration) and position >= duration * 0.95
        WatchProgress.objects.update_or_create(customer=request.user.customer_profile, episode=e,
                                               defaults={"position_seconds": position, "duration_seconds": duration, "finished": finished})
        return Response({"position_seconds": position, "finished": finished})


class WatchlistView(APIView):
    permission_classes = [IsCustomer]

    def post(self, request, slug):
        t = get_object_or_404(StreamTitle.objects.filter(is_active=True), slug=slug)
        c = request.user.customer_profile
        existing = WatchlistItem.objects.filter(customer=c, title=t)
        if existing.exists():
            existing.delete()
            return Response({"in_watchlist": False})
        WatchlistItem.objects.create(customer=c, title=t)
        return Response({"in_watchlist": True})
