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
import { BookingPage } from './pages/BookingPage';
import { BookingsPage } from './pages/BookingsPage';
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
import { SettingsPage } from './pages/SettingsPage';
import { ServicePage } from './pages/ServicePage';
import { StorePage } from './pages/StorePage';
import { TicketPage } from './pages/TicketPage';
import { WishlistPage } from './pages/WishlistPage';
import { CheckoutDonePage } from './pages/CheckoutDonePage';
import { ShopBrandsPage } from './pages/ShopBrandsPage';
import { ShopComparePage } from './pages/ShopComparePage';
import { ShopResultsPage } from './pages/ShopResultsPage';
import { ShoppingPage } from './pages/ShoppingPage';

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
      <Route path="buzz" element={<BuzzPage />} />
      {/* Profile: a dedicated personal page with its own header (no app header or bottom navigation) */}
      <Route path="account" element={guard(<ProfilePage />)} />
      <Route element={<AppShell />}>
        {/* Discovery (public) */}
        <Route index element={<HomePage />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="food" element={<ServicePage key="restaurant" storeType="restaurant" />} />
        <Route path="groceries" element={<ServicePage key="grocery" storeType="grocery" />} />
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
        <Route path="parcels" element={<ServiceComingSoonPage key="parcels" serviceId="parcels" />} />
        <Route path="services" element={<ServiceComingSoonPage key="services" serviceId="services" />} />
        <Route path="experiences" element={<ServiceComingSoonPage key="experiences" serviceId="experiences" />} />
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
        <Route path="settings" element={guard(<SettingsPage />)} />
        <Route path="wallet" element={guard(<WalletPage />)} />
        <Route path="bookings" element={<Navigate to="/tickets" replace />} />
        <Route path="bookings/:id" element={<ParamRedirect to="/tickets/:id" />} />
        <Route path="activity" element={guard(<ActivityPage />)} />
        <Route path="help/new" element={guard(<NewTicketPage />)} />
        <Route path="help/tickets/:id" element={guard(<TicketPage />)} />
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
