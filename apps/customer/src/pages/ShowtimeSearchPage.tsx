import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { EmptyState, ErrorState, Icon, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { TitleCard } from '../features/showtime/parts';
import { ShowtimeSearchField } from '../features/showtime/ShowtimeSearch';
import { api } from '../lib/api';
import { useDeliveryLocation } from '../location/LocationProvider';

const WHEN = [{ id: 'today', label: 'Today' }, { id: 'tonight', label: 'Tonight' }, { id: 'tomorrow', label: 'Tomorrow' }, { id: 'weekend', label: 'This weekend' }];

/** Showtime search and browse (filters live in the URL). Shows what the search understood. */
export function ShowtimeSearchPage() {
  useThemeOverride('movies');
  const [params, setParams] = useSearchParams();
  const { point } = useDeliveryLocation();
  const query: Record<string, string> = {};
  params.forEach((v, k) => { query[k] = v; });
  const res = useQuery({ queryKey: ['showtime', 'search', query, point], queryFn: () => api.showtime.search({ ...query, lat: point?.lat, lng: point?.lng }) });
  const home = useQuery({ queryKey: ['showtime', 'home', point], queryFn: () => api.showtime.home(point ?? undefined), staleTime: 60_000 });
  const toggle = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (next.get(key) === value) next.delete(key); else next.set(key, value);
    setParams(next, { replace: true });
  };
  const q = params.get('q') ?? '';
  const d = res.data;
  const filters = home.data?.filters;
  const heading = q ? `Results for “${q}”` : params.get('kind') === 'event' ? 'Live shows' : params.get('status') === 'now_showing' ? 'Now Showing'
    : params.get('when') === 'tonight' ? 'Tonight' : 'Browse shows';

  return (
    <div className="st-page" data-theme="movies">
      <Link to="/showtime" className="btn btn--ghost btn--sm" style={{ alignSelf: 'flex-start', paddingLeft: 4, color: 'var(--c-ink-2)' }}><Icon name="back" size={18} /> Showtime</Link>
      <ShowtimeSearchField initial={q} />
      <header className="stack" style={{ gap: 6 }}>
        <h1 style={{ fontSize: 'clamp(1.4rem, 4vw, 2rem)' }}>{heading}</h1>
        {d && d.understood.length > 0 && (
          <div className="st-understood" aria-label="What search understood">Understood: {d.understood.map((u) => <span key={u.label}>{u.label}</span>)}</div>
        )}
      </header>
      <nav className="st-filters" aria-label="When">
        <span className="st-filter-label">When</span>
        {WHEN.map((w) => <button key={w.id} type="button" className="chip" aria-pressed={params.get('when') === w.id} onClick={() => toggle('when', w.id)}>{w.label}</button>)}
      </nav>
      {filters && (
        <>
          {filters.formats.length > 1 && <nav className="st-filters" aria-label="Format"><span className="st-filter-label">Format</span>
            {filters.formats.map((f) => <button key={f} type="button" className="chip" aria-pressed={params.get('format') === f} onClick={() => toggle('format', f)}>{f}</button>)}</nav>}
          <nav className="st-filters" aria-label="Language"><span className="st-filter-label">Language</span>
            {filters.languages.map((l) => <button key={l} type="button" className="chip" aria-pressed={params.get('language') === l} onClick={() => toggle('language', l)}>{l}</button>)}</nav>
          <nav className="st-filters" aria-label="Genre"><span className="st-filter-label">Genre</span>
            {filters.genres.slice(0, 16).map((g) => <button key={g} type="button" className="chip" aria-pressed={params.get('genre') === g} onClick={() => toggle('genre', g)}>{g}</button>)}</nav>
        </>
      )}

      {res.isError ? <ErrorState error={res.error} onRetry={() => res.refetch()} /> : res.isPending ? (
        <div className="st-grid">{Array.from({ length: 8 }, (_, i) => <Skeleton key={i} height={260} radius={16} />)}</div>
      ) : (
        <>
          {d!.people.length > 0 && (
            <section className="st-sec" aria-label="Cast and crew">
              <h2 style={{ fontSize: 'var(--fs-lg)' }}>Cast & crew</h2>
              <div className="chips">{d!.people.map((p) => <Link key={p.name} to={`/showtime/search?q=${encodeURIComponent(p.name)}`} className="chip">{p.name} · {p.titleCount}</Link>)}</div>
            </section>
          )}
          {d!.cinemas.length > 0 && (
            <section className="st-sec" aria-label="Cinemas">
              <h2 style={{ fontSize: 'var(--fs-lg)' }}>Cinemas</h2>
              <div className="st-cinemas">{d!.cinemas.map((c) => (
                <div key={c.id} className="st-cinema"><div className="st-cinema__top"><strong>{c.name}</strong>{c.distanceKm != null && <span className="st-cinema__dist">{c.distanceKm} km</span>}</div>
                  <span className="small muted">{c.address}, {c.locality}</span>
                  <span className="tcard__formats">{c.formats.map((f) => <span key={f} className="fmt">{f}</span>)}</span></div>))}</div>
            </section>
          )}
          {d!.count === 0 ? (
            <EmptyState icon="film" title="We couldn’t find that show." message="Try another word, fewer filters, or see what’s playing."
              action={<div className="row" style={{ flexWrap: 'wrap', justifyContent: 'center' }}>
                {[...params.keys()].length > 1 && <Link to={q ? `/showtime/search?q=${encodeURIComponent(q)}` : '/showtime/search'} className="btn btn--outline">Clear filters</Link>}
                <Link to="/showtime" className="btn btn--primary">See what’s playing</Link></div>} />
          ) : (
            <section className="st-sec" aria-label="Shows">
              <p className="small muted" role="status">{d!.count} show{d!.count === 1 ? '' : 's'}</p>
              <div className="st-grid">{d!.titles.map((t) => <TitleCard key={t.id} t={t} mode={t.status === 'coming_soon' ? 'coming' : 'default'} />)}</div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
