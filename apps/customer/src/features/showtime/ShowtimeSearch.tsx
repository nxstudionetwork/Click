import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Icon, Sheet, type IconName } from '../../components/ui';
import { api } from '../../lib/api';

const KEY = 'click.showtimeRecentSearches';
const recent = (): string[] => {
  try { const v = JSON.parse(localStorage.getItem(KEY) ?? '[]'); return Array.isArray(v) ? v.filter((x) => typeof x === 'string').slice(0, 6) : []; } catch { return []; }
};
const remember = (q: string) => {
  try { localStorage.setItem(KEY, JSON.stringify([q, ...recent().filter((r) => r.toLowerCase() !== q.toLowerCase())].slice(0, 6))); } catch { /* storage unavailable */ }
};
const KIND: Record<string, { icon: IconName; label: string }> = {
  title: { icon: 'film', label: 'Show' }, title_language: { icon: 'film', label: 'Language' }, cinema: { icon: 'pin', label: 'Cinema' }, person: { icon: 'user', label: 'Cast & crew' },
};

export function ShowtimeSearchField({ initial = '' }: { initial?: string }) {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  return (
    <>
      <div className="st-search" role="search">
        <Icon name="search" size={20} />
        <button type="button" className="st-search__input" onClick={() => setOpen(true)} aria-label="Search shows, cinemas, actors & more">
          <span style={initial ? { color: 'var(--c-ink)' } : undefined}>{initial || 'Search shows, cinemas, actors & more'}</span>
        </button>
        <button type="button" className="st-search__tool" aria-label="Ask Buddy what to watch" onClick={() => navigate('/buddy?q=What%20should%20I%20watch%20tonight%3F')}>
          <Icon name="sparkle" size={18} />
        </button>
      </div>
      <ShowtimeSearchPanel open={open} onClose={() => setOpen(false)} initial={initial} />
    </>
  );
}

function ShowtimeSearchPanel({ open, onClose, initial }: { open: boolean; onClose: () => void; initial: string }) {
  const navigate = useNavigate();
  const [q, setQ] = useState(initial);
  const [debounced, setDebounced] = useState('');
  const [recents, setRecents] = useState<string[]>([]);
  useEffect(() => { if (open) { setQ(initial); setRecents(recent()); } }, [open, initial]);
  useEffect(() => { const t = setTimeout(() => setDebounced(q.trim()), 220); return () => clearTimeout(t); }, [q]);
  const s = useQuery({ queryKey: ['showtime', 'suggest', debounced], queryFn: () => api.showtime.suggest(debounced), enabled: open, staleTime: 60_000 });
  const go = (text: string) => {
    const t = text.trim();
    if (!t) return;
    remember(t);
    onClose();
    navigate(`/showtime/search?q=${encodeURIComponent(t)}`);
  };
  const open_ = (path: string) => { onClose(); navigate(path); };
  return (
    <Sheet open={open} onClose={onClose} label="Search Showtime" variant="full">
      <form className="st-panel st-page" style={{ gap: 'var(--s-4)', paddingBottom: 'var(--s-4)' }} onSubmit={(e) => { e.preventDefault(); go(q); }}>
        <div className="st-panel__bar">
          <Icon name="search" size={20} />
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search shows, cinemas, actors & more" aria-label="Search Showtime" enterKeyHint="search" />
          <button type="button" className="icon-btn" aria-label="Close search" onClick={onClose}><Icon name="close" size={18} /></button>
        </div>
        {debounced.length >= 2 ? (
          <section>
            <h3>Suggestions</h3>
            <button type="button" className="st-panel__row" onClick={() => go(q)}><Icon name="search" size={16} /> Search “{q.trim()}”</button>
            {(s.data?.suggestions ?? []).map((x) => (
              <button key={`${x.kind}-${x.text}`} type="button" className="st-panel__row" onClick={() => open_(x.path)}>
                <Icon name={KIND[x.kind]?.icon ?? 'search'} size={16} /> {x.text}<small>{KIND[x.kind]?.label}</small>
              </button>
            ))}
            {s.isSuccess && s.data.suggestions.length === 0 && <p className="small muted" style={{ marginTop: 8 }}>No matching shows, cinemas or people yet. Press search to look everywhere.</p>}
          </section>
        ) : (
          <>
            {recents.length > 0 && (
              <section><h3>Recent searches</h3><div className="chips">{recents.map((r) => <button key={r} type="button" className="chip" onClick={() => go(r)}><Icon name="history" size={14} /> {r}</button>)}</div></section>
            )}
            {(s.data?.trending.length ?? 0) > 0 && (
              <section><h3>Trending searches</h3><div className="chips">{s.data!.trending.map((t) => <button key={t} type="button" className="chip" onClick={() => go(t)}>{t}</button>)}</div></section>
            )}
            {(s.data?.popular.length ?? 0) > 0 && (
              <section><h3>Popular shows</h3>{s.data!.popular.map((p) => (
                <button key={p.slug} type="button" className="st-panel__row" onClick={() => open_(`/showtime/${p.slug}`)}><Icon name="film" size={16} /> {p.title}</button>))}
              </section>
            )}
            <section>
              <h3>Try</h3>
              <div className="chips">{['comedy tonight', 'IMAX near me', 'Telugu shows', 'live music this weekend'].map((t) => <button key={t} type="button" className="chip" onClick={() => go(t)}>{t}</button>)}</div>
              <p className="small muted" style={{ marginTop: 8 }}>Search understands languages, genres, formats (IMAX, 4DX, 3D), “tonight” or “this weekend” and “near me”, and shows what it understood.</p>
            </section>
          </>
        )}
      </form>
    </Sheet>
  );
}
