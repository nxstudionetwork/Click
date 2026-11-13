import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { SearchHit } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { EmptyState, ErrorState, Icon, Skeleton, SmartImage } from '../components/ui';
import { THEME, iconFor } from '../features/money/parts';
import { api } from '../lib/api';
import { DiscoverTile } from './DiscoverPage';
import { formatMoney } from '../lib/format';

const ICON: Record<string, Parameters<typeof Icon>[0]['name']> = {
  store: 'store', dish: 'food', product: 'shop', destination: 'pin', hotel: 'hotel', attraction: 'temple', collection: 'compass', show: 'film',
  event_type: 'gift', event_provider: 'team', service_category: 'wrench', service_job: 'wrench', professional: 'user', offer: 'tag', article: 'book',
  gift_card: 'gift', order: 'bag', payment: 'card', parcel: 'parcel', ride: 'ride', invoice: 'receipt', support: 'help',
};

/** Click. Global Search: one search across every service, your own records by ID, suggestions as you type, your
 *  recent searches (kept on your account, clearable) and trending searches only when real people searched them. */
export function SearchPage() {
  const { status } = useAuth();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const q = params.get('q') ?? '';
  const group = params.get('group') ?? '';
  const [draft, setDraft] = useState(q);
  const [typed, setTyped] = useState('');
  const [focused, setFocused] = useState(!q);
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => { setDraft(q); }, [q]);
  useEffect(() => { const t = setTimeout(() => setTyped(draft.trim()), 200); return () => clearTimeout(t); }, [draft]);

  const results = useQuery({ queryKey: ['search', 'global', q, group], queryFn: () => api.money.search.global(q, group), enabled: q.trim().length >= 2, placeholderData: keepPreviousData });
  const suggest = useQuery({ queryKey: ['search', 'suggest', typed, status], queryFn: () => api.money.search.suggest(typed), enabled: focused && status !== 'loading', placeholderData: keepPreviousData });
  const clear = useMutation({ mutationFn: (id?: string) => api.money.search.clearRecent(id), onSuccess: () => qc.invalidateQueries({ queryKey: ['search', 'suggest'] }) });

  const go = (text: string, g = '') => { const t = text.trim(); if (t.length < 2) return; setFocused(false); inputRef.current?.blur(); setParams(g ? { q: t, group: g } : { q: t }); };
  const s = suggest.data;
  const r = results.data;
  const showPanel = focused && (draft.trim().length >= 2 ? (s?.suggestions.length || s?.mine?.length) : (s?.recent.length || s?.trending?.length));

  return (
    <div className="gs-page">
      <form className="gs-bar" role="search" onSubmit={(e) => { e.preventDefault(); go(draft); }}>
        <Icon name="search" size={20} />
        <input ref={inputRef} type="search" value={draft} autoFocus={!q} placeholder="Search Click." aria-label="Search Click."
          onChange={(e) => { setDraft(e.target.value); setFocused(true); }} onFocus={() => setFocused(true)} />
        {draft && <button type="button" className="gs-clear" aria-label="Clear" onClick={() => { setDraft(''); inputRef.current?.focus(); }}><Icon name="close" size={16} /></button>}
      </form>

      {showPanel ? (
        <div className="gs-panel" role="listbox" aria-label="Suggestions">
          {draft.trim().length >= 2 ? (
            <>
              {s?.mine?.map((h) => <SuggestRow key={h.link} h={h} onPick={() => nav(h.link)} />)}
              {s?.suggestions.map((h) => <SuggestRow key={h.link} h={h} onPick={() => nav(h.link)} />)}
              <button type="button" className="gs-row" onClick={() => go(draft)}><span className="gs-row__icon"><Icon name="search" size={16} /></span><span>Search for “{draft.trim()}”</span></button>
            </>
          ) : (
            <>
              {!!s?.recent.length && (
                <div className="gs-sec"><div className="gs-sec__head"><h2>Recent searches</h2><button type="button" className="mn-link small" onClick={() => clear.mutate(undefined)}>Clear all</button></div>
                  {s.recent.map((x) => (
                    <div key={x.id} className="gs-recent">
                      <button type="button" className="gs-row" onClick={() => go(x.query)}><span className="gs-row__icon"><Icon name="history" size={16} /></span><span className="truncate">{x.query}</span></button>
                      <button type="button" className="gs-x" aria-label={`Remove ${x.query}`} onClick={() => clear.mutate(x.id)}><Icon name="close" size={14} /></button>
                    </div>
                  ))}</div>
              )}
              {!!s?.trending?.length && (
                <div className="gs-sec"><h2>Trending on Click.</h2><div className="mn-chips mn-chips--wrap">{s.trending.map((t) => <button key={t} type="button" className="mn-chip" onClick={() => go(t)}>{t}</button>)}</div></div>
              )}
            </>
          )}
        </div>
      ) : null}

      {q.trim().length < 2 ? (
        !showPanel && <EmptyState icon="search" title="What are you looking for?" message="Restaurants, dishes, groceries, products, hotels, places, shows, services, offers — or an order or booking ID." />
      ) : results.isError ? <ErrorState error={results.error} onRetry={() => results.refetch()} /> : !r ? <Skeleton height={300} /> : (
        <>
          {r.groups.length > 1 && (
            <div className="mn-chips" role="tablist" aria-label="Result type">
              <button type="button" role="tab" className="mn-chip" aria-pressed={!group} aria-selected={!group} onClick={() => go(q)}>All · {r.count + r.mine.length}</button>
              {(group ? r.groups : r.groups).map((g) => <button key={g.code} type="button" role="tab" className="mn-chip" aria-pressed={group === g.code} aria-selected={group === g.code}
                onClick={() => go(q, g.code)}>{g.label} · {g.count}</button>)}
            </div>
          )}
          {r.mine.length > 0 && <Group title="Your records" rows={r.mine} />}
          {r.sponsored?.map((ad) => <div key={ad.campaign} className="gs-ad"><DiscoverTile c={ad} /></div>)}
          {!group && r.top.length > 0 && <Group title="Top results" rows={r.top} />}
          {r.groups.map((g) => <Group key={g.code} title={g.label} rows={g.results} more={!group && g.count > g.results.length ? () => go(q, g.code) : undefined} total={g.count} />)}
          {r.count === 0 && r.mine.length === 0 && (
            <EmptyState icon="search" title={`Nothing found for “${q}”`} message="Try another word, a shorter search, or ask Buddy."
              action={<Link to={`/buddy?q=${encodeURIComponent(q)}`} className="btn btn--outline">Ask Buddy</Link>} />
          )}
        </>
      )}
    </div>
  );
}

