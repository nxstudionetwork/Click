import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { DiscoverCard } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { EmptyState, ErrorState, Icon, Skeleton, SmartImage, useToast } from '../components/ui';
import { useAddresses } from '../features/addresses/useAddresses';
import { MoneyHead, THEME, iconFor } from '../features/money/parts';
import { api } from '../lib/api';

const SERVICES = [['', 'Everything'], ['food', 'Food'], ['groceries', 'Groceries'], ['shop', 'Shop'], ['hotels', 'Stays'], ['bookings', 'Places']];

/** One Discover card. Sponsored cards say so, explain why they're shown, can be hidden, and report one impression
 *  (when half visible for a second) and clicks to the server, which charges the advertiser — never the client. */
export function DiscoverTile({ c, onHidden }: { c: DiscoverCard; onHidden?: () => void }) {
  const { status } = useAuth();
  const nav = useNavigate();
  const toast = useToast();
  const ref = useRef<HTMLDivElement>(null);
  const [why, setWhy] = useState(false);
  const hide = useMutation({ mutationFn: () => api.money.discover.hide(c.campaign!), onSuccess: () => { toast('You won’t see this ad again'); onHidden?.(); } });
  useEffect(() => {
    if (!c.sponsored || !c.token || !ref.current || typeof IntersectionObserver === 'undefined') return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let sent = false;
    const io = new IntersectionObserver(([e]) => {
      if (e?.isIntersecting && !sent) timer = setTimeout(() => { sent = true; void api.money.discover.track(c.token!, 'impression').catch(() => undefined); }, 1000);
      else if (timer) clearTimeout(timer);
    }, { threshold: 0.5 });
    io.observe(ref.current);
    return () => { io.disconnect(); if (timer) clearTimeout(timer); };
  }, [c.sponsored, c.token]);
  const open = async () => {
    if (c.sponsored && c.token) await api.money.discover.track(c.token, 'click').catch(() => undefined);
    nav(c.link);
  };
  return (
    <div ref={ref} className={`dc-card ${c.sponsored ? 'dc-card--ad' : ''}`} data-theme={THEME[c.service]}>
      <button type="button" className="dc-card__main" onClick={open}>
        {c.image ? <SmartImage src={c.image} alt="" className="dc-card__img" /> : <span className="dc-card__img dc-card__img--icon"><Icon name={iconFor(c.service)} size={28} /></span>}
        <span className="dc-card__body">
          {c.sponsored && <span className="dc-ad">Sponsored</span>}
          <strong className="dc-card__title">{c.title}</strong>
          <span className="small mn-muted dc-card__sub">{c.subtitle}</span>
          <span className="dc-card__facts small">
            {c.rating && <span><Icon name="star" size={12} /> {c.rating}{c.ratingCount ? ` (${c.ratingCount})` : ''}</span>}
            {c.eta && <span>{c.eta}</span>}
            {!c.open && <span className="mn-bad">Closed now</span>}
          </span>
          {c.offer && <span className="dc-card__offer small"><Icon name="tag" size={12} /> {c.offer}</span>}
          {!c.sponsored && c.why && <span className="dc-card__why small">{c.why}</span>}
        </span>
      </button>
      <div className="dc-card__foot">
        <button type="button" className="dc-card__cta" onClick={open}>{c.cta}</button>
        {c.sponsored && (
          <span className="dc-card__adctl">
            <button type="button" className="mn-link small" onClick={() => setWhy((v) => !v)} aria-expanded={why}>Why this ad?</button>
            {status === 'authenticated' && <button type="button" className="mn-link small" onClick={() => hide.mutate()}>Hide</button>}
          </span>
        )}
      </div>
      {why && <p className="small dc-card__whytext">{c.why}</p>}
    </div>
  );
}

/** Discover: what's interesting, useful, new or popular around you on Click. — organic sections from real activity,
 *  with a few clearly labelled sponsored cards. Explore stays the quick launcher; Home stays your dashboard. */
export function DiscoverPage() {
  const { status } = useAuth();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const service = params.get('service') ?? '';
  const city = params.get('city') ?? '';
  const addresses = useAddresses();
  const [q, setQ] = useState('');
  const feed = useQuery({ queryKey: ['discover', service, city, status], queryFn: () => api.money.discover.feed({ service, city }), enabled: status !== 'loading' });
  const cities = [...new Set((addresses.data ?? []).map((a) => a.city).filter(Boolean))];
  const set = (k: string, v: string) => { const n = new URLSearchParams(params); if (v) n.set(k, v); else n.delete(k); setParams(n, { replace: true }); };
  return (
    <div className="mn-page dc-page">
      <MoneyHead title="Discover" back="/" />
      <form className="mn-search" role="search" onSubmit={(e) => { e.preventDefault(); if (q.trim().length >= 2) nav(`/search?q=${encodeURIComponent(q.trim())}`); }}>
        <Icon name="search" size={18} /><input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Late night food, salons, things to do this weekend…" aria-label="Search Click." />
      </form>
      <div className="dc-where">
        <Icon name="pin" size={16} />
        <span className="small">Discovering around <strong>{feed.data?.city || city || 'you'}</strong></span>
        {cities.length > 1 && (
          <select className="dc-where__pick" value={city} onChange={(e) => set('city', e.target.value)} aria-label="Change discovery location">
            <option value="">My default address</option>{cities.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        )}
      </div>
      <div className="mn-chips" role="tablist" aria-label="What to discover">
        {SERVICES.map(([v, l]) => <button key={v || 'all'} type="button" role="tab" className="mn-chip" aria-pressed={service === v} aria-selected={service === v} onClick={() => set('service', v!)}>{l}</button>)}
      </div>
      {feed.isError ? <ErrorState error={feed.error} onRetry={() => feed.refetch()} /> : !feed.data ? <Skeleton height={420} /> : feed.data.sections.length === 0 ? (
        <EmptyState icon="compass" title="Nothing to discover here yet" message="Try another category or location." action={<Link to="/explore" className="btn btn--outline">Open Explore</Link>} />
      ) : feed.data.sections.map((s) => (
        <section key={s.code} className="mn-sec" aria-labelledby={`dc-${s.code}`}>
          <div className="mn-sec__head"><div><h2 id={`dc-${s.code}`}>{s.title}</h2><p className="small mn-muted">{s.subtitle}</p></div></div>
          <div className="dc-rail">{s.cards.map((c) => <DiscoverTile key={`${c.type}:${c.id}:${c.sponsored ? 'ad' : ''}`} c={c} onHidden={() => qc.invalidateQueries({ queryKey: ['discover'] })} />)}</div>
        </section>
      ))}
      <p className="small mn-muted">Sponsored cards are ads from Click. partners, chosen by relevance and quality as well as bid, and never use your orders or searches.</p>
    </div>
  );
}
