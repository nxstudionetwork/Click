import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { StoreQuery, StoreType } from '@click/api';
import { useThemeOverride } from '../components/layout/AppShell';
import { Icon } from '../components/ui';
import { SERVICE_PAGES, type ServiceSort } from '../config/servicePages';
import { serviceForStoreType } from '../config/services';
import { HomeSection } from '../features/home/HomeSection';
import { FilterBar, HorizontalDiscovery, ServiceIntro, ServiceSearch, type ServiceFilters } from '../features/service/ServiceBlocks';
import { ServiceExploreCategories, ServiceNearby, ServiceOffers, ServicePopular, ServiceRecommended } from '../features/service/ServiceSections';
import { StoreFeed } from '../features/service/StoreFeed';
import { useStoreCategories } from '../features/stores/hooks';
import { ProductCard } from '../features/stores/ProductCard';
import { api } from '../lib/api';
import { useDeliveryLocation } from '../location/LocationProvider';

const FLAGS = ['veg', 'rating', 'offers', 'open', 'budget'] as const;

/**
 * Main service page (Food, Groceries, Shop): intro → horizontal categories → search → filters → discovery
 * sections → all stores. The URL holds category, search and filters, so Back, refresh and links keep them.
 */
export function ServicePage({ storeType }: { storeType: StoreType }) {
  const config = SERVICE_PAGES[storeType];
  useThemeOverride(serviceForStoreType(storeType).theme);
  const [params, setParams] = useSearchParams();
  const { point } = useDeliveryLocation();
  const category = params.get('category') ?? '';
  const q = params.get('q') ?? '';
  const filters: ServiceFilters = {
    veg: params.get('veg') === '1', rating: params.get('rating') === '1', offers: params.get('offers') === '1',
    open: params.get('open') === '1', budget: params.get('budget') === '1', sort: (params.get('sort') ?? '') as ServiceSort,
  };
  const [draft, setDraft] = useState(q);
  const categories = useStoreCategories(storeType);

  const patch = (next: Record<string, string>) => setParams((p) => {
    const n = new URLSearchParams(p);
    for (const [k, v] of Object.entries(next)) { if (v) n.set(k, v); else n.delete(k); }
    return n;
  }, { replace: true });

  // Debounced search into the URL. The box follows the URL only for outside changes (Clear, Back, links),
  // never for our own debounced write, so letters typed meanwhile are never lost.
  const written = useRef(q);
  useEffect(() => {
    if (draft.trim() === q) return;
    const t = setTimeout(() => { written.current = draft.trim(); patch({ q: draft.trim() }); }, 300);
    return () => clearTimeout(t);
  }, [draft]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (q !== written.current) { written.current = q; setDraft(q); } }, [q]);

  const query: StoreQuery = useMemo(() => ({
    type: storeType, category: category || undefined, search: q || undefined,
    veg: filters.veg || undefined, minRating: filters.rating ? 4 : undefined, offers: filters.offers || undefined,
    open: filters.open || undefined, maxPrice: filters.budget ? 2 : undefined,
    ...(filters.sort === 'distance' && point ? { lat: point.lat, lng: point.lng, radius: 50, sort: 'distance' as const } : filters.sort && filters.sort !== 'distance' ? { sort: filters.sort } : {}),
  }), [storeType, category, q, filters.veg, filters.rating, filters.offers, filters.open, filters.budget, filters.sort, point]);

  const filtering = !!(category || FLAGS.some((f) => filters[f]) || filters.sort);
  const clearAll = () => { written.current = ''; setDraft(''); setParams({}, { replace: true }); };
  const selectedName = categories.data?.find((c) => c.slug === category)?.name;

  return (
    <div className="svc" data-theme={serviceForStoreType(storeType).theme}>
      <ServiceIntro config={config} />
      <HorizontalDiscovery config={config} categories={categories.data ?? []} loading={categories.isPending} selected={category} onSelect={(slug) => patch({ category: slug })} />
      <ServiceSearch config={config} value={draft} onChange={setDraft} />
      <FilterBar config={config} filters={filters} hasLocation={!!point}
        onChange={(p) => patch(Object.fromEntries(Object.entries(p).map(([k, v]) => [k, typeof v === 'boolean' ? (v ? '1' : '') : String(v ?? '')])))} />

      {q ? (
        <SearchResults config={config} q={q} query={query} onClear={clearAll} />
      ) : filtering ? (
        <section className="stack" aria-labelledby="results-h">
          <div className="spread">
            <h2 id="results-h">{selectedName ?? `All ${config.plural}`}</h2>
            <button className="btn btn--ghost btn--sm" onClick={clearAll}><Icon name="close" size={16} /> Clear</button>
          </div>
          <StoreFeed query={query} plural={config.plural}
            empty={{ title: `No ${config.plural} match`, message: 'Try removing a filter or choosing another category.', action: <button className="btn btn--outline" onClick={clearAll}>Clear filters</button> }} />
        </section>
      ) : (
        <div className="svc-feed">
          <ServiceOffers config={config} />
          <ServiceNearby config={config} />
          <ServicePopular config={config} />
          <ServiceRecommended config={config} />
          <ServiceExploreCategories config={config} categories={categories.data ?? []} onSelect={(slug) => patch({ category: slug })} />
          <HomeSection id="svc-all" title={`All ${config.plural}`} icon="menu" theme={serviceForStoreType(storeType).theme}>
            <StoreFeed query={query} plural={config.plural} empty={{ title: `No ${config.plural} yet`, message: `${config.title} on Click. will appear here as partners join.` }} />
          </HomeSection>
        </div>
      )}
    </div>
  );
}

/** Search: stores (name, category or anything on their menu) plus matching dishes/products. */
function SearchResults({ config, q, query, onClear }: { config: (typeof SERVICE_PAGES)[StoreType]; q: string; query: StoreQuery; onClear: () => void }) {
  const items = useQuery({ queryKey: ['search', config.storeType, q], queryFn: ({ signal }) => api.catalog.search(q, config.storeType, signal), enabled: q.length >= 2 });
  const products = items.data?.products ?? [];
  return (
    <section className="stack" aria-labelledby="search-h" aria-live="polite">
      <div className="spread">
        <h2 id="search-h">Results for “{q}”</h2>
        <button className="btn btn--ghost btn--sm" onClick={onClear}><Icon name="close" size={16} /> Clear search</button>
      </div>
      {products.length > 0 && (
        <div className="stack" style={{ gap: 'var(--s-2)' }}>
          <h3>{config.dishesLabel}</h3>
          <div className="rail" role="list" aria-label={config.dishesLabel}>
            {products.slice(0, 12).map((p) => (
              <div key={p.id} className="rail__item" role="listitem"><ProductCard product={p} currency={p.store.currency} showStore /></div>
            ))}
          </div>
        </div>
      )}
      <h3>{config.plural[0]!.toUpperCase() + config.plural.slice(1)}</h3>
      <StoreFeed query={query} plural={config.plural} empty={{
        title: products.length ? `No ${config.plural} by that name` : 'We couldn’t find that.',
        message: `Try another ${config.storeType === 'restaurant' ? 'restaurant, dish or cuisine' : 'product, brand or store'}.`,
        action: <button className="btn btn--outline" onClick={onClear}>Browse {config.title}</button>,
      }} />
      <Link to={`/buddy?q=${encodeURIComponent(q)}`} className="small muted" style={{ alignSelf: 'center' }}>Can’t find it? Ask Buddy</Link>
    </section>
  );
}
