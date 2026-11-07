import { Link } from 'react-router-dom';
import type { Product, ProductWithStore } from '@click/api';
import { Button, PriceTag, QuantityStepper, SmartImage } from '../../components/ui';
import { WishlistButton } from '../wishlist/WishlistButton';

/** Grid card for grocery/retail products (restaurants use the menu row layout). */
export function ProductCard({ product, currency, quantity = 0, canOrder, busy, onAdd, onChangeQuantity, showStore }: {
  product: Product | ProductWithStore;
  currency: string;
  quantity?: number;
  canOrder?: boolean;
  busy?: boolean;
  onAdd?: () => void;
  onChangeQuantity?: (n: number) => void;
  showStore?: boolean;
}) {
  const store = 'store' in product ? product.store : null;
  const orderable = canOrder && product.isAvailable && onAdd;
  return (
    <article className={`product-card ${product.isAvailable ? '' : 'product-card--off'}`}>
      <Link to={`/products/${product.id}`} className="product-card__link" aria-label={product.name}>
        <SmartImage src={product.imageUrl} alt={product.name} className="product-card__media">
          {product.discountPercent ? <span className="product-card__deal badge">{product.discountPercent}% off</span> : null}
        </SmartImage>
      </Link>
      <WishlistButton target={{ productId: product.id }} name={product.name} className="product-card__wish" />
      <div className="product-card__body">
        {product.brand && <span className="muted small">{product.brand}</span>}
        <Link to={`/products/${product.id}`} className="product-card__name">{product.name}</Link>
        {product.unitLabel && <span className="muted small">{product.unitLabel}</span>}
        {showStore && store && <span className="muted small">from {store.name}</span>}
        <div className="spread" style={{ marginTop: 'auto', paddingTop: 6 }}>
          <PriceTag price={product.price} compareAt={product.compareAtPrice} currency={currency} />
          {!product.isAvailable ? (
            <span className="badge badge--warning">Out of stock</span>
          ) : orderable ? (
            quantity > 0 && onChangeQuantity ? (
              <QuantityStepper value={quantity} onChange={onChangeQuantity} busy={busy} label={product.name} />
            ) : (
              <Button size="sm" variant="secondary" onClick={onAdd} disabled={busy} aria-label={`Add ${product.name}`}>Add</Button>
            )
          ) : null}
        </div>
        {product.lowStock && product.isAvailable && <span className="badge badge--warning" style={{ alignSelf: 'flex-start' }}>Only a few left</span>}
      </div>
    </article>
  );
}
