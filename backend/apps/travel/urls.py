"""Travel routes. Public: /api/v1/travel/... ; customer: /api/v1/customer/travel/..."""

from django.urls import path

from . import views

public = [
    path("home", views.HomeView.as_view(), name="travel-home"),
    path("places", views.PlacesView.as_view(), name="travel-places"),
    path("search", views.SearchView.as_view(), name="travel-search"),
    path("dates", views.DatesView.as_view(), name="travel-dates"),
    path("options/<uuid:journey>/<uuid:a>/<uuid:b>", views.OptionView.as_view(), name="travel-option"),
]

customer = [
    path("review", views.PrepareView.as_view(), name="travel-prepare"),
    path("next", views.NextJourneyView.as_view(), name="travel-next"),
    path("bookings", views.BookingsView.as_view(), name="travel-bookings"),
    path("bookings/<uuid:pk>", views.BookingDetailView.as_view(), name="travel-booking"),
    path("bookings/<uuid:pk>/ticket", views.TicketView.as_view(), name="travel-ticket"),
    path("bookings/<uuid:pk>/<slug:action>", views.BookingActionView.as_view(), name="travel-booking-action"),
    path("recent", views.RecentView.as_view(), name="travel-recent"),
    path("routes", views.SavedRoutesView.as_view(), name="travel-routes"),
    path("travellers", views.TravellersView.as_view(), name="travel-travellers"),
    path("travellers/<uuid:pk>", views.TravellerDetailView.as_view(), name="travel-traveller"),
    path("alerts", views.AlertsView.as_view(), name="travel-alerts"),
    path("alerts/<uuid:pk>", views.AlertDetailView.as_view(), name="travel-alert"),
    path("preferences", views.PreferencesView.as_view(), name="travel-preferences"),
]
