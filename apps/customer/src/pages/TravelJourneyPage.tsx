import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ApiError } from '@click/api';
import { EmptyState, ErrorState, Icon, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { fmtDate, fmtDur, fmtTime, modeOf, RouteTimeline, SeatMap, searchFrom, searchQs } from '../features/travel/parts';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

/** Journey details and the seat / class choice: bus seats from the operator's layout and boarding / dropping points,
 *  train classes with live availability (available, RAC, waitlist), flight fares with baggage and rules. */
export function TravelJourneyPage() {
  useThemeOverride('travel');
  const { journey = '', from = '', to = '' } = useParams();
  const [sp] = useSearchParams();
  const nav = useNavigate();
  const s = searchFrom(sp);
  const seats = s.adults + s.children;
  const q = useQuery({ queryKey: ['travel', 'option', journey, from, to, seats], queryFn: () => api.travel.option(journey, from, to, seats) });
  const [cls, setCls] = useState(sp.get('class') ?? '');
  const [picked, setPicked] = useState<string[]>([]);
  const o = q.data;
  useEffect(() => {
    if (!o || cls) return;
    const first = o.classes.find((c) => c.bookable) ?? o.classes[0];
    if (first) setCls(first.code);
  }, [o, cls]);
  useEffect(() => { setPicked([]); }, [from, to]);

  if (q.isError) {
    const gone = q.error instanceof ApiError && q.error.status === 404;
    return <div className="tv-page">{gone
      ? <EmptyState icon="alert" title="This journey is no longer available" message="It may have been withdrawn by the operator." action={<Link className="tv-btn" to={`/travel/search?${searchQs(s)}`}>Refresh results</Link>} />
      : <ErrorState error={q.error} onRetry={() => q.refetch()} />}</div>;
  }
  if (!o) return <div className="tv-page"><Skeleton height={220} radius={22} /><Skeleton height={320} radius={22} /></div>;
  const m = modeOf(o.mode);
  const chosen = o.classes.find((c) => c.code === cls);
  const busReady = o.mode !== 'bus' || picked.length === seats;
  const canGo = o.bookableNow && o.status !== 'cancelled' && (o.mode === 'bus' ? busReady : !!chosen?.bookable);
  const back = `/travel/search?${searchQs(s)}`;
  const seatTotal = o.seatMap ? picked.reduce((t, k) => t + Number(o.seatMap!.seats[k]?.fare ?? 0), 0) : 0;
  const goBook = () => {
    const p = new URLSearchParams(searchQs(s));
    p.set('journey', o.journeyId); p.set('from', o.fromStopId); p.set('to', o.toStopId); p.set('class', o.mode === 'bus' ? (o.seatMap!.seats[picked[0]!]?.class ?? cls) : cls);
    if (picked.length) p.set('seats', picked.join(','));
    nav(`/travel/book?${p}`);
  };
  const point = (kind: 'from' | 'to', stopId: string) => nav(`/travel/journey/${o.journeyId}/${kind === 'from' ? stopId : o.fromStopId}/${kind === 'to' ? stopId : o.toStopId}?${sp}`, { replace: true });

  return (
    <div className="tv-page" data-theme="travel" style={{ ['--tv-accent' as string]: o.operator.accent }}>
      <Link to={back} className="tv-backlink"><Icon name="back" size={18} /> Results</Link>
      <header className="tv-dhead">
        <span className="tv-kicker"><Icon name={m.icon} size={14} /> {m.label} · {fmtDate(o.departsAt, { weekday: 'long', day: 'numeric', month: 'long' })}</span>
        <h1 className="tv-title">{o.from.city} → {o.to.city}</h1>
        <p className="tv-muted">{o.operator.name} · {o.mode === 'train' ? `${o.service.number} ${o.service.name}` : o.mode === 'flight' ? `${o.service.number} · ${o.service.vehicle}` : o.service.vehicle}
          {o.operator.rating ? ` · ★ ${o.operator.rating.average} (${o.operator.rating.count} verified trips)` : ''}</p>
        {o.status !== 'scheduled' && <p className={`tv-alert${o.status === 'cancelled' ? ' tv-alert--bad' : ''}`}><Icon name="alert" size={14} /> {o.statusLabel}{o.delayMinutes ? ` · about ${o.delayMinutes} min late` : ''}{o.notice ? ` · ${o.notice}` : ''}</p>}
      </header>

      <section className="tv-legbig" aria-label="Journey">
        <div><strong className="tv-time">{fmtTime(o.departsAt)}</strong><span>{o.from.name}{o.from.code ? ` (${o.from.code})` : ''}</span><span className="small tv-muted">{fmtDate(o.departsAt)}{o.from.note ? ` · ${o.from.note}` : ''}</span></div>
        <div className="tv-legbig__mid"><span>{fmtDur(o.durationMinutes)}</span><span className="tv-leg__line" aria-hidden="true"><i /></span>
          <span className="small tv-muted">{o.mode === 'flight' ? (o.stops ? `${o.stops} stop via ${o.via.join(', ')}` : 'Non-stop') : `${o.distanceKm} km`}</span></div>
        <div className="tv-legbig__end"><strong className="tv-time">{fmtTime(o.arrivesAt)}</strong><span>{o.to.name}{o.to.code ? ` (${o.to.code})` : ''}</span><span className="small tv-muted">{fmtDate(o.arrivesAt)}</span></div>
      </section>

      {o.mode === 'bus' && o.seatMap && (
        <section className="tv-sec" aria-labelledby="tv-seats">
          <h2 className="tv-h2" id="tv-seats">Choose your seat{seats > 1 ? `s (${seats})` : ''}</h2>
          <p className="small tv-muted">Seats and fares come from the operator’s live layout; a seat is held only when you continue to pay.</p>
          <SeatMap map={o.seatMap} picked={picked} max={seats} onToggle={(k) => setPicked((p) => (p.includes(k) ? p.filter((x) => x !== k) : p.length < seats ? [...p, k] : p))} />
          <p className="small" aria-live="polite">{picked.length ? `Selected: ${picked.join(', ')} · ${formatMoney(String(seatTotal))} incl. GST` : `Select ${seats} seat${seats > 1 ? 's' : ''}.`}</p>
        </section>
      )}
      {o.mode === 'bus' && (
        <section className="tv-sec tv-points">
          <fieldset><legend className="tv-h3">Boarding point</legend>
            {o.boardingPoints!.map((b) => (
              <label key={b.stopId} className="tv-radio"><input type="radio" name="bp" checked={b.stopId === o.fromStopId} onChange={() => point('from', b.stopId)} />
                <span><strong>{fmtTime(b.at)} · {b.name}</strong><span className="small tv-muted">{b.address || b.landmark}{b.note ? ` · ${b.note}` : ''}</span></span></label>
            ))}</fieldset>
          <fieldset><legend className="tv-h3">Dropping point</legend>
            {o.droppingPoints!.map((b) => (
              <label key={b.stopId} className="tv-radio"><input type="radio" name="dp" checked={b.stopId === o.toStopId} onChange={() => point('to', b.stopId)} />
                <span><strong>{fmtTime(b.at)} · {b.name}</strong><span className="small tv-muted">{b.address || b.landmark}</span></span></label>
            ))}</fieldset>
        </section>
      )}

      {o.mode !== 'bus' && (
        <section className="tv-sec" aria-labelledby="tv-cls">
          <h2 className="tv-h2" id="tv-cls">{o.mode === 'train' ? 'Class & availability' : 'Fare'}</h2>
          <div className="tv-fares" role="radiogroup" aria-labelledby="tv-cls">
            {o.classes.map((c) => (
              <label key={c.code} className={`tv-fare${cls === c.code ? ' is-on' : ''}${c.bookable ? '' : ' is-off'}`}>
                <input type="radio" name="cls" checked={cls === c.code} disabled={!c.bookable} onChange={() => setCls(c.code)} />
                <span className="tv-fare__head"><strong>{c.name}{c.fareType ? ` · ${c.fareType}` : ''}</strong><span className={`tv-avail tv-avail--${c.availability.status}`}>{c.availability.label}</span></span>
                <strong className="tv-fare__price">{formatMoney(c.perPerson)}<span className="small tv-muted"> /person</span></strong>
                <span className="small tv-muted">Fare {formatMoney(c.fare)}{Number(c.fees) ? ` + charges ${formatMoney(c.fees)}` : ''}{Number(c.tax) ? ` + GST ${formatMoney(c.tax)}` : ''}</span>
                <ul className="tv-fare__rules small">
                  <li>{c.refundable ? 'Refundable under the cancellation rules' : 'Non-refundable'}</li>
                  {o.mode === 'flight' && <li>{c.changeFee == null ? 'Date change not allowed' : Number(c.changeFee) ? `Date change fee ${formatMoney(c.changeFee)} + fare difference` : 'Free date change (fare difference applies)'}</li>}
                  {c.meal && <li>{c.meal}</li>}
                  {o.mode === 'flight' && o.service.baggage && <li>Baggage: {o.service.baggage.cabin} cabin{o.service.baggage.checkIn ? ` · ${o.service.baggage.checkIn} check-in` : ''}</li>}
                  {c.infantFare && <li>Infant on lap {formatMoney(c.infantFare)}</li>}
                  {c.availability.status === 'rac' && <li>RAC: you can board and share a side-lower berth; it may be confirmed before the chart.</li>}
                  {c.availability.status === 'waitlist' && <li>Waitlist: you can’t board unless it’s confirmed; fully waitlisted tickets are refunded in full.</li>}
                </ul>
              </label>
            ))}
          </div>
        </section>
      )}

      <section className="tv-sec"><h2 className="tv-h2">Route</h2><RouteTimeline route={o.route} /></section>
      <section className="tv-sec tv-facts">
        <div><h3 className="tv-h3">Cancellation</h3><p className="small">{o.policy}</p>
          {o.policyRules.length > 0 && <table className="tv-table small"><thead><tr><th scope="col">Cancel</th><th scope="col">Fee</th></tr></thead>
            <tbody>{[...o.policyRules].sort((a, b) => b.hours - a.hours).map((r) => <tr key={r.hours}><td>{r.hours}+ hours before</td><td>{r.feePercent}%</td></tr>)}
              <tr><td>Later</td><td>100%</td></tr></tbody></table>}</div>
        {o.service.amenities.length > 0 && <div><h3 className="tv-h3">On board</h3><ul className="tv-amen small">{o.service.amenities.map((a) => <li key={a}><Icon name="check" size={12} /> {a}</li>)}</ul></div>}
        <div><h3 className="tv-h3">Booked with</h3><p className="small">{o.operator.name} · {o.source}</p></div>
      </section>

      <div className="tv-cta">
        <div>{o.mode === 'bus' ? (picked.length ? <strong>{formatMoney(String(seatTotal))}</strong> : <span className="small tv-muted">Choose {seats} seat{seats > 1 ? 's' : ''}</span>)
          : chosen ? <><strong>{formatMoney(String(Number(chosen.perPerson) * seats))}</strong><span className="small tv-muted"> for {seats}</span></> : null}
          {!o.bookableNow && <span className="small tv-error">Booking for this departure has closed.</span>}</div>
        <button type="button" className="tv-btn" disabled={!canGo} onClick={goBook}>Continue</button>
      </div>
    </div>
  );
}
