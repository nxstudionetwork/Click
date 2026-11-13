import { Link } from 'react-router-dom';
import type { ClickEvent } from '@click/api';
import { Rating, SmartImage } from '../../components/ui';

export function EventCard({ event }: { event: ClickEvent }) {
  return (
    <Link to={`/showtime/${event.slug}`} className="event-card">
      <SmartImage src={event.posterUrl} alt={event.title} className="event-card__poster">
        {event.certification && <span className="event-card__cert">{event.certification}</span>}
        {event.kind === 'event' && <span className="event-card__kind">Live</span>}
      </SmartImage>
      <div className="event-card__body">
        <strong className="event-card__title">{event.title}</strong>
        <span className="small muted truncate">{event.genres.join(' · ')}</span>
        <div className="row small" style={{ gap: 6 }}>
          {event.status === 'coming_soon'
            ? <span className="badge">{event.releaseDate ? `Releases ${new Date(event.releaseDate).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}` : 'Coming soon'}</span>
            : <Rating value={event.ratingAverage} count={event.ratingCount} />}
        </div>
      </div>
    </Link>
  );
}

