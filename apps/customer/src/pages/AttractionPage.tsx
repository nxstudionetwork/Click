import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ApiError } from '@click/api';
import { EmptyState, ErrorState, Icon, Skeleton, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { fmtDay, fmtSlot, PlaceCard, PlaceImage, SavePlace, Stepper } from '../features/bookings/parts';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const DAY_STATE: Record<string, string> = { available: 'Available', sold_out: 'Sold out', expired: 'Closed for today', closed: 'Closed', not_running: 'Not running', too_far: 'Not open yet', past: 'Past' };
const osm = (lat: number, lng: number) => `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=16/${lat}/${lng}`;

/** A place or experience: verified visitor information, and — when Click. can actually sell it — the booking model the
 *  provider uses: a day ticket, or a date + time slot (darshan, seva, tours, activities), with ticket types and live
 *  places left. Information-only places say where they are booked instead. */
export function AttractionPage() {
  useThemeOverride('bookings');
  const { slug = '' } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const q = useQuery({ queryKey: ['bookings', 'attraction', slug], queryFn: () => api.bookings.attraction(slug) });
  const a = q.data;
  const [oid, setOid] = useState('');
  const o = a?.offerings.find((x) => x.id === oid) ?? a?.offerings[0];
  const firstOpen = o?.calendar.find((d) => d.status === 'available')?.date ?? '';
  const [date, setDate] = useState('');
  const [slot, setSlot] = useState<string | null>(null);
  const [tickets, setTickets] = useState<Record<string, number>>({});
  const [pickup, setPickup] = useState('');
  useEffect(() => { setDate(firstOpen); setSlot(null); setTickets({}); setPickup(''); }, [o?.id, firstOpen]);
  const av = useQuery({ queryKey: ['bookings', 'availability', o?.id, date], queryFn: () => api.bookings.availability(o!.id, date), enabled: !!o && !!date });
  useEffect(() => { if (o?.bookingModel === 'ticket' && av.data?.slots[0]?.status === 'available') setSlot(null); }, [av.data, o?.bookingModel]);
  const units = useMemo(() => o ? Object.entries(tickets).reduce((t, [v, n]) => t + n * (o.prices.find((p) => p.visitor === v)?.units ?? 1), 0) : 0, [tickets, o]);
  const subtotal = o ? Object.entries(tickets).reduce((t, [v, n]) => t + n * Number(o.prices.find((p) => p.visitor === v)?.amount ?? 0), 0) : 0;
  const chosenSlot = av.data?.slots.find((s) => s.time === slot) ?? (o?.bookingModel === 'ticket' ? av.data?.slots[0] : undefined);
  const left = chosenSlot?.status === 'available' ? chosenSlot.left : 0;
  const ready = !!o && !!date && !!chosenSlot && chosenSlot.status === 'available' && units > 0 && units <= left && (!o.pickupPoints.length || !!pickup);

  if (q.isError) return <div className="bk-page">{q.error instanceof ApiError && q.error.status === 404
    ? <EmptyState icon="alert" title="This place isn’t listed" action={<Link className="bk-btn" to="/bookings">Explore Bookings</Link>} /> : <ErrorState error={q.error} onRetry={() => q.refetch()} />}</div>;
  if (!a) return <div className="bk-page"><Skeleton height={260} radius={24} /><Skeleton height={300} radius={22} /></div>;

  const go = () => {
    const p = new URLSearchParams({ offering: o!.id, date, tickets: Object.entries(tickets).filter(([, n]) => n).map(([v, n]) => `${v}:${n}`).join(','), place: a.slug });
    if (slot) p.set('slot', slot);
    if (pickup) p.set('pickup', pickup);
    nav(`/bookings/book?${p}`);
  };

  return (
    <div className="bk-page" data-theme="bookings" style={{ ['--bk-accent' as string]: a.accent }}>
      <Link to="/bookings/search" className="bk-back"><Icon name="back" size={18} /> Places</Link>
      <header className="bk-dhead">
        <div className="bk-gallery">{a.images.length ? a.images.slice(0, 3).map((im) => <figure key={im.url}><img src={im.url} alt={im.caption || a.name} loading="lazy" />{im.credit && <figcaption className="small">{im.credit}</figcaption>}</figure>)
          : <PlaceImage src={null} name={a.name} accent={a.accent} kind={a.kind} className="bk-gallery__ph" />}</div>
        <div className="bk-dhead__info">
          <span className="bk-kicker">{a.kindLabel}{a.deity ? ` · ${a.deity}` : ''}</span>
          <h1 className="bk-title">{a.name}</h1>
          <p className="bk-muted"><Icon name="pin" size={14} /> {a.address || `${a.area ? `${a.area}, ` : ''}${a.city}, ${a.region}`}</p>
          <div className="bk-tags">
            <span className={a.bookable ? 'bk-pill bk-pill--book' : 'bk-pill bk-pill--info'}>{a.bookable ? 'Bookable through Click.' : 'Information available'}</span>
            {a.rating && <span>★ {a.rating.average} · {a.rating.count} verified visits</span>}
            {a.verified && <span className="bk-ok"><Icon name="shield" size={12} /> Verified provider{a.provider ? ` · ${a.provider}` : ''}</span>}
            {a.instant && <span>Instant confirmation</span>}
          </div>
          <div className="bk-dhead__acts">
            <SavePlace id={a.id} favoriteId={a.favoriteId} name={a.name} />
            <button type="button" className="bk-ghostbtn" onClick={async () => { try { if (navigator.share) await navigator.share({ title: a.name, url: location.href }); else { await navigator.clipboard.writeText(location.href); toast('Link copied'); } } catch { /* dismissed */ } }}><Icon name="share" size={16} /> Share</button>
            {a.latitude != null && <a className="bk-ghostbtn" href={osm(a.latitude, a.longitude!)} target="_blank" rel="noreferrer"><Icon name="compass" size={16} /> Map</a>}
          </div>
        </div>
      </header>

      {a.description && <section className="bk-sec"><p>{a.description}</p>{a.highlights.length > 0 && <ul className="bk-hl">{a.highlights.map((h) => <li key={h}><Icon name="sparkle" size={12} /> {h}</li>)}</ul>}</section>}

      {a.bookable && o ? (
        <section className="bk-sec bk-book" aria-labelledby="bk-book">
          <h2 className="bk-h2" id="bk-book">{a.group === 'spiritual' ? 'Book darshan & sevas' : 'Book tickets'}</h2>
          {a.offerings.length > 1 && (
            <div className="bk-chips" role="tablist" aria-label="What to book">{a.offerings.map((x) => (
              <button key={x.id} type="button" role="tab" aria-selected={x.id === o.id} className={x.id === o.id ? 'is-on' : ''} onClick={() => setOid(x.id)}>{x.name}</button>))}</div>
          )}
          <p className="small bk-muted">{o.kindLabel} · {o.description}{o.durationMinutes ? ` · about ${o.durationMinutes} min` : ''}{o.includes.length ? ` · includes ${o.includes.join(', ')}` : ''}</p>
          <h3 className="bk-h3">1. Date</h3>
          <div className="bk-cal" role="radiogroup" aria-label="Visit date">{o.calendar.map((d) => (
            <button key={d.date} type="button" role="radio" aria-checked={date === d.date} disabled={d.status !== 'available'} className={date === d.date ? 'is-on' : ''}
              aria-label={`${fmtDay(d.date, { weekday: 'long', day: 'numeric', month: 'long' })}: ${DAY_STATE[d.status]}`} onClick={() => { setDate(d.date); setSlot(null); }}>
              <span className="small">{fmtDay(d.date, { weekday: 'short' })}</span><strong>{fmtDay(d.date, { day: 'numeric' })}</strong>
              <span className="small">{d.status === 'available' ? (d.left <= 20 ? `${d.left} left` : 'Open') : DAY_STATE[d.status]}</span>
            </button>))}</div>
          {!firstOpen && <p className="bk-alert small">Nothing is available in the next two weeks for {o.name}.</p>}
          {date && o.bookingModel === 'slot' && (
            <>
              <h3 className="bk-h3">2. Time</h3>
              {av.isError ? <ErrorState error={av.error} onRetry={() => av.refetch()} /> : !av.data ? <Skeleton height={44} /> : av.data.state !== 'open' ? <p className="bk-alert small">{av.data.reason}</p> : (
                <div className="bk-slots" role="radiogroup" aria-label="Time slot">{av.data.slots.map((s) => (
                  <button key={s.time} type="button" role="radio" aria-checked={slot === s.time} disabled={s.status !== 'available'} className={slot === s.time ? 'is-on' : ''} onClick={() => setSlot(s.time)}>
                    <strong>{fmtSlot(s.time)}</strong><span className="small">{s.label}</span></button>))}</div>
              )}
            </>
          )}
          {date && o.bookingModel === 'ticket' && av.data && av.data.slots[0] && <p className="small bk-muted">Valid any time {fmtDay(date)}{a.opening?.open ? ` · ${a.opening.open}–${a.opening.close}` : ''} · {av.data.slots[0].label}</p>}
          <h3 className="bk-h3">{o.bookingModel === 'slot' ? '3.' : '2.'} {a.group === 'spiritual' ? 'Devotees' : 'Tickets'}</h3>
          {o.prices.map((p) => (
            <Stepper key={p.visitor} label={p.label} note={p.note} price={p.amount} value={tickets[p.visitor] ?? 0}
              max={p.units ? Math.floor(Math.max(0, Math.min(o.maxPerBooking, left || o.maxPerBooking) - units + (tickets[p.visitor] ?? 0) * p.units) / p.units) : 4}
              onChange={(n) => setTickets({ ...tickets, [p.visitor]: n })} />
          ))}
          {o.minAge && <p className="small bk-muted">Minimum age {o.minAge}.</p>}
          {o.pickupPoints.length > 0 && (
            <label className="bk-field"><span className="small">Pickup point</span><select value={pickup} onChange={(e) => setPickup(e.target.value)}>
              <option value="">Choose…</option>{o.pickupPoints.map((x) => <option key={x}>{x}</option>)}</select></label>
          )}
          {o.requirements && <p className="small bk-note"><Icon name="alert" size={12} /> {o.requirements}</p>}
          {units > left && left > 0 && <p className="small bk-warn">Only {left} places left for this time.</p>}
          <div className="bk-cta">
            <div>{subtotal > 0 ? <><strong>{formatMoney(String(subtotal))}</strong><span className="small bk-muted"> + taxes if any</span></> : units > 0 ? <strong>Free</strong> : <span className="small bk-muted">Choose tickets</span>}</div>
            <button type="button" className="bk-btn" disabled={!ready} onClick={go}>Continue</button>
          </div>
          <p className="small bk-muted">{a.policy}</p>
        </section>
      ) : !a.bookable ? (
        <section className="bk-sec bk-official"><Icon name="ticket" size={20} /><div><strong>Not bookable through Click.</strong><p className="small">{a.officialSource}</p>
          {a.officialUrl && <a className="bk-link" href={a.officialUrl} target="_blank" rel="noreferrer">Official website</a>}</div></section>
      ) : null}

      <section className="bk-sec bk-info">
        {a.opening && (a.opening.open || a.opening.note) && <div><h3 className="bk-h3">Opening hours</h3><p className="small">{a.opening.days ? a.opening.days.map((d) => DAYS[d]).join(', ') : ''}{a.opening.open ? ` · ${a.opening.open}–${a.opening.close}` : ''}{a.opening.note ? ` · ${a.opening.note}` : ''}</p></div>}
        {a.durationMinutes && <div><h3 className="bk-h3">Typical visit</h3><p className="small">About {a.durationMinutes >= 60 ? `${Math.round(a.durationMinutes / 60 * 10) / 10} hours` : `${a.durationMinutes} min`}</p></div>}
        {a.facilities.length > 0 && <div><h3 className="bk-h3">Facilities</h3><ul className="small">{a.facilities.map((x) => <li key={x}>{x}</li>)}</ul></div>}
        {a.accessibility.length > 0 && <div><h3 className="bk-h3">Accessibility</h3><ul className="small">{a.accessibility.map((x) => <li key={x}>{x}</li>)}</ul></div>}
        {(a.rules.length > 0 || a.dressCode || a.ageNote) && <div><h3 className="bk-h3">Visitor information</h3><ul className="small">{a.dressCode && <li>Dress: {a.dressCode}</li>}{a.ageNote && <li>{a.ageNote}</li>}{a.rules.map((x) => <li key={x}>{x}</li>)}</ul></div>}
        {a.prohibited.length > 0 && <div><h3 className="bk-h3">Not allowed</h3><ul className="small">{a.prohibited.map((x) => <li key={x}>{x}</li>)}</ul></div>}
      </section>
      {a.faqs.length > 0 && <section className="bk-sec"><h2 className="bk-h2">FAQs</h2>{a.faqs.map((f) => <details key={f.q} className="bk-faq"><summary>{f.q}</summary><p className="small">{f.a}</p></details>)}</section>}
      {a.reviews.length > 0 && (
        <section className="bk-sec"><h2 className="bk-h2">Verified visits</h2>
          <ul className="bk-reviews">{a.reviews.map((r, i) => <li key={i}><strong>{'★'.repeat(r.rating)}<span className="bk-muted">{'★'.repeat(5 - r.rating)}</span></strong>
            <p className="small">{r.comment || '—'}</p><span className="small bk-muted">{r.author} · {r.offering} · {r.visited}</span></li>)}</ul></section>
      )}
      {a.related.length > 0 && <section className="bk-sec"><h2 className="bk-h2">More in {a.city}</h2><div className="bk-row">{a.related.map((x) => <PlaceCard key={x.id} a={x} />)}</div></section>}
    </div>
  );
}
