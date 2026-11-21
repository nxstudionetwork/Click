import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { CameraSearch } from '../../features/assist/CameraSearch';
import { VoiceInput } from '../../features/assist/VoiceInput';
import { clearRecentSearches, recentSearches, rememberSearch, SEARCH_HINTS } from '../../features/search/recent';
import { Icon, Sheet } from '../ui';

type Panel = 'voice' | 'camera' | null;

/** One Click. search: type (with recent searches and hints), speak, or scan. Results come from /search. */
export function GlobalSearch({ compact = false }: { compact?: boolean }) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [params] = useSearchParams();
  const [q, setQ] = useState(pathname === '/search' ? params.get('q') ?? '' : '');
  const [panel, setPanel] = useState<Panel>(null);
  const [focused, setFocused] = useState(false);
  const [recent, setRecent] = useState<string[]>([]);
  const wrap = useRef<HTMLDivElement>(null);

  useEffect(() => { if (pathname !== '/search') setQ(''); }, [pathname]);
  useEffect(() => { if (focused) setRecent(recentSearches()); }, [focused]);
  useEffect(() => {
    if (!focused) return;
    const onDoc = (e: MouseEvent) => { if (!wrap.current?.contains(e.target as Node)) setFocused(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [focused]);

  const search = (term: string) => {
    const t = term.trim();
    if (t) rememberSearch(t);
    setFocused(false);
    navigate(`/search${t ? `?q=${encodeURIComponent(t)}` : ''}`);
  };
  const submit = (e: FormEvent) => { e.preventDefault(); search(q); };

  return (
    <div className="gsearch-wrap" ref={wrap}>
      <form className={`gsearch ${compact ? 'gsearch--compact' : ''}`} role="search" onSubmit={submit}>
        <Icon name="search" size={18} className="gsearch__lead" />
        <input
          value={q} onChange={(e) => setQ(e.target.value)} onFocus={() => setFocused(true)}
          onKeyDown={(e) => { if (e.key === 'Escape') setFocused(false); }}
          placeholder="Search Click." aria-label="Search Click." enterKeyHint="search" autoComplete="off"
        />
        <div className="gsearch__tools">
          <button type="button" className="gsearch__tool" aria-label="Search by voice" onClick={() => setPanel('voice')}><Icon name="mic" size={18} /></button>
          <button type="button" className="gsearch__tool" aria-label="Search with camera" onClick={() => setPanel('camera')}><Icon name="camera" size={18} /></button>
        </div>
      </form>

      {focused && !q.trim() && (
        <div className="gsearch__panel" role="dialog" aria-label="Search suggestions">
          {recent.length > 0 && (
            <section>
              <div className="spread"><span className="gsearch__heading">Recent</span>
                <button className="gsearch__clear" onClick={() => { clearRecentSearches(); setRecent([]); }}>Clear</button></div>
              <ul className="gsearch__recent">
                {recent.map((r) => (
                  <li key={r}><button onClick={() => search(r)}><Icon name="history" size={16} />{r}</button></li>
                ))}
              </ul>
            </section>
          )}
          <section>
            <span className="gsearch__heading">Try</span>
            <div className="gsearch__hints">
              {SEARCH_HINTS.map((h) => <Link key={h.label} to={h.to} data-theme={h.theme} className="hint-chip" onClick={() => setFocused(false)}>{h.label}</Link>)}
            </div>
          </section>
        </div>
      )}

      <Sheet open={panel !== null} onClose={() => setPanel(null)} label={panel === 'voice' ? 'Voice search' : 'Camera search'}>
        <div className="stack" style={{ padding: 'var(--s-5)' }}>
          <div className="spread"><h2>{panel === 'voice' ? 'Voice search' : 'Scan with camera'}</h2>
            <button className="icon-btn" aria-label="Close" onClick={() => setPanel(null)}><Icon name="close" /></button></div>
          {panel === 'voice' && <VoiceInput onText={(t) => { setPanel(null); search(t); }} placeholder="Type your search" />}
          {panel === 'camera' && <CameraSearch onDone={() => setPanel(null)} />}
        </div>
      </Sheet>
    </div>
  );
}
