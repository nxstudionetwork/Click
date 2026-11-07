import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { EmptyState, ErrorState, Skeleton } from '../components/ui';
import { PageHeader } from '../components/shell/PageHeader';
import { BookingCard } from '../features/bookings/BookingCard';
import { api } from '../lib/api';

export function BookingsPage() {
  const [params, setParams] = useSearchParams();
  const when = params.get('when') === 'past' ? 'past' : 'upcoming';
  const list = useQuery({ queryKey: ['customer', 'bookings', when], queryFn: () => api.customer.bookings.list(when) });
  return (
    <div className="stack">
      <PageHeader title="Bookings" subtitle="Your movie and event tickets." />
      <div className="tabs" role="tablist" aria-label="Booking time">
        <button role="tab" aria-selected={when === 'upcoming'} onClick={() => setParams({}, { replace: true })}>Upcoming</button>
        <button role="tab" aria-selected={when === 'past'} onClick={() => setParams({ when: 'past' }, { replace: true })}>Past & cancelled</button>
      </div>
      {list.isError ? <ErrorState error={list.error} onRetry={() => list.refetch()} />
        : list.isPending ? <Skeleton height={100} radius={16} />
        : list.data.results.length === 0 ? <EmptyState icon="ticket" title={when === 'upcoming' ? 'No upcoming bookings' : 'No past bookings'} action={<Link to="/movies" className="btn btn--primary">Browse movies & events</Link>} />
        : <div className="card">{list.data.results.map((b, i) => <div key={b.id} style={i ? { borderTop: '1px solid var(--c-line)' } : undefined}><BookingCard booking={b} /></div>)}</div>}
    </div>
  );
}
