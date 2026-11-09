import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@click/api';
import { Button, EmptyState, ErrorState, Icon, Skeleton, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { cartKey } from '../features/cart/useCart';
import { AddControl, GroceryImage, ProductCard, StatusPill } from '../features/groceries/parts';
import { basketKey, useBasketActions, useGroceryBasket } from '../features/groceries/useGroceries';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';
import { useDeliveryLocation } from '../location/LocationProvider';

/**
 * The grocery basket, one sub-basket per store (each becomes its own order with its own minimum, fee and delivery).
 * Price changes, sold-out items and closed stores are shown here with what to do next — never fixed silently.
 */
export function GroceryBasketPage() {
  useThemeOverride('grocery');
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const { selected } = useDeliveryLocation();
  const basket = useGroceryBasket(selected?.id ?? null);
  const { setQuantity, busy } = useBasketActions();
  const ack = useMutation({
    mutationFn: () => api.groceries.acknowledgePrices(selected?.id),
    onSuccess: (b) => { qc.setQueryData([...basketKey, selected?.id ?? null], b); qc.invalidateQueries({ queryKey: cartKey }); },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t update prices.', 'error'),
  });

  if (basket.isError) return <ErrorState error={basket.error} onRetry={() => basket.refetch()} />;
  if (basket.isPending) return <div className="gr-page" data-theme="grocery"><Skeleton height={28} width="40%" /><Skeleton height={220} radius={20} /></div>;
  const { cart, grocery: g } = basket.data;
  if (cart.mode !== 'basket' || cart.items.length === 0 || !g) {
    return (
      <div className="gr-page" data-theme="grocery">
        <EmptyState icon="grocery" title="Your basket is waiting" message={cart.items.length ? 'Your cart has Food or Shopping items. They check out separately.' : 'Add groceries from stores near you.'}
          action={<Link to={cart.items.length ? '/cart' : '/groceries'} className="btn btn--primary">{cart.items.length ? 'Open cart' : 'Browse Groceries'}</Link>} />
      </div>
    );
  }
  const unavailable = new Map(g.unavailable.map((u) => [u.itemId, u]));
  const changes = new Map(g.priceChanges.map((c) => [c.itemId, c]));
  const blocked = g.unavailable.length > 0 || g.priceChanges.length > 0 || g.stores.some((s) => s.minimumRemaining || s.status.state === 'unavailable');

  return (
    <div className="gr-page" data-theme="grocery">
      <Link to="/groceries" className="gr-back"><Icon name="back" size={18} /> Keep shopping</Link>
      <h1 className="gr-title">Your basket</h1>
      {cart.groups.length > 1 && (
        <p className="small gr-note"><Icon name="store" size={14} /> Items from {cart.groups.length} stores. Each store packs and delivers its part separately, so you’ll get {cart.groups.length} orders with their own delivery fee and timing.</p>
      )}

      {g.priceChanges.length > 0 && (
        <div className="gr-callout" role="alert">
          <div>
            <strong>Some prices changed</strong>
            {g.priceChanges.map((c) => <p key={c.itemId} className="small">The price of {c.name} changed from {formatMoney(c.from)} to {formatMoney(c.to)}.</p>)}
          </div>
          <Button size="sm" onClick={() => ack.mutate()} loading={ack.isPending}>Accept new prices</Button>
        </div>
      )}

      {cart.groups.map((grp) => {
        const s = g.stores.find((x) => x.storeId === grp.store.id);
        const items = cart.items.filter((i) => grp.itemIds.includes(i.id));
        return (
          <section key={grp.store.id} className="gr-basket card" aria-label={`From ${grp.store.name}`}>
            <header className="gr-basket__head">
              <Link to={`/groceries/store/${grp.store.slug}`}><strong>{grp.store.name}</strong></Link>
              {s && <StatusPill status={s.status} />}
            </header>
            {items.map((i) => {
              const u = unavailable.get(i.id);
              const ch = changes.get(i.id);
              return (
                <div key={i.id} className={`gr-line${u ? ' gr-line--off' : ''}`}>
                  {i.listing && <span className="gr-line__img"><GroceryImage l={i.listing} /></span>}
                  <div className="gr-line__main">
                    <strong>{i.listing?.brand ? `${i.listing.brand} ` : ''}{i.product.name}</strong>
                    <span className="small muted">{i.listing?.size ?? i.product.unitLabel} · {formatMoney(i.unitPrice)} each{i.listing?.variableWeight ? ' · weighed, never charged more' : ''}</span>
                    {ch && <span className="small gr-warn">Was {formatMoney(ch.from)}, now {formatMoney(ch.to)}</span>}
                    {u && (
                      <div className="gr-line__alt">
                        <span className="small gr-warn">{i.product.name} is no longer available from this store ({u.reason.toLowerCase()}).</span>
                        <div className="row">
                          <button type="button" className="link-btn small" onClick={() => setQuantity(i.product.id, 0)}>Remove</button>
                          {u.alternatives.length > 0 && <span className="small muted">or choose:</span>}
                        </div>
                        {u.alternatives.length > 0 && <div className="gr-rail gr-rail--tight">{u.alternatives.map((a) => <ProductCard key={a.id} l={a} />)}</div>}
                      </div>
                    )}
                  </div>
                  <div className="gr-line__side">
                    {!u && i.listing ? <AddControl l={i.listing} compact /> : !u && (
                      <div className="gr-qty"><button type="button" disabled={busy} onClick={() => setQuantity(i.product.id, i.quantity - 1)}>−</button><span>{i.quantity}</span><button type="button" disabled={busy} onClick={() => setQuantity(i.product.id, i.quantity + 1)}>+</button></div>
                    )}
                    <strong>{formatMoney(i.lineTotal)}</strong>
                  </div>
                </div>
              );
            })}
            {s && (
              <footer className="gr-basket__foot">
                {s.minimumRemaining && <p className="small gr-warn">Add {formatMoney(s.minimumRemaining)} more to place this order (minimum order at {grp.store.name}).</p>}
                {s.freeDeliveryRemaining && !s.minimumRemaining && <p className="small muted">Add {formatMoney(s.freeDeliveryRemaining)} more for a lower delivery fee.</p>}
                <div className="spread small"><span>Items</span><span>{formatMoney(s.subtotal)}</span></div>
                <div className="spread small"><span>Delivery {s.choice ? `(${s.choice.mode})` : ''}</span><span>{s.problem ? s.problem : Number(s.deliveryFee) ? formatMoney(s.deliveryFee) : 'Free'}</span></div>
              </footer>
            )}
          </section>
        );
      })}

      <aside className="gr-sum card card--pad">
        <div className="spread"><span>Estimated total</span><strong>{formatMoney(g.total)}</strong></div>
        <p className="small muted">Delivery mode, slot, offers and taxes are confirmed on the next step.</p>
        <Button block disabled={blocked} onClick={() => navigate('/groceries/checkout')}>Continue to checkout</Button>
        {blocked && <p className="small muted">Resolve the items marked above to continue.</p>}
        <Link to="/groceries/lists" className="small">Add from your shopping list</Link>
      </aside>
    </div>
  );
}
