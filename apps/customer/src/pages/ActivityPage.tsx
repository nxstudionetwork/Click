import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { EmptyState, ErrorState, Skeleton } from '../components/ui';
import { PageHeader } from '../components/shell/PageHeader';
import { BookingCard } from '../features/bookings/BookingCard';
import { OrderCard } from '../features/orders/OrderCard';
import { api } from '../lib/api';

/** One timeline of everything the customer has done on Click (orders and bookings today; rides etc. as they launch). */
export function ActivityPage() {
  const orders = useQuery({ queryKey: ['customer', 'orders', 'list', 'activity'], queryFn: () => api.customer.orders.list() });
  const bookings = useQuery({ queryKey: ['customer', 'bookings', 'activity'], queryFn: () => api.customer.bookings.list() });
  const failed = orders.error ?? bookings.error;
  if (failed) return <ErrorState error={failed} onRetry={() => { orders.refetch(); bookings.refetch(); }} />;
  if (!orders.data || !bookings.data) return <div className="stack"><Skeleton height={28} width="30%" /><Skeleton height={200} radius={16} /></div>;
  const items = [
    ...orders.data.results.map((o) => ({ at: o.createdAt, key: `o-${o.id}`, node: <OrderCard order={o} /> })),
    ...bookings.data.results.map((b) => ({ at: b.createdAt, key: `b-${b.id}`, node: <BookingCard booking={b} /> })),
  ].sort((a, b) => b.at.localeCompare(a.at));
  return (
    <div className="stack">
      <PageHeader title="Activity" subtitle="Your orders and bookings, newest first." back={{ to: '/account', label: 'Account' }} />
      {items.length === 0 ? <EmptyState icon="history" title="No activity yet" message="Orders and bookings will appear here." action={<Link to="/explore" className="btn btn--primary">Explore Click</Link>} />
        : <div className="card">{items.map((it, i) => <div key={it.key} style={i ? { borderTop: '1px solid var(--c-line)' } : undefined}>{it.node}</div>)}</div>}
    </div>
  );
}
