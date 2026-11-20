"""
DEVELOPMENT MOCK DATA for Click. Live. Real, openly licensed films from the Blender Foundation (served by the
Internet Archive) and a public HLS *test* stream, so playback, resume and live viewing can be tested end to end.
Licences are shown on each title. Production content comes from licensed partners.
"""

from datetime import date

from apps.streaming.models import Episode, LiveChannel, Season, StreamTitle

ARCHIVE = "https://archive.org/download"
TITLES = [
    {"slug": "open-movie-shorts", "kind": "series", "title": "Open Movie Shorts", "year": 2008, "accent": "#7c3aed", "featured": True,
     "genres": "Animation, Fantasy, Comedy", "maturity": "U",
     "synopsis": "An anthology of landmark open movies made by the Blender community: a surreal machine-world journey and a gentle "
                 "giant's revenge on three bullies.",
     "credits": "Blender Foundation · Elephants Dream (CC BY 2.5), Big Buck Bunny (CC BY 3.0) · via the Internet Archive",
     "episodes": [
         (1, "Elephants Dream", "Emo and Proog wander an endless machine that seems to have a mind of its own.", 654,
          f"{ARCHIVE}/ElephantsDream/ed_1024_512kb.mp4", date(2006, 3, 24)),
         (2, "Big Buck Bunny", "A big-hearted rabbit's peaceful day is spoiled by three rodents. He has a plan.", 596,
          f"{ARCHIVE}/BigBuckBunny_124/Content/big_buck_bunny_720p_surround.mp4", date(2008, 5, 30)),
     ]},
    {"slug": "sintel", "kind": "film", "title": "Sintel", "year": 2010, "accent": "#b45309",
     "genres": "Animation, Fantasy, Adventure", "maturity": "U/A 7+",
     "synopsis": "A lonely young woman searches the world for the baby dragon she once rescued, and finds more than she bargained for.",
     "credits": "Blender Foundation · Sintel (CC BY 3.0) · via the Internet Archive",
     "episodes": [(1, "Sintel", "The full film.", 888, f"{ARCHIVE}/Sintel/sintel-2048-surround_512kb.mp4", date(2010, 9, 27))]},
    {"slug": "tears-of-steel", "kind": "film", "title": "Tears of Steel", "year": 2012, "accent": "#0e7490",
     "genres": "Science fiction, Action", "maturity": "U/A 13+",
     "synopsis": "In a future Amsterdam, a group of scientists try to save the world by reliving a painful breakup.",
     "credits": "Blender Foundation · Tears of Steel (CC BY 3.0) · via the Internet Archive",
     "episodes": [(1, "Tears of Steel", "The full film.", 734, f"{ARCHIVE}/Tears-of-Steel/tears_of_steel_720p.mp4", date(2012, 9, 26))]},
]
CHANNELS = [
    {"slug": "click-test-live", "name": "Click. Test Channel", "category": "Test stream", "accent": "#e5294b", "position": 0,
     "description": "A public HLS test stream used to check live playback in development.", "now_playing": "Test loop",
     "stream_url": "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"},
]


def seed_streaming(log) -> None:
    for t in TITLES:
        title, _ = StreamTitle.objects.update_or_create(slug=t["slug"], defaults={
            "kind": t["kind"], "title": t["title"], "year": t["year"], "accent": t["accent"], "genres": t["genres"], "maturity": t["maturity"],
            "synopsis": t["synopsis"], "credits": t["credits"], "is_featured": t.get("featured", False), "is_active": True})
        season, _ = Season.objects.get_or_create(title=title, number=1)
        for number, name, synopsis, seconds, url, released in t["episodes"]:
            Episode.objects.update_or_create(season=season, number=number, defaults={
                "name": name, "synopsis": synopsis, "duration_seconds": seconds, "video_url": url, "released_at": released, "is_active": True})
    for c in CHANNELS:
        LiveChannel.objects.update_or_create(slug=c["slug"], defaults={k: v for k, v in c.items() if k != "slug"})
    log(f"Click. Live: {len(TITLES)} titles (open movies, CC BY) and {len(CHANNELS)} test channel")
