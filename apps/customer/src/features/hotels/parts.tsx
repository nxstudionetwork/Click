import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError, type HotelCard, type HotelRating, type StayQuery } from '@click/api';
import { useAuth } from '../../auth/AuthProvider';
import { Button, Icon, type IconName, Sheet, useToast } from '../../components/ui';
import { api } from '../../lib/api';
import { formatMoney } from '../../lib/format';

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
export const addDays = (s: string, n: number) => { const d = new Date(`${s}T00:00:00`); d.setDate(d.getDate() + n); return iso(d); };
export const todayIso = () => iso(new Date());

/** The stay (dates and party) lives in the URL so results, the hotel and booking pages share it and links can be shared. */
export function stayFrom(sp: URLSearchParams): StayQuery {
  const ci = sp.get('check_in') && sp.get('check_in')! >= todayIso() ? sp.get('check_in')! : addDays(todayIso(), 1);
  const co = sp.get('check_out') && sp.get('check_out')! > ci ? sp.get('check_out')! : addDays(ci, 1);
  const n = (k: string, d: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, Number(sp.get(k)) || d));
  return { checkIn: ci, checkOut: co, adults: n('adults', 2, 1, 48), children: Math.min(24, Math.max(0, Number(sp.get('children')) || 0)), rooms: n('rooms', 1, 1, 8) };
}
export const stayQs = (s: StayQuery) => new URLSearchParams({ check_in: s.checkIn, check_out: s.checkOut, adults: String(s.adults), children: String(s.children), rooms: String(s.rooms) }).toString();
export const nightsOf = (s: StayQuery) => Math.round((new Date(`${s.checkOut}T00:00:00`).getTime() - new Date(`${s.checkIn}T00:00:00`).getTime()) / 86400000);
export const fmtDay = (d: string, opts: Intl.DateTimeFormatOptions = { weekday: 'short', day: 'numeric', month: 'short' }) =>
  new Date(`${d}T00:00:00`).toLocaleDateString('en-IN', opts);
export const partyLabel = (s: StayQuery) =>
  `${s.adults} adult${s.adults > 1 ? 's' : ''}${s.children ? ` · ${s.children} child${s.children > 1 ? 'ren' : ''}` : ''} · ${s.rooms} room${s.rooms > 1 ? 's' : ''}`;

export function Stars({ n }: { n: number | null }) {
  if (!n) return null;
  return <span className="ht-stars" aria-label={`${n}-star property`}>{Array.from({ length: n }, (_, i) => <Icon key={i} name="star" size={11} />)}</span>;
}

export function RatingBadge({ r, big = false }: { r: HotelRating | { average: string; count: number; label?: string } | null; big?: boolean }) {
  if (!r) return <span className="ht-new small">New on Click.</span>;
  return (
    <span className={`ht-score${big ? ' ht-score--big' : ''}`}>
      <span className="ht-score__n">{r.average}</span>
      <span className="ht-score__t"><strong>{'label' in r && r.label ? r.label : 'Rated'}</strong><span>{r.count} verified stay{r.count === 1 ? '' : 's'}</span></span>
    </span>
  );
}

/** A designed placeholder until the property uploads its own photos (never a generated or borrowed image). */
export function HotelImage({ src, name, accent, className = '' }: { src: string; name: string; accent: string; className?: string }) {
  if (src) return <img className={`ht-img ${className}`} src={src} alt={name} loading="lazy" />;
  const initials = name.split(' ').filter((w) => /^[A-Z]/.test(w)).map((w) => w[0]).slice(0, 2).join('');
  return (
    <span className={`ht-img ht-img--ph ${className}`} style={{ ['--ht-accent' as string]: accent }} role="img" aria-label={`${name} (no photos yet)`}>
      <span className="ht-img__mono" aria-hidden="true">{initials}</span>
      <span className="ht-img__note">Photos coming soon</span>
    </span>
  );
}

export function SaveHotel({ id, favoriteId, name }: { id: string; favoriteId?: string | null; name: string }) {
  const { status } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: async () => (favoriteId ? api.customer.wishlist.remove(favoriteId) : api.customer.wishlist.add({ hotelId: id })),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['hotels'] }); qc.invalidateQueries({ queryKey: ['customer', 'wishlist'] }); toast(favoriteId ? `Removed ${name}` : `Saved ${name} to your wishlist`); },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t update.', 'error'),
  });
  if (status !== 'authenticated') return null;
  return (
    <button type="button" className={`ht-save${favoriteId ? ' is-on' : ''}`} aria-pressed={!!favoriteId} disabled={m.isPending}
      aria-label={favoriteId ? `Remove ${name} from wishlist` : `Save ${name} to wishlist`} onClick={(e) => { e.preventDefault(); e.stopPropagation(); m.mutate(); }}>
      <Icon name="heart" size={18} />
    </button>
  );
}

