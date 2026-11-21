import { useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type ShowtimeTitleDetail } from '@click/api';
import { Button, EmptyState, ErrorState, Icon, Skeleton, TextArea, useConfirm, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { InterestButton, Poster, SectionHead, TitleCard, TrailerSheet, dateParts, releaseLabel, runtime, timeOf } from '../features/showtime/parts';
import { api } from '../lib/api';
import { formatDateTime, formatMoney } from '../lib/format';
import { useDeliveryLocation } from '../location/LocationProvider';

/** A title's page: details, trailer, cast & crew, showtimes for one day at a time (nearest cinemas first), reviews. */
export function ShowtimeTitlePage() {
  useThemeOverride('movies');
  const { slug = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const { point } = useDeliveryLocation();
  const q = { date: params.get('date') ?? undefined, format: params.get('format') ?? undefined, language: params.get('language') ?? undefined,
    lat: point?.lat, lng: point?.lng };
  const title = useQuery({ queryKey: ['showtime', 'title', slug, q], queryFn: () => api.showtime.title(slug, q), placeholderData: keepPreviousData });
  const [trailer, setTrailer] = useState(false);
  const set = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    setParams(next, { replace: true });
  };

  if (title.isError) {
    return title.error instanceof ApiError && title.error.status === 404
      ? <div className="st-page"><EmptyState icon="film" title="This show isn’t available" message="It may have finished its run." action={<Link className="btn btn--primary" to="/showtime">See what’s playing</Link>} /></div>
      : <div className="st-page"><ErrorState error={title.error} onRetry={() => title.refetch()} /></div>;
  }
  if (title.isPending) return <div className="st-page"><Skeleton height={320} radius={24} /><Skeleton height={60} radius={14} /><Skeleton height={200} radius={18} /></div>;
  const t = title.data;
  const share = async () => {
    const url = `${location.origin}/showtime/${t.slug}`;
    try { if (navigator.share) await navigator.share({ title: t.title, url }); else await navigator.clipboard.writeText(url); } catch { /* cancelled */ }
  };

  return (
    <div className="st-page" data-theme="movies">
      <Link to="/showtime" className="btn btn--ghost btn--sm" style={{ alignSelf: 'flex-start', paddingLeft: 4, color: 'var(--c-ink-2)' }}><Icon name="back" size={18} /> Showtime</Link>
      <section className="st-title-hero" aria-label={t.title}>
        {(t.backdropUrl || t.posterUrl) && <div className="st-title-hero__bg"><img src={t.backdropUrl || t.posterUrl} alt="" /></div>}
        <div className="st-title-hero__body">
          <div className="st-title-hero__poster"><Poster t={t} eager /></div>
          <div className="stack" style={{ gap: 8 }}>
            <span className="st-hero__eyebrow">{t.kind === 'event' ? 'Live show' : t.status === 'coming_soon' ? 'Coming soon' : 'Now showing'}</span>
            <h1>{t.title}</h1>
            <div className="st-meta">
              {t.rating !== null ? <span className="st-rating"><Icon name="star" size={13} /> {t.rating.toFixed(1)} <span className="muted" style={{ fontWeight: 400 }}>({t.ratingCount})</span></span>
                : <span className="muted">{t.ratingCount ? `${t.ratingCount} review${t.ratingCount === 1 ? '' : 's'}, not rated yet` : 'Not rated yet'}</span>}
              {t.certification && <span className="st-cert">{t.certification}</span>}
              {t.durationMinutes ? <span>{runtime(t.durationMinutes)}</span> : null}
            </div>
            <div className="st-meta">{[t.languages.join(', '), t.genres.join(' • ')].filter(Boolean).join(' · ')}</div>
            {t.releaseDate && <div className="st-meta">{t.status === 'coming_soon' ? 'Releases' : 'Released'} {releaseLabel(t.releaseDate)}</div>}
            <div className="st-hero__ctas">
              {t.trailerUrl && <button type="button" className="st-btn st-btn--ghost" onClick={() => setTrailer(true)}><Icon name="play" size={16} /> Watch trailer</button>}
              {t.bookable && <a href="#times" className="st-btn st-btn--book"><Icon name="ticket" size={16} /> Book tickets</a>}
              {t.status === 'coming_soon' && <InterestButton t={t} />}
              <button type="button" className="st-btn st-btn--ghost" onClick={share} aria-label="Share"><Icon name="share" size={16} /></button>
            </div>
            {t.interestCount ? <span className="small muted">{t.interestCount} people are interested</span> : null}
            {t.mediaCredit && <span className="st-credit">{t.mediaCredit}</span>}
          </div>
        </div>
      </section>

      <div className="st-title-layout">
        <div className="stack" style={{ gap: 'var(--s-6)' }}>
          {(t.tagline || t.description) && (
            <section className="st-sec" aria-label="About">
              <h2 style={{ fontSize: 'var(--fs-lg)' }}>About</h2>
              {t.tagline && <p style={{ fontStyle: 'italic', color: 'var(--c-ink-2)' }}>{t.tagline}</p>}
              {t.description && <p className="small" style={{ color: 'var(--c-ink-2)' }}>{t.description}</p>}
            </section>
          )}
          {t.credits.length > 0 && (
            <section className="st-sec" aria-label="Cast and crew">
              <h2 style={{ fontSize: 'var(--fs-lg)' }}>Cast & crew</h2>
              <div className="st-cast">{t.credits.map((c) => (
                <Link key={`${c.role}-${c.name}`} to={`/showtime/search?q=${encodeURIComponent(c.name)}`} className="st-person">
                  <span className="st-person__avatar" aria-hidden="true">{c.name.split(' ').map((w) => w[0]).slice(0, 2).join('')}</span>
                  <strong>{c.name}</strong><span>{c.part || (c.role === 'cast' ? 'Cast' : 'Crew')}</span>
                </Link>))}</div>
            </section>
          )}
          <Reviews t={t} />
        </div>

        <section className="st-sec" id="times" aria-label="Showtimes" style={{ scrollMarginTop: 'calc(var(--header-total, 64px) + 12px)' }}>
          <h2 style={{ fontSize: 'var(--fs-lg)' }}>{t.bookable ? 'Book tickets' : 'Showtimes'}</h2>
          {t.dates.length === 0 ? (
            <p className="small muted">{t.status === 'coming_soon' ? 'Booking hasn’t opened yet. Tap “I’m interested” and we’ll tell you when it does.' : 'No upcoming showtimes right now.'}</p>
          ) : (
            <>
              <div className="st-dates" role="group" aria-label="Choose a date">
                {t.dates.map((d) => { const p = dateParts(d); return (
                  <button key={d} type="button" className="st-date" aria-pressed={d === t.date} onClick={() => set('date', d)}>
                    <small>{p.top}</small><strong>{p.day}</strong><span>{p.month}</span>
                  </button>); })}
              </div>
              {(t.allFormats.length > 1 || t.allLanguages.length > 1) && (
                <div className="st-filters">
                  {t.allFormats.length > 1 && t.allFormats.map((f) => <button key={f} type="button" className="chip" aria-pressed={t.filters.format === f} onClick={() => set('format', t.filters.format === f ? null : f)}>{f}</button>)}
                  {t.allLanguages.length > 1 && t.allLanguages.map((l) => <button key={l} type="button" className="chip" aria-pressed={t.filters.language === l} onClick={() => set('language', t.filters.language === l ? null : l)}>{l}</button>)}
                </div>
              )}
              {!t.locationUsed && <p className="small muted">Choose your location on Home to see the nearest cinemas first.</p>}
              {t.schedule.length === 0 ? (
                <div className="st-box"><strong>No showtimes available for this date.</strong>
                  <span className="small muted">Try another date{t.filters.format || t.filters.language ? ' or clear the format/language filter' : ''}.</span>
                  {(t.filters.format || t.filters.language) && <Button size="sm" variant="secondary" onClick={() => {
                    const next = new URLSearchParams(params); next.delete('format'); next.delete('language'); setParams(next, { replace: true });
                  }}>Clear filters</Button>}</div>
              ) : t.schedule.map((v) => (
                <article key={v.venue.id} className="st-venue">
                  <div className="st-venue__head">
                    <div><strong>{v.venue.name}</strong><div className="small muted">{v.venue.locality}{v.venue.hasFood ? ' · Food & drinks' : ''}</div></div>
                    {v.distanceKm != null && <span className="st-cinema__dist">{v.distanceKm} km</span>}
                  </div>
                  {v.groups.map((g) => (
                    <div key={`${g.format}-${g.language}`} className="st-venue__group">
                      <span className="st-venue__label">{[g.language, g.format].filter(Boolean).join(' • ')}</span>
                      <div className="st-times">
                        {g.times.map((x) => (
                          <Link key={x.showId} to={`/shows/${x.showId}`} className={`st-time st-time--${x.status}`} aria-disabled={x.status === 'sold_out'}
                            aria-label={`${timeOf(x.startsAt)}, ${x.status === 'sold_out' ? 'sold out' : x.status === 'filling_fast' ? 'filling fast' : 'available'}, ${formatMoney(x.priceFrom, x.currency)} to ${formatMoney(x.priceTo, x.currency)}`}>
                            <strong>{timeOf(x.startsAt)}</strong>
                            <span>{x.status === 'sold_out' ? 'Sold out' : x.status === 'filling_fast' ? 'Filling fast' : `${formatMoney(x.priceFrom, x.currency).replace('.00', '')}+`}</span>
                          </Link>
                        ))}
                      </div>
                    </div>
                  ))}
                </article>
              ))}
            </>
          )}
          {t.offers.length > 0 && t.bookable && (
            <div className="st-offers">{t.offers.map((o) => <div key={o.id} className="st-offer"><strong>{o.title}</strong><span>{o.description}</span></div>)}</div>
          )}
        </section>
      </div>

      {t.related.length > 0 && (
        <section className="st-sec" aria-label="More like this"><SectionHead title="More like this" /><div className="st-rail">{t.related.map((r) => <TitleCard key={r.id} t={r} />)}</div></section>
      )}
      <TrailerSheet t={trailer ? t : null} onClose={() => setTrailer(false)} />
    </div>
  );
}

function Reviews({ t }: { t: ShowtimeTitleDetail }) {
  const s = t.ratingSummary;
  const max = Math.max(1, ...Object.values(s.distribution));
  const [editing, setEditing] = useState(false);
  return (
    <section className="st-sec" aria-label="Reviews" id="reviews">
      <h2 style={{ fontSize: 'var(--fs-lg)' }}>Audience reviews</h2>
      {s.count > 0 && (
        <div className="rsum">
          <div className="rsum__big"><strong>{s.average !== null ? s.average.toFixed(1) : '—'}</strong>
            <span className="small muted">{s.average !== null ? `${s.count} reviews` : `Rating shows after ${s.minimum} reviews`}</span></div>
          <div className="rsum__bars">{['5', '4', '3', '2', '1'].map((k) => (
            <div key={k} className="rsum__bar"><span>{k}★</span><span className="rsum__track"><span className="rsum__fill" style={{ width: `${(s.distribution[k]! / max) * 100}%`, background: 'var(--c-theme)' }} /></span><span>{s.distribution[k]}</span></div>))}</div>
        </div>
      )}
      <p className="small muted">Reviews come only from people who watched with a Click. booking.</p>
      {t.myReview && !editing && (
        <div className="st-box"><strong>Your review · {t.myReview.rating}★</strong>{t.myReview.body && <p className="small">{t.myReview.body}</p>}
          <MyReviewActions slug={t.slug} onEdit={() => setEditing(true)} /></div>
      )}
      {(t.canReview || editing) && <ReviewForm slug={t.slug} existing={editing ? t.myReview : null} onDone={() => setEditing(false)} />}
      {t.reviews.map((r) => (
        <div key={r.id} className="review" style={{ borderColor: 'var(--c-line)' }}>
          <div className="review__head"><span className="st-rating"><Icon name="star" size={12} /> {r.rating}</span><strong>{r.author}</strong>{r.verified && <span className="small muted">Watched with Click.</span>}</div>
          {r.body && <p className="small" style={{ color: 'var(--c-ink-2)' }}>{r.body}</p>}
          <span className="review__meta">{formatDateTime(r.createdAt)}{r.edited ? ' · edited' : ''}</span>
        </div>
      ))}
      {s.count === 0 && !t.canReview && <p className="small muted">No reviews yet.</p>}
    </section>
  );
}

function useRefresh() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ['showtime', 'title'] });
}

