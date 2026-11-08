import type { Product } from '@click/api';
import { ApiError } from '@click/api';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthProvider';
import { useConfirm, useToast } from '../../components/ui';
import { usingMockData } from '../../data/stores-source';
import { isStoreConflict, useCartActions } from '../cart/useCart';
import { needsChoices } from './OptionPicker';

/**
 * Shared add-to-cart flow: sign-in gate, required customisation, single-store conflict (asked in a Click.
 * dialog, never silently cleared) and error feedback. Prices are always computed by the server.
 */
export function useAddToCart() {
  const { status } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const confirm = useConfirm();
  const { add, clear } = useCartActions();

  async function addToCart(product: Product, quantity = 1, note = '', optionIds?: string[]): Promise<boolean> {
    if (usingMockData) {
      toast('Cart needs the real API. Mock data is for UI review only.', 'error');
      return false;
    }
    if (status !== 'authenticated') {
      navigate(`/login?next=${encodeURIComponent(location.pathname)}`);
      return false;
    }
    // Items with required choices (size, portion…) are added from their picker, never with silent defaults.
    if (optionIds === undefined && needsChoices(product)) {
      navigate(`/products/${product.id}`);
      return false;
    }
    const input = { productId: product.id, quantity, note, optionIds: optionIds ?? [] };
    try {
      await add.mutateAsync(input);
      toast(`Added ${product.name}`);
      return true;
    } catch (e) {
      if (isStoreConflict(e)) {
        const ok = await confirm({
          title: 'Start a new cart?',
          message: 'Your cart contains items from another restaurant. Clear the cart and add this item?',
          confirmLabel: 'Clear cart and add',
          cancelLabel: 'Keep my cart',
        });
        if (!ok) return false;
        try {
          await clear.mutateAsync();
          await add.mutateAsync(input);
          toast(`Added ${product.name}`);
          return true;
        } catch (err) {
          toast(err instanceof ApiError ? err.message : 'Could not add item.', 'error');
          return false;
        }
      }
      toast(e instanceof ApiError ? e.message : 'Could not add item.', 'error');
      return false;
    }
  }

  return { addToCart, isAdding: add.isPending || clear.isPending };
}
