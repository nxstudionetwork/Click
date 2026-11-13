import { useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@click/api';
import { Button, ErrorState, Icon, Sheet, Skeleton, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { BOOKING_STEPS, fmtDate, ProviderMark, Stars } from '../features/events/parts';
import { walletKey } from '../features/wallet/useWallet';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

const REASONS = ['Plans changed', 'Date changed', 'Found another team', 'Budget changed', 'Booked by mistake', 'Other'];
const ASPECTS = [['quality', 'Quality of work'], ['communication', 'Communication'], ['value', 'Value for money']] as const;

/** An event booking: status, the provider's milestones, payment, requirements, cancellation by the provider's terms,
 *  support and a verified review after the event. Refreshes while active so the team's updates appear. */
export function EventBookingPage() {
  useThemeOverride('events');
  const { id = '' } = useParams();
  const location = useLocation();
  const toast = useToast();
  const qc = useQueryClient();
  const key = ['eventhub', 'booking', id];
  const q = useQuery({ queryKey: key, queryFn: () => api.eventHub.booking(id), refetchInterval: (query) => (query.state.data?.isActive ? 30_000 : false) });
  const [cancelOpen, setCancelOpen] = useState(false);
  const [reason, setReason] = useState(REASONS[0]!);
  const [review, setReview] = useState({ overall: 0, quality: 0, communication: 0, value: 0, comment: '' });
  const act = useMutation({
    mutationFn: ({ action, body }: { action: 'pay' | 'cancel' | 'review'; body: object; done: string }) => api.eventHub.act(id, action, body),
    onSuccess: (b, v) => { qc.setQueryData(key, b); qc.invalidateQueries({ queryKey: ['eventhub'] }); qc.invalidateQueries({ queryKey: walletKey }); setCancelOpen(false); toast(v.done); },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Something went wrong.', 'error'),
  });

  if (q.isError) return <div className="ev-page"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  if (!q.data) return <div className="ev-page"><Skeleton height={200} radius={24} /><Skeleton height={320} radius={22} /></div>;
  const b = q.data;
  const reached = new Set(b.timeline.map((t) => t.to));
  const idx = Math.max(...BOOKING_STEPS.map((s, i) => (reached.has(s.status) || s.status === b.status ? i : -1)));

  return (
    <div className="ev-page" data-theme="events" style={{ ['--ev-accent' as string]: b.provider.accent }}>
      <Link to="/events/mine" className="ev-back"><Icon name="back" size={18} /> My events</Link>
      {(location.state as { justBooked?: boolean } | null)?.justBooked && (
        <div className="ev-banner" role="status"><Icon name="check" size={18} /> {b.status === 'confirmed' ? 'Booking confirmed and paid.' : `Booking held. Pay by ${fmtDate(b.payBy)} to keep it.`}</div>
      )}
      <header className="ev-planhead">
        <span className="ev-kicker">{b.number} · {b.plan.eventType}</span>
        <h1>{b.title}</h1>
        <p className={`ev-status ev-status--${b.status}`}>{b.statusLabel}</p>
        <div className="ev-planfacts small">
          <span><Icon name="ticket" size={14} /> {fmtDate(b.eventDate, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}{b.startTime ? `, ${b.startTime}` : ''}</span>
          <span><Icon name="team" size={14} /> {b.guests} guests</span>
          <span><Icon name="pin" size={14} /> {[b.address.line1, b.address.line2, b.address.city].filter(Boolean).join(', ')}</span>
        </div>
      </header>

      <div className="ev-bookpro">
        <ProviderMark p={b.provider} size={52} />
        <div><strong>{b.provider.name}</strong><span className="small ev-muted">{b.provider.verified ? 'Verified · ' : ''}{b.teamNote ? `Team: ${b.teamNote}` : 'Team details appear when assigned'}</span></div>
        <Link to={`/events/providers/${b.provider.id}`} className="ev-link small">Profile</Link>
      </div>

      {b.canPay && (
        <section className="ev-pay" aria-labelledby="ev-pay-h">
          <h2 id="ev-pay-h">Payment pending</h2>
          <p>Pay <strong>{formatMoney(b.total)}</strong> from your Click. Wallet by {fmtDate(b.payBy)} to keep this date.</p>
          <Button block loading={act.isPending} onClick={() => act.mutate({ action: 'pay', body: {}, done: 'Paid — booking confirmed' })}>Pay {formatMoney(b.total)}</Button>
        </section>
      )}

      <section className="ev-sec">
        <h2 className="ev-h2">Status</h2>
        {b.status === 'cancelled' ? <p className="ev-note">Cancelled{b.cancelReason ? ` · ${b.cancelReason}` : ''}. {Number(b.refunded) > 0 ? `${formatMoney(b.refunded)} refunded to your Click. Wallet.` : ''}</p> : (
          <ol className="ev-timeline">{BOOKING_STEPS.map((s, i) => {
            const t = [...b.timeline].reverse().find((x) => x.to === s.status);
            return <li key={s.status} className={i < idx ? 'is-done' : i === idx ? 'is-now' : ''}><span className="ev-timeline__dot" /><span><strong>{s.label}</strong>{t && <span className="small ev-muted">{new Date(t.at).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })}{t.note ? ` · ${t.note}` : ''}</span>}</span></li>;
          })}</ol>
        )}
      </section>

      <section className="ev-sec">
        <h2 className="ev-h2">Event timeline</h2>
        <ul className="ev-milestones">{b.milestones.map((m) => (
          <li key={m.key} className={m.doneAt ? 'is-done' : ''}>
            <Icon name={m.doneAt ? 'check' : 'clock'} size={14} />
            <span><strong>{m.label}</strong><span className="small ev-muted">{m.doneAt ? `Done ${new Date(m.doneAt).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}` : m.dueDate ? `By ${fmtDate(m.dueDate, { day: 'numeric', month: 'short' })}` : ''}{m.note ? ` · ${m.note}` : ''}</span></span>
          </li>
        ))}</ul>
        <Link to={`/events/plans/${b.plan.id}?tab=checklist`} className="ev-link small">Open your event checklist</Link>
      </section>

      <section className="ev-sec">
        <h2 className="ev-h2">Bill</h2>
        <ul className="ev-lines">{b.lines.map((l, i) => <li key={i}><span>{l.label}</span><span>{formatMoney(l.amount)}</span></li>)}
          {Number(b.discount) > 0 && <li><span>Discount</span><span>−{formatMoney(b.discount)}</span></li>}
          <li><span>Tax</span><span>{formatMoney(b.tax)}</span></li>
          <li className="ev-lines__total"><span>Total</span><span>{formatMoney(b.total)}</span></li>
          <li><span>Payment</span><span>{b.paymentStatusLabel}{b.payment ? ` · ${b.payment.method === 'wallet' ? 'Click. Wallet' : b.payment.method}` : ''}</span></li>
          {Number(b.refunded) > 0 && <li><span>Refunded</span><span>{formatMoney(b.refunded)}</span></li>}
        </ul>
        {b.package && <p className="small ev-muted">Package: {b.package}</p>}
        {b.quoteVersion && <p className="small ev-muted">From quote v{b.quoteVersion}</p>}
        {b.terms && <p className="small ev-muted">Terms: {b.terms}</p>}
      </section>

      {(b.plan.requirements || b.plan.attachments.length > 0) && (
        <section className="ev-sec">
          <h2 className="ev-h2">Your requirements</h2>
          {b.plan.requirements && <p>{b.plan.requirements}</p>}
          {b.plan.attachments.length > 0 && <div className="ev-photos">{b.plan.attachments.map((a) => <a key={a.id} className="ev-thumb" href={a.src} target="_blank" rel="noreferrer"><img src={a.thumb} alt="Reference" /></a>)}</div>}
        </section>
      )}

      {b.canReview && (
        <section className="ev-review" aria-labelledby="ev-r">
          <h2 id="ev-r">Review {b.provider.name}</h2>
          <Stars label="Overall" value={review.overall} onChange={(n) => setReview((r) => ({ ...r, overall: n, quality: r.quality || n, communication: r.communication || n, value: r.value || n }))} />
          {review.overall > 0 && (
            <>
              {ASPECTS.map(([k, l]) => <div key={k} className="ev-aspectrow"><span className="small">{l}</span><Stars label={l} value={review[k]} onChange={(n) => setReview((r) => ({ ...r, [k]: n }))} /></div>)}
              <textarea className="ev-textarea" rows={3} maxLength={1500} placeholder="How was it? (optional)" value={review.comment} onChange={(e) => setReview((r) => ({ ...r, comment: e.target.value }))} aria-label="Review" />
              <Button block loading={act.isPending} onClick={() => act.mutate({ action: 'review', body: review, done: 'Thanks for your review' })}>Submit review</Button>
              <p className="small ev-muted">Shown with a “Verified booking” label. Photo reviews aren’t supported yet.</p>
            </>
          )}
        </section>
      )}
      {b.review && <section className="ev-sec"><h2 className="ev-h2">Your review</h2><p className="ev-rating"><Icon name="star" size={14} /> {b.review.overall} / 5</p>{b.review.comment && <p>{b.review.comment}</p>}</section>}

      <div className="ev-row">
        {b.cancellation.allowed && <Button variant="secondary" onClick={() => setCancelOpen(true)}>Cancel booking</Button>}
        <Link to={`/help/new?eventBookingId=${b.id}&category=other&subject=${encodeURIComponent(`${b.title} · ${b.number}`)}`} className="btn btn--ghost"><Icon name="help" size={16} /> Get help</Link>
      </div>
      {!b.cancellation.allowed && b.isActive && <p className="small ev-muted">{b.cancellation.note}</p>}
      {b.tickets.length > 0 && <p className="small">Support: {b.tickets.map((t) => <Link key={t.id} to={`/help/tickets/${t.id}`} className="ev-link">{t.reference} ({t.status}) </Link>)}</p>}

      <Sheet open={cancelOpen} onClose={() => setCancelOpen(false)} label="Cancel booking">
        <div className="ev-sheet">
          <h2>Cancel this booking?</h2>
          <p className="small">{b.cancellation.note}</p>
          <div role="radiogroup" aria-label="Reason">{REASONS.map((r) => <label key={r} className="ev-check"><input type="radio" name="reason" checked={reason === r} onChange={() => setReason(r)} /> {r}</label>)}</div>
          <Button block variant="danger" loading={act.isPending} onClick={() => act.mutate({ action: 'cancel', body: { reason }, done: 'Booking cancelled' })}>Cancel booking</Button>
        </div>
      </Sheet>
    </div>
  );
}
