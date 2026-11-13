"""Hotels routes. Public: /api/v1/hotels/... ; customer: /api/v1/customer/hotels/... ; partner: /api/v1/partner/hotels/..."""

from django.urls import path

from . import views

public = [
    path("home", views.HomeView.as_view(), name="hotels-home"),
    path("destinations", views.DestinationsView.as_view(), name="hotels-destinations"),
    path("search", views.SearchView.as_view(), name="hotels-search"),
    path("compare", views.CompareView.as_view(), name="hotels-compare"),
    path("properties/<uuid:pk>", views.PropertyView.as_view(), name="hotels-property"),
    path("properties/<uuid:pk>/reviews", views.ReviewsView.as_view(), name="hotels-reviews"),
]

customer = [
    path("review", views.PrepareView.as_view(), name="hotels-prepare"),
    path("bookings", views.BookingsView.as_view(), name="hotels-bookings"),
    path("bookings/<uuid:pk>", views.BookingDetailView.as_view(), name="hotels-booking"),
    path("bookings/<uuid:pk>/<slug:action>", views.BookingActionView.as_view(), name="hotels-booking-action"),
    path("saved", views.SavedView.as_view(), name="hotels-saved"),
]

partner = [
    path("inventory", views.PartnerInventoryView.as_view(), name="hotels-partner-inventory"),
]
