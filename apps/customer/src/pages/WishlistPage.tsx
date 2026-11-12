import { Link } from 'react-router-dom';
import { EmptyState, ErrorState, Skeleton } from '../components/ui';
import { PackageCardView, ProviderCardView } from '../features/events/parts';
import { addDays, HotelImage, RatingBadge, SaveHotel, todayIso } from '../features/hotels/parts';
import { ProCardView } from '../features/pros/parts';
import { ProductCard } from '../features/stores/ProductCard';
import { StoreCard } from '../features/stores/StoreCard';
import { useWishlist } from '../features/wishlist/useWishlist';

export function WishlistPage() {
  const wishlist = useWishlist();
  if (wishlist.isError) return <ErrorState error={wishlist.error} onRetry={() => wishlist.refetch()} />;
  if (wishlist.isPending) return <div className="stack"><Skeleton height={28} width="30%" /><Skeleton height={200} /></div>;
  const stores = wishlist.data.filter((i) => i.store).map((i) => i.store!);
  const products = wishlist.data.filter((i) => i.product).map((i) => i.product!);
  const pros = wishlist.data.filter((i) => i.provider).map((i) => ({ ...i.provider!, favoriteId: i.id }));
  const evTeams = wishlist.data.filter((i) => i.eventProvider).map((i) => ({ ...i.eventProvider!, favoriteId: i.id }));
  const hotels = wishlist.data.filter((i) => i.hotel).map((i) => ({ ...i.hotel!, favoriteId: i.id }));
  const evPkgs = wishlist.data.filter((i) => i.eventPackage).map((i) => ({ ...i.eventPackage!, favoriteId: i.id }));

  return (
    <div className="stack">
      <h1>Wishlist</h1>
      {wishlist.data.length === 0 ? (
        <EmptyState icon="heart" title="Your wishlist is empty." message="Save things you love and find them here later." action={<Link to="/food" className="btn btn--primary">Discover places</Link>} />
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
          {pros.length > 0 && (
            <section className="stack sv-scope" data-theme="services">
              <h2>My Professionals</h2>
              <div className="sv-prolist">{pros.map((p) => <ProCardView key={p.id} p={p} wide />)}</div>
            </section>
          )}
          {hotels.length > 0 && (
            <section className="stack ht-scope" data-theme="hotels">
              <h2>Hotels</h2>
              <div className="ht-savedgrid">{hotels.map((h) => (
                <Link key={h.id} to={`/hotels/${h.id}?check_in=${addDays(todayIso(), 1)}&check_out=${addDays(todayIso(), 2)}`} className="ht-saved">
                  <HotelImage src={h.imageUrl} name={h.name} accent={h.accent} />
                  <span className="ht-saved__body"><span className="ht-kicker">{h.typeLabel} · {h.destination}</span><strong>{h.name}</strong><RatingBadge r={h.rating} /></span>
                  <SaveHotel id={h.id} favoriteId={h.favoriteId} name={h.name} />
                </Link>
              ))}</div>
            </section>
          )}
          {evTeams.length + evPkgs.length > 0 && (
            <section className="stack ev-scope" data-theme="events">
              <h2>Event teams, venues & packages</h2>
              <div className="ev-grid">{evTeams.map((p) => <ProviderCardView key={p.id} p={p} />)}
                {evPkgs.map((x) => <PackageCardView key={x.id} pkg={x} showProvider action={<Link to={`/events/book?package=${x.id}`} className="ev-btn ev-btn--sm">Book</Link>} />)}</div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
