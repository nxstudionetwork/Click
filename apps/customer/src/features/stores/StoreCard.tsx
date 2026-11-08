import type { Store } from '@click/api';
import { Link } from 'react-router-dom';
import { etaLabel, formatMoney, priceLevelLabel } from '../../lib/format';
import { Rating, Skeleton, SmartImage } from '../../components/ui';

export function StoreCard({ store }: { store: Store }) {
  const offer = store.offers[0];
  return (
    <Link to={`/stores/${store.slug}`} className={`store-card ${store.isOpen ? '' : 'store-card--closed'}`}>
      <SmartImage src={store.imageUrl} alt={store.name} className="store-card__media">
        {offer && store.isOpen && (
          <div className="store-card__offer"><span className="badge">{offer.title}</span></div>
        )}
        {!store.isOpen && <div className="store-card__closed"><span className="badge badge--danger">Currently closed</span></div>}
      </SmartImage>
      <div className="store-card__body">
        <div className="store-card__title">
          <h3>{store.name}</h3>
          <Rating value={store.ratingAverage} />
        </div>
        <div className="store-card__meta">
          {store.distanceKm != null && <span className="store-card__dist">{store.distanceKm < 1 ? `${Math.round(store.distanceKm * 1000)} m` : `${store.distanceKm.toFixed(1)} km`}</span>}
          <span className={store.distanceKm != null ? 'dot-sep' : undefined}>{etaLabel(store.deliveryTimeMin, store.deliveryTimeMax)}</span>
          <span className="dot-sep">{Number(store.deliveryFee) ? `${formatMoney(store.deliveryFee, store.currency)} delivery` : 'Free delivery'}</span>
          <span className="dot-sep">{priceLevelLabel(store.priceLevel)}</span>
        </div>
        <span className="muted small">{store.categories.map((c) => c.name).join(', ')}</span>
      </div>
    </Link>
  );
}

export function StoreCardSkeleton() {
  return (
    <div className="store-card" aria-hidden="true">
      <div className="skeleton" style={{ aspectRatio: '16 / 10', borderRadius: 16 }} />
      <Skeleton width="70%" height={18} />
      <Skeleton width="50%" height={14} />
    </div>
  );
}
