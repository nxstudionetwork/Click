"""
Click. Showtime discovery: home sections, search (with plain-language interpretation), suggestions, title pages
with per-day schedules, cinemas near the customer and seat maps.

Rules: dates are the customer's local dates (CLICK_LOCAL_TIMEZONE); a section appears only with real content;
ratings show only once RATING_MIN verified-attendance reviews exist; distances only when both points are known;
trending comes from real bookings, interest and views; seat states come from bookings and live holds.
"""

import math
import re
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.activity.models import CustomerActivity
from apps.activity.services import record

from .models import ROW_LETTERS, BookedSeat, ConcessionItem, Credit, Event, HeldSeat, SeatHold, Show, ShowFeature, ShowInterest, ShowReview, Venue
from .services import CANCELLATION_CUTOFF, HOLD_MINUTES, MAX_SEATS, active_offers, bookable_shows

RATING_MIN = 3
TRENDING_DAYS = 7
EVENING_FROM = 17
SECTION = 12
FORMATS = ["IMAX", "4DX", "3D", "2D"]


def local_tz():
    return ZoneInfo(settings.CLICK_LOCAL_TIMEZONE)


def local(dt):
    return dt.astimezone(local_tz())


def today():
    return local(timezone.now()).date()


def day_bounds(d):
    tz = local_tz()
    start = datetime.combine(d, time.min, tz)
    return start, start + timedelta(days=1)


def customer_of(request):
    user = getattr(request, "user", None)
    return getattr(user, "customer_profile", None) if user is not None and user.is_authenticated else None


