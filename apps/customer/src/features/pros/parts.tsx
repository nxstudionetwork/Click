import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError, type PricingModel, type ProCard as Pro, type ServiceBookingStatus } from '@click/api';
import { useAuth } from '../../auth/AuthProvider';
import { Icon, type IconName, useToast } from '../../components/ui';
import { api } from '../../lib/api';

export const PRICING_HINT: Record<PricingModel, string> = {
  fixed: 'Fixed price', starting: 'Starting price · final after inspection, any increase needs your approval',
  hourly: 'Hourly · never billed beyond the hours you book', quote: 'Quote after inspection · work starts only when you approve',
};

/** The professional's own uploaded photo, or a neutral monogram (never a generated or borrowed face). */
export function ProAvatar({ p, size = 64 }: { p: Pick<Pro, 'name' | 'photoUrl' | 'accent'>; size?: number }) {
  const initials = p.name.split(' ').map((w) => w[0]).slice(0, 2).join('');
  return (
    <span className="sv-avatar" style={{ width: size, height: size, ['--sv-accent' as string]: p.accent }}>
      {p.photoUrl ? <img src={p.photoUrl} alt={`${p.name}`} loading="lazy" /> : <span aria-hidden="true">{initials}</span>}
      {!p.photoUrl && <span className="sr-only">{p.name} (no photo yet)</span>}
    </span>
  );
}

export function Rating({ r, compact = false }: { r: Pro['rating']; compact?: boolean }) {
  if (!r) return <span className="sv-muted small">New on Click.</span>;
  return <span className="sv-rating"><Icon name="star" size={13} /> {r.average}{!compact && <span className="sv-muted"> ({r.count})</span>}</span>;
}

export function AvailabilityPill({ a, label }: { a: Pro['availability']; label: string }) {
  return <span className={`sv-avail sv-avail--${a}`}>{a === 'now' && <span className="sv-dot" aria-hidden="true" />}{label}</span>;
}

export function FavoriteButton({ id, favoriteId, name, onChange }: { id: string; favoriteId: string | null | undefined; name: string; onChange?: () => void }) {
  const { status } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: async () => (favoriteId ? api.customer.wishlist.remove(favoriteId) : api.customer.wishlist.add({ providerId: id })),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['services'] });
      qc.invalidateQueries({ queryKey: ['customer', 'wishlist'] });
      toast(favoriteId ? `Removed ${name} from My Professionals` : `Saved ${name} to My Professionals`);
      onChange?.();
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t update.', 'error'),
  });
  if (status !== 'authenticated') return null;
  return (
    <button type="button" className={`sv-fav${favoriteId ? ' is-on' : ''}`} aria-pressed={!!favoriteId} disabled={m.isPending}
      aria-label={favoriteId ? `Remove ${name} from My Professionals` : `Save ${name} to My Professionals`}
      onClick={(e) => { e.preventDefault(); e.stopPropagation(); m.mutate(); }}>
      <Icon name="heart" size={18} />
    </button>
  );
}

export function ProCardView({ p, job, wide = false, extra }: { p: Pro; job?: string | null; wide?: boolean; extra?: ReactNode }) {
  const to = `/services/pro/${p.id}${job ? `?job=${job}` : ''}`;
  return (
    <article className={`sv-pro${wide ? ' sv-pro--wide' : ''}`} style={{ ['--sv-accent' as string]: p.accent }}>
      <Link to={to} className="sv-pro__link" aria-label={`${p.name}, ${p.profession}`}>
        <div className="sv-pro__top">
          <ProAvatar p={p} size={wide ? 72 : 64} />
          <div className="sv-pro__id">
            <strong>{p.name}</strong>
            <span className="small">{p.profession}{p.verified && <span className="sv-verified"><Icon name="shield" size={12} /> Verified</span>}</span>
            <Rating r={p.rating} />
          </div>
        </div>
        <div className="sv-pro__facts small">
          {p.experienceYears != null && <span>{p.experienceYears} yrs experience</span>}
          {p.jobsCompleted > 0 && <span>{p.jobsCompleted.toLocaleString('en-IN')} jobs on Click.</span>}
          {p.distanceKm != null && <span>{p.distanceKm.toFixed(1)} km</span>}
        </div>
        <div className="sv-pro__foot">
          <AvailabilityPill a={p.availability} label={p.availability === 'now' && p.etaMinutes ? `Available now · ~${p.etaMinutes} min` : p.availabilityLabel} />
          <span className="sv-pro__price">{p.priceLabel}</span>
        </div>
      </Link>
      <div className="sv-pro__actions">
        <FavoriteButton id={p.id} favoriteId={p.favoriteId} name={p.name} />
        {extra}
        <Link to={`/services/book?pro=${p.id}${job ? `&job=${job}` : ''}`} className="sv-btn sv-btn--sm">Book</Link>
      </div>
    </article>
  );
}

const ICON: Record<string, IconName> = {};
export const catIcon = (icon: string): IconName => (ICON[icon] ?? (icon as IconName)) || 'wrench';

export const STATUS_STEPS: { status: ServiceBookingStatus; label: string }[] = [
  { status: 'requested', label: 'Requested' }, { status: 'confirmed', label: 'Professional confirmed' }, { status: 'on_the_way', label: 'On the way' },
  { status: 'arrived', label: 'Arrived' }, { status: 'in_progress', label: 'Work in progress' }, { status: 'completed', label: 'Work completed' },
  { status: 'paid', label: 'Paid' },
];

export function Section({ title, kicker, children, action }: { title: string; kicker?: string; children: ReactNode; action?: ReactNode }) {
  return (
    <section className="sv-sec">
      <header className="sv-sec__head"><div>{kicker && <span className="sv-kicker">{kicker}</span>}<h2>{title}</h2></div>{action}</header>
      {children}
    </section>
  );
}
