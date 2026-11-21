import { useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import type { RoomOption, StayQuery } from '@click/api';
import { Button, EmptyState, ErrorState, Icon, type IconName, Sheet, Skeleton, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { addDays, fmtDay, GuestsPicker, HotelImage, nightsOf, partyLabel, RatingBadge, SaveHotel, Stars, stayFrom, stayQs, todayIso } from '../features/hotels/parts';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

const ASPECTS = [['cleanliness', 'Cleanliness'], ['location', 'Location'], ['comfort', 'Comfort'], ['facilities', 'Facilities'], ['staff', 'Staff'], ['value', 'Value']] as const;
const osm = (lat: number, lng: number) => `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=16/${lat}/${lng}`;

/** Hotel → rooms → rate. Rooms and prices are for the stay in the URL and come from live inventory. */
export function HotelPropertyPage() {
  useThemeOverride('hotels');
  const { id = '' } = useParams();
  const [sp, setSp] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const stay = stayFrom(sp);
  const q = useQuery({ queryKey: ['hotels', 'property', id, stay], queryFn: () => api.hotels.property(id, stay), placeholderData: (p) => p });
  const [sort, setSort] = useState('relevant');
  const reviews = useInfiniteQuery({
    queryKey: ['hotels', 'reviews', id, sort], initialPageParam: 1, enabled: !!q.data?.rating,
    queryFn: ({ pageParam }) => api.hotels.reviews(id, sort, pageParam), getNextPageParam: (l, all) => (l.hasMore ? all.length + 1 : undefined),
  });
  const [photo, setPhoto] = useState<number | null>(null);
  const [compare, setCompare] = useState(false);
  const setStay = (s: StayQuery) => { const n = new URLSearchParams(stayQs(s)); setSp(n, { replace: true }); };

  if (q.isError) return <div className="ht-page"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  if (!q.data) return <div className="ht-page"><Skeleton height={280} radius={26} /><Skeleton height={400} radius={22} /></div>;
  const h = q.data;
  const rooms = h.rooms ?? [];
  const share = async () => {
    const url = window.location.href;
    try {
      if (navigator.share) await navigator.share({ title: h.name, url });
      else { await navigator.clipboard.writeText(url); toast('Link copied'); }
    } catch { /* dismissed */ }
  };
  const pick = (room: RoomOption, rateId: string) => navigate(`/hotels/book?rate=${rateId}&property=${h.id}&${stayQs(stay)}`, { state: { room: room.name } });

  return (
    <div className="ht-page" data-theme="hotels" style={{ ['--ht-accent' as string]: h.accent }}>
      <Link to={`/hotels/search?destination=${encodeURIComponent(h.destination.name)}&${stayQs(stay)}`} className="ht-back"><Icon name="back" size={18} /> Stays in {h.destination.name}</Link>

      <section className="ht-gallery" aria-label="Photos">
        {h.images.length === 0 ? <HotelImage src="" name={h.name} accent={h.accent} className="ht-gallery__hero" /> : (
          <>
            <button type="button" className="ht-gallery__hero" onClick={() => setPhoto(0)} aria-label="Open photos"><img src={h.images[0]!.src} alt={h.images[0]!.caption || h.name} /></button>
            <div className="ht-gallery__thumbs">{h.images.slice(1, 5).map((im, i) => (
              <button key={im.id} type="button" onClick={() => setPhoto(i + 1)} aria-label={im.caption || 'Open photo'}><img src={im.thumb} alt="" loading="lazy" /></button>
            ))}</div>
          </>
        )}
      </section>

      <header className="ht-head">
        <div>
          <span className="ht-kicker">{h.typeLabel} <Stars n={h.starRating} /></span>
          <h1>{h.name}</h1>
          {h.tagline && <p className="ht-muted">{h.tagline}</p>}
          <p className="small"><Icon name="pin" size={13} /> {h.address}{h.distanceFromCentre != null ? ` · ${h.distanceFromCentre.toFixed(1)} km from the centre` : ''}</p>
        </div>
        <div className="ht-head__side">
          <RatingBadge r={h.rating} big />
          <div className="ht-head__acts">
            <SaveHotel id={h.id} favoriteId={h.favoriteId} name={h.name} />
            <button type="button" className="ht-icon" onClick={share} aria-label="Share"><Icon name="share" size={18} /></button>
            <a className="ht-icon" href={osm(h.latitude, h.longitude)} target="_blank" rel="noreferrer" aria-label="View map (OpenStreetMap)"><Icon name="compass" size={18} /></a>
          </div>
        </div>
      </header>

      <div className="ht-staybar">
        <label className="ht-field"><span className="ht-field__label">Check-in</span>
          <input type="date" min={todayIso()} value={stay.checkIn} onChange={(e) => setStay({ ...stay, checkIn: e.target.value, checkOut: stay.checkOut <= e.target.value ? addDays(e.target.value, 1) : stay.checkOut })} /></label>
        <label className="ht-field"><span className="ht-field__label">Check-out</span>
          <input type="date" min={addDays(stay.checkIn, 1)} value={stay.checkOut} onChange={(e) => setStay({ ...stay, checkOut: e.target.value })} /></label>
        <GuestsPicker value={stay} onChange={setStay} />
      </div>

      {h.offers.length > 0 && <div className="ht-offerline">{h.offers.map((o) => <span key={o.title} className="ht-badge ht-badge--gold">{o.title}{o.conditions ? ` · ${o.conditions}` : ''}</span>)}</div>}

      <section className="ht-sec" id="rooms" aria-labelledby="rooms-h">
        <header className="ht-sec__head">
          <div><span className="ht-kicker">{fmtDay(stay.checkIn)} – {fmtDay(stay.checkOut)} · {nightsOf(stay)} night{nightsOf(stay) > 1 ? 's' : ''} · {partyLabel(stay)}</span><h2 id="rooms-h">Choose your room</h2></div>
          {rooms.length > 1 && <button type="button" className="ht-chipbtn" aria-pressed={compare} onClick={() => setCompare(!compare)}><Icon name="compare" size={14} /> Compare rooms</button>}
        </header>
        {q.isFetching && <p className="small ht-muted" aria-live="polite">Updating prices…</p>}
        {compare && rooms.length > 1 && (
          <div className="ht-cmpwrap" role="region" aria-label="Room comparison" tabIndex={0}>
            <table className="ht-cmptable">
              <thead><tr><th scope="col"><span className="sr-only">Detail</span></th>{rooms.map((r) => <th key={r.id} scope="col">{r.name}</th>)}</tr></thead>
              <tbody>
                <tr><th scope="row">From</th>{rooms.map((r) => { const c = r.rates.find((x) => !x.problem); return <td key={r.id}>{c ? formatMoney(c.total) : 'Not available'}</td>; })}</tr>
                <tr><th scope="row">Size</th>{rooms.map((r) => <td key={r.id}>{r.sizeSqm ? `${r.sizeSqm} m²` : '—'}</td>)}</tr>
                <tr><th scope="row">Beds</th>{rooms.map((r) => <td key={r.id}>{r.beds}</td>)}</tr>
                <tr><th scope="row">Sleeps</th>{rooms.map((r) => <td key={r.id}>{r.maxAdults} adults{r.maxChildren ? ` + ${r.maxChildren} child` : ''}</td>)}</tr>
                <tr><th scope="row">Breakfast</th>{rooms.map((r) => <td key={r.id}>{r.rates.some((x) => x.mealPlan !== 'room_only') ? 'Option' : 'No'}</td>)}</tr>
                <tr><th scope="row">Free cancellation</th>{rooms.map((r) => <td key={r.id}>{r.rates.some((x) => x.freeCancelUntil) ? 'Option' : 'No'}</td>)}</tr>
                <tr><th scope="row">Pay at property</th>{rooms.map((r) => <td key={r.id}>{r.rates.some((x) => x.payment !== 'pay_now') ? 'Option' : 'No'}</td>)}</tr>
                <tr><th scope="row">Fits your party</th>{rooms.map((r) => <td key={r.id}>{r.fits ? 'Yes' : 'No'}</td>)}</tr>
              </tbody>
            </table>
          </div>
        )}
        {rooms.length === 0 ? <EmptyState icon="hotel" title="No rooms listed" /> : (
          <div className="ht-rooms">{rooms.map((r) => (
            <article key={r.id} className={`ht-room${r.fits ? '' : ' is-dim'}`}>
              <div className="ht-room__id">
                <HotelImage src={r.imageUrl} name={r.name} accent={h.accent} className="ht-room__img" />
                <div>
                  <h3>{r.name}</h3>
                  <span className="small ht-muted">{r.beds}{r.sizeSqm ? ` · ${r.sizeSqm} m²` : ''}{r.view ? ` · ${r.view}` : ''}</span>
                  <span className="small">Sleeps {r.maxAdults} adult{r.maxAdults > 1 ? 's' : ''}{r.maxChildren ? ` + ${r.maxChildren} child${r.maxChildren > 1 ? 'ren' : ''}` : ''}</span>
                  <div className="ht-amen">{r.amenities.slice(0, 5).map((a) => <span key={a.slug}><Icon name={(a.icon || 'check') as IconName} size={12} /> {a.name}</span>)}</div>
                  {!r.fits && <p className="small ht-warn">Doesn’t fit {partyLabel(stay)} — add rooms or choose a bigger room.</p>}
                </div>
              </div>
              <ul className="ht-rates">{r.rates.map((x) => (
                <li key={x.rateId} className={x.problem ? 'is-off' : ''}>
                  <div className="ht-rate__terms">
                    <strong>{x.rateName}</strong>
                    <span className="small">{x.mealLabel}</span>
                    <span className={`small ${x.freeCancelUntil ? 'ht-ok' : 'ht-muted'}`}>{x.policy}</span>
                    <span className="small ht-muted">{x.paymentLabel}</span>
                  </div>
                  <div className="ht-rate__price">
                    {Number(x.discount) > 0 && <span className="small ht-ok">{x.offer}: −{formatMoney(x.discount)}</span>}
                    <strong>{formatMoney(x.total)}</strong>
                    <span className="small ht-muted">{x.perNight ? `${formatMoney(x.perNight)}/night · ` : ''}incl. {formatMoney(x.tax)} tax</span>
                    {x.problem ? <span className="small ht-warn">{x.problem}</span> : (
                      <>
                        {x.roomsLeft <= 3 && <span className="small ht-warn">{x.roomsLeft} left</span>}
                        <button type="button" className="ht-btn ht-btn--sm" onClick={() => pick(r, x.rateId)}>Select room</button>
                      </>
                    )}
                  </div>
                </li>
              ))}</ul>
            </article>
          ))}</div>
        )}
      </section>

      <section className="ht-sec"><h2 className="ht-h2">About this stay</h2>
        {h.description && <p className="ht-about">{h.description}</p>}
        {h.highlights.length > 0 && <ul className="ht-hl">{h.highlights.map((x) => <li key={x}><Icon name="sparkle" size={13} /> {x}</li>)}</ul>}
        <div className="ht-amengrid">{h.amenities.map((a) => <span key={a.slug}><Icon name={(a.icon || 'check') as IconName} size={15} /> {a.name}</span>)}</div>
      </section>

      <section className="ht-sec"><h2 className="ht-h2">Location</h2>
        <p className="small">{h.address}</p>
        <ul className="ht-dist">{h.distances.map((d) => <li key={d.name}><span>{d.name}<span className="small ht-muted"> · {d.kindLabel}</span></span><span>{d.km != null ? `${d.km.toFixed(1)} km` : '—'}</span></li>)}</ul>
        <p className="small ht-muted">Straight-line distances. Travel times depend on traffic.</p>
        <a className="ht-link small" href={osm(h.latitude, h.longitude)} target="_blank" rel="noreferrer">Open the map <Icon name="right" size={12} /></a>
      </section>

      <section className="ht-sec"><h2 className="ht-h2">Policies</h2>
        <dl className="ht-dl">
          <dt>Check-in</dt><dd>From {h.checkInTime}</dd><dt>Check-out</dt><dd>Until {h.checkOutTime}</dd>
          <dt>Payment</dt><dd>{h.paymentOptions.join(' · ')}</dd><dt>Meals</dt><dd>{h.mealOptions.join(' · ')}</dd>
          {h.parking && <><dt>Parking</dt><dd>{h.parking}</dd></>}
          {h.accessibility && <><dt>Accessibility</dt><dd>{h.accessibility}</dd></>}
          {h.languages.length > 0 && <><dt>Languages</dt><dd>{h.languages.join(', ')}</dd></>}
        </dl>
        {h.policies.length > 0 && <ul className="ht-rules">{h.policies.map((p) => <li key={p} className="small">{p}</li>)}</ul>}
        <p className="small ht-muted">Cancellation terms differ by rate and are shown on each room above.</p>
      </section>

      <section className="ht-sec" aria-labelledby="rev-h">
        <header className="ht-sec__head"><div><span className="ht-kicker">Only guests who stayed through Click.</span><h2 id="rev-h">Reviews</h2></div>
          {h.rating && <label className="ht-select"><span className="sr-only">Sort reviews</span>
            <select value={sort} onChange={(e) => setSort(e.target.value)}><option value="relevant">Most relevant</option><option value="recent">Most recent</option>
              <option value="highest">Highest rated</option><option value="lowest">Lowest rated</option></select></label>}
        </header>
        {!h.rating ? <EmptyState icon="star" title="No reviews yet" message="Reviews appear after guests complete a stay booked on Click." /> : (
          <>
            <div className="ht-aspects">{ASPECTS.map(([k, l]) => h.aspects[k] != null && (
              <div key={k}><span className="small">{l}</span><span className="ht-bar"><span style={{ width: `${(h.aspects[k]! / 10) * 100}%` }} /></span><strong className="small">{h.aspects[k]!.toFixed(1)}</strong></div>
            ))}</div>
            {reviews.isPending ? <Skeleton height={120} /> : (
              <ul className="ht-reviews">{reviews.data?.pages.flatMap((p) => p.results).map((r) => (
                <li key={r.id}>
                  <div className="ht-reviews__top"><span className="ht-score__n ht-score__n--sm">{r.overall}</span><span><strong>{r.title || r.author}</strong>
                    <span className="small ht-muted">{r.author}{r.traveller ? ` · ${r.traveller}` : ''} · {r.room} · stayed {r.stayed} · <Icon name="check" size={11} /> Verified stay</span></span></div>
                  {r.comment && <p>{r.comment}</p>}
                </li>
              ))}</ul>
            )}
            {reviews.hasNextPage && <Button variant="secondary" loading={reviews.isFetchingNextPage} onClick={() => reviews.fetchNextPage()}>More reviews</Button>}
          </>
        )}
      </section>

      <Sheet open={photo != null} onClose={() => setPhoto(null)} label="Photos" variant="full">
        {photo != null && h.images[photo] && (
          <figure className="ht-photo">
            <img src={h.images[photo]!.src} alt={h.images[photo]!.caption || h.name} />
            <figcaption className="small">{h.images[photo]!.caption} · {photo + 1} / {h.images.length}</figcaption>
            <div className="ht-row2">
              <Button variant="secondary" disabled={photo === 0} onClick={() => setPhoto(photo - 1)}>Previous</Button>
              <Button variant="secondary" disabled={photo >= h.images.length - 1} onClick={() => setPhoto(photo + 1)}>Next</Button>
            </div>
          </figure>
        )}
      </Sheet>
    </div>
  );
}
