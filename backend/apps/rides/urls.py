from django.urls import path

from . import views

customer_urlpatterns = [
    path("rides/places", views.PlacesView.as_view(), name="ride-places"),
    path("rides/quote", views.QuoteView.as_view(), name="ride-quote"),
    path("rides", views.RideListCreateView.as_view(), name="rides"),
    path("rides/<uuid:pk>", views.RideDetailView.as_view(), name="ride-detail"),
    path("rides/<uuid:pk>/cancel", views.RideCancelView.as_view(), name="ride-cancel"),
    path("rides/<uuid:pk>/rating", views.RideRateView.as_view(), name="ride-rating"),
    path("rides/<uuid:pk>/safety", views.RideSafetyView.as_view(), name="ride-safety"),
]

partner_urlpatterns = [
    path("rides/offers", views.DriverOffersView.as_view(), name="driver-ride-offers"),
    path("rides/<uuid:pk>/accept", views.DriverAcceptView.as_view(), name="driver-ride-accept"),
    path("rides/<uuid:pk>/status", views.DriverStatusView.as_view(), name="driver-ride-status"),
    path("driver/location", views.DriverLocationView.as_view(), name="driver-location"),
]
