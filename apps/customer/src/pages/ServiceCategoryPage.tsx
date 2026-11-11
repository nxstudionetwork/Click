import { useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Button, EmptyState, ErrorState, Icon, Sheet, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { catIcon, PRICING_HINT, ProCardView, Section } from '../features/pros/parts';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';
import { useDeliveryLocation } from '../location/LocationProvider';

const SORTS = [
  ['recommended', 'Recommended'], ['available', 'Earliest available'], ['nearest', 'Nearest'], ['rating', 'Highest rated'],
  ['experience', 'Most experienced'], ['price', 'Lowest price'],
] as const;
const FILTER_KEYS = ['available_now', 'verified', 'min_rating', 'min_experience', 'max_price', 'max_km'] as const;

/** One service (e.g. Plumbing): common jobs with their pricing model, then the real professionals who do it near the
 *  selected address, with filters and sort. Choosing a job re-prices every card for that job. */
export function ServiceCategoryPage() {
  useThemeOverride('services');
  const { slug = '' } = useParams();
  const [sp, setSp] = useSearchParams();
  const { selected } = useDeliveryLocation();
  const job = sp.get('job');
  const sort = sp.get('sort') ?? 'recommended';
  const params: Record<string, string | undefined> = { address: selected?.id, job: job ?? undefined, sort };
  for (const k of FILTER_KEYS) params[k] = sp.get(k) ?? undefined;
  const q = useQuery({ queryKey: ['services', 'category', slug, params], queryFn: () => api.services.category(slug, params), placeholderData: (prev) => prev });
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const set = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(sp);
    for (const [k, v] of Object.entries(patch)) { if (v) next.set(k, v); else next.delete(k); }
    setSp(next, { replace: true });
  };
  const activeFilters = FILTER_KEYS.filter((k) => sp.get(k)).length;
  const c = q.data;
  const selectedJob = c?.jobs.find((j) => j.id === job) ?? null;

  if (q.isError) return <div className="sv-page"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  if (!c) return <div className="sv-page"><Skeleton height={160} radius={22} /><Skeleton height={300} radius={22} /></div>;

  const openFilters = () => { setDraft(Object.fromEntries(FILTER_KEYS.map((k) => [k, sp.get(k) ?? '']))); setFiltersOpen(true); };
  return (
    <div className="sv-page" data-theme="services" style={{ ['--sv-accent' as string]: c.accent }}>
      <Link to="/services" className="sv-back"><Icon name="back" size={18} /> Services</Link>
      <header className="sv-cathead">
        <span className="sv-cat__icon sv-cat__icon--lg"><Icon name={catIcon(c.icon)} size={30} /></span>
        <div><span className="sv-kicker">{c.groupLabel}</span><h1>{c.name}</h1><p className="sv-muted">{c.summary}</p></div>
      </header>

      <Section title="What do you need?" kicker="Common jobs">
        <div className="sv-jobs" role="radiogroup" aria-label="Choose a job">
          {c.jobs.map((j) => (
            <button key={j.id} type="button" role="radio" aria-checked={j.id === job} className={`sv-job${j.id === job ? ' is-on' : ''}`}
              onClick={() => set({ job: j.id === job ? null : j.id })}>
              <span className="sv-job__name"><strong>{j.name}</strong>{j.instant && <span className="sv-chip">Same day</span>}</span>
              <span className="small sv-muted">{j.description}</span>
              <span className="sv-job__price">{j.priceLabel}<span className="small sv-muted"> · {j.pricingLabel}</span></span>
            </button>
          ))}
        </div>
        {selectedJob && (
          <div className="sv-jobinfo">
            <p className="small"><Icon name="receipt" size={14} /> {PRICING_HINT[selectedJob.pricing]}{selectedJob.inspectionFee ? ` Inspection/visit fee ${formatMoney(selectedJob.inspectionFee)} if you decline the quote.` : ''}</p>
            {selectedJob.includes.length > 0 && <p className="small"><strong>Includes:</strong> {selectedJob.includes.join(' · ')}</p>}
            {selectedJob.excludes.length > 0 && <p className="small sv-muted"><strong>Not included:</strong> {selectedJob.excludes.join(' · ')}</p>}
            <Link to={`/services/book?job=${selectedJob.id}&category=${c.slug}`} className="sv-btn">Book any available {c.profession.toLowerCase()}</Link>
          </div>
        )}
      </Section>

      {c.offers.length > 0 && <div className="sv-offers">{c.offers.map((o) => <div key={o.id} className="sv-offer"><Icon name="tag" size={18} /><span><strong>{o.title}</strong><span className="small sv-muted">{o.description}</span></span></div>)}</div>}

      <section className="sv-sec">
        <header className="sv-sec__head">
          <div><span className="sv-kicker">{c.hasLocation ? 'Serving your address' : 'Choose an address to see who serves it'}</span><h2>{c.profession}s</h2></div>
        </header>
        <div className="sv-toolbar">
          <label className="sv-select"><Icon name="sort" size={16} /><span className="sr-only">Sort</span>
            <select value={sort} onChange={(e) => set({ sort: e.target.value === 'recommended' ? null : e.target.value })}>
              {SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <button type="button" className={`sv-chipbtn${sp.get('available_now') ? ' is-on' : ''}`} aria-pressed={!!sp.get('available_now')}
            onClick={() => set({ available_now: sp.get('available_now') ? null : 'true' })}>Available now</button>
          <button type="button" className={`sv-chipbtn${sp.get('verified') ? ' is-on' : ''}`} aria-pressed={!!sp.get('verified')}
            onClick={() => set({ verified: sp.get('verified') ? null : 'true' })}>Verified</button>
          <button type="button" className="sv-chipbtn" onClick={openFilters}><Icon name="filter" size={14} /> Filters{activeFilters ? ` (${activeFilters})` : ''}</button>
        </div>
        {c.professionals.length === 0 ? (
          <EmptyState icon="user" title={activeFilters ? 'No professional matches these filters' : `No ${c.profession.toLowerCase()} serves this address yet`}
            message={activeFilters ? 'Clear a filter to see more.' : 'Tell Click what you need and we’ll look for someone.'}
            action={activeFilters ? <Button variant="secondary" onClick={() => set(Object.fromEntries(FILTER_KEYS.map((k) => [k, null])))}>Clear filters</Button>
              : <Link to="/services/request" className="btn btn--primary">Tell Click what you need</Link>} />
        ) : (
          <div className="sv-prolist" aria-busy={q.isFetching}>{c.professionals.map((p) => <ProCardView key={p.id} p={p} job={job} wide />)}</div>
        )}
      </section>

      <Sheet open={filtersOpen} onClose={() => setFiltersOpen(false)} label="Filters">
        <div className="sv-sheet">
          <h2>Filters</h2>
          <label className="sv-field">Minimum rating
            <select value={draft.min_rating ?? ''} onChange={(e) => setDraft({ ...draft, min_rating: e.target.value })}>
              <option value="">Any</option><option value="4">4.0+</option><option value="4.5">4.5+</option>
            </select>
          </label>
          <label className="sv-field">Experience
            <select value={draft.min_experience ?? ''} onChange={(e) => setDraft({ ...draft, min_experience: e.target.value })}>
              <option value="">Any</option><option value="3">3+ years</option><option value="5">5+ years</option><option value="10">10+ years</option>
            </select>
          </label>
          <label className="sv-field">Maximum price (₹)
            <input inputMode="numeric" value={draft.max_price ?? ''} onChange={(e) => setDraft({ ...draft, max_price: e.target.value.replace(/\D/g, '') })} placeholder="Any" />
          </label>
          <label className="sv-field">Distance
            <select value={draft.max_km ?? ''} onChange={(e) => setDraft({ ...draft, max_km: e.target.value })} disabled={!c.hasLocation}>
              <option value="">Any</option><option value="3">Within 3 km</option><option value="5">Within 5 km</option><option value="10">Within 10 km</option>
            </select>
          </label>
          <label className="sv-check"><input type="checkbox" checked={draft.available_now === 'true'} onChange={(e) => setDraft({ ...draft, available_now: e.target.checked ? 'true' : '' })} /> Available now</label>
          <label className="sv-check"><input type="checkbox" checked={draft.verified === 'true'} onChange={(e) => setDraft({ ...draft, verified: e.target.checked ? 'true' : '' })} /> Verified only</label>
          <div className="sv-sheet__actions">
            <Button variant="secondary" onClick={() => { set(Object.fromEntries(FILTER_KEYS.map((k) => [k, null]))); setFiltersOpen(false); }}>Clear</Button>
            <Button onClick={() => { set(Object.fromEntries(FILTER_KEYS.map((k) => [k, draft[k] || null]))); setFiltersOpen(false); }}>Show results</Button>
          </div>
        </div>
      </Sheet>
    </div>
  );
}
