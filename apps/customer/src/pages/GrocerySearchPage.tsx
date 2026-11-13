import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { EmptyState, ErrorState, Icon, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { GrocerySearchField } from '../features/groceries/GrocerySearch';
import { BasketBar, ProductCard, StoreCard } from '../features/groceries/parts';
import { useGroceryAt } from '../features/groceries/useGroceries';
import { api } from '../lib/api';

const SORTS = [
  { id: 'relevance', label: 'Relevance' }, { id: 'price_low', label: 'Price: low to high' }, { id: 'price_high', label: 'Price: high to low' },
  { id: 'rating', label: 'Rating' }, { id: 'fastest', label: 'Fastest delivery' }, { id: 'popular', label: 'Popular' }, { id: 'new', label: 'New' },
];
const FILTER_KEYS = ['category', 'brand', 'store', 'in_stock', 'offers', 'dietary', 'min_rating', 'max_eta', 'min_price', 'max_price', 'section'];

/** Grocery search results with backend filters (only those the matched products actually support) and sorting. */
export function GrocerySearchPage() {
  useThemeOverride('grocery');
  const [params, setParams] = useSearchParams();
  const { at, key } = useGroceryAt();
  const [page, setPage] = useState(1);
  const query = Object.fromEntries([...params.entries()].filter(([, v]) => v !== ''));
  const res = useQuery({
    queryKey: ['groceries', 'search', query, page, key], queryFn: () => api.groceries.search({ ...query, page }, at),
    placeholderData: keepPreviousData,
  });
  const set = (k: string, v: string | null) => {
    const next = new URLSearchParams(params);
    if (v === null || v === '') next.delete(k); else next.set(k, v);
    setPage(1);
    setParams(next, { replace: true });
  };
  const toggle = (k: string, v: string) => set(k, params.get(k) === v ? null : v);
  const d = res.data;
  const active = FILTER_KEYS.filter((k) => params.get(k));

  return (
    <div className="gr-page" data-theme="grocery">
      <Link to="/groceries" className="gr-back"><Icon name="back" size={18} /> Groceries</Link>
      <GrocerySearchField key={params.get('q') ?? ''} initial={params.get('q') ?? ''} />

      <div className="gr-filters" role="group" aria-label="Filters">
        <label className="gr-select">
          <span className="sr-only">Sort</span>
          <Icon name="sort" size={16} />
          <select value={params.get('sort') ?? 'relevance'} onChange={(e) => set('sort', e.target.value === 'relevance' ? null : e.target.value)}>
            {SORTS.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </label>
        <button type="button" className="chip" aria-pressed={params.get('in_stock') === 'true'} onClick={() => toggle('in_stock', 'true')}>In stock</button>
        <button type="button" className="chip" aria-pressed={params.get('offers') === 'true'} onClick={() => toggle('offers', 'true')}>Offers</button>
        <button type="button" className="chip" aria-pressed={params.get('max_eta') === '30'} onClick={() => toggle('max_eta', '30')}>Under 30 min</button>
        <button type="button" className="chip" aria-pressed={params.get('min_rating') === '4'} onClick={() => toggle('min_rating', '4')}>Stores 4★+</button>
        <button type="button" className="chip" aria-pressed={params.get('dietary') === 'veg'} onClick={() => toggle('dietary', 'veg')}>Vegetarian</button>
        <button type="button" className="chip" aria-pressed={params.get('max_price') === '100'} onClick={() => toggle('max_price', '100')}>Under ₹100</button>
        {active.length > 0 && <button type="button" className="link-btn small" onClick={() => { const n = new URLSearchParams(); if (params.get('q')) n.set('q', params.get('q')!); setParams(n, { replace: true }); }}>Clear filters</button>}
      </div>

      {d && (d.facets.categories.length > 1 || d.facets.brands.length > 0) && (
        <div className="gr-facets">
          {d.facets.categories.length > 1 && (
            <div className="gr-chips" aria-label="Category">
              {d.facets.categories.map((c) => <button key={c.slug} type="button" className="chip" aria-pressed={params.get('category') === c.slug} onClick={() => toggle('category', c.slug)}>{c.name}</button>)}
            </div>
          )}
          {d.facets.brands.length > 0 && (
            <div className="gr-chips" aria-label="Brand">
              {d.facets.brands.slice(0, 14).map((b) => <button key={b} type="button" className="chip" aria-pressed={params.get('brand') === b} onClick={() => toggle('brand', b)}>{b}</button>)}
            </div>
          )}
        </div>
      )}

      {res.isError ? <ErrorState error={res.error} onRetry={() => res.refetch()} /> : !d ? (
        <div className="gr-grid">{Array.from({ length: 8 }, (_, i) => <Skeleton key={i} height={260} radius={18} />)}</div>
      ) : (
        <>
          {!d.hasLocation && <p className="small gr-note"><Icon name="pin" size={14} /> Choose a delivery location to see which stores can deliver and how fast.</p>}
          {d.stores.length > 0 && (
            <section className="gr-sec" aria-label="Stores">
              <h2 className="gr-h3">Stores</h2>
              <div className="gr-stores">{d.stores.map((s) => <StoreCard key={s.id} s={s} />)}</div>
            </section>
          )}
          <p className="small muted" aria-live="polite">{d.count} product{d.count === 1 ? '' : 's'}{d.query ? ` for “${d.query}”` : ''} · one card per product, showing the best nearby price</p>
          {d.results.length === 0 ? (
            <EmptyState icon="search" title="Nothing found nearby" message="Try another word, remove a filter, or check a different store." action={<Link to="/groceries" className="btn btn--outline">Back to Groceries</Link>} />
          ) : (
            <div className="gr-grid">{d.results.map((l) => <ProductCard key={l.id} l={l} />)}</div>
          )}
          {d.hasMore && <button type="button" className="btn btn--outline" onClick={() => setPage((p) => p + 1)} disabled={res.isFetching}>{res.isFetching ? 'Loading…' : 'Next page'}</button>}
          {page > 1 && <button type="button" className="link-btn small" onClick={() => setPage((p) => p - 1)}>Previous page</button>}
        </>
      )}
      <BasketBar />
    </div>
  );
}
