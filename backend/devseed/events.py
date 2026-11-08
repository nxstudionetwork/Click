"""DEVELOPMENT MOCK DATA: fictional venues, movies, live events and their upcoming shows."""

from datetime import datetime, time, timedelta
from decimal import Decimal as D

from django.utils import timezone
from django.utils.text import slugify

from apps.bookings.models import Event, Show, Venue

VENUES = [
    ("Click Cineplex Indiranagar", "cinema", "Indiranagar", "100 Feet Road"),
    ("Starline Cinemas Koramangala", "cinema", "Koramangala", "80 Feet Road"),
    ("Skydeck Arena", "arena", "MG Road", "Church Street"),
    ("Rangmanch Theatre House", "theatre", "Basavanagudi", "Bull Temple Road"),
    ("The Velvet Room", "club", "Indiranagar", "12th Main"),
    ("Lakeside Open Grounds", "arena", "Hebbal", "Outer Ring Road"),
]

# title, status, genres, languages, cert, minutes, rating, votes, tagline, cast
MOVIES = [
    ("Monsoon Protocol", "now_showing", "Thriller, Action", "Hindi, English", "UA", 142, "4.4", 18200, "One city. One storm. Twelve hours.", "Aarav Sen, Meera Kulkarni"),
    ("The Last Lighthouse", "now_showing", "Drama", "English", "U", 118, "4.6", 9400, "Some lights never go out.", "Nora Ellis, Dev Malhotra"),
    ("Chai & Chaos", "now_showing", "Comedy, Family", "Hindi", "U", 126, "4.1", 12700, "Two cafes. One street. Zero peace.", "Ritika Rao, Kabir Shah"),
    ("Orbit 9", "now_showing", "Sci-Fi, Adventure", "English, Tamil", "UA", 155, "4.3", 21500, "Beyond the edge of the map.", "Ishaan Varma, Lena Park"),
    ("Paper Tigers", "now_showing", "Action, Comedy", "Telugu, Hindi", "UA", 148, "3.9", 6100, "Fake heroes. Real trouble.", "Vikram Reddy, Sana Iqbal"),
    ("Whispering Pines", "now_showing", "Horror", "English", "A", 104, "3.6", 3300, "Don’t answer the door.", "Mara Quinn, Theo Blake"),
    ("Gully Cricket League", "now_showing", "Sports, Drama", "Hindi", "U", 137, "4.5", 15800, "Every street has a champion.", "Arjun Patil, Diya Menon"),
    ("A Very Long Title About Love, Loss and the Last Train to Mysore", "now_showing", "Romance, Drama", "Kannada", "U", 129, "4.2", 2200, "Some journeys end where they began.", "Anika Hegde, Rohan Gowda"),
    ("Neon Monks", "now_showing", "Animation, Family", "English, Hindi", "U", 96, "4.7", 8800, "Peace was never this loud.", "Voice cast"),
    ("The Accountant’s Wife", "now_showing", "Mystery, Thriller", "Malayalam", "UA", 132, "4.4", 5400, "She knew the numbers didn’t add up.", "Fahad Nair, Parvathi Iyer"),
    ("Rocket Biryani", "now_showing", "Comedy", "Tamil", "U", 121, "3.8", 4100, "A recipe for disaster.", "Karthik Raja, Nila Bose"),
    ("Silent Shore", "now_showing", "Drama", "Bengali, English", "UA", 113, "4.0", 1900, "The sea remembers.", "Ritwik Das, Tara Sen"),
    ("Iron Monsoon II", "now_showing", "Action", "Hindi", "UA", 161, "3.4", 27400, "The storm returns.", "Aarav Sen, Kriti Joshi"),
    ("Small Town Satellites", "now_showing", "Sci-Fi, Comedy", "English", "U", 108, "4.1", 2600, "Signals from Hosur.", "Neel Kapoor, Ivy Fernandes"),
    ("Grandma’s Secret Masala", "now_showing", "Family, Comedy", "Gujarati, Hindi", "U", 117, "4.6", 3900, "Some recipes are worth fighting for.", "Hema Shah, Jay Patel"),
    ("Kaveri Nights", "coming_soon", "Romance, Musical", "Kannada, Hindi", "U", 134, "0.0", 0, "Coming to cinemas soon.", "Anika Hegde, Rohan Gowda"),
    ("Deep Blue Dharavi", "coming_soon", "Drama", "Hindi, Marathi", "UA", 140, "0.0", 0, "Dreams don’t need permission.", "Sameer Kale, Juhi Rane"),
    ("Starlight Express to Ooty", "coming_soon", "Adventure, Family", "Tamil, English", "U", 119, "0.0", 0, "All aboard.", "Meena Raj, Arun Pillai"),
    ("Codebreakers", "coming_soon", "Thriller", "English", "UA", 127, "0.0", 0, "Every system has a weakness.", "Leah Thomas, Raghav Iyer"),
    ("The Monsoon Wedding Planner", "coming_soon", "Romance, Comedy", "Hindi, Punjabi", "U", 131, "0.0", 0, "Love, logistics and lots of rain.", "Simran Gill, Kunal Ahuja"),
]

