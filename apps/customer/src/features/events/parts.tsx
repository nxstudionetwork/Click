import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError, type EventPackageInfo, type EventProviderCard, type LiveEvent } from '@click/api';
import { useAuth } from '../../auth/AuthProvider';
import { Icon, type IconName, useToast } from '../../components/ui';
import { api } from '../../lib/api';
import { formatMoney } from '../../lib/format';

export const evIcon = (name: string): IconName => (name || 'sparkle') as IconName;

export const fmtDate = (iso: string | null, opts: Intl.DateTimeFormatOptions = { weekday: 'short', day: 'numeric', month: 'short' }) =>
  iso ? new Date(`${iso.length === 10 ? `${iso}T00:00:00` : iso}`).toLocaleDateString('en-IN', opts) : 'Flexible date';

/** The provider's own logo, or a monogram — never a generated or borrowed image. */
export function ProviderMark({ p, size = 56 }: { p: { name: string; logoUrl: string; accent: string }; size?: number }) {
  const initials = p.name.replace(/[^A-Za-z ]/g, '').split(' ').filter(Boolean).map((w) => w[0]).slice(0, 2).join('');
  return (
    <span className="ev-mark" style={{ width: size, height: size, ['--ev-accent' as string]: p.accent }}>
      {p.logoUrl ? <img src={p.logoUrl} alt="" loading="lazy" /> : <span aria-hidden="true">{initials}</span>}
    </span>
  );
}

export function RatingLine({ r }: { r: { average: string; count: number } | null }) {
  if (!r) return <span className="ev-muted small">New on Click.</span>;
  return <span className="ev-rating"><Icon name="star" size={13} /> {r.average} <span className="ev-muted">({r.count})</span></span>;
}

export function Section({ title, kicker, action, children, id }: { title: string; kicker?: string; action?: ReactNode; children: ReactNode; id?: string }) {
  return (
    <section className="ev-sec" id={id} aria-labelledby={id ? `${id}-h` : undefined}>
      <header className="ev-sec__head"><div>{kicker && <span className="ev-kicker">{kicker}</span>}<h2 id={id ? `${id}-h` : undefined}>{title}</h2></div>{action}</header>
      {children}
    </section>
  );
}

type FavTarget = { eventProviderId: string } | { eventPackageId: string };

/** Save to / remove from the shared Click. Wishlist. */
export function SaveButton({ target, favoriteId, name }: { target: FavTarget; favoriteId?: string | null; name: string }) {
  const { status } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: async () => (favoriteId ? api.customer.wishlist.remove(favoriteId) : api.customer.wishlist.add(target)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['eventhub'] });
      qc.invalidateQueries({ queryKey: ['customer', 'wishlist'] });
      toast(favoriteId ? `Removed ${name} from your saved list` : `Saved ${name}`);
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t update.', 'error'),
  });
  if (status !== 'authenticated') return null;
  return (
    <button type="button" className={`ev-save${favoriteId ? ' is-on' : ''}`} aria-pressed={!!favoriteId} disabled={m.isPending}
      aria-label={favoriteId ? `Remove ${name} from saved` : `Save ${name}`} onClick={(e) => { e.preventDefault(); e.stopPropagation(); m.mutate(); }}>
      <Icon name="heart" size={18} />
    </button>
  );
}

export function ProviderCardView({ p, query = '', extra, compact = false }: { p: EventProviderCard; query?: string; extra?: ReactNode; compact?: boolean }) {
  const to = `/events/providers/${p.id}${query}`;
  return (
    <article className={`ev-card${compact ? ' ev-card--compact' : ''}`} style={{ ['--ev-accent' as string]: p.accent }}>
      <Link to={to} className="ev-card__link" aria-label={`${p.name}, ${p.kindLabel}`}>
        <div className="ev-card__band">{p.coverUrl ? <img src={p.coverUrl} alt="" loading="lazy" /> : <span className="ev-card__pattern" aria-hidden="true" />}
          {p.featured && <span className="ev-badge ev-badge--gold">Featured</span>}
        </div>
        <div className="ev-card__body">
          <div className="ev-card__id">
            <ProviderMark p={p} size={52} />
            <div>
              <strong>{p.name}</strong>
              <span className="small ev-muted">{p.kindLabel}{p.venue ? ` · ${p.venue.spaceType}` : ''}{p.verified && <span className="ev-verified"><Icon name="shield" size={12} /> Verified</span>}</span>
              <RatingLine r={p.rating} />
            </div>
          </div>
          {p.tagline && <p className="small ev-tagline">{p.tagline}</p>}
          <div className="ev-chips">{(p.venue ? p.venue.amenities : p.services.map((s) => s.name)).slice(0, 4).map((s) => <span key={s} className="ev-chip">{s}</span>)}</div>
          <div className="ev-facts small">
            {p.venue && <span><Icon name="team" size={13} /> {p.venue.seated}–{p.venue.floating} guests</span>}
            {p.eventsCompleted > 0 && <span>{p.eventsCompleted} events on Click.</span>}
            {p.experienceYears != null && !p.venue && <span>{p.experienceYears} yrs</span>}
            <span><Icon name="pin" size={13} /> {p.area}{p.distanceKm != null ? ` · ${p.distanceKm.toFixed(1)} km` : ''}</span>
          </div>
          {p.response && <span className="small ev-muted"><Icon name="clock" size={12} /> {p.response}</span>}
          <div className="ev-card__foot">
            {p.availability ? <span className={`ev-avail ev-avail--${p.availability.state}`}>{p.availability.label}</span> : <span />}
            <span className="ev-price">{p.priceFrom ? p.priceFrom.label : 'Quote on request'}</span>
          </div>
        </div>
      </Link>
      <div className="ev-card__actions">
        <SaveButton target={{ eventProviderId: p.id }} favoriteId={p.favoriteId} name={p.name} />
        {extra ?? <Link to={to} className="ev-btn ev-btn--sm">View {p.kind === 'venue' ? 'venue' : 'profile'}</Link>}
      </div>
    </article>
  );
}

