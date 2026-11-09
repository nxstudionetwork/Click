import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ApiError } from '@click/api';
import { useAuth } from '../../auth/AuthProvider';
import { Icon, Sheet, type IconName } from '../../components/ui';
import { api } from '../../lib/api';
import { useCapabilities } from '../assist/useCapabilities';
import { useRecorder } from '../assist/useRecorder';

const RECENT_KEY = 'click.shopRecentSearches';

function recent(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]');
    return Array.isArray(v) ? v.filter((s): s is string => typeof s === 'string').slice(0, 6) : [];
  } catch { return []; }
}
export function rememberShopSearch(q: string) {
  const t = q.trim();
  if (!t) return;
  try { localStorage.setItem(RECENT_KEY, JSON.stringify([t, ...recent().filter((s) => s.toLowerCase() !== t.toLowerCase())].slice(0, 6))); } catch { /* storage unavailable */ }
}

const KIND_ICON: Record<string, IconName> = { category: 'compass', brand: 'tag', product: 'search' };

/** The Shopping search field: a large entry that opens the full search panel. */
export function ShopSearchField({ initial = '' }: { initial?: string }) {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  return (
    <>
      <div className="shop-search" role="search">
        <Icon name="search" size={20} />
        <button type="button" className="shop-search__input" onClick={() => setOpen(true)} aria-label="Search products, brands & categories">
          <span className={initial ? '' : 'shop-search__placeholder'}>{initial || 'Search products, brands & categories'}</span>
        </button>
        <button type="button" className="shop-search__tool shop-search__tool--buddy" aria-label="Ask Buddy to find something" onClick={() => navigate('/buddy')}>
          <Icon name="sparkle" size={18} />
        </button>
      </div>
      <ShopSearchPanel open={open} onClose={() => setOpen(false)} initial={initial} />
    </>
  );
}

