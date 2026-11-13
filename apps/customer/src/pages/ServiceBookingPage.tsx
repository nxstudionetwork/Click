import { useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type ServiceBookingDetail, type ServiceReviewInput } from '@click/api';
import { Button, ErrorState, Icon, Sheet, Skeleton, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { ProAvatar, Rating, STATUS_STEPS } from '../features/pros/parts';
import { useWallet, walletKey } from '../features/wallet/useWallet';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

const REASONS = ['Plans changed', 'Booked by mistake', 'Found someone else', 'Wrong address or time', 'Professional is taking too long', 'Other'];
const ASPECTS = [['quality', 'Work quality'], ['behaviour', 'Behaviour'], ['timeliness', 'On time']] as const;
const when = (iso: string) => new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' });

function Stars({ value, onChange, label }: { value: number; onChange: (n: number) => void; label: string }) {
  return (
    <div className="sv-stars" role="radiogroup" aria-label={label}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button key={n} type="button" role="radio" aria-checked={value === n} aria-label={`${n} star${n > 1 ? 's' : ''}`} className={n <= value ? 'is-on' : ''} onClick={() => onChange(n)}>
          <Icon name="star" size={22} />
        </button>
      ))}
    </div>
  );
}

/** Status (the real lifecycle, no fake map), quote approval, payment after completion, review, cancel, help and rebook.
 *  Refreshes every 15 s while active so the professional's updates appear. */
