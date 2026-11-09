import { Link, Navigate } from 'react-router-dom';
import type { Cart, CartGroup } from '@click/api';
import { Button, EmptyState, ErrorState, Icon, QuantityStepper, Skeleton, SmartImage, useToast } from '../components/ui';
import { Totals } from '../features/cart/Totals';
import { useCart, useCartActions } from '../features/cart/useCart';
import { formatMoney } from '../lib/format';

/**
 * The one Click. cart. Food and groceries come from a single store; Shopping carts can hold several sellers, each
 * shown as its own parcel (delivery fee, free-delivery threshold) and placed as its own order at checkout.
 */
export function CartPage() {
  const cart = useCart();
  const { update, remove, clear } = useCartActions();
  const toast = useToast();
  const onError = (e: unknown) => toast(e instanceof Error ? e.message : 'Could not update cart.', 'error');

  if (cart.isError) return <ErrorState error={cart.error} onRetry={() => cart.refetch()} />;
  if (cart.isPending) return <div className="stack"><Skeleton height={28} width="30%" /><Skeleton height={180} /></div>;

  const c = cart.data;
  // Grocery baskets have their own page (per-store delivery, substitutions, price checks).
  if (c.mode === 'basket' && c.items.length > 0) return <Navigate to="/groceries/basket" replace />;
  if (c.items.length === 0) {
    return (
      <EmptyState icon="bag" title="Your cart is waiting for something great." message="Add something from Food, Groceries or Shopping."
        action={<div className="row" style={{ flexWrap: 'wrap', justifyContent: 'center' }}><Link to="/shopping" className="btn btn--primary">Browse Shopping</Link><Link to="/food" className="btn btn--outline">Order food</Link></div>} />
    );
  }
  const marketplace = c.mode === 'marketplace';
  const currency = c.groups[0]?.store.currency ?? 'INR';
  const blocked = c.groups.some((g) => g.belowMinimum || !g.store.isOpen) || c.items.some((i) => !i.isAvailable);
  const busy = update.isPending || remove.isPending;

  return (
    <div className="checkout" data-theme={marketplace ? 'shopping' : undefined}>
      <div className="stack">
        <div className="spread"><h1>Your cart</h1>{marketplace && c.groups.length > 1 && <span className="small muted">{c.groups.length} sellers · {c.groups.length} deliveries</span>}</div>
        {c.groups.map((g) => (
          <GroupCard key={g.store.id} cart={c} g={g} marketplace={marketplace} busy={busy}
            onQty={(id, n) => (n <= 0 ? remove.mutate(id, { onError }) : update.mutate({ id, quantity: n }, { onError }))} />
        ))}
        <Button variant="ghost" size="sm" onClick={() => clear.mutate(undefined, { onError })} loading={clear.isPending} style={{ alignSelf: 'flex-start' }}>Clear cart</Button>
      </div>
      <aside className="checkout__aside card card--pad stack">
        <h3>Bill details</h3>
        <Totals totals={c.totals} currency={currency} offerTitle={c.offer?.title} />
        {c.items.some((i) => !i.isAvailable) && <p className="badge badge--warning" style={{ whiteSpace: 'normal' }}>Remove items that are no longer available to continue.</p>}
        <Link to="/checkout" className={`btn btn--primary btn--block ${blocked ? 'disabled' : ''}`} aria-disabled={blocked}
          onClick={(e) => blocked && e.preventDefault()} style={blocked ? { opacity: 0.55, cursor: 'not-allowed' } : undefined}>
          Proceed to checkout
        </Link>
        {marketplace && <Link to="/shopping" className="btn btn--ghost btn--block">Continue shopping</Link>}
      </aside>
    </div>
  );
}

function GroupCard({ cart, g, marketplace, busy, onQty }: { cart: Cart; g: CartGroup; marketplace: boolean; busy: boolean; onQty: (id: string, n: number) => void }) {
  const items = cart.items.filter((i) => g.itemIds.includes(i.id));
  const s = g.store;
  return (
    <section className="card card--pad seller-group" aria-label={`From ${s.name}`}>
      <div className="seller-group__head">
        <Link to={marketplace ? `/shopping/search?seller=${s.slug}` : `/stores/${s.slug}`} className="row">
          {!marketplace && <SmartImage src={s.imageUrl} alt={s.name} className="thumb" />}
          <span><span className="small muted">{marketplace ? 'Sold by ' : ''}</span><strong>{s.name}</strong>
            {s.isVerified && marketplace && <span className="verified" style={{ marginLeft: 6 }}><Icon name="shield" size={12} /> Verified</span>}</span>
        </Link>
        {marketplace && <span className="small">{Number(g.deliveryFee) ? `Delivery ${formatMoney(g.deliveryFee, s.currency)}` : 'Free delivery'}</span>}
      </div>
      {g.freeDeliveryRemaining && <p className="shop-note"><Icon name="parcel" size={16} /> Add {formatMoney(g.freeDeliveryRemaining, s.currency)} more from {s.name} for free delivery.</p>}
      {items.map((i) => (
        <div key={i.id} className="line">
          <div>
            <Link to={`/products/${i.product.id}`}>{i.product.name}</Link>
            {i.variant && <div className="muted small">{i.variant.label}</div>}
            {i.options.length > 0 && <div className="muted small">{i.options.map((o) => o.name).join(' · ')}</div>}
            {i.note && <div className="muted small">“{i.note}”</div>}
            {!i.isAvailable && <span className="badge badge--warning">No longer available</span>}
          </div>
          <QuantityStepper value={i.quantity} busy={busy} label={i.product.name} onChange={(n) => onQty(i.id, n)} />
          <strong style={{ minWidth: 72, textAlign: 'right' }}>{formatMoney(i.lineTotal, s.currency)}</strong>
        </div>
      ))}
      {g.belowMinimum && <p className="badge badge--warning">Add {formatMoney(Number(s.minOrderAmount) - Number(g.subtotal), s.currency)} more to reach {s.name}’s minimum order</p>}
      {!s.isOpen && <p className="badge badge--danger">{s.name} isn’t taking orders right now</p>}
    </section>
  );
}
