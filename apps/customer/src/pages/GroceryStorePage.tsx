import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { EmptyState, ErrorState, Icon, Skeleton, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { WishlistButton } from '../features/wishlist/WishlistButton';
import { Badges, BasketBar, ProductCard, Rail, Section, StatusPill } from '../features/groceries/parts';
import { useGroceryAt } from '../features/groceries/useGroceries';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

/** One vendor's store: its own catalogue, prices, stock, offers, hours and delivery options. */
export function GroceryStorePage() {
  useThemeOverride('grocery');
  const { slug = '' } = useParams();
  const { at, key } = useGroceryAt();
  const { status } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const store = useQuery({ queryKey: ['groceries', 'store', slug, key, status], queryFn: () => api.groceries.store(slug, at) });
  const [cat, setCat] = useState<string>('');
  const [q, setQ] = useState('');
  const [debounced, setDebounced] = useState('');
  const [sort, setSort] = useState('popular');
  useEffect(() => { const t = setTimeout(() => setDebounced(q.trim()), 250); return () => clearTimeout(t); }, [q]);
  const products = useQuery({
    queryKey: ['groceries', 'store-products', slug, cat, debounced, sort, key],
    queryFn: () => api.groceries.storeProducts(slug, { category: cat || undefined, q: debounced || undefined, sort }, at),
    placeholderData: keepPreviousData,
  });
  const notify = useMutation({
    mutationFn: () => api.groceries.alert({ storeId: store.data!.id }),
    onSuccess: () => { toast('We’ll notify you when this store takes orders again.'); qc.invalidateQueries({ queryKey: ['groceries', 'store', slug] }); },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t set the reminder.', 'error'),
  });

  if (store.isError) {
    return store.error instanceof ApiError && store.error.status === 404
      ? <EmptyState icon="store" title="Store not found" message="It may have moved or is no longer on Click." action={<Link className="btn btn--outline" to="/groceries">Browse Groceries</Link>} />
      : <ErrorState error={store.error} onRetry={() => store.refetch()} />;
  }
  if (store.isPending) return <div className="gr-page" data-theme="grocery"><Skeleton height={220} radius={24} /><Skeleton height={60} /><Skeleton height={300} /></div>;
  const s = store.data;
  const unavailable = s.status.state === 'unavailable';

  return (
    <div className="gr-page" data-theme="grocery">
      <Link to="/groceries" className="gr-back"><Icon name="back" size={18} /> Groceries</Link>
      <section className="gr-storehero">
        {s.coverUrl && <img className="gr-storehero__cover" src={s.coverUrl} alt="" />}
        <div className="gr-storehero__body">
          <div className="spread" style={{ alignItems: 'flex-start' }}>
            <div className="gr-storehero__id">
              <span className="gr-store__mark gr-store__mark--lg" aria-hidden="true">{s.name.slice(0, 1)}</span>
              <div>
                <h1>{s.name}</h1>
                <p className="small muted">{s.categories.map((c) => c.name).slice(0, 4).join(' · ')}</p>
              </div>
            </div>
            <WishlistButton target={{ storeId: s.id }} name={s.name} />
          </div>
          <Badges badges={s.badges} />
          <div className="gr-storehero__facts">
            <StatusPill status={s.status} />
            {s.rating ? <span><Icon name="star" size={14} /> {s.rating.average} ({s.rating.count} ratings)</span> : <span className="muted">No ratings yet</span>}
            {s.etaLabel && <span><Icon name="clock" size={14} /> {s.etaLabel}</span>}
            {s.distanceKm != null && <span><Icon name="pin" size={14} /> {s.distanceKm.toFixed(1)} km</span>}
            {s.minOrder && <span>Minimum order {formatMoney(s.minOrder, s.currency)}</span>}
            {s.freeDeliveryAbove && <span>Free delivery over {formatMoney(s.freeDeliveryAbove, s.currency)}</span>}
          </div>
          {!s.deliverable && s.reason && <p className="small gr-note">{s.reason}</p>}
          {unavailable && (
            <div className="gr-callout" role="status">
              <span>This store is currently unavailable.</span>
              <div className="row">
                {status === 'authenticated' && (s.alertSet ? <span className="small muted">We’ll notify you.</span> : <button type="button" className="btn btn--sm btn--primary" onClick={() => notify.mutate()} disabled={notify.isPending}>Notify me</button>)}
                <Link to="/groceries" className="btn btn--sm btn--outline">View other stores</Link>
              </div>
            </div>
          )}
          {s.status.state === 'closed' && <p className="small gr-note">Closed now · {s.status.detail}. You can still schedule a delivery for when it opens.</p>}
        </div>
      </section>

      <div className="gr-modes" aria-label="Delivery options">
        {s.deliveryOptions.map((o) => (
          <div key={o.mode} className={`gr-mode${o.available ? '' : ' gr-mode--off'}`}>
            <strong>{o.label}</strong>
            <span className="small">{o.available ? `${o.summary}${o.fee ? ` · ${Number(o.fee) ? formatMoney(o.fee) : 'free'}` : ''}` : o.reason}</span>
          </div>
        ))}
      </div>

      {s.offers.length > 0 && (
        <div className="gr-offers">
          {s.offers.map((o) => <div key={o.id} className="gr-offer"><Icon name="tag" size={18} /><span><strong>{o.title}</strong><span className="small muted">{o.description}</span></span></div>)}
        </div>
      )}

      <div className="gr-search__field gr-search__field--store" role="search">
        <Icon name="search" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Search ${s.name}`} aria-label={`Search in ${s.name}`} />
      </div>

      <div className="gr-catbar">
        <button type="button" className="chip" aria-pressed={!cat} onClick={() => setCat('')}>All ({s.productCount})</button>
        {s.categories.map((c) => <button key={c.slug} type="button" className="chip" aria-pressed={cat === c.slug} onClick={() => setCat(cat === c.slug ? '' : c.slug)}>{c.name} ({c.count})</button>)}
        <label className="gr-select">
          <span className="sr-only">Sort</span>
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="popular">Popular</option><option value="price_low">Price: low to high</option><option value="price_high">Price: high to low</option><option value="new">New</option>
          </select>
        </label>
      </div>

      {!cat && !debounced && s.popular.length > 0 && (
        <Section title="Popular here" subtitle="Most ordered from this store."><Rail items={s.popular} showStore={false} /></Section>
      )}

      {products.isError ? <ErrorState error={products.error} onRetry={() => products.refetch()} /> : !products.data ? (
        <div className="gr-grid">{Array.from({ length: 6 }, (_, i) => <Skeleton key={i} height={250} radius={18} />)}</div>
      ) : products.data.results.length === 0 ? (
        <EmptyState icon="grocery" title={debounced ? 'No matching products' : 'Nothing here yet'} message={debounced ? 'Try another word.' : 'This store hasn’t added products in this category yet.'} />
      ) : (
        <Section title={cat ? s.categories.find((c) => c.slug === cat)?.name ?? 'Products' : 'All products'} subtitle={`${products.data.count} products from ${s.name}`}>
          <div className="gr-grid">{products.data.results.map((l) => <ProductCard key={l.id} l={l} showStore={false} />)}</div>
        </Section>
      )}

      <section className="gr-about card card--pad">
        <h2 className="gr-h3">About {s.name}</h2>
        {s.about && <p className="small">{s.about}</p>}
        <p className="small muted"><Icon name="pin" size={14} /> {s.address}{s.verified ? ' · Verified by Click.' : ' · Verification pending'}</p>
        {s.hours.length > 0 && (
          <div className="gr-hours">
            {s.hours.map((h, i) => <span key={i} className="small"><strong>{h.day}</strong> {h.opens} – {h.closes}</span>)}
          </div>
        )}
        {s.freshnessNote && <p className="small">{s.freshnessNote}</p>}
        {s.policies && <p className="small muted">{s.policies}</p>}
        {s.reviews.length > 0 && (
          <div className="stack" style={{ gap: 6 }}>
            <h3 className="gr-h3">What customers say</h3>
            {s.reviews.map((r, i) => <p key={i} className="small"><Icon name="star" size={12} /> {r.rating} · “{r.comment}” — {r.author}</p>)}
          </div>
        )}
        <Link to="/help" className="small">Help with an order from this store</Link>
      </section>
      <BasketBar />
    </div>
  );
}

