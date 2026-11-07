import { Link } from 'react-router-dom';
import { formatMoney } from '../../lib/format';
import { useCart } from './useCart';

/** Floating summary shown on a store page when the cart has items from that store. */
export function CartBar({ storeId }: { storeId: string }) {
  const { data: cart } = useCart();
  if (!cart || cart.itemCount === 0 || cart.store?.id !== storeId) return null;
  return (
    <>
    {/* Spacer so the floating bar never covers the last menu item. */}
    <div aria-hidden="true" style={{ height: 80 }} />
    <div className="cart-bar">
      <Link to="/cart">
        <span>{cart.itemCount} item{cart.itemCount > 1 ? 's' : ''} · {formatMoney(cart.totals.subtotal, cart.store.currency)}</span>
        <span>View cart →</span>
      </Link>
    </div>
    </>
  );
}
