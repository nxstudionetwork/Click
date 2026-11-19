from django.urls import path

from . import views

urlpatterns = [
    path("geo/search", views.SearchView.as_view(), name="geo-search"),
    path("geo/reverse", views.ReverseView.as_view(), name="geo-reverse"),
    path("geo/route", views.RouteView.as_view(), name="geo-route"),
]