function MyReviewActions({ slug, onEdit }: { slug: string; onEdit: () => void }) {
  const confirm = useConfirm();
  const toast = useToast();
  const refresh = useRefresh();
  const remove = useMutation({ mutationFn: () => api.showtime.review.remove(slug), onSuccess: () => { toast('Review deleted'); refresh(); } });
  return (
    <div className="row">
      <Button size="sm" variant="ghost" onClick={onEdit}>Edit</Button>
      <Button size="sm" variant="ghost" loading={remove.isPending}
        onClick={async () => { if (await confirm({ title: 'Delete your review?', message: 'Your rating is removed from this show.', confirmLabel: 'Delete', danger: true })) remove.mutate(); }}>Delete</Button>
    </div>
  );
}

function ReviewForm({ slug, existing, onDone }: { slug: string; existing: { rating: number; body: string } | null; onDone: () => void }) {
  const [rating, setRating] = useState(existing?.rating ?? 0);
  const [body, setBody] = useState(existing?.body ?? '');
  const toast = useToast();
  const refresh = useRefresh();
  const save = useMutation({
    mutationFn: () => (existing ? api.showtime.review.update : api.showtime.review.create)(slug, { rating, body }),
    onSuccess: () => { toast(existing ? 'Review updated' : 'Thanks for your review'); refresh(); onDone(); },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t save your review.', 'error'),
  });
  return (
    <form className="st-box" onSubmit={(e) => { e.preventDefault(); if (rating) save.mutate(); }}>
      <strong>{existing ? 'Edit your review' : 'You watched this. How was it?'}</strong>
      <div className="stars-input" role="radiogroup" aria-label="Your rating">
        {[1, 2, 3, 4, 5].map((n) => <button key={n} type="button" role="radio" aria-checked={rating === n} aria-label={`${n} star${n > 1 ? 's' : ''}`} className={n <= rating ? 'is-lit' : ''} onClick={() => setRating(n)}><Icon name="star" size={26} /></button>)}
      </div>
      <TextArea label="Review (optional)" maxLength={1500} value={body} onChange={(e) => setBody(e.target.value)} />
      <div className="row"><Button type="submit" size="sm" disabled={!rating} loading={save.isPending}>{existing ? 'Save' : 'Submit review'}</Button>
        {existing && <Button type="button" size="sm" variant="ghost" onClick={onDone}>Cancel</Button>}</div>
    </form>
  );
}
