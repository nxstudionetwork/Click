import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthProvider';
import { useToast } from '../../components/ui';
import { api } from '../../lib/api';

export const wishlistKey = ['customer', 'wishlist'] as const;

export function useWishlist() {
  const { status } = useAuth();
  return useQuery({ queryKey: wishlistKey, queryFn: api.customer.wishlist.list, enabled: status === 'authenticated' });
}

/** Toggle a store or product in the signed-in customer's wishlist. */
export function useWishlistToggle(target: { storeId: string } | { productId: string }) {
  const { status } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const qc = useQueryClient();
  const { data } = useWishlist();
  const saved = data?.find((i) => ('storeId' in target ? i.store?.id === target.storeId : i.product?.id === target.productId));
  const onError = (e: unknown) => toast(e instanceof Error ? e.message : 'Could not update wishlist.', 'error');
  const invalidate = () => qc.invalidateQueries({ queryKey: wishlistKey });
  const add = useMutation({ mutationFn: () => api.customer.wishlist.add(target), onSuccess: invalidate, onError });
  const remove = useMutation({ mutationFn: (id: string) => api.customer.wishlist.remove(id), onSuccess: invalidate, onError });

  return {
    saved: !!saved,
    busy: add.isPending || remove.isPending,
    toggle: () => {
      if (status !== 'authenticated') return navigate(`/login?next=${encodeURIComponent(location.pathname)}`);
      if (saved) remove.mutate(saved.id);
      else add.mutate();
    },
  };
}
