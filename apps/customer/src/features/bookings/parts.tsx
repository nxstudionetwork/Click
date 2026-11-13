import { Link } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError, type AttractionCard, type Reservation } from '@click/api';
import { useAuth } from '../../auth/AuthProvider';
import { Icon, type IconName, useToast } from '../../components/ui';
import { api } from '../../lib/api';
import { formatMoney } from '../../lib/format';

const TZ = 'Asia/Kolkata';
export const todayIso = () => new Date().toLocaleDateString('en-CA', { timeZone: TZ });
export const fmtDay = (d: string, opts: Intl.DateTimeFormatOptions = { weekday: 'short', day: 'numeric', month: 'short' }) =>
  new Date(d.length === 10 ? `${d}T12:00:00` : d).toLocaleDateString('en-IN', { ...opts, timeZone: TZ });
export const fmtSlot = (t: string | null) => {
  if (!t) return 'Any time that day';
  const [h, m] = t.split(':').map(Number);
  return new Date(2000, 0, 1, h, m).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', hour12: true });
};
export const STATUS_TONE: Record<string, string> = { confirmed: 'ok', completed: 'ok', pending_payment: 'warn', cancelled: 'bad', failed: 'bad' };
export const GROUP_ICON: Record<string, IconName> = { spiritual: 'temple', tourist: 'compass', parks: 'sparkle', experiences: 'ticket' };
export const KIND_ICON: Record<Reservation['kind'], IconName> = {
  temple: 'temple', attraction: 'compass', experience: 'ticket', travel: 'bus', hotel: 'hotel', show: 'film', event: 'gift', service: 'wrench',
};

/** A designed placeholder until the provider uploads its own photos (never a generated or borrowed image). */
export function PlaceImage({ src, name, accent, kind, className = '' }: { src: string | null; name: string; accent: string; kind: string; className?: string }) {
  if (src) return <img className={`bk-img ${className}`} src={src} alt={name} loading="lazy" />;
  return (
    <span className={`bk-img bk-img--ph ${className}`} style={{ ['--bk-accent' as string]: accent }} role="img" aria-label={`${name} (no photos yet)`}>
      <Icon name={kind === 'temple' ? 'temple' : ['water_park', 'theme_park', 'zoo', 'aquarium', 'garden', 'nature_park', 'adventure_park'].includes(kind) ? 'sparkle'
        : ['boat_ride', 'cruise'].includes(kind) ? 'compass' : ['museum', 'gallery', 'science_centre', 'planetarium'].includes(kind) ? 'book' : 'pin'} size={34} />
    </span>
  );
}

export function SavePlace({ id, favoriteId, name }: { id: string; favoriteId?: string | null; name: string }) {
  const { status } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: async () => (favoriteId ? api.customer.wishlist.remove(favoriteId) : api.customer.wishlist.add({ attractionId: id })),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bookings'] }); qc.invalidateQueries({ queryKey: ['customer', 'wishlist'] }); toast(favoriteId ? `Removed ${name}` : `Saved ${name} to your wishlist`); },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t update.', 'error'),
  });
  if (status !== 'authenticated') return null;
  return (
    <button type="button" className={`bk-save${favoriteId ? ' is-on' : ''}`} aria-pressed={!!favoriteId} disabled={m.isPending}
      aria-label={favoriteId ? `Remove ${name} from wishlist` : `Save ${name} to wishlist`} onClick={(e) => { e.preventDefault(); e.stopPropagation(); m.mutate(); }}>
      <Icon name="heart" size={18} />
    </button>
  );
}

export function PlaceCard({ a, wide }: { a: AttractionCard; wide?: boolean }) {
  return (
    <article className={`bk-card${wide ? ' bk-card--wide' : ''}`} style={{ ['--bk-accent' as string]: a.accent }}>
      <Link to={`/bookings/places/${a.slug}`} className="bk-card__media" tabIndex={-1} aria-hidden="true">
        <PlaceImage src={a.imageUrl} name={a.name} accent={a.accent} kind={a.kind} />
        <span className={`bk-pill ${a.bookable ? 'bk-pill--book' : 'bk-pill--info'}`}>{a.bookable ? 'Bookable through Click.' : 'Information available'}</span>
      </Link>
      <div className="bk-card__body">
        <div className="bk-card__head">
          <div>
            <span className="bk-kicker">{a.kindLabel}{a.deity ? ` · ${a.deity}` : ''}</span>
            <h3><Link to={`/bookings/places/${a.slug}`}>{a.name}</Link></h3>
            <span className="small bk-muted"><Icon name="pin" size={12} /> {a.area ? `${a.area}, ` : ''}{a.city}{a.distanceKm != null ? ` · ${a.distanceKm} km` : ''}</span>
          </div>
          <SavePlace id={a.id} favoriteId={a.favoriteId} name={a.name} />
        </div>
        {a.bookable ? (
          <>
            <div className="bk-tags">{a.bookingTypes.slice(0, 3).map((t) => <span key={t}>{t} available</span>)}{a.verified && <span className="bk-ok"><Icon name="shield" size={11} /> Verified provider</span>}</div>
            <div className="bk-card__foot">
              <span>{a.fromPrice != null ? (Number(a.fromPrice) === 0 ? <strong>Free</strong> : <><span className="small bk-muted">from </span><strong>{formatMoney(a.fromPrice)}</strong></>) : null}
                {a.rating && <span className="small bk-muted"> · ★ {a.rating.average} ({a.rating.count})</span>}
                {a.nextAvailable && <span className="small bk-muted"> · next {fmtDay(a.nextAvailable, { day: 'numeric', month: 'short' })}</span>}</span>
              <Link to={`/bookings/places/${a.slug}`} className="bk-btn bk-btn--sm">Book now</Link>
            </div>
          </>
        ) : (
          <div className="bk-card__foot"><span className="small bk-muted">{a.officialSource}</span><Link to={`/bookings/places/${a.slug}`} className="bk-btn bk-btn--ghost bk-btn--sm">View details</Link></div>
        )}
      </div>
    </article>
  );
}

export function Stepper({ label, note, price, value, min = 0, max, onChange }: {
  label: string; note?: string; price: string; value: number; min?: number; max: number; onChange: (n: number) => void;
}) {
  return (
    <div className="bk-step">
      <span><strong>{label}</strong><span className="small bk-muted">{note ? `${note} · ` : ''}{Number(price) === 0 ? 'Free' : formatMoney(price)}</span></span>
      <span className="bk-step__ctl">
        <button type="button" aria-label={`Fewer ${label}`} disabled={value <= min} onClick={() => onChange(value - 1)}>−</button>
        <output aria-live="polite" aria-label={`${label}: ${value}`}>{value}</output>
        <button type="button" aria-label={`More ${label}`} disabled={value >= max} onClick={() => onChange(value + 1)}>+</button>
      </span>
    </div>
  );
}
