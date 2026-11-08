from django.urls import path

from . import views

urlpatterns = [
    path("categories", views.PartnerCatalogView.as_view(), name="partner-categories"),
    path("me", views.PartnerMeView.as_view(), name="partner-me"),
    path("onboarding/category", views.ChooseCategoryView.as_view(), name="partner-onboarding-category"),
    path("onboarding/profile", views.ProfileView.as_view(), name="partner-onboarding-profile"),
    path("onboarding/location", views.LocationView.as_view(), name="partner-onboarding-location"),
    path("onboarding/submit", views.SubmitView.as_view(), name="partner-onboarding-submit"),
]
