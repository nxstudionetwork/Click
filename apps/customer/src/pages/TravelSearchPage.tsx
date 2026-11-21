import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type TravelMode, type TravelPlace, type TravelSearchResult } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, EmptyState, ErrorState, Icon, Sheet, Skeleton, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { fmtDate, fmtDur, fmtTime, JourneyCard, ModeTabs, modeOf, PaxPicker, PlaceField, paxLabel, searchFrom, searchQs, todayIso } from '../features/travel/parts';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

const LIST_KEYS = ['departure', 'arrival', 'operators', 'cancellation', 'amenities', 'bus_type', 'boarding', 'dropping', 'train_type', 'stops'] as const;
const ONE_KEYS = ['min_price', 'max_price', 'min_rating', 'max_duration', 'available_only', 'refundable', 'checked_bag', 'sort'] as const;
const SORTS: Record<TravelMode, [string, string][]> = {
  bus: [['recommended', 'Recommended'], ['price', 'Cheapest'], ['departure', 'Earliest departure'], ['arrival', 'Earliest arrival'], ['duration', 'Shortest duration'], ['rating', 'Highest rated']],
  train: [['recommended', 'Recommended'], ['departure', 'Earliest departure'], ['arrival', 'Earliest arrival'], ['duration', 'Shortest duration'], ['price', 'Cheapest']],
  flight: [['recommended', 'Recommended'], ['price', 'Cheapest'], ['duration', 'Fastest'], ['departure', 'Earliest departure'], ['arrival', 'Earliest arrival']],
};
const BUS_TYPES: [string, string][] = [['ac', 'AC'], ['non_ac', 'Non-AC'], ['sleeper', 'Sleeper'], ['seater', 'Seater'], ['semi_sleeper', 'Semi-sleeper'], ['premium', 'Premium / multi-axle']];
const CANCEL: [string, string][] = [['free', 'Free cancellation window'], ['partial', 'Partial refund'], ['non_refundable', 'Non-refundable']];

/** Results: a journey summary bar, the lowest fares on nearby dates, a cheapest / fastest / best-value strip, server-side
 *  filters (sidebar on desktop, sheet on mobile), transport-specific cards and a compare tray. Search state is the URL. */
