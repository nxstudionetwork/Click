import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { EmptyState, ErrorState, Icon, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { evIcon, fmtDate, PackageCardView, ProviderCardView } from '../features/events/parts';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

const TABS = [['plans', 'Plans'], ['upcoming', 'Upcoming'], ['past', 'Past'], ['saved', 'Saved']] as const;

/** The customer's event plans, bookings and saved teams / venues / packages. */
export function EventsMinePage() {
  useThemeOverride('events');
  const [sp, setSp] = useSearchParams();
  const tab = (TABS.find(([t]) => t === sp.get('tab'))?.[0] ?? 'plans');
  const plans = useQuery({ queryKey: ['eventhub', 'plans'], queryFn: () => api.eventHub.plans(), enabled: tab === 'plans' });
  const bookings = useQuery({ queryKey: ['eventhub', 'bookings', tab], queryFn: () => api.eventHub.bookings(tab === 'upcoming' ? 'active' : 'past'), enabled: tab === 'upcoming' || tab === 'past' });
  const saved = useQuery({ queryKey: ['eventhub', 'favorites'], queryFn: () => api.eventHub.favorites(), enabled: tab === 'saved' });
  const cur = tab === 'plans' ? plans : tab === 'saved' ? saved : bookings;

  return (
    <div className="ev-page" data-theme="events">
      <Link to="/events" className="ev-back"><Icon name="back" size={18} /> Events</Link>
      <h1 className="ev-title">My events</h1>
      <div className="ev-seg ev-seg--wide" role="tablist" aria-label="My events">
        {TABS.map(([t, l]) => <button key={t} type="button" role="tab" aria-selected={t === tab} onClick={() => setSp({ tab: t }, { replace: true })}>{l}</button>)}
      </div>
      {cur.isError ? <ErrorState error={cur.error} onRetry={() => cur.refetch()} /> : cur.isPending ? <Skeleton height={240} radius={20} /> : tab === 'plans' ? (
        plans.data!.results.length === 0 ? <EmptyState icon="gift" title="No event plans yet" action={<Link to="/events/plan" className="btn btn--primary">Plan an event</Link>} /> : (
          <ul className="ev-list">{plans.data!.results.map((p) => (
            <li key={p.id} style={{ ['--ev-accent' as string]: p.eventType.accent }}>
              <Link to={`/events/plans/${p.id}`} className="ev-row-link">
                <span className="ev-type__icon ev-type__icon--sm"><Icon name={evIcon(p.eventType.icon)} size={18} /></span>
                <span className="ev-row-link__main"><strong>{p.title}</strong>
                  <span className="small ev-muted">{p.dateFlexible ? 'Flexible date' : fmtDate(p.date)} · {p.guests} guests · {p.number}</span>
                  <span className="small">{p.statusLabel}{p.quotesWaiting ? ` · ${p.quotesWaiting} quote${p.quotesWaiting > 1 ? 's' : ''} waiting` : ''}{p.bookings ? ` · ${p.bookings} booking${p.bookings > 1 ? 's' : ''}` : ''}</span></span>
                <Icon name="chevron" size={16} />
              </Link>
            </li>
          ))}</ul>
        )
      ) : tab === 'saved' ? (
        saved.data!.providers.length + saved.data!.packages.length === 0 ? <EmptyState icon="heart" title="Nothing saved yet" message="Tap the heart on a team, venue or package to save it." /> : (
          <>
            {saved.data!.providers.length > 0 && <div className="ev-grid">{saved.data!.providers.map((p) => <ProviderCardView key={p.id} p={p} />)}</div>}
            {saved.data!.packages.length > 0 && <div className="ev-grid">{saved.data!.packages.map((x) => <PackageCardView key={x.id} pkg={x} showProvider action={<Link to={`/events/book?package=${x.id}`} className="ev-btn ev-btn--sm">Book</Link>} />)}</div>}
          </>
        )
      ) : bookings.data!.results.length === 0 ? (
        <EmptyState icon="ticket" title={tab === 'upcoming' ? 'No upcoming bookings' : 'No past bookings'} action={<Link to="/events/plan" className="btn btn--primary">Plan an event</Link>} />
      ) : (
        <ul className="ev-list">{bookings.data!.results.map((b) => (
          <li key={b.id} style={{ ['--ev-accent' as string]: b.provider.accent }}>
            <Link to={`/events/bookings/${b.id}`} className="ev-row-link">
              <span className="ev-type__icon ev-type__icon--sm"><Icon name="ticket" size={18} /></span>
              <span className="ev-row-link__main"><strong>{b.title}</strong>
                <span className="small ev-muted">{fmtDate(b.eventDate)} · {b.guests} guests · {b.number}</span>
                <span className={`ev-status ev-status--${b.status} small`}>{b.statusLabel}</span></span>
              <span className="ev-price">{formatMoney(b.total)}</span>
            </Link>
            {b.status === 'completed' && !b.reviewed && <Link to={`/events/bookings/${b.id}`} className="ev-link small ev-list__act">Leave a review</Link>}
          </li>
        ))}</ul>
      )}
    </div>
  );
}
