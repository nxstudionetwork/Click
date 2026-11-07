import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError, type PaymentMethod } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, EmptyState, ErrorState, Skeleton, TextArea } from '../components/ui';
import { AddressForm } from '../features/addresses/AddressForm';
import { useAddresses } from '../features/addresses/useAddresses';
import { Totals } from '../features/cart/Totals';
import { cartKey, useCart } from '../features/cart/useCart';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

export function CheckoutPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const cart = useCart();
  const addresses = useAddresses();
  const [addressId, setAddressId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [payment, setPayment] = useState<PaymentMethod>('cash_on_delivery');
  const [note, setNote] = useState('');
  // One key per checkout attempt: retries/double-clicks can never create two orders.
  const idempotencyKey = useRef(crypto.randomUUID());

  useEffect(() => {
    if (!addressId && addresses.data?.length) setAddressId((addresses.data.find((a) => a.isDefault) ?? addresses.data[0]!).id);
  }, [addresses.data, addressId]);

  const place = useMutation({
    mutationFn: api.customer.orders.place,
    onSuccess: (order) => {
      qc.invalidateQueries({ queryKey: cartKey });
      qc.invalidateQueries({ queryKey: ['customer', 'orders'] });
      navigate(`/orders/${order.id}`, { replace: true, state: { justPlaced: true } });
    },
    onError: (e) => {
      // Business-rule rejections (e.g. item sold out) are final for this attempt; refresh the cart.
      if (e instanceof ApiError && e.status !== 0) {
        idempotencyKey.current = crypto.randomUUID();
        qc.invalidateQueries({ queryKey: cartKey });
      }
    },
  });

  if (cart.isError) return <ErrorState error={cart.error} onRetry={() => cart.refetch()} />;
  if (cart.isPending || addresses.isPending) return <div className="stack"><Skeleton height={28} width="30%" /><Skeleton height={220} /></div>;
  const c = cart.data;
  if (!c.store || c.items.length === 0) {
    return <EmptyState icon="bag" title="Nothing to check out" message="Your cart is empty." action={<Link to="/food" className="btn btn--primary">Browse food</Link>} />;
  }
  const currency = c.store.currency;
  const list = addresses.data ?? [];
  const showForm = adding || list.length === 0;
  const canPlace = !!addressId && !showForm && c.store.isOpen;
  const err = place.error instanceof ApiError ? place.error : null;

  return (
    <div className="checkout">
      <div className="stack">
        <h1>Checkout</h1>

        <section className="card card--pad stack" aria-labelledby="addr-h">
          <div className="spread">
            <h3 id="addr-h">1. Delivery address</h3>
            {!showForm && <Button variant="ghost" size="sm" onClick={() => setAdding(true)}>+ Add new</Button>}
          </div>
          {showForm ? (
            <AddressForm
              defaultName={user?.fullName}
              onSaved={(a) => { setAddressId(a.id); setAdding(false); }}
              onCancel={list.length ? () => setAdding(false) : undefined}
            />
          ) : (
            <div className="stack" style={{ gap: 'var(--s-2)' }} role="radiogroup" aria-label="Delivery address">
              {list.map((a) => (
                <label key={a.id} className="option">
                  <input type="radio" name="address" checked={addressId === a.id} onChange={() => setAddressId(a.id)} />
                  <div>
                    <strong style={{ textTransform: 'capitalize' }}>{a.label}</strong>
                    <div className="small">{a.recipientName} · {a.phone}</div>
                    <div className="muted small">{[a.line1, a.line2, a.landmark, a.city, a.postalCode].filter(Boolean).join(', ')}</div>
                  </div>
                </label>
              ))}
            </div>
          )}
        </section>

        <section className="card card--pad stack" aria-labelledby="review-h">
          <h3 id="review-h">2. Review order · {c.store.name}</h3>
          {c.items.map((i) => (
            <div key={i.id} className="spread small">
              <span>{i.quantity} × {i.product.name}</span>
              <span>{formatMoney(i.lineTotal, currency)}</span>
            </div>
          ))}
          <Link to="/cart" className="small" style={{ color: 'var(--c-brand)', fontWeight: 600 }}>Edit cart</Link>
          <TextArea label="Note for the restaurant (optional)" maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
        </section>

        <section className="card card--pad stack" aria-labelledby="pay-h">
          <h3 id="pay-h">3. Payment</h3>
          <label className="option">
            <input type="radio" name="payment" checked={payment === 'cash_on_delivery'} onChange={() => setPayment('cash_on_delivery')} />
            <div><strong>Cash on delivery</strong><div className="muted small">Pay with cash or UPI when your order arrives.</div></div>
          </label>
        </section>
      </div>

      <aside className="checkout__aside card card--pad stack">
        <h3>Bill details</h3>
        <Totals totals={c.totals} currency={currency} />
        {err && (
          <div className="badge badge--danger" role="alert" style={{ whiteSpace: 'normal', padding: '8px 12px' }}>
            {err.message}
            {Array.isArray(err.details?.items) && ` (${(err.details.items as string[]).join(', ')})`}
          </div>
        )}
        <Button
          block
          loading={place.isPending}
          disabled={!canPlace}
          onClick={() => addressId && place.mutate({ addressId, paymentMethod: payment, idempotencyKey: idempotencyKey.current, customerNote: note })}
        >
          Place order · {formatMoney(c.totals.total, currency)}
        </Button>
        {!c.store.isOpen && <p className="small muted">This store is closed right now.</p>}
      </aside>
    </div>
  );
}