export function ServiceBookingPage() {
  useThemeOverride('services');
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const qc = useQueryClient();
  const key = ['services', 'booking', id];
  const q = useQuery({ queryKey: key, queryFn: () => api.services.booking(id), refetchInterval: (query) => (query.state.data?.isActive ? 15_000 : false) });
  const b = q.data;
  const wallet = useWallet(!!b?.canPay);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [reason, setReason] = useState(REASONS[0]!);
  const [payOpen, setPayOpen] = useState(false);
  const [review, setReview] = useState<ServiceReviewInput>({ overall: 0, quality: 0, behaviour: 0, timeliness: 0, comment: '' });
  const act = useMutation({
    mutationFn: ({ action, body }: { action: 'cancel' | 'quote' | 'pay' | 'review'; body: object; done: string }) => api.services.act(id, action, body),
    onSuccess: (r: ServiceBookingDetail, v) => {
      qc.setQueryData(key, r);
      qc.invalidateQueries({ queryKey: ['services', 'bookings'] });
      qc.invalidateQueries({ queryKey: walletKey });
      setCancelOpen(false); setPayOpen(false);
      toast(v.done);
    },
    onError: (e) => { toast(e instanceof ApiError ? e.message : 'Something went wrong.', 'error'); q.refetch(); },
  });

  if (q.isError) return <div className="sv-page"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  if (!b) return <div className="sv-page"><Skeleton height={160} radius={22} /><Skeleton height={320} radius={22} /></div>;

  const pending = b.quotes.find((x) => x.status === 'pending');
  const reached = new Set(b.timeline.map((t) => t.to));
  const steps = STATUS_STEPS.filter((s) => !(s.status === 'on_the_way' && !reached.has('on_the_way') && ['in_progress', 'completed', 'paid'].includes(b.status)));
  const idx = Math.max(...steps.map((s, i) => (reached.has(s.status) || s.status === b.status ? i : -1)));
  const ended = b.status === 'cancelled' || b.status === 'unassigned';
  const balance = wallet.data ? Number(wallet.data.balance) : null;
  const shortOfWallet = balance != null && b.total != null && balance < Number(b.total);

  return (
    <div className="sv-page" data-theme="services" style={{ ['--sv-accent' as string]: b.category.accent }}>
      <Link to="/services/bookings" className="sv-back"><Icon name="back" size={18} /> Service bookings</Link>
      {(location.state as { justBooked?: boolean } | null)?.justBooked && b.status === 'requested' && (
        <div className="sv-banner" role="status"><Icon name="check" size={18} /> Request sent. {b.requestedProvider ? `Waiting for ${b.requestedProvider.name.split(' ')[0]} to accept.` : 'Nearby professionals are being asked — the first to accept gets the job.'}</div>
      )}

      <header className="sv-bkhead">
        <span className="sv-kicker">{b.number} · {b.category.name}</span>
        <h1>{b.job.name}</h1>
        <p className={`sv-status sv-status--${b.status}`}>{b.statusLabel}</p>
        <p className="small sv-muted">{b.mode === 'now' ? 'As soon as possible' : b.scheduledStart ? when(b.scheduledStart) : ''} · {b.addressLabel}</p>
        {b.etaMinutes != null && ['confirmed', 'on_the_way'].includes(b.status) && <p className="small">Estimated arrival about {b.etaMinutes} min (from their last known distance; live location isn’t shared).</p>}
      </header>

      {b.provider ? (
        <div className="sv-bookpro">
          <ProAvatar p={{ ...b.provider, accent: b.category.accent }} size={56} />
          <div><strong>{b.provider.name}</strong><span className="small sv-muted">{b.provider.profession}{b.provider.verified ? ' · Verified' : ''}</span><Rating r={b.provider.rating} compact /></div>
          <Link to={`/services/pro/${b.provider.id}`} className="sv-link small">Profile</Link>
        </div>
      ) : !ended && <p className="sv-note"><Icon name="clock" size={14} /> {b.requestedProvider ? <>Waiting for <Link to={`/services/pro/${b.requestedProvider.id}`}>{b.requestedProvider.name}</Link> to accept.</> : 'Finding a professional.'} If nobody accepts in time, the request closes and nothing is charged.</p>}

      {pending && (
        <section className="sv-quote" aria-labelledby="sv-q">
          <h2 id="sv-q">Approve the quote?</h2>
          <p className="sv-quote__amt">{formatMoney(pending.amount)}<span className="small sv-muted"> + 18% tax</span></p>
          {pending.note && <p className="small">“{pending.note}”</p>}
          <p className="small sv-muted">{b.agreedAmount ? `Your booking was ${formatMoney(b.agreedAmount)}. Decline to keep that price.` : b.inspectionFee ? `If you decline, only the visit fee of ${formatMoney(b.inspectionFee)} is charged.` : 'If you decline, the job ends without work.'}</p>
          <div className="sv-row">
            <Button variant="secondary" loading={act.isPending} onClick={() => act.mutate({ action: 'quote', body: { approve: false }, done: 'Quote declined' })}>Decline</Button>
            <Button loading={act.isPending} onClick={() => act.mutate({ action: 'quote', body: { approve: true }, done: 'Quote approved — work can start' })}>Approve</Button>
          </div>
        </section>
      )}

      {b.canPay && (
        <section className="sv-pay" aria-labelledby="sv-p">
          <h2 id="sv-p">Work completed</h2>
          <p>Pay <strong>{formatMoney(b.total!)}</strong> to finish.</p>
          {b.awaitingCash ? <p className="small"><Icon name="clock" size={13} /> You chose cash. The booking closes when {b.provider?.name.split(' ')[0] ?? 'the professional'} confirms they received it.</p>
            : <Button block onClick={() => setPayOpen(true)}>Pay now</Button>}
        </section>
      )}

      <section className="sv-sec">
        <h2 className="sv-h2">Status</h2>
        {ended ? (
          <p className="sv-note">{b.status === 'cancelled' ? 'This booking was cancelled.' : 'No professional accepted in time. Nothing was charged.'}</p>
        ) : (
          <ol className="sv-timeline">{steps.map((s, i) => {
            const t = [...b.timeline].reverse().find((x) => x.to === s.status);
            return <li key={s.status} className={i < idx ? 'is-done' : i === idx ? 'is-now' : ''}><span className="sv-timeline__dot" /><span><strong>{s.label}</strong>{t && <span className="small sv-muted">{when(t.at)}{t.note ? ` · ${t.note}` : ''}</span>}</span></li>;
          })}</ol>
        )}
        <details className="sv-log"><summary className="small">Full history</summary>
          <ul>{b.timeline.map((t, i) => <li key={i} className="small"><strong>{t.label}</strong> · {when(t.at)}{t.note && <span className="sv-muted"> · {t.note}</span>}</li>)}</ul>
        </details>
      </section>

      <section className="sv-sec">
        <h2 className="sv-h2">Bill</h2>
        <dl className="sv-summary">
          <dt>Pricing</dt><dd>{b.priceLabel}<span className="small sv-muted">{b.pricingLabel}</span></dd>
          {b.hours != null && <><dt>Hours booked</dt><dd>{b.hours}{b.billedHours && ` · billed ${Number(b.billedHours)}`}</dd></>}
          {b.agreedAmount && <><dt>Agreed</dt><dd>{formatMoney(b.agreedAmount)}</dd></>}
          {Number(b.discount) > 0 && <><dt>{b.offerTitle || 'Offer'}</dt><dd>−{formatMoney(b.discount)}</dd></>}
          {b.total && <><dt>Tax</dt><dd>{formatMoney(b.tax)}</dd><dt><strong>Total</strong></dt><dd><strong>{formatMoney(b.total)}</strong></dd></>}
          {b.payment && <><dt>Payment</dt><dd>{b.payment.method === 'wallet' ? 'Click. Wallet' : 'Cash'} · {b.payment.status === 'captured' ? 'paid' : b.payment.status}</dd></>}
        </dl>
        {!b.total && !ended && <p className="small sv-muted">The final bill appears when the work is completed. Any change from the agreed price needs your approval.</p>}
        {b.quotes.filter((x) => x.status !== 'pending').map((x) => <p key={x.id} className="small sv-muted">Quote {formatMoney(x.amount)} · {x.status}</p>)}
      </section>

      {(b.description || b.photos.length > 0) && (
        <section className="sv-sec">
          <h2 className="sv-h2">Your request</h2>
          {b.description && <p>{b.description}</p>}
          {b.photos.length > 0 && <div className="sv-photos">{b.photos.map((p) => <a key={p.id} className="sv-thumb" href={p.src} target="_blank" rel="noreferrer"><img src={p.thumb} alt="Attached photo" /></a>)}</div>}
        </section>
      )}

      {b.canReview && (
        <section className="sv-review" aria-labelledby="sv-r">
          <h2 id="sv-r">Rate {b.provider?.name.split(' ')[0] ?? 'the professional'}</h2>
          <Stars label="Overall" value={review.overall} onChange={(n) => setReview((r) => ({ ...r, overall: n, quality: r.quality || n, behaviour: r.behaviour || n, timeliness: r.timeliness || n }))} />
          {review.overall > 0 && (
            <>
              {ASPECTS.map(([k, l]) => <div key={k} className="sv-aspectrow"><span className="small">{l}</span><Stars label={l} value={review[k]} onChange={(n) => setReview((r) => ({ ...r, [k]: n }))} /></div>)}
              <textarea className="sv-textarea" rows={3} maxLength={1000} placeholder="Anything others should know? (optional)" value={review.comment}
                onChange={(e) => setReview((r) => ({ ...r, comment: e.target.value }))} aria-label="Comment" />
              <Button block loading={act.isPending} onClick={() => act.mutate({ action: 'review', body: review, done: 'Thanks for your review' })}>Submit review</Button>
            </>
          )}
        </section>
      )}
      {b.review && <section className="sv-sec"><h2 className="sv-h2">Your review</h2><p className="sv-rating"><Icon name="star" size={14} /> {b.review.overall} / 5</p>{b.review.comment && <p>{b.review.comment}</p>}</section>}

      <div className="sv-actions">
        {b.cancellation.allowed && <Button variant="secondary" onClick={() => setCancelOpen(true)}>Cancel booking</Button>}
        {!b.isActive && <Button variant="secondary" onClick={() => navigate(`/services/book?rebook=${b.id}`)}><Icon name="history" size={16} /> Book again</Button>}
        <Link to={`/help/new?serviceBookingId=${b.id}&category=service&subject=${encodeURIComponent(`${b.job.name} · ${b.number}`)}`} className="btn btn--ghost"><Icon name="help" size={16} /> Get help</Link>
      </div>
      {!b.cancellation.allowed && b.isActive && <p className="small sv-muted">{b.cancellation.note}</p>}
      {b.tickets.length > 0 && <p className="small">Support: {b.tickets.map((t) => <Link key={t.id} to={`/help/tickets/${t.id}`}>{t.reference} ({t.status}) </Link>)}</p>}

      <Sheet open={cancelOpen} onClose={() => setCancelOpen(false)} label="Cancel booking">
        <div className="sv-sheet">
          <h2>Cancel this booking?</h2>
          <p className="small">{b.cancellation.note || 'Free while the professional isn’t on the way yet.'}</p>
          <div className="sv-reasons" role="radiogroup" aria-label="Reason">
            {REASONS.map((r) => <label key={r} className="sv-check"><input type="radio" name="reason" checked={reason === r} onChange={() => setReason(r)} /> {r}</label>)}
          </div>
          <Button block variant="danger" loading={act.isPending} onClick={() => act.mutate({ action: 'cancel', body: { reason }, done: 'Booking cancelled' })}>Cancel booking</Button>
        </div>
      </Sheet>

      <Sheet open={payOpen} onClose={() => setPayOpen(false)} label="Pay">
        <div className="sv-sheet">
          <h2>Pay {b.total ? formatMoney(b.total) : ''}</h2>
          <Button block disabled={shortOfWallet} loading={act.isPending} onClick={() => act.mutate({ action: 'pay', body: { method: 'wallet' }, done: 'Paid from Click. Wallet' })}>
            <Icon name="wallet" size={16} /> Pay with Click. Wallet{balance != null ? ` · balance ${formatMoney(String(balance))}` : ''}
          </Button>
          {shortOfWallet && <p className="small">Not enough balance. <Link to="/wallet">Add money</Link> or pay in cash.</p>}
          <Button block variant="secondary" loading={act.isPending} onClick={() => act.mutate({ action: 'pay', body: { method: 'cash' }, done: 'Pay the professional in cash' })}>Pay in cash</Button>
          <p className="small sv-muted">Card and UPI aren’t available yet.</p>
        </div>
      </Sheet>
    </div>
  );
}
