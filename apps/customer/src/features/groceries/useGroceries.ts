import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useLocation, useNavigate } from 'react-router-dom';
import { ApiError, type Cart, type GroceryAt, type GroceryListing } from '@click/api';
import { useAuth } from '../../auth/AuthProvider';
import { useConfirm, useToast } from '../../components/ui';
import { api } from '../../lib/api';
import { useDeliveryLocation } from '../../location/LocationProvider';
import { cartKey, isStoreConflict, useCart } from '../cart/useCart';

export const groceryKey = ['groceries'] as const;
export const basketKey = ['customer', 'groceries', 'basket'] as const;

/** The delivery location for grocery queries: the selected saved address (server checks ownership). */
export function useGroceryAt(): { at: GroceryAt | undefined; key: string } {
  const { selected } = useDeliveryLocation();
  return selected ? { at: { address: selected.id }, key: selected.id } : { at: undefined, key: 'none' };
}

/** Cart lines by grocery listing id (the shared Click. cart, basket mode). */
export function useBasketLines() {
  const { data: cart } = useCart();
  const lines = new Map<string, Cart['items'][number]>();
  if (cart?.mode === 'basket') for (const i of cart.items) lines.set(i.product.id, i);
  return { cart, lines };
}

/**
 * Add / change / remove grocery items. Signed-out customers go to login; a cart holding food or shopping items is
 * never cleared silently (the customer confirms); every price comes back from the server.
 */
export function useBasketActions() {
  const { status } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const { lines } = useBasketLines();
  const sync = (cart: Cart) => {
    qc.setQueryData(cartKey, cart);
    qc.invalidateQueries({ queryKey: basketKey });
  };
  const add = useMutation({ mutationFn: api.customer.cart.addItem, onSuccess: sync });
  const update = useMutation({ mutationFn: ({ id, quantity }: { id: string; quantity: number }) => api.customer.cart.updateItem(id, { quantity }), onSuccess: sync });
  const remove = useMutation({ mutationFn: api.customer.cart.removeItem, onSuccess: sync });
  const clear = useMutation({ mutationFn: api.customer.cart.clear, onSuccess: sync });
  const fail = (e: unknown) => toast(e instanceof ApiError ? e.message : 'Couldn’t update your basket. Check your connection and try again.', 'error');

  async function addListing(l: GroceryListing, quantity = 1): Promise<boolean> {
    if (status !== 'authenticated') {
      navigate(`/login?next=${encodeURIComponent(location.pathname + location.search)}`);
      return false;
    }
    const input = { productId: l.id, quantity, note: '', optionIds: [] };
    try {
      await add.mutateAsync(input);
      return true;
    } catch (e) {
      if (!isStoreConflict(e)) { fail(e); return false; }
      const ok = await confirm({
        title: 'Start a grocery basket?',
        message: `${e instanceof ApiError ? e.message.replace(/ Clear it to add this (item|product)\.$/, '') : 'Your cart has other items.'} Food, Shopping and Groceries are checked out separately. Clear the cart and add ${l.name}?`,
        confirmLabel: 'Clear cart and add', cancelLabel: 'Keep my cart',
      });
      if (!ok) return false;
      try {
        await clear.mutateAsync();
        await add.mutateAsync(input);
        return true;
      } catch (err) { fail(err); return false; }
    }
  }

  function setQuantity(listingId: string, next: number) {
    const line = lines.get(listingId);
    if (!line) return;
    if (next <= 0) remove.mutate(line.id, { onError: fail });
    else update.mutate({ id: line.id, quantity: next }, { onError: fail });
  }

  const busy = add.isPending || update.isPending || remove.isPending || clear.isPending;
  return { addListing, setQuantity, busy, lines };
}

export function useGroceryBasket(addressId: string | null) {
  const { status } = useAuth();
  return useQuery({ queryKey: [...basketKey, addressId], queryFn: () => api.groceries.basket(addressId), enabled: status === 'authenticated' });
}

const RECENT_KEY = 'click.groceryRecentSearches';
/** Signed-out search history stays on this device only; signed-in history comes from the server. */
export function localRecent(): string[] {
  try { return JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]') as string[]; } catch { return []; }
}
export function rememberLocal(q: string) {
  try {
    const next = [q, ...localRecent().filter((x) => x.toLowerCase() !== q.toLowerCase())].slice(0, 6);
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch { /* storage unavailable */ }
}
