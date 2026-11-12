import { useMemo, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, ErrorState, Icon, Skeleton, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { fmtDay, fmtSlot } from '../features/bookings/parts';
import { useWallet, walletKey } from '../features/wallet/useWallet';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

const newKey = () => (globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`);

/** Booking summary → visitor details → Pay & book. Prices, places left, offer and tax are re-checked on the server; a
 *  changed price must be confirmed; a free darshan registration confirms without payment. */
export function ExperienceBookPage() {
  useThemeOverride('bookings');
  const [sp] = useSearchParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const { user } = useAuth();
  const wallet = useWallet();
  const tickets = useMemo(() => Object.fromEntries((sp.get('tickets') ?? '').split(',').filter(Boolean).map((x) => { const [v, n] = x.split(':'); return [v!, Number(n) || 0]; })), [sp]);
  const [coupon, setCoupon] = useState('');
  const [applied, setApplied] = useState('');
  const input = { offeringId: sp.get('offering') ?? '', visitDate: sp.get('date') ?? '', slotTime: sp.get('slot'), tickets, pickupPoint: sp.get('pickup') ?? undefined, coupon: applied || undefined };
  const review = useQuery({ queryKey: ['bookings', 'review', input], queryFn: () => api.bookings.review(input), enabled: !!input.offeringId, retry: false });
  const [lead, setLead] = useState({ name: user?.fullName ?? '', phone: user?.phone ?? '', email: user?.email ?? '' });
  const [names, setNames] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const idem = useRef(newKey());
  const book = useMutation({
    mutationFn: () => api.bookings.book({ ...input, leadName: lead.name.trim(), leadPhone: lead.phone.trim(), leadEmail: lead.email.trim(),
      visitorNames: names.split(',').map((x) => x.trim()).filter(Boolean), expectedTotal: review.data?.total ?? null, idempotencyKey: idem.current }),
    onSuccess: (b) => {
      qc.invalidateQueries({ queryKey: ['bookings'] }); qc.invalidateQueries({ queryKey: walletKey });
      nav(`/bookings/r/${b.id}`, { replace: true, state: { justBooked: true, paymentError: b.paymentError } });
    },
    onError: (e) => {
      if (e instanceof ApiError && ['price_changed', 'not_available'].includes(e.code)) { qc.invalidateQueries({ queryKey: ['bookings', 'review'] }); idem.current = newKey(); }
      toast(e instanceof ApiError ? (e.code === 'price_changed' ? 'The price changed — check the new total below and confirm again.' : e.message) : 'Couldn’t book.', 'error');
    },
  });
  const r = review.data;
  const balance = wallet.data ? Number(wallet.data.balance) : null;
  const short = r != null && balance != null && Number(r.total) > 0 && balance < Number(r.total);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const err: Record<string, string> = {};
    if (lead.name.trim().length < 2) err.name = 'Enter the lead visitor’s name.';
    if (!/^\+?[0-9 ]{8,16}$/.test(lead.phone.trim())) err.phone = 'Enter a valid phone number.';
    if (lead.email && !/^\S+@\S+\.\S+$/.test(lead.email.trim())) err.email = 'Enter a valid email or leave it empty.';
    setErrors(err);
    if (!Object.keys(err).length) book.mutate();
  };
  const back = sp.get('place') ? `/bookings/places/${sp.get('place')}` : '/bookings';

  return (
    <div className="bk-page bk-bookflow" data-theme="bookings">
      <Link to={back} className="bk-back"><Icon name="back" size={18} /> Change date or tickets</Link>
      <ol className="bk-steps" aria-label="Booking steps">{['Date & tickets', 'Details', 'Payment'].map((s, i) => <li key={s} className={i === 0 ? 'is-done' : i === 1 ? 'is-now' : ''}>{s}</li>)}</ol>
      {review.isError ? <ErrorState error={review.error} onRetry={() => review.refetch()} /> : !r ? <Skeleton height={300} radius={22} /> : (
        <form onSubmit={submit} noValidate className="bk-form">
          <section className="bk-sec bk-summary" style={{ ['--bk-accent' as string]: r.attraction.accent }}>
            <span className="bk-kicker">{r.offering.kindLabel} · {r.attraction.kindLabel}</span>
            <h1 className="bk-title">{r.offering.name}</h1>
            <p className="bk-muted">{r.attraction.name}, {r.attraction.city}</p>
            <dl className="bk-dl">
              <dt>Date</dt><dd>{fmtDay(r.visitDate, { weekday: 'long', day: 'numeric', month: 'long' })}</dd>
              <dt>Time</dt><dd>{fmtSlot(r.slotTime)}</dd>
              {r.pickupPoint && <><dt>Pickup</dt><dd>{r.pickupPoint}</dd></>}
              <dt>{r.attraction.kind === 'temple' ? 'Devotees' : 'Visitors'}</dt><dd>{r.visitors}</dd>
            </dl>
            <ul className="bk-lines">
              {r.lines.map((l) => <li key={l.visitor}><span>{l.label} × {l.qty}</span><span>{Number(l.amount) ? formatMoney(l.amount) : 'Free'}</span></li>)}
              {Number(r.discount) > 0 && <li className="bk-ok"><span>{r.offer}</span><span>−{formatMoney(r.discount)}</span></li>}
              {Number(r.tax) > 0 && <li><span>Taxes (GST)</span><span>{formatMoney(r.tax)}</span></li>}
              <li className="bk-lines__total"><span>Total</span><span>{Number(r.total) ? formatMoney(r.total) : 'Free'}</span></li>
            </ul>
            <p className="small bk-muted">{r.policy}</p>
            {r.points > 0 && <p className="small"><Icon name="star" size={12} /> You’ll earn {r.points} Click. Rewards points after your visit.</p>}
            {r.offering.requirements && <p className="small bk-note"><Icon name="alert" size={12} /> {r.offering.requirements}</p>}
            {r.dressCode && <p className="small bk-muted">Dress: {r.dressCode}</p>}
          </section>
          {!r.bookable && <p className="bk-alert" role="alert"><Icon name="alert" size={14} /> {r.problem} <Link to={back} className="bk-link">Choose again</Link></p>}

          <fieldset className="bk-fs"><legend className="bk-h3">Lead visitor</legend>
            <label className="bk-field"><span className="small">Full name</span><input value={lead.name} autoComplete="name" onChange={(e) => setLead({ ...lead, name: e.target.value })} aria-invalid={!!errors.name} /></label>
            {errors.name && <p className="bk-error small">{errors.name}</p>}
            <label className="bk-field"><span className="small">Phone</span><input type="tel" autoComplete="tel" value={lead.phone} onChange={(e) => setLead({ ...lead, phone: e.target.value })} aria-invalid={!!errors.phone} /></label>
            {errors.phone && <p className="bk-error small">{errors.phone}</p>}
            <label className="bk-field"><span className="small">Email (optional)</span><input type="email" autoComplete="email" value={lead.email} onChange={(e) => setLead({ ...lead, email: e.target.value })} /></label>
            {errors.email && <p className="bk-error small">{errors.email}</p>}
            {r.visitors > 1 && <label className="bk-field"><span className="small">Other visitors’ names (optional, comma separated)</span><input value={names} onChange={(e) => setNames(e.target.value)} /></label>}
          </fieldset>

          {Number(r.subtotal) > 0 && (
            <div className="bk-coupon"><input value={coupon} onChange={(e) => setCoupon(e.target.value.toUpperCase())} placeholder="Offer code" aria-label="Offer code" />
              <Button variant="secondary" size="sm" onClick={() => setApplied(coupon.trim())}>Apply</Button></div>
          )}
          {r.couponError && <p className="small bk-warn">{r.couponError}</p>}

          {Number(r.total) > 0 && (
            <section className="bk-sec"><h2 className="bk-h3">Payment</h2>
              <div className="bk-paywith"><Icon name="wallet" size={18} /><span><strong>Click. Wallet</strong><span className="small bk-muted">{balance != null ? `Balance ${formatMoney(String(balance))}` : 'Charged when you confirm'}</span></span></div>
              <p className="small bk-muted">Cards and UPI aren’t connected yet.</p>
              {short && <p className="small bk-warn">Your balance is lower than the total. If you continue, your places are held for {r.holdMinutes} minutes so you can <Link to="/wallet" className="bk-link">add money</Link> and retry.</p>}
            </section>
          )}
          <div className="bk-cta">
            <div><strong>{Number(r.total) ? formatMoney(r.total) : 'Free'}</strong></div>
            <button type="submit" className="bk-btn" disabled={!r.bookable || book.isPending}>{book.isPending ? 'Booking…' : Number(r.total) ? 'Pay & book' : 'Confirm booking'}</button>
          </div>
        </form>
      )}
    </div>
  );
}
