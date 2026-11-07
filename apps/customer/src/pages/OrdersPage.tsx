import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { StoreType } from '@click/api';
import { EmptyState, ErrorState, Skeleton } from '../components/ui';
import { OrderCard } from '../features/orders/OrderCard';
import { api } from '../lib/api';

/** Order categories map to commerce verticals; Rides/Deliveries/Bookings join as those domains launch. */
const TABS: { id: '' | StoreType; label: string }[] = [
  { id: '', label: 'All' },
  { id: 'restaurant', label: 'Food' },
  { id: 'grocery', label: 'Groceries' },
  { id: 'retail', label: 'Shopping' },
];

export function OrdersPage() {
  const [params, setParams] = useSearchParams();
  const type = (TABS.find((t) => t.id === params.get('type'))?.id ?? '') as '' | StoreType;
  const page = Math.max(1, Number(params.get('page')) || 1);
  const orders = useQuery({
    queryKey: ['customer', 'orders', 'list', type, page],
    queryFn: () => api.customer.orders.list({ type: type || undefined, page }),
  });

  return (
    <div className="stack">
      <h1>Your orders</h1>
      <div className="tabs" role="tablist" aria-label="Order type">
        {TABS.map((t) => (
          <button key={t.id || 'all'} role="tab" aria-selected={type === t.id} onClick={() => setParams(t.id ? { type: t.id } : {}, { replace: true })}>{t.label}</button>
        ))}
      </div>
      {orders.isError ? (
        <ErrorState error={orders.error} onRetry={() => orders.refetch()} />
      ) : orders.isPending ? (
        Array.from({ length: 3 }, (_, i) => <Skeleton key={i} height={100} radius={16} />)
      ) : orders.data.results.length === 0 ? (
        <EmptyState icon="receipt" title={type ? 'No orders in this category' : 'No orders yet'} message="Your orders will show up here." action={<Link to="/explore" className="btn btn--primary">Start exploring</Link>} />
      ) : (
        <>
          <div className="card">
            {orders.data.results.map((o, idx) => (
              <div key={o.id} style={idx ? { borderTop: '1px solid var(--c-line)' } : undefined}><OrderCard order={o} /></div>
            ))}
          </div>
          {(page > 1 || orders.data.hasNext) && (
            <div className="spread">
              <button className="btn btn--outline btn--sm" disabled={page <= 1} onClick={() => setParams({ ...(type && { type }), page: String(page - 1) })}>Previous</button>
              <span className="small muted">Page {page}</span>
              <button className="btn btn--outline btn--sm" disabled={!orders.data.hasNext} onClick={() => setParams({ ...(type && { type }), page: String(page + 1) })}>Next</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
