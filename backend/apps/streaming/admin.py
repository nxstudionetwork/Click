from django.contrib import admin

from .models import Episode, LiveChannel, Season, StreamTitle


class SeasonInline(admin.TabularInline):
    model = Season
    extra = 0


class EpisodeInline(admin.TabularInline):
    model = Episode
    extra = 0
    fields = ["number", "name", "duration_seconds", "video_url", "is_active"]


@admin.register(StreamTitle)
class StreamTitleAdmin(admin.ModelAdmin):
    list_display = ["title", "kind", "language", "maturity", "is_featured", "is_active"]
    list_filter = ["kind", "is_active", "language"]
    search_fields = ["title", "genres"]
    prepopulated_fields = {"slug": ("title",)}
    inlines = [SeasonInline]


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ["title", "number", "name"]
    inlines = [EpisodeInline]


@admin.register(LiveChannel)
class LiveChannelAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "now_playing", "is_live", "position"]
    list_editable = ["is_live", "position"]
