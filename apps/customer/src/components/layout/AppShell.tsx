import { Link, NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../../auth/AuthProvider';
import { usingMockData } from '../../data/stores-source';
import { useCart } from '../../features/cart/useCart';
import { Icon, type IconName } from '../ui';
import { Logo } from './Logo';

const NAV: { to: string; label: string; icon: IconName }[] = [
  { to: '/', label: 'Home', icon: 'home' },
  { to: '/food', label: 'Food', icon: 'food' },
  { to: '/orders', label: 'Orders', icon: 'receipt' },
  { to: '/account', label: 'Account', icon: 'user' },
];

export function AppShell() {
  const { status } = useAuth();
  const { data: cart } = useCart();
  const count = cart?.itemCount ?? 0;

  return (
    <div className="shell">
      {usingMockData && <div className="mock-banner">Showing TEMPORARY MOCK DATA for discovery — not real stores</div>}
      <header className="header">
        <div className="container header__inner">
          <Link to="/" aria-label="Click home"><Logo /></Link>
          <nav className="header__nav" aria-label="Primary">
            {NAV.map((n) => <NavLink key={n.to} to={n.to} end={n.to === '/'}>{n.label}</NavLink>)}
          </nav>
          <div className="header__actions">
            <Link to="/food" className="icon-btn" aria-label="Search"><Icon name="search" /></Link>
            <Link to="/cart" className="icon-btn" aria-label={`Cart, ${count} items`}>
              <Icon name="bag" />
              {count > 0 && <span className="icon-btn__count">{count}</span>}
            </Link>
            {status === 'anonymous' && <Link to="/login" className="btn btn--secondary btn--sm">Sign in</Link>}
          </div>
        </div>
      </header>
      <main className="main">
        <div className="container"><Outlet /></div>
      </main>
      <nav className="bottom-nav" aria-label="Primary">
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.to === '/'}>
            <Icon name={n.icon} />
            {n.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
