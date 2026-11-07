import { useState } from 'react';
import type { Product } from '@click/api';
import { Button, DietMark, Icon, QuantityStepper, Sheet, SmartImage, TextArea } from '../../components/ui';
import { formatMoney } from '../../lib/format';

export function ProductSheet({ product, currency, canOrder, busy, onClose, onAdd }: {
  product: Product | null;
  currency: string;
  canOrder: boolean;
  busy: boolean;
  onClose: () => void;
  onAdd: (product: Product, quantity: number, note: string) => void;
}) {
  return (
    <Sheet open={!!product} onClose={onClose} label={product?.name ?? 'Item'}>
      {product && <Body key={product.id} {...{ product, currency, canOrder, busy, onClose, onAdd }} />}
    </Sheet>
  );
}

function Body({ product, currency, canOrder, busy, onClose, onAdd }: {
  product: Product; currency: string; canOrder: boolean; busy: boolean; onClose: () => void;
  onAdd: (product: Product, quantity: number, note: string) => void;
}) {
  const [qty, setQty] = useState(1);
  const [note, setNote] = useState('');
  const total = (Number(product.price) * qty).toFixed(2);
  return (
    <>
      <div style={{ position: 'relative' }}>
        <SmartImage src={product.imageUrl} alt={product.name} className="thumb" />
        <button className="icon-btn" onClick={onClose} aria-label="Close" style={{ position: 'absolute', top: 8, right: 8, background: '#fff' }}>
          <Icon name="close" />
        </button>
      </div>
      <div className="stack" style={{ padding: 'var(--s-5)' }}>
        <div className="stack" style={{ gap: 6 }}>
          <div className="row"><DietMark dietary={product.dietary} />{product.isFeatured && <span className="badge badge--brand">Popular</span>}</div>
          <h2>{product.name}</h2>
          <strong>{formatMoney(product.price, currency)}</strong>
          {product.description && <p className="muted">{product.description}</p>}
        </div>
        <TextArea label="Note for the kitchen (optional)" maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. less spicy" />
        <div className="spread">
          <QuantityStepper value={qty} onChange={(n) => setQty(Math.max(1, n))} label={product.name} />
          <Button onClick={() => onAdd(product, qty, note)} loading={busy} disabled={!canOrder} style={{ flex: 1 }}>
            {canOrder ? `Add item · ${formatMoney(total, currency)}` : 'Store is closed'}
          </Button>
        </div>
      </div>
    </>
  );
}
