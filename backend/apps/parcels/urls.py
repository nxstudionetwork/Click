"""Parcel routes. Public: /api/v1/parcels/... ; customer: /api/v1/customer/parcels/..."""

from django.urls import path

from . import views

public = [
    path("options", views.OptionsView.as_view(), name="parcel-options"),
    path("shared/<str:token>", views.SharedTrackingView.as_view(), name="parcel-shared"),
]

customer = [
    path("quote", views.QuoteView.as_view(), name="parcel-quote"),
    path("track", views.ParcelTrackView.as_view(), name="parcel-track"),
    path("recipients", views.RecipientListCreateView.as_view(), name="parcel-recipients"),
    path("recipients/<uuid:pk>", views.RecipientDetailView.as_view(), name="parcel-recipient"),
    path("<uuid:pk>", views.ParcelDetailView.as_view(), name="parcel-detail"),
    path("<uuid:pk>/cancel", views.ParcelCancelView.as_view(), name="parcel-cancel"),
    path("<uuid:pk>/repeat", views.ParcelRepeatView.as_view(), name="parcel-repeat"),
    path("<uuid:pk>/share", views.ParcelShareView.as_view(), name="parcel-share"),
]
