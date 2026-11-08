import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthProvider';
import { SERVICE_GROUPS, SERVICES } from '../../config/services';
import { OfferCard } from '../../features/offers/OfferCard';
import { api } from '../../lib/api';
import { Icon, Sheet, type IconName } from '../ui';

const CUSTOMER: { to: string; label: string; icon: IconName }[] = [
  { to: '/orders', label: 'Orders', icon: 'receipt' },
  { to: '/bookings', label: 'Bookings', icon: 'ticket' },
  { to: '/wishlist', label: 'Wishlist', icon: 'heart' },
  { to: '/rewards', label: 'Rewards', icon: 'gift' },
  { to: '/wallet', label: 'Wallet', icon: 'wallet' },
  { to: '/offers', label: 'Offers', icon: 'tag' },
  { to: '/notifications', label: 'Notifications', icon: 'bell' },
  { to: '/activity', label: 'Activity', icon: 'history' },
];
const ACCOUNT: { to: string; label: string; icon: IconName }[] = [
  { to: '/account', label: 'Profile', icon: 'user' },
  { to: '/account/addresses', label: 'Addresses', icon: 'pin' },
  { to: '/account/payments', label: 'Payments', icon: 'card' },
  { to: '/settings', label: 'Settings', icon: 'settings' },
  { to: '/help', label: 'Help & Support', icon: 'help' },
];

/** The Click command centre: opens bottom-up from the Menu button. */
export function MenuHub({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { status } = useAuth();
  const authed = status === 'authenticated';
  const offers = useQuery({ queryKey: ['offers', 'all'], queryFn: () => api.catalog.offers(), enabled: open });
  const upcoming = useQuery({ queryKey: ['customer', 'bookings', 'upcoming'], queryFn: () => api.customer.bookings.list('upcoming'), enabled: open && authed });
  const nextBooking = upcoming.data?.results[0];

  return (
    <Sheet open={open} onClose={onClose} label="Click menu" variant="full">
      <div className="hub">
        <div className="spread hub__top">
          <h2>Everything on Click</h2>
          <button className="icon-btn" aria-label="Close menu" onClick={onClose}><Icon name="close" /></button>
        </div>

        {nextBooking && (
          <Link to={`/bookings/${nextBooking.id}`} className="hub__active" onClick={onClose}>
            <Icon name="ticket" /> <span><strong>Up next: {nextBooking.event.title}</strong><span className="small" style={{ display: 'block' }}>{new Date(nextBooking.show.startsAt).toLocaleString('en-IN', { weekday: 'short', hour: 'numeric', minute: '2-digit' })} · {nextBooking.show.venue.name}</span></span>
          </Link>
        )}

        {(offers.data?.results.length ?? 0) > 0 && (
          <section className="hub__section">
            <div className="spread"><h3>Offers for you</h3><Link to="/offers" onClick={onClose} className="small" style={{ color: 'var(--c-brand)', fontWeight: 600 }}>See all</Link></div>
            <div className="hub__offers" onClick={onClose}>{offers.data!.results.slice(0, 6).map((o) => <OfferCard key={o.id} offer={o} />)}</div>
          </section>
        )}

        {SERVICE_GROUPS.map((g) => {
          const items = SERVICES.filter((s) => s.group === g.id);
          if (!items.length) return null;
          return (
            <section key={g.id} className="hub__section">
              <h3>{g.label}</h3>
              <div className="hub__grid">
                {items.map((s) => (
                  <Link key={s.id} to={s.path} onClick={onClose} data-tile={s.theme} className={`hub__tile ${s.status === 'soon' ? 'hub__tile--soon' : ''}`}>
                    <span className="hub__icon"><Icon name={s.icon} /></span>
                    <span className="hub__label">{s.name}</span>
                    {s.status === 'soon' && <span className="hub__soon">Soon</span>}
                  </Link>
                ))}
                {g.id === 'content' && (
                  <Link to="/buddy" onClick={onClose} data-tile="buddy" className="hub__tile">
                    <span className="hub__icon"><Icon name="sparkle" /></span><span className="hub__label">Buddy AI</span>
                  </Link>
                )}
              </div>
            </section>
          );
        })}

        <section className="hub__section">
          <h3>Your Click</h3>
          <div className="hub__links">{CUSTOMER.map((l) => <Link key={l.to} to={l.to} onClick={onClose} className="hub__link"><Icon name={l.icon} size={18} />{l.label}</Link>)}</div>
        </section>
        <section className="hub__section">
          <h3>Account</h3>
          <div className="hub__links">{ACCOUNT.map((l) => <Link key={l.to} to={l.to} onClick={onClose} className="hub__link"><Icon name={l.icon} size={18} />{l.label}</Link>)}</div>
        </section>
      </div>
    </Sheet>
  );
}
