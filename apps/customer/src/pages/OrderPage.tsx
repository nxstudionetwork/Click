import { Link, useLocation, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type OrderDetail } from '@click/api';
import { Button, EmptyState, ErrorState, Icon, Skeleton, useToast } from '../components/ui';
import { Totals } from '../features/cart/Totals';
import { isTerminal, PROGRESS, STATUS_LABEL, statusTone } from '../features/orders/status';
import { api } from '../lib/api';
import { formatDateTime, formatMoney, formatTime } from '../lib/format';

export function OrderPage() {
  const { id = '' } = useParams();
  const location = useLocation();
  const qc = useQueryClient();
  const toast = useToast();
  const key = ['customer', 'orders', 'detail', id];
  const order = useQuery({
    queryKey: key,
    queryFn: () => api.customer.orders.get(id),
    // Poll while the order is in progress. (Realtime push replaces this in Phase 3.)
    refetchInterval: (q) => (q.state.data && !isTerminal(q.state.data.status) ? 15_000 : false),
  });
  const cancel = useMutation({
    mutationFn: () => api.customer.orders.cancel(id),
    onSuccess: (o) => { qc.setQueryData(key, o); qc.invalidateQueries({ queryKey: ['customer', 'orders', 'list'] }); toast('Order cancelled'); },
    onError: (e) => toast(e instanceof Error ? e.message : 'Could not cancel.', 'error'),
  });

  if (order.isError) {
    return order.error instanceof ApiError && order.error.status === 404
      ? <EmptyState icon="receipt" title="Order not found" action={<Link className="btn btn--outline" to="/orders">All orders</Link>} />
      : <ErrorState error={order.error} onRetry={() => order.refetch()} />;
  }
  if (order.isPending) return <div className="stack"><Skeleton height={28} width="40%" /><Skeleton height={200} /></div>;
  const o: OrderDetail = order.data;
  const reached = new Map(o.events.map((e) => [e.toStatus, e.createdAt]));
  const currentIdx = PROGRESS.indexOf(o.status === 'ready' ? 'preparing' : o.status);
  const address = o.deliveryAddress;

  return (
    <div className="checkout">
      <div className="stack">
        {(location.state as { justPlaced?: boolean } | null)?.justPlaced && (
          <div className="card card--pad row" style={{ background: 'var(--c-accent-soft)', borderColor: 'transparent' }} role="status">
            <Icon name="check" /> <strong>Order placed! {o.store.name} will confirm it shortly.</strong>
          </div>
        )}
        <div className="spread">
          <div>
            <h1>{o.store.name}</h1>
            <span className="muted small">{o.number} · {formatDateTime(o.createdAt)}</span>
          </div>
          <span className={`badge ${statusTone(o.status)}`}>{STATUS_LABEL[o.status]}</span>
        </div>

        <section className="card card--pad stack" aria-label="Order status">
          {o.status === 'cancelled' ? (
            <p>This order was cancelled{o.cancelledAt ? ` at ${formatTime(o.cancelledAt)}` : ''}.</p>
          ) : (
            <>
              {o.estimatedDeliveryAt && o.status !== 'delivered' && <p className="small">Estimated arrival by <strong>{formatTime(o.estimatedDeliveryAt)}</strong></p>}
              <ol className="timeline">
                {PROGRESS.map((s, i) => (
                  <li key={s} className={`${i <= currentIdx ? 'done' : ''} ${i === currentIdx ? 'current' : ''}`}>
                    <div className="spread"><span>{STATUS_LABEL[s]}</span>{reached.get(s) && <span className="small muted">{formatTime(reached.get(s)!)}</span>}</div>
                  </li>
                ))}
              </ol>
            </>
          )}
          {o.canCancel && (
            <Button variant="danger" size="sm" style={{ alignSelf: 'flex-start' }} loading={cancel.isPending}
              onClick={() => window.confirm('Cancel this order?') && cancel.mutate()}>
              Cancel order
            </Button>
          )}
        </section>

        <section className="card card--pad stack">
          <h3>Items</h3>
          {o.items.map((i) => (
            <div key={i.id} className="spread small">
              <span>{i.quantity} × {i.productName}{i.note && <span className="muted"> — “{i.note}”</span>}</span>
              <span>{formatMoney(i.lineTotal, o.currency)}</span>
            </div>
          ))}
          {o.customerNote && <p className="small muted">Note: {o.customerNote}</p>}
        </section>
      </div>

      <aside className="checkout__aside stack">
        <div className="card card--pad stack">
          <h3>Bill</h3>
          <Totals totals={{ subtotal: o.subtotal, deliveryFee: o.deliveryFee, tax: o.tax, total: o.total }} currency={o.currency} discount={o.discount} />
          {o.payments[0] && (
            <p className="small muted">Payment: {o.payments[0].method === 'cash_on_delivery' ? 'Cash on delivery' : o.payments[0].method} · {o.payments[0].status}</p>
          )}
        </div>
        <div className="card card--pad stack" style={{ gap: 4 }}>
          <h3>Delivering to</h3>
          <span className="small">{address.recipientName} · {address.phone}</span>
          <span className="small muted">{[address.line1, address.line2, address.landmark, address.city, address.postalCode].filter(Boolean).join(', ')}</span>
        </div>
      </aside>
    </div>
  );
}
