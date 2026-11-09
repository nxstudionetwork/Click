"""
DEVELOPMENT MOCK DATA: Click. Showtime.

Builds on devseed.events (titles and venues):
  * cinema locations, facilities and real screen layouts (Classic / Prime / Recliner tiers, aisles, accessible seats)
  * a week of showtimes in local time (Asia/Kolkata), per screen and format (2D, 3D, IMAX, 4DX), with titles shown in
    each of their languages; live shows re-timed to local evenings
  * food & drinks menus, Showtime offers, an editorial feature, cast & crew
  * "Open Cinema": three Creative Commons films by the Blender Foundation (Big Buck Bunny, Sintel, Elephants Dream)
    with their real posters/trailers hotlinked from blender.org and attributed (CC BY). Other titles are fictional
    and have no artwork; the app shows a typographic poster instead of a fake one.
  * ratings come only from reviews written by dev viewers who attended past shows (their bookings are recorded),
    and "interested" from dev viewers following upcoming titles. Seeded rating numbers are reset to these records.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal as D
from zoneinfo import ZoneInfo
from zlib import crc32

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.bookings.engagement import recompute_rating, save_review
from apps.bookings.models import (BookedSeat, Booking, ConcessionItem, Credit, Event, Screen, Show, ShowFeature, ShowInterest, ShowOffer,
                                  ShowReview, Venue)
from apps.customers.models import CustomerProfile
from apps.payments.models import Payment
from apps.users.models import User

from . import locality_point

TZ = ZoneInfo(settings.CLICK_LOCAL_TIMEZONE)


def h(s: str) -> int:
    return crc32(s.encode())


# name, locality, address, facilities, screens [(name, formats, sound, layout kind)]
CINEMAS = [
    ("Click Cineplex Indiranagar", "Indiranagar", "100 Feet Road", ["Parking", "Wheelchair access", "Food court", "M-ticket"],
     [("Audi 1 · IMAX", "IMAX, 2D", "IMAX 12-channel", "large"), ("Audi 2", "2D, 3D", "Dolby Atmos", "medium"), ("Audi 3", "2D", "Dolby 7.1", "small")]),
    ("Starline Cinemas Koramangala", "Koramangala", "80 Feet Road", ["Wheelchair access", "Food court", "M-ticket"],
     [("Screen 1", "2D, 3D", "Dolby Atmos", "medium"), ("Screen 2", "2D", "Dolby 7.1", "small")]),
    ("Aurora Multiplex Whitefield", "Whitefield", "ITPL Main Road", ["Parking", "Wheelchair access", "Food court", "Recliners"],
     [("4DX Hall", "4DX, 3D", "Dolby Atmos", "fourdx"), ("Hall 2", "2D, 3D", "Dolby 7.1", "medium")]),
    ("Regal Talkies Jayanagar", "Jayanagar", "11th Main, 4th Block", ["Single screen", "Wheelchair access"],
     [("Main Screen", "2D", "Dolby 7.1", "classic")]),
    ("Skyline Cinemas HSR", "HSR Layout", "27th Main", ["Parking", "Food court", "M-ticket"],
     [("Screen A", "2D, 3D", "Dolby Atmos", "medium"), ("Screen B", "IMAX, 2D", "IMAX 12-channel", "large")]),
]
OTHER_VENUES = {"Skydeck Arena": ["Parking", "Wheelchair access"], "Rangmanch Theatre House": ["Wheelchair access"],
                "The Velvet Room": ["Bar", "18+"], "Lakeside Open Grounds": ["Parking", "Open air"]}

TIERS = [{"code": "classic", "name": "Classic"}, {"code": "prime", "name": "Prime"}, {"code": "recliner", "name": "Recliner"}]


def layout(kind: str) -> dict:
    """Front-to-back rows. Aisles via `gaps` (after seat N), accessible seats on row A, a few seats out of service."""
    if kind == "large":
        spec = [(r, "classic", 20, [5, 15]) for r in "ABCDE"] + [(r, "prime", 22, [5, 17]) for r in "FGHIJK"] + [(r, "recliner", 12, [6]) for r in "LM"]
    elif kind == "fourdx":
        spec = [(r, "prime", 12, [6]) for r in "ABCDEF"]
    elif kind == "classic":
        spec = [(r, "classic", 18, [9]) for r in "ABCDEFGH"] + [(r, "prime", 18, [9]) for r in "IJK"]
    elif kind == "small":
        spec = [(r, "classic", 12, [6]) for r in "ABC"] + [(r, "prime", 14, [7]) for r in "DEFG"] + [("H", "recliner", 8, [4])]
    else:
        spec = [(r, "classic", 16, [4, 12]) for r in "ABCD"] + [(r, "prime", 16, [4, 12]) for r in "EFGHI"] + [(r, "recliner", 10, [5]) for r in "JK"]
    rows = []
    for i, (row, tier, seats, gaps) in enumerate(spec):
        rows.append({"row": row, "tier": tier, "seats": seats, "gaps": gaps,
                     "accessible": [1, 2] if i == 0 else [], "unavailable": [seats // 2] if row in ("C",) and kind != "fourdx" else []})
    used = {r["tier"] for r in rows}
    return {"rows": rows, "tiers": [t for t in TIERS if t["code"] in used]}


BASE_PRICES = {"classic": 180, "prime": 260, "recliner": 480}
FORMAT_EXTRA = {"2D": 0, "3D": 60, "IMAX": 180, "4DX": 260}

MENU = [  # name, description, category, price, veg
    ("Click. Date Night Combo", "Large popcorn, 2 drinks, nachos", "combo", "649", True),
    ("Solo Combo", "Regular popcorn + drink", "combo", "349", True),
    ("Salted Popcorn (Large)", "", "popcorn", "299", True),
    ("Caramel Popcorn (Regular)", "", "popcorn", "249", True),
    ("Cheese Nachos", "With salsa", "snacks", "229", True),
    ("Chicken Hot Dog", "", "snacks", "249", False),
    ("Cold Coffee", "400 ml", "drinks", "189", True),
    ("Soft Drink (Large)", "", "drinks", "149", True),
    ("Mineral Water", "500 ml", "drinks", "40", True),
]

OPEN_CINEMA = [  # title, minutes, genres, release, poster, trailer, synopsis, director
    ("Big Buck Bunny", 10, "Animation, Comedy, Family", date(2008, 5, 30), "", "https://download.blender.org/peach/trailer/trailer_iphone.m4v",
     "A giant rabbit's peaceful day is ruined by three bullies, until he decides to teach them a lesson.", "Sacha Goedegebure"),
    ("Sintel", 15, "Animation, Fantasy, Adventure", date(2010, 9, 27), "", "https://download.blender.org/durian/trailer/sintel_trailer-720p.mp4",
     "A lonely young woman searches for the baby dragon she once rescued.", "Colin Levy"),
    ("Elephants Dream", 11, "Animation, Sci-Fi", date(2006, 3, 24), "https://download.blender.org/ED/cover.jpg", "",
     "Two men explore a strange machine-world that one of them believes he controls.", "Bassam Kurdali"),
]
OPEN_CREDIT = "© Blender Foundation · CC BY · blender.org"

CREW_FIRST = ["Anand", "Priya", "Rahul", "Lakshmi", "Farhan", "Nandini", "Suresh", "Kavya", "Imran", "Deepa"]
CREW_LAST = ["Menon", "Kapoor", "Rao", "Iyer", "Sheikh", "Gowda", "Nair", "Bhat", "Das", "Pillai"]

VIEWERS = [("Aditi", "Indiranagar"), ("Nikhil", "Koramangala"), ("Sneha", "HSR Layout"), ("Arvind", "Whitefield"),
           ("Zoya", "Jayanagar"), ("Manoj", "Malleshwaram"), ("Ira", "Bellandur"), ("Kabir", "Basavanagudi")]
REVIEW_BODY = {5: "Loved every minute. The big screen made it.", 4: "Really good watch, a little long in the middle.",
               3: "Decent once. Great sound in this hall.", 2: "Not for me, but the cinema was comfortable."}


def local_dt(d: date, hh: int, mm: int) -> datetime:
    return datetime.combine(d, time(hh, mm), TZ)


def _venues():
    cinemas = []
    for name, locality, address, facilities, screens in CINEMAS:
        lat, lng = locality_point(locality, name)
        v, _ = Venue.objects.update_or_create(slug=slugify(name), defaults=dict(
            name=name, kind=Venue.Kind.CINEMA, city="Bengaluru", locality=locality, address=address, facilities=facilities, latitude=lat, longitude=lng))
        made = []
        for sname, formats, sound, kind in screens:
            s, _ = Screen.objects.update_or_create(venue=v, name=sname, defaults=dict(formats=formats, sound=sound, layout=layout(kind)))
            made.append(s)
        for pos, (item, desc, cat, price, veg) in enumerate(MENU):
            ConcessionItem.objects.update_or_create(venue=v, name=item, defaults=dict(description=desc, category=cat, price=D(price), is_veg=veg,
                                                                                      is_available=not (item == "Chicken Hot Dog" and "Regal" in name), position=pos))
        cinemas.append((v, made))
    for v in Venue.objects.exclude(kind=Venue.Kind.CINEMA):
        lat, lng = locality_point(v.locality or "MG Road", v.name)
        Venue.objects.filter(pk=v.pk).update(facilities=OTHER_VENUES.get(v.name, []), **({"latitude": lat, "longitude": lng} if lat else {}))
    return cinemas


def _credits(event, idx):
    if event.credits.exists():
        return
    for pos, name in enumerate([c.strip() for c in event.cast.split(",") if c.strip() and c.strip() != "Voice cast"][:4]):
        Credit.objects.create(event=event, name=name, role=Credit.Role.CAST, part="Lead" if pos == 0 else "", position=pos)
    for pos, job in enumerate(["Director", "Producer", "Music", "Cinematography"]):
        n = h(event.title + job)
        Credit.objects.create(event=event, role=Credit.Role.CREW, part=job, position=pos,
                              name=f"{CREW_FIRST[n % 10]} {CREW_LAST[(n // 10) % 10]}")


def _open_cinema():
    out = []
    for title, minutes, genres, released, poster, trailer, synopsis, director in OPEN_CINEMA:
        e, _ = Event.objects.update_or_create(slug=slugify(title), defaults=dict(
            title=title, kind=Event.Kind.MOVIE, status=Event.Status.NOW_SHOWING, genres=genres, languages="English", certification="U",
            duration_minutes=minutes, release_date=released, tagline="Open Cinema: a Creative Commons film", description=synopsis,
            poster_url=poster, trailer_url=trailer, media_credit=OPEN_CREDIT, cast=""))
        if not e.credits.exists():
            Credit.objects.create(event=e, name=director, role=Credit.Role.CREW, part="Director", position=0)
            Credit.objects.create(event=e, name="Blender Foundation", role=Credit.Role.CREW, part="Producer", position=1)
        out.append(e)
    return out


def _showtimes(cinemas) -> int:
    """A week of showtimes from today (local), idempotent per (title, screen, start)."""
    now = timezone.now()
    today = timezone.localtime(now, TZ).date()
    # Older seed runs scheduled shows in UTC on simple layouts: retire the unbooked future ones (kept, not deleted).
    Show.objects.filter(starts_at__gt=now, screen_ref__isnull=True, venue__kind=Venue.Kind.CINEMA, bookings__isnull=True).update(status=Show.Status.CANCELLED)
    movies = list(Event.objects.filter(kind=Event.Kind.MOVIE, status=Event.Status.NOW_SHOWING).order_by("title"))
    slots = [(10, 15), (13, 30), (16, 45), (19, 30), (22, 15)]
    made = 0
    for mi, movie in enumerate(movies):
        langs = [l.strip() for l in movie.languages.split(",") if l.strip()] or ["English"]
        genres = movie.genres.lower()
        short = (movie.duration_minutes or 120) < 30
        for ci, (venue, screens) in enumerate(cinemas):
            if (mi + ci) % 3 == 2 and not short:
                continue  # each title plays at most cinemas, not all
            for day in range(7):
                if (mi + day) % 6 == 5 and ci == 0:
                    continue  # some days have no show at a cinema (tests "no showtimes for this date")
                for si, (hh, mm) in enumerate(slots):
                    if (mi * 3 + ci + si + day) % 4:
                        continue
                    if short and hh not in (10, 13):
                        continue
                    screen = screens[(mi + si) % len(screens)]
                    allowed = [f.strip() for f in screen.formats.split(",")]
                    if "IMAX" in allowed and ("action" in genres or "sci-fi" in genres or "adventure" in genres):
                        fmt = "IMAX"
                    elif "4DX" in allowed and ("action" in genres or "adventure" in genres or "animation" in genres):
                        fmt = "4DX"
                    elif "3D" in allowed and ("animation" in genres or "sci-fi" in genres) and si % 2 == 0:
                        fmt = "3D"
                    else:
                        fmt = "2D" if "2D" in allowed else allowed[0]
                    starts = local_dt(today + timedelta(days=day), hh, mm)
                    if starts <= now + timedelta(minutes=30):
                        continue
                    lang = langs[(si + day) % len(langs)]
                    tiers = {t["code"] for t in screen.layout["tiers"]}
                    prices = {t: f"{BASE_PRICES[t] + FORMAT_EXTRA.get(fmt, 0) + (20 if ci == 0 else 0)}.00" for t in tiers}
                    rows = screen.layout["rows"]
                    _, created = Show.objects.get_or_create(event=movie, venue=venue, screen_ref=screen, starts_at=starts, defaults=dict(
                        language=lang, format=fmt, screen=screen.name, rows=len(rows), seats_per_row=max(int(r["seats"]) for r in rows),
                        premium_rows=0, price=D(min(prices.values())), premium_price=D(max(prices.values())), tier_prices=prices))
                    made += created
    # Live shows created by older seed runs in UTC (after midnight locally): retire the unbooked ones.
    for show in Show.objects.filter(starts_at__gt=now, event__kind=Event.Kind.EVENT, bookings__isnull=True, status=Show.Status.SCHEDULED):
        if timezone.localtime(show.starts_at, TZ).hour < 12:
            Show.objects.filter(pk=show.pk).update(status=Show.Status.CANCELLED)
    return made


def _offers(cinemas):
    now = timezone.now()
    first = cinemas[0][0]
    for title, desc, kind, value, cap, min_amount, min_seats, venue, pay, ends in [
        ("20% off on 2+ seats", "Up to ₹150 off your tickets", "percent", "20", "150", "0", 2, None, "", 30),
        ("₹75 off with Click. Wallet", "On tickets worth ₹400 or more", "flat", "75", None, "400", 1, None, "wallet", 30),
        (f"Recliner nights at {first.name}", "₹100 off tickets worth ₹900+", "flat", "100", None, "900", 1, first, "", 14),
        ("Diwali screenings (ended)", "This offer has ended and must not show", "percent", "30", "200", "0", 1, None, "", -2),
    ]:
        ShowOffer.objects.update_or_create(title=title, defaults=dict(
            description=desc, discount_type=kind, discount_value=D(value), max_discount=D(cap) if cap else None, min_amount=D(min_amount),
            min_seats=min_seats, venue=venue, payment_method=pay, is_active=True,
            starts_at=now - timedelta(days=40) if ends < 0 else now - timedelta(days=1), ends_at=now + timedelta(days=ends)))


def _viewer(name, locality):
    email = f"viewer.{name.lower()}@click.local"
    user = User.objects.filter(email=email).first() or User.objects.create_user(email, None, full_name=f"{name} (dev viewer)", phone_verified=False)
    profile, _ = CustomerProfile.objects.get_or_create(user=user)
    return profile


def _past_booking(profile, event, venue, screen, starts, seats) -> Booking:
    """A booking for a show that already happened (attendance), recorded with its pay-at-venue payment."""
    rows = screen.layout["rows"]
    show, _ = Show.objects.get_or_create(event=event, venue=venue, screen_ref=screen, starts_at=starts, defaults=dict(
        language=event.languages.split(",")[0].strip(), format="2D", screen=screen.name, rows=len(rows), seats_per_row=max(int(r["seats"]) for r in rows),
        price=D("200"), premium_price=D("480"), tier_prices={t["code"]: f"{BASE_PRICES[t['code']]}.00" for t in screen.layout["tiers"]}))
    taken = set(BookedSeat.objects.filter(show=show, is_active=True).values_list("label", flat=True))
    labels = [l for l in seats if l not in taken and show.seat_tier(l)]
    if not labels:
        return None
    sub = sum((show.seat_price(l) for l in labels), D("0"))
    fee = D("20") * len(labels)
    tax = (fee * settings.CLICK_SERVICE_FEE_TAX_RATE).quantize(D("0.01"))
    import uuid

    b = Booking.objects.create(customer=profile, show=show, subtotal=sub, convenience_fee=fee, tax=tax, total=sub + fee + tax,
                               idempotency_key=uuid.uuid4(), checked_in_at=starts - timedelta(minutes=10))
    BookedSeat.objects.bulk_create(BookedSeat(booking=b, show=show, label=l, tier=show.seat_tier(l), price=show.seat_price(l)) for l in labels)
    Payment.objects.create(booking=b, method="pay_at_venue", amount=b.total, status=Payment.Status.CAPTURED)
    Booking.objects.filter(pk=b.pk).update(created_at=starts - timedelta(days=1))
    return b


def _audience(cinemas):
    """Dev viewers who attended past shows and reviewed them (the only source of ratings), and follow upcoming titles."""
    if ShowReview.objects.filter(customer__user__email__startswith="viewer.").exists():
        return 0
    viewers = [_viewer(n, l) for n, l in VIEWERS]
    today = timezone.localtime(timezone.now(), TZ).date()
    movies = list(Event.objects.filter(kind=Event.Kind.MOVIE, status=Event.Status.NOW_SHOWING).order_by("title"))
    made = 0
    for mi, movie in enumerate(movies):
        audience = viewers[: 2 + (h(movie.title) % 6)]  # some titles get 2 reviews (below the rating minimum), most more
        venue, screens = cinemas[mi % len(cinemas)]
        screen = screens[-1]
        for vi, viewer in enumerate(audience):
            starts = local_dt(today - timedelta(days=1 + (vi % 3)), 19, 30)
            row = screen.layout["rows"][min(3, len(screen.layout["rows"]) - 1)]["row"]
            b = _past_booking(viewer, movie, venue, screen, starts, [f"{row}{3 + vi * 2}", f"{row}{4 + vi * 2}"][: 1 + vi % 2])
            if b is None:
                continue
            n = h(movie.title + viewer.user.email)
            rating = [5, 4, 5, 4, 3, 5, 4, 2, 5, 4][n % 10]
            save_review(viewer, movie, rating=rating, body=REVIEW_BODY[rating] if n % 3 else "", create=True)
            made += 1
    for ci, coming in enumerate(Event.objects.filter(status=Event.Status.COMING_SOON)):
        for viewer in viewers[: 1 + (h(coming.title) % 7)]:
            ShowInterest.objects.get_or_create(event=coming, customer=viewer)
    return made


@transaction.atomic
def seed_showtime(log) -> None:
    cinemas = _venues()
    for idx, e in enumerate(Event.objects.filter(kind__in=[Event.Kind.MOVIE, Event.Kind.EVENT])):
        _credits(e, idx)
    open_titles = _open_cinema()
    # Ratings are earned: reset seeded numbers and recompute from published reviews.
    for e in Event.objects.all():
        recompute_rating(e.pk)
    made = _showtimes(cinemas)
    _offers(cinemas)
    now = timezone.now()
    lead = Event.objects.filter(slug="monsoon-protocol").first() or open_titles[1]
    ShowFeature.objects.update_or_create(event=lead, headline="This week’s big screen pick", defaults=dict(
        priority=10, starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=7), is_active=True))
    ShowFeature.objects.update_or_create(event=open_titles[0], headline="An ended feature (must not show)", defaults=dict(
        priority=99, starts_at=now - timedelta(days=10), ends_at=now - timedelta(days=1), is_active=True))
    reviews = _audience(cinemas)
    for e in Event.objects.all():
        recompute_rating(e.pk)
    log(f"showtime: {len(cinemas)} cinemas with real screen layouts and menus, {made} new showtimes (local time), "
        f"{len(open_titles)} Creative Commons titles, offers, feature, {reviews} attended-show reviews")


def seed_showtime_history(profile, log) -> None:
    """The test customer attended one show yesterday (so they can review it) and follows one upcoming title."""
    if Booking.objects.filter(customer=profile, show__event__slug="the-last-lighthouse", show__starts_at__lt=timezone.now()).exists():
        return
    cinema = Venue.objects.filter(kind=Venue.Kind.CINEMA, screens__isnull=False).distinct().order_by("name").first()
    event = Event.objects.filter(slug="the-last-lighthouse").first()
    if cinema is None or event is None:
        return
    today = timezone.localtime(timezone.now(), TZ).date()
    _past_booking(profile, event, cinema, cinema.screens.order_by("name").last(), local_dt(today - timedelta(days=1), 18, 45), ["F7", "F8"])
    coming = Event.objects.filter(status=Event.Status.COMING_SOON).order_by("title").first()
    log("showtime: test customer attended The Last Lighthouse yesterday (reviewable)" + (f" and can follow {coming.title}" if coming else ""))
