import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ApiError, type Show } from '@click/api';
import { EmptyState, ErrorState, Icon, Rating, Skeleton, SmartImage } from '../components/ui';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

const dayKey = (iso: string) => new Date(iso).toLocaleDateString('en-CA');
const dayLabel = (key: string) => {
  const d = new Date(`${key}T00:00:00`);
  const today = new Date().toLocaleDateString('en-CA');
  const tomorrow = new Date(Date.now() + 864e5).toLocaleDateString('en-CA');
  return { top: key === today ? 'Today' : key === tomorrow ? 'Tomorrow' : d.toLocaleDateString('en-IN', { weekday: 'short' }), bottom: d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }) };
};

export function EventPage() {
  const { slug = '' } = useParams();
  const event = useQuery({ queryKey: ['events', 'detail', slug], queryFn: () => api.events.get(slug) });
  const days = useMemo(() => [...new Set((event.data?.shows ?? []).map((s) => dayKey(s.startsAt)))], [event.data]);
  const [day, setDay] = useState<string | null>(null);
  const activeDay = day ?? days[0] ?? null;
  const byVenue = useMemo(() => {
    const m = new Map<string, { venue: Show['venue']; shows: Show[] }>();
    for (const s of event.data?.shows ?? []) {
      if (dayKey(s.startsAt) !== activeDay) continue;
      const entry = m.get(s.venue.id) ?? { venue: s.venue, shows: [] };
      entry.shows.push(s);
      m.set(s.venue.id, entry);
    }
    return [...m.values()];
  }, [event.data, activeDay]);

  if (event.isError) {
    return event.error instanceof ApiError && event.error.status === 404
      ? <EmptyState icon="ticket" title="Show not found" action={<Link className="btn btn--outline" to="/movies">Browse movies</Link>} />
      : <ErrorState error={event.error} onRetry={() => event.refetch()} />;
  }
  if (event.isPending) return <div className="stack"><Skeleton height={300} radius={22} /><Skeleton height={120} /></div>;
  const e = event.data;

  return (
    <div className="stack">
      <Link to="/movies" className="phead__back"><Icon name="back" size={18} /> Movies & Events</Link>
      <section className="event-hero">
        <SmartImage src={e.posterUrl} alt={e.title} className="event-hero__poster" />
        <div className="stack" style={{ gap: 'var(--s-2)' }}>
          <h1>{e.title}</h1>
          {e.tagline && <p className="event-hero__tagline">{e.tagline}</p>}
          <div className="row" style={{ flexWrap: 'wrap' }}>
            {e.status === 'now_showing' && <Rating value={e.ratingAverage} count={e.ratingCount} />}
            {e.certification && <span className="badge">{e.certification}</span>}
            {e.durationMinutes && <span className="badge">{Math.floor(e.durationMinutes / 60)}h {e.durationMinutes % 60}m</span>}
            {e.languages.map((l) => <span key={l} className="badge">{l}</span>)}
          </div>
          <span className="small event-hero__meta">{e.genres.join(' · ')}{e.cast && ` · ${e.cast}`}</span>
          {e.description && <p className="event-hero__desc">{e.description}</p>}
        </div>
      </section>

      {e.shows.length === 0 ? (
        <EmptyState icon="ticket" title={e.status === 'coming_soon' ? 'Bookings open closer to release' : 'No upcoming shows'}
          message={e.status === 'coming_soon' && e.releaseDate ? `Releases ${new Date(e.releaseDate).toLocaleDateString('en-IN', { day: 'numeric', month: 'long' })}.` : 'Check back later for new showtimes.'} />
      ) : (
        <>
          <section className="stack" style={{ gap: 'var(--s-2)' }}>
            <h2>Choose a date</h2>
            <div className="chips" role="tablist" aria-label="Show date">
              {days.map((d) => { const l = dayLabel(d); return (
                <button key={d} role="tab" aria-selected={activeDay === d} className="date-chip" onClick={() => setDay(d)}><span className="small">{l.top}</span><strong>{l.bottom}</strong></button>
              ); })}
            </div>
          </section>
          <section className="stack">
            <h2>Venues & showtimes</h2>
            {byVenue.map(({ venue, shows }) => (
              <div key={venue.id} className="card card--pad stack" style={{ gap: 'var(--s-3)' }}>
                <div><strong>{venue.name}</strong><div className="small muted">{[venue.locality, venue.city].filter(Boolean).join(', ')}</div></div>
                <div className="row" style={{ flexWrap: 'wrap' }}>
                  {shows.map((s) => (
                    <Link key={s.id} to={`/shows/${s.id}`} className={`showtime ${s.seatsLeft !== null && s.seatsLeft <= 10 ? 'showtime--low' : ''}`} aria-label={`${new Date(s.startsAt).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' })}, ${s.format}, ${s.seatsLeft} seats left, from ${formatMoney(s.price, s.currency)}`}>
                      <strong>{new Date(s.startsAt).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' })}</strong>
                      <span className="small">{s.format}{s.language && ` · ${s.language}`}</span>
                      {s.seatsLeft !== null && s.seatsLeft <= 10 && <span className="small">{s.seatsLeft === 0 ? 'Sold out' : `${s.seatsLeft} left`}</span>}
                    </Link>
                  ))}
                </div>
              </div>
            ))}
          </section>
        </>
      )}
    </div>
  );
}
