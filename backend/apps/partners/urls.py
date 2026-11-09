from django.urls import path

from . import views

urlpatterns = [
    path("categories", views.PartnerCatalogView.as_view(), name="partner-categories"),
    path("me", views.PartnerMeView.as_view(), name="partner-me"),
    path("onboarding/category", views.ChooseCategoryView.as_view(), name="partner-onboarding-category"),
    path("onboarding/profile", views.ProfileView.as_view(), name="partner-onboarding-profile"),
    path("onboarding/location", views.LocationView.as_view(), name="partner-onboarding-location"),
    path("onboarding/submit", views.SubmitView.as_view(), name="partner-onboarding-submit"),
    # Partner Home / operations
    path("home", views.HomeView.as_view(), name="partner-home"),
    path("availability", views.AvailabilityView.as_view(), name="partner-availability"),
    path("work", views.WorkView.as_view(), name="partner-work"),
    path("work/<slug:kind>/<uuid:pk>/<slug:action>", views.WorkActionView.as_view(), name="partner-work-action"),
    path("earnings", views.EarningsView.as_view(), name="partner-earnings"),
    path("notifications", views.NotificationListView.as_view(), name="partner-notifications"),
    path("notifications/read-all", views.NotificationReadView.as_view(), name="partner-notifications-read-all"),
    path("notifications/<uuid:pk>/read", views.NotificationReadView.as_view(), name="partner-notification-read"),
    path("dev-login", views.DevPartnerLoginView.as_view(), name="partner-dev-login"),  # 404 unless DEBUG
]
