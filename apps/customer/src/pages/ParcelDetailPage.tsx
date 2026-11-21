import { lazy, Suspense, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@click/api';
import { Button, EmptyState, ErrorState, Icon, Sheet, Skeleton, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { clock, RouteLine, StatusChip, Timeline, vehicleIcon, when } from '../features/parcels/parts';
import { walletKey } from '../features/wallet/useWallet';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

const RideMap = lazy(() => import('../features/ride/RideMap').then((m) => ({ default: m.RideMap })));
const ISSUES = ['Delayed parcel', 'Pickup issue', 'Recipient unavailable', 'Wrong address', 'Damaged parcel', 'Missing parcel', 'Payment issue', 'Cancellation', 'Other issue'];
const REASONS = ['Plans changed', 'Booked by mistake', 'Wrong address or details', 'Partner is taking too long', 'Other'];

/** Booking confirmation, tracking (status timeline; the partner's position only when their app reported it recently),
 *  PINs, proof, cancellation, sharing, repeat and parcel-specific help. Refreshes every 20 s while active. */
export function ParcelDetailPage() {
  useThemeOverride('parcel');
  const { id = '' } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const key = ['customer', 'parcels', 'detail', id];
  const q = useQuery({ queryKey: key, queryFn: () => api.parcels.get(id), refetchInterval: (query) => (query.state.data?.isActive ? 20_000 : false) });
  const [cancelOpen, setCancelOpen] = useState(false);
  const [reason, setReason] = useState(REASONS[0]!);
  const [helpOpen, setHelpOpen] = useState(false);
  const [showPins, setShowPins] = useState(false);
  const cancel = useMutation({
    mutationFn: () => api.parcels.cancel(id, reason),
    onSuccess: (p) => { qc.setQueryData(key, p); qc.invalidateQueries({ queryKey: ['customer', 'parcels'] }); qc.invalidateQueries({ queryKey: walletKey }); setCancelOpen(false); toast('Parcel cancelled'); },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t cancel.', 'error'),
  });
  const share = useMutation({
    mutationFn: () => api.parcels.share(id),
    onSuccess: async ({ token }) => {
      const url = `${window.location.origin}/track/${token}`;
      const text = `Track parcel ${q.data?.number} on Click.`;
      try {
        if (navigator.share) await navigator.share({ title: text, url });
        else { await navigator.clipboard.writeText(url); toast('Tracking link copied (valid 7 days, shows status only)'); }
      } catch { /* share sheet dismissed */ }
    },
    onError: () => toast('Couldn’t create a tracking link.', 'error'),
  });

  if (q.isError) {
    return q.error instanceof ApiError && q.error.status === 404
      ? <EmptyState icon="parcel" title="Parcel not found" message="It isn’t in your account." action={<Link to="/parcels" className="btn btn--outline">Parcel</Link>} />
      : <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  }
  if (q.isPending) return <div className="pc-page" data-theme="parcel"><Skeleton height={200} radius={24} /><Skeleton height={300} /></div>;
  const p = q.data;
  const just = (location.state as { justBooked?: boolean } | null)?.justBooked;
  const pos = p.partner?.position;
  const payLabel = p.payment.method === 'wallet' ? `Click Wallet · ${p.payment.refunded ? 'refunded' : p.payment.status === 'captured' ? 'paid' : p.payment.status}`
    : `Cash to partner at pickup · ${p.payment.status === 'captured' ? 'collected' : p.payment.status === 'cancelled' ? 'not charged' : 'to pay at pickup'}`;

  return (
    <div className="pc-page" data-theme="parcel">
      <Link to="/parcels" className="pc-back"><Icon name="back" size={18} /> Parcel</Link>

      {just && (
        <section className="pc-booked" role="status">
          <span className="pc-booked__check" aria-hidden="true"><Icon name="check" size={28} /></span>
          <h1>Parcel booked</h1>
          <p>{p.status === 'scheduled' ? `Pickup scheduled for ${when(p.scheduledFor)}.` : 'We’re offering it to delivery partners nearby. You’ll be notified as it moves.'}</p>
          <div className="row" style={{ justifyContent: 'center', flexWrap: 'wrap' }}>
            <a href="#pc-track" className="btn btn--primary btn--sm">Track parcel</a>
            <Button size="sm" variant="outline" loading={share.isPending} onClick={() => share.mutate()}>Share tracking</Button>
            <Link to="/parcels" className="btn btn--ghost btn--sm">Back to Parcel</Link>
          </div>
        </section>
      )}

      <header className="pc-dhead">
        <div>
          <span className="pc-kicker">{p.modeLabel} · {p.service.name}</span>
          <h1 className="pc-dhead__id">{p.number}</h1>
          <span className="small muted">Booked {when(p.createdAt)}</span>
        </div>
        <StatusChip status={p.status} label={p.statusLabel} />
      </header>

      <div className="pc-dgrid">
        <div className="pc-dmain">
          <section className="pc-card" id="pc-track" aria-label="Tracking">
            <RouteLine from={p.pickup.label} to={p.drop.label} stops={p.stops.length} />
            {p.deliverBy && p.isActive && <p className="small"><Icon name="clock" size={14} /> {p.service.code === 'express' ? 'Estimated delivery' : 'Delivery by'} {when(p.deliverBy)}</p>}
            <Timeline steps={p.timeline} />
            {p.partner ? (
              <div className="pc-partner">
                <span className="pc-row__icon"><Icon name={vehicleIcon(p.vehicle.code)} size={20} /></span>
                <div><strong>{p.partner.name}</strong><span className="small muted">{p.partner.vehicle}{p.partner.vehicleNumber ? ` · ${p.partner.vehicleNumber}` : ''}</span></div>
                {pos && <span className={`pc-live${pos.live ? ' is-live' : ''}`}>{pos.live ? 'Live' : `Last seen ${clock(pos.reportedAt)}`}</span>}
              </div>
            ) : p.isActive && <p className="small muted">Waiting for a partner to accept. Partners nearby have been offered this delivery.</p>}
            {pos && p.isActive && (
              <Suspense fallback={<div className="pc-map pc-map--loading">Loading map…</div>}>
                <RideMap className="pc-map" pickup={p.pickup} drop={p.drop} stops={p.stops} driver={pos} />
              </Suspense>
            )}
            {p.isActive && !pos && p.partner && <p className="small muted">The partner’s location appears here when their app shares it. Status updates come from their confirmed steps.</p>}
            {p.failureReason && <p className="pc-note pc-note--warn">Partner reported: {p.failureReason}</p>}
            {p.cancelReason && p.status === 'cancelled' && <p className="small muted">Cancelled: {p.cancelReason}</p>}
          </section>

          {(p.pins.pickup || p.pins.delivery) && (
            <section className="pc-card pc-pins" aria-label="PINs">
              <div className="spread"><h2 className="pc-h3">Verification PINs</h2>
                <button type="button" className="link-btn small" onClick={() => setShowPins((v) => !v)} aria-pressed={showPins}>{showPins ? 'Hide' : 'Show'}</button></div>
              <div className="pc-pins__row">
                {p.pins.pickup && <div><span className="pc-kicker">Pickup PIN</span><strong className="pc-pin">{showPins ? p.pins.pickup : '••••'}</strong>
                  <span className="small muted">{p.mode === 'send' ? 'Give it to the partner when you hand over.' : 'Share it with the sender for the handover.'}</span></div>}
                {p.pins.delivery && <div><span className="pc-kicker">Delivery PIN</span><strong className="pc-pin">{showPins ? p.pins.delivery : '••••'}</strong>
                  <span className="small muted">{p.mode === 'send' ? 'Share it only with the recipient.' : 'Give it to the partner when you receive it.'}</span></div>}
              </div>
            </section>
          )}

          <section className="pc-card" aria-label="Details">
            <h2 className="pc-h3">Details</h2>
            <dl className="pc-sum">
              <div><dt>Pickup</dt><dd>{p.pickup.label}<span className="small muted">{[p.pickup.address, p.pickup.name, p.pickup.phoneMasked].filter(Boolean).join(' · ')}</span>
                {p.pickup.storeReference && <span className="small muted">Reference: {p.pickup.storeReference}</span>}</dd></div>
              {p.stops.map((s) => <div key={s.position}><dt>Stop {s.position}</dt><dd>{s.label}<span className="small muted">{s.completedAt ? `Completed ${clock(s.completedAt)}` : s.address}</span></dd></div>)}
              <div><dt>Drop</dt><dd>{p.drop.label}<span className="small muted">{[p.drop.address, p.drop.name, p.drop.phoneMasked].filter(Boolean).join(' · ')}</span></dd></div>
              <div><dt>Package</dt><dd>{p.package.category} · {p.package.sizeLabel} · {p.package.weightKg} kg{p.package.dims ? ` · ${p.package.dims.join('×')} cm` : ''}
                {p.package.notes && <span className="small muted">{p.package.notes}</span>}</dd></div>
              <div><dt>Vehicle</dt><dd>{p.vehicle.name}</dd></div>
              <div><dt>Route</dt><dd>{p.distanceKm} km · about {p.durationMinutes} min<span className="small muted">Estimated from straight-line distance</span></dd></div>
            </dl>
            {p.proofs.length > 0 && (
              <div className="pc-proofs"><strong className="small">Proof</strong>
                {p.proofs.map((x, i) => <span key={i} className="small"><Icon name="check" size={13} /> {x.kindLabel}: {x.method === 'pin' ? 'PIN verified' : 'confirmed by partner'} at {when(x.at)}{x.located ? ' · partner location recorded' : ''}</span>)}
              </div>
            )}
          </section>
        </div>

        <aside className="pc-dside">
          <section className="pc-card" aria-label="Payment">
            <h2 className="pc-h3">Payment</h2>
            <dl className="pc-bill">
              <div><dt>Base fare</dt><dd>{formatMoney(p.fare.base)}</dd></div>
              <div><dt>Distance</dt><dd>{formatMoney(p.fare.distance)}</dd></div>
              {Number(p.fare.service) !== 0 && <div><dt>{p.service.name} service</dt><dd>{formatMoney(p.fare.service)}</dd></div>}
              {Number(p.fare.stops) > 0 && <div><dt>Extra stops</dt><dd>{formatMoney(p.fare.stops)}</dd></div>}
              <div><dt>Taxes</dt><dd>{formatMoney(p.fare.tax)}</dd></div>
              <div className="pc-bill__total"><dt>Total</dt><dd>{formatMoney(p.fare.total)}</dd></div>
              {Number(p.fare.cancellationFee) > 0 && <div><dt>Cancellation fee kept</dt><dd>{formatMoney(p.fare.cancellationFee)}</dd></div>}
            </dl>
            <p className="small muted">{payLabel}</p>
          </section>

          <section className="pc-card pc-actions" aria-label="Actions">
            {p.isActive && <Button variant="outline" size="sm" loading={share.isPending} onClick={() => share.mutate()}><Icon name="share" size={16} /> Share tracking</Button>}
            {p.cancellation.allowed && <Button variant="danger" size="sm" onClick={() => setCancelOpen(true)}>Cancel parcel</Button>}
            {!p.cancellation.allowed && p.cancellation.note && <p className="small muted">{p.cancellation.note}</p>}
            {!p.isActive && <Button size="sm" variant="secondary" onClick={() => navigate(`/parcels?repeat=${p.id}`)}>Repeat this delivery</Button>}
            <Button size="sm" variant={p.supportRequired ? 'primary' : 'outline'} onClick={() => setHelpOpen(true)}>{p.supportRequired ? 'Support needed · get help' : 'Get help'}</Button>
            {p.tickets.map((t) => <Link key={t.id} to={`/help/tickets/${t.id}`} className="small">Request {t.reference} · {t.status.replace('_', ' ')}</Link>)}
          </section>
        </aside>
      </div>

      <Sheet open={cancelOpen} onClose={() => setCancelOpen(false)} label="Cancel parcel">
        <div className="pc-review">
          <h2>Cancel {p.number}?</h2>
          <p className="small">{p.cancellation.note}</p>
          <fieldset className="pc-reasons"><legend className="small">Reason</legend>
            {REASONS.map((r) => <label key={r} className="option"><input type="radio" name="reason" checked={reason === r} onChange={() => setReason(r)} /> {r}</label>)}</fieldset>
          <Button variant="danger" block loading={cancel.isPending} onClick={() => cancel.mutate()}>
            Cancel parcel{p.cancellation.fee && Number(p.cancellation.fee) > 0 ? ` · ₹${Number(p.cancellation.fee).toFixed(0)} fee` : ''}</Button>
          <Button variant="ghost" block onClick={() => setCancelOpen(false)}>Keep it</Button>
        </div>
      </Sheet>
      <Sheet open={helpOpen} onClose={() => setHelpOpen(false)} label="Get help">
        <div className="pc-review">
          <h2>What’s wrong with {p.number}?</h2>
          <div className="pc-issues">
            {ISSUES.map((i) => <Link key={i} className="pc-issue" to={`/help/new?parcelId=${p.id}&category=${i === 'Payment issue' ? 'payment' : 'delivery'}&subject=${encodeURIComponent(`${i} · ${p.number}`)}`}>{i}<Icon name="right" size={16} /></Link>)}
          </div>
        </div>
      </Sheet>
    </div>
  );
}
