import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type Cart } from '@click/api';
import { useAuth } from '../../auth/AuthProvider';
import { api } from '../../lib/api';

export const cartKey = ['customer', 'cart'] as const;

export function useCart() {
  const { status } = useAuth();
  return useQuery({ queryKey: cartKey, queryFn: api.customer.cart.get, enabled: status === 'authenticated' });
}

/** All cart mutations return the full server cart, which replaces the cache. */
export function useCartActions() {
  const qc = useQueryClient();
  const onSuccess = (cart: Cart) => qc.setQueryData(cartKey, cart);
  return {
    add: useMutation({ mutationFn: api.customer.cart.addItem, onSuccess }),
    update: useMutation({
      mutationFn: ({ id, quantity }: { id: string; quantity: number }) => api.customer.cart.updateItem(id, { quantity }),
      onSuccess,
    }),
    remove: useMutation({ mutationFn: api.customer.cart.removeItem, onSuccess }),
    clear: useMutation({ mutationFn: api.customer.cart.clear, onSuccess }),
  };
}

export const isStoreConflict = (e: unknown) => e instanceof ApiError && e.code === 'cart_store_conflict';
