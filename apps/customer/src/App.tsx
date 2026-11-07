import { Link, Route, Routes } from 'react-router-dom';
import { RequireAuth } from './auth/RequireAuth';
import { AppShell } from './components/layout/AppShell';
import { EmptyState } from './components/ui';
import { AccountPage } from './pages/AccountPage';
import { LoginPage, RegisterPage } from './pages/AuthPages';
import { CartPage } from './pages/CartPage';
import { CheckoutPage } from './pages/CheckoutPage';
import { FoodPage } from './pages/FoodPage';
import { HomePage } from './pages/HomePage';
import { OrderPage } from './pages/OrderPage';
import { OrdersPage } from './pages/OrdersPage';
import { StorePage } from './pages/StorePage';

const guard = (el: React.ReactNode) => <RequireAuth>{el}</RequireAuth>;

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<HomePage />} />
        <Route path="food" element={<FoodPage />} />
        <Route path="stores/:slug" element={<StorePage />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="register" element={<RegisterPage />} />
        <Route path="cart" element={guard(<CartPage />)} />
        <Route path="checkout" element={guard(<CheckoutPage />)} />
        <Route path="orders" element={guard(<OrdersPage />)} />
        <Route path="orders/:id" element={guard(<OrderPage />)} />
        <Route path="account" element={guard(<AccountPage />)} />
        <Route path="*" element={<EmptyState icon="alert" title="Page not found" action={<Link to="/" className="btn btn--outline">Go home</Link>} />} />
      </Route>
    </Routes>
  );
}
