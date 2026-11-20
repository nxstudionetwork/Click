import { Link } from 'react-router-dom';
import type { StoreType } from '@click/api';
import { Icon, type IconName } from '../../components/ui';
import type { Theme } from '../../config/services';

export const CART_SERVICES: { type: StoreType; label: string; icon: IconName; theme: Theme; browse: string; cta: string }[] = [
  { type: 'restaurant', label: 'Food', icon: 'food', theme: 'food', browse: '/food', cta: 'Order food' },
  { type: 'grocery', label: 'Groceries', icon: 'grocery', theme: 'grocery', browse: '/groceries', cta: 'Shop groceries' },
  { type: 'retail', label: 'Shop', icon: 'shop', theme: 'shopping', browse: '/shopping', cta: 'Browse Shop' },
  { type: 'pharmacy', label: 'Pharma', icon: 'plus', theme: 'pharma', browse: '/pharma', cta: 'Find medicines' },
];

/**
 * One row of service tabs at the top of the cart. Click. keeps one cart at a time; the tab of the service in the cart
 * shows its item count, the others say they're empty. Grocery baskets open their own basket page.
 */
export function CartTabs({ active, current, count, onPick }: { active: StoreType; current: StoreType | null; count: number; onPick: (t: StoreType) => void }) {
  return (
    <nav className="cart-tabs" aria-label="Carts by service">
      {CART_SERVICES.map((s) => {
        const mine = current === s.type;
        const body = <>
          <span className="cart-tabs__icon"><Icon name={s.icon} size={18} /></span>
          <span className="cart-tabs__label">{s.label}</span>
          {mine && count > 0 && <span className="cart-tabs__count" aria-label={`${count} items`}>{count}</span>}
        </>;
        return s.type === 'grocery' && mine
          ? <Link key={s.type} to="/groceries/basket" className="cart-tabs__tab" data-theme={s.theme}>{body}</Link>
          : <button key={s.type} type="button" className="cart-tabs__tab" data-theme={s.theme} aria-pressed={active === s.type} onClick={() => onPick(s.type)}>{body}</button>;
      })}
    </nav>
  );
}
