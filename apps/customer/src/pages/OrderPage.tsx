import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type OrderDetail } from '@click/api';
import { Button, EmptyState, ErrorState, Icon, Skeleton, useConfirm, useToast } from '../components/ui';
import { OrderReview } from '../features/orders/OrderReview';
import { serviceForStoreType } from '../config/services';
import { Totals } from '../features/cart/Totals';
import { cartKey } from '../features/cart/useCart';
import { isTerminal, PAYMENT_LABEL, PROGRESS, STATUS_LABEL, statusTone } from '../features/orders/status';
import { api } from '../lib/api';
import { formatDateTime, formatMoney, formatTime } from '../lib/format';

export function OrderPage() {
  const { id = '' } = useParams();
  const location = useLocation();
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const key = ['customer', 'orders', 'detail', id];
  const order = useQuery({
    queryKey: key,
    queryFn: () => api.customer.orders.get(id),
    // Poll while the order is in progress. (Realtime push replaces this in Phase 3.)
    refetchInterval: (q) => (q.state.data && !isTerminal(q.state.data.status) ? 15_000 : false),
  });
  const navigate = useNavigate();
  const reorder = useMutation({
    mutationFn: () => api.customer.orders.reorder(id),
    onSuccess: (r) => {
      qc.setQueryData(cartKey, r.cart);
      if (r.skipped.length) toast(`Not available anymore: ${r.skipped.join(', ')}`);
      navigate('/cart');
    },
    onError: (e) => toast(e instanceof Error ? e.message : 'Could not reorder.', 'error'),
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
          <section className="placed" data-theme={serviceForStoreType(o.store.storeType).theme} role="status" aria-labelledby="placed-h">
            <span className="placed__check" aria-hidden="true"><Icon name="check" size={30} /></span>
            <h2 id="placed-h">Order placed</h2>
            <p>{o.store.name} will confirm it shortly.</p>
            <dl className="placed__facts">
              <div><dt>Order ID</dt><dd>{o.number}</dd></div>
              <div><dt>Total</dt><dd>{formatMoney(o.total, o.currency)}</dd></div>
              <div><dt>Payment</dt><dd>{o.payments[0] ? `${o.payments[0].method === 'cash_on_delivery' ? 'Cash on delivery' : 'Click. Wallet'} · ${PAYMENT_LABEL[o.payments[0].status]}` : '—'}</dd></div>
              {o.estimatedDeliveryAt && <div><dt>Estimated arrival</dt><dd>by {formatTime(o.estimatedDeliveryAt)}</dd></div>}
              <div className="placed__wide"><dt>Delivering to</dt><dd>{[o.deliveryAddress.line1, o.deliveryAddress.line2, o.deliveryAddress.city].filter(Boolean).join(', ')}</dd></div>
            </dl>
            <div className="row" style={{ flexWrap: 'wrap', justifyContent: 'center' }}>
              <a href="#order-status" className="btn btn--light btn--sm">View order</a>
              <Link to={`/${serviceForStoreType(o.store.storeType).id}`} className="btn btn--glass btn--sm">Continue {serviceForStoreType(o.store.storeType).name}</Link>
              <Link to="/" className="btn btn--glass btn--sm">Go home</Link>
            </div>
          </section>
        )}
        <div className="spread">
          <div>
            <h1>{o.store.name}</h1>
            <span className="muted small">{o.number} · {formatDateTime(o.createdAt)}</span>
          </div>
          <span className={`badge ${statusTone(o.status)}`}>{STATUS_LABEL[o.status]}</span>
        </div>

        <section className="card card--pad stack" aria-label="Order status" id="order-status">
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
          <div className="row" style={{ flexWrap: 'wrap' }}>
            {o.canCancel && (
              <Button variant="danger" size="sm" loading={cancel.isPending}
                onClick={async () => { if (await confirm({ title: 'Cancel this order?', message: `${o.store.name} won’t prepare it. Wallet payments are refunded to your Click. Wallet.`, confirmLabel: 'Cancel order', cancelLabel: 'Keep order', danger: true })) cancel.mutate(); }}>
                Cancel order
              </Button>
            )}
            {isTerminal(o.status) && (
              <Button variant="secondary" size="sm" loading={reorder.isPending} onClick={() => reorder.mutate()}>Reorder</Button>
            )}
            <Link to={`/help/new?orderId=${o.id}&category=order`} className="btn btn--outline btn--sm">Get help</Link>
          </div>
        </section>

        <section className="card card--pad stack">
          <h3>Items</h3>
          {o.items.map((i) => (
            <div key={i.id} className="spread small">
              <span>{i.quantity} × {i.productName}{i.optionsSummary && <span className="muted"> ({i.optionsSummary})</span>}{i.note && <span className="muted"> — “{i.note}”</span>}</span>
              <span>{formatMoney(i.lineTotal, o.currency)}</span>
            </div>
          ))}
          {o.customerNote && <p className="small muted">Note: {o.customerNote}</p>}
        </section>
        <OrderReview order={o} />
      </div>

      <aside className="checkout__aside stack">
        <div className="card card--pad stack">
          <h3>Bill</h3>
          <Totals totals={{ subtotal: o.subtotal, deliveryFee: o.deliveryFee, tax: o.tax, discount: o.discount, total: o.total }} currency={o.currency} offerTitle={o.offerTitle} />
          {o.payments[0] && (
            <p className="small muted">Payment: {o.payments[0].method === 'cash_on_delivery' ? 'Cash on delivery' : o.payments[0].method} · {PAYMENT_LABEL[o.payments[0].status]}</p>
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
