import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type Ride, type RideStatus } from '@click/api';
import { useThemeOverride } from '../components/layout/AppShell';
import { Button, EmptyState, ErrorState, Icon, Sheet, Skeleton, TextArea, useConfirm, useToast } from '../components/ui';
import { RideMap } from '../features/ride/RideMap';
import { walletKey } from '../features/wallet/useWallet';
import { api } from '../lib/api';
import { formatDateTime, formatMoney, formatTime } from '../lib/format';

const ACTIVE: RideStatus[] = ['searching', 'driver_assigned', 'driver_arrived', 'in_progress'];
const STEPS: { status: RideStatus; label: string }[] = [
  { status: 'searching', label: 'Finding your ride' },
  { status: 'driver_assigned', label: 'Driver on the way' },
  { status: 'driver_arrived', label: 'Driver has arrived' },
  { status: 'in_progress', label: 'Trip in progress' },
  { status: 'completed', label: 'Completed' },
];
const COMPLIMENTS = [{ id: 'safe_driving', label: 'Safe driving' }, { id: 'clean_vehicle', label: 'Clean vehicle' }, { id: 'on_time', label: 'On time' }, { id: 'friendly', label: 'Friendly' }];

/** A ride's live status (server-controlled; polled while active), driver identity, safety tools, receipt and rating. */
export function RideTripPage() {
  useThemeOverride('ride');
  const { id = '' } = useParams();
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const navigate = useNavigate();
  const [safety, setSafety] = useState(false);
  const key = ['customer', 'rides', id];
  const ride = useQuery({
    queryKey: key, queryFn: () => api.customer.rides.get(id),
    refetchInterval: (q) => (q.state.data && (ACTIVE.includes(q.state.data.status) || q.state.data.status === 'scheduled') ? 5_000 : false),
  });
  const cancel = useMutation({
    mutationFn: () => api.customer.rides.cancel(id),
    onSuccess: (r) => { qc.setQueryData(key, r); qc.invalidateQueries({ queryKey: walletKey }); toast('Ride cancelled'); },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t cancel. Try again.', 'error'),
  });

  if (ride.isError) {
    return ride.error instanceof ApiError && ride.error.status === 404
      ? <EmptyState icon="ride" title="Ride not found" action={<Link className="btn btn--outline" to="/rides">Book a ride</Link>} />
      : <ErrorState error={ride.error} onRetry={() => ride.refetch()} />;
  }
  if (ride.isPending) return <div className="stack"><Skeleton height={260} radius={22} /><Skeleton height={160} radius={18} /></div>;
  const r = ride.data;
  const stepIdx = STEPS.findIndex((s) => s.status === r.status);
  const askCancel = async () => {
    if (await confirm({ title: 'Cancel this ride?', message: r.paymentMethod === 'wallet' ? 'Your wallet payment will be refunded.' : 'No charge applies before the trip starts.', confirmLabel: 'Cancel ride', cancelLabel: 'Keep ride', danger: true })) cancel.mutate();
  };

  return (
    <div className="ride ride-trip">
      <div className="ride__grid">
        <div className="ride__map-wrap">
          <RideMap pickup={r.pickup} drop={r.drop} stops={r.stops} driver={r.driver?.location ?? null} className="ride__map" />
          {r.driver?.location && (
            <span className="ride__estimate">{r.driver.location.live ? 'Driver location · live' : `Driver location from ${formatTime(r.driver.location.reportedAt)}`}</span>
          )}
        </div>

        <div className="ride__console">
          <StatusHeader ride={r} />

          {r.status !== 'cancelled' && r.status !== 'no_driver' && r.status !== 'scheduled' && (
            <ol className="ride-steps" aria-label="Ride progress">
              {STEPS.map((s, i) => <li key={s.status} className={`${i < stepIdx ? 'done' : ''} ${i === stepIdx ? 'current' : ''}`}>{s.label}</li>)}
            </ol>
          )}

          {r.driver && r.status !== 'cancelled' && <DriverCard ride={r} />}

          <section className="ride-trip__route" aria-label="Trip">
            <div className="route-row route-row--pickup"><span className="route-row__marker" /><div><span className="route-row__title">Pick-up</span><span className="route-row__value">{r.pickup.label}</span>{r.pickup.address && <span className="route-row__addr">{r.pickup.address}</span>}</div></div>
            {r.stops.map((s, i) => <div key={i} className="route-row route-row--stop"><span className="route-row__marker">{i + 1}</span><div><span className="route-row__title">Stop {i + 1}</span><span className="route-row__value">{s.label}</span></div></div>)}
            <div className="route-row route-row--drop"><span className="route-row__marker" /><div><span className="route-row__title">Drop</span><span className="route-row__value">{r.drop.label}</span>{r.drop.address && <span className="route-row__addr">{r.drop.address}</span>}</div></div>
          </section>

          <section className="ride-receipt" aria-label="Fare">
            <div className="spread"><span>{r.rideType.name} · {r.distanceKm} km · ~{r.durationMinutes} min</span><strong>{formatMoney(r.fare.total, r.currency)}</strong></div>
            {Number(r.fare.discount) > 0 && <div className="spread small"><span>{r.offerTitle || 'Offer'}</span><span className="totals__saving">−{formatMoney(r.fare.discount, r.currency)}</span></div>}
            <div className="spread small muted"><span>{r.paymentMethod === 'cash' ? 'Cash' : 'Click. Wallet'}</span><span>{paymentLabel(r)}</span></div>
            <div className="spread small muted"><span>Ride ID</span><span>{r.number}</span></div>
            {r.passengerName && <div className="spread small muted"><span>Passenger</span><span>{r.passengerName}</span></div>}
          </section>

          <div className="row" style={{ flexWrap: 'wrap' }}>
            {ACTIVE.includes(r.status) && r.status !== 'searching' && <Button variant="secondary" size="sm" onClick={() => setSafety(true)}><Icon name="shield" size={16} /> Safety</Button>}
            {r.canCancel && <Button variant="danger" size="sm" loading={cancel.isPending} onClick={askCancel}>Cancel ride</Button>}
            {(r.status === 'no_driver' || r.status === 'cancelled' || r.status === 'completed') && (
              <Button size="sm" onClick={() => navigate(`/rides?again=${r.id}`)}>{r.status === 'completed' ? 'Ride again' : 'Try again'}</Button>
            )}
            <Link to={`/help/new?category=ride`} className="btn btn--outline btn--sm">Get help</Link>
          </div>

          {r.status === 'completed' && <RateRide ride={r} />}
        </div>
      </div>
      <SafetySheet open={safety} ride={r} onClose={() => setSafety(false)} />
    </div>
  );
}

