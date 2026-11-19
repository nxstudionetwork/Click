import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Icon, type IconName } from '@click/ui';
import { api } from '../lib/api';
import { useOS } from '../session/OSSession';

interface Item { key: string; group: string; title: string; subtitle?: string; icon: IconName; path: string }

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}

/** Global search + jump-to. Results come from the server's permission-filtered search: nothing restricted can appear. */
export function CommandPalette({ onClose }: { onClose: () => void }) {
  const ctx = useOS();
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const [active, setActive] = useState(0);
  const term = useDebounced(q.trim(), 200);

  const search = useQuery({
    queryKey: ['os', 'search', term], queryFn: ({ signal }) => api.search(term, undefined, signal), enabled: term.length >= 2, staleTime: 15_000,
  });

  const items = useMemo<Item[]>(() => {
    const lower = term.toLowerCase();
    const pages: Item[] = ctx.navigation.flatMap((g) => g.items).filter((i) => !lower || i.label.toLowerCase().includes(lower))
      .slice(0, lower ? 5 : 8).map((i) => ({ key: `nav:${i.key}`, group: 'Go to', title: i.label, icon: i.icon as IconName, path: i.path }));
    const actions: Item[] = ctx.quickActions.filter((a) => !lower || a.label.toLowerCase().includes(lower))
      .slice(0, 4).map((a) => ({ key: `qa:${a.key}`, group: 'Actions', title: a.label, icon: a.icon as IconName, path: a.path }));
    const results: Item[] = term.length >= 2 ? (search.data?.groups ?? []).flatMap((g) =>
      g.results.map((r) => ({ key: `${g.type}:${r.id}`, group: g.label, title: r.title, subtitle: r.subtitle, icon: 'search' as IconName, path: r.path }))) : [];
    return [...results, ...actions, ...pages];
  }, [ctx, term, search.data]);

  useEffect(() => setActive(0), [term]);

  const go = (it?: Item) => {
    if (!it) {
      if (term.length >= 2) { navigate(`/search?q=${encodeURIComponent(term)}`); onClose(); }
      return;
    }
    navigate(it.path);
    onClose();
  };

  let lastGroup = '';
  return (
    <div className="overlay overlay--center" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Search Business OS">
        <div className="palette__input">
          <Icon name="search" size={18} />
          <input
            autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search people, approvals, tasks, pages…" aria-label="Search"
            role="combobox" aria-expanded="true" aria-controls="palette-list" aria-activedescendant={items[active] ? `pi-${active}` : undefined}
            onKeyDown={(e) => {
              if (e.key === 'Escape') onClose();
              else if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, items.length - 1)); }
              else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
              else if (e.key === 'Enter') { e.preventDefault(); go(items[active]); }
            }}
          />
          {search.isFetching && <span className="btn__spinner" style={{ color: 'var(--c-ink-3)' }} />}
        </div>
        <div className="palette__list" id="palette-list" role="listbox">
          {items.length === 0 && <p className="muted small" style={{ padding: 16 }}>{term.length >= 2 && !search.isFetching ? 'Nothing you have access to matches that.' : 'Type at least 2 characters.'}</p>}
          {items.map((it, i) => {
            const header = it.group !== lastGroup ? <div className="palette__group">{it.group}</div> : null;
            lastGroup = it.group;
            return (
              <div key={it.key}>
                {header}
                <button id={`pi-${i}`} role="option" aria-selected={i === active} className="palette__item" onMouseEnter={() => setActive(i)} onClick={() => go(it)}>
                  <Icon name={it.icon} size={16} />
                  <span className="grow ellipsis">{it.title}{it.subtitle && <><br /><small>{it.subtitle}</small></>}</span>
                </button>
              </div>
            );
          })}
        </div>
        <div className="palette__foot"><span>↑↓ to move</span><span>Enter to open</span><span>Esc to close</span></div>
      </div>
    </div>
  );
}
