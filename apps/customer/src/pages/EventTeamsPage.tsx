import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { Button, EmptyState, ErrorState, Icon, Sheet, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { PackageCardView, ProviderCardView } from '../features/events/parts';
import { api } from '../lib/api';
import { useDeliveryLocation } from '../location/LocationProvider';

const SORTS = [['recommended', 'Recommended'], ['rating', 'Highest rated'], ['nearest', 'Nearest'], ['price', 'Lowest price'], ['experience', 'Most experienced']] as const;
const FILTERS = ['type', 'service', 'date', 'guests', 'max_budget', 'min_rating', 'verified', 'available'] as const;

/** Event teams, specialists and venues (/events/teams, /events/venues) with filters that change the server's results,
 *  plus every package. `date` + `available` uses the providers' real blocked dates and bookings. */
export function EventTeamsPage({ venues = false }: { venues?: boolean }) {
  useThemeOverride('events');
  const [sp, setSp] = useSearchParams();
  const { selected } = useDeliveryLocation();
  const registry = useQuery({ queryKey: ['eventhub', 'registry'], queryFn: () => api.eventHub.registry(), staleTime: 300_000 });
  const view = venues ? 'venues' : sp.get('view') === 'packages' ? 'packages' : 'teams';
  const params: Record<string, string | undefined> = { address: selected?.id, sort: sp.get('sort') ?? undefined, kind: venues ? 'venue' : sp.get('kind') ?? undefined, q: sp.get('q') ?? undefined };
  for (const k of FILTERS) params[k] = sp.get(k) ?? undefined;
  const list = useInfiniteQuery({
    queryKey: ['eventhub', 'providers', params], enabled: view !== 'packages', initialPageParam: 1,
    queryFn: ({ pageParam }) => api.eventHub.providers({ ...params, page: String(pageParam) }),
    getNextPageParam: (last) => (last.hasMore ? last.page + 1 : undefined),
  });
  const home = useQuery({ queryKey: ['eventhub', 'home', selected?.id ?? null], queryFn: () => api.eventHub.home(selected?.id), enabled: view === 'packages' });
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const set = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(sp);
    for (const [k, v] of Object.entries(patch)) { if (v) next.set(k, v); else next.delete(k); }
    setSp(next, { replace: true });
  };
  const active = FILTERS.filter((k) => sp.get(k)).length;
  const rows = list.data?.pages.flatMap((p) => p.results) ?? [];
  const count = list.data?.pages[0]?.count ?? 0;
  const dateQ = sp.get('date') ? `?date=${sp.get('date')}${sp.get('guests') ? `&guests=${sp.get('guests')}` : ''}` : '';
  const pkgs = (home.data?.packages ?? []).filter((x) => (!sp.get('type') || x.eventTypes.includes(sp.get('type')!)) && (!sp.get('guests') || (x.minGuests <= +sp.get('guests')! && +sp.get('guests')! <= x.maxGuests)));

  return (
    <div className="ev-page" data-theme="events">
      <Link to="/events" className="ev-back"><Icon name="back" size={18} /> Events</Link>
      <h1 className="ev-title">{venues ? 'Venues' : view === 'packages' ? 'Event packages' : 'Event teams & specialists'}</h1>
      {!venues && (
        <div className="ev-seg" role="tablist" aria-label="Browse">
          <button type="button" role="tab" aria-selected={view === 'teams'} onClick={() => set({ view: null })}>Teams</button>
          <Link to="/events/venues" role="tab" aria-selected={false}>Venues</Link>
          <button type="button" role="tab" aria-selected={view === 'packages'} onClick={() => set({ view: 'packages' })}>Packages</button>
        </div>
      )}

      <div className="ev-toolbar">
        {view !== 'packages' && (
          <label className="ev-select"><Icon name="sort" size={16} /><span className="sr-only">Sort</span>
            <select value={sp.get('sort') ?? 'recommended'} onChange={(e) => set({ sort: e.target.value === 'recommended' ? null : e.target.value })}>
              {SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
        )}
        <label className="ev-select"><Icon name="gift" size={16} /><span className="sr-only">Event type</span>
          <select value={sp.get('type') ?? ''} onChange={(e) => set({ type: e.target.value || null })}>
            <option value="">All events</option>{registry.data?.eventTypes.map((t) => <option key={t.slug} value={t.slug}>{t.name}</option>)}
          </select>
        </label>
        {view !== 'packages' && <button type="button" className={`ev-chipbtn${sp.get('verified') ? ' is-on' : ''}`} aria-pressed={!!sp.get('verified')} onClick={() => set({ verified: sp.get('verified') ? null : 'true' })}>Verified</button>}
        {view !== 'packages' && <button type="button" className="ev-chipbtn" onClick={() => { setDraft(Object.fromEntries(FILTERS.map((k) => [k, sp.get(k) ?? '']))); setOpen(true); }}><Icon name="filter" size={14} /> Filters{active ? ` (${active})` : ''}</button>}
      </div>

      {view === 'packages' ? (
        home.isError ? <ErrorState error={home.error} onRetry={() => home.refetch()} /> : home.isPending ? <Skeleton height={300} radius={22} /> : pkgs.length === 0 ? (
          <EmptyState icon="gift" title="No packages match" message="Try another event type, or start a plan and ask teams for a quote." action={<Link to="/events/plan" className="btn btn--primary">Start planning</Link>} />
        ) : <div className="ev-grid">{pkgs.map((pkg) => <PackageCardView key={pkg.id} pkg={pkg} showProvider action={<Link to={`/events/book?package=${pkg.id}`} className="ev-btn ev-btn--sm">Book</Link>} />)}</div>
      ) : list.isError ? <ErrorState error={list.error} onRetry={() => list.refetch()} /> : list.isPending ? (
        <div className="ev-grid">{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} height={300} radius={22} />)}</div>
      ) : rows.length === 0 ? (
        <EmptyState icon={venues ? 'hotel' : 'team'} title={active ? 'Nobody matches these filters' : venues ? 'No venues in this area yet' : 'No event teams in this area yet'}
          message={active ? 'Clear a filter to see more.' : 'Start a plan and we’ll show you who can take it as teams join.'}
          action={active ? <Button variant="secondary" onClick={() => set(Object.fromEntries(FILTERS.map((k) => [k, null])))}>Clear filters</Button> : <Link to="/events/plan" className="btn btn--primary">Start planning</Link>} />
      ) : (
        <>
          <p className="small ev-muted" aria-live="polite">{count} {venues ? `venue${count === 1 ? '' : 's'}` : `team${count === 1 ? '' : 's'} and specialist${count === 1 ? '' : 's'}`}{sp.get('date') ? ` · availability for ${sp.get('date')}` : ''}</p>
          <div className="ev-grid">{rows.map((p) => <ProviderCardView key={p.id} p={p} query={dateQ} />)}</div>
          {list.hasNextPage && <Button variant="secondary" loading={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>Show more</Button>}
        </>
      )}

      <Sheet open={open} onClose={() => setOpen(false)} label="Filters">
        <div className="ev-sheet">
          <h2>Filters</h2>
          <label className="ev-field">Service
            <select value={draft.service ?? ''} onChange={(e) => setDraft({ ...draft, service: e.target.value })}>
              <option value="">Any service</option>{registry.data?.services.map((s) => <option key={s.slug} value={s.slug}>{s.name}</option>)}
            </select>
          </label>
          <label className="ev-field">Event date
            <input type="date" value={draft.date ?? ''} min={new Date().toISOString().slice(0, 10)} onChange={(e) => setDraft({ ...draft, date: e.target.value })} />
          </label>
          <label className="ev-check"><input type="checkbox" checked={draft.available === 'true'} disabled={!draft.date} onChange={(e) => setDraft({ ...draft, available: e.target.checked ? 'true' : '' })} /> Only those free on that date</label>
          <label className="ev-field">Guests
            <input inputMode="numeric" value={draft.guests ?? ''} placeholder="Any" onChange={(e) => setDraft({ ...draft, guests: e.target.value.replace(/\D/g, '') })} />
          </label>
          <label className="ev-field">Budget (starting price up to, ₹)
            <input inputMode="numeric" value={draft.max_budget ?? ''} placeholder="Any" onChange={(e) => setDraft({ ...draft, max_budget: e.target.value.replace(/\D/g, '') })} />
          </label>
          <label className="ev-field">Rating
            <select value={draft.min_rating ?? ''} onChange={(e) => setDraft({ ...draft, min_rating: e.target.value })}>
              <option value="">Any</option><option value="4">4.0+</option><option value="4.5">4.5+</option>
            </select>
          </label>
          <label className="ev-check"><input type="checkbox" checked={draft.verified === 'true'} onChange={(e) => setDraft({ ...draft, verified: e.target.checked ? 'true' : '' })} /> Verified only</label>
          <div className="ev-sheet__actions">
            <Button variant="secondary" onClick={() => { set(Object.fromEntries(FILTERS.map((k) => [k, null]))); setOpen(false); }}>Clear</Button>
            <Button onClick={() => { set(Object.fromEntries(FILTERS.map((k) => [k, draft[k] || null]))); setOpen(false); }}>Show results</Button>
          </div>
        </div>
      </Sheet>
    </div>
  );
}