# title, status, genres, language, cert, minutes, rating, votes, tagline, performers, venue index, base price, premium price
LIVE_EVENTS = [
    ("Indie Sundown Live", "now_showing", "Music, Live", "English", "A", 180, "4.7", 860, "Five indie bands. One rooftop.", "The Paper Boats, Lowtide", 2, "999", "1999"),
    ("Stand-up Saturdays: Office Hours", "now_showing", "Comedy", "English, Hindi", "A", 90, "4.5", 1240, "Laugh about your manager. Responsibly.", "Rhea Sharma, Tanmay K", 4, "499", "899"),
    ("Carnatic Under the Stars", "now_showing", "Music, Classical", "Tamil, Kannada", "U", 150, "4.9", 410, "An evening of ragas by the lake.", "Vidushi Lakshmi R", 5, "599", "1499"),
    ("Hamlet, Reimagined", "now_showing", "Theatre, Drama", "English", "UA", 135, "4.6", 520, "To be, in Bengaluru.", "Rangmanch Repertory", 3, "699", "1299"),
    ("Bollywood Retro Night", "now_showing", "Music, Party", "Hindi", "A", 240, "4.3", 980, "70s, 80s and 90s. All night.", "DJ Neha & The Groove Unit", 4, "799", "1499"),
    ("Kids Science Carnival", "now_showing", "Kids, Workshop", "English, Kannada", "U", 180, "4.8", 300, "Explode volcanoes (safely).", "Curious Minds Collective", 5, "399", "699"),
    ("Jazz at the Velvet Room", "now_showing", "Music, Jazz", "English", "A", 120, "4.6", 640, "Smoky notes, late nights.", "The Bangalore Swing Trio", 4, "899", "1599"),
    ("Pottery Workshop: First Wheel", "now_showing", "Workshop, Art", "English", "U", 150, "4.7", 120, "Get your hands dirty.", "Clay & Co. Studio", 3, "1499", "1999"),
    ("Football Night: Big Screen Derby", "now_showing", "Sports, Screening", "English", "U", 150, "4.2", 2100, "Every goal on a 40-foot screen.", "Live screening", 2, "299", "599"),
    ("Sufi Evenings", "now_showing", "Music, Sufi", "Hindi, Urdu", "U", 120, "4.8", 760, "Music for the soul.", "Noor Ensemble", 3, "699", "1199"),
    ("Startup Pitch Night", "now_showing", "Business, Talk", "English", "U", 150, "4.1", 230, "Ten founders. Five minutes each.", "Founders Circle BLR", 4, "199", "499"),
    ("Kannada Folk Festival", "now_showing", "Music, Folk", "Kannada", "U", 240, "4.7", 1800, "Yakshagana, dollu kunitha and more.", "Janapada Troupe", 5, "299", "799"),
    ("Magic & Mentalism", "now_showing", "Magic, Family", "English, Hindi", "U", 100, "4.4", 340, "You won’t believe your eyes.", "The Great Varun", 3, "599", "999"),
    ("Electronic Sunrise", "now_showing", "Music, Electronic", "English", "A", 300, "4.0", 1500, "Dance till dawn by the lake.", "Kosmic Kid, Arya B", 5, "1199", "2499"),
    ("Poetry Open Mic", "now_showing", "Poetry, Open Mic", "English, Hindi", "U", 120, "4.5", 180, "Bring your words.", "Open to all", 4, "149", "299"),
    ("Theatre for Tiny Humans", "now_showing", "Kids, Theatre", "English", "U", 60, "4.9", 260, "A puppet show for ages 3–8.", "Little Lantern Puppets", 3, "349", "549"),
    ("Food Trucks & Film Night", "now_showing", "Food, Screening", "English", "U", 210, "4.3", 690, "Classic films and 20 food trucks.", "Click Community", 5, "249", "499"),
    ("Esports Showdown Finals", "now_showing", "Gaming, Sports", "English", "U", 240, "4.2", 870, "Who takes the city crown?", "City Gaming League", 2, "399", "899"),
    ("New Year’s Eve Gala", "coming_soon", "Party, Music", "English, Hindi", "A", 300, "0.0", 0, "Ring it in with Click.", "Lineup to be announced", 2, "2499", "4999"),
    ("Spring Literature Festival", "coming_soon", "Books, Talk", "English, Kannada", "U", 480, "0.0", 0, "Three days of stories.", "Authors to be announced", 3, "0", "499"),
]


