"""Services routes. Public: /api/v1/services/... ; customer: /api/v1/customer/services/... ; partner: /api/v1/partner/services/..."""

from django.urls import path

from . import views

public = [
    path("home", views.HomeView.as_view(), name="services-home"),
    path("search", views.SearchView.as_view(), name="services-search"),
    path("categories/<slug:slug>", views.CategoryView.as_view(), name="services-category"),
    path("providers/<uuid:pk>", views.ProviderView.as_view(), name="services-provider"),
    path("providers/<uuid:pk>/slots", views.SlotsView.as_view(), name="services-provider-slots"),
]

customer = [
    path("attachments", views.AttachmentView.as_view(), name="services-attachments"),
    path("attachments/<uuid:pk>", views.AttachmentDetailView.as_view(), name="services-attachment"),
    path("estimate", views.EstimateView.as_view(), name="services-estimate"),
    path("bookings", views.BookingListCreateView.as_view(), name="services-bookings"),
    path("bookings/<uuid:pk>", views.BookingDetailView.as_view(), name="services-booking"),
    path("bookings/<uuid:pk>/rebook", views.RebookView.as_view(), name="services-rebook"),
    path("bookings/<uuid:pk>/<slug:action>", views.BookingActionView.as_view(), name="services-booking-action"),
    path("needs", views.NeedsView.as_view(), name="services-needs"),
    path("favorites", views.FavoritesView.as_view(), name="services-favorites"),
]

partner = [
    path("profile", views.ProProfileView.as_view(), name="services-pro-profile"),
    path("portfolio", views.ProPortfolioView.as_view(), name="services-pro-portfolio"),
    path("portfolio/<uuid:pk>", views.ProPortfolioView.as_view(), name="services-pro-portfolio-item"),
    path("<slug:what>", views.ProHoursView.as_view(), name="services-pro-settings"),
]
