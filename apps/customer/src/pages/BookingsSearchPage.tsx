import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useInfiniteQuery } from '@tanstack/react-query';
import { Button, EmptyState, ErrorState, Icon, Sheet, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { PlaceCard, todayIso } from '../features/bookings/parts';
import { useDeliveryLocation } from '../location/LocationProvider';
import { api } from '../lib/api';

const GROUPS = [['', 'All'], ['spiritual', 'Temples & spiritual'], ['tourist', 'Tourist spots'], ['parks', 'Parks & fun'], ['experiences', 'Experiences']];
const SORT_LABEL: Record<string, string> = { recommended: 'Recommended', popular: 'Most booked (90 days)', rating: 'Rating', price_asc: 'Price: low to high',
  price_desc: 'Price: high to low', nearest: 'Nearest', soonest: 'Soonest available' };
const FLAGS = [['bookable', 'Bookable through Click.'], ['instant', 'Instant confirmation'], ['free_cancellation', 'Free cancellation'], ['verified', 'Verified provider'],
  ['family', 'Family friendly'], ['kids', 'Kids friendly']];
const KEYS = ['q', 'group', 'kind', 'city', 'date', 'bookable', 'instant', 'free_cancellation', 'verified', 'family', 'kids', 'setting', 'min_rating', 'min_price', 'max_price', 'sort', 'max_km'];

/** Places and experiences: search, server-side filters and sorts (each with a stated rule), availability on a date, and
 *  matches elsewhere on Click. (hotels, travel, shows) for the same words. */
export function BookingsSearchPage() {
  useThemeOverride('bookings');
  const [sp, setSp] = useSearchParams();
  const { point } = useDeliveryLocation();
  const [open, setOpen] = useState(false);
  const params: Record<string, string> = {};
  KEYS.forEach((k) => { const v = sp.get(k); if (v) params[k] = v; });
  if (point) { params.lat = String(point.lat); params.lng = String(point.lng); }
  const q = useInfiniteQuery({
    queryKey: ['bookings', 'search', params], initialPageParam: 1,
    queryFn: ({ pageParam }) => api.bookings.search({ ...params, page: String(pageParam) }),
    getNextPageParam: (last, all) => (last.hasMore ? all.length + 1 : undefined),
  });
  const first = q.data?.pages[0];
  const rows = q.data?.pages.flatMap((p) => p.results) ?? [];
  const set = (k: string, v: string | null) => { const n = new URLSearchParams(sp); if (v) n.set(k, v); else n.delete(k); setSp(n, { replace: true }); };
  const [text, setText] = useState(sp.get('q') ?? '');
  const title = sp.get('city') ? `In ${sp.get('city')}` : sp.get('group') ? GROUPS.find(([g]) => g === sp.get('group'))?.[1] : sp.get('q') ? `“${sp.get('q')}”` : 'Places & experiences';

  const panel = (
    <div className="bk-filters">
      <fieldset className="bk-fgroup"><legend>Visit date</legend>
        <input type="date" min={todayIso()} value={sp.get('date') ?? ''} onChange={(e) => set('date', e.target.value || null)} aria-label="Visit date" />
        <span className="small bk-muted">Shows only places with places left that day.</span></fieldset>
      <fieldset className="bk-fgroup"><legend>Show</legend>{FLAGS.map(([k, l]) => (
        <label key={k} className="bk-check"><input type="checkbox" checked={sp.get(k!) === '1'} onChange={(e) => set(k!, e.target.checked ? '1' : null)} /> {l}</label>))}</fieldset>
      <fieldset className="bk-fgroup"><legend>Setting</legend>{[['', 'Any'], ['indoor', 'Indoor'], ['outdoor', 'Outdoor']].map(([v, l]) => (
        <label key={v} className="bk-check"><input type="radio" name="setting" checked={(sp.get('setting') ?? '') === v} onChange={() => set('setting', v || null)} /> {l}</label>))}</fieldset>
      <fieldset className="bk-fgroup"><legend>Rating</legend>{[['', 'Any'], ['4', '4.0+'], ['4.5', '4.5+']].map(([v, l]) => (
        <label key={v} className="bk-check"><input type="radio" name="rating" checked={(sp.get('min_rating') ?? '') === v} onChange={() => set('min_rating', v || null)} /> {l}{v ? ' (3+ verified visits)' : ''}</label>))}</fieldset>
      <fieldset className="bk-fgroup"><legend>Price (from)</legend>
        <div className="bk-row2"><input inputMode="numeric" placeholder="Min ₹" defaultValue={sp.get('min_price') ?? ''} onBlur={(e) => set('min_price', e.target.value.replace(/\D/g, '') || null)} aria-label="Minimum price" />
          <input inputMode="numeric" placeholder="Max ₹" defaultValue={sp.get('max_price') ?? ''} onBlur={(e) => set('max_price', e.target.value.replace(/\D/g, '') || null)} aria-label="Maximum price" /></div></fieldset>
      {point && <fieldset className="bk-fgroup"><legend>Distance</legend>{[['', 'Any'], ['10', 'Within 10 km'], ['30', 'Within 30 km']].map(([v, l]) => (
        <label key={v} className="bk-check"><input type="radio" name="km" checked={(sp.get('max_km') ?? '') === v} onChange={() => set('max_km', v || null)} /> {l}</label>))}</fieldset>}
      <button type="button" className="bk-link small" onClick={() => setSp(new URLSearchParams(sp.get('q') ? { q: sp.get('q')! } : {}), { replace: true })}>Reset filters</button>
    </div>
  );

  return (
    <div className="bk-page" data-theme="bookings">
      <Link to="/bookings" className="bk-back"><Icon name="back" size={18} /> Bookings</Link>
      <form className="bk-search bk-search--bar" role="search" onSubmit={(e) => { e.preventDefault(); set('q', text.trim() || null); }}>
        <label className="bk-search__q"><span className="sr-only">Search</span><Icon name="search" size={18} />
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Temple, city, attraction, activity…" /></label>
        <Button type="submit">Search</Button>
      </form>
      <h1 className="bk-title">{title}</h1>
      <div className="bk-chips" role="tablist" aria-label="Category">{GROUPS.map(([g, l]) => (
        <button key={g} type="button" role="tab" aria-selected={(sp.get('group') ?? '') === g} className={(sp.get('group') ?? '') === g ? 'is-on' : ''} onClick={() => { set('group', g || null); set('kind', null); }}>{l}</button>))}</div>
      <div className="bk-tools">
        <span className="small bk-muted" aria-live="polite">{first ? `${first.count} result${first.count === 1 ? '' : 's'}` : ''}</span>
        <button type="button" className="bk-ghostbtn bk-only-mobile" onClick={() => setOpen(true)}><Icon name="filter" size={16} /> Filters</button>
        <label className="bk-sort"><span className="sr-only">Sort</span><Icon name="sort" size={16} />
          <select value={sp.get('sort') ?? 'recommended'} onChange={(e) => set('sort', e.target.value === 'recommended' ? null : e.target.value)}>
            {(first?.filters.sorts ?? Object.keys(SORT_LABEL)).sort((a, b) => Object.keys(SORT_LABEL).indexOf(a) - Object.keys(SORT_LABEL).indexOf(b)).map((s) => <option key={s} value={s}>{SORT_LABEL[s] ?? s}</option>)}
          </select></label>
      </div>
      <div className="bk-layout">
        <aside className="bk-side" aria-label="Filters">{panel}</aside>
        <div className="bk-main">
          {q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !first ? <div className="bk-grid">{[0, 1, 2, 3].map((i) => <Skeleton key={i} height={260} radius={20} />)}</div> : (
            <>
              {(first.elsewhere.length ?? 0) > 0 && (
                <div className="bk-elsewhere"><span className="small bk-muted">Also on Click.:</span>{first.elsewhere.map((e) => <Link key={e.link} to={e.link} className="bk-chip">{e.title}</Link>)}</div>
              )}
              {rows.length === 0 ? <EmptyState icon="search" title="Nothing available for these choices yet" message={sp.get('date') ? 'Try another date or remove a filter.' : 'Try another place or category.'}
                action={<Link to="/bookings" className="bk-btn">Explore Bookings</Link>} /> : (
                <div className="bk-grid">{rows.map((a) => <PlaceCard key={a.id} a={a} />)}</div>
              )}
              {q.hasNextPage && <Button variant="secondary" loading={q.isFetchingNextPage} onClick={() => q.fetchNextPage()}>Show more</Button>}
            </>
          )}
        </div>
      </div>
      <Sheet open={open} onClose={() => setOpen(false)} label="Filters"><div className="bk-sheet">{panel}<Button block onClick={() => setOpen(false)}>Show results</Button></div></Sheet>
    </div>
  );
}
