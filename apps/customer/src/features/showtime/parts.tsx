import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError, type ShowtimeTitle } from '@click/api';
import { useAuth } from '../../auth/AuthProvider';
import { Icon, Sheet, useToast } from '../../components/ui';
import { api } from '../../lib/api';

export const runtime = (m: number | null) => (m ? (m >= 60 ? `${Math.floor(m / 60)}h ${m % 60 ? `${m % 60}m` : ''}`.trim() : `${m}m`) : '');
export const timeOf = (iso: string) => new Date(iso).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' });
export const dayOf = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' });
export function dateParts(ymd: string) {
  const d = new Date(`${ymd}T12:00:00`);
  const today = new Date();
  const isToday = d.toDateString() === today.toDateString();
  const tomorrow = new Date(today.getTime() + 864e5).toDateString() === d.toDateString();
  return { top: isToday ? 'Today' : tomorrow ? 'Tmrw' : d.toLocaleDateString('en-IN', { weekday: 'short' }), day: d.getDate(), month: d.toLocaleDateString('en-IN', { month: 'short' }) };
}
export const releaseLabel = (ymd: string | null) => (ymd ? new Date(`${ymd}T12:00:00`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '');

function hue(s: string) { let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) % 360; return h; }

/**
 * A title's poster: the licensed artwork when the title has one, otherwise a typographic poster made from its own
 * title and genre (never a borrowed or generated image).
 */
export function Poster({ t, eager = false }: { t: Pick<ShowtimeTitle, 'title' | 'posterUrl' | 'genres' | 'kind'>; eager?: boolean }) {
  const [failed, setFailed] = useState(false);
  if (t.posterUrl && !failed) {
    return <div className="poster"><img src={t.posterUrl} alt={`${t.title} poster`} loading={eager ? 'eager' : 'lazy'} decoding="async" onError={() => setFailed(true)} /></div>;
  }
  const h = hue(t.title);
  return (
    <div className="poster" role="img" aria-label={`${t.title} (no artwork)`}>
      <div className="poster__type" style={{ ['--p-a' as string]: `hsl(${h} 45% 16%)`, ['--p-rgb' as string]: `${120 + (h % 120)} ${30 + (h % 40)} ${60 + (h % 80)}` }}>
        <span className="poster__kind">{t.kind === 'event' ? 'Live' : 'Showtime'}</span>
        <span className="poster__title">{t.title}</span>
        <span className="poster__genre">{t.genres.slice(0, 2).join(' · ')}</span>
      </div>
    </div>
  );
}

export function Formats({ formats }: { formats: string[] }) {
  if (!formats.length) return null;
  return <span className="tcard__formats">{formats.map((f) => <span key={f} className={`fmt fmt--${f.toLowerCase()}`}>{f}</span>)}</span>;
}

