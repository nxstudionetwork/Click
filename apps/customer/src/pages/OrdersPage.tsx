import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { EmptyState, ErrorState, Skeleton, SmartImage } from '../components/ui';
import { STATUS_LABEL, statusTone } from '../features/orders/status';
import { api } from '../lib/api';
import { formatDateTime, formatMoney } from '../lib/format';

export function OrdersPage() {
  const orders = useQuery({ queryKey: ['customer', 'orders', 'list'], queryFn: () => api.customer.orders.list() });

  return (
    <div className="stack">
      <h1>Your orders</h1>
      {orders.isError ? (
        <ErrorState error={orders.error} onRetry={() => orders.refetch()} />
      ) : orders.isPending ? (
        Array.from({ length: 3 }, (_, i) => <Skeleton key={i} height={88} radius={16} />)
      ) : orders.data.results.length === 0 ? (
        <EmptyState icon="receipt" title="No orders yet" message="Your order history will show up here." action={<Link to="/food" className="btn btn--primary">Order food</Link>} />
      ) : (
        <div className="card">
          {orders.data.results.map((o, idx) => (
            <Link key={o.id} to={`/orders/${o.id}`} className="order-row" style={idx ? { borderTop: '1px solid var(--c-line)' } : undefined}>
              <SmartImage src={o.store.imageUrl} alt={o.store.name} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="spread"><strong>{o.store.name}</strong><strong>{formatMoney(o.total, o.currency)}</strong></div>
                <div className="muted small">{o.itemCount} item{o.itemCount > 1 ? 's' : ''} · {formatDateTime(o.createdAt)} · {o.number}</div>
                <span className={`badge ${statusTone(o.status)}`} style={{ marginTop: 6 }}>{STATUS_LABEL[o.status]}</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