export function HotelCardView({ h, stay, compare, onCompare }: { h: HotelCard; stay: StayQuery; compare?: boolean; onCompare?: () => void }) {
  const to = `/hotels/${h.id}?${stayQs(stay)}`;
  return (
    <article className="ht-card" style={{ ['--ht-accent' as string]: h.accent }}>
      <Link to={to} className="ht-card__media" aria-label={`${h.name}: view rooms`} tabIndex={-1}>
        <HotelImage src={h.imageUrl} name={h.name} accent={h.accent} />
        {h.highlights[0] && <span className="ht-flag">{h.highlights[0]}</span>}
      </Link>
      <div className="ht-card__body">
        <div className="ht-card__head">
          <div>
            <span className="ht-kicker">{h.typeLabel}{h.starRating ? '' : ''} <Stars n={h.starRating} /></span>
            <h3><Link to={to}>{h.name}</Link></h3>
            <span className="small ht-muted"><Icon name="pin" size={12} /> {h.area}{h.distanceKm != null ? ` · ${h.distanceKm.toFixed(1)} km from ${h.distanceFrom}` : ''}</span>
          </div>
          <SaveHotel id={h.id} favoriteId={h.favoriteId} name={h.name} />
        </div>
        <RatingBadge r={h.rating} />
        <div className="ht-amen">{h.amenities.slice(0, 4).map((a) => <span key={a.slug}><Icon name={(a.icon || 'check') as IconName} size={12} /> {a.name}</span>)}</div>
        <div className="ht-badges">
          {h.freeCancellation && <span className="ht-badge ht-badge--ok"><Icon name="check" size={12} /> Free cancellation</span>}
          {h.breakfast && <span className="ht-badge">Breakfast included</span>}
          {h.payAtProperty && <span className="ht-badge">Pay at property option</span>}
          {h.offer && <span className="ht-badge ht-badge--gold">{h.offer}</span>}
          {h.highlights.slice(1).filter((x) => x !== 'Free cancellation').map((x) => <span key={x} className="ht-badge ht-badge--gold">{x}</span>)}
        </div>
        <div className="ht-card__foot">
          <div className="ht-price">
            <span className="small ht-muted">{h.room} · {h.mealLabel}</span>
            {h.price.beforeDiscount && <s className="small ht-muted">{formatMoney(String(Number(h.price.beforeDiscount) / h.price.nights / h.price.rooms))}</s>}
            <strong>{formatMoney(h.price.perNight)}<span className="small ht-muted"> /night</span></strong>
            <span className="small">{formatMoney(h.price.total)} total · {h.price.nights} night{h.price.nights > 1 ? 's' : ''} incl. taxes</span>
            {h.roomsLeft != null && <span className="small ht-warn">Only {h.roomsLeft} left at this price</span>}
          </div>
          <div className="ht-card__cta">
            {onCompare && <label className="ht-cmp small"><input type="checkbox" checked={!!compare} onChange={onCompare} /> Compare</label>}
            <Link to={to} className="ht-btn">View rooms</Link>
          </div>
        </div>
      </div>
    </article>
  );
}

export function GuestsPicker({ value, onChange, children }: { value: StayQuery; onChange: (s: StayQuery) => void; children?: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [d, setD] = useState(value);
  const row = (k: 'adults' | 'children' | 'rooms', label: string, hint: string, lo: number, hi: number) => (
    <div className="ht-step" key={k}>
      <span><strong>{label}</strong><span className="small ht-muted">{hint}</span></span>
      <span className="ht-step__ctl">
        <button type="button" aria-label={`Fewer ${label.toLowerCase()}`} disabled={d[k] <= lo} onClick={() => setD({ ...d, [k]: d[k] - 1 })}>−</button>
        <output aria-live="polite">{d[k]}</output>
        <button type="button" aria-label={`More ${label.toLowerCase()}`} disabled={d[k] >= hi} onClick={() => setD({ ...d, [k]: d[k] + 1 })}>+</button>
      </span>
    </div>
  );
  return (
    <>
      <button type="button" className="ht-field ht-field--btn" onClick={() => { setD(value); setOpen(true); }}>
        <span className="ht-field__label">Guests &amp; rooms</span><span className="ht-field__value">{partyLabel(value)}</span>{children}
      </button>
      <Sheet open={open} onClose={() => setOpen(false)} label="Guests and rooms">
        <div className="ht-sheet">
          <h2>Guests &amp; rooms</h2>
          {row('adults', 'Adults', '18 and over', Math.max(1, d.rooms), 48)}
          {row('children', 'Children', '0–17', 0, 24)}
          {row('rooms', 'Rooms', 'Each room needs an adult', 1, Math.min(8, d.adults))}
          <Button block onClick={() => { onChange(d); setOpen(false); }}>Done</Button>
        </div>
      </Sheet>
    </>
  );
}

export const STATUS_TONE: Record<string, string> = { confirmed: 'ok', completed: 'ok', pending_payment: 'warn', cancelled: 'bad', failed: 'bad' };
