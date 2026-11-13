import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ApiError } from '@click/api';
import { useAuth } from '../../auth/AuthProvider';
import { Button, Icon, Sheet, useConfirm, useToast } from '../../components/ui';
import { isStoreConflict, useCartActions } from '../cart/useCart';
import { compareStore, type CompareItem } from './compare';

interface Addable { id: string; name: string; hasVariants: boolean }

/**
 * Shopping cart actions on the one Click. cart. Prices, stock, variants and deals are all validated by the
 * server; this only gates sign-in, asks before replacing a food/grocery cart, and gives clear feedback.
 */
export function useShopActions() {
  const { status } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const confirm = useConfirm();
  const { add, clear } = useCartActions();
  const [added, setAdded] = useState<{ name: string; label?: string } | null>(null);

  async function addToCart(p: Addable, opts: { variantId?: string | null; variantLabel?: string; quantity?: number; quiet?: boolean } = {}) {
    if (status !== 'authenticated') {
      navigate(`/login?next=${encodeURIComponent(location.pathname + location.search)}`);
      return false;
    }
    if (p.hasVariants && !opts.variantId) {
      navigate(`/products/${p.id}`); // sizes/colours are chosen on the product page, never defaulted silently
      return false;
    }
    const input = { productId: p.id, quantity: opts.quantity ?? 1, variantId: opts.variantId ?? null };
    try {
      await add.mutateAsync(input);
    } catch (e) {
      if (!isStoreConflict(e)) {
        toast(e instanceof ApiError ? e.message : 'Couldn’t add this to your cart.', 'error');
        return false;
      }
      const ok = await confirm({
        title: 'Start a new cart?',
        message: `${(e as ApiError).message.replace(/ Clear it to add this (item|product)\.$/, '')} Shopping is checked out separately. Clear the cart and add ${p.name}?`,
        confirmLabel: 'Clear cart and add', cancelLabel: 'Keep my cart',
      });
      if (!ok) return false;
      try {
        await clear.mutateAsync();
        await add.mutateAsync(input);
      } catch (err) {
        toast(err instanceof ApiError ? err.message : 'Couldn’t add this to your cart.', 'error');
        return false;
      }
    }
    if (!opts.quiet) setAdded({ name: p.name, label: opts.variantLabel });
    return true;
  }

  async function buyNow(p: Addable, opts: { variantId?: string | null; quantity?: number } = {}) {
    if (await addToCart(p, { ...opts, quiet: true })) navigate('/checkout');
  }

  async function toggleCompare(item: CompareItem) {
    if (compareStore.has(item.id)) { compareStore.remove(item.id); return; }
    const r = compareStore.add(item);
    if (r === 'full') toast('You can compare up to 4 products at a time.', 'error');
    if (r === 'other_category') {
      const ok = await confirm({ title: 'Compare a different category?', message: 'Products are compared within one category. Start a new comparison with this product?',
        confirmLabel: 'Start new comparison', cancelLabel: 'Keep current' });
      if (ok) compareStore.replaceWith(item);
    }
  }

  const addedSheet = (
    <Sheet open={!!added} onClose={() => setAdded(null)} label="Added to cart">
      <div className="added">
        <div className="added__row">
          <span className="added__check"><Icon name="check" size={22} /></span>
          <div><strong>Added to cart</strong><div className="small muted">{added?.name}{added?.label ? ` · ${added.label}` : ''}</div></div>
        </div>
        <div className="row">
          <Link to="/cart" className="btn btn--primary" style={{ flex: 1 }} onClick={() => setAdded(null)}>View cart</Link>
          <Button variant="secondary" style={{ flex: 1 }} onClick={() => setAdded(null)}>Continue shopping</Button>
        </div>
      </div>
    </Sheet>
  );

  return { addToCart, buyNow, toggleCompare, addedSheet, isAdding: add.isPending || clear.isPending };
}
