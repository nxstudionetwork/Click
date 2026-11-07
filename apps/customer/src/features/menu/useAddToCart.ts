import type { Product } from '@click/api';
import { ApiError } from '@click/api';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthProvider';
import { useToast } from '../../components/ui';
import { usingMockData } from '../../data/stores-source';
import { isStoreConflict, useCartActions } from '../cart/useCart';

/** Shared add-to-cart flow: auth gate, single-store conflict, error feedback. */
export function useAddToCart() {
  const { status } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const { add, clear } = useCartActions();

  async function addToCart(product: Product, quantity = 1, note = ''): Promise<boolean> {
    if (usingMockData) {
      toast('Cart needs the real API. Mock data is for UI review only.', 'error');
      return false;
    }
    if (status !== 'authenticated') {
      navigate(`/login?next=${encodeURIComponent(location.pathname)}`);
      return false;
    }
    const input = { productId: product.id, quantity, note };
    try {
      await add.mutateAsync(input);
      return true;
    } catch (e) {
      if (isStoreConflict(e) && window.confirm('Your cart has items from another store. Start a new cart?')) {
        await clear.mutateAsync();
        await add.mutateAsync(input);
        return true;
      }
      if (!isStoreConflict(e)) toast(e instanceof ApiError ? e.message : 'Could not add item.', 'error');
      return false;
    }
  }

  return { addToCart, isAdding: add.isPending || clear.isPending };
}