/** Poster card. `mode` changes the secondary line: next show, release date (coming soon), trailer play, tonight. */
export function TitleCard({ t, mode = 'default', onPlay }: { t: ShowtimeTitle & { tonightCount?: number; tonightFirst?: string; nearestKm?: number | null }; mode?: 'default' | 'coming' | 'trailer' | 'tonight'; onPlay?: () => void }) {
  const meta = [t.languages.slice(0, 2).join(', '), t.genres[0]].filter(Boolean).join(' · ');
  const inner = (
    <>
      <div className="tcard__poster">
        <Poster t={t} />
        {mode === 'coming' && t.releaseDate && <span className="tcard__badge">{releaseLabel(t.releaseDate)}</span>}
        {mode !== 'coming' && t.certification && <span className="tcard__badge">{t.certification}</span>}
        {t.rating !== null && <span className="tcard__rating"><Icon name="star" size={10} /> {t.rating.toFixed(1)}</span>}
        {mode === 'trailer' && <span className="tcard__play" aria-hidden="true"><span><Icon name="play" size={20} /></span></span>}
      </div>
      <span className="tcard__title">{t.title}</span>
      <span className="tcard__meta">{meta}{t.durationMinutes ? ` · ${runtime(t.durationMinutes)}` : ''}</span>
      {mode === 'tonight' && t.tonightFirst ? (
        <span className="tcard__meta"><strong>From {timeOf(t.tonightFirst)}</strong> · {t.tonightCount} show{t.tonightCount === 1 ? '' : 's'}{t.nearestKm != null ? ` · ${t.nearestKm} km` : ''}</span>
      ) : mode === 'coming' ? <span className="tcard__meta">{t.bookable ? 'Booking open' : 'Coming soon'}</span> : <Formats formats={t.formats} />}
    </>
  );
  if (mode === 'trailer' && onPlay) {
    return <button type="button" className="tcard" style={{ background: 'none', border: 0, padding: 0, textAlign: 'left', font: 'inherit', cursor: 'pointer' }}
      onClick={onPlay} aria-label={`Play trailer: ${t.title}`}>{inner}</button>;
  }
  return <Link to={`/showtime/${t.slug}`} className={`tcard ${mode === 'tonight' ? 'tcard--tonight' : ''}`} aria-label={`${t.title}${t.rating !== null ? `, rated ${t.rating}` : ''}`}>{inner}</Link>;
}

/** Plays a title's licensed trailer (an MP4/WebM file). Credit/licence shown under the video. */
export function TrailerSheet({ t, onClose }: { t: Pick<ShowtimeTitle, 'title' | 'trailerUrl' | 'mediaCredit' | 'slug'> | null; onClose: () => void }) {
  return (
    <Sheet open={!!t} onClose={onClose} label={t ? `Trailer: ${t.title}` : 'Trailer'}>
      {t && (
        <div className="stack st-trailer" data-theme="movies">
          <div className="spread"><h2>{t.title}</h2><button className="icon-btn" aria-label="Close trailer" onClick={onClose}><Icon name="close" /></button></div>
          <video src={t.trailerUrl} controls autoPlay playsInline preload="metadata" />
          {t.mediaCredit && <p className="small muted">{t.mediaCredit}</p>}
          <Link to={`/showtime/${t.slug}`} className="btn btn--primary" onClick={onClose}>See showtimes</Link>
        </div>
      )}
    </Sheet>
  );
}

/** "I'm interested": stored on the server; one notification when booking opens. */
export function InterestButton({ t, onChange }: { t: Pick<ShowtimeTitle, 'slug' | 'title' | 'interested'>; onChange?: (on: boolean) => void }) {
  const { status } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const qc = useQueryClient();
  const toast = useToast();
  const [on, setOn] = useState(!!t.interested);
  const m = useMutation({
    mutationFn: (next: boolean) => api.showtime.interest(t.slug, next),
    onSuccess: (r) => {
      setOn(r.interested); onChange?.(r.interested);
      toast(r.interested ? `We’ll tell you when booking opens for ${t.title}` : 'Removed from your interests');
      qc.invalidateQueries({ queryKey: ['showtime'] });
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t update that.', 'error'),
  });
  return (
    <button type="button" className={`st-btn ${on ? 'st-btn--book' : 'st-btn--ghost'}`} aria-pressed={on} disabled={m.isPending}
      onClick={() => (status === 'authenticated' ? m.mutate(!on) : navigate(`/login?next=${encodeURIComponent(location.pathname)}`))}>
      <Icon name={on ? 'check' : 'bell'} size={16} /> {on ? 'Interested' : 'I’m interested'}
    </button>
  );
}

export function SectionHead({ title, subtitle, link, linkLabel = 'See all' }: { title: string; subtitle?: string | null; link?: string | null; linkLabel?: string }) {
  return (
    <div className="st-sec__head">
      <div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
      {link && <Link to={link} className="st-sec__link">{linkLabel} <Icon name="right" size={14} /></Link>}
    </div>
  );
}
