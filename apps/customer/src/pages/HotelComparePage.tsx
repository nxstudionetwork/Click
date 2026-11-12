import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ErrorState, Icon, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { fmtDay, HotelImage, partyLabel, stayFrom, stayQs } from '../features/hotels/parts';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

/** Compare 2–4 stays for the same dates and party: cheapest bookable room, its policy and payment, rating, amenities. */
export function HotelComparePage() {
  useThemeOverride('hotels');
  const [sp] = useSearchParams();
  const stay = stayFrom(sp);
  const ids = (sp.get('ids') ?? '').split(',').filter(Boolean).slice(0, 4);
  const q = useQuery({ queryKey: ['hotels', 'compare', ids, stay], queryFn: () => api.hotels.compare(ids, stay), enabled: ids.length >= 2 });
  const rows = q.data?.results ?? [];
  const allAmen = [...new Set(rows.flatMap((r) => r.amenities))];
  return (
    <div className="ht-page" data-theme="hotels">
      <button type="button" className="ht-back" onClick={() => history.back()}><Icon name="back" size={18} /> Results</button>
      <h1 className="ht-title">Compare stays</h1>
      <p className="small ht-muted">{fmtDay(stay.checkIn)} – {fmtDay(stay.checkOut)} · {partyLabel(stay)}</p>
      {q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isPending ? <Skeleton height={320} radius={22} /> : (
        <div className="ht-cmpwrap" role="region" aria-label="Comparison" tabIndex={0}>
          <table className="ht-cmptable ht-cmptable--stays">
            <thead><tr><th scope="col"><span className="sr-only">Detail</span></th>{rows.map((r) => (
              <th key={r.id} scope="col"><HotelImage src={r.imageUrl} name={r.name} accent="#d9bf8c" className="ht-cmp__img" /><Link to={`/hotels/${r.id}?${stayQs(stay)}`}>{r.name}</Link></th>
            ))}</tr></thead>
            <tbody>
              <tr><th scope="row">Type</th>{rows.map((r) => <td key={r.id}>{r.typeLabel}{r.starRating ? ` · ${r.starRating}★` : ''}</td>)}</tr>
              <tr><th scope="row">Area</th>{rows.map((r) => <td key={r.id}>{r.area}</td>)}</tr>
              <tr><th scope="row">Guest rating</th>{rows.map((r) => <td key={r.id}>{r.rating ? `${r.rating.average}/10 (${r.rating.count})` : 'New'}</td>)}</tr>
              <tr><th scope="row">Cheapest room</th>{rows.map((r) => <td key={r.id}>{r.cheapest ? `${r.cheapest.room} · ${r.cheapest.meal}` : 'Not available'}</td>)}</tr>
              <tr><th scope="row">Total incl. tax</th>{rows.map((r) => <td key={r.id}><strong>{r.cheapest ? formatMoney(r.cheapest.total) : '—'}</strong></td>)}</tr>
              <tr><th scope="row">Cancellation</th>{rows.map((r) => <td key={r.id} className="small">{r.cheapest?.policy ?? '—'}</td>)}</tr>
              <tr><th scope="row">Payment</th>{rows.map((r) => <td key={r.id}>{r.cheapest?.payment ?? '—'}</td>)}</tr>
              <tr><th scope="row">Check-in</th>{rows.map((r) => <td key={r.id}>From {r.checkInTime}</td>)}</tr>
              {allAmen.map((a) => <tr key={a}><th scope="row">{a}</th>{rows.map((r) => <td key={r.id}>{r.amenities.includes(a) ? <Icon name="check" size={14} /> : <span className="ht-muted">—</span>}</td>)}</tr>)}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
