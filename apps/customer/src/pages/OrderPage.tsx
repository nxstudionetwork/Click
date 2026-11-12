import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { PayOnline } from '../features/payments/OnlinePay';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type OrderDetail } from '@click/api';
import { Button, EmptyState, ErrorState, Icon, Skeleton, useConfirm, useToast } from '../components/ui';
import { OrderReview } from '../features/orders/OrderReview';
import { serviceForStoreType } from '../config/services';
import { Totals } from '../features/cart/Totals';
import { cartKey } from '../features/cart/useCart';
import { isTerminal, PAYMENT_LABEL, progressFor, statusLabel, statusTone } from '../features/orders/status';
import { ReturnSheet } from '../features/orders/ReturnSheet';
import { api } from '../lib/api';
import { formatDateTime, formatMoney, formatTime } from '../lib/format';
import { useState } from 'react';

const day = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' });

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
  const [returning, setReturning] = useState<string | null>(null);
  const groceryReorder = useMutation({
    mutationFn: () => api.groceries.reorder(id),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: cartKey });
      qc.invalidateQueries({ queryKey: ['customer', 'groceries'] });
      const notes = [
        r.skipped.length ? `Not available now: ${r.skipped.join(', ')}` : '',
        r.priceChanges.length ? `New prices: ${r.priceChanges.map((c) => `${c.name} ${formatMoney(c.from)} → ${formatMoney(c.to)}`).join(', ')}` : '',
      ].filter(Boolean);
      toast(notes.length ? notes.join('. ') : `Added ${r.added.length} item${r.added.length === 1 ? '' : 's'} at today’s prices`);
      navigate('/groceries/basket');
    },
    onError: (e) => toast(e instanceof Error ? e.message : 'Could not reorder.', 'error'),
  });
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
  const retail = o.store.storeType === 'retail';
  const progress = progressFor(o.store.storeType);
  const currentIdx = progress.indexOf(o.status === 'ready' && !progress.includes('ready') ? 'preparing' : o.status);
  const grocery = o.store.storeType === 'grocery' ? o.grocery ?? null : null;
  const eta = retail && o.estimatedDeliveryFrom && o.estimatedDeliveryAt
    ? `Estimated delivery ${day(o.estimatedDeliveryFrom)} – ${day(o.estimatedDeliveryAt)}`
    : o.grocery?.slotStart && o.grocery.slotEnd ? `Scheduled delivery ${day(o.grocery.slotStart)}, ${formatTime(o.grocery.slotStart)} – ${formatTime(o.grocery.slotEnd)}`
    : o.estimatedDeliveryAt ? `Estimated arrival by ${formatTime(o.estimatedDeliveryAt)}` : null;
  const address = o.deliveryAddress;

  return (
    <div className="checkout">
      <div className="stack">
        {o.paymentIntent && (o.status === 'awaiting_payment' || o.paymentIntent.status !== 'succeeded') && <PayOnline intent={o.paymentIntent} />}
        {(location.state as { justPlaced?: boolean } | null)?.justPlaced && o.status !== 'awaiting_payment' && o.status !== 'cancelled' && (
          <section className="placed" data-theme={serviceForStoreType(o.store.storeType).theme} role="status" aria-labelledby="placed-h">
            <span className="placed__check" aria-hidden="true"><Icon name="check" size={30} /></span>
            <h2 id="placed-h">Order placed</h2>
            <p>{o.store.name} will confirm it shortly.</p>
            {o.checkout && o.checkout.orderCount > 1 && <p className="small">Part of checkout {o.checkout.number} · <Link to={`/checkout/done/${o.checkout.id}`} style={{ textDecoration: 'underline' }}>see all {o.checkout.orderCount} orders</Link></p>}
            <dl className="placed__facts">
              <div><dt>Order ID</dt><dd>{o.number}</dd></div>
              <div><dt>Total</dt><dd>{formatMoney(o.total, o.currency)}</dd></div>
              <div><dt>Payment</dt><dd>{o.payments[0] ? `${o.payments[0].method === 'cash_on_delivery' ? 'Cash on delivery' : 'Click. Wallet'} · ${PAYMENT_LABEL[o.payments[0].status]}` : '—'}</dd></div>
              {eta && <div><dt>{retail ? 'Delivery' : 'Estimated arrival'}</dt><dd>{eta.replace(/^Estimated (delivery|arrival) /, '')}</dd></div>}
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
          <span className={`badge ${statusTone(o.status)}`}>{statusLabel(o.status, o.store.storeType)}</span>
        </div>

        <section className="card card--pad stack" aria-label="Order status" id="order-status">
          {o.status === 'cancelled' ? (
            <p>This order was cancelled{o.cancelledAt ? ` at ${formatTime(o.cancelledAt)}` : ''}.</p>
          ) : (
            <>
              {eta && o.status !== 'delivered' && <p className="small"><strong>{eta}</strong>{retail && <span className="muted"> · an estimate until the seller ships</span>}</p>}
              {o.checkout && o.checkout.orderCount > 1 && <p className="small muted">One of {o.checkout.orderCount} orders from checkout {o.checkout.number}. <Link to={`/checkout/done/${o.checkout.id}`} style={{ color: 'var(--c-theme-strong)' }}>See all</Link></p>}
              <ol className="timeline">
                {progress.map((s, i) => (
                  <li key={s} className={`${i <= currentIdx ? 'done' : ''} ${i === currentIdx ? 'current' : ''}`}>
                    <div className="spread"><span>{statusLabel(s, o.store.storeType)}</span>{reached.get(s) && <span className="small muted">{formatTime(reached.get(s)!)}</span>}</div>
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
            {isTerminal(o.status) && (grocery ? (
              <Button variant="secondary" size="sm" loading={groceryReorder.isPending} onClick={() => groceryReorder.mutate()}>Buy again</Button>
            ) : (
              <Button variant="secondary" size="sm" loading={reorder.isPending} onClick={() => reorder.mutate()}>Reorder</Button>
            ))}
            <Link to={`/help/new?orderId=${o.id}&category=order`} className="btn btn--outline btn--sm">Get help</Link>
          </div>
        </section>

        {grocery && (
          <section className="card card--pad stack" aria-label="Delivery details">
            <h3>Delivery</h3>
            <div className="spread small"><span>Method</span><strong>{grocery.deliveryModeLabel}</strong></div>
            {grocery.slotStart && grocery.slotEnd && <div className="spread small"><span>Slot</span><strong>{day(grocery.slotStart)}, {formatTime(grocery.slotStart)} – {formatTime(grocery.slotEnd)}</strong></div>}
            {grocery.distanceKm && <div className="spread small"><span>Distance from store</span><span>{grocery.distanceKm} km</span></div>}
            <div className="spread small"><span>If an item is unavailable</span><span>{grocery.substitutionLabel}</span></div>
            {grocery.substitutionNote && <p className="small muted">Your preference: “{grocery.substitutionNote}”</p>}
            {grocery.refund && <p className="small"><strong>Refund:</strong> {formatMoney(grocery.refund.amount, o.currency)} returned to your {grocery.refund.to}.</p>}
            {o.status === 'cancelled' && !grocery.refund && o.payments[0]?.method === 'cash_on_delivery' && <p className="small muted">Nothing was charged for this order (cash on delivery).</p>}
            <p className="small muted"><Icon name="clock" size={14} /> You’ll see each step as the store records it. Live rider tracking isn’t available yet.</p>
            {o.status !== 'cancelled' && (
              <div className="row small" style={{ flexWrap: 'wrap', gap: 12 }}>
                <Link to="/food">Need dinner instead? Food</Link>
                <Link to="/groceries/lists">Something else? Shopping list</Link>
              </div>
            )}
          </section>
        )}

        <section className="card card--pad stack">
          <h3>Items</h3>
          {o.items.map((i) => (
            <div key={i.id} className="stack" style={{ gap: 6 }}>
              <div className="spread small">
                <span>{i.quantity} × {retail && i.productId ? <Link to={`/products/${i.productId}`}>{i.productName}</Link> : grocery && i.productId ? <Link to={`/groceries/p/${i.productId}`}>{i.productName}</Link> : i.productName}
                  {i.optionsSummary && <span className="muted"> ({i.optionsSummary})</span>}{i.note && <span className="muted"> — “{i.note}”</span>}</span>
                <span>{formatMoney(i.lineTotal, o.currency)}</span>
              </div>
              {retail && (
                <div className="row small" style={{ flexWrap: 'wrap', gap: 8 }}>
                  <span className="muted">{i.returnDays ? `${i.returnDays}-day ${i.replacementOnly ? 'replacement' : 'return'}${i.returnUntil ? ` · until ${day(i.returnUntil)}` : ''}` : 'Not returnable'}</span>
                  {i.canReturn && <Button size="sm" variant="outline" onClick={() => setReturning(i.id)}>{i.replacementOnly ? 'Request replacement' : 'Return or replace'}</Button>}
                  {!i.canReturn && i.returnNote && o.status === 'delivered' && i.returns.length === 0 && <span className="muted">{i.returnNote}</span>}
                </div>
              )}
              {i.returns.map((rr) => (
                <div key={rr.id} className="ret">
                  <strong>{rr.kindLabel} · {rr.statusLabel}</strong>
                  <span>{rr.reasonLabel} · {rr.quantity} item{rr.quantity === 1 ? '' : 's'} · {formatDateTime(rr.createdAt)}</span>
                  {rr.refundAmount && <span>{formatMoney(rr.refundAmount, o.currency)} refunded to your Click. Wallet</span>}
                  {rr.resolutionNote && <span>{rr.resolutionNote}</span>}
                </div>
              ))}
            </div>
          ))}
          {o.customerNote && <p className="small muted">Note: {o.customerNote}</p>}
        </section>
        {retail ? o.status === 'delivered' && (
          <p className="small muted">Rate the products you received on each product’s page{o.items[0]?.productId ? <> · <Link to={`/products/${o.items[0].productId}#reviews`} style={{ color: 'var(--c-theme-strong)' }}>review {o.items[0].productName}</Link></> : null}.</p>
        ) : <OrderReview order={o} />}
        <ReturnSheet order={o} itemId={returning} onClose={() => setReturning(null)} onDone={(next) => qc.setQueryData(key, next)} />
      </div>

      <aside className="checkout__aside stack">
        <div className="card card--pad stack">
          <h3>Bill</h3>
          <Totals totals={{ subtotal: o.subtotal, deliveryFee: o.deliveryFee, tax: o.tax, discount: o.discount, total: o.total }} currency={o.currency} offerTitle={o.offerTitle} />
          {o.payments[0] && (
            <p className="small muted">Payment: {o.payments[0].method === 'cash_on_delivery' ? 'Cash on delivery' : o.payments[0].method === 'wallet' ? 'Click. Wallet' : o.payments[0].method} · {PAYMENT_LABEL[o.payments[0].status]}</p>
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
