import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { LiveCard, LiveEpisode } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { useThemeOverride } from '../components/layout/AppShell';
import { BackBar } from '../components/layout/BackBar';
import { EmptyState, ErrorState, Icon, Skeleton, useToast } from '../components/ui';
import { api } from '../lib/api';

/**
 * Click. Live: series episode by episode, films and live channels, watched inside Click. (Showtime books cinema seats;
 * this is for watching). Continue-watching and the watchlist are the viewer's own; progress is saved as they watch.
 */
export function LivePage() {
  useThemeOverride('live');
  const { status } = useAuth();
  const home = useQuery({ queryKey: ['live', 'home', status], queryFn: api.live.home, enabled: status !== 'loading' });
  const [q, setQ] = useState('');
  const [term, setTerm] = useState('');
  useEffect(() => { const t = setTimeout(() => setTerm(q.trim()), 300); return () => clearTimeout(t); }, [q]);
  const search = useQuery({ queryKey: ['live', 'search', term], queryFn: () => api.live.search(term), enabled: term.length >= 2 });
  const h = home.data;
  return (
    <div className="lv-page" data-theme="live">
      <header className="svc-intro">
        <h1>Live</h1>
        <p>Series, films and live streams. One Click. away.</p>
      </header>

      {home.isError ? <ErrorState error={home.error} onRetry={() => home.refetch()} /> : !h ? <Skeleton height={300} radius={26} /> : (
        <>
          {h.featured && <Featured card={h.featured} />}
          <div className="svc-search" role="search">
            <Icon name="search" size={20} className="svc-search__lead" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search series, films and episodes" aria-label="Search Live" enterKeyHint="search" />
            {q && <button type="button" className="gsearch__tool" aria-label="Clear text" onClick={() => setQ('')}><Icon name="close" size={18} /></button>}
          </div>
          {term.length >= 2 ? (
            <section className="lv-sec" aria-live="polite">
              <h2>Results for “{term}”</h2>
              {search.isPending ? <Skeleton height={180} /> : (search.data?.results.length ?? 0) === 0
                ? <p className="small muted">Nothing matches. Try a title, a genre or an episode name.</p>
                : <div className="lv-rail">{search.data!.results.map((c) => <PosterCard key={c.slug} c={c} />)}</div>}
            </section>
          ) : (
            <>
              {h.live.length > 0 && (
                <section className="lv-sec" aria-labelledby="lv-live-h">
                  <h2 id="lv-live-h"><span className="lv-dot" aria-hidden="true" /> Live now</h2>
                  <div className="lv-rail">{h.live.map((ch) => (
                    <Link key={ch.slug} to={`/live/channel/${ch.slug}`} className="lv-channel" style={{ ['--acc' as string]: ch.accent }}>
                      <span className="lv-badge">LIVE</span>
                      <strong>{ch.name}</strong>
                      <span className="small">{ch.nowPlaying || ch.category}</span>
                    </Link>
                  ))}</div>
                </section>
              )}
              {h.continueWatching.length > 0 && (
                <section className="lv-sec" aria-labelledby="lv-cw-h">
                  <h2 id="lv-cw-h">Continue watching</h2>
                  <div className="lv-rail">{h.continueWatching.map((c) => (
                    <Link key={c.slug} to={`/live/watch/${c.episode.id}`} className="lv-cw" style={{ ['--acc' as string]: c.accent }}>
                      <span className="lv-cw__art"><Icon name="play" size={26} /></span>
                      <strong>{c.title}</strong>
                      <span className="small">{c.kind === 'film' ? 'Film' : `S${c.episode.season} E${c.episode.number} · ${c.episode.name}`}</span>
                      <span className="lv-bar"><span style={{ width: `${c.percent}%` }} /></span>
                    </Link>
                  ))}</div>
                </section>
              )}
              {h.watchlist.length > 0 && (
                <section className="lv-sec"><h2>Your watchlist</h2><div className="lv-rail">{h.watchlist.map((c) => <PosterCard key={c.slug} c={c} />)}</div></section>
              )}
              {h.rails.map((r) => (
                <section key={r.id} className="lv-sec"><h2>{r.title}</h2><div className="lv-rail">{r.items.map((c) => <PosterCard key={c.slug} c={c} />)}</div></section>
              ))}
              {h.rails.length === 0 && h.live.length === 0 && <EmptyState icon="tv" title="Nothing to watch yet" message="Series, films and live channels from Click. partners will appear here." />}
            </>
          )}
        </>
      )}
    </div>
  );
}

