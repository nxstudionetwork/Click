import { formatMoney } from '../../lib/format';

export function PriceTag({ price, compareAt, discountPercent, currency }: { price: string; compareAt?: string | null; discountPercent?: number | null; currency: string }) {
  return (
    <span className="price">
      <strong>{formatMoney(price, currency)}</strong>
      {compareAt && <s className="muted small">{formatMoney(compareAt, currency)}</s>}
      {discountPercent ? <span className="price__off">{discountPercent}% off</span> : null}
    </span>
  );
}