export function ShopSearchPanel({ open, onClose, initial = '' }: { open: boolean; onClose: () => void; initial?: string }) {
  const navigate = useNavigate();
  const { status } = useAuth();
  const caps = useCapabilities();
  const [q, setQ] = useState(initial);
  const [debounced, setDebounced] = useState('');
  const [note, setNote] = useState<string | null>(null);
  const [recents, setRecents] = useState<string[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);
  useEffect(() => { if (open) { setQ(initial); setRecents(recent()); setNote(null); } }, [open, initial]);
  useEffect(() => { const t = setTimeout(() => setDebounced(q.trim()), 220); return () => clearTimeout(t); }, [q]);
  const sugg = useQuery({ queryKey: ['shop', 'suggest', debounced], queryFn: () => api.shop.suggest(debounced), enabled: open, staleTime: 60_000 });

  const go = (text: string) => {
    const t = text.trim();
    if (!t) return;
    rememberShopSearch(t);
    onClose();
    navigate(`/shopping/search?q=${encodeURIComponent(t)}`);
  };

  const voiceOn = status === 'authenticated' && caps.data?.voice === true;
  const visualOn = status === 'authenticated' && caps.data?.visualSearch === true;
  const transcribe = useMutation({ mutationFn: (audio: Blob) => api.customer.assistant.transcribe(audio), onSuccess: (r) => r.text && go(r.text),
    onError: () => setNote('Couldn’t hear that clearly. Try again or type instead.') });
  const rec = useRecorder((audio) => transcribe.mutate(audio));
  const visual = useMutation({ mutationFn: (f: File) => api.shop.visualSearch(f), onSuccess: (r) => go(r.query),
    onError: (e) => setNote(e instanceof ApiError ? e.message : 'Image search didn’t work. Search by text instead.') });

  return (
    <Sheet open={open} onClose={onClose} label="Search Shopping" variant="full">
      <form className="ssearch" data-theme="shopping" onSubmit={(e) => { e.preventDefault(); go(q); }}>
        <div className="ssearch__bar">
          <Icon name="search" size={20} />
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search products, brands & categories" aria-label="Search Shopping" enterKeyHint="search" />
          {q && <button type="button" className="shop-search__tool" aria-label="Clear" onClick={() => setQ('')}><Icon name="close" size={16} /></button>}
          {voiceOn && (
            <button type="button" className="shop-search__tool" aria-label={rec.state === 'listening' ? 'Stop listening' : 'Search by voice'} aria-pressed={rec.state === 'listening'}
              onClick={() => (rec.state === 'listening' ? rec.stop() : rec.start())}><Icon name="mic" size={18} /></button>
          )}
          {visualOn && (
            <>
              <button type="button" className="shop-search__tool" aria-label="Search with a photo" onClick={() => fileRef.current?.click()}><Icon name="camera" size={18} /></button>
              <input ref={fileRef} type="file" accept="image/*" capture="environment" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) visual.mutate(f); }} />
            </>
          )}
          <button type="button" className="shop-search__tool" aria-label="Close search" onClick={onClose}><Icon name="close" size={18} /></button>
        </div>
        {rec.state === 'listening' && <p className="ssearch__note" role="status">Listening… speak your search.</p>}
        {(transcribe.isPending || visual.isPending) && <p className="ssearch__note" role="status">Working on it…</p>}
        {note && <p className="loc-warn" role="alert">{note}</p>}
        {status === 'authenticated' && caps.isSuccess && !voiceOn && <p className="ssearch__note">Voice search isn’t switched on for Click. yet, so type your search.</p>}

        {debounced.length >= 2 ? (
          <section>
            <h3>Suggestions</h3>
            <div className="ssearch__list">
              <button type="button" className="ssearch__row" onClick={() => go(q)}><Icon name="search" size={16} /> Search “{q.trim()}”</button>
              {(sugg.data?.suggestions ?? []).map((s) => (
                <button key={`${s.kind}-${s.text}`} type="button" className="ssearch__row"
                  onClick={() => { if (s.path) { onClose(); navigate(s.path); } else go(s.text); }}>
                  <Icon name={KIND_ICON[s.kind] ?? 'search'} size={16} /> {s.text} <span className="muted">{s.kind === 'product' ? '' : s.kind === 'brand' ? 'Brand' : 'Category'}</span>
                </button>
              ))}
            </div>
          </section>
        ) : (
          <>
            {recents.length > 0 && (
              <section>
                <div className="spread"><h3>Recent searches</h3>
                  <button type="button" className="btn btn--ghost btn--sm" onClick={() => { try { localStorage.removeItem(RECENT_KEY); } catch { /* */ } setRecents([]); }}>Clear</button></div>
                <div className="ssearch__chips">{recents.map((r) => <button key={r} type="button" className="chip" onClick={() => go(r)}><Icon name="history" size={14} /> {r}</button>)}</div>
              </section>
            )}
            {(sugg.data?.trending.length ?? 0) > 0 && (
              <section><h3>Trending searches</h3>
                <div className="ssearch__chips">{sugg.data!.trending.map((t) => <button key={t} type="button" className="chip" onClick={() => go(t)}>{t}</button>)}</div></section>
            )}
            {(sugg.data?.categories.length ?? 0) > 0 && (
              <section><h3>Popular categories</h3>
                <div className="ssearch__chips">{sugg.data!.categories.map((c) => <Link key={c.slug} to={`/shopping/c/${c.slug}`} className="chip" onClick={onClose}>{c.name}</Link>)}</div></section>
            )}
            <section>
              <h3>Try asking</h3>
              <div className="ssearch__chips">
                {['wireless earbuds under 2000', 'black running shoes', 'gift for a 10 year old', 'kitchen items for new home'].map((t) => (
                  <button key={t} type="button" className="chip" onClick={() => go(t)}>{t}</button>
                ))}
              </div>
              <p className="ssearch__note" style={{ marginTop: 8 }}>Search understands prices (“under 1500”), colours, brands and categories, and shows what it understood.</p>
            </section>
          </>
        )}
      </form>
    </Sheet>
  );
}
