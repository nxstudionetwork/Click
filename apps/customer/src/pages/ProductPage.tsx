import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ApiError } from '@click/api';
import { Button, DietMark, EmptyState, ErrorState, Icon, PriceTag, QuantityStepper, Skeleton, SmartImage } from '../components/ui';
import { serviceForStoreType } from '../config/services';
import { useThemeOverride } from '../components/layout/AppShell';
import { OptionPicker, useOptionSelection } from '../features/menu/OptionPicker';
import { useAddToCart } from '../features/menu/useAddToCart';
import { ProductCard } from '../features/stores/ProductCard';
import { WishlistButton } from '../features/wishlist/WishlistButton';
import { api } from '../lib/api';
import { etaLabel, formatMoney } from '../lib/format';

const useProductQuery = (id: string) => useQuery({ queryKey: ['products', id], queryFn: () => api.catalog.product(id) });

export function ProductPage() {
  const { id = '' } = useParams();
  const product = useProductQuery(id);
  useThemeOverride(product.data ? serviceForStoreType(product.data.store.storeType).theme : null);
  const { addToCart, isAdding } = useAddToCart();
  const [qty, setQty] = useState(1);
  const [added, setAdded] = useState(false);

  if (product.isError) {
    return product.error instanceof ApiError && product.error.status === 404
      ? <EmptyState icon="alert" title="Product not found" message="It may no longer be sold on Click." action={<Link to="/explore" className="btn btn--outline">Explore</Link>} />
      : <ErrorState error={product.error} onRetry={() => product.refetch()} />;
  }
  if (product.isPending) return <div className="pdp"><Skeleton height={360} radius={22} /><div className="stack"><Skeleton height={32} width="70%" /><Skeleton height={20} width="40%" /><Skeleton height={80} /></div></div>;

  return <ProductDetail p={product.data} addToCart={addToCart} isAdding={isAdding} qty={qty} setQty={setQty} added={added} setAdded={setAdded} />;
}

function ProductDetail({ p, addToCart, isAdding, qty, setQty, added, setAdded }: {
  p: NonNullable<ReturnType<typeof useProductQuery>['data']>; addToCart: ReturnType<typeof useAddToCart>['addToCart']; isAdding: boolean;
  qty: number; setQty: (n: number) => void; added: boolean; setAdded: (v: boolean) => void;
}) {
  const store = p.store;
  const canOrder = store.isOpen && p.isAvailable;
  const selection = useOptionSelection(p);

  return (
    <div className="stack">
      <Link to={`/stores/${store.slug}`} className="btn btn--ghost btn--sm" style={{ alignSelf: 'flex-start', paddingLeft: 4 }}><Icon name="back" size={18} /> {store.name}</Link>
      <div className="pdp">
        <SmartImage src={p.imageUrl} alt={p.name} className="pdp__media">
          <WishlistButton target={{ productId: p.id }} name={p.name} />
        </SmartImage>
        <div className="stack">
          <div className="stack" style={{ gap: 6 }}>
            {p.brand && <span className="muted">{p.brand}</span>}
            <div className="row"><DietMark dietary={p.dietary} /><h1>{p.name}</h1></div>
            {p.unitLabel && <span className="muted">{p.unitLabel}</span>}
            <PriceTag price={p.price} compareAt={p.compareAtPrice} discountPercent={p.discountPercent} currency={store.currency} />
            <span className="small muted">Inclusive of item price; taxes and delivery are shown at checkout.</span>
          </div>
          <div className="row" style={{ flexWrap: 'wrap' }}>
            {!p.isAvailable ? <span className="badge badge--warning">Out of stock</span>
              : p.lowStock ? <span className="badge badge--warning">Only a few left</span>
              : <span className="badge badge--accent">In stock</span>}
            {!store.isOpen && <span className="badge badge--danger">Store closed right now</span>}
            {p.categoryName && <span className="badge">{p.categoryName}</span>}
          </div>
          {p.description && <p>{p.description}</p>}
          <OptionPicker product={p} currency={store.currency} selection={selection} />
          {canOrder && (
            <div className="row">
              <QuantityStepper value={qty} onChange={(n) => setQty(Math.max(1, n))} label={p.name} />
              <Button loading={isAdding} disabled={selection.missing.length > 0} style={{ flex: 1 }} onClick={async () => { if (await addToCart(p, qty, '', selection.optionIds)) setAdded(true); }}>
                Add to cart · {formatMoney((selection.unitPrice * qty).toFixed(2), store.currency)}
              </Button>
            </div>
          )}
          {added && <p className="badge badge--accent" role="status" style={{ alignSelf: 'flex-start' }}>Added to cart · <Link to="/cart" style={{ textDecoration: 'underline' }}>View cart</Link></p>}
          <Link to={`/stores/${store.slug}`} className="card card--pad row">
            <SmartImage src={store.imageUrl} alt={store.name} className="thumb" />
            <div><strong>{store.name}</strong><div className="small muted">{serviceForStoreType(store.storeType).name} · {etaLabel(store.deliveryTimeMin, store.deliveryTimeMax)}</div></div>
          </Link>
        </div>
      </div>
      {p.related.length > 0 && (
        <section className="section">
          <h2>More from {store.name}</h2>
          <div className="product-grid">{p.related.map((r) => <ProductCard key={r.id} product={r} currency={store.currency} />)}</div>
        </section>
      )}
    </div>
  );
}
