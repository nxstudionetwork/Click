"""
One shared API for all Click products, versioned under /api/v1/.

  public      /api/v1/stores...               discovery (no auth)
  auth        /api/v1/auth/..., /api/v1/me    shared identity
  customer    /api/v1/customer/...            Customer App (IsCustomer + ownership)
  partner     /api/v1/partner/...             Phase 5
  business os /api/v1/os/...                  Phase 6
"""

from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from apps.ai.views import CustomerAssistantView
from apps.carts import views as cart_views
from apps.catalog.search import SearchView
from apps.catalog.views import ProductDetailView, StoreMenuView
from apps.notifications import views as notification_views
from apps.rewards.views import RewardsView
from apps.support import views as support_views
from apps.wishlists import views as wishlist_views
from apps.core.views import health
from apps.customers.views import AddressViewSet
from apps.orders import views as order_views
from apps.stores import views as store_views

customer_router = SimpleRouter(trailing_slash=False)
customer_router.register("addresses", AddressViewSet, basename="address")

customer_urls = [
    path("cart", cart_views.CartView.as_view(), name="cart"),
    path("cart/items", cart_views.CartItemsView.as_view(), name="cart-items"),
    path("cart/items/<uuid:item_id>", cart_views.CartItemDetailView.as_view(), name="cart-item"),
    path("orders", order_views.OrderListCreateView.as_view(), name="orders"),
    path("orders/<uuid:pk>", order_views.OrderDetailView.as_view(), name="order-detail"),
    path("orders/<uuid:pk>/cancel", order_views.OrderCancelView.as_view(), name="order-cancel"),
    path("orders/<uuid:pk>/reorder", order_views.OrderReorderView.as_view(), name="order-reorder"),
    path("wishlist", wishlist_views.WishlistView.as_view(), name="wishlist"),
    path("wishlist/<uuid:pk>", wishlist_views.WishlistItemView.as_view(), name="wishlist-item"),
    path("notifications", notification_views.NotificationListView.as_view(), name="notifications"),
    path("notifications/summary", notification_views.NotificationSummaryView.as_view(), name="notifications-summary"),
    path("notifications/read-all", notification_views.NotificationReadAllView.as_view(), name="notifications-read-all"),
    path("notifications/<uuid:pk>/read", notification_views.NotificationReadView.as_view(), name="notification-read"),
    path("rewards", RewardsView.as_view(), name="rewards"),
    path("support/tickets", support_views.SupportTicketListCreateView.as_view(), name="support-tickets"),
    path("support/tickets/<uuid:pk>", support_views.SupportTicketDetailView.as_view(), name="support-ticket"),
    path("assistant/messages", CustomerAssistantView.as_view(), name="assistant"),
    *customer_router.urls,
]

api_v1 = [
    path("", include("apps.users.urls")),
    path("stores", store_views.StoreListView.as_view(), name="store-list"),
    path("stores/<slug:slug>", store_views.StoreDetailView.as_view(), name="store-detail"),
    path("stores/<slug:slug>/menu", StoreMenuView.as_view(), name="store-menu"),
    path("products/<uuid:pk>", ProductDetailView.as_view(), name="product-detail"),
    path("search", SearchView.as_view(), name="search"),
    path("offers", store_views.OfferListView.as_view(), name="offers"),
    path("store-categories", store_views.StoreCategoryListView.as_view(), name="store-categories"),
    path("customer/", include(customer_urls)),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health", health, name="health"),
    path("api/v1/", include(api_v1)),
]
