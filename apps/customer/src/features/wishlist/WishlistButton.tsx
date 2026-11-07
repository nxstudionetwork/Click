import { Icon } from '../../components/ui';
import { usingMockData } from '../../data/stores-source';
import { useWishlistToggle } from './useWishlist';

export function WishlistButton({ target, name, className = '' }: { target: { storeId: string } | { productId: string }; name: string; className?: string }) {
  const { saved, busy, toggle } = useWishlistToggle(target);
  if (usingMockData) return null; // mock IDs don't exist on the server
  return (
    <button
      type="button"
      className={`wish-btn ${saved ? 'wish-btn--on' : ''} ${className}`}
      aria-pressed={saved}
      aria-label={saved ? `Remove ${name} from wishlist` : `Save ${name} to wishlist`}
      disabled={busy}
      onClick={(e) => { e.preventDefault(); e.stopPropagation(); toggle(); }}
    >
      <Icon name="heart" size={20} />
    </button>
  );
}