export function PackageCardView({ pkg, action, showProvider = false }: { pkg: EventPackageInfo; action?: ReactNode; showProvider?: boolean }) {
  return (
    <article className="ev-pkg" style={{ ['--ev-accent' as string]: pkg.provider?.accent ?? '#c084fc' }}>
      <header>
        <div>
          {showProvider && pkg.provider && <Link to={`/events/providers/${pkg.provider.id}`} className="ev-kicker ev-pkg__by">{pkg.provider.name}{pkg.provider.verified ? ' · Verified' : ''}</Link>}
          <h3>{pkg.name}</h3>
          <span className="small ev-muted">{pkg.minGuests === pkg.maxGuests ? `${pkg.minGuests} guest${pkg.minGuests > 1 ? 's' : ''}` : `${pkg.minGuests}–${pkg.maxGuests} guests`} · {pkg.durationHours} hrs</span>
        </div>
        <SaveButton target={{ eventPackageId: pkg.id }} favoriteId={pkg.favoriteId} name={pkg.name} />
      </header>
      <ul className="ev-includes">{pkg.includes.slice(0, 5).map((i) => <li key={i}><Icon name="check" size={13} /> {i}</li>)}</ul>
      {pkg.addons.length > 0 && <p className="small ev-muted">Add-ons: {pkg.addons.map((a) => `${a.name} (+${formatMoney(a.price)}${a.perGuest ? '/guest' : ''})`).join(', ')}</p>}
      <footer><span className="ev-price ev-price--lg">{pkg.priceLabel}{pkg.basis === 'per_guest' && <span className="small ev-muted"> per guest</span>}</span>{action}</footer>
    </article>
  );
}

export function LiveEventCard({ e }: { e: LiveEvent }) {
  return (
    <Link to={e.path} className="ev-live">
      <span className="ev-live__img">{e.imageUrl ? <img src={e.imageUrl} alt="" loading="lazy" /> : <Icon name="ticket" size={34} />}</span>
      <span className="ev-live__body">
        <span className="ev-kicker">{e.category}</span>
        <strong>{e.title}</strong>
        <span className="small ev-muted">{new Date(e.startsAt).toLocaleString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })}{e.shows > 1 ? ` · ${e.shows} shows` : ''}</span>
        <span className="small ev-muted"><Icon name="pin" size={12} /> {e.venue}, {e.area}{e.distanceKm != null ? ` · ${e.distanceKm.toFixed(1)} km` : ''}</span>
        <span className="ev-live__foot"><span className="ev-price">{e.priceFrom ? `From ${formatMoney(e.priceFrom)}` : ''}</span><span className="ev-link small">View details</span></span>
      </span>
    </Link>
  );
}

export const BOOKING_STEPS = [
  { status: 'payment_pending', label: 'Booking made' }, { status: 'confirmed', label: 'Confirmed & paid' }, { status: 'preparing', label: 'Team preparing' },
  { status: 'in_progress', label: 'Event in progress' }, { status: 'completed', label: 'Completed' },
] as const;

export function Stars({ value, onChange, label }: { value: number; onChange: (n: number) => void; label: string }) {
  return (
    <div className="ev-stars" role="radiogroup" aria-label={label}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button key={n} type="button" role="radio" aria-checked={value === n} aria-label={`${n} star${n > 1 ? 's' : ''}`} className={n <= value ? 'is-on' : ''} onClick={() => onChange(n)}>
          <Icon name="star" size={22} />
        </button>
      ))}
    </div>
  );
}
