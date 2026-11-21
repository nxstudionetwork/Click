import { useState } from 'react';
import type { Product } from '@click/api';
import { Button, DietMark, Icon, QuantityStepper, Sheet, SmartImage, TextArea } from '../../components/ui';
import { formatMoney } from '../../lib/format';
import { OptionPicker, useOptionSelection } from './OptionPicker';

export function ProductSheet({ product, currency, canOrder, busy, onClose, onAdd }: {
  product: Product | null;
  currency: string;
  canOrder: boolean;
  busy: boolean;
  onClose: () => void;
  onAdd: (product: Product, quantity: number, note: string, optionIds: string[]) => void;
}) {
  return (
    <Sheet open={!!product} onClose={onClose} label={product?.name ?? 'Item'}>
      {product && <Body key={product.id} {...{ product, currency, canOrder, busy, onClose, onAdd }} />}
    </Sheet>
  );
}

function Body({ product, currency, canOrder, busy, onClose, onAdd }: {
  product: Product; currency: string; canOrder: boolean; busy: boolean; onClose: () => void;
  onAdd: (product: Product, quantity: number, note: string, optionIds: string[]) => void;
}) {
  const [qty, setQty] = useState(1);
  const [note, setNote] = useState('');
  const selection = useOptionSelection(product);
  const total = (selection.unitPrice * qty).toFixed(2);
  const orderable = canOrder && product.isAvailable;
  return (
    <>
      <div style={{ position: 'relative' }}>
        <SmartImage src={product.imageUrl} alt={product.name} className="thumb" />
        <button className="icon-btn icon-btn--glass" onClick={onClose} aria-label="Close" style={{ position: 'absolute', top: 8, right: 8 }}>
          <Icon name="close" />
        </button>
      </div>
      <div className="stack" style={{ padding: 'var(--s-5)' }}>
        <div className="stack" style={{ gap: 6 }}>
          <div className="row"><DietMark dietary={product.dietary} />{product.isFeatured && <span className="badge badge--brand">Popular</span>}</div>
          <h2>{product.name}</h2>
          <strong>{formatMoney(product.price, currency)}{product.optionGroups.length > 0 && <span className="muted small"> base price</span>}</strong>
          {product.description && <p className="muted">{product.description}</p>}
        </div>
        <OptionPicker product={product} currency={currency} selection={selection} />
        <TextArea label="Note for the kitchen (optional)" maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. less spicy" />
        {selection.missing.length > 0 && <p className="small" role="status" style={{ color: 'var(--c-theme-strong)' }}>Choose {selection.missing.join(' and ').toLowerCase()} to continue.</p>}
        <div className="spread">
          <QuantityStepper value={qty} onChange={(n) => setQty(Math.max(1, n))} label={product.name} />
          <Button onClick={() => onAdd(product, qty, note, selection.optionIds)} loading={busy} disabled={!orderable || selection.missing.length > 0} style={{ flex: 1 }}>
            {!product.isAvailable ? 'Sold out' : !canOrder ? 'Store is closed' : `Add item · ${formatMoney(total, currency)}`}
          </Button>
        </div>
      </div>
    </>
  );
}
