import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { EmptyState, ErrorState, Icon } from '../components/ui';
import { useStoreCategories, useStores } from '../features/stores/hooks';
import { StoreCard, StoreCardSkeleton } from '../features/stores/StoreCard';

export function FoodPage() {
  const [params, setParams] = useSearchParams();
  const search = params.get('search') ?? '';
  const category = params.get('category') ?? '';
  const open = params.get('open') === 'true';
  const [draft, setDraft] = useState(search);

  // Debounce typing into the URL (the URL is the source of truth for filters).
  // Only write when the draft really differs, so it never clobbers other filter changes.
  useEffect(() => {
    if (draft.trim() === search) return;
    const t = setTimeout(() => update('search', draft.trim()), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, search]);

  function update(key: string, value: string) {
    setParams((p) => {
      const next = new URLSearchParams(p);
      if (value) next.set(key, value);
      else next.delete(key);
      return next;
    }, { replace: true });
  }

  const categories = useStoreCategories('restaurant');
  const stores = useStores({ type: 'restaurant', search: search || undefined, category: category || undefined, open: open || undefined });
  const hasFilters = !!(search || category || open);

  return (
    <div className="stack">
      <h1>Food</h1>
      <div className="search" role="search">
        <Icon name="search" />
        <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Search restaurants, cuisines or dishes" aria-label="Search food" />
        {draft && <button className="icon-btn" onClick={() => setDraft('')} aria-label="Clear search"><Icon name="close" size={18} /></button>}
      </div>
      <div className="chips" aria-label="Filters">
        <button className="chip" aria-pressed={open} onClick={() => update('open', open ? '' : 'true')}>Open now</button>
        {categories.data?.map((c) => (
          <button key={c.id} className="chip" aria-pressed={category === c.slug} onClick={() => update('category', category === c.slug ? '' : c.slug)}>
            {c.name}
          </button>
        ))}
      </div>

      {stores.isError ? (
        <ErrorState error={stores.error} onRetry={() => stores.refetch()} />
      ) : stores.isPending ? (
        <div className="store-grid">{Array.from({ length: 6 }, (_, i) => <StoreCardSkeleton key={i} />)}</div>
      ) : stores.data.results.length === 0 ? (
        <EmptyState
          title={hasFilters ? 'No matches' : 'No restaurants yet'}
          message={hasFilters ? 'Try a different search or remove a filter.' : 'Restaurants near you will appear here.'}
          action={hasFilters && <button className="btn btn--outline" onClick={() => { setDraft(''); setParams({}, { replace: true }); }}>Clear filters</button>}
        />
      ) : (
        <>
          <p className="muted small" aria-live="polite">{stores.data.count} restaurant{stores.data.count === 1 ? '' : 's'}</p>
          <div className="store-grid" style={{ opacity: stores.isPlaceholderData ? 0.6 : 1 }}>
            {stores.data.results.map((s) => <StoreCard key={s.id} store={s} />)}
          </div>
        </>
      )}
    </div>
  );
}
