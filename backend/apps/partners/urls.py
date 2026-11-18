from django.urls import path

from apps.buzz import views as BuzzViews
from apps.orders import restaurant_views as rv
from apps.rides import driver_views as dv

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
    # Restaurant mode (apps.orders.restaurant): menu, kitchen operations, order history, offers, insights
    path("restaurant/menu", rv.MenuView.as_view(), name="partner-restaurant-menu"),
    path("restaurant/menu/categories", rv.MenuCategoriesView.as_view(), name="partner-restaurant-categories"),
    path("restaurant/menu/categories/order", rv.MenuCategoryOrderView.as_view(), name="partner-restaurant-categories-order"),
    path("restaurant/menu/categories/<uuid:pk>", rv.MenuCategoryView.as_view(), name="partner-restaurant-category"),
    path("restaurant/menu/items", rv.MenuItemsView.as_view(), name="partner-restaurant-items"),
    path("restaurant/menu/items/order", rv.MenuItemOrderView.as_view(), name="partner-restaurant-items-order"),
    path("restaurant/menu/items/<uuid:pk>", rv.MenuItemView.as_view(), name="partner-restaurant-item"),
    path("restaurant/operations", rv.OperationsView.as_view(), name="partner-restaurant-operations"),
    path("restaurant/orders", rv.OrdersView.as_view(), name="partner-restaurant-orders"),
    path("restaurant/kitchen", rv.KitchenView.as_view(), name="partner-restaurant-kitchen"),
    path("restaurant/offers", rv.OffersView.as_view(), name="partner-restaurant-offers"),
    path("restaurant/offers/<uuid:pk>/<slug:action>", rv.OfferActionView.as_view(), name="partner-restaurant-offer-action"),
    path("restaurant/insights", rv.InsightsView.as_view(), name="partner-restaurant-insights"),
    # Driver mode (apps.rides.driver): profile & vehicle, earnings, trip history, rate rider, safety
    path("driver/profile", dv.ProfileView.as_view(), name="partner-driver-profile"),
    path("driver/earnings", dv.EarningsView.as_view(), name="partner-driver-earnings"),
    path("driver/trips", dv.TripsView.as_view(), name="partner-driver-trips"),
    path("driver/trips/<uuid:pk>/rate-rider", dv.RateRiderView.as_view(), name="partner-driver-rate-rider"),
    path("driver/trips/<uuid:pk>/safety", dv.SafetyView.as_view(), name="partner-driver-safety"),
    # Click. Buzz posts (every partner type with a live listing)
    path("buzz", BuzzViews.PartnerBuzzView.as_view(), name="partner-buzz"),
    path("buzz/media", BuzzViews.PartnerBuzzMediaView.as_view(), name="partner-buzz-media"),
    path("buzz/media/<uuid:pk>", BuzzViews.PartnerBuzzMediaView.as_view(), name="partner-buzz-media-item"),
    path("buzz/community", BuzzViews.PartnerBuzzCommunityView.as_view(), name="partner-buzz-community"),
    path("buzz/<uuid:pk>", BuzzViews.PartnerBuzzPostView.as_view(), name="partner-buzz-post"),
    path("buzz/<uuid:pk>/<slug:action>", BuzzViews.PartnerBuzzActionView.as_view(), name="partner-buzz-action"),
    # Verification documents (every partner type)
    path("documents", views.DocumentsView.as_view(), name="partner-documents"),
    path("dev-login", views.DevPartnerLoginView.as_view(), name="partner-dev-login"),  # 404 unless DEBUG
]