function Featured({ card }: { card: LiveCard }) {
  return (
    <section className="lv-hero" style={{ ['--acc' as string]: card.accent }} aria-label={`Featured: ${card.title}`}>
      <span className="lv-kicker">{card.kindLabel} · {card.maturity}</span>
      <h2>{card.title}</h2>
      <p>{card.synopsis}</p>
      <span className="lv-meta">{[card.year, card.genres.slice(0, 2).join(' · '), card.language].filter(Boolean).join(' · ')}</span>
      <Link to={`/live/t/${card.slug}`} className="btn lv-play"><Icon name="play" size={18} /> Watch now</Link>
    </section>
  );
}

function PosterCard({ c }: { c: LiveCard }) {
  return (
    <Link to={`/live/t/${c.slug}`} className="lv-poster" style={{ ['--acc' as string]: c.accent }} aria-label={`${c.title}, ${c.kindLabel}`}>
      {c.posterUrl ? <img src={c.posterUrl} alt="" loading="lazy" /> : <span className="lv-poster__type"><span className="lv-poster__kind">{c.kindLabel}</span><strong>{c.title}</strong></span>}
      <span className="lv-poster__foot small">{c.maturity}{c.episodes && c.kind !== 'film' ? ` · ${c.episodes} episodes` : c.year ? ` · ${c.year}` : ''}</span>
    </Link>
  );
}

const mins = (s: number) => (s >= 3600 ? `${Math.floor(s / 3600)}h ${Math.round((s % 3600) / 60)}m` : `${Math.max(1, Math.round(s / 60))} min`);

/** /live/t/:slug — a series or film: seasons, episodes with your progress, watchlist. */
export function LiveTitlePage() {
  useThemeOverride('live');
  const { slug = '' } = useParams();
  const { status } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const t = useQuery({ queryKey: ['live', 'title', slug, status], queryFn: () => api.live.title(slug), enabled: status !== 'loading' });
  const [season, setSeason] = useState(1);
  const save = useMutation({
    mutationFn: () => api.live.watchlist(slug),
    onSuccess: (r) => { toast(r.inWatchlist ? 'Added to your watchlist' : 'Removed from your watchlist'); void qc.invalidateQueries({ queryKey: ['live'] }); },
  });
  if (t.isError) return <ErrorState error={t.error} onRetry={() => t.refetch()} />;
  if (!t.data) return <Skeleton height={420} radius={26} />;
  const d = t.data;
  const eps = d.seasons.find((s) => s.number === season)?.episodes ?? d.seasons[0]?.episodes ?? [];
  const next = d.playNext;
  return (
    <div className="lv-page" data-theme="live">
      <BackBar fallback="/live" />
      <section className="lv-hero lv-hero--title" style={{ ['--acc' as string]: d.accent }}>
        <span className="lv-kicker">{d.kindLabel} · {d.maturity}</span>
        <h1>{d.title}</h1>
        <span className="lv-meta">{[d.year, d.genres.join(' · '), d.language].filter(Boolean).join(' · ')}</span>
        <p>{d.synopsis}</p>
        <div className="lv-actions">
          {next && <Link to={`/live/watch/${next.id}`} className="btn lv-play"><Icon name="play" size={18} />
            {next.progress && !next.progress.finished ? 'Resume' : d.kind === 'film' ? 'Watch film' : `Play S${next.season} E${next.number}`}</Link>}
          <button type="button" className={`btn lv-ghost ${d.inWatchlist ? 'is-on' : ''}`} aria-pressed={d.inWatchlist}
            onClick={() => (status === 'authenticated' ? save.mutate() : navigate(`/login?next=/live/t/${slug}`))}>
            <Icon name={d.inWatchlist ? 'check' : 'plus'} size={18} /> {d.inWatchlist ? 'In watchlist' : 'Watchlist'}
          </button>
        </div>
        {d.credits && <p className="lv-credits small">{d.credits}</p>}
      </section>
      {d.kind !== 'film' && (
        <section className="lv-sec" aria-labelledby="lv-eps-h">
          <div className="spread"><h2 id="lv-eps-h">Episodes</h2>
            {d.seasons.length > 1 && <select value={season} onChange={(e) => setSeason(Number(e.target.value))} aria-label="Season">
              {d.seasons.map((s) => <option key={s.number} value={s.number}>{s.name}</option>)}</select>}</div>
          <ol className="lv-eps">{eps.map((e) => <EpisodeRow key={e.id} e={e} accent={d.accent} />)}</ol>
        </section>
      )}
    </div>
  );
}

