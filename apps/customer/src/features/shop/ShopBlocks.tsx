import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import type { ShopBrand, ShopCampaign, ShopCard as Card, ShopCategory, ShopSection } from '@click/api';
import { Icon, type IconName } from '../../components/ui';
import { compareStore, useCompare } from './compare';
import { CardSkeletons, ShopCard } from './ShopCard';

const ROTATE_KEY = 'click.shopHeroIndex';

/**
 * The Shopping campaign hero. Campaigns (priority, start/end dates, active flag) come from the backend; expired ones
 * never arrive. With several, each visit opens on the next one and the customer can step through them. There is no
 * auto-scrolling carousel.
 */
export function CampaignHero({ campaigns }: { campaigns: ShopCampaign[] }) {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (campaigns.length < 2) return;
    try {
      const last = Number(localStorage.getItem(ROTATE_KEY) ?? -1);
      const next = Number.isFinite(last) ? (last + 1) % campaigns.length : 0;
      localStorage.setItem(ROTATE_KEY, String(next));
      setI(next);
    } catch { /* storage unavailable: start with the top campaign */ }
  }, [campaigns.length]);
  if (!campaigns.length) return null;
  const go = (d: number) => setI((x) => (x + d + campaigns.length) % campaigns.length);
  return (
    <section className="shop-hero" aria-roledescription="carousel" aria-label="Shopping campaigns">
      {campaigns.map((c, n) => (
        <div key={c.id} className={`shop-hero__slide ${n === i ? 'is-on' : ''}`} aria-hidden={n !== i} role="group" aria-roledescription="slide"
          aria-label={`${n + 1} of ${campaigns.length}`}>
          {c.imageUrl ? <img className="shop-hero__img" src={c.imageUrl} alt="" loading={n === 0 ? 'eager' : 'lazy'} /> : <div className="shop-hero__art" aria-hidden="true" />}
          {c.eyebrow && <span className="shop-hero__eyebrow">{c.eyebrow}</span>}
          <h2 className="shop-hero__title">{c.title}</h2>
          {c.subtitle && <p className="shop-hero__sub">{c.subtitle}</p>}
          <Link to={c.ctaPath} className="shop-hero__cta" tabIndex={n === i ? 0 : -1}>{c.ctaLabel} <Icon name="right" size={16} /></Link>
        </div>
      ))}
      {campaigns.length > 1 && (
        <div className="shop-hero__nav">
          <button type="button" className="shop-hero__arrow" aria-label="Previous campaign" onClick={() => go(-1)}><Icon name="back" size={16} /></button>
          {campaigns.map((c, n) => <button key={c.id} type="button" className="shop-hero__dot" aria-label={`Show campaign ${n + 1}`} aria-current={n === i} onClick={() => setI(n)} />)}
          <button type="button" className="shop-hero__arrow" aria-label="Next campaign" onClick={() => go(1)}><Icon name="right" size={16} /></button>
        </div>
      )}
    </section>
  );
}

export function CategoryTiles({ categories, current }: { categories: ShopCategory[]; current?: string }) {
  return (
    <div className="shop-cats">
      {categories.map((c) => (
        <Link key={c.slug} to={`/shopping/c/${c.slug}`} className="shop-cat" aria-current={current === c.slug ? 'page' : undefined}
          aria-label={`${c.name}${c.productCount ? `, ${c.productCount} products` : ''}`}>
          <span className="shop-cat__art">{c.imageUrl ? <img src={c.imageUrl} alt="" loading="lazy" /> : <Icon name={(c.icon || 'bag') as IconName} size={26} />}</span>
          <span className="shop-cat__name">{c.name}</span>
        </Link>
      ))}
    </div>
  );
}

export function SectionHead({ title, subtitle, link, linkLabel = 'See all' }: { title: string; subtitle?: string | null; link?: string | null; linkLabel?: string }) {
  return (
    <div className="shop-sec__head">
      <div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
      {link && <Link to={link} className="shop-sec__link">{linkLabel} <Icon name="right" size={14} /></Link>}
    </div>
  );
}

export function ProductRail({ products, onCompare }: { products: Card[]; onCompare?: (p: Card) => void }) {
  return <div className="shop-rail">{products.map((p) => <ShopCard key={p.id} p={p} onCompare={onCompare} />)}</div>;
}

export function BrandRail({ brands }: { brands: ShopBrand[] }) {
  return <div className="brand-rail">{brands.map((b) => <BrandCard key={b.slug} b={b} />)}</div>;
}

export function BrandCard({ b }: { b: ShopBrand }) {
  return (
    <Link to={`/shopping/brands/${b.slug}`} className="brand-card">
      {b.logoUrl ? <img src={b.logoUrl} alt="" width={52} height={52} loading="lazy" /> : <span className="brand-card__mono" aria-hidden="true">{b.name.slice(0, 2).toUpperCase()}</span>}
      <strong>{b.name}</strong><span>{b.productCount} product{b.productCount === 1 ? '' : 's'}</span>
    </Link>
  );
}

export function Section({ s, onCompare }: { s: ShopSection; onCompare?: (p: Card) => void }) {
  if (s.kind === 'brands') {
    return <section className="shop-sec" aria-labelledby={`s-${s.id}`}><SectionHead title={s.title} subtitle={s.subtitle} link={s.link} linkLabel="View all brands" /><BrandRail brands={s.brands} /></section>;
  }
  return (
    <section className={`shop-sec ${s.id === 'deals' ? 'shop-sec--deals' : ''}`} aria-label={s.title}>
      <SectionHead title={s.title} subtitle={s.subtitle} link={s.link} />
      <ProductRail products={s.products} onCompare={onCompare} />
    </section>
  );
}

export function RailSkeleton() {
  return <div className="shop-rail"><CardSkeletons n={4} /></div>;
}

/** Floating tray: shows while 1-4 products are chosen for comparison. */
export function CompareBar() {
  const items = useCompare();
  if (!items.length) return null;
  return (
    <div className="compare-bar" role="region" aria-label="Compare products">
      <strong>{items.length} to compare</strong>
      {items.length >= 2
        ? <Link to={`/shopping/compare?ids=${items.map((x) => x.id).join(',')}`} className="btn btn--primary btn--sm" data-theme="shopping">Compare now</Link>
        : <span className="small" style={{ opacity: .8 }}>Add one more</span>}
      <button type="button" className="compare-bar__clear" aria-label="Clear comparison" onClick={() => compareStore.clear()}><Icon name="close" size={16} /></button>
    </div>
  );
}
