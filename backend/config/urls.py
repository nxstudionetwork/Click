"""
One shared API for all Click products, versioned under /api/v1/.

  public      /api/v1/stores...               discovery (no auth)
  auth        /api/v1/auth/..., /api/v1/me    shared identity
  bookings    /api/v1/events, /api/v1/shows   movies & live events (public)
  customer    /api/v1/customer/...            Customer App (IsCustomer + ownership)
  partner     /api/v1/partner/...             Click Partner App (resolved from request.user)
  business os /api/v1/os/...                  Phase 6
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from apps.ai.views import AssistantCapabilitiesView, AssistantTranscribeView, CustomerAssistantView
from apps.bookings import views as booking_views
from apps.buzz.views import BuzzFeedView
from apps.shop.urls import customer_urls as shop_customer_urls, public_urls as shop_public_urls
from apps.groceries import urls as grocery_urls
from apps.parcels import urls as parcel_urls
from apps.professionals import urls as services_urls
from apps.rides.urls import customer_urlpatterns as ride_customer_urls, partner_urlpatterns as ride_partner_urls
from apps.wallet.views import WalletView
from apps.carts import views as cart_views
from apps.catalog.search import SearchView
from apps.catalog.views import ProductDetailView, StoreMenuView
from apps.notifications import views as notification_views
from apps.rewards.views import RewardsView
from apps.support import views as support_views
from apps.wishlists import views as wishlist_views
from apps.core.views import health
from apps.customers.views import AddressViewSet, ProfileSummaryView
from apps.orders import views as order_views
from apps.stores import views as store_views

customer_router = SimpleRouter(trailing_slash=False)
customer_router.register("addresses", AddressViewSet, basename="address")

customer_urls = [
    path("groceries/", include(grocery_urls.customer)),
    path("parcels", parcel_urls.views.ParcelListCreateView.as_view(), name="parcels"),
    path("parcels/", include(parcel_urls.customer)),
    path("services/", include(services_urls.customer)),
    path("profile/summary", ProfileSummaryView.as_view(), name="profile-summary"),
    *ride_customer_urls,
    *shop_customer_urls,
    path("recommendations/stores", store_views.RecommendedStoresView.as_view(), name="recommended-stores"),
    path("cart", cart_views.CartView.as_view(), name="cart"),
    path("cart/items", cart_views.CartItemsView.as_view(), name="cart-items"),
    path("cart/offer", cart_views.CartOfferView.as_view(), name="cart-offer"),
    path("cart/items/<uuid:item_id>", cart_views.CartItemDetailView.as_view(), name="cart-item"),
    path("orders", order_views.OrderListCreateView.as_view(), name="orders"),
    path("orders/<uuid:pk>", order_views.OrderDetailView.as_view(), name="order-detail"),
    path("orders/<uuid:pk>/cancel", order_views.OrderCancelView.as_view(), name="order-cancel"),
    path("orders/<uuid:pk>/reorder", order_views.OrderReorderView.as_view(), name="order-reorder"),
    path("orders/<uuid:pk>/review", order_views.OrderReviewView.as_view(), name="order-review"),
    path("orders/<uuid:pk>/items/<uuid:item_id>/return", order_views.ReturnRequestView.as_view(), name="order-item-return"),
    path("checkout", order_views.CheckoutView.as_view(), name="checkout"),
    path("checkouts/<uuid:pk>", order_views.CheckoutDetailView.as_view(), name="checkout-detail"),
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
    path("assistant/capabilities", AssistantCapabilitiesView.as_view(), name="assistant-capabilities"),
    path("assistant/transcribe", AssistantTranscribeView.as_view(), name="assistant-transcribe"),
    path("wallet", WalletView.as_view(), name="wallet"),
    path("bookings", booking_views.BookingListCreateView.as_view(), name="bookings"),
    path("bookings/<uuid:pk>", booking_views.BookingDetailView.as_view(), name="booking-detail"),
    path("bookings/<uuid:pk>/cancel", booking_views.BookingCancelView.as_view(), name="booking-cancel"),
    path("showtime/holds", booking_views.HoldsView.as_view(), name="showtime-holds"),
    path("showtime/holds/<uuid:pk>", booking_views.HoldDetailView.as_view(), name="showtime-hold"),
    path("showtime/quote", booking_views.QuoteView.as_view(), name="showtime-quote"),
    path("showtime/titles/<slug:slug>/interest", booking_views.InterestView.as_view(), name="showtime-interest"),
    path("showtime/titles/<slug:slug>/review", booking_views.MyReviewView.as_view(), name="showtime-my-review"),
    *customer_router.urls,
]

api_v1 = [
    path("", include("apps.users.urls")),
    path("stores", store_views.StoreListView.as_view(), name="store-list"),
    path("stores/<slug:slug>", store_views.StoreDetailView.as_view(), name="store-detail"),
    path("stores/<slug:slug>/menu", StoreMenuView.as_view(), name="store-menu"),
    path("products/<uuid:pk>", ProductDetailView.as_view(), name="product-detail"),
    path("search", SearchView.as_view(), name="search"),
    path("shop/", include(shop_public_urls)),
    path("groceries/", include(grocery_urls.public)),
    path("parcels/", include(parcel_urls.public)),
    path("services/", include(services_urls.public)),
    path("partner/services/", include(services_urls.partner)),
    path("partner/grocery/", include(grocery_urls.partner_urls)),
    path("events", booking_views.EventListView.as_view(), name="events"),
    path("events/<slug:slug>", booking_views.EventDetailView.as_view(), name="event-detail"),
    path("shows/<uuid:pk>", booking_views.ShowSeatMapView.as_view(), name="show-seatmap"),
    path("showtime/home", booking_views.ShowtimeHomeView.as_view(), name="showtime-home"),
    path("showtime/search", booking_views.ShowtimeSearchView.as_view(), name="showtime-search"),
    path("showtime/suggest", booking_views.ShowtimeSuggestView.as_view(), name="showtime-suggest"),
    path("showtime/cinemas", booking_views.ShowtimeCinemasView.as_view(), name="showtime-cinemas"),
    path("showtime/titles/<slug:slug>", booking_views.ShowtimeTitleView.as_view(), name="showtime-title"),
    path("showtime/titles/<slug:slug>/reviews", booking_views.ShowtimeReviewsView.as_view(), name="showtime-reviews"),
    path("partner/tickets/verify", booking_views.TicketVerifyView.as_view(), name="partner-ticket-verify"),
    path("offers", store_views.OfferListView.as_view(), name="offers"),
    path("buzz", BuzzFeedView.as_view(), name="buzz"),
    path("store-categories", store_views.StoreCategoryListView.as_view(), name="store-categories"),
    path("customer/", include(customer_urls)),
    path("partner/", include(ride_partner_urls)),
    path("partner/", include("apps.partners.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health", health, name="health"),
    path("api/v1/", include(api_v1)),
]
if settings.DEBUG:  # development only; production serves uploads from object storage/CDN
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
