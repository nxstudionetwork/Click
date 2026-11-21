import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import type { GroceryBadge, GroceryCategoryChip, GroceryListing, GroceryStoreCard, GroceryStoreStatus } from '@click/api';
import { Icon, type IconName } from '../../components/ui';
import { formatMoney } from '../../lib/format';
import { useBasketActions, useBasketLines } from './useGroceries';

const CATEGORY_ICON: Record<string, IconName> = {
  vegetables: 'leaf', fruits: 'apple', 'leafy-greens-herbs': 'leaf', dairy: 'milk', eggs: 'egg', bakery: 'bread', breakfast: 'coffee',
  'rice-atta': 'wheat', pulses: 'wheat', 'oil-ghee': 'oil', 'spices-salt-sugar': 'spice', snacks: 'cookie', beverages: 'drop',
  cleaning: 'spray', 'personal-care': 'beauty', 'baby-care': 'baby', 'pet-care': 'paw',
};
export const categoryIcon = (slug: string, icon?: string): IconName => (icon as IconName) || CATEGORY_ICON[slug] || 'grocery';

/** Licensed photo when the item has one; otherwise a neutral placeholder (never an invented product image). */
export function GroceryImage({ l, large = false }: { l: Pick<GroceryListing, 'imageUrl' | 'name' | 'brand' | 'category' | 'imageCredit'>; large?: boolean }) {
  if (l.imageUrl) {
    return (
      <figure className={`gr-img${large ? ' gr-img--large' : ''}`}>
        <img src={l.imageUrl} alt={l.name} loading="lazy" decoding="async" referrerPolicy="no-referrer" />
        {large && l.imageCredit && <figcaption>Photo: {l.imageCredit}</figcaption>}
      </figure>
    );
  }
  return (
    <div className={`gr-img gr-img--none${large ? ' gr-img--large' : ''}`} role="img" aria-label={`${l.name} (no photo yet)`}>
      <Icon name={categoryIcon(l.category.slug)} size={large ? 44 : 28} />
      {l.brand && <span>{l.brand}</span>}
    </div>
  );
}

export function StatusPill({ status }: { status: GroceryStoreStatus }) {
  return <span className={`gr-status gr-status--${status.state}`}>{status.label}{status.detail && status.state !== 'open' ? ` · ${status.detail}` : ''}</span>;
}

export function Badges({ badges }: { badges: GroceryBadge[] }) {
  if (!badges.length) return null;
  return <span className="gr-badges">{badges.map((b) => <span key={b.code} className={`gr-badge gr-badge--${b.code}`}>{b.code === 'verified' && <Icon name="shield" size={12} />}{b.label}</span>)}</span>;
}

/** Add / quantity control. Out of stock or closed stores never show an add button. */
export function AddControl({ l, compact = false }: { l: GroceryListing; compact?: boolean }) {
  const { lines } = useBasketLines();
  const { addListing, setQuantity, busy } = useBasketActions();
  const line = lines.get(l.id);
  if (!l.inStock) return <span className="gr-oos">Out of stock</span>;
  if (!l.orderable) return <span className="gr-oos">Store not taking orders</span>;
  if (!line) {
    return (
      <button type="button" className={`gr-add${compact ? ' gr-add--compact' : ''}`} disabled={busy}
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); void addListing(l); }} aria-label={`Add ${l.name} ${l.size}`}>
        <Icon name="plus" size={16} /> Add
      </button>
    );
  }
  const max = l.stockLeft ?? 50;
  return (
    <div className="gr-qty" role="group" aria-label={`Quantity of ${l.name}`} onClick={(e) => { e.preventDefault(); e.stopPropagation(); }}>
      <button type="button" aria-label={`Remove one ${l.name}`} disabled={busy} onClick={() => setQuantity(l.id, line.quantity - 1)}>−</button>
      <span aria-live="polite">{line.quantity}</span>
      <button type="button" aria-label={`Add one more ${l.name}`} disabled={busy || line.quantity >= max} onClick={() => setQuantity(l.id, line.quantity + 1)}>+</button>
    </div>
  );
}

export function Price({ l, currency = 'INR' }: { l: GroceryListing; currency?: string }) {
  return (
    <span className="gr-price">
      <strong>{formatMoney(l.price, currency)}</strong>
      {l.mrp && (l.dealEndsAt
        ? <s aria-label={`Usual price ${formatMoney(l.mrp, currency)}`}>{formatMoney(l.mrp, currency)}</s>
        : <s aria-label={`MRP ${formatMoney(l.mrp, currency)}`}>MRP {formatMoney(l.mrp, currency)}</s>)}
      {l.discountPercent ? <em>{l.discountPercent}% off</em> : null}
    </span>
  );
}

