import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../../auth/AuthProvider';
import { SERVICES } from '../../config/services';
import { usingMockData } from '../../data/stores-source';
import { useCart } from '../../features/cart/useCart';
import { useUnreadCount } from '../../features/notifications/hooks';
import { LocationSelector } from '../../location/LocationSelector';
import { Icon, type IconName } from '../ui';
import { Logo } from './Logo';

type NavItem = { to: string; label: string; icon: IconName; end?: boolean };

const PRIMARY: NavItem[] = [{ to: '/', label: 'Home', icon: 'home', end: true }];
const SECONDARY: NavItem[] = [
  { to: '/orders', label: 'Orders', icon: 'receipt' },
  { to: '/wishlist', label: 'Wishlist', icon: 'heart' },
  { to: '/rewards', label: 'Rewards', icon: 'gift' },
  { to: '/offers', label: 'Offers', icon: 'tag' },
  { to: '/notifications', label: 'Notifications', icon: 'bell' },
];
const FOOTER: NavItem[] = [
  { to: '/help', label: 'Help & Support', icon: 'help' },
  { to: '/settings', label: 'Settings', icon: 'settings' },
];
/** Mobile: only the most important destinations; everything else lives under Explore/Account. */
const BOTTOM: NavItem[] = [
  { to: '/', label: 'Home', icon: 'home', end: true },
  { to: '/explore', label: 'Explore', icon: 'compass' },
  { to: '/orders', label: 'Orders', icon: 'receipt' },
  { to: '/rewards', label: 'Rewards', icon: 'gift' },
  { to: '/account', label: 'Account', icon: 'user' },
];

/** Pages where location context matters (commerce discovery). */
const LOCATION_PAGES = ['/', '/food', '/groceries', '/shopping', '/explore', '/search', '/offers'];

function SideLink({ item, badge }: { item: NavItem; badge?: number }) {
  return (
    <NavLink to={item.to} end={item.end} className="side-link">
      <Icon name={item.icon} size={20} />
      <span>{item.label}</span>
      {badge ? <span className="side-link__badge">{badge > 99 ? '99+' : badge}</span> : null}
    </NavLink>
  );
}

export function AppShell() {
  const { status, user } = useAuth();
  const { pathname } = useLocation();
  const { data: cart } = useCart();
  const { data: unread = 0 } = useUnreadCount();
  const count = cart?.itemCount ?? 0;
  const showLocation = LOCATION_PAGES.includes(pathname) || pathname.startsWith('/stores/');
  const onSearch = pathname === '/search';

  return (
    <div className="shell">
      {usingMockData && <div className="mock-banner">Showing TEMPORARY MOCK DATA for discovery — not real stores</div>}
      <header className="header">
        <div className="header__inner">
          <Link to="/" aria-label="Click home" className="header__logo"><Logo /></Link>
          {showLocation && <div className="header__location"><LocationSelector /></div>}
          {!onSearch && (
            <Link to="/search" className="header__search" aria-label="Search Click">
              <Icon name="search" size={18} /> <span>Search food, groceries, products…</span>
            </Link>
          )}
          <div className="header__actions">
            {!onSearch && <Link to="/search" className="icon-btn header__search-icon" aria-label="Search"><Icon name="search" /></Link>}
            <Link to="/assistant" className="icon-btn" aria-label="Ask Click AI"><Icon name="sparkle" /></Link>
            {status === 'authenticated' && (
              <Link to="/notifications" className="icon-btn" aria-label={`Notifications${unread ? `, ${unread} unread` : ''}`}>
                <Icon name="bell" />
                {unread > 0 && <span className="icon-btn__count">{unread > 9 ? '9+' : unread}</span>}
              </Link>
            )}
            <Link to="/cart" className="icon-btn" aria-label={`Cart, ${count} items`}>
              <Icon name="bag" />
              {count > 0 && <span className="icon-btn__count">{count}</span>}
            </Link>
            {status === 'authenticated' ? (
              <Link to="/account" className="avatar header__avatar" aria-label="Your account">
                {(user?.fullName || user?.email || '?').trim()[0]!.toUpperCase()}
              </Link>
            ) : status === 'anonymous' ? (
              <Link to="/login" className="btn btn--secondary btn--sm">Sign in</Link>
            ) : null}
          </div>
        </div>
        {showLocation && <div className="header__location-mobile"><LocationSelector compact /></div>}
      </header>

      <div className="layout">
        <aside className="sidebar" aria-label="Main navigation">
          <nav className="stack" style={{ gap: 2 }}>
            {PRIMARY.map((i) => <SideLink key={i.to} item={i} />)}
            <div className="side-group">Explore</div>
            {SERVICES.map((s) => (
              <NavLink key={s.id} to={s.path} className="side-link">
                <Icon name={s.icon} size={20} /><span>{s.name}</span>
                {s.status === 'soon' && <span className="side-link__soon">Soon</span>}
              </NavLink>
            ))}
            <div className="side-group" />
            {SECONDARY.map((i) => <SideLink key={i.to} item={i} badge={i.to === '/notifications' ? unread : undefined} />)}
            <div className="side-group" />
            {FOOTER.map((i) => <SideLink key={i.to} item={i} />)}
          </nav>
        </aside>
        <main className="main" id="main">
          <Outlet />
        </main>
      </div>

      <nav className="bottom-nav" aria-label="Primary">
        {BOTTOM.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end}>
            <Icon name={n.icon} />
            {n.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
