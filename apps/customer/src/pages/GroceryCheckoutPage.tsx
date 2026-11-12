import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type DeliveryChoice, type Substitution } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, EmptyState, ErrorState, Icon, Skeleton, TextArea } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { AddressForm } from '../features/addresses/AddressForm';
import { useAddresses } from '../features/addresses/useAddresses';
import { OfferPicker } from '../features/cart/OfferPicker';
import { cartKey, useCart } from '../features/cart/useCart';
import { StatusPill } from '../features/groceries/parts';
import { basketKey } from '../features/groceries/useGroceries';
import { OnlineMethodOptions } from '../features/payments/OnlinePay';
import { WalletOption } from '../features/wallet/WalletOption';
import { walletKey } from '../features/wallet/useWallet';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';
import { useDeliveryLocation } from '../location/LocationProvider';

const SUBS: { id: Substitution; label: string; hint: string }[] = [
  { id: 'none', label: 'Don’t substitute', hint: 'Unavailable items are left out and not charged.' },
  { id: 'similar', label: 'Substitute with a similar item', hint: 'Same kind and size; never a higher price than the original.' },
  { id: 'store_choice', label: 'Let the store choose within my preference', hint: 'Tell the store what you’d accept below.' },
];

/** Grocery checkout: address → per-store delivery mode/slot → substitutions → offers → payment, priced by the server. */
export function GroceryCheckoutPage() {
  useThemeOverride('grocery');
  const { user } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const cart = useCart();
  const addresses = useAddresses();
  const { selected, select } = useDeliveryLocation();
  const [addressId, setAddressId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [delivery, setDelivery] = useState<Record<string, DeliveryChoice>>({});
  const [sub, setSub] = useState<Substitution>('similar');
  const [subNote, setSubNote] = useState('');
  const [note, setNote] = useState('');
  const [payment, setPayment] = useState<string>('cash_on_delivery');
  const key = useRef(crypto.randomUUID());

  useEffect(() => {
    if (!addressId && addresses.data?.length) setAddressId((selected ?? addresses.data.find((a) => a.isDefault) ?? addresses.data[0]!).id);
  }, [addresses.data, addressId, selected]);

  const quote = useQuery({
    queryKey: [...basketKey, 'quote', addressId, delivery, cart.data?.offer?.id ?? null, cart.data?.itemCount],
    queryFn: () => api.groceries.quote(addressId, delivery),
    enabled: !!addressId, placeholderData: keepPreviousData,
  });
  const place = useMutation({
    mutationFn: api.groceries.checkout,
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: cartKey });
      qc.invalidateQueries({ queryKey: basketKey });
      qc.invalidateQueries({ queryKey: ['customer', 'orders'] });
      qc.invalidateQueries({ queryKey: walletKey });
      if (r.checkout && r.orders.length > 1) navigate(`/checkout/done/${r.checkout.id}`, { replace: true });
      else navigate(`/orders/${r.orders[0]!.id}`, { replace: true, state: { justPlaced: true } });
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status !== 0) { key.current = crypto.randomUUID(); qc.invalidateQueries({ queryKey: basketKey }); }
    },
  });

  if (cart.isError) return <ErrorState error={cart.error} onRetry={() => cart.refetch()} />;
  if (cart.isPending || addresses.isPending) return <div className="gr-page" data-theme="grocery"><Skeleton height={28} width="30%" /><Skeleton height={260} /></div>;
  if (!cart.data || cart.data.mode !== 'basket' || cart.data.itemCount === 0) {
    return <div className="gr-page" data-theme="grocery"><EmptyState icon="grocery" title="Your basket is empty" action={<Link to="/groceries" className="btn btn--primary">Browse Groceries</Link>} /></div>;
  }
  const c = cart.data;
  const g = quote.data?.grocery;
  const list = addresses.data ?? [];
  const showForm = adding || list.length === 0;
  const err = place.error instanceof ApiError ? place.error : null;
  const choiceOf = (storeId: string) => delivery[storeId] ?? g?.stores.find((s) => s.storeId === storeId)?.choice ?? null;
  const ready = !!g && g.ready && !!addressId && !showForm && g.stores.every((s) => !s.problem);
  const submit = () => {
    if (!addressId || !g) return;
    const chosen = Object.fromEntries(g.stores.map((s) => [s.storeId, choiceOf(s.storeId)!]));
    place.mutate({ addressId, paymentMethod: payment as 'cash_on_delivery', idempotencyKey: key.current, substitution: sub, substitutionNote: sub === 'store_choice' ? subNote : '', customerNote: note, delivery: chosen });
  };

  return (
    <div className="gr-page" data-theme="grocery">
      <Link to="/groceries/basket" className="gr-back"><Icon name="back" size={18} /> Basket</Link>
      <h1 className="gr-title">Checkout</h1>
      <div className="checkout">
        <div className="stack">
          <section className="card card--pad stack" aria-labelledby="g-addr">
            <div className="spread"><h3 id="g-addr">1. Delivery address</h3>{!showForm && <Button variant="ghost" size="sm" onClick={() => setAdding(true)}>+ Add new</Button>}</div>
            {showForm ? (
              <AddressForm defaultName={user?.fullName} onSaved={(a) => { setAddressId(a.id); select(a.id); setAdding(false); }} onCancel={list.length ? () => setAdding(false) : undefined} />
            ) : (
              <div className="stack" style={{ gap: 'var(--s-2)' }} role="radiogroup" aria-label="Delivery address">
                {list.map((a) => (
                  <label key={a.id} className="option">
                    <input type="radio" name="address" checked={addressId === a.id} onChange={() => { setAddressId(a.id); select(a.id); setDelivery({}); }} />
                    <div><strong style={{ textTransform: 'capitalize' }}>{a.label}</strong>
                      <div className="muted small">{[a.line1, a.line2, a.city, a.postalCode].filter(Boolean).join(', ')}</div>
                      {(!a.latitude || !a.longitude) && <div className="small gr-warn">No map pin: delivery times can’t be estimated for this address.</div>}
                    </div>
                  </label>
                ))}
              </div>
            )}
          </section>

          <section className="card card--pad stack" aria-labelledby="g-del">
            <h3 id="g-del">2. Delivery {c.groups.length > 1 ? `(${c.groups.length} stores, delivered separately)` : ''}</h3>
            {!g ? <Skeleton height={120} /> : c.groups.map((grp) => {
              const s = g.stores.find((x) => x.storeId === grp.store.id);
              if (!s) return null;
              const ch = choiceOf(s.storeId);
              const sched = s.options.find((o) => o.mode === 'scheduled');
              return (
                <div key={s.storeId} className="gr-deliv">
                  <div className="spread"><strong>{grp.store.name}</strong><StatusPill status={s.status} /></div>
                  <div className="gr-deliv__modes" role="radiogroup" aria-label={`Delivery for ${grp.store.name}`}>
                    {s.options.map((o) => (
                      <label key={o.mode} className={`gr-deliv__mode${o.available ? '' : ' is-off'}`}>
                        <input type="radio" name={`mode-${s.storeId}`} disabled={!o.available} checked={ch?.mode === o.mode}
                          onChange={() => setDelivery((d) => ({ ...d, [s.storeId]: { mode: o.mode, slotStart: o.mode === 'scheduled' ? o.slots[0]?.start ?? null : null } }))} />
                        <span><strong>{o.label}</strong><span className="small muted">{o.available ? `${o.summary}${o.fee != null ? ` · ${Number(o.fee) ? formatMoney(o.fee) : 'free'}` : ''}` : o.reason}</span></span>
                      </label>
                    ))}
                  </div>
                  {ch?.mode === 'scheduled' && sched && (
                    <label className="gr-select gr-select--block">
                      <span className="small">Delivery slot</span>
                      <select value={ch.slotStart ?? ''} onChange={(e) => setDelivery((d) => ({ ...d, [s.storeId]: { mode: 'scheduled', slotStart: e.target.value } }))}>
                        {sched.slots.map((sl) => <option key={sl.start} value={sl.start}>{sl.day} · {sl.label}{sl.remaining <= 2 ? ` (${sl.remaining} left)` : ''}</option>)}
                      </select>
                    </label>
                  )}
                  {s.problem && <p className="small gr-warn">{s.problem}</p>}
                  {s.minimumRemaining && <p className="small gr-warn">Add {formatMoney(s.minimumRemaining)} more from {grp.store.name} to place this order.</p>}
                </div>
              );
            })}
            <p className="small muted"><Icon name="clock" size={14} /> Times are estimates from each store’s packing time, distance and current orders. You’ll see status updates as the store progresses; there’s no live rider map yet.</p>
          </section>

          <section className="card card--pad stack" aria-labelledby="g-sub">
            <h3 id="g-sub">3. If an item is unavailable</h3>
            <div className="stack" role="radiogroup" aria-label="Substitution preference" style={{ gap: 'var(--s-2)' }}>
              {SUBS.map((o) => (
                <label key={o.id} className="option"><input type="radio" name="sub" checked={sub === o.id} onChange={() => setSub(o.id)} />
                  <div><strong>{o.label}</strong><div className="small muted">{o.hint}</div></div></label>
              ))}
            </div>
            {sub === 'store_choice' && <TextArea label="Your preference (optional)" maxLength={200} value={subNote} onChange={(e) => setSubNote(e.target.value)} placeholder="e.g. Any brand of toned milk, no organic swaps" />}
            {c.items.some((i) => i.product.unitLabel && /kg|g\b/.test(i.product.unitLabel)) && (
              <p className="small muted"><Icon name="alert" size={14} /> Loose produce is weighed when packed. You pay the price shown, never more; if it’s lighter, the store adjusts down.</p>
            )}
            <TextArea label="Note for the store (optional)" maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
          </section>

          <section className="card card--pad stack" aria-labelledby="g-off">
            <h3 id="g-off">4. Offers</h3>
            <OfferPicker cart={c} />
          </section>

          <section className="card card--pad stack" aria-labelledby="g-pay">
            <h3 id="g-pay">5. Payment</h3>
            <label className="option"><input type="radio" name="payment" checked={payment === 'cash_on_delivery'} onChange={() => setPayment('cash_on_delivery')} />
              <div><strong>Cash on delivery</strong><div className="muted small">Pay with cash or UPI when each order arrives.</div></div></label>
            <WalletOption total={g?.total ?? c.totals.total} currency="INR" checked={payment === 'wallet'} onSelect={() => setPayment('wallet')} />
            <OnlineMethodOptions value={payment} onChange={setPayment} />
          </section>
        </div>

        <aside className="checkout__aside card card--pad stack">
          <h3>Bill details</h3>
          {g?.stores.map((s) => {
            const grp = c.groups.find((x) => x.store.id === s.storeId);
            return (
              <div key={s.storeId} className="stack" style={{ gap: 4 }}>
                {c.groups.length > 1 && <strong className="small">{grp?.store.name}</strong>}
                <div className="spread small"><span>Items</span><span>{formatMoney(s.subtotal)}</span></div>
                <div className="spread small"><span>Delivery</span><span>{Number(s.deliveryFee) ? formatMoney(s.deliveryFee) : 'Free'}</span></div>
                <div className="spread small"><span>Taxes</span><span>{formatMoney(s.tax)}</span></div>
                {Number(s.discount) > 0 && <div className="spread small gr-save"><span>{s.offerTitle || 'Offer'}</span><span>−{formatMoney(s.discount)}</span></div>}
              </div>
            );
          })}
          <div className="spread"><strong>To pay</strong><strong>{g ? formatMoney(g.total) : '…'}</strong></div>
          {err && (
            <div className="gr-callout" role="alert">
              <span>{err.message}{Array.isArray(err.details?.items) && ` (${(err.details.items as { name?: string }[] | string[]).map((x) => (typeof x === 'string' ? x : x.name)).join(', ')})`}</span>
              {['price_changed', 'items_unavailable', 'store_unavailable'].includes(err.code ?? '') && <Link to="/groceries/basket" className="btn btn--sm btn--outline">Review basket</Link>}
              {err.code === 'store_unavailable' && <Link to="/groceries" className="btn btn--sm btn--outline">Find another store</Link>}
            </div>
          )}
          {g && !g.ready && !err && <p className="small gr-warn">Your basket needs attention before you can order. <Link to="/groceries/basket">Review basket</Link></p>}
          <Button block loading={place.isPending} disabled={!ready || place.isPending} onClick={submit}>
            Place {c.groups.length > 1 ? `${c.groups.length} orders` : 'order'}{g ? ` · ${formatMoney(g.total)}` : ''}
          </Button>
          <p className="small muted">Nothing is charged until you place the order. You can cancel until the store starts packing.</p>
        </aside>
      </div>
    </div>
  );
}
