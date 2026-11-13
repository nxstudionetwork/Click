import { lazy, Suspense, useState } from 'react';
import { Link, Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom';
import { useAuth } from './auth/AuthProvider';
import { LoginPage } from './onboarding/LoginPage';
import { SignupPage } from './onboarding/SignupPage';
import { Splash, splashAlreadyShown } from './onboarding/Splash';
import { VerifyPage } from './onboarding/VerifyPage';
import { RequireAuth } from './auth/RequireAuth';
import { AppShell } from './components/layout/AppShell';
import { EmptyState } from './components/ui';
import { AddressesPage } from './pages/AddressesPage';
import { ActivityPage } from './pages/ActivityPage';
import { WalletEntryPage } from './pages/WalletEntryPage';
import { PaymentDetailPage } from './pages/PaymentDetailPage';
import { HelpArticlePage } from './pages/HelpArticlePage';
import { ReviewsPage } from './pages/ReviewsPage';
import { InvoicePage, InvoicesPage } from './pages/InvoicesPage';
import { GiftCardDetailPage, GiftCardsPage, MyGiftCardsPage } from './pages/GiftCardsPage';
import { SafetyPage } from './pages/SafetyPage';
import { BookingPage } from './pages/BookingPage';
import { BookingsPage } from './pages/BookingsPage';
import { BuddyGoPage } from './pages/BuddyGoPage';
import { BuddyPage } from './pages/BuddyPage';
import { BuzzPage } from './pages/BuzzPage';
import { useAppearance } from './appearance';
import { ShowPage } from './pages/ShowPage';
import { ShowtimeCheckoutPage } from './pages/ShowtimeCheckoutPage';
import { ShowtimePage } from './pages/ShowtimePage';
import { ShowtimeSearchPage } from './pages/ShowtimeSearchPage';
import { ShowtimeTitlePage } from './pages/ShowtimeTitlePage';
import { WalletPage } from './pages/WalletPage';
import { CartPage } from './pages/CartPage';
import { CheckoutPage } from './pages/CheckoutPage';
import { ExplorePage } from './pages/ExplorePage';
import { HelpPage } from './pages/HelpPage';
import { HomePage } from './pages/HomePage';
import { NewTicketPage } from './pages/NewTicketPage';
import { NotificationsPage } from './pages/NotificationsPage';
import { OffersPage } from './pages/OffersPage';
import { OrderPage } from './pages/OrderPage';
import { OrdersPage } from './pages/OrdersPage';
import { PaymentsPage } from './pages/PaymentsPage';
import { ProductPage } from './pages/ProductPage';
import { ProfilePage } from './pages/ProfilePage';
import { RewardsPage } from './pages/RewardsPage';
import { SearchPage } from './pages/SearchPage';
import { ServiceComingSoonPage } from './pages/ServiceComingSoonPage';
import { SERVICES } from './config/services';
import { SettingsPage } from './pages/SettingsPage';
import { ServicePage } from './pages/ServicePage';
import { StorePage } from './pages/StorePage';
import { TicketPage, TicketsPage } from './pages/TicketPage';
import { WishlistPage } from './pages/WishlistPage';
import { CheckoutDonePage } from './pages/CheckoutDonePage';
import { ShopBrandsPage } from './pages/ShopBrandsPage';
import { ShopComparePage } from './pages/ShopComparePage';
import { ShopResultsPage } from './pages/ShopResultsPage';
import { ShoppingPage } from './pages/ShoppingPage';
import { GroceriesPage } from './pages/GroceriesPage';
import { ParcelDetailPage } from './pages/ParcelDetailPage';
import { ParcelHistoryPage } from './pages/ParcelHistoryPage';
import { ParcelPage } from './pages/ParcelPage';
import { ParcelSharedPage } from './pages/ParcelSharedPage';
import { EventBookingPage } from './pages/EventBookingPage';
import { EventBookPage } from './pages/EventBookPage';
import { EventPlanFlowPage } from './pages/EventPlanFlowPage';
import { EventPlanPage } from './pages/EventPlanPage';
import { EventProviderPage } from './pages/EventProviderPage';
import { EventsMinePage } from './pages/EventsMinePage';
import { EventsPage } from './pages/EventsPage';
import { EventTeamsPage } from './pages/EventTeamsPage';
import { HotelBookingPage } from './pages/HotelBookingPage';
import { HotelBookingsPage } from './pages/HotelBookingsPage';
import { HotelBookPage } from './pages/HotelBookPage';
import { HotelComparePage } from './pages/HotelComparePage';
import { HotelPropertyPage } from './pages/HotelPropertyPage';
import { HotelSearchPage } from './pages/HotelSearchPage';
import { HotelsPage } from './pages/HotelsPage';
import { TravelPage } from './pages/TravelPage';
import { TravelSearchPage } from './pages/TravelSearchPage';
import { TravelJourneyPage } from './pages/TravelJourneyPage';
import { TravelBookPage } from './pages/TravelBookPage';
import { TravelBookingPage } from './pages/TravelBookingPage';
import { TravelBookingsPage, TravelComparePage } from './pages/TravelBookingsPage';
import { TravelMePage } from './pages/TravelMePage';
import { TravelPlanPage } from './pages/TravelPlanPage';
import { BookingsHubPage } from './pages/BookingsHubPage';
import { BookingsSearchPage } from './pages/BookingsSearchPage';
import { AttractionPage } from './pages/AttractionPage';
import { ExperienceBookPage } from './pages/ExperienceBookPage';
import { ExperienceBookingPage } from './pages/ExperienceBookingPage';
import { MyBookingsPage } from './pages/MyBookingsPage';
import { ProProfilePage } from './pages/ProProfilePage';
import { ServiceBookingPage } from './pages/ServiceBookingPage';
import { ServiceBookPage } from './pages/ServiceBookPage';
import { ServiceCategoryPage } from './pages/ServiceCategoryPage';
import { ServiceHistoryPage } from './pages/ServiceHistoryPage';
import { ServiceRequestPage } from './pages/ServiceRequestPage';
import { ServicesPage } from './pages/ServicesPage';
import { GroceryBasketPage } from './pages/GroceryBasketPage';
import { GroceryBuyAgainPage } from './pages/GroceryBuyAgainPage';
import { GroceryCheckoutPage } from './pages/GroceryCheckoutPage';
import { GroceryListsPage } from './pages/GroceryListsPage';
import { GroceryProductPage } from './pages/GroceryProductPage';
import { GrocerySearchPage } from './pages/GrocerySearchPage';
import { GroceryStorePage } from './pages/GroceryStorePage';

const guard = (el: React.ReactNode) => <RequireAuth>{el}</RequireAuth>;
// The Click card (QR rendering) is only needed after signup / from Account, so it loads on demand.
// Ride pages carry the map library (Leaflet), so they load on first visit rather than with the app.
const RidePage = lazy(() => import('./pages/RidePage').then((m) => ({ default: m.RidePage })));
const RideTripPage = lazy(() => import('./pages/RideTripPage').then((m) => ({ default: m.RideTripPage })));
const rideFallback = <div className="stack"><div className="skeleton" style={{ height: 320, borderRadius: 20 }} /><div className="skeleton" style={{ height: 160, borderRadius: 20 }} /></div>;
const CardPage = lazy(() => import('./onboarding/CardPage').then((m) => ({ default: m.CardPage })));
const lazyCard = (onboardingStep: boolean) => <Suspense fallback={<div className="state"><div className="skeleton" style={{ width: 320, height: 200, borderRadius: 26 }} /></div>}><CardPage onboardingStep={onboardingStep} /></Suspense>;

export function App() {
  useAppearance(); // keeps the saved White / Dark / device appearance applied (and follows device changes)
  const [splash, setSplash] = useState(() => !splashAlreadyShown());
  const { status } = useAuth();
  const navigate = useNavigate();
  const { pathname, search } = useLocation();
  const finishSplash = () => {
    setSplash(false);
    // First open of Click, not signed in, landing on Home: go to sign in (guests can still explore).
    if (status !== 'authenticated' && pathname === '/' && !search.includes('guest')) navigate('/login', { replace: true });
  };
  return (
    <>
      {splash && <Splash onDone={finishSplash} />}
      <AppRoutes />
    </>
  );
}

function AppRoutes() {
  return (
    <Routes>
      {/* Onboarding & sign-in: full-screen, outside the app shell */}
      <Route path="login" element={<LoginPage />} />
      <Route path="login/verify" element={<VerifyPage />} />
      <Route path="signup" element={<SignupPage />} />
      <Route path="welcome/card" element={guard(lazyCard(true))} />
      <Route path="register" element={<Navigate to="/login" replace />} />
      {/* Immersive experiences with their own layouts (no app header / bottom navigation) */}
      <Route path="buddy" element={<BuddyPage />} />
      <Route path="buddy/go" element={<BuddyGoPage />} />
      <Route path="buzz" element={<BuzzPage />} />
      {/* Profile: a dedicated personal page with its own header (no app header or bottom navigation) */}
      <Route path="account" element={guard(<ProfilePage />)} />
      {/* Activity: a dedicated timeline with its own Back / Activity / Home header (no app header or bottom navigation) */}
      <Route path="activity" element={guard(<ActivityPage />)} />
      <Route element={<AppShell />}>
        {/* Discovery (public) */}
        <Route index element={<HomePage />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="food" element={<ServicePage key="restaurant" storeType="restaurant" />} />
        <Route path="groceries" element={<GroceriesPage />} />
        <Route path="groceries/search" element={<GrocerySearchPage />} />
        <Route path="groceries/store/:slug" element={<GroceryStorePage />} />
        <Route path="groceries/p/:id" element={<GroceryProductPage />} />
        <Route path="groceries/basket" element={guard(<GroceryBasketPage />)} />
        <Route path="groceries/checkout" element={guard(<GroceryCheckoutPage />)} />
        <Route path="groceries/lists" element={guard(<GroceryListsPage />)} />
        <Route path="groceries/buy-again" element={guard(<GroceryBuyAgainPage />)} />
        <Route path="shopping" element={<ShoppingPage />} />
        <Route path="shopping/search" element={<ShopResultsPage key="search" mode="search" />} />
        <Route path="shopping/c/:slug" element={<ShopResultsPage key="category" mode="category" />} />
        <Route path="shopping/brands" element={<ShopBrandsPage />} />
        <Route path="shopping/brands/:slug" element={<ShopResultsPage key="brand" mode="brand" />} />
        <Route path="shopping/compare" element={<ShopComparePage />} />
        <Route path="shop" element={<Navigate to="/shopping" replace />} />
        <Route path="stores/:slug" element={<StorePage />} />
        <Route path="products/:id" element={<ProductPage />} />
        <Route path="offers" element={<OffersPage />} />
        <Route path="showtime" element={<ShowtimePage />} />
        <Route path="showtime/search" element={<ShowtimeSearchPage />} />
        <Route path="showtime/checkout/:holdId" element={guard(<ShowtimeCheckoutPage />)} />
        <Route path="showtime/:slug" element={<ShowtimeTitlePage />} />
        <Route path="shows/:id" element={<ShowPage />} />
        {/* Old Movies links keep working */}
        <Route path="movies" element={<MoviesRedirect />} />
        <Route path="movies/:slug" element={<ParamRedirect to="/showtime/:slug" />} />
        <Route path="rides" element={<Suspense fallback={rideFallback}><RidePage /></Suspense>} />
        <Route path="rides/:id" element={guard(<Suspense fallback={rideFallback}><RideTripPage /></Suspense>)} />
        <Route path="parcels" element={<ParcelPage />} />
        <Route path="parcels/history" element={guard(<ParcelHistoryPage />)} />
        <Route path="parcels/:id" element={guard(<ParcelDetailPage />)} />
        <Route path="track/:token" element={<ParcelSharedPage />} />
        <Route path="parcel" element={<Navigate to="/parcels" replace />} />
        <Route path="hotels" element={<HotelsPage />} />
        <Route path="hotels/search" element={<HotelSearchPage />} />
        <Route path="hotels/compare" element={<HotelComparePage />} />
        <Route path="hotels/book" element={guard(<HotelBookPage />)} />
        <Route path="hotels/bookings" element={guard(<HotelBookingsPage />)} />
        <Route path="hotels/bookings/:id" element={guard(<HotelBookingPage />)} />
        <Route path="hotels/:id" element={<HotelPropertyPage />} />
        <Route path="travel" element={<TravelPage />} />
        <Route path="travel/search" element={<TravelSearchPage />} />
        <Route path="travel/journey/:journey/:from/:to" element={<TravelJourneyPage />} />
        <Route path="travel/compare" element={<TravelComparePage />} />
        <Route path="travel/plan" element={<TravelPlanPage />} />
        <Route path="travel/book" element={guard(<TravelBookPage />)} />
        <Route path="travel/bookings" element={guard(<TravelBookingsPage />)} />
        <Route path="travel/bookings/:id" element={guard(<TravelBookingPage />)} />
        <Route path="travel/me" element={guard(<TravelMePage />)} />
        <Route path="bookings" element={<BookingsHubPage />} />
        <Route path="bookings/search" element={<BookingsSearchPage />} />
        <Route path="bookings/places/:slug" element={<AttractionPage />} />
        <Route path="bookings/book" element={guard(<ExperienceBookPage />)} />
        <Route path="bookings/mine" element={guard(<MyBookingsPage />)} />
        <Route path="bookings/r/:id" element={guard(<ExperienceBookingPage />)} />
        <Route path="events" element={<EventsPage />} />
        <Route path="events/teams" element={<EventTeamsPage />} />
        <Route path="events/venues" element={<EventTeamsPage key="venues" venues />} />
        <Route path="events/providers/:id" element={<EventProviderPage />} />
        <Route path="events/plan" element={guard(<EventPlanFlowPage />)} />
        <Route path="events/plans/:id" element={guard(<EventPlanPage />)} />
        <Route path="events/book" element={guard(<EventBookPage />)} />
        <Route path="events/bookings/:id" element={guard(<EventBookingPage />)} />
        <Route path="events/mine" element={guard(<EventsMinePage />)} />
        <Route path="services" element={<ServicesPage />} />
        <Route path="services/book" element={guard(<ServiceBookPage />)} />
        <Route path="services/request" element={<ServiceRequestPage />} />
        <Route path="services/bookings" element={guard(<ServiceHistoryPage />)} />
        <Route path="services/bookings/:id" element={guard(<ServiceBookingPage />)} />
        <Route path="services/pro/:id" element={<ProProfilePage />} />
        <Route path="services/:slug" element={<ServiceCategoryPage />} />
        <Route path="experiences" element={<Navigate to="/bookings/search?group=experiences" replace />} />
        {/* Services announced but not live yet get an honest coming-soon page at their registry path. */}
        {SERVICES.filter((s) => s.status === 'soon').map((s) => <Route key={s.id} path={s.path.slice(1)} element={<ServiceComingSoonPage serviceId={s.id} />} />)}
        <Route path="tickets" element={guard(<BookingsPage />)} />
        <Route path="tickets/:id" element={guard(<BookingPage />)} />
        <Route path="deliveries" element={<Navigate to="/parcels" replace />} />
        <Route path="help" element={<HelpPage />} />
        <Route path="assistant" element={<Navigate to="/buddy" replace />} />
        {/* Friendly aliases for the primary destinations */}
        <Route path="home" element={<Navigate to="/" replace />} />
        <Route path="ride" element={<Navigate to="/rides" replace />} />
        <Route path="profile" element={<Navigate to="/account" replace />} />

        {/* Customer-owned data (authenticated; API enforces ownership) */}
        <Route path="explore" element={guard(<ExplorePage />)} />
        <Route path="cart" element={guard(<CartPage />)} />
        <Route path="checkout" element={guard(<CheckoutPage />)} />
        <Route path="checkout/done/:id" element={guard(<CheckoutDonePage />)} />
        <Route path="orders" element={guard(<OrdersPage />)} />
        <Route path="orders/:id" element={guard(<OrderPage />)} />
        <Route path="wishlist" element={guard(<WishlistPage />)} />
        <Route path="rewards" element={guard(<RewardsPage />)} />
        <Route path="notifications" element={guard(<NotificationsPage />)} />
        <Route path="account/addresses" element={guard(<AddressesPage />)} />
        <Route path="account/card" element={guard(lazyCard(false))} />
        <Route path="account/payments" element={guard(<PaymentsPage />)} />
        <Route path="account/payments/:id" element={guard(<PaymentDetailPage />)} />
        <Route path="account/invoices" element={guard(<InvoicesPage />)} />
        <Route path="account/invoices/:id" element={guard(<InvoicePage />)} />
        <Route path="account/reviews" element={guard(<ReviewsPage />)} />
        <Route path="gift-cards" element={<GiftCardsPage />} />
        <Route path="gift-cards/mine" element={guard(<MyGiftCardsPage />)} />
        <Route path="gift-cards/mine/:id" element={guard(<GiftCardDetailPage />)} />
        <Route path="safety" element={guard(<SafetyPage />)} />
        <Route path="settings" element={guard(<SettingsPage />)} />
        <Route path="wallet" element={guard(<WalletPage />)} />
        <Route path="wallet/activity/:id" element={guard(<WalletEntryPage />)} />
        <Route path="bookings/:id" element={<ParamRedirect to="/tickets/:id" />} />
        <Route path="help/new" element={guard(<NewTicketPage />)} />
        <Route path="help/tickets" element={guard(<TicketsPage />)} />
        <Route path="help/tickets/:id" element={guard(<TicketPage />)} />
        <Route path="help/articles/:slug" element={<HelpArticlePage />} />
        <Route path="*" element={<EmptyState icon="alert" title="Page not found" action={<Link to="/" className="btn btn--outline">Go home</Link>} />} />
      </Route>
    </Routes>
  );
}

/** /movies?tab=events -> live shows; /movies -> Showtime. */
function MoviesRedirect() {
  const { search } = useLocation();
  return <Navigate to={search.includes('tab=events') ? '/showtime/search?kind=event' : '/showtime'} replace />;
}

function ParamRedirect({ to }: { to: string }) {
  const params = useParams();
  return <Navigate to={to.replace(/:(\w+)/g, (_, k: string) => params[k] ?? '')} replace />;
}
