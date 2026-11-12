import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { EmptyState, ErrorState, Icon, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { addDays, fmtDay, HotelImage, RatingBadge, SaveHotel, STATUS_TONE, stayQs, todayIso } from '../features/hotels/parts';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

const TABS = [['upcoming', 'Upcoming'], ['past', 'Past & cancelled'], ['saved', 'Saved']] as const;

/** The customer's hotel reservations and saved hotels (the shared Wishlist). */
export function HotelBookingsPage() {
  useThemeOverride('hotels');
  const [sp, setSp] = useSearchParams();
  const tab = TABS.find(([t]) => t === sp.get('tab'))?.[0] ?? 'upcoming';
  const list = useQuery({ queryKey: ['hotels', 'bookings', tab], queryFn: () => api.hotels.bookings(tab === 'past' ? 'past' : 'upcoming'), enabled: tab !== 'saved' });
  const saved = useQuery({ queryKey: ['hotels', 'saved'], queryFn: () => api.hotels.saved(), enabled: tab === 'saved' });
  const cur = tab === 'saved' ? saved : list;
  const nextStay = stayQs({ checkIn: addDays(todayIso(), 1), checkOut: addDays(todayIso(), 2), adults: 2, children: 0, rooms: 1 });

  return (
    <div className="ht-page" data-theme="hotels">
      <Link to="/hotels" className="ht-back"><Icon name="back" size={18} /> Hotels</Link>
      <h1 className="ht-title">My stays</h1>
      <div className="ht-seg" role="tablist" aria-label="My stays">
        {TABS.map(([t, l]) => <button key={t} type="button" role="tab" aria-selected={t === tab} onClick={() => setSp({ tab: t }, { replace: true })}>{l}</button>)}
      </div>
      {cur.isError ? <ErrorState error={cur.error} onRetry={() => cur.refetch()} /> : cur.isPending ? <Skeleton height={240} radius={20} /> : tab === 'saved' ? (
        saved.data!.results.length === 0 ? <EmptyState icon="heart" title="No saved hotels" message="Tap the heart on a hotel to keep it here." action={<Link to="/hotels" className="btn btn--primary">Find a stay</Link>} /> : (
          <div className="ht-savedgrid">{saved.data!.results.map((h) => (
            <Link key={h.id} to={`/hotels/${h.id}?${nextStay}`} className="ht-saved" style={{ ['--ht-accent' as string]: h.accent }}>
              <HotelImage src={h.imageUrl} name={h.name} accent={h.accent} />
              <span className="ht-saved__body"><span className="ht-kicker">{h.typeLabel} · {h.destination}</span><strong>{h.name}</strong>
                <RatingBadge r={h.rating} />{h.fromPrice && <span className="small ht-muted">Rooms from {formatMoney(h.fromPrice)}/night before tax</span>}</span>
              <SaveHotel id={h.id} favoriteId={h.favoriteId} name={h.name} />
            </Link>
          ))}</div>
        )
      ) : list.data!.results.length === 0 ? (
        <EmptyState icon="hotel" title={tab === 'upcoming' ? 'No upcoming stays' : 'No past stays'} action={<Link to="/hotels" className="btn btn--primary">Find a stay</Link>} />
      ) : (
        <ul className="ht-blist">{list.data!.results.map((b) => (
          <li key={b.id}>
            <Link to={`/hotels/bookings/${b.id}`} className="ht-brow" style={{ ['--ht-accent' as string]: b.property.accent }}>
              <HotelImage src={b.property.imageUrl} name={b.property.name} accent={b.property.accent} className="ht-brow__img" />
              <span className="ht-brow__main"><strong>{b.property.name}</strong>
                <span className="small ht-muted">{fmtDay(b.checkIn)} – {fmtDay(b.checkOut)} · {b.nights} night{b.nights > 1 ? 's' : ''} · {b.number}</span>
                <span className={`ht-status ht-status--${STATUS_TONE[b.status] ?? 'warn'} small`}>{b.statusLabel}</span></span>
              <span className="ht-brow__end">{formatMoney(b.total)}</span>
            </Link>
            {b.status === 'completed' && !b.reviewed && <Link to={`/hotels/bookings/${b.id}`} className="ht-link small ht-brow__act">Review your stay</Link>}
          </li>
        ))}</ul>
      )}
    </div>
  );
}
