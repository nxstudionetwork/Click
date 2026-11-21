from django.urls import path

from . import views

public = [
    path("live/home", views.HomeView.as_view(), name="live-home"),
    path("live/search", views.SearchView.as_view(), name="live-search"),
    path("live/titles/<slug:slug>", views.TitleView.as_view(), name="live-title"),
    path("live/play/<uuid:pk>", views.PlayView.as_view(), name="live-play"),
    path("live/channels/<slug:slug>", views.ChannelView.as_view(), name="live-channel"),
]
customer = [
    path("live/progress", views.ProgressView.as_view(), name="live-progress"),
    path("live/watchlist/<slug:slug>", views.WatchlistView.as_view(), name="live-watchlist"),
]