function EpisodeRow({ e, accent }: { e: LiveEpisode; accent: string }) {
  const pct = e.progress ? Math.min(100, Math.round((100 * e.progress.positionSeconds) / Math.max(1, e.durationSeconds))) : 0;
  return (
    <li>
      <Link to={`/live/watch/${e.id}`} className="lv-ep" style={{ ['--acc' as string]: accent }}>
        <span className="lv-ep__art"><Icon name="play" size={20} /><span className="lv-ep__n">E{e.number}</span></span>
        <span className="lv-ep__text"><strong>{e.name}</strong><span className="small muted">{mins(e.durationSeconds)}{e.progress?.finished ? ' · Watched' : ''}</span>
          {e.synopsis && <span className="small lv-ep__syn">{e.synopsis}</span>}
          {pct > 0 && !e.progress?.finished && <span className="lv-bar"><span style={{ width: `${pct}%` }} /></span>}</span>
      </Link>
    </li>
  );
}

/** Plays MP4 natively and HLS (.m3u8) natively on Safari or through hls.js elsewhere. */
function useVideoSource(video: React.RefObject<HTMLVideoElement | null>, url: string | null | undefined, startAt = 0) {
  const [error, setError] = useState(false);
  useEffect(() => {
    const v = video.current;
    if (!v || !url) return;
    setError(false);
    let hls: { destroy: () => void } | null = null;
    const seek = () => { if (startAt > 0) v.currentTime = startAt; };
    v.addEventListener('loadedmetadata', seek, { once: true });
    const isHls = /\.m3u8(\?|$)/.test(url);
    if (!isHls || v.canPlayType('application/vnd.apple.mpegurl')) {
      v.src = url;
    } else {
      void import('hls.js').then(({ default: Hls }) => {
        if (!Hls.isSupported()) { setError(true); return; }
        const h = new Hls({ enableWorker: true });
        h.on(Hls.Events.ERROR, (_e, data) => { if (data.fatal) setError(true); });
        h.loadSource(url);
        h.attachMedia(v);
        hls = h;
      }).catch(() => setError(true));
    }
    const onErr = () => setError(true);
    v.addEventListener('error', onErr);
    return () => { v.removeEventListener('error', onErr); v.removeEventListener('loadedmetadata', seek); hls?.destroy(); v.removeAttribute('src'); v.load(); };
  }, [url, startAt]); // eslint-disable-line react-hooks/exhaustive-deps
  return error;
}

