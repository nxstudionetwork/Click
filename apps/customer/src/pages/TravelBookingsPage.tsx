import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQueries, useQuery } from '@tanstack/react-query';
import { EmptyState, ErrorState, Icon, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { fmtDate, fmtDur, fmtTime, modeOf, searchFrom, STATUS_TONE } from '../features/travel/parts';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

const TABS = [['upcoming', 'Upcoming'], ['past', 'Completed'], ['cancelled', 'Cancelled']] as const;

/** My journeys: the customer's travel tickets (the same records the central Bookings list shows). */
export function TravelBookingsPage() {
  useThemeOverride('travel');
  const [tab, setTab] = useState<(typeof TABS)[number][0]>('upcoming');
  const q = useQuery({ queryKey: ['travel', 'bookings', tab], queryFn: () => api.travel.bookings(tab) });
  return (
    <div className="tv-page" data-theme="travel">
      <Link to="/travel" className="tv-backlink"><Icon name="back" size={18} /> Travel</Link>
      <h1 className="tv-title">My journeys</h1>
      <div className="tv-tabs" role="tablist">{TABS.map(([k, l]) => <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? 'is-on' : ''} onClick={() => setTab(k)}>{l}</button>)}</div>
      {q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !q.data ? <Skeleton height={120} radius={18} /> : q.data.results.length === 0
        ? <EmptyState icon="bus" title={tab === 'upcoming' ? 'No upcoming journeys' : tab === 'past' ? 'No completed journeys yet' : 'Nothing cancelled'} action={<Link className="tv-btn" to="/travel">Plan a journey</Link>} />
        : <ul className="tv-mylist">{q.data.results.map((b) => (
          <li key={b.id}><Link to={`/travel/bookings/${b.id}`} className="tv-myrow">
            <Icon name={modeOf(b.mode).icon} size={20} />
            <span><strong>{b.from.city} → {b.to.city}</strong><span className="small tv-muted">{fmtDate(b.departsAt)} · {fmtTime(b.departsAt)} · {b.operator} · {b.passengersCount} passenger{b.passengersCount > 1 ? 's' : ''}{b.pnr ? ` · PNR ${b.pnr}` : ''}</span></span>
            <span className="tv-myrow__end"><span className={`tv-status tv-status--${STATUS_TONE[b.status] ?? 'warn'}`}>{b.statusLabel}</span><strong className="small">{formatMoney(b.total)}</strong></span>
          </Link></li>
        ))}</ul>}
    </div>
  );
}

/** Compare 2–3 options of the same transport type side by side (fetched fresh from the server). */
export function TravelComparePage() {
  useThemeOverride('travel');
  const [sp] = useSearchParams();
  const s = searchFrom(sp);
  const ids = (sp.get('ids') ?? '').split(',').filter(Boolean).slice(0, 3);
  const seats = s.adults + s.children;
  const qs = useQueries({ queries: ids.map((id) => { const [j, a, b] = id.split('.'); return { queryKey: ['travel', 'option', j, a, b, seats], queryFn: () => api.travel.option(j!, a!, b!, seats) }; }) });
  const rows = qs.map((x) => x.data).filter(Boolean) as NonNullable<(typeof qs)[number]['data']>[];
  const back = `/travel/search?${new URLSearchParams([...sp].filter(([k]) => k !== 'ids'))}`;
  if (ids.length < 2) return <div className="tv-page"><EmptyState icon="compare" title="Pick 2 or 3 options to compare" action={<Link className="tv-btn" to={back}>Back to results</Link>} /></div>;
  if (qs.some((x) => x.isError)) return <div className="tv-page"><ErrorState error={qs.find((x) => x.isError)!.error} /></div>;
  if (rows.length < ids.length) return <div className="tv-page"><Skeleton height={300} radius={22} /></div>;
  const low = (o: (typeof rows)[number]) => (o.lowest ? formatMoney(o.lowest) : 'Sold out');
  const fields: [string, (o: (typeof rows)[number]) => string][] = [
    [s.mode === 'flight' ? 'Airline' : s.mode === 'train' ? 'Train' : 'Operator', (o) => `${o.operator.name}${s.mode !== 'bus' ? ` ${o.service.number}` : ''}${s.mode === 'train' ? ` ${o.service.name}` : ''}`],
    ['Departure', (o) => `${fmtTime(o.departsAt)} · ${o.from.name}`], ['Arrival', (o) => `${fmtTime(o.arrivesAt)}${o.daysLater ? ` (+${o.daysLater})` : ''} · ${o.to.name}`],
    ['Duration', (o) => fmtDur(o.durationMinutes)],
    ...(s.mode === 'bus' ? [['Bus type', (o) => `${o.service.ac ? 'AC' : 'Non-AC'} ${o.service.busTypeLabel}`], ['Amenities', (o) => o.service.amenities.join(', ') || '—']] as [string, (o: (typeof rows)[number]) => string][] : []),
    ...(s.mode === 'train' ? [['Classes', (o) => o.classes.map((c) => `${c.code}: ${c.availability.label}`).join(' · ')]] as [string, (o: (typeof rows)[number]) => string][] : []),
    ...(s.mode === 'flight' ? [['Stops', (o) => (o.stops ? `${o.stops} via ${o.via.join(', ')}` : 'Non-stop')], ['Baggage', (o) => (o.service.baggage ? `${o.service.baggage.cabin} cabin, ${o.service.baggage.checkIn ?? 'no'} check-in` : '—')]] as [string, (o: (typeof rows)[number]) => string][] : []),
    ['Cancellation', (o) => o.policy], ['Lowest fare', low],
  ];
  return (
    <div className="tv-page" data-theme="travel">
      <Link to={back} className="tv-backlink"><Icon name="back" size={18} /> Results</Link>
      <h1 className="tv-title">Compare {modeOf(s.mode).noun}</h1>
      <div className="tv-cmpwrap"><table className="tv-cmp-table">
        <thead><tr><th scope="col"><span className="sr-only">Detail</span></th>{rows.map((o) => <th key={o.id} scope="col">{o.operator.name}<span className="small tv-muted">{fmtTime(o.departsAt)}</span></th>)}</tr></thead>
        <tbody>{fields.map(([label, f]) => <tr key={label}><th scope="row">{label}</th>{rows.map((o) => <td key={o.id}>{f(o)}</td>)}</tr>)}
          <tr><th scope="row"><span className="sr-only">Choose</span></th>{rows.map((o) => <td key={o.id}><Link className="tv-btn tv-btn--sm" to={`/travel/journey/${o.journeyId}/${o.fromStopId}/${o.toStopId}?${new URLSearchParams([...sp].filter(([k]) => k !== 'ids'))}`}>Choose</Link></td>)}</tr>
        </tbody></table></div>
    </div>
  );
}
