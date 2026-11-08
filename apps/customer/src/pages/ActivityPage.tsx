import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { StoreType } from '@click/api';
import { EmptyState, ErrorState, Skeleton } from '../components/ui';
import { PageHeader } from '../components/shell/PageHeader';
import { BookingCard } from '../features/bookings/BookingCard';
import { OrderCard } from '../features/orders/OrderCard';
import { api } from '../lib/api';

/**
 * Activity: one timeline of everything the customer has done on Click., read from the source domains (orders,
 * bookings) rather than copied into a separate table. Filters exist only for domains that exist today; rides,
 * parcels and service bookings join as those services launch (each as another source here).
 */
const FILTERS: { id: string; label: string; source: 'all' | 'orders' | 'bookings'; type?: StoreType }[] = [
  { id: 'all', label: 'All', source: 'all' },
  { id: 'food', label: 'Food', source: 'orders', type: 'restaurant' },
  { id: 'groceries', label: 'Groceries', source: 'orders', type: 'grocery' },
  { id: 'shopping', label: 'Shopping', source: 'orders', type: 'retail' },
  { id: 'bookings', label: 'Bookings', source: 'bookings' },
];

export function ActivityPage() {
  const [params, setParams] = useSearchParams();
  const filter = FILTERS.find((f) => f.id === params.get('filter')) ?? FILTERS[0]!;
  const wantOrders = filter.source !== 'bookings';
  const wantBookings = filter.source !== 'orders';
  const orders = useQuery({ queryKey: ['customer', 'orders', 'list', 'activity', filter.type ?? ''], queryFn: () => api.customer.orders.list({ type: filter.type }), enabled: wantOrders });
  const bookings = useQuery({ queryKey: ['customer', 'bookings', 'activity'], queryFn: () => api.customer.bookings.list(), enabled: wantBookings });

  const failed = (wantOrders && orders.error) || (wantBookings && bookings.error);
  const loading = (wantOrders && orders.isPending) || (wantBookings && bookings.isPending);
  const items = [
    ...(wantOrders ? orders.data?.results ?? [] : []).map((o) => ({ at: o.createdAt, key: `o-${o.id}`, node: <OrderCard order={o} /> })),
    ...(wantBookings ? bookings.data?.results ?? [] : []).map((b) => ({ at: b.createdAt, key: `b-${b.id}`, node: <BookingCard booking={b} /> })),
  ].sort((a, b) => b.at.localeCompare(a.at));

  return (
    <div className="stack">
      <PageHeader title="Activity" subtitle="Your Click. orders and bookings, newest first." back={{ to: '/account', label: 'Profile' }} />
      <div className="chips" role="group" aria-label="Filter activity">
        {FILTERS.map((f) => (
          <button key={f.id} type="button" className="chip" aria-pressed={f.id === filter.id}
            onClick={() => setParams(f.id === 'all' ? {} : { filter: f.id }, { replace: true })}>{f.label}</button>
        ))}
      </div>
      {failed ? <ErrorState error={failed} onRetry={() => { orders.refetch(); bookings.refetch(); }} />
        : loading ? <Skeleton height={200} radius={16} />
          : items.length === 0 ? (
            <EmptyState icon="history" title="No activity yet." message={filter.id === 'all' ? 'Your Click. orders, rides and bookings will appear here.' : `Nothing in ${filter.label} yet.`}
              action={<Link to={filter.id === 'bookings' ? '/movies' : '/food'} className="btn btn--primary">{filter.id === 'bookings' ? 'Book a show' : 'Order food'}</Link>} />
          ) : <div className="card">{items.map((it, i) => <div key={it.key} style={i ? { borderTop: '1px solid var(--c-line)' } : undefined}>{it.node}</div>)}</div>}
    </div>
  );
}
