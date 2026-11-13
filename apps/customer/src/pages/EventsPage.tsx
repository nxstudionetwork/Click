import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../auth/AuthProvider';
import { EmptyState, ErrorState, Icon, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { servicePhoto } from '../config/media';
import { evIcon, fmtDate, LiveEventCard, PackageCardView, ProviderCardView, ProviderMark, Section } from '../features/events/parts';
import { api } from '../lib/api';
import { LocationSelector } from '../location/LocationSelector';
import { useDeliveryLocation } from '../location/LocationProvider';

/**
 * Click. Events: plan your own event (the main flow) and discover events to attend. Event teams, venues, packages and
 * services are real Click. Events records; live events are Click. Showtime's, opened in Showtime to book.
 */
export function EventsPage() {
  useThemeOverride('events');
  const { status } = useAuth();
  const { selected } = useDeliveryLocation();
  const address = selected?.id ?? null;
  const authed = status === 'authenticated';
  const home = useQuery({ queryKey: ['eventhub', 'home', address], queryFn: () => api.eventHub.home(address), staleTime: 60_000 });
  const plans = useQuery({ queryKey: ['eventhub', 'plans'], queryFn: () => api.eventHub.plans(), enabled: authed });
  const upcoming = useQuery({ queryKey: ['eventhub', 'bookings', 'active'], queryFn: () => api.eventHub.bookings('active'), enabled: authed });
  const [q, setQ] = useState('');
  const [debounced, setDebounced] = useState('');
  useEffect(() => { const t = setTimeout(() => setDebounced(q.trim()), 250); return () => clearTimeout(t); }, [q]);
  const search = useQuery({ queryKey: ['eventhub', 'search', debounced, address], queryFn: () => api.eventHub.search(debounced, address), enabled: debounced.length > 1 });
  const photo = servicePhoto('movies');
  const d = home.data;
  const s = search.data;
  const openPlans = (plans.data?.results ?? []).filter((p) => p.status === 'planning' || p.status === 'booked');
  const nothing = s && s.eventTypes.length + s.services.length + s.providers.length + s.packages.length + s.liveEvents.length === 0;

  return (
    <div className="ev-page" data-theme="events">
      <header className="ev-hero">
        {photo && <img className="ev-hero__img" src={photo.src} srcSet={photo.srcSet} sizes="(min-width: 900px) 60vw, 100vw" alt="" />}
        <div className="ev-hero__text">
          <span className="ev-kicker">Click. Events</span>
          <h1>Events<span>.</span></h1>
          <p className="ev-hero__tag">Make every moment worth remembering.</p>
          <p className="ev-hero__sub">Plan it. Find the right team. Make it happen.</p>
          <div className="ev-hero__cta">
            <Link to="/events/plan" className="ev-btn ev-btn--big"><Icon name="sparkle" size={18} /> Plan an Event</Link>
            <a href="#ev-live" className="ev-btn ev-btn--ghost ev-btn--big">Explore Events</a>
          </div>
        </div>
      </header>

      <div className="ev-where"><LocationSelector /></div>

      <div className="ev-search" role="search">
        <Icon name="search" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search events, planners, venues & services" aria-label="Search events, planners, venues and services" />
        {q && <button type="button" className="ev-search__clear" aria-label="Clear search" onClick={() => setQ('')}><Icon name="close" size={16} /></button>}
      </div>
      {debounced.length > 1 && (
        <div className="ev-results" aria-live="polite">
          {search.isPending ? <Skeleton height={80} /> : search.isError ? <ErrorState error={search.error} onRetry={() => search.refetch()} /> : nothing ? (
            <p className="small ev-muted">Nothing matches “{debounced}”. <Link to={`/events/plan?note=${encodeURIComponent(debounced)}`} className="ev-link">Plan it with us anyway</Link>.</p>
          ) : s && (
            <>
              {s.eventTypes.map((t) => <Link key={t.slug} to={`/events/plan?type=${t.slug}`} className="ev-result"><Icon name={evIcon(t.icon)} size={18} /><span><strong>Plan a {t.name.toLowerCase()}</strong><span className="small ev-muted">{t.summary}</span></span></Link>)}
              {s.services.map((x) => <Link key={x.slug} to={`/events/teams?service=${x.slug}`} className="ev-result"><Icon name={evIcon(x.icon)} size={18} /><span><strong>{x.name}</strong><span className="small ev-muted">Teams and specialists</span></span></Link>)}
              {s.providers.slice(0, 5).map((p) => <Link key={p.id} to={`/events/providers/${p.id}`} className="ev-result"><ProviderMark p={p} size={32} /><span><strong>{p.name}</strong><span className="small ev-muted">{p.kindLabel} · {p.area}{p.priceFrom ? ` · ${p.priceFrom.label}` : ''}</span></span></Link>)}
              {s.packages.slice(0, 4).map((x) => <Link key={x.id} to={`/events/providers/${x.provider?.id}#packages`} className="ev-result"><Icon name="gift" size={18} /><span><strong>{x.name}</strong><span className="small ev-muted">{x.provider?.name} · {x.priceLabel}</span></span></Link>)}
              {s.liveEvents.slice(0, 4).map((e) => <Link key={e.slug} to={e.path} className="ev-result"><Icon name="ticket" size={18} /><span><strong>{e.title}</strong><span className="small ev-muted">{e.venue} · {fmtDate(e.startsAt)}</span></span></Link>)}
            </>
          )}
        </div>
      )}

      {home.isError ? <ErrorState error={home.error} onRetry={() => home.refetch()} /> : (
        <nav className="ev-types" aria-label="Plan by event type">
          {home.isPending ? Array.from({ length: 8 }, (_, i) => <Skeleton key={i} width={96} height={100} radius={20} />) : d!.eventTypes.map((t) => (
            <Link key={t.slug} to={`/events/plan?type=${t.slug}`} className="ev-type" style={{ ['--ev-accent' as string]: t.accent }}>
              <span className="ev-type__icon"><Icon name={evIcon(t.icon)} size={22} /></span><span className="ev-type__name">{t.name}</span>
            </Link>
          ))}
        </nav>
      )}

      <section className="ev-plan" aria-labelledby="ev-plan-h">
        <div className="ev-plan__glow" aria-hidden="true" />
        <div>
          <span className="ev-kicker">Plan your event</span>
          <h2 id="ev-plan-h">Plan Your Event</h2>
          <p>Tell us what you’re planning. We’ll help you find the right people and services.</p>
          <ol className="ev-plan__steps">
            <li><Icon name="edit" size={14} /> Share the date, place, guests and what you need</li>
            <li><Icon name="team" size={14} /> See teams and venues that can actually take it</li>
            <li><Icon name="receipt" size={14} /> Compare quotes, then book and pay through Click.</li>
          </ol>
        </div>
        <Link to="/events/plan" className="ev-btn ev-btn--big">Start Planning</Link>
      </section>

      {authed && (openPlans.length > 0 || (upcoming.data?.results.length ?? 0) > 0) && (
        <Section title="Your events" kicker="In progress" action={<Link to="/events/mine" className="ev-more">All</Link>}>
          <div className="ev-mine">
            {upcoming.data?.results.slice(0, 2).map((b) => (
              <Link key={b.id} to={`/events/bookings/${b.id}`} className="ev-minecard" style={{ ['--ev-accent' as string]: b.provider.accent }}>
                <span className="ev-kicker">{fmtDate(b.eventDate)} · {b.statusLabel}</span><strong>{b.title}</strong><span className="small ev-muted">{b.guests} guests · {b.number}</span>
              </Link>
            ))}
            {openPlans.slice(0, 2).map((p) => (
              <Link key={p.id} to={`/events/plans/${p.id}`} className="ev-minecard" style={{ ['--ev-accent' as string]: p.eventType.accent }}>
                <span className="ev-kicker">{p.dateFlexible ? 'Flexible date' : fmtDate(p.date)} · Plan</span><strong>{p.title}</strong>
                <span className="small ev-muted">{p.guests} guests{p.quotesWaiting ? ` · ${p.quotesWaiting} quote${p.quotesWaiting > 1 ? 's' : ''} waiting` : ''}</span>
              </Link>
            ))}
          </div>
        </Section>
      )}

      {home.isPending ? <><Skeleton height={260} radius={22} /><Skeleton height={260} radius={22} /></> : d && (
        <>
          <Section id="ev-live" title="Upcoming events" kicker="Concerts, comedy, workshops · on Click. Showtime"
            action={<Link to="/showtime/search?kind=event" className="ev-more">See all</Link>}>
            {d.liveEvents.length === 0 ? <EmptyState icon="ticket" title="No live events scheduled right now" message="New shows appear here as soon as venues publish them." /> : (
              <div className="ev-rail">{d.liveEvents.map((e) => <LiveEventCard key={e.slug} e={e} />)}</div>
            )}
          </Section>

          {d.teams.length + d.venues.length === 0 ? (
            <EmptyState icon="gift" title="No event teams serve this area yet" message="Start a plan anyway — we’ll show teams and venues as they join." action={<Link to="/events/plan" className="btn btn--primary">Start planning</Link>} />
          ) : (
            <>
              <Section title="Event teams" kicker={d.featured.length ? 'Featured and top rated' : 'Near you'} action={<Link to="/events/teams" className="ev-more">All {d.counts.teams}</Link>}>
                <div className="ev-rail">{[...d.featured, ...d.teams.filter((t) => !t.featured)].slice(0, 10).map((p) => <ProviderCardView key={p.id} p={p} />)}</div>
              </Section>
              {d.packages.length > 0 && (
                <Section title="Event packages" kicker="Clear inclusions, real prices" action={<Link to="/events/teams?view=packages" className="ev-more">All {d.counts.packages}</Link>}>
                  <div className="ev-rail ev-rail--pkg">{d.packages.slice(0, 12).map((pkg) => (
                    <PackageCardView key={pkg.id} pkg={pkg} showProvider action={<Link to={`/events/book?package=${pkg.id}`} className="ev-btn ev-btn--sm">Book</Link>} />
                  ))}</div>
                </Section>
              )}
              {d.venues.length > 0 && (
                <Section title="Venues" kicker="Halls, lawns, rooftops and studios" action={<Link to="/events/venues" className="ev-more">All {d.counts.venues}</Link>}>
                  <div className="ev-rail">{d.venues.map((p) => <ProviderCardView key={p.id} p={p} />)}</div>
                </Section>
              )}
            </>
          )}

          <Section title="Find by service" kicker="Specialists and full teams">
            <div className="ev-services">{d.services.map((x) => (
              <Link key={x.slug} to={x.slug === 'venue' ? '/events/venues' : `/events/teams?service=${x.slug}`} className="ev-service"><Icon name={evIcon(x.icon)} size={18} /><span>{x.name}</span></Link>
            ))}</div>
          </Section>
        </>
      )}
      {authed && <Link to="/events/mine" className="ev-link small" style={{ alignSelf: 'center' }}>My events and bookings</Link>}
    </div>
  );
}
