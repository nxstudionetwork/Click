import { Link } from 'react-router-dom';
import type { OfferWithStore } from '@click/api';
import { Icon, SmartImage } from '../../components/ui';
import { formatDateTime } from '../../lib/format';
import { serviceForStoreType } from '../../config/services';

export function OfferCard({ offer }: { offer: OfferWithStore }) {
  return (
    <Link to={`/stores/${offer.store.slug}`} className={`offer-card ${offer.store.isOpen ? '' : 'offer-card--closed'}`}>
      <SmartImage src={offer.store.imageUrl} alt={offer.store.name} className="offer-card__media" />
      <div className="offer-card__body">
        <span className="offer-card__title"><Icon name="tag" size={16} /> {offer.title}</span>
        {offer.description && <span className="small muted">{offer.description}</span>}
        <span className="small">{offer.store.name} · {serviceForStoreType(offer.store.storeType).name}</span>
        <span className="small muted">
          {!offer.store.isOpen ? 'Store closed right now' : offer.endsAt ? `Ends ${formatDateTime(offer.endsAt)}` : 'Ongoing'}
        </span>
      </div>
    </Link>
  );
}
