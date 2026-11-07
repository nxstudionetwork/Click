import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { StoreType } from '@click/api';
import { serviceForStoreType, STORE_TYPE_LABEL } from '../config/services';
import { PageHeader } from '../components/shell/PageHeader';
import { EmptyState, ErrorState, Icon } from '../components/ui';
import { useStoreCategories, useStores } from '../features/stores/hooks';
import { StoreCard, StoreCardSkeleton } from '../features/stores/StoreCard';

/** Discovery for any commerce vertical (Food, Groceries, Shopping) on the shared catalogue. */
export function StoreBrowsePage({ storeType }: { storeType: StoreType }) {
  const service = serviceForStoreType(storeType);
  const label = STORE_TYPE_LABEL[storeType];
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

  const categories = useStoreCategories(storeType);
  const stores = useStores({ type: storeType, search: search || undefined, category: category || undefined, open: open || undefined });
  const hasFilters = !!(search || category || open);

  return (
    <div className="stack">
      <PageHeader band title={service.name} subtitle={service.tagline} back={{ to: '/', label: 'Home' }} />
      <div className="search" role="search">
        <Icon name="search" />
        <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder={`Search ${label.plural}`} aria-label={`Search ${service.name}`} />
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
          title={hasFilters ? 'No matches' : `No ${label.plural} yet`}
          message={hasFilters ? 'Try a different search or remove a filter.' : `${label.plural[0]!.toUpperCase()}${label.plural.slice(1)} will appear here as they join Click.`}
          action={hasFilters && <button className="btn btn--outline" onClick={() => { setDraft(''); setParams({}, { replace: true }); }}>Clear filters</button>}
        />
      ) : (
        <>
          <p className="muted small" aria-live="polite">{stores.data.count} {stores.data.count === 1 ? label.singular : label.plural}</p>
          <div className="store-grid" style={{ opacity: stores.isPlaceholderData ? 0.6 : 1 }}>
            {stores.data.results.map((s) => <StoreCard key={s.id} store={s} />)}
          </div>
        </>
      )}
    </div>
  );
}
