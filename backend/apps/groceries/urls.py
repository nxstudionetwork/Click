"""Groceries routes. Public: /api/v1/groceries/... ; customer: /api/v1/customer/groceries/... ; partner: /api/v1/partner/grocery/..."""

from django.urls import path

from . import partner, views

public = [
    path("home", views.HomeView.as_view(), name="groceries-home"),
    path("search", views.SearchView.as_view(), name="groceries-search"),
    path("suggest", views.SuggestView.as_view(), name="groceries-suggest"),
    path("stores/<slug:slug>", views.StoreView.as_view(), name="groceries-store"),
    path("stores/<slug:slug>/products", views.StoreProductsView.as_view(), name="groceries-store-products"),
    path("products/<uuid:pk>", views.ProductView.as_view(), name="groceries-product"),
]

customer = [
    path("basket", views.BasketView.as_view(), name="groceries-basket"),
    path("basket/quote", views.QuoteView.as_view(), name="groceries-quote"),
    path("basket/acknowledge-prices", views.AcknowledgePricesView.as_view(), name="groceries-ack-prices"),
    path("checkout", views.CheckoutView.as_view(), name="groceries-checkout"),
    path("buy-again", views.BuyAgainView.as_view(), name="groceries-buy-again"),
    path("orders/<uuid:pk>/reorder", views.ReorderView.as_view(), name="groceries-reorder"),
    path("alerts", views.AlertsView.as_view(), name="groceries-alerts"),
    path("recent-searches", views.RecentSearchesView.as_view(), name="groceries-recent"),
    path("lists", views.ListsView.as_view(), name="groceries-lists"),
    path("lists/<uuid:pk>", views.ListDetailView.as_view(), name="groceries-list"),
    path("lists/<uuid:pk>/items", views.ListItemsView.as_view(), name="groceries-list-items"),
    path("lists/<uuid:pk>/items/<uuid:item_pk>", views.ListItemDetailView.as_view(), name="groceries-list-item"),
    path("lists/<uuid:pk>/find", views.FindEverythingView.as_view(), name="groceries-list-find"),
]

partner_urls = [
    path("listings", partner.PartnerListingsView.as_view(), name="partner-grocery-listings"),
    path("listings/<uuid:pk>", partner.PartnerListingDetailView.as_view(), name="partner-grocery-listing"),
]
