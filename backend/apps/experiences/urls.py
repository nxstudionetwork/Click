"""Bookings routes. Public: /api/v1/experiences/... ; customer: /api/v1/customer/experiences/... and
/api/v1/customer/reservations (every booking across Click.) ; partner: /api/v1/partner/experiences/..."""

from django.urls import path

from . import views

public = [
    path("home", views.HomeView.as_view(), name="experiences-home"),
    path("search", views.SearchView.as_view(), name="experiences-search"),
    path("attractions/<slug:slug>", views.AttractionView.as_view(), name="experiences-attraction"),
    path("offerings/<uuid:pk>/availability", views.AvailabilityView.as_view(), name="experiences-availability"),
]

customer = [
    path("review", views.PrepareView.as_view(), name="experiences-prepare"),
    path("bookings", views.BookingsView.as_view(), name="experiences-bookings"),
    path("bookings/<uuid:pk>", views.BookingDetailView.as_view(), name="experiences-booking"),
    path("bookings/<uuid:pk>/<slug:action>", views.BookingActionView.as_view(), name="experiences-booking-action"),
    path("saved", views.SavedView.as_view(), name="experiences-saved"),
]

partner = [
    path("check-in", views.PartnerCheckInView.as_view(), name="experiences-partner-check-in"),
]
