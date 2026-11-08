import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../../auth/AuthProvider';
import { Icon, type IconName } from '../ui';

export const PROFILE_LINKS: { to: string; label: string; icon: IconName }[] = [
  { to: '/account', label: 'Profile', icon: 'user' },
  { to: '/orders', label: 'Orders', icon: 'receipt' },
  { to: '/bookings', label: 'Bookings', icon: 'ticket' },
  { to: '/cart', label: 'Cart', icon: 'bag' },
  { to: '/wishlist', label: 'Wishlist', icon: 'heart' },
  { to: '/wallet', label: 'Wallet', icon: 'wallet' },
  { to: '/rewards', label: 'Rewards', icon: 'gift' },
  { to: '/offers', label: 'Offers', icon: 'tag' },
  { to: '/notifications', label: 'Notifications', icon: 'bell' },
  { to: '/account/addresses', label: 'Addresses', icon: 'pin' },
  { to: '/account/payments', label: 'Payments', icon: 'card' },
  { to: '/activity', label: 'Activity', icon: 'history' },
  { to: '/settings', label: 'Settings & privacy', icon: 'shield' },
  { to: '/help', label: 'Help & Support', icon: 'help' },
];

export function ProfileMenu() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { pathname } = useLocation();
  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey); };
  }, [open]);
  const initial = (user?.fullName || user?.email || '?').trim()[0]!.toUpperCase();

  return (
    <div className="pmenu" ref={ref}>
      <button className="avatar" aria-haspopup="menu" aria-expanded={open} aria-label="Your account menu" onClick={() => setOpen((o) => !o)}>{initial}</button>
      {open && (
        <div className="pmenu__panel" role="menu">
          <div className="pmenu__head">
            <span className="avatar">{initial}</span>
            <div style={{ minWidth: 0 }}><strong className="truncate" style={{ display: 'block' }}>{user?.fullName || 'Click member'}</strong><span className="small muted truncate" style={{ display: 'block' }}>{user?.email}</span></div>
          </div>
          <div className="pmenu__grid">
            {PROFILE_LINKS.map((l) => (
              <Link key={l.to} to={l.to} role="menuitem" className="pmenu__item"><Icon name={l.icon} size={18} />{l.label}</Link>
            ))}
          </div>
          <button role="menuitem" className="pmenu__item pmenu__logout" onClick={logout}><Icon name="logout" size={18} />Log out</button>
        </div>
      )}
    </div>
  );
}