function SuggestRow({ h, onPick }: { h: SearchHit; onPick: () => void }) {
  return (
    <button type="button" role="option" className="gs-row" onClick={onPick}>
      <span className="gs-row__icon"><Icon name={ICON[h.type] ?? iconFor(h.service)} size={16} /></span>
      <span className="gs-row__text"><strong className="truncate">{h.title}</strong><span className="small mn-muted truncate">{h.subtitle}</span></span>
    </button>
  );
}

function Group({ title, rows, more, total }: { title: string; rows: SearchHit[]; more?: () => void; total?: number }) {
  return (
    <section className="gs-group">
      <div className="mn-sec__head"><h2>{title}</h2>{more && <button type="button" className="mn-link small" onClick={more}>See all {total}</button>}</div>
      <ul className="mn-list">{rows.map((h) => (
        <li key={`${h.type}:${h.id}:${h.link}`}><Link to={h.link} className="mn-row" data-theme={THEME[h.service]}>
          {h.image ? <SmartImage src={h.image} alt="" className="gs-thumb" /> : <span className="mn-row__icon mn-row__icon--theme"><Icon name={ICON[h.type] ?? iconFor(h.service)} size={18} /></span>}
          <span className="mn-row__text"><strong className="truncate">{h.title}</strong><span className="small mn-muted truncate">{h.subtitle}</span></span>
          <span className="mn-row__end">
            {h.price && <strong>{formatMoney(h.price)}</strong>}
            {h.rating && <span className="small"><Icon name="star" size={12} /> {h.rating}</span>}
            {h.badge && <span className="mn-tag">{h.badge}</span>}
          </span>
        </Link></li>
      ))}</ul>
    </section>
  );
}
