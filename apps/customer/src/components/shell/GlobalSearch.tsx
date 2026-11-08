import { useEffect, useState, type FormEvent } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { Icon, Sheet } from '../ui';

type Pending = 'voice' | 'camera' | null;

/**
 * One Click search: type, speak, show or ask. Text search and "ask Buddy" are live.
 * Voice and camera input need a speech-to-text / image-recognition provider that is
 * not yet approved (browser speech APIs route audio to third-party clouds such as
 * Google's, which Click does not use), so they explain that instead of faking it.
 */
export function GlobalSearch({ compact = false }: { compact?: boolean }) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [params] = useSearchParams();
  const [q, setQ] = useState(pathname === '/search' ? params.get('q') ?? '' : '');
  const [pending, setPending] = useState<Pending>(null);

  useEffect(() => {
    if (pathname !== '/search') setQ('');
  }, [pathname]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    navigate(`/search${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ''}`);
  };

  return (
    <>
      <form className={`gsearch ${compact ? 'gsearch--compact' : ''}`} role="search" onSubmit={submit}>
        <Icon name="search" size={18} className="gsearch__lead" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search food, groceries, products, movies…" aria-label="Search Click" enterKeyHint="search" />
        <div className="gsearch__tools">
          <button type="button" className="gsearch__tool" aria-label="Search by voice" onClick={() => setPending('voice')}><Icon name="mic" size={18} /></button>
          <button type="button" className="gsearch__tool" aria-label="Search with camera" onClick={() => setPending('camera')}><Icon name="camera" size={18} /></button>
          <button type="button" className="gsearch__tool gsearch__tool--ai" aria-label="Ask Buddy"
            onClick={() => navigate(q.trim() ? `/buddy?q=${encodeURIComponent(q.trim())}` : '/buddy')}>
            <Icon name="sparkle" size={18} />
          </button>
        </div>
      </form>
      <Sheet open={pending !== null} onClose={() => setPending(null)} label={pending === 'voice' ? 'Voice search' : 'Camera search'}>
        <div className="stack" style={{ padding: 'var(--s-6)', textAlign: 'center', alignItems: 'center' }}>
          <div className="state__icon"><Icon name={pending === 'voice' ? 'mic' : 'camera'} /></div>
          <h2>{pending === 'voice' ? 'Voice search is coming' : 'Camera search is coming'}</h2>
          <p className="muted">
            {pending === 'voice'
              ? 'Speak to search Click and talk to Buddy. We’re choosing a private speech provider before turning this on.'
              : 'Snap a dish or product to find it on Click. We’re choosing an image-recognition provider before turning this on.'}
          </p>
          <div className="row">
            <button className="btn btn--primary" onClick={() => { setPending(null); navigate('/buddy'); }}>Ask Buddy instead</button>
            <button className="btn btn--ghost" onClick={() => setPending(null)}>Close</button>
          </div>
        </div>
      </Sheet>
    </>
  );
}
