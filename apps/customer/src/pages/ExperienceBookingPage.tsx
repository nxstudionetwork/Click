import { useEffect, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@click/api';
import { Button, ErrorState, Icon, Sheet, Skeleton, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { fmtDay, fmtSlot, STATUS_TONE } from '../features/bookings/parts';
import { walletKey } from '../features/wallet/useWallet';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

const REASONS = ['Plans changed', 'Booked the wrong date', 'Weather', 'Health', 'Other'];

function Countdown({ until, onDone }: { until: string; onDone: () => void }) {
  const [left, setLeft] = useState(() => Math.max(0, new Date(until).getTime() - Date.now()));
  useEffect(() => {
    const t = setInterval(() => { const l = Math.max(0, new Date(until).getTime() - Date.now()); setLeft(l); if (!l) { clearInterval(t); onDone(); } }, 1000);
    return () => clearInterval(t);
  }, [until, onDone]);
  return <strong>{Math.floor(left / 60000)}:{String(Math.floor((left % 60000) / 1000)).padStart(2, '0')}</strong>;
}

/** Confirmation and booking details for a temple / attraction / experience: the entry code the provider verifies,
 *  visit instructions, payment and refund status, policy-based cancellation, support, and a review after the visit. */
export function ExperienceBookingPage() {
  useThemeOverride('bookings');
  const { id = '' } = useParams();
  const location = useLocation();
  const toast = useToast();
  const qc = useQueryClient();
  const key = ['bookings', 'booking', id];
  const q = useQuery({ queryKey: key, queryFn: () => api.bookings.booking(id) });
  const [cancelOpen, setCancelOpen] = useState(false);
  const [reason, setReason] = useState(REASONS[0]!);
  const [stars, setStars] = useState(0);
  const [comment, setComment] = useState('');
  const act = useMutation({
    mutationFn: ({ action, body }: { action: 'pay' | 'cancel' | 'review'; body: object; done: string }) => api.bookings.act(id, action, body),
    onSuccess: (b, v) => { qc.setQueryData(key, b); qc.invalidateQueries({ queryKey: ['bookings'] }); qc.invalidateQueries({ queryKey: walletKey }); setCancelOpen(false); toast(v.done); },
    onError: (e) => { toast(e instanceof ApiError ? e.message : 'Something went wrong.', 'error'); q.refetch(); },
  });
  if (q.isError) return <div className="bk-page"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  if (!q.data) return <div className="bk-page"><Skeleton height={240} radius={22} /><Skeleton height={280} radius={22} /></div>;
  const b = q.data;
  const st = location.state as { justBooked?: boolean; paymentError?: string } | null;

  return (
    <div className="bk-page" data-theme="bookings" style={{ ['--bk-accent' as string]: b.attraction.accent }}>
      <Link to="/bookings/mine" className="bk-back"><Icon name="back" size={18} /> My bookings</Link>
      {st?.justBooked && b.status === 'confirmed' && (
        <section className="bk-confirm" role="status"><span className="bk-confirm__mark" aria-hidden="true"><Icon name="check" size={26} /></span>
          <h1>Booking confirmed</h1><p className="bk-muted">Booking ID <strong>{b.number}</strong> · a confirmation is in your notifications.</p></section>
      )}
      {b.canPay && b.holdExpiresAt && (
        <section className="bk-hold" role="alert"><h2>Payment wasn’t completed</h2>
          <p className="small">{st?.paymentError || 'Your payment didn’t go through.'} Your places are held for <Countdown until={b.holdExpiresAt} onDone={() => q.refetch()} />.</p>
          <div className="bk-row2"><Link to="/wallet" className="btn btn--secondary">Add money</Link>
            <Button loading={act.isPending} onClick={() => act.mutate({ action: 'pay', body: {}, done: 'Paid — booking confirmed' })}>Try again · {formatMoney(b.total)}</Button></div>
        </section>
      )}
      {b.status === 'failed' && <p className="bk-alert"><Icon name="alert" size={14} /> Payment wasn’t completed in time, so the places were released. Nothing was charged.</p>}

      <header className="bk-dhead bk-dhead--slim">
        <span className="bk-kicker">{b.offering.kindLabel} · {b.attraction.kindLabel}</span>
        <h1 className="bk-title">{b.offering.name}</h1>
        <p className="bk-muted"><Link to={`/bookings/places/${b.attraction.slug}`}>{b.attraction.name}</Link>, {b.attraction.city}</p>
        <span className={`bk-status bk-status--${STATUS_TONE[b.status] ?? 'warn'}`}>{b.statusLabel}</span>
      </header>

      {b.entryCode && b.status === 'confirmed' && (
        <section className="bk-entry" aria-label="Entry code">
          <span className="small">Entry code</span><strong className="bk-entry__code">{b.entryCode}</strong>
          <span className="small bk-muted">{b.checkedInAt ? `Used at ${new Date(b.checkedInAt).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' })}` : b.entryNote}</span>
        </section>
      )}

      <section className="bk-sec">
        <dl className="bk-dl">
          <dt>Date</dt><dd>{fmtDay(b.visitDate, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}</dd>
          <dt>Time</dt><dd>{fmtSlot(b.slotTime)}</dd>
          {b.pickupPoint && <><dt>Pickup</dt><dd>{b.pickupPoint}</dd></>}
          <dt>Lead visitor</dt><dd>{b.lead.name} · {b.lead.phone}</dd>
          {b.visitorNames.length > 0 && <><dt>With</dt><dd>{b.visitorNames.join(', ')}</dd></>}
          <dt>Address</dt><dd>{b.address}</dd>
          {b.provider && <><dt>Provider</dt><dd>{b.provider}</dd></>}
          <dt>Cancellation</dt><dd>{b.policy}</dd>
          <dt>Payment</dt><dd>{b.paymentStatusLabel}{b.payment ? ` · Click. Wallet · ref ${b.payment.reference}` : ''}</dd>
          {b.refund && <><dt>Refund</dt><dd className="bk-ok">{formatMoney(b.refund.amount)} · {b.refund.label}</dd></>}
        </dl>
        <ul className="bk-lines">
          {b.lines.map((l) => <li key={l.visitor}><span>{l.label} × {l.qty}</span><span>{Number(l.amount) ? formatMoney(l.amount) : 'Free'}</span></li>)}
          {Number(b.discount) > 0 && <li className="bk-ok"><span>{b.offerTitle}</span><span>−{formatMoney(b.discount)}</span></li>}
          {Number(b.tax) > 0 && <li><span>Taxes (GST)</span><span>{formatMoney(b.tax)}</span></li>}
          <li className="bk-lines__total"><span>Total</span><span>{Number(b.total) ? formatMoney(b.total) : 'Free'}</span></li>
        </ul>
      </section>
      {(b.requirements || b.dressCode || b.rules.length > 0) && (
        <section className="bk-sec"><h2 className="bk-h3">Before you go</h2><ul className="small">
          {b.requirements && <li>{b.requirements}</li>}{b.dressCode && <li>Dress: {b.dressCode}</li>}{b.rules.map((x) => <li key={x}>{x}</li>)}
          {b.prohibited.length > 0 && <li>Not allowed: {b.prohibited.join(', ')}</li>}</ul></section>
      )}
      <div className="bk-actions">
        {b.latitude != null && <a className="btn btn--secondary" href={`https://www.openstreetmap.org/directions?to=${b.latitude}%2C${b.longitude}`} target="_blank" rel="noreferrer"><Icon name="compass" size={16} /> Directions</a>}
        <Button variant="secondary" onClick={() => window.print()}><Icon name="download" size={16} /> Download</Button>
        <Button variant="secondary" onClick={async () => {
          const text = `${b.title}, ${fmtDay(b.visitDate)} ${b.slotTime ? fmtSlot(b.slotTime) : ''} (${b.number})`;
          try { if (navigator.share) await navigator.share({ title: 'My booking', text }); else { await navigator.clipboard.writeText(text); toast('Copied'); } } catch { /* dismissed */ }
        }}><Icon name="share" size={16} /> Share</Button>
        <Link className="btn btn--ghost" to={`/help/new?experienceBookingId=${b.id}&category=other&subject=${encodeURIComponent(`${b.title} · ${b.number}`)}`}><Icon name="help" size={16} /> Contact support</Link>
      </div>
      {b.cancellation.allowed && <Button variant="danger" onClick={() => setCancelOpen(true)}>Cancel booking</Button>}

      {b.canReview && (
        <section className="bk-sec" aria-labelledby="bk-rv"><h2 className="bk-h2" id="bk-rv">How was your visit?</h2>
          <div className="bk-stars" role="radiogroup" aria-label="Rating">{[1, 2, 3, 4, 5].map((n) => (
            <button key={n} type="button" role="radio" aria-checked={stars === n} aria-label={`${n} star${n > 1 ? 's' : ''}`} className={n <= stars ? 'is-on' : ''} onClick={() => setStars(n)}><Icon name="star" size={22} /></button>))}</div>
          {stars > 0 && <><textarea className="bk-textarea" rows={3} maxLength={2000} value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Tips for other visitors (optional)" aria-label="Review" />
            <Button block loading={act.isPending} onClick={() => act.mutate({ action: 'review', body: { rating: stars, comment }, done: 'Thanks for your review' })}>Submit review</Button></>}
        </section>
      )}
      {b.review && <p className="bk-note small"><Icon name="star" size={14} /> You rated this visit {b.review.rating}/5.</p>}
      <section className="bk-sec"><h2 className="bk-h3">Timeline</h2>
        <ol className="bk-timeline">{b.timeline.map((t, i) => <li key={i}><strong>{t.note || t.label}</strong><span className="small bk-muted">{new Date(t.at).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })}</span></li>)}</ol></section>

      <Sheet open={cancelOpen} onClose={() => setCancelOpen(false)} label="Cancel booking">
        <div className="bk-sheet">
          <h2>Cancel this booking?</h2><p className="small">{b.policy}</p>
          <dl className="bk-dl"><dt>Cancellation fee</dt><dd>{b.cancellation.fee != null ? formatMoney(b.cancellation.fee) : '—'}</dd>
            <dt>Refund</dt><dd>{b.cancellation.refund != null && Number(b.cancellation.refund) > 0 ? `${formatMoney(b.cancellation.refund)} to your Click. Wallet, immediately` : 'No refund'}</dd></dl>
          <p className="small bk-muted">{b.cancellation.note}</p>
          <div role="radiogroup" aria-label="Reason">{REASONS.map((r) => <label key={r} className="bk-check"><input type="radio" name="reason" checked={reason === r} onChange={() => setReason(r)} /> {r}</label>)}</div>
          <Button block variant="danger" loading={act.isPending} onClick={() => act.mutate({ action: 'cancel', body: { reason }, done: 'Booking cancelled' })}>Confirm cancellation</Button>
        </div>
      </Sheet>
    </div>
  );
}