function paymentLabel(r: Ride) {
  const s = r.payment?.status;
  if (r.paymentMethod === 'cash') return s === 'captured' ? 'Paid to driver' : s === 'cancelled' ? 'Not charged' : 'Pay the driver at the end';
  return s === 'captured' ? 'Paid' : s === 'refunded' ? 'Refunded to wallet' : s ?? '';
}

function StatusHeader({ ride: r }: { ride: Ride }) {
  if (r.status === 'searching') {
    return (
      <section className="ride-status ride-status--search" role="status">
        <span className="ride-radar" aria-hidden="true"><span /><span /><Icon name="ride" size={22} /></span>
        <div><h1>Finding your ride</h1><p>Offering your trip to drivers near your pickup. We’ll show them as soon as one accepts.</p></div>
      </section>
    );
  }
  const copy: Partial<Record<RideStatus, [string, string]>> = {
    scheduled: ['Ride scheduled', r.scheduledFor ? `Pickup ${formatDateTime(r.scheduledFor)}. We’ll start finding a driver shortly before.` : ''],
    driver_assigned: ['Your driver is on the way', 'Meet at your pickup point. Check the plate before you get in.'],
    driver_arrived: ['Your driver has arrived', 'Match the vehicle and plate below before getting in.'],
    in_progress: ['Trip in progress', `Heading to ${r.drop.label}.`],
    completed: ['Ride completed', r.completedAt ? `Arrived ${formatTime(r.completedAt)}${r.startedAt && r.completedAt ? ` · ${Math.max(1, Math.round((+new Date(r.completedAt) - +new Date(r.startedAt)) / 60000))} min trip` : ''}` : ''],
    cancelled: ['Ride cancelled', r.paymentMethod === 'wallet' ? 'Your wallet payment has been refunded.' : 'You haven’t been charged.'],
    no_driver: ['No rides available right now', 'No driver was free near your pickup. You haven’t been charged. Try another ride type or pickup point.'],
  };
  const [title, text] = copy[r.status] ?? [r.statusLabel, ''];
  return (
    <section className={`ride-status ride-status--${r.status}`} role="status">
      <span className="ride-status__icon" aria-hidden="true"><Icon name={r.status === 'completed' ? 'check' : r.status === 'cancelled' || r.status === 'no_driver' ? 'alert' : 'ride'} size={22} /></span>
      <div><h1>{title}</h1>{text && <p>{text}</p>}</div>
    </section>
  );
}

