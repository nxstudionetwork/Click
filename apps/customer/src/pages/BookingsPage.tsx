import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { EmptyState, ErrorState, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { Poster, dayOf, timeOf } from '../features/showtime/parts';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

const TABS = [{ id: 'upcoming', label: 'Upcoming' }, { id: 'completed', label: 'Completed' }, { id: 'cancelled', label: 'Cancelled' }] as const;

/** My Tickets: Showtime bookings by state (the same bookings appear in Profile → Activity). */
export function BookingsPage() {
  useThemeOverride('movies');
  const [params, setParams] = useSearchParams();
  const when = (TABS.find((t) => t.id === params.get('when'))?.id ?? 'upcoming') as (typeof TABS)[number]['id'];
  const list = useQuery({ queryKey: ['customer', 'bookings', when], queryFn: () => api.customer.bookings.list(when) });
  return (
    <div className="st-page" data-theme="movies">
      <header className="st-intro"><h1>My Tickets<span>.</span></h1><p>Your Showtime bookings.</p></header>
      <div className="st-tabs" role="tablist" aria-label="Tickets">
        {TABS.map((t) => <button key={t.id} role="tab" className="chip" aria-selected={when === t.id} aria-pressed={when === t.id}
          onClick={() => setParams(t.id === 'upcoming' ? {} : { when: t.id }, { replace: true })}>{t.label}</button>)}
      </div>
      {list.isError ? <ErrorState error={list.error} onRetry={() => list.refetch()} />
        : list.isPending ? <Skeleton height={120} radius={18} />
        : list.data.results.length === 0 ? (
          <EmptyState icon="ticket" title={when === 'upcoming' ? 'No upcoming shows' : when === 'completed' ? 'No completed shows yet' : 'No cancelled bookings'}
            action={<Link to="/showtime" className="btn btn--primary">Find a show</Link>} />
        ) : (
          <div className="stack" style={{ gap: 'var(--s-3)' }}>
            {list.data.results.map((b) => (
              <Link key={b.id} to={`/tickets/${b.id}`} className="st-box" style={{ gridTemplateColumns: '64px 1fr', alignItems: 'center', color: 'inherit' }}>
                <div style={{ position: 'relative', aspectRatio: '2 / 3', borderRadius: 10, overflow: 'hidden' }}>
                  <Poster t={{ title: b.event.title, posterUrl: b.event.posterUrl, genres: b.event.genres, kind: b.event.kind }} />
                </div>
                <div className="stack" style={{ gap: 2, minWidth: 0 }}>
                  <strong className="truncate">{b.event.title}</strong>
                  <span className="small" style={{ color: 'var(--c-ink-2)' }}>{dayOf(b.show.startsAt)}, {timeOf(b.show.startsAt)} · {b.show.venue.name}</span>
                  <span className="small muted">{b.seats.map((s) => s.label).join(', ')} · {formatMoney(b.total, b.currency)} · {b.reference}</span>
                </div>
              </Link>
            ))}
          </div>
        )}
    </div>
  );
}
