import { Link } from 'react-router-dom';
import { Button, EmptyState, ErrorState, QuantityStepper, Skeleton, SmartImage, useToast } from '../components/ui';
import { Totals } from '../features/cart/Totals';
import { useCart, useCartActions } from '../features/cart/useCart';
import { formatMoney } from '../lib/format';

export function CartPage() {
  const cart = useCart();
  const { update, remove, clear } = useCartActions();
  const toast = useToast();
  const onError = (e: unknown) => toast(e instanceof Error ? e.message : 'Could not update cart.', 'error');

  if (cart.isError) return <ErrorState error={cart.error} onRetry={() => cart.refetch()} />;
  if (cart.isPending) return <div className="stack"><Skeleton height={28} width="30%" /><Skeleton height={180} /></div>;

  const c = cart.data;
  if (!c.store || c.items.length === 0) {
    return <EmptyState icon="bag" title="Your cart is empty" message="Add something delicious to get started." action={<Link to="/food" className="btn btn--primary">Browse food</Link>} />;
  }
  const currency = c.store.currency;
  const belowMin = Number(c.totals.subtotal) < Number(c.store.minOrderAmount);
  const busy = update.isPending || remove.isPending;

  return (
    <div className="checkout">
      <div className="stack">
        <h1>Your cart</h1>
        <div className="card card--pad">
          <Link to={`/stores/${c.store.slug}`} className="row" style={{ marginBottom: 8 }}>
            <SmartImage src={c.store.imageUrl} alt={c.store.name} className="" />
            <strong>{c.store.name}</strong>
          </Link>
          {c.items.map((i) => (
            <div key={i.id} className="line">
              <div>
                <div>{i.product.name}</div>
                {i.note && <div className="muted small">“{i.note}”</div>}
                {!i.product.isAvailable && <span className="badge badge--warning">No longer available</span>}
              </div>
              <QuantityStepper
                value={i.quantity}
                busy={busy}
                label={i.product.name}
                onChange={(n) => (n <= 0 ? remove.mutate(i.id, { onError }) : update.mutate({ id: i.id, quantity: n }, { onError }))}
              />
              <strong style={{ minWidth: 72, textAlign: 'right' }}>{formatMoney(i.lineTotal, currency)}</strong>
            </div>
          ))}
        </div>
        <Button variant="ghost" size="sm" onClick={() => clear.mutate(undefined, { onError })} loading={clear.isPending} style={{ alignSelf: 'flex-start' }}>
          Clear cart
        </Button>
      </div>
      <aside className="checkout__aside card card--pad stack">
        <h3>Bill details</h3>
        <Totals totals={c.totals} currency={currency} />
        {belowMin && <p className="badge badge--warning">Add {formatMoney(Number(c.store.minOrderAmount) - Number(c.totals.subtotal), currency)} more to reach the minimum order</p>}
        {!c.store.isOpen && <p className="badge badge--danger">This store is closed right now</p>}
        <Link to="/checkout" className={`btn btn--primary btn--block ${belowMin || !c.store.isOpen ? 'disabled' : ''}`} aria-disabled={belowMin || !c.store.isOpen} onClick={(e) => (belowMin || !c.store?.isOpen) && e.preventDefault()} style={belowMin || !c.store.isOpen ? { opacity: 0.55, cursor: 'not-allowed' } : undefined}>
          Proceed to checkout
        </Link>
      </aside>
    </div>
  );
}
