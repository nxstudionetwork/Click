import type { Product } from '@click/api';
import { Button, DietMark, QuantityStepper, SmartImage } from '../../components/ui';
import { formatMoney } from '../../lib/format';

export interface ProductRowProps {
  product: Product;
  currency: string;
  quantity: number;
  canOrder: boolean;
  busy: boolean;
  onOpen: () => void;
  onAdd: () => void;
  onChangeQuantity: (next: number) => void;
}

export function ProductRow({ product, currency, quantity, canOrder, busy, onOpen, onAdd, onChangeQuantity }: ProductRowProps) {
  const orderable = canOrder && product.isAvailable;
  return (
    <article
      className={`product ${product.isAvailable ? '' : 'product--unavailable'}`}
      onClick={product.isAvailable ? onOpen : undefined}
      aria-label={product.name}
    >
      <div className="product__body">
        <div className="row">
          <DietMark dietary={product.dietary} />
          {product.isFeatured && <span className="badge badge--brand">Popular</span>}
        </div>
        <h3 style={{ fontSize: 'var(--fs-md)' }}>{product.name}</h3>
        <strong>{formatMoney(product.price, currency)}</strong>
        {product.description && <p>{product.description}</p>}
        {!product.isAvailable && <span className="badge badge--warning" style={{ alignSelf: 'flex-start' }}>Sold out</span>}
      </div>
      <div className="product__media">
        <SmartImage src={product.imageUrl} alt={product.name} />
        {orderable && (
          <div className="product__action" onClick={(e) => e.stopPropagation()}>
            {quantity > 0 ? (
              <QuantityStepper value={quantity} onChange={onChangeQuantity} busy={busy} label={product.name} />
            ) : (
              <Button size="sm" onClick={onAdd} disabled={busy} aria-label={`Add ${product.name}`}>ADD</Button>
            )}
          </div>
        )}
      </div>
    </article>
  );
}
