import { Link } from 'react-router-dom';
import { EmptyState, ErrorState, Skeleton } from '../components/ui';
import { ProductCard } from '../features/stores/ProductCard';
import { StoreCard } from '../features/stores/StoreCard';
import { useWishlist } from '../features/wishlist/useWishlist';

export function WishlistPage() {
  const wishlist = useWishlist();
  if (wishlist.isError) return <ErrorState error={wishlist.error} onRetry={() => wishlist.refetch()} />;
  if (wishlist.isPending) return <div className="stack"><Skeleton height={28} width="30%" /><Skeleton height={200} /></div>;
  const stores = wishlist.data.filter((i) => i.store).map((i) => i.store!);
  const products = wishlist.data.filter((i) => i.product).map((i) => i.product!);

  return (
    <div className="stack">
      <h1>Wishlist</h1>
      {wishlist.data.length === 0 ? (
        <EmptyState icon="heart" title="Nothing saved yet" message="Tap the heart on a store or product to save it here." action={<Link to="/explore" className="btn btn--primary">Explore</Link>} />
      ) : (
        <>
          {stores.length > 0 && (
            <section className="stack">
              <h2>Stores & restaurants</h2>
              <div className="store-grid">{stores.map((s) => <StoreCard key={s.id} store={s} />)}</div>
            </section>
          )}
          {products.length > 0 && (
            <section className="stack">
              <h2>Products</h2>
              <div className="product-grid">{products.map((p) => <ProductCard key={p.id} product={p} currency={p.store.currency} showStore />)}</div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
