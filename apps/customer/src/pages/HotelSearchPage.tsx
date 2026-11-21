import { useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import type { StayQuery } from '@click/api';
import { Button, EmptyState, ErrorState, Icon, Sheet, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { addDays, fmtDay, GuestsPicker, HotelCardView, nightsOf, partyLabel, stayFrom, stayQs, todayIso } from '../features/hotels/parts';
import { api } from '../lib/api';

const LISTS = ['type', 'stars', 'amenities', 'room_class'] as const;
const FLAGS = ['breakfast', 'free_cancellation', 'pay_at_property'] as const;
const VALUES = ['min_price', 'max_price', 'min_rating', 'near', 'max_km'] as const;
const FILTER_KEYS = [...LISTS, ...FLAGS, ...VALUES];

/** Results for a destination and stay. Every filter and sort is applied on the server; prices are for these dates. */
export function HotelSearchPage() {
  useThemeOverride('hotels');
  const [sp, setSp] = useSearchParams();
  const navigate = useNavigate();
  const stay = stayFrom(sp);
  const destination = sp.get('destination') ?? '';
  const meta = useQuery({ queryKey: ['hotels', 'home'], queryFn: () => api.hotels.home(), staleTime: 300_000 });
  const params = useMemo(() => {
    const p: Record<string, string | undefined> = { destination, check_in: stay.checkIn, check_out: stay.checkOut, adults: String(stay.adults),
      children: String(stay.children), rooms: String(stay.rooms), sort: sp.get('sort') ?? 'recommended' };
    for (const k of FILTER_KEYS) p[k] = sp.get(k) ?? undefined;
    return p;
  }, [sp, destination, stay.checkIn, stay.checkOut, stay.adults, stay.children, stay.rooms]);
  const q = useInfiniteQuery({
    queryKey: ['hotels', 'search', params], initialPageParam: 1, enabled: !!destination,
    queryFn: ({ pageParam }) => api.hotels.search({ ...params, page: String(pageParam) }),
    getNextPageParam: (last) => (last.hasMore ? last.page + 1 : undefined),
  });
  const first = q.data?.pages[0];
  const rows = q.data?.pages.flatMap((p) => p.results) ?? [];
  const [editOpen, setEditOpen] = useState(false);
  const [edit, setEdit] = useState<{ destination: string; stay: StayQuery }>({ destination, stay });
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [cmp, setCmp] = useState<string[]>([]);
  const active = FILTER_KEYS.filter((k) => sp.get(k)).length;
  const set = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(sp);
    for (const [k, v] of Object.entries(patch)) { if (v) next.set(k, v); else next.delete(k); }
    setSp(next, { replace: true });
  };
  const toggleList = (k: string, v: string) => {
    const cur = new Set((draft[k] || '').split(',').filter(Boolean));
    if (cur.has(v)) cur.delete(v); else cur.add(v);
    setDraft({ ...draft, [k]: [...cur].join(',') });
  };
  const f = meta.data?.filters;

  return (
    <div className="ht-page" data-theme="hotels">
      <Link to="/hotels" className="ht-back"><Icon name="back" size={18} /> Hotels</Link>
      <button type="button" className="ht-summary" onClick={() => { setEdit({ destination, stay }); setEditOpen(true); }} aria-label="Edit search">
        <span><strong>{first?.destination?.name ?? destination}</strong>
          <span className="small ht-muted">{fmtDay(stay.checkIn)} – {fmtDay(stay.checkOut)} · {nightsOf(stay)} night{nightsOf(stay) > 1 ? 's' : ''} · {partyLabel(stay)}</span></span>
        <Icon name="edit" size={16} />
      </button>

      <div className="ht-toolbar">
        <label className="ht-select"><Icon name="sort" size={16} /><span className="sr-only">Sort</span>
          <select value={sp.get('sort') ?? 'recommended'} onChange={(e) => set({ sort: e.target.value === 'recommended' ? null : e.target.value })}>
            {(f?.sorts ?? [{ value: 'recommended', label: 'Recommended' }]).map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </label>
        <button type="button" className={`ht-chipbtn${sp.get('free_cancellation') ? ' is-on' : ''}`} aria-pressed={!!sp.get('free_cancellation')}
          onClick={() => set({ free_cancellation: sp.get('free_cancellation') ? null : 'true' })}>Free cancellation</button>
        <button type="button" className={`ht-chipbtn${sp.get('breakfast') ? ' is-on' : ''}`} aria-pressed={!!sp.get('breakfast')}
          onClick={() => set({ breakfast: sp.get('breakfast') ? null : 'true' })}>Breakfast</button>
        <button type="button" className="ht-chipbtn" onClick={() => { setDraft(Object.fromEntries(FILTER_KEYS.map((k) => [k, sp.get(k) ?? '']))); setFiltersOpen(true); }}>
          <Icon name="filter" size={14} /> Filters{active ? ` (${active})` : ''}</button>
      </div>

      {!destination ? <EmptyState icon="pin" title="Where do you want to stay?" action={<Link to="/hotels" className="btn btn--primary">Search hotels</Link>} />
        : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isPending ? (
          <div className="ht-results">{Array.from({ length: 3 }, (_, i) => <Skeleton key={i} height={260} radius={24} />)}</div>
        ) : !first?.destination ? (
          <EmptyState icon="pin" title={`Click. doesn’t have stays in “${destination}” yet`} message="Try one of the destinations on the Hotels page."
            action={<Link to="/hotels" className="btn btn--primary">See destinations</Link>} />
        ) : rows.length === 0 ? (
          <EmptyState icon="hotel" title="No stays match" message={active ? 'Loosen a filter or try other dates.' : 'Everything is booked for these dates. Try other dates.'}
            action={active ? <Button variant="secondary" onClick={() => set(Object.fromEntries(FILTER_KEYS.map((k) => [k, null])))}>Clear filters</Button> : undefined} />
        ) : (
          <>
            <h1 className="ht-title">Hotels in {first.destination.name} <span className="ht-muted small">{first.count} available · distances from {first.measuredFrom}</span></h1>
            <div className="ht-results">{rows.map((h) => (
              <HotelCardView key={h.id} h={h} stay={stay} compare={cmp.includes(h.id)}
                onCompare={() => setCmp((c) => (c.includes(h.id) ? c.filter((x) => x !== h.id) : c.length >= 4 ? c : [...c, h.id]))} />
            ))}</div>
            {q.hasNextPage && <Button variant="secondary" loading={q.isFetchingNextPage} onClick={() => q.fetchNextPage()}>Show more stays</Button>}
          </>
        )}

      {cmp.length > 0 && (
        <div className="ht-cmpbar" role="region" aria-label="Compare stays">
          <span className="small">{cmp.length} selected{cmp.length < 2 ? ' · pick at least 2' : ''}</span>
          <button type="button" className="ht-link small" onClick={() => setCmp([])}>Clear</button>
          <Button disabled={cmp.length < 2} onClick={() => navigate(`/hotels/compare?ids=${cmp.join(',')}&${stayQs(stay)}`)}>Compare</Button>
        </div>
      )}

      <Sheet open={editOpen} onClose={() => setEditOpen(false)} label="Edit search">
        <div className="ht-sheet">
          <h2>Edit search</h2>
          <label className="ht-field"><span className="ht-field__label">Destination</span><input value={edit.destination} onChange={(e) => setEdit({ ...edit, destination: e.target.value })} /></label>
          <div className="ht-row2">
            <label className="ht-field"><span className="ht-field__label">Check-in</span>
              <input type="date" min={todayIso()} value={edit.stay.checkIn} onChange={(e) => { const ci = e.target.value; setEdit((x) => ({ ...x, stay: { ...x.stay, checkIn: ci, checkOut: x.stay.checkOut <= ci ? addDays(ci, 1) : x.stay.checkOut } })); }} />
            </label>
            <label className="ht-field"><span className="ht-field__label">Check-out</span>
              <input type="date" min={addDays(edit.stay.checkIn, 1)} value={edit.stay.checkOut} onChange={(e) => setEdit((x) => ({ ...x, stay: { ...x.stay, checkOut: e.target.value } }))} />
            </label>
          </div>
          <GuestsPicker value={edit.stay} onChange={(s) => setEdit((x) => ({ ...x, stay: s }))} />
          <Button block onClick={() => {
            const next = new URLSearchParams(sp);
            next.set('destination', edit.destination.trim());
            for (const [k, v] of Object.entries({ check_in: edit.stay.checkIn, check_out: edit.stay.checkOut, adults: edit.stay.adults, children: edit.stay.children, rooms: edit.stay.rooms })) next.set(k, String(v));
            next.delete('near');
            setSp(next, { replace: true });
            setEditOpen(false);
          }}>Search</Button>
        </div>
      </Sheet>

      <Sheet open={filtersOpen} onClose={() => setFiltersOpen(false)} label="Filters">
        <div className="ht-sheet">
          <h2>Filters</h2>
          <fieldset className="ht-fs"><legend>Price per night (₹)</legend>
            <div className="ht-row2">
              <input className="ht-input" inputMode="numeric" placeholder="Min" aria-label="Minimum price per night" value={draft.min_price ?? ''} onChange={(e) => setDraft({ ...draft, min_price: e.target.value.replace(/\D/g, '') })} />
              <input className="ht-input" inputMode="numeric" placeholder="Max" aria-label="Maximum price per night" value={draft.max_price ?? ''} onChange={(e) => setDraft({ ...draft, max_price: e.target.value.replace(/\D/g, '') })} />
            </div>
          </fieldset>
          <fieldset className="ht-fs"><legend>Property type</legend><div className="ht-chips">
            {f?.types.map((t) => <button key={t.value} type="button" aria-pressed={(draft.type || '').split(',').includes(t.value)} className={`ht-chipbtn${(draft.type || '').split(',').includes(t.value) ? ' is-on' : ''}`} onClick={() => toggleList('type', t.value)}>{t.label}</button>)}
          </div></fieldset>
          <fieldset className="ht-fs"><legend>Star rating</legend><div className="ht-chips">
            {[1, 2, 3, 4, 5].map((n) => <button key={n} type="button" aria-pressed={(draft.stars || '').split(',').includes(String(n))} className={`ht-chipbtn${(draft.stars || '').split(',').includes(String(n)) ? ' is-on' : ''}`} onClick={() => toggleList('stars', String(n))}>{n} ★</button>)}
          </div></fieldset>
          <fieldset className="ht-fs"><legend>Guest rating</legend><div className="ht-chips">
            {f?.guestRatings.map((g) => <button key={g.value} type="button" aria-pressed={draft.min_rating === String(g.value)} className={`ht-chipbtn${draft.min_rating === String(g.value) ? ' is-on' : ''}`} onClick={() => setDraft({ ...draft, min_rating: draft.min_rating === String(g.value) ? '' : String(g.value) })}>{g.label}</button>)}
          </div></fieldset>
          <fieldset className="ht-fs"><legend>Amenities (all of)</legend><div className="ht-chips">
            {f?.amenities.map((a) => <button key={a.slug} type="button" aria-pressed={(draft.amenities || '').split(',').includes(a.slug)} className={`ht-chipbtn${(draft.amenities || '').split(',').includes(a.slug) ? ' is-on' : ''}`} onClick={() => toggleList('amenities', a.slug)}>{a.name}</button>)}
          </div></fieldset>
          <fieldset className="ht-fs"><legend>Room</legend><div className="ht-chips">
            {f?.roomClasses.map((r) => <button key={r.value} type="button" aria-pressed={(draft.room_class || '').split(',').includes(r.value)} className={`ht-chipbtn${(draft.room_class || '').split(',').includes(r.value) ? ' is-on' : ''}`} onClick={() => toggleList('room_class', r.value)}>{r.label}</button>)}
          </div></fieldset>
          <fieldset className="ht-fs"><legend>Booking flexibility</legend>
            {([['free_cancellation', 'Free cancellation'], ['pay_at_property', 'Pay at the property'], ['breakfast', 'Breakfast included']] as const).map(([k, l]) => (
              <label key={k} className="ht-check"><input type="checkbox" checked={draft[k] === 'true'} onChange={(e) => setDraft({ ...draft, [k]: e.target.checked ? 'true' : '' })} /> {l}</label>
            ))}
          </fieldset>
          {(first?.landmarks?.length ?? 0) > 0 && (
            <fieldset className="ht-fs"><legend>Location</legend>
              <select className="ht-input" aria-label="Near" value={draft.near ?? ''} onChange={(e) => setDraft({ ...draft, near: e.target.value })}>
                <option value="">Distances from the city centre</option>
                {first!.landmarks!.map((l) => <option key={l.id} value={l.id}>Near {l.name} ({l.kindLabel})</option>)}
              </select>
              <select className="ht-input" aria-label="Within" value={draft.max_km ?? ''} onChange={(e) => setDraft({ ...draft, max_km: e.target.value })}>
                <option value="">Any distance</option><option value="2">Within 2 km</option><option value="5">Within 5 km</option><option value="10">Within 10 km</option>
              </select>
            </fieldset>
          )}
          <div className="ht-sheet__actions">
            <Button variant="secondary" onClick={() => { set(Object.fromEntries(FILTER_KEYS.map((k) => [k, null]))); setFiltersOpen(false); }}>Clear all</Button>
            <Button onClick={() => { set(Object.fromEntries(FILTER_KEYS.map((k) => [k, draft[k] || null]))); setFiltersOpen(false); }}>Show stays</Button>
          </div>
        </div>
      </Sheet>
    </div>
  );
}
