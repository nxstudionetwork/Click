import { createContext, useContext, useEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../../auth/AuthProvider';
import { themeForPath, type Theme } from '../../config/services';
import { usingMockData } from '../../data/stores-source';
import { useCart } from '../../features/cart/useCart';
import { useUnreadCount } from '../../features/notifications/hooks';
import { LocationSelector } from '../../location/LocationSelector';
import { BuddyLauncher } from '../shell/BuddyLauncher';
import { GlobalSearch } from '../shell/GlobalSearch';
import { MenuHub } from '../shell/MenuHub';
import { ProfileMenu } from '../shell/ProfileMenu';
import { Icon, type IconName } from '../ui';
import { Logo } from './Logo';

/** Primary navigation: the most frequent destinations, plus Menu for everything else. */
const PRIMARY: { to: string; label: string; icon: IconName; end?: boolean }[] = [
  { to: '/', label: 'Home', icon: 'home', end: true },
  { to: '/rides', label: 'Ride', icon: 'ride' },
  { to: '/food', label: 'Food', icon: 'food' },
  { to: '/services', label: 'Services', icon: 'wrench' },
];

const ThemeOverride = createContext<(t: Theme | null) => void>(() => {});
/** Pages whose theme depends on data (e.g. a store's vertical) set it here. */
export function useThemeOverride(theme: Theme | null) {
  const set = useContext(ThemeOverride);
  useEffect(() => { set(theme); return () => set(null); }, [theme, set]);
}

export function AppShell() {
  const { status } = useAuth();
  const { pathname } = useLocation();
  const { data: cart } = useCart();
  const { data: unread = 0 } = useUnreadCount();
  const [menuOpen, setMenuOpen] = useState(false);
  const [override, setOverride] = useState<Theme | null>(null);
  const count = cart?.itemCount ?? 0;
  const theme = override ?? themeForPath(pathname);
  const focused = pathname === '/buddy' || pathname === '/checkout';
  const headerRef = useRef<HTMLElement>(null);

  // Sticky page elements sit below the real header height, which varies by breakpoint and page.
  useEffect(() => {
    const el = headerRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => document.documentElement.style.setProperty('--header-total', `${el.offsetHeight}px`));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => setMenuOpen(false), [pathname]);
  useEffect(() => { window.scrollTo?.(0, 0); }, [pathname]);

  return (
    <ThemeOverride.Provider value={setOverride}>
      <div className="shell" data-theme={theme}>
        <a href="#main" className="skip-link">Skip to content</a>
        {usingMockData && <div className="mock-banner">Showing TEMPORARY MOCK DATA for discovery — not real stores</div>}
        <header className="header" ref={headerRef}>
          <div className="header__bar">
            <Link to="/" aria-label="Click home" className="header__logo"><Logo /></Link>
            <div className="header__location"><LocationSelector /></div>
            {!focused && <div className="header__search"><GlobalSearch /></div>}
            <div className="header__actions">
              <BuddyLauncher />
              {status === 'authenticated' && (
                <Link to="/notifications" className="icon-btn" aria-label={`Notifications${unread ? `, ${unread} unread` : ''}`}>
                  <Icon name="bell" />
                  {unread > 0 && <span className="icon-btn__count">{unread > 9 ? '9+' : unread}</span>}
                </Link>
              )}
              <Link to="/cart" className="icon-btn" aria-label={`Cart, ${count} items`}>
                <Icon name="bag" />
                {count > 0 && <span key={count} className="icon-btn__count icon-btn__count--pop">{count}</span>}
              </Link>
              {status === 'authenticated' ? <ProfileMenu /> : status === 'anonymous' ? <Link to="/login" className="btn btn--secondary btn--sm">Sign in</Link> : null}
            </div>
          </div>
          <div className="header__mobile-location"><LocationSelector compact /></div>
          {!focused && <div className="header__mobile-search"><GlobalSearch compact /></div>}
          <nav className="header__nav" aria-label="Primary">
            {PRIMARY.map((n) => <NavLink key={n.to} to={n.to} end={n.end}><Icon name={n.icon} size={18} />{n.label}</NavLink>)}
            <button type="button" className={menuOpen ? 'active' : ''} onClick={() => setMenuOpen(true)} aria-haspopup="dialog"><Icon name="menu" size={18} />Menu</button>
          </nav>
        </header>

        <main className="main" id="main">
          <div key={pathname} className="route">
            <Outlet />
          </div>
        </main>

        <nav className="bottom-nav" aria-label="Primary">
          {PRIMARY.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end}><Icon name={n.icon} />{n.label}</NavLink>
          ))}
          <button type="button" className={menuOpen ? 'active' : ''} onClick={() => setMenuOpen(true)} aria-haspopup="dialog"><Icon name="menu" />Menu</button>
        </nav>
        <MenuHub open={menuOpen} onClose={() => setMenuOpen(false)} />
      </div>
    </ThemeOverride.Provider>
  );
}
