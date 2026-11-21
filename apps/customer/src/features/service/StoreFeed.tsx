import { useEffect, useRef } from 'react';
import { keepPreviousData, useInfiniteQuery } from '@tanstack/react-query';
import type { StoreQuery } from '@click/api';
import { EmptyState, ErrorState } from '../../components/ui';
import { storesSource } from '../../data/stores-source';
import { StoreCard, StoreCardSkeleton } from '../stores/StoreCard';

/** Paged store list (20 per page from the API), loading more as the customer scrolls. */
export function useStoreFeed(query: StoreQuery) {
  return useInfiniteQuery({
    queryKey: ['stores', 'feed', query],
    queryFn: ({ pageParam }) => storesSource.list({ ...query, page: pageParam }),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.hasNext ? last.page + 1 : undefined),
    placeholderData: keepPreviousData,
  });
}

export function StoreFeed({ query, plural, empty }: { query: StoreQuery; plural: string; empty: { title: string; message: string; action?: React.ReactNode } }) {
  const feed = useStoreFeed(query);
  const sentinel = useRef<HTMLDivElement>(null);
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = feed;

  useEffect(() => {
    const el = sentinel.current;
    if (!el || !hasNextPage || typeof IntersectionObserver === 'undefined') return;
    const io = new IntersectionObserver((entries) => { if (entries[0]?.isIntersecting && !isFetchingNextPage) fetchNextPage(); }, { rootMargin: '600px' });
    io.observe(el);
    return () => io.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  if (feed.isError) return <ErrorState error={feed.error} onRetry={() => feed.refetch()} />;
  if (feed.isPending) return <div className="store-grid" aria-busy="true">{Array.from({ length: 6 }, (_, i) => <StoreCardSkeleton key={i} />)}</div>;
  const stores = feed.data.pages.flatMap((p) => p.results);
  const count = feed.data.pages[0]?.count ?? 0;
  if (stores.length === 0) return <EmptyState icon="food" title={empty.title} message={empty.message} action={empty.action} />;

  return (
    <>
      <p className="muted small" aria-live="polite">{count} {count === 1 ? plural.replace(/s$/, '') : plural}</p>
      <div className="store-grid" style={{ opacity: feed.isPlaceholderData ? 0.6 : 1 }}>
        {stores.map((s) => <StoreCard key={s.id} store={s} />)}
        {isFetchingNextPage && Array.from({ length: 3 }, (_, i) => <StoreCardSkeleton key={`more-${i}`} />)}
      </div>
      <div ref={sentinel} aria-hidden="true" />
      {hasNextPage && !isFetchingNextPage && (
        <button className="btn btn--outline" style={{ alignSelf: 'center' }} onClick={() => fetchNextPage()}>Load more {plural}</button>
      )}
    </>
  );
}
