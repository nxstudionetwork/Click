"""
One shared API for all Click products, versioned under /api/v1/.

  public      /api/v1/stores...               discovery (no auth)
  auth        /api/v1/auth/..., /api/v1/me    shared identity
  bookings    /api/v1/events, /api/v1/shows   movies & live events (public)
  hotels      /api/v1/hotels/...              Click. Hotels: search, properties, rooms, bookings (public + customer + partner)
  travel      /api/v1/travel/...              Click. Travel: bus, train and flight search, journeys, tickets (public + customer)
  experiences /api/v1/experiences/...         Click. Bookings: temples, attractions, experiences; /customer/reservations = every booking
  eventhub    /api/v1/eventhub/...            Click. Events: plan events, teams, venues, quotes (public + customer + partner)
  customer    /api/v1/customer/...            Customer App (IsCustomer + ownership)
  partner     /api/v1/partner/...             Click Partner App (resolved from request.user)
  business os /api/v1/os/...                  Phase 6
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from apps.search import views as search_views
from apps.reviews import views as review_views
from apps.invoices import views as invoice_views
from apps.giftcards import views as giftcard_views
from apps.support import safety as safety_views
from apps.discover import views as discover_views
from apps.ai import conversation_views as ai_conv
from apps.ai.views import AssistantCapabilitiesView, AssistantTranscribeView, CustomerAssistantView
from apps.bookings import views as booking_views
from apps.buzz.views import BuzzFeedView
from apps.shop.urls import customer_urls as shop_customer_urls, public_urls as shop_public_urls
from apps.groceries import urls as grocery_urls
from apps.parcels import urls as parcel_urls
from apps.professionals import urls as services_urls
from apps.eventhub import urls as eventhub_urls
from apps.hotels import urls as hotel_urls
from apps.travel import urls as travel_urls
from apps.experiences import urls as experience_urls
from apps.experiences.views import HubView as ReservationsView
from apps.rides.urls import customer_urlpatterns as ride_customer_urls, partner_urlpatterns as ride_partner_urls
from apps.wallet import views as wallet_views
from apps.payments import views as payment_views
from apps.activity.views import ActivityView
from apps.offers import views as offer_views
from apps.rewards import views as reward_views
from apps.carts import views as cart_views
from apps.catalog.search import SearchView
from apps.catalog.views import ProductDetailView, StoreMenuView
from apps.notifications import views as notification_views
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
    path("eventhub/", include(eventhub_urls.customer)),
    path("hotels/", include(hotel_urls.customer)),
    path("travel/", include(travel_urls.customer)),
    path("experiences/", include(experience_urls.customer)),
    path("reservations", ReservationsView.as_view(), name="customer-reservations"),
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
    path("notifications/<uuid:pk>/unread", notification_views.NotificationUnreadView.as_view(), name="notification-unread"),
    path("notifications/preferences", notification_views.PreferencesView.as_view(), name="notification-preferences"),
    path("rewards", reward_views.RewardsView.as_view(), name="rewards"),
    path("rewards/history", reward_views.HistoryView.as_view(), name="rewards-history"),
    path("rewards/history/<uuid:pk>", reward_views.HistoryDetailView.as_view(), name="rewards-history-detail"),
    path("rewards/catalog/<uuid:pk>/redeem", reward_views.RedeemView.as_view(), name="rewards-redeem"),
    path("support/tickets", support_views.SupportTicketListCreateView.as_view(), name="support-tickets"),
    path("support/tickets/<uuid:pk>", support_views.SupportTicketDetailView.as_view(), name="support-ticket"),
    path("support/tickets/<uuid:pk>/messages", support_views.MessagesView.as_view(), name="support-ticket-messages"),
    path("support/tickets/<uuid:pk>/<slug:action>", support_views.TicketActionView.as_view(), name="support-ticket-action"),
    path("support/attachments/<uuid:pk>", support_views.AttachmentView.as_view(), name="support-attachment"),
    path("support/related", support_views.RelatedItemsView.as_view(), name="support-related"),
    path("support/articles/<slug:slug>/feedback", support_views.ArticleFeedbackView.as_view(), name="support-article-feedback"),
    path("activity", ActivityView.as_view(), name="activity"),
    path("search/recent", search_views.RecentView.as_view(), name="search-recent"),
    path("reviews", review_views.ReviewsView.as_view(), name="reviews"),
    path("invoices", invoice_views.InvoicesView.as_view(), name="invoices"),
    path("safety", safety_views.SafetyView.as_view(), name="safety"),
    path("discover/hide", discover_views.HideView.as_view(), name="discover-hide"),
    path("safety/sign-out-others", safety_views.SignOutOthersView.as_view(), name="safety-sign-out-others"),
    path("gift-cards", giftcard_views.MyCardsView.as_view(), name="gift-cards-mine"),
    path("gift-cards/redeem", giftcard_views.RedeemView.as_view(), name="gift-cards-redeem"),
    path("gift-cards/usable", giftcard_views.UsableView.as_view(), name="gift-cards-usable"),
    path("gift-cards/<uuid:pk>", giftcard_views.CardView.as_view(), name="gift-card"),
    path("invoices/<uuid:pk>", invoice_views.InvoiceView.as_view(), name="invoice"),
    path("invoices/<uuid:pk>/document", invoice_views.InvoiceDocumentView.as_view(), name="invoice-document"),
    path("reviews/report", review_views.ReportView.as_view(), name="reviews-report"),
    path("search/recent/<uuid:pk>", search_views.RecentView.as_view(), name="search-recent-one"),
    path("payments", payment_views.PaymentsView.as_view(), name="payments"),
    path("payments/overview", payment_views.OverviewView.as_view(), name="payments-overview"),
    path("payments/preferences", payment_views.PreferencesView.as_view(), name="payments-preferences"),
    path("payments/refunds", payment_views.RefundsView.as_view(), name="payments-refunds"),
    path("payments/<uuid:pk>", payment_views.PaymentDetailView.as_view(), name="payment-detail"),
    path("payments/intents/<str:reference>", payment_views.IntentView.as_view(), name="payment-intent"),
    path("payments/intents/<str:reference>/sandbox", payment_views.IntentSandboxView.as_view(), name="payment-intent-sandbox"),
    path("offers/mine", offer_views.MineView.as_view(), name="offers-mine"),
    path("offers/claimed", offer_views.ClaimedView.as_view(), name="offers-claimed"),
    path("offers/<str:ref>/save", offer_views.SaveView.as_view(), name="offers-save"),
    path("offers/<str:ref>/claim", offer_views.ClaimView.as_view(), name="offers-claim"),
    path("assistant/messages", CustomerAssistantView.as_view(), name="assistant"),
    path("assistant/conversations", ai_conv.ConversationsView.as_view(), name="assistant-conversations"),
    path("assistant/conversations/<uuid:pk>", ai_conv.ConversationDetailView.as_view(), name="assistant-conversation"),
    path("assistant/conversations/<uuid:pk>/messages", ai_conv.ConversationMessagesView.as_view(), name="assistant-conversation-messages"),
    path("assistant/actions", ai_conv.ActionsView.as_view(), name="assistant-actions"),
    path("assistant/actions/<uuid:pk>/<slug:decision>", ai_conv.ActionDecisionView.as_view(), name="assistant-action-decision"),
    path("assistant/events", ai_conv.EventsView.as_view(), name="assistant-events"),
    path("assistant/capabilities", AssistantCapabilitiesView.as_view(), name="assistant-capabilities"),
    path("assistant/transcribe", AssistantTranscribeView.as_view(), name="assistant-transcribe"),
    path("wallet", wallet_views.WalletView.as_view(), name="wallet"),
    path("wallet/transactions", wallet_views.TransactionsView.as_view(), name="wallet-transactions"),
    path("wallet/transactions/<uuid:pk>", wallet_views.TransactionDetailView.as_view(), name="wallet-transaction"),
    path("wallet/top-ups", wallet_views.TopUpsView.as_view(), name="wallet-topups"),
    path("wallet/top-ups/<uuid:pk>", wallet_views.TopUpDetailView.as_view(), name="wallet-topup"),
    path("wallet/top-ups/<uuid:pk>/sandbox", wallet_views.SandboxPayView.as_view(), name="wallet-topup-sandbox"),
    path("wallet/security", wallet_views.SecurityView.as_view(), name="wallet-security"),
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
    path("search/global", search_views.GlobalSearchView.as_view(), name="search-global"),
    path("gift-cards", giftcard_views.DesignsView.as_view(), name="gift-card-designs"),
    path("discover", discover_views.FeedView.as_view(), name="discover"),
    path("discover/events", discover_views.EventView.as_view(), name="discover-events"),
    path("search/suggest", search_views.SuggestView.as_view(), name="search-suggest"),
    path("shop/", include(shop_public_urls)),
    path("groceries/", include(grocery_urls.public)),
    path("parcels/", include(parcel_urls.public)),
    path("services/", include(services_urls.public)),
    path("partner/services/", include(services_urls.partner)),
    path("eventhub/", include(eventhub_urls.public)),
    path("partner/eventhub/", include(eventhub_urls.partner)),
    path("hotels/", include(hotel_urls.public)),
    path("partner/hotels/", include(hotel_urls.partner)),
    path("travel/", include(travel_urls.public)),
    path("experiences/", include(experience_urls.public)),
    path("partner/experiences/", include(experience_urls.partner)),
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
    path("offers/hub", offer_views.HubView.as_view(), name="offers-hub"),
    path("offers/item/<str:ref>", offer_views.OfferView.as_view(), name="offers-item"),
    path("support/help", support_views.HelpHomeView.as_view(), name="support-help"),
    path("support/articles", support_views.ArticleSearchView.as_view(), name="support-articles"),
    path("support/articles/<slug:slug>", support_views.ArticleView.as_view(), name="support-article"),
    path("payments/webhooks/<slug:provider>", wallet_views.ProviderWebhookView.as_view(), name="payments-webhook"),
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