function DriverCard({ ride: r }: { ride: Ride }) {
  const d = r.driver!;
  return (
    <section className="driver-card" aria-label="Your driver and vehicle">
      <span className="driver-card__avatar" aria-hidden="true">{d.name[0]}</span>
      <div className="driver-card__who">
        <strong>{d.name}</strong>
        <span>{d.rating ? <><Icon name="star" size={13} /> {d.rating.toFixed(1)} · {d.ratingCount} {d.ratingCount === 1 ? 'rating' : 'ratings'}</> : 'New driver'}</span>
      </div>
      <div className="driver-card__vehicle">
        <span className="driver-card__plate">{d.plate}</span>
        <span>{[d.vehicleColor, d.vehicleModel].filter(Boolean).join(' ')}</span>
      </div>
    </section>
  );
}

function SafetySheet({ open, ride: r, onClose }: { open: boolean; ride: Ride; onClose: () => void }) {
  const toast = useToast();
  const [report, setReport] = useState('');
  const log = (kind: 'sos' | 'share' | 'report', note = '') => api.customer.rides.safety(r.id, kind, note).catch(() => undefined);
  async function share() {
    const text = `I'm on a Click. ride (${r.number}) from ${r.pickup.label} to ${r.drop.label}.${r.driver ? ` Driver ${r.driver.name}, ${[r.driver.vehicleColor, r.driver.vehicleModel].filter(Boolean).join(' ')}, plate ${r.driver.plate}.` : ''}`;
    try {
      if (navigator.share) await navigator.share({ title: 'My Click. ride', text });
      else { await navigator.clipboard.writeText(text); toast('Trip details copied. Paste them to someone you trust.'); }
      log('share');
    } catch (e) { if ((e as Error).name !== 'AbortError') toast('Sharing isn’t available here.', 'error'); }
  }
  return (
    <Sheet open={open} onClose={onClose} label="Ride safety">
      <div className="psheet" data-theme="ride">
        <h2>Safety</h2>
        <a href="tel:112" className="safety-sos" onClick={() => log('sos', 'Customer opened emergency call')}>
          <Icon name="phone" size={20} /><span><strong>Call emergency services (112)</strong><small>Click. records this so our safety team can follow up.</small></span>
        </a>
        <button type="button" className="psheet__opt" onClick={share}><Icon name="share" />Share trip details</button>
        {r.driver && <p className="small muted">Driver {r.driver.name} · {[r.driver.vehicleColor, r.driver.vehicleModel].filter(Boolean).join(' ')} · {r.driver.plate}</p>}
        <TextArea label="Report a safety issue" maxLength={500} value={report} onChange={(e) => setReport(e.target.value)} />
        <div className="row">
          <Button variant="outline" disabled={!report.trim()} onClick={async () => { await log('report', report); setReport(''); toast('Reported. Our safety team will review it.'); }}>Send report</Button>
          <Link to="/help/new?category=ride" className="btn btn--ghost" onClick={onClose}>Contact support</Link>
        </div>
      </div>
    </Sheet>
  );
}

function RateRide({ ride: r }: { ride: Ride }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [stars, setStars] = useState(0);
  const [comment, setComment] = useState('');
  const [compliment, setCompliment] = useState('');
  const send = useMutation({
    mutationFn: () => api.customer.rides.rate(r.id, { stars, comment, compliment }),
    onSuccess: (x) => { qc.setQueryData(['customer', 'rides', r.id], x); toast('Thanks for rating your ride'); },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t send your rating.', 'error'),
  });
  if (r.rating) {
    return <section className="card card--pad stack"><h3>Your rating</h3><div className="stars">{[1, 2, 3, 4, 5].map((n) => <Icon key={n} name="star" size={20} className={n <= r.rating!.stars ? 'on' : ''} />)}</div>{r.rating.comment && <p className="muted">“{r.rating.comment}”</p>}</section>;
  }
  return (
    <section className="card card--pad stack" aria-labelledby="rate-ride-h">
      <h3 id="rate-ride-h">Rate your ride</h3>
      <div className="stars stars--input" role="radiogroup" aria-label="Rating">
        {[1, 2, 3, 4, 5].map((n) => <button key={n} type="button" role="radio" aria-checked={stars === n} aria-label={`${n} star${n > 1 ? 's' : ''}`} onClick={() => setStars(n)}><Icon name="star" size={28} className={n <= stars ? 'on' : ''} /></button>)}
      </div>
      {stars >= 4 && <div className="chips" role="group" aria-label="Compliment">{COMPLIMENTS.map((c) => <button key={c.id} type="button" className="chip" aria-pressed={compliment === c.id} onClick={() => setCompliment(compliment === c.id ? '' : c.id)}>{c.label}</button>)}</div>}
      <TextArea label="Feedback (optional)" maxLength={500} value={comment} onChange={(e) => setComment(e.target.value)} />
      <Button disabled={!stars} loading={send.isPending} onClick={() => send.mutate()} style={{ alignSelf: 'flex-start' }}>Submit rating</Button>
    </section>
  );
}
