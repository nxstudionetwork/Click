import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { ShowtimeSection, ShowtimeTitle } from '@click/api';
import { ErrorState, Icon, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { InterestButton, Poster, SectionHead, TitleCard, TrailerSheet, runtime } from '../features/showtime/parts';
import { ShowtimeSearchField } from '../features/showtime/ShowtimeSearch';
import { api } from '../lib/api';
import { useDeliveryLocation } from '../location/LocationProvider';

/**
 * Click. Showtime: cinema and live shows. Order: title + line, featured title, Show Highlights, search, quick
 * filters, then only sections with real content (tonight, now showing, coming soon, trending, top rated, trailers,
 * live), cinemas near the active location, special formats, offers and Plan your night.
 */
export function ShowtimePage() {
  useThemeOverride('movies');
  const { point } = useDeliveryLocation();
  const home = useQuery({ queryKey: ['showtime', 'home', point], queryFn: () => api.showtime.home(point ?? undefined), staleTime: 60_000 });
  const [trailer, setTrailer] = useState<ShowtimeTitle | null>(null);
  const d = home.data;

  return (
    <div className="st-page" data-theme="movies">
      <header className="st-intro">
        <h1>Showtime<span>.</span></h1>
        <p>Your next story starts here.</p>
      </header>

      {home.isError ? <ErrorState error={home.error} onRetry={() => home.refetch()} /> : home.isPending ? (
        <><Skeleton height={340} radius={24} /><div className="st-rail">{Array.from({ length: 5 }, (_, i) => <Skeleton key={i} height={250} radius={16} />)}</div></>
      ) : (
        <>
          {d!.featured && <Featured f={d!.featured} onTrailer={() => setTrailer(d!.featured)} />}

          {d!.highlights.length > 0 && (
            <section className="st-sec" aria-label="Show Highlights">
              <SectionHead title="Show Highlights" subtitle="What everyone’s booking and talking about." />
              <div className="st-rail st-rail--highlights">{d!.highlights.map((t) => <TitleCard key={t.id} t={t} />)}</div>
            </section>
          )}

          <ShowtimeSearchField />

          {(d!.filters.languages.length > 0 || d!.filters.formats.length > 0) && (
            <nav className="st-filters" aria-label="Quick filters">
              {d!.filters.formats.filter((f) => f !== '2D').map((f) => <Link key={f} to={`/showtime/search?format=${f}`} className="chip">{f}</Link>)}
              {d!.filters.languages.slice(0, 8).map((l) => <Link key={l} to={`/showtime/search?language=${encodeURIComponent(l)}`} className="chip">{l}</Link>)}
              {d!.filters.genres.slice(0, 8).map((g) => <Link key={g} to={`/showtime/search?genre=${encodeURIComponent(g)}`} className="chip">{g}</Link>)}
            </nav>
          )}

          {d!.sections.map((s) => <Section key={s.id} s={s} onTrailer={setTrailer} />)}

          {d!.cinemas.length > 0 && (
            <section className="st-sec" aria-label="Cinemas near you">
              <SectionHead title={d!.locationUsed ? 'Cinemas Near You' : 'Cinemas'}
                subtitle={d!.locationUsed ? 'Nearest first, from your selected location.' : 'Choose a location on Home to see distances.'} />
              <div className="st-cinemas">
                {d!.cinemas.slice(0, 6).map((c) => (
                  <Link key={c.id} to={`/showtime/search?q=${encodeURIComponent(c.name)}`} className="st-cinema">
                    <div className="st-cinema__top"><strong>{c.name}</strong>{c.distanceKm != null && <span className="st-cinema__dist">{c.distanceKm} km</span>}</div>
                    <span className="small muted">{c.locality}{c.showsToday ? ` · ${c.showsToday} shows today` : ''}</span>
                    <span className="tcard__formats">{c.formats.map((f) => <span key={f} className={`fmt fmt--${f.toLowerCase()}`}>{f}</span>)}{c.sound.map((s) => <span key={s} className="fmt">{s}</span>)}</span>
                    {c.nextShow && <span className="small">Next: <strong>{c.nextShow.title}</strong> · {new Date(c.nextShow.startsAt).toLocaleString('en-IN', { weekday: 'short', hour: 'numeric', minute: '2-digit' })}</span>}
                    {c.facilities.length > 0 && <span className="st-facilities">{c.facilities.map((f) => <span key={f}>{f}</span>)}</span>}
                  </Link>
                ))}
              </div>
            </section>
          )}

          {d!.formats.length > 0 && (
            <section className="st-sec" aria-label="Watch it bigger">
              <SectionHead title="Watch It Bigger" subtitle="Premium formats playing near you." />
              <div className="st-formats">
                {d!.formats.map((f) => (
                  <Link key={f.code} to={f.code === 'atmos' ? '/showtime/search?q=dolby atmos' : `/showtime/search?format=${f.code}`} className="st-format">
                    <strong>{f.label}</strong><span>{f.titleCount} show{f.titleCount === 1 ? '' : 's'} · {f.venueCount} cinema{f.venueCount === 1 ? '' : 's'}</span>
                  </Link>
                ))}
              </div>
            </section>
          )}

          {d!.offers.length > 0 && (
            <section className="st-sec" aria-label="Offers">
              <SectionHead title="Offers" subtitle="Applied and checked by Click. at checkout." />
              <div className="st-offers">
                {d!.offers.map((o) => (
                  <div key={o.id} className="st-offer"><strong>{o.title}</strong>{o.description && <span>{o.description}</span>}
                    {o.venue && <span>At {o.venue}</span>}{o.endsAt && <span>Until {new Date(o.endsAt).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}</span>}</div>
                ))}
              </div>
            </section>
          )}

          <PlanYourNight />
        </>
      )}
      <TrailerSheet t={trailer} onClose={() => setTrailer(null)} />
    </div>
  );
}

function Featured({ f, onTrailer }: { f: NonNullable<import('@click/api').ShowtimeHome['featured']>; onTrailer: () => void }) {
  const art = f.backdropUrl || f.posterUrl;
  return (
    <section className="st-hero" aria-label={`Featured: ${f.title}`}>
      {art && <div className="st-hero__art"><img src={art} alt="" /></div>}
      <div className="st-hero__body">
        <div className="st-hero__poster"><Poster t={f} eager /></div>
        <div>
          <span className="st-hero__eyebrow">{f.headline || (f.status === 'coming_soon' ? 'Coming soon' : 'Featured')}</span>
          <h2 className="st-hero__title">{f.title}</h2>
          <div className="st-meta">
            {f.genres.slice(0, 2).join(' • ')}
            {f.durationMinutes ? <span className="dot">{runtime(f.durationMinutes)}</span> : null}
            {f.certification && <span className="st-cert">{f.certification}</span>}
            {f.rating !== null && <span className="st-rating"><Icon name="star" size={13} /> {f.rating.toFixed(1)}</span>}
          </div>
          <div className="st-meta" style={{ marginTop: 4 }}>{f.languages.join(' • ')}</div>
          <div className="st-hero__ctas">
            {f.trailerUrl && <button type="button" className="st-btn st-btn--ghost" onClick={onTrailer}><Icon name="play" size={16} /> Watch trailer</button>}
            {f.bookable ? <Link to={`/showtime/${f.slug}#times`} className="st-btn st-btn--book"><Icon name="ticket" size={16} /> Book now</Link>
              : <InterestButton t={f} />}
          </div>
          {f.mediaCredit && <p className="st-credit" style={{ marginTop: 8 }}>{f.mediaCredit}</p>}
        </div>
      </div>
    </section>
  );
}

function Section({ s, onTrailer }: { s: ShowtimeSection; onTrailer: (t: ShowtimeTitle) => void }) {
  const mode = s.kind === 'coming' ? 'coming' : s.kind === 'trailers' ? 'trailer' : s.kind === 'tonight' ? 'tonight' : 'default';
  return (
    <section className="st-sec" aria-label={s.title}>
      <SectionHead title={s.title} subtitle={s.subtitle} link={s.link} />
      <div className="st-rail">
        {s.titles.map((t) => <TitleCard key={t.id} t={t} mode={mode} onPlay={mode === 'trailer' ? () => onTrailer(t) : undefined} />)}
      </div>
    </section>
  );
}

/** Click.'s evening: each step is the customer's own choice (nothing is booked or paid automatically). */
function PlanYourNight() {
  return (
    <section className="st-plan" aria-label="Plan your night">
      <h2 style={{ color: '#fff' }}>Plan Your Night</h2>
      <p>Book a show, then get a ride to the cinema and something to eat, all on Click. You confirm every step.</p>
      <div className="st-plan__steps">
        <a href="#top" className="st-plan__step" onClick={(e) => { e.preventDefault(); window.scrollTo({ top: 0, behavior: 'smooth' }); }}><span><Icon name="ticket" size={18} /></span>Book a show</a>
        <Link to="/food" className="st-plan__step"><span><Icon name="food" size={18} /></span>Grab a bite</Link>
        <Link to="/rides" className="st-plan__step"><span><Icon name="ride" size={18} /></span>Ride there</Link>
      </div>
    </section>
  );
}