export function TravelSearchPage() {
  useThemeOverride('travel');
  const [sp, setSp] = useSearchParams();
  const nav = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const { status } = useAuth();
  const s = searchFrom(sp);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [picked, setPicked] = useState<string[]>([]);
  const filters = useMemo(() => {
    const out: Record<string, string> = {};
    [...LIST_KEYS, ...ONE_KEYS].forEach((k) => { const v = sp.get(k); if (v) out[k] = v; });
    return out;
  }, [sp]);
  // Saved travel preferences pre-select filters once per search (never a promise of availability); "prefs" marks it done.
  const prefs = useQuery({ queryKey: ['travel', 'prefs'], queryFn: () => api.travel.preferences(), enabled: status === 'authenticated' });
  const needPrefs = status === 'authenticated' && !sp.has('prefs');
  useEffect(() => {
    if (!needPrefs || !prefs.isFetched) return;
    const n = new URLSearchParams(sp);
    const p = prefs.data;
    if (p && !Object.keys(filters).some((k) => k !== 'sort')) {
      if (s.mode === 'bus' && p.busTypes.length) n.set('bus_type', p.busTypes.join(','));
      if (s.mode === 'bus' && p.busDeparture) n.set('departure', p.busDeparture);
      if (s.mode === 'flight' && p.nonstop) n.set('stops', '0');
      if (s.mode === 'flight' && p.airlines.length) n.set('operators', p.airlines.join(','));
      if (s.mode === 'train' && p.trainClass && !s.travelClass) n.set('travel_class', p.trainClass);
      if (s.mode === 'flight' && p.flightCabin && !s.travelClass) n.set('travel_class', p.flightCabin);
    }
    n.set('prefs', '1');
    setSp(n, { replace: true });
  }, [needPrefs, prefs.isFetched, prefs.data, sp, setSp, filters, s.mode, s.travelClass]);
  const key = ['travel', 'search', searchQs(s), filters];
  const q = useInfiniteQuery({
    queryKey: key, initialPageParam: 1, enabled: !!s.origin && !!s.destination && !needPrefs,
    queryFn: ({ pageParam }) => api.travel.search(s, { ...filters, page: String(pageParam) }),
    getNextPageParam: (last, all) => (last.hasMore ? all.length + 1 : undefined),
  });
  const dates = useQuery({ queryKey: ['travel', 'dates', searchQs(s)], queryFn: () => api.travel.dates(s), enabled: !!s.origin && q.isSuccess, staleTime: 60_000 });
  const first = q.data?.pages[0];
  const results = q.data?.pages.flatMap((p) => p.results) ?? [];
  const setParam = (k: string, v: string | null) => { const n = new URLSearchParams(sp); if (v) n.set(k, v); else n.delete(k); setSp(n, { replace: true }); };
  const toggle = (k: string, v: string) => {
    const cur = (sp.get(k) ?? '').split(',').filter(Boolean);
    setParam(k, (cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]).join(',') || null);
  };
  const setSearch = (patch: Partial<typeof s>) => { nav(`/travel/search?${searchQs({ ...s, ...patch }, { sort: sp.get('sort') ?? '' })}`, { replace: true }); setPicked([]); };
  const saveRoute = useMutation({
    mutationFn: async () => { if (first?.savedRouteId) await api.customer.wishlist.remove(first.savedRouteId); else await api.travel.saveRoute(s.origin, s.destination); },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['travel'] }); toast(first?.savedRouteId ? 'Route removed from My routes' : 'Route saved to My routes and your Wishlist'); },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t update.', 'error'),
  });
  const follow = useMutation({
    mutationFn: () => api.travel.addAlert({ origin: s.origin, destination: s.destination, mode: s.mode, date: s.date }),
    onSuccess: (a) => toast(a.lastFare ? `Following the fare: lowest is ${formatMoney(a.lastFare)} now. We’ll notify you when it changes.` : 'Following this journey. We’ll notify you when fares appear or change.'),
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t follow this journey.', 'error'),
  });
  const detailTo = (o: (typeof results)[number]) => `/travel/journey/${o.journeyId}/${o.fromStopId}/${o.toStopId}?${searchQs(s)}`;
  const activeCount = Object.keys(filters).filter((k) => k !== 'sort').length;
  const sortOptions = SORTS[s.mode];

  if (!s.origin || !s.destination) return <div className="tv-page"><EmptyState icon="bus" title="Start a journey search" action={<Link to="/travel" className="tv-btn">Search journeys</Link>} /></div>;
  const err = q.error instanceof ApiError ? q.error : null;

  const filterPanel = first && (
    <FilterPanel s={s} f={first.facets} sp={sp} toggle={toggle} setParam={setParam} onReset={() => { const n = new URLSearchParams(searchQs(s, { prefs: '1' })); setSp(n, { replace: true }); }} />
  );

  return (
    <div className="tv-page tv-results" data-theme="travel">
      <header className="tv-summary">
        <Link to="/travel" className="tv-back" aria-label="Back to Travel"><Icon name="back" size={18} /></Link>
        <div className="tv-summary__main">
          <strong>{first?.query.origin.name ?? s.origin} <Icon name="right" size={14} /> {first?.query.destination.name ?? s.destination}</strong>
          <span className="small tv-muted">{fmtDate(s.date)}{s.returnDate ? ` · return ${fmtDate(s.returnDate, { day: 'numeric', month: 'short' })}` : ''} · {paxLabel(s)}{s.travelClass ? ` · ${s.travelClass}` : ''}</span>
        </div>
        <button type="button" className="tv-ghostbtn" onClick={() => setEditOpen(true)}><Icon name="edit" size={16} /> Edit</button>
      </header>
      <ModeTabs compact value={s.mode} onChange={(m) => setSearch({ mode: m, travelClass: '', infants: m === 'flight' ? s.infants : 0 })} />
      {s.returnDate && <p className="tv-note small"><Icon name="swap" size={14} /> Step 1 of 2: choose your outbound journey. After booking it, we’ll open the return ({fmtDate(s.returnDate)}).</p>}

      {dates.data && (
        <div className="tv-dates" role="list" aria-label="Lowest fares on nearby dates">
          {dates.data.results.map((d) => (
            <button key={d.date} role="listitem" type="button" className={d.date === s.date ? 'is-on' : ''} aria-current={d.date === s.date ? 'date' : undefined}
              disabled={d.date < todayIso()} onClick={() => setSearch({ date: d.date })}>
              <span>{fmtDate(d.date, { weekday: 'short', day: 'numeric', month: 'short' })}</span>
              <strong>{d.lowest ? formatMoney(String(Math.round(Number(d.lowest)))) : '—'}</strong>
            </button>
          ))}
        </div>
      )}

      {q.isError ? (
        err?.status === 503 ? <ErrorState error={new Error('Travel options are temporarily unavailable.')} onRetry={() => q.refetch()} />
          : err?.status === 400 ? <EmptyState icon="alert" title="Check your search" message={err.message} action={<Link to="/travel" className="tv-btn">Edit search</Link>} />
            : <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : !first ? (
        <div className="tv-list">{[0, 1, 2].map((i) => <Skeleton key={i} height={190} radius={22} />)}</div>
      ) : (
        <div className="tv-layout">
          <aside className="tv-side" aria-label="Filters">{filterPanel}</aside>
          <div className="tv-main">
            {first.strip.length > 0 && (
              <div className="tv-strip" role="list" aria-label="Best options">
                {first.strip.map((x) => (
                  <Link key={x.key} role="listitem" to={detailTo(results.find((r) => r.id === x.id) ?? first.results[0]!)} className={`tv-strip__item tv-strip__item--${x.key}`}
                    onClick={(e) => { if (!results.find((r) => r.id === x.id)) e.preventDefault(); }}>
                    <span className="small">{x.label}</span><strong>{formatMoney(x.total)}</strong>
                    <span className="small tv-muted">{fmtTime(x.departsAt)} · {fmtDur(x.durationMinutes)} · {x.operator}</span>
                  </Link>
                ))}
              </div>
            )}
            <div className="tv-tools">
              <span className="small tv-muted" aria-live="polite">{first.count} of {first.total} {modeOf(s.mode).noun}</span>
              <button type="button" className="tv-ghostbtn tv-only-mobile" onClick={() => setFiltersOpen(true)}><Icon name="filter" size={16} /> Filters{activeCount ? ` (${activeCount})` : ''}</button>
              <label className="tv-sort"><span className="sr-only">Sort</span><Icon name="sort" size={16} />
                <select value={sp.get('sort') ?? 'recommended'} onChange={(e) => setParam('sort', e.target.value === 'recommended' ? null : e.target.value)}>
                  {sortOptions.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select></label>
              {status === 'authenticated' && <>
                <button type="button" className="tv-ghostbtn" aria-pressed={!!first.savedRouteId} onClick={() => saveRoute.mutate()} disabled={saveRoute.isPending}>
                  <Icon name="heart" size={16} /> {first.savedRouteId ? 'Saved route' : 'Save route'}</button>
                <button type="button" className="tv-ghostbtn" onClick={() => follow.mutate()} disabled={follow.isPending}><Icon name="bell" size={16} /> Fare alert</button>
              </>}
            </div>
            {results.length === 0 ? (
              <EmptyState icon="search" title={first.total ? 'No journeys match these filters' : 'No journeys found'}
                message={first.total ? 'Clear a filter to see more.' : 'Try another date, a nearby station or airport, or a different transport type.'}
                action={<div className="tv-alts">
                  {first.total > 0 && <Button variant="secondary" onClick={() => setSp(new URLSearchParams(searchQs(s, { prefs: '1' })), { replace: true })}>Clear filters</Button>}
                  {first.alternatives.map((a) => <Button key={a.mode} variant="secondary" onClick={() => setSearch({ mode: a.mode, travelClass: '' })}>
                    {a.count} {modeOf(a.mode).noun}{a.lowest ? ` from ${formatMoney(a.lowest)}` : ''}</Button>)}
                </div>} />
            ) : (
              <div className="tv-list">
                {results.map((o) => (
                  <JourneyCard key={o.id} o={o} to={detailTo(o)} compare={picked.includes(o.id)}
                    onCompare={() => setPicked((p) => (p.includes(o.id) ? p.filter((x) => x !== o.id) : p.length >= 3 ? p : [...p, o.id]))} />
                ))}
                {q.hasNextPage && <Button variant="secondary" loading={q.isFetchingNextPage} onClick={() => q.fetchNextPage()}>Show more</Button>}
              </div>
            )}
            <p className="small tv-muted">{first.fareNote}</p>
          </div>
        </div>
      )}

      {picked.length > 0 && (
        <div className="tv-tray" role="region" aria-label="Compare">
          <span className="small">{picked.length} selected{picked.length < 2 ? ' · pick at least 2' : ''}</span>
          <button type="button" className="tv-link small" onClick={() => setPicked([])}>Clear</button>
          <Button size="sm" disabled={picked.length < 2} onClick={() => nav(`/travel/compare?ids=${picked.join(',')}&${searchQs(s)}`)}>Compare {picked.length}</Button>
        </div>
      )}

      <Sheet open={filtersOpen} onClose={() => setFiltersOpen(false)} label="Filters">
        <div className="tv-sheet">{filterPanel}<Button block onClick={() => setFiltersOpen(false)}>Show {first?.count ?? ''} results</Button></div>
      </Sheet>
      <EditSheet open={editOpen} onClose={() => setEditOpen(false)} s={s} first={first} onSearch={(patch) => { setEditOpen(false); setSearch(patch); }} />
    </div>
  );
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return <fieldset className="tv-fgroup"><legend>{title}</legend>{children}</fieldset>;
}

function FilterPanel({ s, f, sp, toggle, setParam, onReset }: {
  s: ReturnType<typeof searchFrom>; f: TravelSearchResult['facets']; sp: URLSearchParams; toggle: (k: string, v: string) => void;
  setParam: (k: string, v: string | null) => void; onReset: () => void;
}) {
  const has = (k: string, v: string) => (sp.get(k) ?? '').split(',').includes(v);
  const box = (k: string, v: string, label: ReactNode) => (
    <label key={v} className="tv-check"><input type="checkbox" checked={has(k, v)} onChange={() => toggle(k, v)} /> {label}</label>
  );
  return (
    <div className="tv-filters">
      <div className="tv-filters__head"><h2 className="tv-h3">Filters</h2><button type="button" className="tv-link small" onClick={onReset}>Reset</button></div>
      <Group title="Budget per person">
        <div className="tv-row2">
          <label className="tv-mini"><span className="small">Min ₹</span><input inputMode="numeric" defaultValue={sp.get('min_price') ?? ''} placeholder={f.price.min ? String(Math.floor(Number(f.price.min))) : ''}
            onBlur={(e) => setParam('min_price', e.target.value.replace(/\D/g, '') || null)} /></label>
          <label className="tv-mini"><span className="small">Max ₹</span><input inputMode="numeric" defaultValue={sp.get('max_price') ?? ''} placeholder={f.price.max ? String(Math.ceil(Number(f.price.max))) : ''}
            onBlur={(e) => setParam('max_price', e.target.value.replace(/\D/g, '') || null)} /></label>
        </div>
      </Group>
      {s.mode === 'bus' && <Group title="Bus type">{BUS_TYPES.map(([v, l]) => box('bus_type', v, l))}</Group>}
      {s.mode === 'flight' && <Group title="Stops">{[['0', 'Non-stop'], ['1', '1 stop'], ['2', '2+ stops']].map(([v, l]) => box('stops', v!, l!))}</Group>}
      {s.mode === 'train' && (f.trainTypes?.length ?? 0) > 0 && <Group title="Train type">{f.trainTypes!.map((t) => box('train_type', t, t))}</Group>}
      <Group title="Departure">{f.departure.map((d) => box('departure', d.code, d.label))}</Group>
      <Group title="Arrival">{f.departure.map((d) => box('arrival', d.code, d.label))}</Group>
      {s.mode === 'bus' && (f.boarding?.length ?? 0) > 0 && <Group title="Boarding point">{f.boarding!.map((p) => box('boarding', p.id, p.name))}</Group>}
      {s.mode === 'bus' && (f.dropping?.length ?? 0) > 0 && <Group title="Dropping point">{f.dropping!.map((p) => box('dropping', p.id, p.name))}</Group>}
      {f.operators.length > 1 && <Group title={s.mode === 'flight' ? 'Airlines' : s.mode === 'train' ? 'Rail operator' : 'Operators'}>{f.operators.map((o) => box('operators', o.id, o.name))}</Group>}
      {f.amenities.length > 0 && <Group title="Amenities">{f.amenities.map((a) => box('amenities', a, a))}</Group>}
      <Group title="Cancellation">{CANCEL.filter(([v]) => f.cancellation.includes(v!)).map(([v, l]) => box('cancellation', v!, l))}</Group>
      {s.mode !== 'train' && (
        <Group title="Rating">{[['4', '4.0+'], ['3.5', '3.5+']].map(([v, l]) => (
          <label key={v} className="tv-check"><input type="radio" name="rating" checked={sp.get('min_rating') === v} onChange={() => setParam('min_rating', v!)} /> {l} (verified trips)</label>
        ))}{sp.get('min_rating') && <button type="button" className="tv-link small" onClick={() => setParam('min_rating', null)}>Any rating</button>}</Group>
      )}
      <Group title="More">
        <label className="tv-check"><input type="checkbox" checked={sp.get('available_only') === '1'} onChange={(e) => setParam('available_only', e.target.checked ? '1' : null)} /> {s.mode === 'train' ? 'Bookable now (incl. RAC / waitlist)' : 'Seats available'}</label>
        {s.mode === 'flight' && <label className="tv-check"><input type="checkbox" checked={sp.get('refundable') === '1'} onChange={(e) => setParam('refundable', e.target.checked ? '1' : null)} /> Refundable fares</label>}
        {s.mode === 'flight' && <label className="tv-check"><input type="checkbox" checked={sp.get('checked_bag') === '1'} onChange={(e) => setParam('checked_bag', e.target.checked ? '1' : null)} /> Checked baggage included</label>}
        <label className="tv-mini"><span className="small">Max duration (hours)</span><input inputMode="numeric" defaultValue={sp.get('max_duration') ?? ''} onBlur={(e) => setParam('max_duration', e.target.value.replace(/\D/g, '') || null)} /></label>
      </Group>
    </div>
  );
}

function EditSheet({ open, onClose, s, first, onSearch }: {
  open: boolean; onClose: () => void; s: ReturnType<typeof searchFrom>; first?: TravelSearchResult;
  onSearch: (patch: Partial<ReturnType<typeof searchFrom>>) => void;
}) {
  const [from, setFrom] = useState<TravelPlace | null>(first?.query.origin ?? null);
  const [to, setTo] = useState<TravelPlace | null>(first?.query.destination ?? null);
  const [date, setDate] = useState(s.date);
  const [pax, setPax] = useState({ adults: s.adults, children: s.children, infants: s.infants });
  const [error, setError] = useState('');
  return (
    <Sheet open={open} onClose={onClose} label="Edit search">
      <div className="tv-sheet">
        <h2>Edit search</h2>
        <PlaceField label="From" mode={s.mode} value={from ?? first?.query.origin ?? null} onPick={setFrom} />
        <button type="button" className="tv-link small" onClick={() => { const f = from ?? first?.query.origin ?? null; setFrom(to ?? first?.query.destination ?? null); setTo(f); }}><Icon name="swap" size={14} /> Swap</button>
        <PlaceField label="To" mode={s.mode} value={to ?? first?.query.destination ?? null} onPick={setTo} />
        <label className="tv-field"><span className="tv-field__label">Date</span><input className="tv-field__input" type="date" min={todayIso()} value={date} onChange={(e) => setDate(e.target.value)} /></label>
        <PaxPicker mode={s.mode} value={pax} max={s.mode === 'flight' ? 9 : 6} onChange={setPax} />
        {error && <p className="tv-error small" role="alert">{error}</p>}
        <Button block onClick={() => {
          const o = from ?? first?.query.origin, d = to ?? first?.query.destination;
          if (!o || !d) return setError('Choose From and To.');
          if (o.citySlug === d.citySlug) return setError('From and To can’t be the same city.');
          onSearch({ origin: o.slug, destination: d.slug, date, ...pax });
        }}>Search</Button>
      </div>
    </Sheet>
  );
}
