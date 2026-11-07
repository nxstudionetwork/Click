import { Link } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { Icon, type IconName } from '../components/ui';

const LINKS: { to: string; label: string; icon: IconName; hint: string }[] = [
  { to: '/orders', label: 'Orders', icon: 'receipt', hint: 'Track and manage orders' },
  { to: '/bookings', label: 'Bookings', icon: 'ticket', hint: 'Movie and event tickets' },
  { to: '/activity', label: 'Activity', icon: 'history', hint: 'Everything you’ve done on Click' },
  { to: '/wallet', label: 'Click Wallet', icon: 'wallet', hint: 'Balance, refunds and credits' },
  { to: '/account/addresses', label: 'Addresses', icon: 'pin', hint: 'Home, work and other places' },
  { to: '/account/payments', label: 'Payments', icon: 'card', hint: 'Methods and payment history' },
  { to: '/wishlist', label: 'Wishlist', icon: 'heart', hint: 'Saved stores and products' },
  { to: '/rewards', label: 'Rewards', icon: 'gift', hint: 'Click points' },
  { to: '/offers', label: 'Offers', icon: 'tag', hint: 'Current deals' },
  { to: '/notifications', label: 'Notifications', icon: 'bell', hint: 'Updates and alerts' },
  { to: '/help', label: 'Help & Support', icon: 'help', hint: 'FAQs and support requests' },
  { to: '/settings', label: 'Settings & privacy', icon: 'shield', hint: 'Profile, privacy and sign out' },
];

export function AccountPage() {
  const { user } = useAuth();
  const initial = (user?.fullName || user?.email || '?').trim()[0]!.toUpperCase();
  return (
    <div className="stack">
      <section className="card card--pad row" style={{ gap: 'var(--s-4)' }}>
        <span className="avatar avatar--lg" aria-hidden="true">{initial}</span>
        <div style={{ minWidth: 0 }}>
          <h2 className="truncate">{user?.fullName || 'Click member'}</h2>
          <div className="muted small truncate">{user?.email}{user?.phone ? ` · ${user.phone}` : ''}</div>
          <div className="muted small">Customer ID {user?.customerCode ?? '—'}</div>
        </div>
        <Link to="/settings" className="btn btn--outline btn--sm" style={{ marginLeft: 'auto' }}>Edit</Link>
      </section>
      <nav className="card list" aria-label="Account">
        {LINKS.map((l) => (
          <Link key={l.to} to={l.to} className="list-row">
            <span className="list-row__icon"><Icon name={l.icon} size={18} /></span>
            <span style={{ flex: 1 }}><span style={{ display: 'block', fontWeight: 600 }}>{l.label}</span><span className="small muted">{l.hint}</span></span>
            <Icon name="right" size={18} />
          </Link>
        ))}
      </nav>
    </div>
  );
}
