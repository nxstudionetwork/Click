"""Events routes. Public: /api/v1/eventhub/... ; customer: /api/v1/customer/eventhub/... ; partner: /api/v1/partner/eventhub/...
(/api/v1/events stays Click. Showtime's events API.)"""

from django.urls import path

from . import views

public = [
    path("registry", views.RegistryView.as_view(), name="eventhub-registry"),
    path("home", views.HomeView.as_view(), name="eventhub-home"),
    path("search", views.SearchView.as_view(), name="eventhub-search"),
    path("live", views.LiveEventsView.as_view(), name="eventhub-live"),
    path("providers", views.ProvidersView.as_view(), name="eventhub-providers"),
    path("providers/<uuid:pk>", views.ProviderView.as_view(), name="eventhub-provider"),
]

customer = [
    path("attachments", views.AttachmentView.as_view(), name="eventhub-attachments"),
    path("attachments/<uuid:pk>", views.AttachmentDetailView.as_view(), name="eventhub-attachment"),
    path("plans", views.PlansView.as_view(), name="eventhub-plans"),
    path("plans/<uuid:pk>", views.PlanDetailView.as_view(), name="eventhub-plan"),
    path("plans/<uuid:pk>/matches", views.PlanMatchesView.as_view(), name="eventhub-plan-matches"),
    path("plans/<uuid:pk>/enquiries", views.PlanEnquireView.as_view(), name="eventhub-plan-enquire"),
    path("plans/<uuid:pk>/checklist", views.ChecklistView.as_view(), name="eventhub-checklist"),
    path("plans/<uuid:pk>/checklist/<uuid:item>", views.ChecklistView.as_view(), name="eventhub-checklist-item"),
    path("enquiries/<uuid:pk>/<slug:action>", views.EnquiryActionView.as_view(), name="eventhub-enquiry-action"),
    path("estimate", views.EstimateView.as_view(), name="eventhub-estimate"),
    path("bookings", views.BookingsView.as_view(), name="eventhub-bookings"),
    path("bookings/<uuid:pk>", views.BookingDetailView.as_view(), name="eventhub-booking"),
    path("bookings/<uuid:pk>/<slug:action>", views.BookingActionView.as_view(), name="eventhub-booking-action"),
    path("favorites", views.FavoritesView.as_view(), name="eventhub-favorites"),
]

partner = [
    path("profile", views.PartnerProfileView.as_view(), name="eventhub-partner-profile"),
    path("dates", views.PartnerDatesView.as_view(), name="eventhub-partner-dates"),
    path("portfolio", views.PartnerPortfolioView.as_view(), name="eventhub-partner-portfolio"),
    path("portfolio/<uuid:pk>", views.PartnerPortfolioView.as_view(), name="eventhub-partner-portfolio-item"),
    path("enquiries/<uuid:pk>", views.PartnerEnquiryView.as_view(), name="eventhub-partner-enquiry"),
    path("enquiries/<uuid:pk>/<slug:action>", views.PartnerEnquiryView.as_view(), name="eventhub-partner-enquiry-action"),
]
