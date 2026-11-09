import { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { ErrorState, Icon, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { useBuzz } from '../features/buzz/useBuzz';
import { CampaignHero, CategoryTiles, CompareBar, RailSkeleton, Section, SectionHead } from '../features/shop/ShopBlocks';
import { CardSkeletons, ShopCard } from '../features/shop/ShopCard';
import { ShopSearchField } from '../features/shop/ShopSearch';
import { useShopActions } from '../features/shop/useShopActions';
import { api } from '../lib/api';

/**
 * Click. Shopping home: a marketplace entrance (title, backend campaigns, search), visual categories, then only the
 * sections the backend has real content for (deals, personal picks, trending, best sellers, price bands, new
 * arrivals, brands, buy again…), an endless discovery feed and shoppable Buzz. Never a padded or empty section.
 */
export function ShoppingPage() {
  useThemeOverride('shopping');
  const home = useQuery({ queryKey: ['shop', 'home'], queryFn: api.shop.home, staleTime: 60_000 });
  const { toggleCompare } = useShopActions();
  const onCompare = (p: { id: string; name: string; categorySlug: string | null }) => toggleCompare({ id: p.id, name: p.name, categorySlug: p.categorySlug });

  return (
    <div className="shop" data-theme="shopping">
      <div className="shop-top">
        <div className="shop-intro">
          <h1>Shopping</h1>
          <p>Everything you want. One Click. away.</p>
        </div>
        {home.isPending ? <Skeleton height={190} radius={18} /> : <CampaignHero campaigns={home.data?.campaigns ?? []} />}
        <ShopSearchField />
      </div>

      {home.isError ? <ErrorState error={home.error} onRetry={() => home.refetch()} /> : (
        <>
          <section className="shop-sec" aria-label="Shop by Category">
            <SectionHead title="Shop by Category" />
            {home.isPending ? <div className="shop-cats">{Array.from({ length: 8 }, (_, i) => <Skeleton key={i} height={96} radius={18} />)}</div>
              : <CategoryTiles categories={home.data.categories} />}
          </section>
          {home.isPending ? <><RailSkeleton /><RailSkeleton /></> : home.data.sections.map((s) => <Section key={s.id} s={s} onCompare={onCompare} />)}
          <ShoppableBuzz />
          <DiscoveryFeed onCompare={onCompare} personalHint={home.data?.personalized ?? false} />
        </>
      )}
      <CompareBar />
    </div>
  );
}

function ShoppableBuzz() {
  const buzz = useBuzz(30);
  const items = (buzz.data?.results ?? []).filter((b) => b.kind === 'product');
  if (items.length < 2) return null;
  return (
    <section className="shop-sec" aria-label="From Click. Buzz">
      <SectionHead title="From Click. Buzz" subtitle="Deals and finds from sellers. Tap to view the product." link="/buzz" linkLabel="Open Buzz" />
      <div className="shop-buzz">
        {items.slice(0, 8).map((b) => (
          <Link key={b.id} to={b.action.path} className="shop-buzz__item">
            <span className="shop-buzz__tag">{b.tag}</span>
            <span className="shop-buzz__title">{b.title}</span>
            <span className="shop-buzz__body">{b.body}</span>
            <span className="shop-sec__link" style={{ color: '#fff' }}>{b.action.label} <Icon name="right" size={14} /></span>
          </Link>
        ))}
      </div>
    </section>
  );
}

function DiscoveryFeed({ onCompare, personalHint }: { onCompare: (p: { id: string; name: string; categorySlug: string | null }) => void; personalHint: boolean }) {
  const feed = useInfiniteQuery({
    queryKey: ['shop', 'feed'],
    queryFn: ({ pageParam }) => api.shop.feed(pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.nextCursor,
    staleTime: 60_000,
  });
  const sentinel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = sentinel.current;
    if (!el || typeof IntersectionObserver === 'undefined') return;
    const io = new IntersectionObserver((e) => { if (e[0]?.isIntersecting && feed.hasNextPage && !feed.isFetchingNextPage) feed.fetchNextPage(); }, { rootMargin: '600px' });
    io.observe(el);
    return () => io.disconnect();
  }, [feed]);
  const items = feed.data?.pages.flatMap((p) => p.results) ?? [];
  return (
    <section className="shop-sec" aria-label="Product feed">
      <SectionHead title={personalHint ? 'More for You' : 'Discover More'}
        subtitle={personalHint ? 'Ordered by what you browse, save and buy.' : 'Popular picks across Click. Shopping.'} />
      {feed.isError ? <ErrorState error={feed.error} onRetry={() => feed.refetch()} /> : (
        <div className="shop-grid">
          {items.map((p) => <ShopCard key={p.id} p={p} onCompare={onCompare} />)}
          {(feed.isPending || feed.isFetchingNextPage) && <CardSkeletons n={4} />}
        </div>
      )}
      <div ref={sentinel} className="shop-feed__more">
        {feed.hasNextPage ? <button type="button" className="btn btn--outline btn--sm" onClick={() => feed.fetchNextPage()} disabled={feed.isFetchingNextPage}>Load more</button>
          : items.length > 0 && <span>You’ve seen everything for now.</span>}
      </div>
    </section>
  );
}
