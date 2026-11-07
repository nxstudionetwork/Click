import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import type { Product } from '@click/api';
import { ApiError } from '@click/api';
import { EmptyState, ErrorState, Icon, Rating, Skeleton, SmartImage, useToast } from '../components/ui';
import { CartBar } from '../features/cart/CartBar';
import { useCart, useCartActions } from '../features/cart/useCart';
import { ProductRow } from '../features/menu/ProductRow';
import { ProductSheet } from '../features/menu/ProductSheet';
import { useAddToCart } from '../features/menu/useAddToCart';
import { useMenu, useStore } from '../features/stores/hooks';
import { etaLabel, formatMoney, priceLevelLabel } from '../lib/format';

export function StorePage() {
  const { slug = '' } = useParams();
  const store = useStore(slug);
  const menu = useMenu(slug);
  const { data: cart } = useCart();
  const { update, remove } = useCartActions();
  const { addToCart, isAdding } = useAddToCart();
  const toast = useToast();
  const [selected, setSelected] = useState<Product | null>(null);

  if (store.isError) {
    return store.error instanceof ApiError && store.error.status === 404 ? (
      <EmptyState icon="alert" title="Store not found" message="It may have moved or is no longer on Click." action={<Link className="btn btn--outline" to="/food">Browse food</Link>} />
    ) : (
      <ErrorState error={store.error} onRetry={() => store.refetch()} />
    );
  }
  if (store.isPending) return <div className="stack"><Skeleton height={200} radius={22} /><Skeleton height={28} width="60%" /><Skeleton height={60} /></div>;

  const s = store.data;
  const qtyFor = (productId: string) => cart?.items.find((i) => i.product.id === productId);
  const busy = isAdding || update.isPending || remove.isPending;

  const changeQty = (productId: string, next: number) => {
    const item = qtyFor(productId);
    if (!item) return;
    const onError = (e: unknown) => toast(e instanceof Error ? e.message : 'Could not update cart.', 'error');
    if (next <= 0) remove.mutate(item.id, { onError });
    else update.mutate({ id: item.id, quantity: next }, { onError });
  };

  return (
    <>
      <Link to="/food" className="btn btn--ghost btn--sm" style={{ marginBottom: 12, paddingLeft: 4 }}><Icon name="back" size={18} /> Food</Link>
      <section className="store-hero">
        <SmartImage src={s.imageUrl} alt={s.name} className="store-hero__media" />
        <div className="stack" style={{ gap: 'var(--s-3)' }}>
          <div className="stack" style={{ gap: 4 }}>
            <h1>{s.name}</h1>
            <span className="muted">{s.categories.map((c) => c.name).join(' · ')} {s.locality && <span className="dot-sep">{s.locality}</span>}</span>
          </div>
          {!s.isOpen && <div className="badge badge--danger" style={{ alignSelf: 'flex-start', padding: '6px 12px' }}>Closed — not accepting orders right now</div>}
          <div className="store-facts">
            <div><strong><Rating value={s.ratingAverage} /></strong><span>{s.ratingCount.toLocaleString('en-IN')} ratings</span></div>
            <div><strong>{etaLabel(s.deliveryTimeMin, s.deliveryTimeMax)}</strong><span>Delivery</span></div>
            <div><strong>{priceLevelLabel(s.priceLevel)}</strong><span>Min {formatMoney(s.minOrderAmount, s.currency)}</span></div>
          </div>
          {s.offers.length > 0 && (
            <div className="row" style={{ flexWrap: 'wrap' }}>
              {s.offers.map((o) => <span key={o.id} className="badge badge--brand"><Icon name="tag" size={14} />{o.title}</span>)}
            </div>
          )}
        </div>
      </section>

      {menu.isError ? (
        <ErrorState error={menu.error} onRetry={() => menu.refetch()} />
      ) : menu.isPending ? (
        <div className="stack" style={{ marginTop: 24 }}>{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} height={96} />)}</div>
      ) : menu.data.categories.length === 0 ? (
        <EmptyState title="Menu coming soon" message="This store hasn’t published its menu yet." />
      ) : (
        <>
          <nav className="menu-nav chips" aria-label="Menu sections">
            {menu.data.categories.map((c) => (
              <a key={c.id} className="chip" href={`#menu-${c.id}`} style={{ display: 'inline-flex', alignItems: 'center' }}>{c.name}</a>
            ))}
          </nav>
          {menu.data.categories.map((c) => (
            <section key={c.id} id={`menu-${c.id}`} className="menu-section section" style={{ marginTop: 'var(--s-4)' }}>
              <h2>{c.name} <span className="muted small">({c.products.length})</span></h2>
              <div className="product-list">
                {c.products.map((p) => (
                  <ProductRow
                    key={p.id}
                    product={p}
                    currency={s.currency}
                    quantity={qtyFor(p.id)?.quantity ?? 0}
                    canOrder={s.isOpen}
                    busy={busy}
                    onOpen={() => setSelected(p)}
                    onAdd={() => addToCart(p)}
                    onChangeQuantity={(n) => changeQty(p.id, n)}
                  />
                ))}
              </div>
            </section>
          ))}
        </>
      )}

      <ProductSheet
        product={selected}
        currency={s.currency}
        canOrder={s.isOpen}
        busy={isAdding}
        onClose={() => setSelected(null)}
        onAdd={async (p, qty, note) => { if (await addToCart(p, qty, note)) setSelected(null); }}
      />
      <CartBar storeId={s.id} />
    </>
  );
}