def _ensure_show(event, venue, starts, **kw):
    Show.objects.get_or_create(event=event, venue=venue, starts_at=starts, defaults=kw)


def seed_events(log) -> None:
    venues = []
    for name, kind, locality, address in VENUES:
        v, _ = Venue.objects.update_or_create(slug=slugify(name), defaults=dict(name=name, kind=kind, city="Bengaluru", locality=locality, address=address))
        venues.append(v)

    tz = timezone.get_current_timezone()
    today = timezone.localdate()
    soon = timezone.now() + timedelta(minutes=45)

    def upsert(title, kind, status, genres, langs, cert, minutes, rating, votes, tagline, cast):
        event, _ = Event.objects.update_or_create(slug=slugify(title)[:170], defaults=dict(
            title=title, kind=kind, status=status, genres=genres, languages=langs, certification=cert, duration_minutes=minutes,
            rating_average=D(rating), rating_count=votes, tagline=tagline, cast=cast,
            description=f"{tagline} A {genres.lower()} {'film' if kind == 'movie' else 'event'} in {langs}. (Development mock data.)",
            release_date=today + timedelta(days=14 + len(title) % 30) if status == "coming_soon" else today - timedelta(days=len(title) % 25),
        ))
        return event

    shows = 0
    for idx, (title, status, genres, langs, cert, minutes, rating, votes, tagline, cast) in enumerate(MOVIES):
        event = upsert(title, "movie", status, genres, langs, cert, minutes, rating, votes, tagline, cast)
        if status != "now_showing":
            continue
        lang = langs.split(",")[0].strip()
        for day in range(3):
            for vi, venue in enumerate(venues[:2]):
                for slot, hour in enumerate((10, 13, 16, 19, 22)):
                    if (idx + slot + vi) % 2:  # each movie gets a different mix of showtimes
                        continue
                    starts = datetime.combine(today + timedelta(days=day), time(hour, 15 * vi + 5 * (idx % 3)), tz)
                    if starts <= soon:
                        continue
                    _ensure_show(event, venue, starts, language=lang, format="IMAX" if hour == 19 and vi == 0 else ("3D" if idx % 5 == 0 else "2D"),
                                 screen=f"Screen {1 + (idx + slot) % 6}", rows=10, seats_per_row=14, premium_rows=3,
                                 price=D("220" if vi else "250"), premium_price=D("380" if vi else "420"))
                    shows += 1

    for title, status, genres, lang, cert, minutes, rating, votes, tagline, cast, vidx, price, premium in LIVE_EVENTS:
        event = upsert(title, "event", status, genres, lang, cert, minutes, rating, votes, tagline, cast)
        if status != "now_showing":
            continue
        for day in (1, 2):
            starts = datetime.combine(today + timedelta(days=day), time(18 + len(title) % 3, 30), tz)
            _ensure_show(event, venues[vidx], starts, language=lang.split(",")[0], format="Live", rows=8, seats_per_row=16, premium_rows=2,
                         price=D(price), premium_price=D(premium))
            shows += 1
    log(f"events: {len(MOVIES)} movies, {len(LIVE_EVENTS)} live events, {len(VENUES)} venues; upcoming shows ensured ({shows} slots)")
