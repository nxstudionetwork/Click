import type { CartTotals } from '@click/api';
import { formatMoney } from '../../lib/format';

export function Totals({ totals, currency, discount }: { totals: CartTotals; currency: string; discount?: string }) {
  return (
    <div className="totals">
      <div><span>Item total</span><span>{formatMoney(totals.subtotal, currency)}</span></div>
      <div><span>Delivery fee</span><span>{Number(totals.deliveryFee) ? formatMoney(totals.deliveryFee, currency) : 'Free'}</span></div>
      <div><span>Taxes</span><span>{formatMoney(totals.tax, currency)}</span></div>
      {discount && Number(discount) > 0 && <div><span>Discount</span><span>−{formatMoney(discount, currency)}</span></div>}
      <div className="totals__grand"><span>To pay</span><span>{formatMoney(totals.total, currency)}</span></div>
    </div>
  );
}
