import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { EmptyState, ErrorState, Icon, Skeleton } from '../components/ui';
import { PAYMENT_LABEL } from '../features/orders/status';
import { api } from '../lib/api';
import { formatDateTime, formatMoney } from '../lib/format';

/**
 * Payment status always comes from the backend payment records.
 * Cards are never stored by Click; online methods will be tokenised by the payment provider.
 */
export function PaymentsPage() {
  const orders = useQuery({ queryKey: ['customer', 'orders', 'list', 'payments'], queryFn: () => api.customer.orders.list() });
  return (
    <div className="stack">
      <h1>Payments</h1>
      <section className="card card--pad stack" style={{ gap: 'var(--s-2)' }}>
        <h3>Payment methods</h3>
        <div className="row"><span className="list-row__icon"><Icon name="card" size={18} /></span><div><strong>Cash on delivery</strong><div className="small muted">Pay with cash or UPI when your order arrives.</div></div></div>
        <Link to="/wallet" className="row"><span className="list-row__icon"><Icon name="wallet" size={18} /></span><div><strong>Click Wallet</strong><div className="small muted">Pay instantly from your balance. Refunds return here.</div></div></Link>
        <p className="small muted">Online payments (cards, UPI) through a secure payment provider are coming soon. Click never stores your card details.</p>
      </section>
      <section className="stack">
        <h2>Payment history</h2>
        {orders.isError ? <ErrorState error={orders.error} onRetry={() => orders.refetch()} />
          : orders.isPending ? <Skeleton height={120} radius={16} />
          : orders.data.results.length === 0 ? <EmptyState icon="card" title="No payments yet" message="Payments for your orders will appear here." />
          : (
            <div className="card list">
              {orders.data.results.map((o) => (
                <Link key={o.id} to={`/orders/${o.id}`} className="list-row">
                  <span style={{ flex: 1 }}>
                    <span style={{ display: 'block', fontWeight: 600 }}>{o.store.name}</span>
                    <span className="small muted">{o.number} · {formatDateTime(o.createdAt)}</span>
                  </span>
                  <span className="stack" style={{ gap: 2, alignItems: 'flex-end' }}>
                    <strong>{formatMoney(o.total, o.currency)}</strong>
                    {o.paymentStatus && <span className="badge">{PAYMENT_LABEL[o.paymentStatus]}</span>}
                  </span>
                </Link>
              ))}
            </div>
          )}
      </section>
    </div>
  );
}
