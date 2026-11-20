"""
Click. Live: watch series episode by episode, films and live channels inside Click. (separate from Showtime, which
books cinema seats). Content comes from licensed partners / content providers; the media URL is whatever their
delivery network serves (MP4 or HLS). Click. stores what people watched and where they stopped.
"""

from django.db import models

from apps.core.models import BaseModel


class StreamTitle(BaseModel):
    class Kind(models.TextChoices):
        SERIES = "series", "Series"
        FILM = "film", "Film"
        SHOW = "show", "Show"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=170, unique=True)
    synopsis = models.TextField(blank=True)
    genres = models.CharField(max_length=160, blank=True, help_text="Comma-separated, e.g. 'Drama, Fantasy'.")
    language = models.CharField(max_length=60, default="English")
    maturity = models.CharField(max_length=8, default="U", help_text="CBFC-style rating: U, U/A 7+, U/A 13+, U/A 16+, A.")
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    poster_url = models.URLField(blank=True)
    backdrop_url = models.URLField(blank=True)
    credits = models.CharField(max_length=300, blank=True, help_text="Studio, licence and attribution shown to viewers.")
    accent = models.CharField(max_length=7, default="#e5294b", help_text="Colour for the title's artwork card.")
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-is_featured", "title"]

    def __str__(self) -> str:
        return self.title


class Season(BaseModel):
    title = models.ForeignKey(StreamTitle, on_delete=models.CASCADE, related_name="seasons")
    number = models.PositiveSmallIntegerField(default=1)
    name = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["number"]
        constraints = [models.UniqueConstraint(fields=["title", "number"], name="streaming_season_unique")]

    def __str__(self) -> str:
        return f"{self.title} S{self.number}"


class Episode(BaseModel):
    """A playable item: an episode of a series/show, or the film itself (season 1, episode 1)."""

    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="episodes")
    number = models.PositiveSmallIntegerField(default=1)
    name = models.CharField(max_length=160)
    synopsis = models.TextField(blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    video_url = models.URLField(max_length=500, help_text="MP4 or HLS (.m3u8) from the content partner's delivery network.")
    thumbnail_url = models.URLField(blank=True)
    released_at = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["season__number", "number"]
        constraints = [models.UniqueConstraint(fields=["season", "number"], name="streaming_episode_unique")]

    def __str__(self) -> str:
        return f"{self.season} E{self.number} {self.name}"


class LiveChannel(BaseModel):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=130, unique=True)
    description = models.CharField(max_length=300, blank=True)
    stream_url = models.URLField(max_length=500, help_text="HLS (.m3u8) live stream.")
    category = models.CharField(max_length=60, blank=True)
    now_playing = models.CharField(max_length=160, blank=True)
    accent = models.CharField(max_length=7, default="#2f3cff")
    is_live = models.BooleanField(default=True, help_text="Off when the channel isn't broadcasting.")
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "name"]

    def __str__(self) -> str:
        return self.name


class WatchProgress(BaseModel):
    customer = models.ForeignKey("customers.CustomerProfile", on_delete=models.CASCADE, related_name="watch_progress")
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE, related_name="progress")
    position_seconds = models.PositiveIntegerField(default=0)
    duration_seconds = models.PositiveIntegerField(default=0)
    finished = models.BooleanField(default=False)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [models.UniqueConstraint(fields=["customer", "episode"], name="streaming_progress_once")]


class WatchlistItem(BaseModel):
    customer = models.ForeignKey("customers.CustomerProfile", on_delete=models.CASCADE, related_name="watchlist")
    title = models.ForeignKey(StreamTitle, on_delete=models.CASCADE, related_name="watchlisted")

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["customer", "title"], name="streaming_watchlist_once")]
