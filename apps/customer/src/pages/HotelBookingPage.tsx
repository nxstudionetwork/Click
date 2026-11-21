import { useEffect, useState } from 'react';
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@click/api';
import { Button, ErrorState, Icon, Sheet, Skeleton, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { fmtDay, HotelImage, STATUS_TONE } from '../features/hotels/parts';
import { walletKey } from '../features/wallet/useWallet';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

const REASONS = ['Plans changed', 'Found another stay', 'Dates changed', 'Booked by mistake', 'Other'];
const ASPECTS = [['cleanliness', 'Cleanliness'], ['location', 'Location'], ['comfort', 'Comfort'], ['facilities', 'Facilities'], ['staff', 'Staff'], ['value', 'Value']] as const;
const osmDir = (lat: number, lng: number) => `https://www.openstreetmap.org/directions?to=${lat}%2C${lng}`;

function Countdown({ until, onDone }: { until: string; onDone: () => void }) {
  const [left, setLeft] = useState(() => Math.max(0, new Date(until).getTime() - Date.now()));
  useEffect(() => {
    const t = setInterval(() => { const l = Math.max(0, new Date(until).getTime() - Date.now()); setLeft(l); if (!l) { clearInterval(t); onDone(); } }, 1000);
    return () => clearInterval(t);
  }, [until, onDone]);
  const m = Math.floor(left / 60000), s = Math.floor((left % 60000) / 1000);
  return <strong aria-live="off">{m}:{String(s).padStart(2, '0')}</strong>;
}

/** Confirmation and booking details: status from the server, payment retry while the room is held, policy-based
 *  cancellation with the exact refund, receipt, directions, support and a verified review after the stay. */
export function HotelBookingPage() {
  useThemeOverride('hotels');
  const { id = '' } = useParams();
  const [sp] = useSearchParams();
  const location = useLocation();
  const toast = useToast();
  const qc = useQueryClient();
  const key = ['hotels', 'booking', id];
  const q = useQuery({ queryKey: key, queryFn: () => api.hotels.booking(id) });
  const [cancelOpen, setCancelOpen] = useState(sp.get('cancel') === '1');
  const [reason, setReason] = useState(REASONS[0]!);
  const [rv, setRv] = useState<{ overall: number; cleanliness: number; location: number; comfort: number; facilities: number; staff: number; value: number }>({ overall: 0, cleanliness: 8, location: 8, comfort: 8, facilities: 8, staff: 8, value: 8 });
  const [comment, setComment] = useState('');
  const act = useMutation({
    mutationFn: ({ action, body }: { action: 'pay' | 'cancel' | 'review'; body: object; done: string }) => api.hotels.act(id, action, body),
    onSuccess: (b, v) => { qc.setQueryData(key, b); qc.invalidateQueries({ queryKey: ['hotels'] }); qc.invalidateQueries({ queryKey: walletKey }); setCancelOpen(false); toast(v.done); },
    onError: (e) => { toast(e instanceof ApiError ? e.message : 'Something went wrong.', 'error'); q.refetch(); },
  });

  if (q.isError) return <div className="ht-page"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  if (!q.data) return <div className="ht-page"><Skeleton height={240} radius={26} /><Skeleton height={300} radius={22} /></div>;
  const b = q.data;
  const st = location.state as { justBooked?: boolean; paymentError?: string } | null;
  const celebrate = st?.justBooked && b.status === 'confirmed';

  return (
    <div className="ht-page" data-theme="hotels" style={{ ['--ht-accent' as string]: b.property.accent }}>
      <Link to="/hotels/bookings" className="ht-back"><Icon name="back" size={18} /> My stays</Link>
      {celebrate && (
        <section className="ht-confirm" role="status">
          <span className="ht-confirm__mark" aria-hidden="true"><Icon name="check" size={26} /></span>
          <h1>Hotel booked successfully</h1>
          <p className="ht-muted">Booking ID <strong>{b.number}</strong> · confirmation sent to your notifications.</p>
        </section>
      )}
      {b.canPay && b.holdExpiresAt && (
        <section className="ht-hold" role="alert">
          <h2>Payment not completed</h2>
          <p className="small">{st?.paymentError || 'Your payment didn’t go through.'} The room is held for you for <Countdown until={b.holdExpiresAt} onDone={() => q.refetch()} />.</p>
          <div className="ht-row2">
            <Link to="/wallet" className="btn btn--secondary">Add money</Link>
            <Button loading={act.isPending} onClick={() => act.mutate({ action: 'pay', body: {}, done: 'Paid — booking confirmed' })}>Retry payment · {formatMoney(b.total)}</Button>
          </div>
        </section>
      )}

      <header className="ht-bkhead">
        <HotelImage src={b.property.imageUrl} name={b.property.name} accent={b.property.accent} className="ht-bkhead__img" />
        <div>
          <span className="ht-kicker">{b.number}</span>
          <h1 className="ht-title">{b.property.name}</h1>
          <span className={`ht-status ht-status--${STATUS_TONE[b.status] ?? 'warn'}`}>{b.statusLabel}</span>
          <p className="small ht-muted">{b.address}</p>
        </div>
      </header>

      <section className="ht-stayfacts">
        <div><span className="ht-kicker">Check-in</span><strong>{fmtDay(b.checkIn, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })}</strong><span className="small ht-muted">from {b.checkInTime}</span></div>
        <div><span className="ht-kicker">Check-out</span><strong>{fmtDay(b.checkOut, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })}</strong><span className="small ht-muted">by {b.checkOutTime}</span></div>
        <div><span className="ht-kicker">Stay</span><strong>{b.nights} night{b.nights > 1 ? 's' : ''}</strong><span className="small ht-muted">{b.rooms} room{b.rooms > 1 ? 's' : ''} · {b.adults} adult{b.adults > 1 ? 's' : ''}{b.children ? ` · ${b.children} child` : ''}</span></div>
      </section>

      <section className="ht-sec ht-receipt" id="receipt">
        <h2 className="ht-h2">Booking details</h2>
        <dl className="ht-dl">
          <dt>Room</dt><dd>{b.roomName} · {b.rateName}</dd><dt>Meal plan</dt><dd>{b.mealLabel}</dd>
          <dt>Guest</dt><dd>{b.guest.name} · {b.guest.phone}{b.guest.email ? ` · ${b.guest.email}` : ''}</dd>
          {b.guest.others.length > 0 && <><dt>Also staying</dt><dd>{b.guest.others.join(', ')}</dd></>}
          {b.specialRequests && <><dt>Requests</dt><dd>{b.specialRequests}</dd></>}
          <dt>Cancellation</dt><dd>{b.policy}</dd>
          <dt>Payment</dt><dd>{b.paymentModeLabel} · {b.paymentStatusLabel}{b.payment ? ` · ref ${b.payment.reference}` : ''}</dd>
        </dl>
        <ul className="ht-lines">
          {b.nightly.map((n) => <li key={n.date}><span>{fmtDay(n.date)}{b.rooms > 1 ? ` × ${b.rooms}` : ''}</span><span>{formatMoney(String(Number(n.price) * b.rooms))}</span></li>)}
          {Number(b.discount) > 0 && <li className="ht-ok"><span>{b.offerTitle}</span><span>−{formatMoney(b.discount)}</span></li>}
          <li><span>Taxes (GST)</span><span>{formatMoney(b.tax)}</span></li>
          <li className="ht-lines__total"><span>{b.paymentStatus === 'paid' ? 'Total paid' : 'Total'}</span><span>{formatMoney(b.total)}</span></li>
          {Number(b.refunded) > 0 && <li className="ht-ok"><span>Refunded to Click. Wallet</span><span>{formatMoney(b.refunded)}</span></li>}
        </ul>
      </section>

      <div className="ht-actions">
        <a className="btn btn--secondary" href={osmDir(b.latitude, b.longitude)} target="_blank" rel="noreferrer"><Icon name="compass" size={16} /> Directions</a>
        <Button variant="secondary" onClick={() => window.print()}><Icon name="receipt" size={16} /> Receipt</Button>
        <Button variant="secondary" onClick={async () => {
          const text = `${b.property.name}, ${fmtDay(b.checkIn)} – ${fmtDay(b.checkOut)} (${b.number})`;
          try { if (navigator.share) await navigator.share({ title: 'My stay', text }); else { await navigator.clipboard.writeText(text); toast('Copied'); } } catch { /* dismissed */ }
        }}><Icon name="share" size={16} /> Share</Button>
        <Link className="btn btn--secondary" to={`/hotels/${b.property.id}`}><Icon name="hotel" size={16} /> View property</Link>
        <Link className="btn btn--ghost" to={`/help/new?hotelBookingId=${b.id}&category=other&subject=${encodeURIComponent(`${b.property.name} · ${b.number}`)}`}><Icon name="help" size={16} /> Contact support</Link>
        <button type="button" className="btn btn--ghost" disabled title="Trips aren’t available on Click yet">Add to trip (soon)</button>
      </div>
      {b.cancellation.allowed && <Button variant="danger" onClick={() => setCancelOpen(true)}>Cancel booking</Button>}
      {b.isActive && <p className="small ht-muted">{b.modification}</p>}

      <section className="ht-sec"><h2 className="ht-h2">Timeline</h2>
        <ol className="ht-timeline">{b.timeline.map((t, i) => <li key={i}><strong>{t.note || t.label}</strong><span className="small ht-muted">{new Date(t.at).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })}</span></li>)}</ol>
      </section>

      {b.canReview && (
        <section className="ht-review" aria-labelledby="ht-rv">
          <h2 id="ht-rv">How was your stay?</h2>
          <label className="ht-field"><span className="ht-field__label">Overall (1–10)</span>
            <div className="ht-scale" role="radiogroup" aria-label="Overall score">{Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
              <button key={n} type="button" role="radio" aria-checked={rv.overall === n} className={rv.overall === n ? 'is-on' : ''} onClick={() => setRv({ ...rv, overall: n })}>{n}</button>
            ))}</div></label>
          {rv.overall > 0 && (
            <>
              {ASPECTS.map(([k, l]) => (
                <label key={k} className="ht-range"><span className="small">{l}</span>
                  <input type="range" min={1} max={10} value={rv[k]} onChange={(e) => setRv({ ...rv, [k]: Number(e.target.value) })} aria-valuetext={`${rv[k]} out of 10`} />
                  <strong className="small">{rv[k]}</strong></label>
              ))}
              <textarea className="ht-textarea" rows={3} maxLength={3000} placeholder="What should other guests know? (optional)" value={comment} onChange={(e) => setComment(e.target.value)} aria-label="Review" />
              <Button block loading={act.isPending} onClick={() => act.mutate({ action: 'review', body: { ...rv, comment }, done: 'Thanks for your review' })}>Submit review</Button>
            </>
          )}
        </section>
      )}
      {b.review && <p className="ht-note"><Icon name="star" size={14} /> You rated this stay {b.review.overall}/10.</p>}

      <Sheet open={cancelOpen} onClose={() => setCancelOpen(false)} label="Cancel booking">
        <div className="ht-sheet">
          <h2>Cancel this booking?</h2>
          <p className="small">{b.policy}</p>
          <dl className="ht-dl">
            <dt>Cancellation fee</dt><dd>{b.cancellation.fee != null ? formatMoney(b.cancellation.fee) : '—'}</dd>
            <dt>Refund</dt><dd>{b.cancellation.refund != null ? `${formatMoney(b.cancellation.refund)} to your Click. Wallet, immediately` : 'Nothing was charged online'}</dd>
          </dl>
          <p className="small ht-muted">{b.cancellation.note}</p>
          <div role="radiogroup" aria-label="Reason">{REASONS.map((r) => <label key={r} className="ht-check"><input type="radio" name="reason" checked={reason === r} onChange={() => setReason(r)} /> {r}</label>)}</div>
          <Button block variant="danger" loading={act.isPending} disabled={!b.cancellation.allowed} onClick={() => act.mutate({ action: 'cancel', body: { reason }, done: 'Booking cancelled' })}>Cancel booking</Button>
        </div>
      </Sheet>
    </div>
  );
}