export function ProductCard({ l, showStore = true }: { l: GroceryListing; showStore?: boolean }) {
  return (
    <Link to={`/groceries/p/${l.id}`} className={`gr-card${l.inStock ? '' : ' gr-card--oos'}`}>
      <div className="gr-card__media">
        <GroceryImage l={l} />
        {l.freshToday && <span className="gr-flag">Fresh today</span>}
        {!l.freshToday && l.discountPercent ? <span className="gr-flag gr-flag--deal">{l.discountPercent}% off</span> : null}
      </div>
      <div className="gr-card__body">
        {l.brand && <span className="gr-card__brand">{l.brand}</span>}
        <strong className="gr-card__name">{l.name}</strong>
        <span className="gr-card__size">{l.size}{l.perUnit ? ` · ${l.perUnit}` : ''}{l.variableWeight ? ' · weighed' : ''}</span>
        {showStore && <span className="gr-card__store"><Icon name="store" size={12} /> {l.store.name}{l.otherStores ? ` +${l.otherStores} more` : ''}</span>}
        {l.stockLeft != null && <span className="gr-card__left">Only {l.stockLeft} left</span>}
      </div>
      <div className="gr-card__foot">
        <Price l={l} />
        <AddControl l={l} compact />
      </div>
    </Link>
  );
}

export function StoreCard({ s, wide = false }: { s: GroceryStoreCard; wide?: boolean }) {
  const fee = s.deliveryFee != null ? (Number(s.deliveryFee) === 0 ? 'Free delivery' : `Delivery ${formatMoney(s.deliveryFee, s.currency)}`) : '';
  return (
    <Link to={`/groceries/store/${s.slug}`} className={`gr-store${wide ? ' gr-store--wide' : ''}${s.status.state === 'unavailable' || !s.deliverable ? ' gr-store--muted' : ''}`}>
      <div className="gr-store__top">
        <span className="gr-store__mark" aria-hidden="true">{s.imageUrl ? <img src={s.imageUrl} alt="" /> : s.name.slice(0, 1)}</span>
        <span className="gr-store__id">
          <strong>{s.name}</strong>
          <span className="small muted">{s.categories.slice(0, 2).join(' · ')}{s.locality ? ` · ${s.locality}` : ''}</span>
        </span>
        {s.rating && <span className="gr-store__rating"><Icon name="star" size={13} /> {s.rating.average}<span className="muted"> ({s.rating.count})</span></span>}
      </div>
      <Badges badges={s.badges} />
      <div className="gr-store__facts">
        <StatusPill status={s.status} />
        {s.etaLabel && <span><Icon name="clock" size={13} /> {s.etaLabel}</span>}
        {s.distanceKm != null && <span>{s.distanceKm.toFixed(1)} km</span>}
        {fee && <span>{fee}</span>}
        {s.minOrder && <span>Min {formatMoney(s.minOrder, s.currency)}</span>}
      </div>
      {!s.deliverable && s.reason && <span className="small muted">{s.reason}</span>}
      {s.offer && <span className="gr-store__offer"><Icon name="tag" size={13} /> {s.offer}</span>}
    </Link>
  );
}

export function CategoryRail({ cats, active, to }: { cats: GroceryCategoryChip[]; active?: string; to: (slug: string) => string }) {
  if (!cats.length) return null;
  return (
    <nav className="gr-cats" aria-label="Categories">
      {cats.map((c) => (
        <Link key={c.slug} to={to(c.slug)} className="gr-cat" aria-current={active === c.slug ? 'page' : undefined}>
          <span className="gr-cat__icon"><Icon name={categoryIcon(c.slug, c.icon)} size={22} /></span>
          <span className="gr-cat__name">{c.name}</span>
        </Link>
      ))}
    </nav>
  );
}

export function Section({ title, subtitle, action, children, id }: { title: string; subtitle?: string; action?: ReactNode; children: ReactNode; id?: string }) {
  return (
    <section className="gr-sec" aria-labelledby={id ?? undefined}>
      <div className="gr-sec__head">
        <div><h2 id={id}>{title}</h2>{subtitle && <p className="small muted">{subtitle}</p>}</div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function Rail({ items, showStore = true }: { items: GroceryListing[]; showStore?: boolean }) {
  return <div className="gr-rail">{items.map((l) => <ProductCard key={l.id} l={l} showStore={showStore} />)}</div>;
}

/** Sticky basket summary (mobile) — sits above the bottom navigation and never covers it. */
export function BasketBar() {
  const { cart } = useBasketLines();
  if (!cart || cart.mode !== 'basket' || cart.itemCount === 0) return null;
  const stores = cart.groups.length;
  return (
    <>
      <div aria-hidden="true" style={{ height: 84 }} />
      <div className="gr-bar">
        <Link to="/groceries/basket">
          <span className="gr-bar__count">{cart.itemCount} item{cart.itemCount > 1 ? 's' : ''}{stores > 1 ? ` · ${stores} stores` : ''}</span>
          <strong>{formatMoney(cart.totals.subtotal)}</strong>
          <span className="gr-bar__cta">View basket <Icon name="right" size={16} /></span>
        </Link>
      </div>
    </>
  );
}
