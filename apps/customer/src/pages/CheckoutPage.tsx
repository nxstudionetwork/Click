import { useEffect, useRef, useState } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type PaymentMethod } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, EmptyState, ErrorState, Icon, Skeleton, TextArea } from '../components/ui';
import { AddressForm } from '../features/addresses/AddressForm';
import { useAddresses } from '../features/addresses/useAddresses';
import { OfferPicker } from '../features/cart/OfferPicker';
import { Totals } from '../features/cart/Totals';
import { cartKey, useCart } from '../features/cart/useCart';
import { deliveryWindow } from '../features/shop/time';
import { api } from '../lib/api';
import { useDeliveryLocation } from '../location/LocationProvider';
import { WalletOption } from '../features/wallet/WalletOption';
import { walletKey } from '../features/wallet/useWallet';
import { formatMoney } from '../lib/format';

export function CheckoutPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const cart = useCart();
  const addresses = useAddresses();
  const { selected: selectedLocation, select: selectLocation } = useDeliveryLocation();
  const [addressId, setAddressId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [payment, setPayment] = useState<PaymentMethod>('cash_on_delivery');
  const [note, setNote] = useState('');
  // One key per checkout attempt: retries/double-clicks can never create two orders (or two checkouts).
  const idempotencyKey = useRef(crypto.randomUUID());
  const marketplace = cart.data?.mode === 'marketplace';
  // Per-seller delivery estimates for the chosen address (Shopping only; food uses the store's ETA).
  const estimates = useQuery({ queryKey: [...cartKey, 'estimates', addressId], queryFn: () => api.customer.cart.get(addressId),
    enabled: marketplace && !!addressId, staleTime: 30_000 });

  useEffect(() => {
    if (!addressId && addresses.data?.length) setAddressId((selectedLocation ?? addresses.data.find((a) => a.isDefault) ?? addresses.data[0]!).id);
  }, [addresses.data, addressId, selectedLocation]);

  const onError = (e: unknown) => {
    // Business-rule rejections (e.g. item sold out, deal ended) are final for this attempt; refresh the cart.
    if (e instanceof ApiError && e.status !== 0) {
      idempotencyKey.current = crypto.randomUUID();
      qc.invalidateQueries({ queryKey: cartKey });
    }
  };
  const done = () => {
    qc.invalidateQueries({ queryKey: cartKey });
    qc.invalidateQueries({ queryKey: ['customer', 'orders'] });
    qc.invalidateQueries({ queryKey: walletKey });
  };
  const place = useMutation({
    mutationFn: api.customer.orders.place,
    onSuccess: (order) => { done(); navigate(`/orders/${order.id}`, { replace: true, state: { justPlaced: true } }); },
    onError,
  });
  const checkout = useMutation({
    mutationFn: api.customer.orders.checkout,
    onSuccess: (r) => {
      done();
      if (r.checkout && r.orders.length > 1) navigate(`/checkout/done/${r.checkout.id}`, { replace: true });
      else navigate(`/orders/${r.orders[0]!.id}`, { replace: true, state: { justPlaced: true } });
    },
    onError,
  });
  const submitting = place.isPending || checkout.isPending;

  const c = cart.data;
  const codAvailable = !c || c.groups.every((g) => g.codAvailable);
  useEffect(() => { if (!codAvailable && payment === 'cash_on_delivery') setPayment('wallet'); }, [codAvailable, payment]);

  if (c?.mode === 'basket') return <Navigate to="/groceries/checkout" replace />;
  if (cart.isError) return <ErrorState error={cart.error} onRetry={() => cart.refetch()} />;
  if (cart.isPending || addresses.isPending) return <div className="stack"><Skeleton height={28} width="30%" /><Skeleton height={220} /></div>;
  if (!c || c.items.length === 0) {
    return <EmptyState icon="bag" title="Nothing to check out" message="Your cart is empty." action={<Link to="/shopping" className="btn btn--primary">Browse Shopping</Link>} />;
  }
  const currency = c.groups[0]?.store.currency ?? 'INR';
  const list = addresses.data ?? [];
  const showForm = adding || list.length === 0;
  const open = c.groups.every((g) => g.store.isOpen);
  const canPlace = !!addressId && !showForm && open && c.items.every((i) => i.isAvailable);
  const err = [place.error, checkout.error].find((e): e is ApiError => e instanceof ApiError) ?? null;
  const estimateFor = (storeId: string) => estimates.data?.groups.find((g) => g.store.id === storeId)?.deliveryEstimate ?? null;

  const submit = () => {
    if (!addressId) return;
    const input = { addressId, paymentMethod: payment, idempotencyKey: idempotencyKey.current, customerNote: note };
    if (marketplace) checkout.mutate(input); else place.mutate(input);
  };

  return (
    <div className="checkout" data-theme={marketplace ? 'shopping' : undefined}>
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
              onSaved={(a) => { setAddressId(a.id); selectLocation(a.id); setAdding(false); }}
              onCancel={list.length ? () => setAdding(false) : undefined}
            />
          ) : (
            <div className="stack" style={{ gap: 'var(--s-2)' }} role="radiogroup" aria-label="Delivery address">
              {list.map((a) => (
                <label key={a.id} className="option">
                  <input type="radio" name="address" checked={addressId === a.id} onChange={() => { setAddressId(a.id); selectLocation(a.id); }} />
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
          <h3 id="review-h">2. {marketplace ? `Review ${c.groups.length > 1 ? `${c.groups.length} deliveries` : 'delivery'}` : `Review order · ${c.groups[0]?.store.name ?? ''}`}</h3>
          {c.groups.map((g) => {
            const est = estimateFor(g.store.id);
            return (
              <div key={g.store.id} className="seller-group">
                {marketplace && (
                  <div className="seller-group__head">
                    <strong className="small">From {g.store.name}</strong>
                    <span className="seller-group__est">
                      Standard delivery · {Number(g.deliveryFee) ? formatMoney(g.deliveryFee, currency) : 'Free'}
                      {est ? ` · estimated ${deliveryWindow(est)}` : estimates.isFetching ? ' · estimating…' : ''}
                    </span>
                  </div>
                )}
                {c.items.filter((i) => g.itemIds.includes(i.id)).map((i) => (
                  <div key={i.id} className="spread small">
                    <span>{i.quantity} × {i.product.name}{(i.variant || i.options.length > 0) && <span className="muted"> ({i.variant?.label ?? i.options.map((o) => o.name).join(', ')})</span>}</span>
                    <span>{formatMoney(i.lineTotal, currency)}</span>
                  </div>
                ))}
              </div>
            );
          })}
          {marketplace && c.groups.length > 1 && <p className="small muted">Each seller ships separately, so this becomes {c.groups.length} orders you can track one by one.</p>}
          <Link to="/cart" className="small" style={{ color: 'var(--c-brand)', fontWeight: 600 }}>Edit cart</Link>
          <TextArea label={marketplace ? 'Delivery note (optional)' : 'Note for the restaurant (optional)'} maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
        </section>

        <section className="card card--pad stack" aria-labelledby="offer-h">
          <h3 id="offer-h">3. Offers</h3>
          <OfferPicker cart={c} />
        </section>

        <section className="card card--pad stack" aria-labelledby="pay-h">
          <h3 id="pay-h">4. Payment</h3>
          <label className="option" style={!codAvailable ? { opacity: 0.6, cursor: 'not-allowed' } : undefined}>
            <input type="radio" name="payment" disabled={!codAvailable} checked={payment === 'cash_on_delivery'} onChange={() => setPayment('cash_on_delivery')} />
            <div><strong>Cash on delivery</strong><div className="muted small">
              {codAvailable ? 'Pay with cash or UPI when your order arrives.' : `Not available: ${c.groups.filter((g) => !g.codAvailable).map((g) => g.store.name).join(', ')} accepts prepaid orders only.`}
            </div></div>
          </label>
          <WalletOption total={c.totals.total} currency={currency} checked={payment === 'wallet'} onSelect={() => setPayment('wallet')} />
          <p className="small muted"><Icon name="shield" size={14} /> Online card and UPI payments aren’t connected yet.</p>
        </section>
      </div>

      <aside className="checkout__aside card card--pad stack">
        <h3>Bill details</h3>
        <Totals totals={c.totals} currency={currency} offerTitle={c.offer?.title} />
        {err && (
          <div className="badge badge--danger" role="alert" style={{ whiteSpace: 'normal', padding: '8px 12px' }}>
            {err.message}
            {Array.isArray(err.details?.items) && ` (${(err.details.items as string[]).join(', ')})`}
          </div>
        )}
        <Button block loading={submitting} disabled={!canPlace || submitting} onClick={submit}>
          Place {marketplace && c.groups.length > 1 ? `${c.groups.length} orders` : 'order'} · {formatMoney(c.totals.total, currency)}
        </Button>
        {!open && <p className="small muted">A store in your cart isn’t taking orders right now.</p>}
      </aside>
    </div>
  );
}
