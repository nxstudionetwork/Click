import { Link } from 'react-router-dom';
import type { ShopBadge, ShopCard as Card } from '@click/api';
import { Icon } from '../../components/ui';
import { formatMoney } from '../../lib/format';
import { WishlistButton } from '../wishlist/WishlistButton';
import { useCompare } from './compare';
import { ShopImage } from './ShopImage';
import { timeLeft, useNow } from './time';

export const BADGE_LABEL: Record<ShopBadge, string> = {
  best_seller: 'Best Seller', trending: 'Trending', new: 'New', top_rated: 'Top Rated', limited_deal: 'Limited Deal',
};

export function Price({ p, size = 'card' }: { p: Pick<Card, 'price' | 'referencePrice' | 'discountPercent' | 'fromPrice'>; size?: 'card' | 'page' }) {
  const c = size === 'page' ? 'spdp' : 'pcard';
  return (
    <div className={`${c}__price`}>
      <span className={`${c}__now`}>{p.fromPrice && <span className="pcard__from">from</span>}{formatMoney(p.price)}</span>
      {p.referencePrice && <span className={`${c}__ref`} aria-label={`was ${formatMoney(p.referencePrice)}`}>{formatMoney(p.referencePrice)}</span>}
      {p.discountPercent ? <span className={`${c}__off`}>{p.discountPercent}% off</span> : null}
    </div>
  );
}

export function Stars({ rating, count }: { rating: number | null; count: number }) {
  if (!rating || !count) return <span className="pcard__meta">No ratings yet</span>;
  return (
    <span className="pcard__rating" aria-label={`Rated ${rating} out of 5 by ${count} customer${count === 1 ? '' : 's'}`}>
      <span className="pcard__stars">{rating.toFixed(1)} <Icon name="star" size={10} /></span>
      <span className="pcard__meta">({count.toLocaleString('en-IN')})</span>
    </span>
  );
}

function DealLine({ endsAt, label }: { endsAt: string; label: string }) {
  const now = useNow(30_000);
  return <span className="pcard__deal"><Icon name="clock" size={12} /> {label} · {timeLeft(endsAt, now)}</span>;
}

/** A Shopping product card. Every figure on it comes from the server (prices, ratings, badges, deal end time). */
export function ShopCard({ p, onCompare }: { p: Card; onCompare?: (p: Card) => void }) {
  const compare = useCompare();
  const comparing = compare.some((x) => x.id === p.id);
  return (
    <article className={`pcard ${p.inStock ? '' : 'pcard--out'}`} data-theme="shopping">
      <Link to={`/products/${p.id}`} className="pcard__link" aria-label={`${p.name}${p.brand ? ` by ${p.brand}` : ''}, ${formatMoney(p.price)}`}>
        <div className="pcard__media">
          <ShopImage image={p.image} alt={p.name} icon={p.categoryIcon} brand={p.brand} />
          {p.badges.length > 0 && <div className="pcard__badges">{p.badges.map((b) => <span key={b} className={`sbadge sbadge--${b}`}>{BADGE_LABEL[b]}</span>)}</div>}
          {!p.inStock && <span className="pcard__out">Out of stock</span>}
        </div>
        <div className="pcard__body">
          {p.brand && <span className="pcard__brand">{p.brand}</span>}
          <span className="pcard__name">{p.name}</span>
          <Stars rating={p.rating} count={p.ratingCount} />
          <Price p={p} />
          {p.deal ? <DealLine endsAt={p.deal.endsAt} label={p.deal.label} />
            : p.reason ? <span className="pcard__meta">{p.reason}</span>
            : <span className="pcard__meta">{p.seller.name}{p.seller.isVerified ? ' · Verified seller' : ''}</span>}
        </div>
      </Link>
      <WishlistButton target={{ productId: p.id }} name={p.name} />
      {onCompare && (
        <label className="pcard__compare">
          <input type="checkbox" checked={comparing} onChange={() => onCompare(p)} /> Compare
        </label>
      )}
    </article>
  );
}

export function CardSkeletons({ n = 4 }: { n?: number }) {
  return <>{Array.from({ length: n }, (_, i) => <div key={i} className="pcard" aria-hidden="true"><div className="pcard__media skeleton" /><div className="pcard__body"><span className="skeleton" style={{ height: 12, width: '50%' }} /><span className="skeleton" style={{ height: 14 }} /><span className="skeleton" style={{ height: 18, width: '40%' }} /></div></div>)}</>;
}