def split(v: str) -> list[str]:
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def km(lat1, lng1, lat2, lng2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def venue_distance(v, lat, lng):
    if None in (lat, lng, v.latitude, v.longitude):
        return None
    return round(km(float(v.latitude), float(v.longitude), lat, lng), 1)


# --- cards ---------------------------------------------------------------------------------------------------

def _schedule_facts(event_ids):
    """formats / languages / next show per title from bookable shows, in one query."""
    facts = defaultdict(lambda: {"formats": set(), "languages": set(), "next": None, "venues": set()})
    for eid, fmt, lang, at, vid in bookable_shows().filter(event_id__in=event_ids).values_list("event_id", "format", "language", "starts_at", "venue_id"):
        f = facts[eid]
        if fmt:
            f["formats"].add(fmt)
        if lang:
            f["languages"].add(lang)
        f["venues"].add(vid)
        if f["next"] is None or at < f["next"]:
            f["next"] = at
    return facts


def card(e, facts=None, *, interested=None) -> dict:
    f = (facts or {}).get(e.id) or {"formats": set(), "languages": set(), "next": None, "venues": set()}
    rated = e.rating_count >= RATING_MIN
    return {
        "id": str(e.id), "slug": e.slug, "kind": e.kind, "status": e.status, "title": e.title, "tagline": e.tagline,
        "poster_url": e.poster_url, "backdrop_url": e.backdrop_url, "trailer_url": e.trailer_url, "media_credit": e.media_credit,
        "languages": split(e.languages), "genres": split(e.genres), "certification": e.certification,
        "duration_minutes": e.duration_minutes, "release_date": e.release_date.isoformat() if e.release_date else None,
        "rating": float(e.rating_average) if rated else None, "rating_count": e.rating_count,
        "formats": sorted(f["formats"], key=lambda x: FORMATS.index(x) if x in FORMATS else 9),
        "next_show_at": f["next"].isoformat() if f["next"] else None, "venue_count": len(f["venues"]),
        "bookable": f["next"] is not None, "interested": interested,
    }


def cards(events, customer=None):
    events = list(events)
    facts = _schedule_facts([e.id for e in events])
    mine = set(ShowInterest.objects.filter(customer=customer, event__in=events).values_list("event_id", flat=True)) if customer else set()
    return [card(e, facts, interested=(e.id in mine) if customer else None) for e in events]


def trending_scores() -> dict:
    since = timezone.now() - timedelta(days=TRENDING_DAYS)
    scores: Counter = Counter()
    for eid, n in BookedSeat.objects.filter(created_at__gte=since, is_active=True).values_list("show__event_id").annotate(n=Count("id")):
        scores[eid] += 3 * n
    for eid, n in ShowInterest.objects.filter(created_at__gte=since).values_list("event_id").annotate(n=Count("id")):
        scores[eid] += 2 * n
    for oid, n in CustomerActivity.objects.filter(created_at__gte=since, verb="show.viewed").values_list("object_id").annotate(n=Count("id")):
        if oid:
            scores[oid] += n
    return {k: v for k, v in scores.items() if v >= 3}


def public_titles():
    return Event.objects.filter(status__in=[Event.Status.NOW_SHOWING, Event.Status.COMING_SOON])


# --- home ----------------------------------------------------------------------------------------------------

def cinemas_near(lat=None, lng=None, limit=8, kinds=("cinema",)) -> list[dict]:
    now = timezone.now()
    _, tonight_end = day_bounds(today())
    venues = list(Venue.objects.filter(shows__in=bookable_shows(), kind__in=kinds).distinct().prefetch_related("screens"))
    out = []
    for v in venues:
        upcoming = bookable_shows().filter(venue=v).order_by("starts_at")
        nxt = upcoming.first()
        formats = sorted({f for s in v.screens.all() for f in split(s.formats)} | set(upcoming.exclude(format="").values_list("format", flat=True).distinct()),
                         key=lambda x: FORMATS.index(x) if x in FORMATS else 9)
        out.append({
            "id": str(v.id), "slug": v.slug, "name": v.name, "kind": v.kind, "locality": v.locality, "city": v.city, "address": v.address,
            "distance_km": venue_distance(v, lat, lng), "facilities": v.facilities, "formats": formats,
            "sound": sorted({s.sound for s in v.screens.all() if s.sound}),
            "shows_today": upcoming.filter(starts_at__lt=tonight_end).count(),
            "next_show": {"title": nxt.event.title, "slug": nxt.event.slug, "starts_at": nxt.starts_at.isoformat()} if nxt else None,
            "latitude": float(v.latitude) if v.latitude is not None else None, "longitude": float(v.longitude) if v.longitude is not None else None,
        })
    out.sort(key=lambda c: (c["distance_km"] is None, c["distance_km"] or 0, c["name"]))
    return out[:limit]


def tonight(lat=None, lng=None, customer=None) -> list[dict]:
    now = timezone.now()
    start, end = day_bounds(today())
    evening = max(now, datetime.combine(today(), time(EVENING_FROM), local_tz()))
    shows = bookable_shows().filter(starts_at__gte=evening, starts_at__lt=end)
    by_event = defaultdict(list)
    for s in shows:
        by_event[s.event_id].append(s)
    events = {e.id: e for e in Event.objects.filter(pk__in=by_event)}
    rows = []
    for eid, ss in by_event.items():
        dists = [d for d in (venue_distance(s.venue, lat, lng) for s in ss) if d is not None]
        rows.append({**card(events[eid], _schedule_facts([eid])), "tonight_count": len(ss),
                     "tonight_first": min(s.starts_at for s in ss).isoformat(), "nearest_km": min(dists) if dists else None})
    rows.sort(key=lambda r: (r["nearest_km"] is None, r["nearest_km"] or 0, r["tonight_first"]))
    return rows[:SECTION]


def special_formats() -> list[dict]:
    shows = bookable_shows()
    out = []
    for f in ["IMAX", "4DX", "3D"]:
        n = shows.filter(format=f).values("event").distinct().count()
        if n:
            out.append({"code": f, "label": f, "title_count": n, "venue_count": shows.filter(format=f).values("venue").distinct().count()})
    atmos = shows.filter(screen_ref__sound__icontains="atmos")
    if atmos.exists():
        out.append({"code": "atmos", "label": "Dolby Atmos", "title_count": atmos.values("event").distinct().count(),
                    "venue_count": atmos.values("venue").distinct().count()})
    return out


def offers_list(show=None) -> list[dict]:
    return [{"id": str(o.id), "title": o.title, "description": o.description, "venue": o.venue.name if o.venue_id else None,
             "title_slug": o.event.slug if o.event_id else None, "payment_method": o.payment_method, "min_seats": o.min_seats,
             "ends_at": o.ends_at.isoformat() if o.ends_at else None}
            for o in active_offers(show).select_related("venue", "event")[:8]]


def home(request, lat=None, lng=None) -> dict:
    customer = customer_of(request)
    bookable_ids = set(bookable_shows().values_list("event_id", flat=True))
    scores = trending_scores()
    movies_now = [e for e in Event.objects.filter(kind=Event.Kind.MOVIE, status=Event.Status.NOW_SHOWING, pk__in=bookable_ids)]
    movies_now.sort(key=lambda e: (-scores.get(e.id, 0), -float(e.rating_average), e.title))
    coming = list(Event.objects.filter(status=Event.Status.COMING_SOON).order_by("release_date", "title"))
    live = list(Event.objects.filter(kind=Event.Kind.EVENT, status=Event.Status.NOW_SHOWING, pk__in=bookable_ids).order_by("-rating_average")[:SECTION])
    trending = sorted([e for e in Event.objects.filter(pk__in=scores, status__in=[Event.Status.NOW_SHOWING, Event.Status.COMING_SOON])],
                      key=lambda e: -scores[e.id])
    top = list(Event.objects.filter(pk__in=bookable_ids, rating_count__gte=RATING_MIN).order_by("-rating_average", "-rating_count")[:SECTION])
    trailers = list(public_titles().exclude(trailer_url="").order_by("-status", "title")[:SECTION])

    now = timezone.now()
    feature = ShowFeature.objects.filter(is_active=True, starts_at__lte=now, ends_at__gt=now, event__status__in=[Event.Status.NOW_SHOWING, Event.Status.COMING_SOON]).select_related("event").first()
    featured_event = feature.event if feature else (movies_now[0] if movies_now else (coming[0] if coming else None))

    sections = []

    def add(sid, title, subtitle, events, *, kind="titles", minimum=1, link=None):
        events = list(events)
        if len(events) >= minimum:
            sections.append({"id": sid, "kind": kind, "title": title, "subtitle": subtitle, "link": link, "titles": cards(events[:SECTION], customer)})

    tonight_rows = tonight(lat, lng, customer)
    if tonight_rows:
        sections.append({"id": "tonight", "kind": "tonight", "title": "Tonight" + (" near you" if lat is not None else ""),
                         "subtitle": "Evening showtimes still open today.", "link": "/showtime/search?when=tonight", "titles": tonight_rows})
    add("now_showing", "Now Showing", "In cinemas now. Pick a showtime and your seats.", movies_now, link="/showtime/search?status=now_showing")
    add("coming_soon", "Coming Soon", "Tap “I’m interested” and we’ll tell you when booking opens.", coming, kind="coming")
    add("trending", "Trending Now", "Most booked, followed and viewed this week.", trending, minimum=3)
    add("top_rated", "Top Rated", f"Rated by people who watched with Click. ({RATING_MIN}+ reviews).", top, minimum=3)
    add("trailers", "Watch the Trailer", None, trailers, kind="trailers")
    add("live", "Live on Stage", "Concerts, comedy, theatre and more.", live, link="/showtime/search?kind=event")

    near = cinemas_near(lat, lng)
    formats = special_formats()
    offers = offers_list()
    langs = Counter(l for e in movies_now + live for l in split(e.languages))
    genres = Counter(g for e in movies_now + live for g in split(e.genres))
    highlights = (trending + [e for e in movies_now if e not in trending])[:SECTION]
    return {
        "featured": {**card(featured_event, _schedule_facts([featured_event.id])), "headline": feature.headline if feature else "",
                     "description": featured_event.description} if featured_event else None,
        "highlights": cards(highlights, customer),
        "sections": sections,
        "cinemas": near, "formats": formats, "offers": offers,
        "filters": {"languages": [l for l, _ in langs.most_common()], "genres": [g for g, _ in genres.most_common()],
                    "formats": sorted({f for e in movies_now for f in _schedule_facts([e.id])[e.id]["formats"]}, key=lambda x: FORMATS.index(x) if x in FORMATS else 9)},
        "location_used": lat is not None and lng is not None,
    }


# --- search --------------------------------------------------------------------------------------------------

def interpret(q: str) -> dict:
    """Plain-language query -> filters. Only what was recognised is reported back as `understood`."""
    text = " ".join(q.lower().split())
    rest = text
    it = {"languages": [], "genres": [], "format": None, "when": None, "near": False, "kind": None, "understood": []}
    known_langs = {l.lower(): l for e in public_titles() for l in split(e.languages)}
    known_genres = {g.lower(): g for e in public_titles() for g in split(e.genres)}
    for low, name in known_langs.items():
        if re.search(rf"\b{re.escape(low)}\b", rest):
            it["languages"].append(name)
            rest = re.sub(rf"\b{re.escape(low)}\b", " ", rest)
            it["understood"].append({"kind": "language", "label": name})
    for low, name in known_genres.items():
        for form in {low, low + "s", low.rstrip("s")}:
            if form and re.search(rf"\b{re.escape(form)}\b", rest):
                it["genres"].append(name)
                rest = re.sub(rf"\b{re.escape(form)}\b", " ", rest)
                it["understood"].append({"kind": "genre", "label": name})
                break
    for f in ["imax", "4dx", "3d", "2d"]:
        if re.search(rf"\b{f}\b", rest):
            it["format"] = f.upper()
            rest = re.sub(rf"\b{f}\b", " ", rest)
            it["understood"].append({"kind": "format", "label": f.upper()})
            break
    for word, when, label in [("tonight", "tonight", "Tonight"), ("today", "today", "Today"), ("tomorrow", "tomorrow", "Tomorrow"),
                              ("this weekend", "weekend", "This weekend"), ("weekend", "weekend", "This weekend")]:
        if re.search(rf"\b{word}\b", rest):
            it["when"] = when
            rest = re.sub(rf"\b{word}\b", " ", rest)
            it["understood"].append({"kind": "when", "label": label})
            break
    if re.search(r"\b(near me|nearby|close by|near)\b", rest):
        it["near"] = True
        rest = re.sub(r"\b(near me|nearby|close by|near)\b", " ", rest)
        it["understood"].append({"kind": "near", "label": "Near you"})
    if re.search(r"\b(concerts?|live|stand ?up|theatre|plays?)\b", rest) and not it["genres"]:
        it["kind"] = Event.Kind.EVENT
        it["understood"].append({"kind": "kind", "label": "Live shows"})
    stop = set("a an the me my i show shows movie movies film films find what whats playing on in at for to watch see good best some any is are with and or".split())
    it["terms"] = [w for w in re.findall(r"[a-z0-9&']+", rest) if w not in stop and len(w) > 1][:5]
    return it


def _when_range(when, date_str=None):
    d0 = today()
    if date_str:
        try:
            d = datetime.fromisoformat(date_str).date()
            return day_bounds(d)
        except ValueError:
            return None
    if when == "tonight":
        start, end = day_bounds(d0)
        return max(timezone.now(), datetime.combine(d0, time(EVENING_FROM), local_tz())), end
    if when == "today":
        return day_bounds(d0)
    if when == "tomorrow":
        return day_bounds(d0 + timedelta(days=1))
    if when == "weekend":
        sat = d0 + timedelta(days=(5 - d0.weekday()) % 7)
        return day_bounds(sat)[0], day_bounds(sat + timedelta(days=1))[1]
    return None


def search(params, request) -> dict:
    customer = customer_of(request)
    q = (params.get("q") or "").strip()[:100]
    it = interpret(q) if q else {"languages": [], "genres": [], "format": None, "when": None, "near": False, "kind": None, "terms": [], "understood": []}
    language = params.get("language") or (it["languages"][0] if it["languages"] else None)
    genre = params.get("genre") or (it["genres"][0] if it["genres"] else None)
    fmt = params.get("format") or it["format"]
    when = params.get("when") or it["when"]
    kind = params.get("kind") if params.get("kind") in Event.Kind.values else it["kind"]
    status = params.get("status")
    lat, lng = _coords(params)
    rng = _when_range(when, params.get("date"))

    titles = public_titles()
    if kind:
        titles = titles.filter(kind=kind)
    if status in (Event.Status.NOW_SHOWING, Event.Status.COMING_SOON):
        titles = titles.filter(status=status)
    if genre:
        titles = titles.filter(genres__icontains=genre)
    if language:
        titles = titles.filter(languages__icontains=language)
    shows = bookable_shows()
    schedule_filter = bool(fmt or rng)
    if fmt:
        shows = shows.filter(format__iexact=fmt)
    if language:
        shows = shows.filter(Q(language__iexact=language) | Q(language=""))
    if rng:
        shows = shows.filter(starts_at__gte=rng[0], starts_at__lt=rng[1])
    if schedule_filter:
        titles = titles.filter(pk__in=shows.values("event_id"))
    people = []
    for term in it["terms"]:
        credit_ids = Credit.objects.filter(name__icontains=term).values("event_id")
        venue_ids = Show.objects.filter(venue__name__icontains=term).values("event_id")
        titles = titles.filter(Q(title__icontains=term) | Q(cast__icontains=term) | Q(pk__in=credit_ids) | Q(pk__in=venue_ids)
                               | Q(tagline__icontains=term))
    if it["terms"]:
        names = Credit.objects.filter(Q(*[Q(name__icontains=t) for t in it["terms"]], _connector=Q.OR)).values("name", "role").annotate(n=Count("event", distinct=True)).order_by("-n")[:6]
        people = [{"name": p["name"], "role": p["role"], "title_count": p["n"]} for p in names]
    titles = list(titles.distinct())
    scores = trending_scores()
    if it["near"] and lat is not None:
        dist = {}
        for s in shows.filter(event__in=titles):
            d = venue_distance(s.venue, lat, lng)
            if d is not None:
                dist[s.event_id] = min(dist.get(s.event_id, 1e9), d)
        titles.sort(key=lambda e: (dist.get(e.id, 1e9), -scores.get(e.id, 0)))
    else:
        titles.sort(key=lambda e: (e.status != Event.Status.NOW_SHOWING, -scores.get(e.id, 0), -float(e.rating_average), e.title))
    cinemas = []
    if it["terms"]:
        vs = Venue.objects.filter(Q(*[Q(name__icontains=t) | Q(locality__icontains=t) for t in it["terms"]], _connector=Q.OR))
        cinemas = [c for c in cinemas_near(lat, lng, limit=50) if c["id"] in {str(v.id) for v in vs}]
    if customer and q:
        record(customer, "showtime.searched", {"q": q.lower()[:60]})
    return {"query": q, "understood": it["understood"], "count": len(titles), "titles": cards(titles[:60], customer), "cinemas": cinemas,
            "people": people, "applied": {"language": language, "genre": genre, "format": fmt, "when": when, "kind": kind, "status": status}}


def _coords(params):
    try:
        lat = float(params["lat"]) if params.get("lat") else None
        lng = float(params["lng"]) if params.get("lng") else None
    except (TypeError, ValueError):
        return None, None
    return lat, lng


def suggest(q: str) -> dict:
    q = q.strip()[:60]
    out = []
    if len(q) >= 2:
        for e in public_titles().filter(title__icontains=q).order_by("-status")[:5]:
            out.append({"text": e.title, "kind": "title", "path": f"/showtime/{e.slug}"})
            for lang in split(e.languages)[:3]:
                out.append({"text": f"{e.title} — {lang}", "kind": "title_language", "path": f"/showtime/{e.slug}?language={lang}"})
        for v in Venue.objects.filter(Q(name__icontains=q) | Q(locality__icontains=q))[:3]:
            out.append({"text": v.name, "kind": "cinema", "path": f"/showtime/search?q={v.name}"})
        for name in Credit.objects.filter(name__icontains=q).values_list("name", flat=True).distinct()[:3]:
            out.append({"text": name, "kind": "person", "path": f"/showtime/search?q={name}"})
    since = timezone.now() - timedelta(days=14)
    counts: dict = {}
    for meta, cust in CustomerActivity.objects.filter(verb="showtime.searched", created_at__gte=since).values_list("metadata", "customer_id")[:5000]:
        if term := (meta or {}).get("q"):
            counts.setdefault(term, set()).add(cust)
    trending = [t for t, c in sorted(counts.items(), key=lambda kv: -len(kv[1])) if len(c) >= 2][:8]
    scores = trending_scores()
    popular = sorted(Event.objects.filter(status=Event.Status.NOW_SHOWING, pk__in=bookable_shows().values("event_id")),
                     key=lambda e: (-scores.get(e.id, 0), -float(e.rating_average)))[:6]
    return {"query": q, "suggestions": out[:12], "trending": trending, "popular": [{"title": e.title, "slug": e.slug} for e in popular]}


# --- title page ----------------------------------------------------------------------------------------------

def _seat_counts(show_ids) -> tuple[dict, dict]:
    booked = dict(BookedSeat.objects.filter(show_id__in=show_ids, is_active=True).values_list("show_id").annotate(n=Count("id")))
    held = dict(HeldSeat.objects.filter(show_id__in=show_ids, hold__expires_at__gt=timezone.now()).values_list("show_id").annotate(n=Count("id")))
    return booked, held


def _price_range(s):
    if s.screen_ref_id and s.tier_prices:
        vals = [float(v) for v in s.tier_prices.values()]
    else:
        vals = [float(s.price), float(s.premium_price)] if s.premium_rows else [float(s.price)]
    return f"{min(vals):.2f}", f"{max(vals):.2f}"


def schedule(event, d, *, lat=None, lng=None, fmt=None, language=None) -> list[dict]:
    start, end = day_bounds(d)
    shows = list(bookable_shows().filter(event=event, starts_at__gte=start, starts_at__lt=end).order_by("starts_at"))
    if fmt:
        shows = [s for s in shows if s.format.lower() == fmt.lower()]
    if language:
        shows = [s for s in shows if not s.language or s.language.lower() == language.lower()]
    booked, held = _seat_counts([s.id for s in shows])
    venues = {}
    for s in shows:
        v = venues.setdefault(s.venue_id, {"venue": s.venue, "groups": {}})
        g = v["groups"].setdefault((s.format, s.language), [])
        cap = s.capacity
        left = max(cap - booked.get(s.id, 0) - held.get(s.id, 0), 0)
        lo, hi = _price_range(s)
        g.append({"show_id": str(s.id), "starts_at": s.starts_at.isoformat(), "screen": s.screen_ref.name if s.screen_ref_id else s.screen,
                  "seats_left": left, "status": "sold_out" if left == 0 else ("filling_fast" if left / cap < 0.2 else "available"),
                  "price_from": lo, "price_to": hi, "currency": s.currency,
                  "sound": s.screen_ref.sound if s.screen_ref_id else ""})
    out = []
    for vid, v in venues.items():
        venue = v["venue"]
        out.append({
            "venue": {"id": str(venue.id), "slug": venue.slug, "name": venue.name, "kind": venue.kind, "locality": venue.locality,
                      "address": venue.address, "city": venue.city, "facilities": venue.facilities,
                      "has_food": ConcessionItem.objects.filter(venue=venue, is_available=True).exists(),
                      "latitude": float(venue.latitude) if venue.latitude is not None else None,
                      "longitude": float(venue.longitude) if venue.longitude is not None else None},
            "distance_km": venue_distance(venue, lat, lng),
            "groups": [{"format": f or "Standard", "language": l, "times": times} for (f, l), times in v["groups"].items()],
        })
    out.sort(key=lambda r: (r["distance_km"] is None, r["distance_km"] or 0, r["venue"]["name"]))
    return out


def title_detail(slug, request, params) -> dict:
    customer = customer_of(request)
    event = get_object_or_404(public_titles(), slug=slug)
    lat, lng = _coords(params)
    all_shows = bookable_shows().filter(event=event)
    dates = sorted({local(s).date() for s in all_shows.values_list("starts_at", flat=True)})[:14]
    try:
        chosen = datetime.fromisoformat(params.get("date")).date() if params.get("date") else (dates[0] if dates else None)
    except ValueError:
        chosen = dates[0] if dates else None
    fmt, language = params.get("format") or None, params.get("language") or None
    published = ShowReview.objects.filter(event=event, status=ShowReview.Status.PUBLISHED).select_related("customer__user")
    dist = dict(published.values_list("rating").annotate(n=Count("id")))
    mine = published.filter(customer=customer).first() if customer else None
    if customer:
        record(customer, "show.viewed", obj=event)
    from .engagement import attended_booking

    related = Event.objects.filter(status=Event.Status.NOW_SHOWING, kind=event.kind, pk__in=bookable_shows().values("event_id")).exclude(pk=event.pk)
    first_genre = split(event.genres)[:1]
    if first_genre:
        related = related.filter(genres__icontains=first_genre[0])
    return {
        **cards([event], customer)[0],
        "description": event.description,
        "credits": [{"name": c.name, "role": c.role, "part": c.part} for c in event.credits.all()],
        "dates": [d.isoformat() for d in dates], "date": chosen.isoformat() if chosen else None,
        "all_formats": sorted(set(all_shows.exclude(format="").values_list("format", flat=True)), key=lambda x: FORMATS.index(x) if x in FORMATS else 9),
        "all_languages": sorted(set(all_shows.exclude(language="").values_list("language", flat=True))),
        "schedule": schedule(event, chosen, lat=lat, lng=lng, fmt=fmt, language=language) if chosen else [],
        "filters": {"format": fmt, "language": language},
        "rating_summary": {"average": float(event.rating_average) if event.rating_count >= RATING_MIN else None, "count": event.rating_count,
                           "minimum": RATING_MIN, "distribution": {str(s): dist.get(s, 0) for s in range(5, 0, -1)}},
        "reviews": [review_card(r) for r in published[:6]],
        "my_review": review_card(mine) if mine else None,
        "can_review": bool(customer and not mine and attended_booking(customer, event)),
        "interest_count": event.interests.count() if event.status == Event.Status.COMING_SOON else None,
        "offers": offers_list(),
        "related": cards(related[:8], customer),
        "location_used": lat is not None and lng is not None,
    }


def review_card(r) -> dict:
    name = (r.customer.user.full_name or "Click customer").split()[0]
    return {"id": str(r.id), "rating": r.rating, "body": r.body, "author": name, "verified": r.booking_id is not None,
            "created_at": r.created_at.isoformat(), "edited": (r.updated_at - r.created_at).total_seconds() > 60}


# --- seat map ------------------------------------------------------------------------------------------------

def seat_map(show_id, customer=None) -> dict:
    show = get_object_or_404(bookable_shows(), pk=show_id)
    booked = set(BookedSeat.objects.filter(show=show, is_active=True).values_list("label", flat=True))
    now = timezone.now()
    held = {}
    for label, cust in HeldSeat.objects.filter(show=show, hold__expires_at__gt=now).values_list("label", "hold__customer_id"):
        held[label] = cust
    my_hold = SeatHold.objects.filter(show=show, customer=customer, expires_at__gt=now).prefetch_related("seats").first() if customer else None

    def state(label, unavailable=False):
        if unavailable:
            return "unavailable"
        if label in booked:
            return "booked"
        if label in held:
            return "mine" if customer and held[label] == customer.id else "held"
        return "available"

    rows, tiers = [], []
    if show.screen_ref_id:
        names = show.screen_ref.tier_names()
        for r in show.screen_ref.layout["rows"]:
            rows.append({"row": r["row"], "tier": r["tier"], "gaps": r.get("gaps", []), "seats": [
                {"label": f"{r['row']}{n}", "number": n, "accessible": n in r.get("accessible", []),
                 "state": state(f"{r['row']}{n}", n in r.get("unavailable", []))} for n in range(1, int(r["seats"]) + 1)]})
        order = []
        for r in show.screen_ref.layout["rows"]:
            if r["tier"] not in order:
                order.append(r["tier"])
        tiers = [{"code": t, "name": names.get(t, t.title()), "price": f"{float(show.tier_prices.get(t, show.price)):.2f}"} for t in order]
    else:
        for i in range(show.rows):
            letter = ROW_LETTERS[i]
            tier = "premium" if i >= show.rows - show.premium_rows else "standard"
            rows.append({"row": letter, "tier": tier, "gaps": [], "seats": [
                {"label": f"{letter}{n}", "number": n, "accessible": False, "state": state(f"{letter}{n}")} for n in range(1, show.seats_per_row + 1)]})
        tiers = [{"code": "standard", "name": "Standard", "price": f"{show.price:.2f}"}]
        if show.premium_rows:
            tiers.append({"code": "premium", "name": "Premium", "price": f"{show.premium_price:.2f}"})
    v = show.venue
    return {
        "id": str(show.id), "starts_at": show.starts_at.isoformat(), "format": show.format, "language": show.language,
        "screen": show.screen_ref.name if show.screen_ref_id else show.screen, "sound": show.screen_ref.sound if show.screen_ref_id else "",
        "currency": show.currency,
        "event": card(show.event, _schedule_facts([show.event_id])),
        "venue": {"id": str(v.id), "slug": v.slug, "name": v.name, "locality": v.locality, "address": v.address, "city": v.city,
                  "facilities": v.facilities, "latitude": float(v.latitude) if v.latitude is not None else None,
                  "longitude": float(v.longitude) if v.longitude is not None else None},
        "tiers": tiers, "rows": rows, "max_per_booking": MAX_SEATS, "hold_minutes": HOLD_MINUTES,
        "my_hold": {"id": str(my_hold.id), "expires_at": my_hold.expires_at.isoformat(), "seats": [s.label for s in my_hold.seats.all()]} if my_hold else None,
        "cancellation_hours": int(CANCELLATION_CUTOFF.total_seconds() // 3600),
    }
