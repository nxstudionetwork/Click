import { useSearchParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { EmptyState, ErrorState, Icon, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { fmtDay, KIND_ICON } from '../features/bookings/parts';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

const TABS = [['upcoming', 'Upcoming'], ['completed', 'Completed'], ['cancelled', 'Cancelled'], ['all', 'All']] as const;
const KINDS = [['', 'Everything'], ['temple', 'Temples'], ['attraction', 'Attractions'], ['experience', 'Experiences'], ['travel', 'Travel'], ['hotel', 'Hotels'],
  ['show', 'Shows'], ['event', 'Events'], ['service', 'Services']] as const;

/** Every booking the customer holds across Click., read from each service’s own records (no copies), with each row
 *  opening that service’s booking details. */
export function MyBookingsPage() {
  useThemeOverride('bookings');
  const [sp, setSp] = useSearchParams();
  const group = (sp.get('group') ?? 'upcoming') as (typeof TABS)[number][0];
  const kind = sp.get('kind') ?? '';
  const q = useQuery({ queryKey: ['bookings', 'reservations', group, kind], queryFn: () => api.bookings.reservations(group, kind || undefined) });
  const set = (k: string, v: string) => { const n = new URLSearchParams(sp); if (v) n.set(k, v); else n.delete(k); setSp(n, { replace: true }); };
  return (
    <div className="bk-page" data-theme="bookings">
      <Link to="/bookings" className="bk-back"><Icon name="back" size={18} /> Bookings</Link>
      <h1 className="bk-title">My bookings</h1>
      <div className="bk-tabs" role="tablist">{TABS.map(([k, l]) => (
        <button key={k} type="button" role="tab" aria-selected={group === k} className={group === k ? 'is-on' : ''} onClick={() => set('group', k === 'upcoming' ? '' : k)}>
          {l}{q.data ? ` (${q.data.counts[k]})` : ''}</button>))}</div>
      <div className="bk-chips" aria-label="Type">{KINDS.map(([k, l]) => <button key={k} type="button" aria-pressed={kind === k} className={kind === k ? 'is-on' : ''} onClick={() => set('kind', k)}>{l}</button>)}</div>
      {q.data && q.data.unavailable.length > 0 && <p className="bk-alert small">Some bookings ({q.data.unavailable.join(', ')}) couldn’t load right now. <button type="button" className="bk-link" onClick={() => q.refetch()}>Retry</button></p>}
      {q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !q.data ? <Skeleton height={200} radius={18} /> : q.data.results.length === 0 ? (
        <EmptyState icon="ticket" title={group === 'upcoming' ? 'Nothing coming up' : 'No bookings here yet'} message="Temples, attractions, journeys, stays, shows, events and services you book appear here."
          action={<Link to="/bookings" className="bk-btn">Find something to book</Link>} />
      ) : (
        <ul className="bk-resv">{q.data.results.map((r) => (
          <li key={r.id}><Link to={r.link} className="bk-resv__row" data-theme={r.theme}>
            <span className="bk-resv__icon"><Icon name={KIND_ICON[r.kind]} size={18} /></span>
            <span><strong>{r.title}</strong><span className="small bk-muted">{r.kindLabel} · {r.subtitle}</span>
              <span className="small bk-muted">{r.when ? fmtDay(r.when, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }) : ''} · {r.reference}</span></span>
            <span className="bk-resv__end"><span className="small">{r.statusLabel}</span>{r.amount != null && <strong className="small">{Number(r.amount) ? formatMoney(r.amount) : 'Free'}</strong>}</span>
          </Link></li>
        ))}</ul>
      )}
    </div>
  );
}
