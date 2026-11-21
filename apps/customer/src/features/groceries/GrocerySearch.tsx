import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthProvider';
import { Icon } from '../../components/ui';
import { api } from '../../lib/api';
import { formatMoney } from '../../lib/format';
import { GroceryImage } from './parts';
import { localRecent, rememberLocal, useGroceryAt } from './useGroceries';

/** One grocery search: products, brands, stores and categories, all from the backend for the selected location. */
export function GrocerySearchField({ initial = '', autoFocus = false }: { initial?: string; autoFocus?: boolean }) {
  const [q, setQ] = useState(initial);
  const [open, setOpen] = useState(false);
  const [debounced, setDebounced] = useState(initial);
  const navigate = useNavigate();
  const { status } = useAuth();
  const { at, key } = useGroceryAt();
  const qc = useQueryClient();
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => { const t = setTimeout(() => setDebounced(q.trim()), 220); return () => clearTimeout(t); }, [q]);
  useEffect(() => {
    const close = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);
  const panel = useQuery({ queryKey: ['groceries', 'suggest', debounced, key, status], queryFn: () => api.groceries.suggest(debounced, at), enabled: open, staleTime: 30_000 });
  const go = (text: string) => {
    const t = text.trim();
    if (!t) return;
    if (status !== 'authenticated') rememberLocal(t);
    setOpen(false);
    navigate(`/groceries/search?q=${encodeURIComponent(t)}`);
  };
  const recent = status === 'authenticated' ? panel.data?.recent ?? [] : localRecent();
  const d = panel.data;

  return (
    <div className="gr-search" ref={box}>
      <form role="search" className="gr-search__field" onSubmit={(e) => { e.preventDefault(); go(q); }}>
        <Icon name="search" />
        <input value={q} onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} autoFocus={autoFocus}
          placeholder="Search groceries, stores & brands" aria-label="Search groceries, stores and brands" enterKeyHint="search"
          onKeyDown={(e) => { if (e.key === 'Escape') setOpen(false); }} />
        {q && <button type="button" className="gr-search__clear" aria-label="Clear search" onClick={() => { setQ(''); setDebounced(''); }}><Icon name="close" size={16} /></button>}
      </form>
      {open && (
        <div className="gr-search__panel" role="listbox" aria-label="Search suggestions">
          {!debounced ? (
            <>
              {recent.length > 0 && (
                <div className="gr-search__group">
                  <div className="spread"><span className="gr-search__label">Recent searches</span>
                    {status === 'authenticated' && <button type="button" className="link-btn small" onClick={async () => { await api.groceries.clearRecent(); qc.invalidateQueries({ queryKey: ['groceries', 'suggest'] }); }}>Clear</button>}
                  </div>
                  <div className="gr-chips">{recent.map((r) => <button key={r} type="button" className="chip" onClick={() => go(r)}><Icon name="history" size={14} /> {r}</button>)}</div>
                </div>
              )}
              {(d?.popular?.length ?? 0) > 0 && (
                <div className="gr-search__group">
                  <span className="gr-search__label">Popular near you</span>
                  <div className="gr-chips">{d!.popular!.map((r) => <button key={r} type="button" className="chip" onClick={() => go(r)}>{r}</button>)}</div>
                </div>
              )}
              {!recent.length && !d?.popular?.length && <p className="small muted gr-search__hint">Try “milk”, “rice”, “vegetables” or a store name.</p>}
            </>
          ) : panel.isPending ? <p className="small muted gr-search__hint">Searching…</p> : (
            <>
              {(d?.products?.length ?? 0) > 0 && (
                <div className="gr-search__group">
                  <span className="gr-search__label">Products</span>
                  {d!.products!.map((p) => (
                    <Link key={p.id} to={`/groceries/p/${p.id}`} className="gr-search__row" onClick={() => setOpen(false)}>
                      <span className="gr-search__thumb"><GroceryImage l={p} /></span>
                      <span className="gr-search__text"><strong>{p.brand ? `${p.brand} ` : ''}{p.name}</strong><span className="small muted">{p.size} · {p.store.name}</span></span>
                      <span className="small">{formatMoney(p.price)}</span>
                    </Link>
                  ))}
                </div>
              )}
              {(d?.stores?.length ?? 0) > 0 && (
                <div className="gr-search__group">
                  <span className="gr-search__label">Stores</span>
                  {d!.stores!.map((s) => (
                    <Link key={s.id} to={`/groceries/store/${s.slug}`} className="gr-search__row" onClick={() => setOpen(false)}>
                      <span className="gr-search__thumb gr-search__thumb--store"><Icon name="store" size={18} /></span>
                      <span className="gr-search__text"><strong>{s.name}</strong><span className="small muted">{s.status.label}{s.etaLabel ? ` · ${s.etaLabel}` : ''}</span></span>
                    </Link>
                  ))}
                </div>
              )}
              {((d?.brands?.length ?? 0) > 0 || (d?.categories?.length ?? 0) > 0) && (
                <div className="gr-search__group">
                  <span className="gr-search__label">Brands & categories</span>
                  <div className="gr-chips">
                    {d!.categories?.map((c) => <Link key={c.slug} className="chip" to={`/groceries/search?category=${c.slug}`} onClick={() => setOpen(false)}>{c.name}</Link>)}
                    {d!.brands?.map((b) => <Link key={b} className="chip" to={`/groceries/search?brand=${encodeURIComponent(b)}`} onClick={() => setOpen(false)}>{b}</Link>)}
                  </div>
                </div>
              )}
              {!d?.products?.length && !d?.stores?.length && !d?.brands?.length && !d?.categories?.length && (
                <p className="small muted gr-search__hint">Nothing nearby matches “{debounced}”. Press Enter to search all results.</p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
