import { Link, Navigate, Route, Routes } from 'react-router-dom';
import { RequireAuth } from './auth/RequireAuth';
import { AppShell } from './components/layout/AppShell';
import { EmptyState } from './components/ui';
import { AccountPage } from './pages/AccountPage';
import { AddressesPage } from './pages/AddressesPage';
import { ActivityPage } from './pages/ActivityPage';
import { BookingPage } from './pages/BookingPage';
import { BookingsPage } from './pages/BookingsPage';
import { BuddyPage } from './pages/BuddyPage';
import { EventPage } from './pages/EventPage';
import { MoviesPage } from './pages/MoviesPage';
import { ShowPage } from './pages/ShowPage';
import { WalletPage } from './pages/WalletPage';
import { LoginPage, RegisterPage } from './pages/AuthPages';
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
import { RewardsPage } from './pages/RewardsPage';
import { SearchPage } from './pages/SearchPage';
import { ServiceComingSoonPage } from './pages/ServiceComingSoonPage';
import { SettingsPage } from './pages/SettingsPage';
import { StoreBrowsePage } from './pages/StoreBrowsePage';
import { StorePage } from './pages/StorePage';
import { TicketPage } from './pages/TicketPage';
import { WishlistPage } from './pages/WishlistPage';

const guard = (el: React.ReactNode) => <RequireAuth>{el}</RequireAuth>;

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        {/* Discovery (public) */}
        <Route index element={<HomePage />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="explore" element={<ExplorePage />} />
        <Route path="food" element={<StoreBrowsePage key="restaurant" storeType="restaurant" />} />
        <Route path="groceries" element={<StoreBrowsePage key="grocery" storeType="grocery" />} />
        <Route path="shopping" element={<StoreBrowsePage key="retail" storeType="retail" />} />
        <Route path="stores/:slug" element={<StorePage />} />
        <Route path="products/:id" element={<ProductPage />} />
        <Route path="offers" element={<OffersPage />} />
        <Route path="movies" element={<MoviesPage />} />
        <Route path="movies/:slug" element={<EventPage />} />
        <Route path="shows/:id" element={<ShowPage />} />
        <Route path="rides" element={<ServiceComingSoonPage key="rides" serviceId="rides" />} />
        <Route path="parcels" element={<ServiceComingSoonPage key="parcels" serviceId="parcels" />} />
        <Route path="services" element={<ServiceComingSoonPage key="services" serviceId="services" />} />
        <Route path="experiences" element={<ServiceComingSoonPage key="experiences" serviceId="experiences" />} />
        <Route path="buzz" element={<ServiceComingSoonPage key="buzz" serviceId="buzz" />} />
        <Route path="tickets" element={<Navigate to="/movies" replace />} />
        <Route path="deliveries" element={<Navigate to="/parcels" replace />} />
        <Route path="help" element={<HelpPage />} />
        <Route path="buddy" element={<BuddyPage />} />
        <Route path="assistant" element={<Navigate to="/buddy" replace />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="register" element={<RegisterPage />} />

        {/* Customer-owned data (authenticated; API enforces ownership) */}
        <Route path="cart" element={guard(<CartPage />)} />
        <Route path="checkout" element={guard(<CheckoutPage />)} />
        <Route path="orders" element={guard(<OrdersPage />)} />
        <Route path="orders/:id" element={guard(<OrderPage />)} />
        <Route path="wishlist" element={guard(<WishlistPage />)} />
        <Route path="rewards" element={guard(<RewardsPage />)} />
        <Route path="notifications" element={guard(<NotificationsPage />)} />
        <Route path="account" element={guard(<AccountPage />)} />
        <Route path="account/addresses" element={guard(<AddressesPage />)} />
        <Route path="account/payments" element={guard(<PaymentsPage />)} />
        <Route path="settings" element={guard(<SettingsPage />)} />
        <Route path="wallet" element={guard(<WalletPage />)} />
        <Route path="bookings" element={guard(<BookingsPage />)} />
        <Route path="bookings/:id" element={guard(<BookingPage />)} />
        <Route path="activity" element={guard(<ActivityPage />)} />
        <Route path="help/new" element={guard(<NewTicketPage />)} />
        <Route path="help/tickets/:id" element={guard(<TicketPage />)} />
        <Route path="*" element={<EmptyState icon="alert" title="Page not found" action={<Link to="/" className="btn btn--outline">Go home</Link>} />} />
      </Route>
    </Routes>
  );
}
