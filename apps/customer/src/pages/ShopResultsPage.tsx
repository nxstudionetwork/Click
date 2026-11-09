import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import type { ShopSort } from '@click/api';
import { Button, EmptyState, ErrorState, Icon, Sheet, Skeleton, type IconName } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { FilterPanel } from '../features/shop/FilterPanel';
import { CampaignHero, CompareBar, ProductRail, SectionHead } from '../features/shop/ShopBlocks';
import { CardSkeletons, ShopCard } from '../features/shop/ShopCard';
import { ShopSearchField } from '../features/shop/ShopSearch';
import { useShopActions } from '../features/shop/useShopActions';
import { api } from '../lib/api';

const SORTS: { id: ShopSort; label: string }[] = [
  { id: 'relevance', label: 'Relevance' }, { id: 'popular', label: 'Popularity' }, { id: 'price_asc', label: 'Price: low to high' },
  { id: 'price_desc', label: 'Price: high to low' }, { id: 'rating', label: 'Customer rating' }, { id: 'newest', label: 'Newest' },
  { id: 'discount', label: 'Biggest discount' },
];

/** Search results, a category page (/shopping/c/:slug) or a brand page (/shopping/brands/:slug). State lives in the URL. */
export function ShopResultsPage({ mode }: { mode: 'search' | 'category' | 'brand' }) {
  useThemeOverride('shopping');
  const { slug = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const { toggleCompare } = useShopActions();
  const q = params.get('q') ?? '';

  const query = useMemo(() => {
    const o: Record<string, string> = {};
    params.forEach((v, k) => { if (k !== 'page') o[k] = v; });
    if (mode === 'category') o.category = slug;
    if (mode === 'brand') o.brand = slug;
    return o;
  }, [params, mode, slug]);

  const category = useQuery({ queryKey: ['shop', 'category', slug], queryFn: () => api.shop.category(slug), enabled: mode === 'category' });
  const results = useInfiniteQuery({
    queryKey: ['shop', 'search', query],
    queryFn: ({ pageParam }) => api.shop.search({ ...query, page: pageParam }),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.hasMore ? last.page + 1 : undefined),
    staleTime: 30_000,
  });
  const first = results.data?.pages[0];
  const items = results.data?.pages.flatMap((p) => p.results) ?? [];
  const update = (mutate: (p: URLSearchParams) => void) => {
    const next = new URLSearchParams(params);
    mutate(next);
    next.delete('page');
    setParams(next, { replace: true });
  };
  const sentinel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = sentinel.current;
    if (!el || typeof IntersectionObserver === 'undefined') return;
    const io = new IntersectionObserver((e) => { if (e[0]?.isIntersecting && results.hasNextPage && !results.isFetchingNextPage) results.fetchNextPage(); }, { rootMargin: '500px' });
    io.observe(el);
    return () => io.disconnect();
  }, [results]);
  const activeFilters = [...params.keys()].filter((k) => !['q', 'sort', 'page'].includes(k)).length;
  const onCompare = (p: { id: string; name: string; categorySlug: string | null }) => toggleCompare({ id: p.id, name: p.name, categorySlug: p.categorySlug });
  const brandName = mode === 'brand' ? first?.facets.brands.find((b) => b.slug === slug)?.name ?? first?.results[0]?.brand : undefined;

  return (
    <div className="shop-results" data-theme="shopping">
      <Link to={mode === 'category' && category.data?.parent ? `/shopping/c/${category.data.parent.slug}` : '/shopping'} className="btn btn--ghost btn--sm" style={{ alignSelf: 'flex-start', paddingLeft: 4 }}>
        <Icon name="back" size={18} /> {mode === 'category' && category.data?.parent ? category.data.parent.name : 'Shopping'}
      </Link>

      {mode === 'category' && (category.isPending ? <Skeleton height={88} radius={22} /> : category.data && (
        <>
          <header className="shop-cathead">
            <span className="shop-cathead__icon"><Icon name={(category.data.category.icon || 'bag') as IconName} size={28} /></span>
            <div><h1>{category.data.category.name}</h1>{category.data.category.productCount != null && <p>{category.data.category.productCount} products from Click. sellers</p>}</div>
          </header>
          {(category.data.children.length > 0 || category.data.siblings.length > 0) && (
            <nav className="shop-subcats" aria-label="Subcategories">
              {(category.data.children.length ? category.data.children : category.data.siblings).map((c) => (
                <Link key={c.slug} to={`/shopping/c/${c.slug}`} className="chip" aria-current={c.slug === slug ? 'page' : undefined} aria-pressed={c.slug === slug}>{c.name}</Link>
              ))}
            </nav>
          )}
          {category.data.campaigns.length > 0 && <CampaignHero campaigns={category.data.campaigns} />}
          {category.data.highlight && (
            <section className="shop-sec"><SectionHead title={category.data.highlight.title} /><ProductRail products={category.data.highlight.products} onCompare={onCompare} /></section>
          )}
        </>
      ))}

      {mode === 'search' && (
        <div className="shop-results__head">
          <ShopSearchField initial={q} />
          {first && q && (
            <>
              <h1>{first.count > 0 ? <>Showing results for <span style={{ color: 'var(--c-theme-strong)' }}>“{q}”</span></> : <>No results for “{q}”</>}</h1>
              {first.interpretation && first.interpretation.understood.length > 0 && (
                <div className="shop-results__understood" aria-label="What search understood">
                  Understood: {first.interpretation.understood.map((u) => <span key={u.label} className="shop-chip-info">{u.label}</span>)}
                </div>
              )}
            </>
          )}
          {!q && <h1>All products</h1>}
        </div>
      )}
      {mode === 'brand' && <div className="shop-results__head"><h1>{brandName ?? 'Brand'}</h1><p className="muted small">Products from this brand, sold by Click. sellers.</p></div>}

      {results.isError ? <ErrorState error={results.error} onRetry={() => results.refetch()} /> : (
        <div className="shop-results__body">
          {first && <aside className="shop-filters__aside" aria-label="Filters"><FilterPanel facets={first.facets} params={params} update={update} hideCategories={mode === 'category'} /></aside>}
          <div className="stack" style={{ minWidth: 0 }}>
            <div className="shop-toolbar">
              <Button variant="secondary" size="sm" className="shop-filters__toggle" onClick={() => setFiltersOpen(true)} disabled={!first}>
                <Icon name="filter" size={16} /> Filters{activeFilters ? ` (${activeFilters})` : ''}
              </Button>
              <label className="visually-hidden" htmlFor="shop-sort">Sort by</label>
              <select id="shop-sort" className="shop-select" value={params.get('sort') ?? first?.sort ?? 'popular'} onChange={(e) => update((p) => p.set('sort', e.target.value))}>
                {SORTS.filter((s) => s.id !== 'relevance' || q).map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
              </select>
              {first && <span className="shop-toolbar__count" role="status">{first.count.toLocaleString('en-IN')} result{first.count === 1 ? '' : 's'}</span>}
            </div>
            {results.isPending ? <div className="shop-grid"><CardSkeletons n={8} /></div>
              : items.length === 0 ? (
                <EmptyState icon="search" title="We couldn’t find what you’re looking for."
                  message={first?.correction ? undefined : 'Try fewer filters, another word, or browse the categories.'}
                  action={
                    <div className="row" style={{ flexWrap: 'wrap', justifyContent: 'center' }}>
                      {first?.correction && <Link className="btn btn--primary" to={`/shopping/search?q=${encodeURIComponent(first.correction)}`}>Search “{first.correction}” instead</Link>}
                      {activeFilters > 0 && <Button variant="secondary" onClick={() => update((p) => { [...p.keys()].filter((k) => !['q', 'sort'].includes(k)).forEach((k) => p.delete(k)); })}>Clear filters</Button>}
                      <Link className="btn btn--outline" to="/shopping">Browse categories</Link>
                    </div>
                  } />
              ) : (
                <div className="shop-grid">
                  {items.map((p) => <ShopCard key={p.id} p={p} onCompare={onCompare} />)}
                  {results.isFetchingNextPage && <CardSkeletons n={4} />}
                </div>
              )}
            <div ref={sentinel} className="shop-feed__more">
              {results.hasNextPage && <button type="button" className="btn btn--outline btn--sm" onClick={() => results.fetchNextPage()} disabled={results.isFetchingNextPage}>Load more</button>}
            </div>
          </div>
        </div>
      )}
      <Sheet open={filtersOpen} onClose={() => setFiltersOpen(false)} label="Filters">
        <div className="stack">
          <div className="spread"><h2>Filters</h2><button className="icon-btn" aria-label="Close" onClick={() => setFiltersOpen(false)}><Icon name="close" /></button></div>
          {first && <FilterPanel facets={first.facets} params={params} update={update} hideCategories={mode === 'category'} />}
          <Button block onClick={() => setFiltersOpen(false)} data-theme="shopping">
            {results.isFetching ? 'Updating…' : `Show ${(first?.count ?? 0).toLocaleString('en-IN')} result${first?.count === 1 ? '' : 's'}`}
          </Button>
        </div>
      </Sheet>
      <CompareBar />
    </div>
  );
}
