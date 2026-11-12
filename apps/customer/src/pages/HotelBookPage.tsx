import { useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, ErrorState, Icon, Skeleton, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { fmtDay, partyLabel, stayFrom, stayQs } from '../features/hotels/parts';
import { useWallet, walletKey } from '../features/wallet/useWallet';
import { api } from '../lib/api';
import { ClaimedCodes } from '../features/offers/ClaimedCodes';
import { formatMoney } from '../lib/format';

const newKey = () => (globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`);

/**
 * SELECT ROOM → GUEST DETAILS → REVIEW → PAYMENT → CONFIRMATION. Every number on Review comes from the server for this
 * room, rate, stay and party; the booking is sent with the total shown, so a price change is caught, never charged.
 */
export function HotelBookPage() {
  useThemeOverride('hotels');
  const [sp] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const { user } = useAuth();
  const stay = stayFrom(sp);
  const rateId = sp.get('rate') ?? '';
  const propertyId = sp.get('property') ?? '';
  const [step, setStep] = useState<'guest' | 'review'>('guest');
  const [g, setG] = useState({ name: user?.fullName ?? '', email: user?.email ?? '', phone: user?.phone ?? '', others: '', requests: '' });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [coupon, setCoupon] = useState('');
  const [applied, setApplied] = useState('');
  const [mode, setMode] = useState<'pay_now' | 'at_property'>('pay_now');
  const idem = useRef(newKey());
  const wallet = useWallet();
  const review = useQuery({ queryKey: ['hotels', 'review', rateId, stay, applied], queryFn: () => api.hotels.review({ rateId, coupon: applied, ...stay }), enabled: !!rateId, retry: false });
  const r = review.data;
  const payMode = r?.payment === 'at_property' ? 'at_property' : r?.payment === 'pay_now' ? 'pay_now' : mode;
  const book = useMutation({
    mutationFn: () => api.hotels.book({ rateId, coupon: applied, ...stay, guestName: g.name.trim(), guestEmail: g.email.trim(), guestPhone: g.phone.trim(),
      otherGuests: g.others.split(',').map((x) => x.trim()).filter(Boolean), specialRequests: g.requests.trim(), paymentMode: payMode,
      expectedTotal: r?.total ?? null, idempotencyKey: idem.current }),
    onSuccess: (b) => {
      qc.invalidateQueries({ queryKey: ['hotels'] }); qc.invalidateQueries({ queryKey: walletKey });
      navigate(`/hotels/bookings/${b.id}`, { replace: true, state: { justBooked: true, paymentError: b.paymentError } });
    },
    onError: (e) => {
      if (e instanceof ApiError && ['price_changed', 'room_unavailable', 'not_bookable'].includes(e.code)) { qc.invalidateQueries({ queryKey: ['hotels', 'review'] }); idem.current = newKey(); }
      toast(e instanceof ApiError ? e.message : 'Couldn’t book.', 'error');
    },
  });
  const balance = wallet.data ? Number(wallet.data.balance) : null;
  const short = payMode === 'pay_now' && balance != null && r != null && balance < Number(r.total);

  const toReview = (e: FormEvent) => {
    e.preventDefault();
    const err: Record<string, string> = {};
    if (g.name.trim().length < 2) err.name = 'Enter the guest’s full name.';
    if (!/^\+?[0-9 ]{8,16}$/.test(g.phone.trim())) err.phone = 'Enter a valid phone number.';
    if (g.email && !/^\S+@\S+\.\S+$/.test(g.email.trim())) err.email = 'Enter a valid email or leave it empty.';
    setErrors(err);
    if (!Object.keys(err).length) setStep('review');
  };

  if (!rateId) return <div className="ht-page"><ErrorState error={new Error('Choose a room first.')} /></div>;
  const back = propertyId ? `/hotels/${propertyId}?${stayQs(stay)}#rooms` : '/hotels';

  return (
    <div className="ht-page ht-bookflow" data-theme="hotels">
      <Link to={back} className="ht-back"><Icon name="back" size={18} /> Rooms</Link>
      <ol className="ht-steps" aria-label="Booking steps">
        {['Room', 'Guest details', 'Review', 'Payment'].map((s, i) => <li key={s} className={i < (step === 'guest' ? 1 : 2) ? 'is-done' : i === (step === 'guest' ? 1 : 2) ? 'is-now' : ''}>{s}</li>)}
      </ol>

      {review.isError ? <ErrorState error={review.error} onRetry={() => review.refetch()} /> : !r ? <Skeleton height={300} radius={22} /> : (
        <>
          <section className="ht-booksrc">
            <span className="ht-kicker">{r.property.typeLabel}</span>
            <strong>{r.property.name}</strong>
            <span className="small">{r.room.name} · {r.rateName}{r.mealLabel !== r.rateName ? ` · ${r.mealLabel}` : ''}</span>
            <span className="small ht-muted">{fmtDay(r.stay.checkIn)} – {fmtDay(r.stay.checkOut)} · {r.stay.nights} night{r.stay.nights > 1 ? 's' : ''} · {partyLabel(stay)}</span>
          </section>
          {!r.bookable && <p className="ht-note ht-note--bad" role="alert"><Icon name="alert" size={14} /> {r.problem} <Link to={back} className="ht-link">Choose another room</Link></p>}

          {step === 'guest' ? (
            <form className="ht-form" onSubmit={toReview} noValidate>
              <h2 className="ht-h2">Primary guest</h2>
              <label className="ht-field"><span className="ht-field__label">Full name (as on ID)</span>
                <input value={g.name} autoComplete="name" aria-invalid={!!errors.name} onChange={(e) => setG({ ...g, name: e.target.value })} />{errors.name && <span className="ht-error small">{errors.name}</span>}</label>
              <label className="ht-field"><span className="ht-field__label">Mobile number</span>
                <input value={g.phone} inputMode="tel" autoComplete="tel" aria-invalid={!!errors.phone} onChange={(e) => setG({ ...g, phone: e.target.value })} />{errors.phone && <span className="ht-error small">{errors.phone}</span>}</label>
              <label className="ht-field"><span className="ht-field__label">Email (for the confirmation, optional)</span>
                <input value={g.email} type="email" autoComplete="email" aria-invalid={!!errors.email} onChange={(e) => setG({ ...g, email: e.target.value })} />{errors.email && <span className="ht-error small">{errors.email}</span>}</label>
              {stay.adults + stay.children > 1 && (
                <label className="ht-field"><span className="ht-field__label">Other guests’ names (optional, comma separated)</span>
                  <input value={g.others} onChange={(e) => setG({ ...g, others: e.target.value })} /></label>
              )}
              <label className="ht-field"><span className="ht-field__label">Special requests (optional — not guaranteed)</span>
                <textarea className="ht-textarea" rows={2} maxLength={500} value={g.requests} onChange={(e) => setG({ ...g, requests: e.target.value })} placeholder="e.g. late check-in around 10 PM, high floor" /></label>
              <p className="small ht-muted"><Icon name="shield" size={12} /> Bring a government photo ID at check-in. Click. doesn’t ask for ID numbers.</p>
              <Button type="submit" block disabled={!r.bookable}>Continue to review</Button>
            </form>
          ) : (
            <>
              <section className="ht-review">
                <h2 className="ht-h2">Review your booking</h2>
                <dl className="ht-dl">
                  <dt>Property</dt><dd>{r.property.name}<span className="small ht-muted">{r.property.address}</span></dd>
                  <dt>Room</dt><dd>{r.room.name} · {r.room.beds}</dd>
                  <dt>Check-in</dt><dd>{fmtDay(r.stay.checkIn, { weekday: 'long', day: 'numeric', month: 'long' })}, from {r.property.checkInTime}</dd>
                  <dt>Check-out</dt><dd>{fmtDay(r.stay.checkOut, { weekday: 'long', day: 'numeric', month: 'long' })}, by {r.property.checkOutTime}</dd>
                  <dt>Nights</dt><dd>{r.stay.nights}</dd><dt>Guests</dt><dd>{partyLabel(stay)}</dd>
                  <dt>Primary guest</dt><dd>{g.name} · {g.phone}</dd>
                  <dt>Meal plan</dt><dd>{r.mealLabel}</dd>
                  <dt>Cancellation</dt><dd className={r.refundable ? 'ht-ok' : ''}>{r.policy}</dd>
                  <dt>Payment</dt><dd>{r.paymentLabel}</dd>
                </dl>
                <ul className="ht-lines">
                  {r.nightly.map((n) => <li key={n.date}><span>{fmtDay(n.date)}{stay.rooms > 1 ? ` × ${stay.rooms} rooms` : ''}</span><span>{formatMoney(String(Number(n.price) * stay.rooms))}</span></li>)}
                  <li><span>Room price</span><span>{formatMoney(r.roomTotal)}</span></li>
                  {Number(r.discount) > 0 && <li className="ht-ok"><span>{r.offer}</span><span>−{formatMoney(r.discount)}</span></li>}
                  <li><span>Taxes (GST)</span><span>{formatMoney(r.tax)}</span></li>
                  <li><span>Fees</span><span>{formatMoney('0')}</span></li>
                  <li className="ht-lines__total"><span>Total</span><span>{formatMoney(r.total)}</span></li>
                </ul>
                <p className="small ht-muted">{r.taxNote}</p>
                <form className="ht-coupon" onSubmit={(e) => { e.preventDefault(); setApplied(coupon.trim()); }}>
                  <input className="ht-input" value={coupon} onChange={(e) => setCoupon(e.target.value.toUpperCase())} placeholder="Coupon code" aria-label="Coupon code" maxLength={20} />
                  <Button type="submit" variant="secondary" disabled={!coupon.trim()}>Apply</Button>
                </form>
                <ClaimedCodes service="hotels" current={applied} onPick={(c) => { setCoupon(c); setApplied(c); }} />
                {applied && <p className={`small ${r.offer && Number(r.discount) > 0 ? 'ht-ok' : 'ht-warn'}`}>{r.offer && Number(r.discount) > 0 ? `${r.offer} applied.` : `“${applied}” doesn’t apply to this stay.`}</p>}
                {r.property.policies.length > 0 && <ul className="ht-rules">{r.property.policies.map((p) => <li key={p} className="small">{p}</li>)}</ul>}
              </section>

              <section className="ht-review">
                <h2 className="ht-h2">Payment</h2>
                <div className="ht-paygrid" role="radiogroup" aria-label="Payment method">
                  <button type="button" role="radio" aria-checked={payMode === 'pay_now'} disabled={r.payment === 'at_property'} className={`ht-payopt${payMode === 'pay_now' ? ' is-on' : ''}`} onClick={() => setMode('pay_now')}>
                    <Icon name="wallet" size={18} /><span><strong>Pay now · Click. Wallet</strong><span className="small ht-muted">{balance != null ? `Balance ${formatMoney(String(balance))}` : 'Charged when you confirm'}</span></span>
                  </button>
                  <button type="button" role="radio" aria-checked={payMode === 'at_property'} disabled={r.payment === 'pay_now'} className={`ht-payopt${payMode === 'at_property' ? ' is-on' : ''}`} onClick={() => setMode('at_property')}>
                    <Icon name="hotel" size={18} /><span><strong>Pay at the property</strong><span className="small ht-muted">{r.payment === 'pay_now' ? 'Not offered on this rate' : 'Nothing charged online'}</span></span>
                  </button>
                </div>
                {short && <p className="small ht-warn">Your wallet balance is lower than the total. If you continue, the room is held for {r.holdMinutes} minutes so you can <Link to="/wallet" className="ht-link">add money</Link> and retry.</p>}
                <p className="small ht-muted">Card and UPI aren’t connected yet.</p>
              </section>
              <Button block loading={book.isPending} disabled={!r.bookable || review.isFetching} onClick={() => book.mutate()}>
                {payMode === 'pay_now' ? `Confirm & pay ${formatMoney(r.total)}` : `Confirm booking · pay ${formatMoney(r.total)} at the property`}
              </Button>
              <button type="button" className="ht-link small" style={{ alignSelf: 'center' }} onClick={() => setStep('guest')}>Edit guest details</button>
            </>
          )}
        </>
      )}
    </div>
  );
}
