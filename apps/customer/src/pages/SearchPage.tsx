import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import type { SearchScope } from '@click/api';
import { EmptyState, ErrorState, Icon, Skeleton } from '../components/ui';
import { SERVICES } from '../config/services';
import { ProductCard } from '../features/stores/ProductCard';
import { StoreCard } from '../features/stores/StoreCard';
import { EventCard } from '../features/bookings/EventCard';
import { api } from '../lib/api';

const SCOPES: { id: SearchScope; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'restaurant', label: 'Food' },
  { id: 'grocery', label: 'Groceries' },
  { id: 'retail', label: 'Shopping' },
  { id: 'products', label: 'Products & dishes' },
  { id: 'events', label: 'Movies & events' },
];
const RECENT_KEY = 'click.recentSearches';

function readRecent(): string[] {
  try { return JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]'); } catch { return []; }
}
function saveRecent(list: string[]) {
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(list)); } catch { /* ignore */ }
}

export function SearchPage() {
  const [params, setParams] = useSearchParams();
  const q = params.get('q') ?? '';
  const scope = (SCOPES.find((s) => s.id === params.get('scope'))?.id ?? 'all') as SearchScope;
  const [draft, setDraft] = useState(q);
  const [recent, setRecent] = useState<string[]>(readRecent);

  const set = (next: { q?: string; scope?: string }) =>
    setParams((p) => {
      const n = new URLSearchParams(p);
      for (const [k, v] of Object.entries(next)) (v ? n.set(k, v) : n.delete(k));
      return n;
    }, { replace: true });

  // Sync the input only when the URL query changes externally (back/forward), never on mount,
  // so text typed immediately after navigating here is not wiped.
  const lastQ = useRef(q);
  useEffect(() => {
    if (lastQ.current === q) return;
    lastQ.current = q;
    setDraft((d) => (d.trim() === q ? d : q));
  }, [q]);
  useEffect(() => {
    if (draft.trim() === q) return;
    const t = setTimeout(() => set({ q: draft.trim() }), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, q]);

  const active = q.length >= 2;
  const results = useQuery({
    queryKey: ['search', q, scope],
    queryFn: ({ signal }) => api.catalog.search(q, scope, signal),
    enabled: active,
    placeholderData: keepPreviousData,
  });

  useEffect(() => {
    if (results.isSuccess && active && (results.data.stores.length || results.data.products.length || results.data.events.length)) {
      setRecent((r) => {
        const next = [q, ...r.filter((x) => x.toLowerCase() !== q.toLowerCase())].slice(0, 8);
        saveRecent(next);
        return next;
      });
    }
  }, [results.isSuccess, results.data, q, active]);

  return (
    <div className="stack">
      <div className="search search-big" role="search">
        <Icon name="search" />
        <input autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Search restaurants, dishes, groceries, products, movies…" aria-label="Search Click" />
        {draft && <button className="icon-btn" onClick={() => setDraft('')} aria-label="Clear search"><Icon name="close" size={18} /></button>}
      </div>
      <div className="tabs" role="tablist" aria-label="Search category">
        {SCOPES.map((s) => (
          <button key={s.id} role="tab" aria-selected={scope === s.id} onClick={() => set({ scope: s.id === 'all' ? '' : s.id })}>{s.label}</button>
        ))}
      </div>

      {!active ? (
        <div className="stack">
          {recent.length > 0 && (
            <section className="stack" style={{ gap: 'var(--s-2)' }}>
              <div className="spread"><h3>Recent searches</h3><button className="btn btn--ghost btn--sm" onClick={() => { setRecent([]); saveRecent([]); }}>Clear</button></div>
              <div className="chips" style={{ flexWrap: 'wrap' }}>{recent.map((r) => <button key={r} className="chip" onClick={() => setDraft(r)}>{r}</button>)}</div>
            </section>
          )}
          <section className="stack" style={{ gap: 'var(--s-2)' }}>
            <h3>Browse</h3>
            <div className="chips" style={{ flexWrap: 'wrap' }}>
              {SERVICES.filter((s) => s.status === 'live').map((s) => <Link key={s.id} to={s.path} className="chip" style={{ display: 'inline-flex', alignItems: 'center' }}>{s.name}</Link>)}
            </div>
          </section>
          {q.length === 1 && <p className="muted small">Type at least 2 characters to search.</p>}
        </div>
      ) : results.isError ? (
        <ErrorState error={results.error} onRetry={() => results.refetch()} />
      ) : results.isPending ? (
        <div className="stack">{Array.from({ length: 3 }, (_, i) => <Skeleton key={i} height={80} radius={16} />)}</div>
      ) : results.data.stores.length + results.data.products.length + results.data.events.length === 0 ? (
        <EmptyState title={`No results for “${q}”`} message="Check the spelling or try a broader term." />
      ) : (
        <div className="stack" style={{ opacity: results.isPlaceholderData ? 0.6 : 1 }}>
          {results.data.stores.length > 0 && (
            <section className="stack">
              <h2>Stores <span className="muted small">({results.data.stores.length})</span></h2>
              <div className="store-grid">{results.data.stores.map((s) => <StoreCard key={s.id} store={s} />)}</div>
            </section>
          )}
          {results.data.events.length > 0 && (
            <section className="stack" data-theme="movies">
              <h2>Movies & events <span className="muted small">({results.data.events.length})</span></h2>
              <div className="event-grid">{results.data.events.map((e) => <EventCard key={e.id} event={e} />)}</div>
            </section>
          )}
          {results.data.products.length > 0 && (
            <section className="stack">
              <h2>Products & dishes <span className="muted small">({results.data.products.length})</span></h2>
              <div className="product-grid">{results.data.products.map((p) => <ProductCard key={p.id} product={p} currency={p.store.currency} showStore />)}</div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
