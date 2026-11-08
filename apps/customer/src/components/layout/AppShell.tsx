import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthProvider';
import { themeForPath, type Theme } from '../../config/services';
import { useCart } from '../../features/cart/useCart';
import { ExploreSheet } from '../../features/explore/ExploreSheet';
import { useUnreadCount } from '../../features/notifications/hooks';
import { LocationSelector } from '../../location/LocationSelector';
import { BuddySelector } from '../shell/BuddySelector';
import { BuzzEntry } from '../shell/BuzzEntry';
import { GlobalSearch } from '../shell/GlobalSearch';
import { ProfileButton } from '../shell/ProfileButton';
import { Icon, type IconName } from '../ui';
import { Logo } from './Logo';

/**
 * Primary navigation. Each destination carries its own service colour (inactive: subtle, active: strong).
 * Explore opens as a bottom sheet over the current page (`sheet`); the others are routes.
 */
export const PRIMARY: { to: string; label: string; icon: IconName; theme: Theme; end?: boolean; sheet?: boolean }[] = [
  { to: '/', label: 'Home', icon: 'home', theme: 'default', end: true },
  { to: '/rides', label: 'Ride', icon: 'ride', theme: 'ride' },
  { to: '/food', label: 'Food', icon: 'food', theme: 'food' },
  { to: '/explore', label: 'Explore', icon: 'compass', theme: 'explore', sheet: true },
  { to: '/shopping', label: 'Shop', icon: 'shop', theme: 'shopping' },
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
  const [override, setOverride] = useState<Theme | null>(null);
  const [exploreOpen, setExploreOpen] = useState(false);
  const navigate = useNavigate();
  const closeExplore = useCallback(() => setExploreOpen(false), []);
  // Explore is for signed-in customers; others are sent to sign in first.
  const openExplore = () => (status === 'authenticated' ? setExploreOpen(true) : navigate('/login?next=/explore'));
  const count = cart?.itemCount ?? 0;
  const theme = override ?? themeForPath(pathname);
  // The global search belongs to Home (and its results page) only; service pages have their own search,
  // and other pages have none. The header itself stays fixed on every page.
  const showSearch = pathname === '/' || pathname === '/search';
  const headerRef = useRef<HTMLElement>(null);

  // Sticky page elements sit below the real header height, which varies by breakpoint and page.
  useEffect(() => {
    const el = headerRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => document.documentElement.style.setProperty('--header-total', `${el.offsetHeight}px`));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => { window.scrollTo?.(0, 0); }, [pathname]);

  return (
    <ThemeOverride.Provider value={setOverride}>
      <div className="shell" data-theme={theme}>
        <a href="#main" className="skip-link">Skip to content</a>
        <header className="header" ref={headerRef}>
          <div className="header__bar">
            <Link to="/" aria-label="Click. home" className="header__logo"><Logo /></Link>
            <div className="header__location"><LocationSelector /></div>
            {showSearch ? <div className="header__search"><GlobalSearch /></div> : <div className="header__spacer" />}
            <div className="header__actions">
              <BuddySelector />
              <Link to="/notifications" className="icon-btn" aria-label={`Notifications${unread ? `, ${unread} unread` : ''}`}>
                <Icon name="bell" />
                {status === 'authenticated' && unread > 0 && <span className="icon-btn__count">{unread > 9 ? '9+' : unread}</span>}
              </Link>
              {count > 0 && (
                <Link to="/cart" className="icon-btn" aria-label={`Cart, ${count} items`}>
                  <Icon name="bag" />
                  <span key={count} className="icon-btn__count icon-btn__count--pop">{count}</span>
                </Link>
              )}
              <ProfileButton />
            </div>
          </div>
          <div className="header__mobile-location"><LocationSelector compact /></div>
          {showSearch && <div className="header__mobile-search"><GlobalSearch compact /></div>}
          <nav className="header__nav" aria-label="Primary">
            {PRIMARY.map((n) => n.sheet ? (
              <button key={n.to} type="button" data-theme={n.theme} className={exploreOpen || pathname === n.to ? 'active' : ''}
                aria-haspopup="dialog" aria-expanded={exploreOpen} onClick={openExplore}><Icon name={n.icon} size={18} />{n.label}</button>
            ) : (
              <NavLink key={n.to} to={n.to} end={n.end} data-theme={n.theme} className={({ isActive }) => (isActive && !exploreOpen ? 'active' : '')}><Icon name={n.icon} size={18} />{n.label}</NavLink>
            ))}
          </nav>
        </header>

        <main className="main" id="main">
          <div key={pathname} className="route">
            <Outlet />
          </div>
        </main>

        <BuzzEntry />
        <nav className="bottom-nav" aria-label="Primary">
          {PRIMARY.map((n) => n.sheet ? (
            <button key={n.to} type="button" data-theme={n.theme} className={`bottom-nav__item ${exploreOpen || pathname === n.to ? 'active' : ''}`}
              aria-haspopup="dialog" aria-expanded={exploreOpen} onClick={openExplore}>
              <span className="bottom-nav__icon"><Icon name={n.icon} /></span>
              <span className="bottom-nav__label">{n.label}</span>
            </button>
          ) : (
            <NavLink key={n.to} to={n.to} end={n.end} data-theme={n.theme} className={({ isActive }) => `bottom-nav__item ${isActive && !exploreOpen ? 'active' : ''}`}>
              <span className="bottom-nav__icon"><Icon name={n.icon} /></span>
              <span className="bottom-nav__label">{n.label}</span>
            </NavLink>
          ))}
        </nav>
        <ExploreSheet open={exploreOpen} onClose={closeExplore} />
      </div>
    </ThemeOverride.Provider>
  );
}
