import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ApiError, type ShopProductDetail, type ShopVariant } from '@click/api';
import { Button, EmptyState, ErrorState, Icon, QuantityStepper, Skeleton, type IconName } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { useDeliveryLocation } from '../location/LocationProvider';
import { formatMoney } from '../lib/format';
import { api } from '../lib/api';
import { useCompare } from '../features/shop/compare';
import { Reviews } from '../features/shop/Reviews';
import { CompareBar, ProductRail, SectionHead } from '../features/shop/ShopBlocks';
import { BADGE_LABEL, Price, Stars } from '../features/shop/ShopCard';
import { ShopImage } from '../features/shop/ShopImage';
import { deliveryWindow, ESTIMATE_BASIS, timeLeft, useNow } from '../features/shop/time';
import { useShopActions } from '../features/shop/useShopActions';
import { WishlistButton } from '../features/wishlist/WishlistButton';

/** Click. Shopping product page (retail listings). Everything shown comes from the product, seller and review records. */
export function ShopProductPage({ id }: { id: string }) {
  useThemeOverride('shopping');
  const { selected, point } = useDeliveryLocation();
  const at = point ? { lat: point.lat, lng: point.lng } : selected ? { city: selected.city } : undefined;
  const product = useQuery({ queryKey: ['shop', 'product', id, at], queryFn: () => api.shop.product(id, at) });

  if (product.isError) {
    return product.error instanceof ApiError && product.error.status === 404
      ? <EmptyState icon="alert" title="This product isn’t available" message="It may no longer be sold on Click." action={<Link to="/shopping" className="btn btn--outline">Back to Shopping</Link>} />
      : <ErrorState error={product.error} onRetry={() => product.refetch()} />;
  }
  if (product.isPending) return <div className="spdp"><Skeleton height={360} radius={22} /><div className="stack"><Skeleton height={20} width="30%" /><Skeleton height={34} width="80%" /><Skeleton height={40} width="50%" /><Skeleton height={140} /></div></div>;
  return <Detail key={product.data.id} p={product.data} addressLabel={selected ? `${selected.label[0]!.toUpperCase()}${selected.label.slice(1)} · ${selected.city}` : null} />;
}

function initialSelection(p: ShopProductDetail): Record<string, string> {
  const v = p.variants.find((x) => x.inStock) ?? p.variants[0];
  return v ? { ...v.options } : {};
}