/** /live/watch/:id — the player. Resumes where you stopped, saves progress every few seconds, offers the next episode. */
export function LiveWatchPage() {
  useThemeOverride('live');
  const { id = '' } = useParams();
  const { status } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const play = useQuery({ queryKey: ['live', 'play', id, status], queryFn: () => api.live.play(id), enabled: status !== 'loading', staleTime: Infinity });
  const video = useRef<HTMLVideoElement>(null);
  const [ended, setEnded] = useState(false);
  const failed = useVideoSource(video, play.data?.videoUrl, play.data?.resumeAt ?? 0);
  const lastSaved = useRef(0);

  // Progress: every 10 seconds of playback, on pause and when leaving.
  useEffect(() => {
    const v = video.current;
    if (!v || status !== 'authenticated' || !play.data) return;
    const save = () => {
      if (!v.duration || Number.isNaN(v.duration)) return;
      lastSaved.current = Date.now();
      void api.live.progress(id, Math.floor(v.currentTime), Math.floor(v.duration)).then(() => qc.invalidateQueries({ queryKey: ['live', 'home'] })).catch(() => undefined);
    };
    const onTime = () => { if (Date.now() - lastSaved.current > 10_000) save(); };
    const onEnd = () => { save(); setEnded(true); };
    v.addEventListener('timeupdate', onTime);
    v.addEventListener('pause', save);
    v.addEventListener('ended', onEnd);
    return () => { save(); v.removeEventListener('timeupdate', onTime); v.removeEventListener('pause', save); v.removeEventListener('ended', onEnd); };
  }, [id, status, play.data]); // eslint-disable-line react-hooks/exhaustive-deps

  if (play.isError) return <ErrorState error={play.error} onRetry={() => play.refetch()} />;
  if (!play.data) return <Skeleton height={260} radius={20} />;
  const p = play.data;
  return (
    <div className="lv-page lv-watch" data-theme="live">
      <BackBar fallback={`/live/t/${p.title.slug}`}><span>{p.title.title}</span></BackBar>
      <div className="lv-player">
        <video ref={video} controls autoPlay playsInline preload="metadata" aria-label={`${p.title.title}: ${p.episode.name}`} />
        {failed && <div className="lv-player__err" role="alert"><Icon name="alert" size={22} /><span>This video can’t play right now. Check your connection and try again.</span></div>}
      </div>
      <section className="lv-now">
        <span className="lv-kicker">{p.title.kind === 'film' ? 'Film' : `Season ${p.episode.season} · Episode ${p.episode.number}`}</span>
        <h1>{p.episode.name}</h1>
        {p.episode.synopsis && <p>{p.episode.synopsis}</p>}
        {p.resumeAt > 0 && <p className="small muted">Resumed from {mins(p.resumeAt)}.</p>}
        {p.next && (
          <button type="button" className={`lv-next ${ended ? 'is-ready' : ''}`} onClick={() => navigate(`/live/watch/${p.next!.id}`)}>
            <span className="small">{ended ? 'Up next' : 'Next episode'}</span><strong>E{p.next.number} · {p.next.name}</strong><Icon name="right" size={18} />
          </button>
        )}
        {p.credits && <p className="lv-credits small muted">{p.credits}</p>}
        {status !== 'authenticated' && <p className="small muted"><Link to={`/login?next=/live/watch/${id}`}>Sign in</Link> to continue where you left off on any device.</p>}
      </section>
    </div>
  );
}

/** /live/channel/:slug — a live channel. */
export function LiveChannelPage() {
  useThemeOverride('live');
  const { slug = '' } = useParams();
  const ch = useQuery({ queryKey: ['live', 'channel', slug], queryFn: () => api.live.channel(slug), refetchInterval: 60_000 });
  const video = useRef<HTMLVideoElement>(null);
  const failed = useVideoSource(video, ch.data?.streamUrl);
  if (ch.isError) return <ErrorState error={ch.error} onRetry={() => ch.refetch()} />;
  if (!ch.data) return <Skeleton height={260} radius={20} />;
  const c = ch.data;
  return (
    <div className="lv-page lv-watch" data-theme="live">
      <BackBar fallback="/live"><span>{c.name}</span></BackBar>
      <div className="lv-player">
        {c.streamUrl ? <video ref={video} controls autoPlay muted playsInline aria-label={`${c.name}, live`} />
          : <div className="lv-player__err"><Icon name="tv" size={22} /><span>{c.name} isn’t broadcasting right now.</span></div>}
        {failed && <div className="lv-player__err" role="alert"><Icon name="alert" size={22} /><span>The stream can’t play right now. Try again shortly.</span></div>}
        {c.isLive && <span className="lv-badge lv-badge--on">LIVE</span>}
      </div>
      <section className="lv-now">
        <span className="lv-kicker">{c.category}</span>
        <h1>{c.name}</h1>
        {c.nowPlaying && <p><strong>Now:</strong> {c.nowPlaying}</p>}
        {c.description && <p className="small muted">{c.description}</p>}
      </section>
    </div>
  );
}
