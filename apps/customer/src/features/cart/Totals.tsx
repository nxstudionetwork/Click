import type { CartTotals } from '@click/api';
import { formatMoney } from '../../lib/format';

/** Bill breakdown. Every figure comes from the server; the client never computes prices. */
export function Totals({ totals, currency, offerTitle }: { totals: CartTotals; currency: string; offerTitle?: string }) {
  const discount = Number(totals.discount);
  return (
    <div className="totals">
      <div><span>Item total</span><span>{formatMoney(totals.subtotal, currency)}</span></div>
      <div><span>Delivery fee</span><span>{Number(totals.deliveryFee) ? formatMoney(totals.deliveryFee, currency) : 'Free'}</span></div>
      <div><span>Taxes</span><span>{formatMoney(totals.tax, currency)}</span></div>
      {discount > 0 && <div className="totals__saving"><span>{offerTitle ? `Offer · ${offerTitle}` : 'Discount'}</span><span>−{formatMoney(totals.discount, currency)}</span></div>}
      <div className="totals__grand"><span>To pay</span><span>{formatMoney(totals.total, currency)}</span></div>
    </div>
  );
}