function Detail({ p, addressLabel }: { p: ShopProductDetail; addressLabel: string | null }) {
  const [sel, setSel] = useState<Record<string, string>>(() => initialSelection(p));
  const [img, setImg] = useState(0);
  const [qty, setQty] = useState(1);
  const { addToCart, buyNow, toggleCompare, addedSheet, isAdding } = useShopActions();
  const compare = useCompare();
  const now = useNow(1000);
  useEffect(() => { window.scrollTo?.(0, 0); }, [p.id]);

  const variant: ShopVariant | undefined = useMemo(
    () => p.variants.find((v) => p.axes.every((a) => v.options[a.name] === sel[a.name])), [p, sel]);
  // A value can be chosen when some in-stock variant has it (choosing it moves to that variant if needed).
  const available = (axis: string, value: string) => p.variants.some((v) => v.inStock && v.options[axis] === value);
  const shown = variant ?? p;
  const purchasable = p.hasVariants ? !!variant?.inStock : p.inStock;
  const needsChoice = p.hasVariants && !variant;
  const comparing = compare.some((x) => x.id === p.id);
  const gallery = p.gallery.length ? p.gallery : [null];
  const action = { variantId: variant?.id ?? null, variantLabel: variant?.label, quantity: qty };
  const choose = (axis: string, value: string) => {
    const next = { ...sel, [axis]: value };
    // Keep other choices if that combination exists; otherwise move to an in-stock variant with this value.
    if (!p.variants.some((v) => v.inStock && p.axes.every((a) => v.options[a.name] === next[a.name]))) {
      const alt = p.variants.find((v) => v.inStock && v.options[axis] === value);
      if (alt) { setSel({ ...alt.options }); return; }
    }
    setSel(next);
  };

  return (
    <div className="stack" data-theme="shopping">
      <nav className="small muted row" aria-label="Breadcrumb" style={{ flexWrap: 'wrap', gap: 4 }}>
        <Link to="/shopping">Shopping</Link><span aria-hidden="true">›</span>
        {p.categorySlug && <><Link to={`/shopping/c/${p.categorySlug}`}>{p.category}</Link></>}
      </nav>
      <div className="spdp">
        <div className="spdp__gallery">
          <div className="spdp__main">
            <ShopImage image={gallery[img] ?? null} alt={p.name} icon={p.categoryIcon} brand={p.brand} sizes="(min-width: 960px) 50vw, 100vw" eager />
            <WishlistButton target={{ productId: p.id }} name={p.name} />
            {p.badges.length > 0 && <div className="pcard__badges">{p.badges.map((b) => <span key={b} className={`sbadge sbadge--${b}`}>{BADGE_LABEL[b]}</span>)}</div>}
          </div>
          {gallery.length > 1 && (
            <div className="spdp__thumbs" role="tablist" aria-label="Product photos">
              {gallery.map((g, i) => (
                <button key={i} type="button" className="spdp__thumb" aria-current={i === img} aria-label={`Photo ${i + 1}`} onClick={() => setImg(i)}>
                  <ShopImage image={g} alt="" icon={p.categoryIcon} sizes="64px" />
                </button>
              ))}
            </div>
          )}
          {!p.gallery.length && <p className="small muted">The seller hasn’t added photos yet.</p>}
        </div>

        <div className="spdp__info">
          <div className="stack" style={{ gap: 6 }}>
            {p.brand && (p.brandSlug ? <Link to={`/shopping/brands/${p.brandSlug}`} className="spdp__brand">{p.brand}</Link> : <span className="spdp__brand">{p.brand}</span>)}
            <h1 className="spdp__title">{p.name}</h1>
            <a href="#reviews"><Stars rating={p.rating} count={p.ratingCount} /></a>
          </div>
          <div className="stack" style={{ gap: 4 }}>
            <Price p={{ ...shown, fromPrice: p.hasVariants && !variant && p.fromPrice }} size="page" />
            <span className="small muted">Inclusive of item price. Tax and delivery are calculated at checkout.</span>
          </div>
          {p.deal && (
            <div className="spdp__deal" role="note">
              <Icon name="clock" size={16} /> {p.deal.label}: {p.deal.percentOff}% off · {timeLeft(p.deal.endsAt, now)}
              {p.deal.remaining != null && <span>· {p.deal.remaining} left at this price</span>}
            </div>
          )}

          {p.axes.map((a) => (
            <div key={a.name} className="spdp__axis">
              <h4>{a.name}: <span>{sel[a.name] ?? 'Choose'}</span></h4>
              <div className="vchips" role="radiogroup" aria-label={a.name}>
                {a.values.map((v) => (
                  <button key={v} type="button" role="radio" className="vchip" aria-checked={sel[a.name] === v} disabled={!available(a.name, v)}
                    aria-label={`${v}${available(a.name, v) ? '' : ' (out of stock)'}`} onClick={() => choose(a.name, v)}>{v}</button>
                ))}
              </div>
            </div>
          ))}
          {variant && !variant.inStock && <p className="badge badge--warning">{variant.label} is out of stock</p>}
          {variant?.lowStock && <p className="badge badge--warning" style={{ alignSelf: 'flex-start' }}>Only a few left</p>}
          {!p.hasVariants && p.lowStock && <p className="badge badge--warning" style={{ alignSelf: 'flex-start' }}>Only a few left</p>}
          {!purchasable && !needsChoice && !p.hasVariants && <p className="badge badge--warning" style={{ alignSelf: 'flex-start' }}>Out of stock</p>}

          <div className="spdp__actions">
            {purchasable && <QuantityStepper value={qty} onChange={(n) => setQty(Math.max(1, Math.min(10, n)))} label={p.name} max={10} />}
            <Button disabled={!purchasable} loading={isAdding} onClick={() => addToCart(p, action)}>Add to cart</Button>
            <Button className="spdp__buy" disabled={!purchasable || isAdding} onClick={() => buyNow(p, action)}>Buy now</Button>
          </div>
          <label className="row small" style={{ gap: 8 }}>
            <input type="checkbox" checked={comparing} onChange={() => toggleCompare({ id: p.id, name: p.name, categorySlug: p.categorySlug })} style={{ accentColor: 'var(--c-theme-solid)' }} />
            Add to compare
          </label>

          <section className="spdp__panel" aria-label="Delivery">
            <h3>Delivery</h3>
            {p.delivery ? (
              <div className="stack" style={{ gap: 4 }}>
                <span><strong>Estimated {deliveryWindow(p.delivery)}</strong>{addressLabel && <span className="muted small"> · to {addressLabel}</span>}</span>
                <span className="small muted">An estimate ({ESTIMATE_BASIS[p.delivery.basis]}), not a promise. The exact date is set when the seller ships.</span>
                <span className="small">{Number(p.delivery.fee) === 0 ? 'Free delivery' : `Delivery ${formatMoney(p.delivery.fee)}`}
                  {p.delivery.freeAbove && Number(p.delivery.fee) > 0 && ` · free on orders from ${p.seller.name} above ${formatMoney(p.delivery.freeAbove)}`}</span>
              </div>
            ) : (
              <p className="small">Choose your delivery address on <Link to="/" style={{ color: 'var(--c-theme-strong)', fontWeight: 600 }}>Home</Link> to see delivery dates and fees.</p>
            )}
          </section>

          <section className="spdp__panel" aria-label="Sold by">
            <div className="seller">
              <span className="seller__mono" aria-hidden="true">{p.seller.name.slice(0, 2).toUpperCase()}</span>
              <div className="stack" style={{ gap: 2 }}>
                <span className="small muted">Sold and shipped by</span>
                <strong>{p.seller.name} {p.seller.isVerified && <span className="verified"><Icon name="shield" size={12} /> Verified seller</span>}</strong>
                <span className="small muted">{p.seller.city}{p.seller.rating ? ` · ${p.seller.rating.toFixed(1)}★ (${p.seller.ratingCount.toLocaleString('en-IN')})` : ''} · ships in {p.seller.dispatchDays} day{p.seller.dispatchDays === 1 ? '' : 's'}</span>
              </div>
            </div>
            <div className="trust">
              <Trust icon="history" title={p.policies.returnDays ? `${p.policies.returnDays}-day ${p.policies.replacementOnly ? 'replacement' : 'returns'}` : 'Not returnable'}
                note={p.seller.returnPolicy || undefined} />
              {p.policies.warranty && <Trust icon="shield" title={p.policies.warranty} />}
              <Trust icon="wallet" title={p.policies.codAvailable ? 'Cash on delivery available' : 'Prepaid only'} note={p.policies.codAvailable ? undefined : 'Pay with Click. Wallet'} />
              <Trust icon="key" title="Secure payment" note="Click. Wallet or cash; prices are checked by Click. at checkout" />
            </div>
          </section>

          {p.offers.length > 0 && (
            <section className="spdp__panel" aria-label="Offers">
              <h3>Offers from {p.seller.name}</h3>
              {p.offers.map((o) => (
                <div key={o.id} className="row small" style={{ alignItems: 'flex-start' }}><Icon name="tag" size={16} />
                  <span><strong>{o.title}</strong>{o.description ? ` · ${o.description}` : ''}{o.redeemable ? ' · apply at checkout' : ''}</span></div>
              ))}
            </section>
          )}

          {(p.highlights.length > 0 || p.description) && (
            <section className="spdp__panel" aria-label="About this item">
              <h3>About this item</h3>
              {p.highlights.length > 0 && <ul className="highlights">{p.highlights.map((h) => <li key={h}>{h}</li>)}</ul>}
              {p.description && <p className="small">{p.description}</p>}
            </section>
          )}
          {p.specs.length > 0 && (
            <section className="spdp__panel" aria-label="Specifications">
              <h3>Specifications</h3>
              <table className="specs"><tbody>{p.specs.map((s) => <tr key={s.code}><th scope="row">{s.name}</th><td>{s.value}</td></tr>)}</tbody></table>
            </section>
          )}
          <Reviews product={p} />
        </div>
      </div>

      {p.boughtTogether.length > 0 && (
        <section className="shop-sec"><SectionHead title="Frequently bought together" subtitle="Based on what customers ordered with this item." /><ProductRail products={p.boughtTogether} /></section>
      )}
      {p.similar.length > 0 && (
        <section className="shop-sec"><SectionHead title="Similar products" link={p.categorySlug ? `/shopping/c/${p.categorySlug}` : null} /><ProductRail products={p.similar} /></section>
      )}

      <div className="spdp__bar" role="region" aria-label="Buy">
        <div className="spdp__bar-price"><strong>{formatMoney(shown.price)}</strong>{shown.referencePrice && <span className="small muted" style={{ textDecoration: 'line-through' }}>{formatMoney(shown.referencePrice)}</span>}</div>
        <Button disabled={!purchasable} loading={isAdding} onClick={() => addToCart(p, action)}>{needsChoice ? 'Choose options' : 'Add to cart'}</Button>
        <Button className="spdp__buy" disabled={!purchasable || isAdding} onClick={() => buyNow(p, action)}>Buy now</Button>
      </div>
      <CompareBar />
      {addedSheet}
    </div>
  );
}

function Trust({ icon, title, note }: { icon: IconName; title: string; note?: string }) {
  return <div className="trust__item"><Icon name={icon} size={18} /><span>{title}{note && <small>{note}</small>}</span></div>;
}
