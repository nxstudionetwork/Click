import { useMemo, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type TravelPassengerInput, type TravelReview } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, ErrorState, Icon, Sheet, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { fmtDate, fmtDur, fmtTime, modeOf, searchFrom, searchQs } from '../features/travel/parts';
import { useWallet, walletKey } from '../features/wallet/useWallet';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

const newKey = () => (globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`);
const BERTHS = [['', 'No preference'], ['LB', 'Lower'], ['MB', 'Middle'], ['UB', 'Upper'], ['SL', 'Side lower'], ['SU', 'Side upper']];
const CHAIR = [['', 'No preference'], ['W', 'Window'], ['A', 'Aisle']];
const STATUS_WORD: Record<string, string> = { CNF: 'Confirmed', RAC: 'RAC', WL: 'Waitlist', NA: 'Not available' };

/** Passengers → Review journey (re-checked on the server) → Pay & book from the Click. Wallet. Only what the booking
 *  needs is asked: name, age, gender, berth preference on trains — no ID numbers. A changed fare is shown as
 *  "Fare updated" and must be confirmed; a retry never books twice. */
export function TravelBookPage() {
  useThemeOverride('travel');
  const [sp] = useSearchParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const { user } = useAuth();
  const s = searchFrom(sp);
  const journeyId = sp.get('journey') ?? '', fromStop = sp.get('from') ?? '', toStop = sp.get('to') ?? '', cls = sp.get('class') ?? '';
  const seats = useMemo(() => (sp.get('seats') ?? '').split(',').filter(Boolean), [sp]);
  const count = s.adults + s.children;
  const [pax, setPax] = useState<TravelPassengerInput[]>(() => Array.from({ length: count }, (_, i) => ({
    name: i === 0 ? user?.fullName ?? '' : '', age: i < s.adults ? (i === 0 ? 30 : 0) : 0, gender: 'male', berthPreference: '' })));
  const [contact, setContact] = useState({ phone: user?.phone ?? '', email: user?.email ?? '' });
  const [save, setSave] = useState(false);
  const [coupon, setCoupon] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [review, setReview] = useState<TravelReview | null>(null);
  const [fareChange, setFareChange] = useState<{ previous: string; review: TravelReview } | null>(null);
  const idem = useRef(newKey());
  const wallet = useWallet();
  const travellers = useQuery({ queryKey: ['travel', 'travellers'], queryFn: () => api.travel.travellers() });
  const base = { journeyId, fromStopId: fromStop, toStopId: toStop, classCode: cls, infants: s.infants, seats, coupon: coupon.trim() || undefined };

  const check = useMutation({
    mutationFn: () => api.travel.review({ ...base, passengers: pax.map((p) => ({ ...p, name: p.name.trim() })) }),
    onSuccess: (r) => { setReview(r); idem.current = newKey(); window.scrollTo({ top: 0, behavior: 'smooth' }); },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t check the journey.', 'error'),
  });
  const book = useMutation({
    mutationFn: (expected: string) => api.travel.book({ ...base, passengers: pax.map((p) => ({ ...p, name: p.name.trim() })), contactPhone: contact.phone.trim(),
      contactEmail: contact.email.trim(), expectedTotal: expected, idempotencyKey: idem.current, saveTravellers: save,
      tripRef: sp.get('trip') ?? undefined }),
    onSuccess: (b) => {
      qc.invalidateQueries({ queryKey: ['travel'] }); qc.invalidateQueries({ queryKey: walletKey });
      const ret = s.returnDate && !sp.get('trip') ? searchQs({ ...s, origin: s.destination, destination: s.origin, date: s.returnDate, returnDate: null }, { trip: b.number }) : '';
      nav(`/travel/bookings/${b.id}`, { replace: true, state: { justBooked: true, paymentError: b.paymentError, returnSearch: ret } });
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === 'price_changed') {
        const d = e.details as { review?: TravelReview; previous?: string } | undefined;
        if (d?.review) { setFareChange({ previous: d.previous ?? review?.total ?? '', review: d.review }); idem.current = newKey(); return; }
      }
      if (e instanceof ApiError && (e.code === 'seat_taken' || e.code === 'not_available')) {
        const d = e.details as { review?: TravelReview } | undefined;
        if (d?.review) setReview(d.review);
        idem.current = newKey();
      }
      toast(e instanceof ApiError ? e.message : 'Couldn’t book.', 'error');
    },
  });

  if (!journeyId || !cls) return <div className="tv-page"><ErrorState error={new Error('Choose a journey first.')} /></div>;
  const back = `/travel/journey/${journeyId}/${fromStop}/${toStop}?${searchQs(s)}`;
  const set = (i: number, patch: Partial<TravelPassengerInput>) => setPax((p) => p.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const toReview = (e: FormEvent) => {
    e.preventDefault();
    const err: Record<string, string> = {};
    pax.forEach((p, i) => {
      if (!/^[A-Za-z][A-Za-z .'-]{1,79}$/.test(p.name.trim())) err[`n${i}`] = 'Enter the name as on a photo ID (letters only).';
      if (!(p.age >= 0 && p.age <= 110) || (i < s.adults && p.age < 12)) err[`a${i}`] = i < s.adults ? 'Adults are 12 or older.' : 'Enter the age.';
    });
    if (!/^\+?[0-9 ]{8,16}$/.test(contact.phone.trim())) err.phone = 'Enter a phone number for journey updates.';
    if (contact.email && !/^\S+@\S+\.\S+$/.test(contact.email.trim())) err.email = 'Enter a valid email or leave it empty.';
    setErrors(err);
    if (!Object.keys(err).length) check.mutate();
  };
  const balance = wallet.data ? Number(wallet.data.balance) : null;
  const r = review;
  const short = r != null && balance != null && balance < Number(r.total);

  return (
    <div className="tv-page tv-bookflow" data-theme="travel">
      {r ? <button type="button" className="tv-backlink" onClick={() => setReview(null)}><Icon name="back" size={18} /> Passenger details</button>
        : <Link to={back} className="tv-backlink"><Icon name="back" size={18} /> {s.mode === 'bus' ? 'Seats' : 'Journey'}</Link>}
      <ol className="tv-steps" aria-label="Booking steps">
        {[s.mode === 'bus' ? 'Seats' : 'Class', 'Passengers', 'Review', 'Payment'].map((x, i) => <li key={x} className={i < (r ? 2 : 1) ? 'is-done' : i === (r ? 2 : 1) ? 'is-now' : ''}>{x}</li>)}
      </ol>

      {!r ? (
        <form onSubmit={toReview} noValidate className="tv-form">
          <h1 className="tv-title">Passenger details</h1>
          <p className="small tv-muted">Only what the operator needs. Bring a photo ID for {s.mode === 'flight' ? 'every passenger' : 'at least one passenger'}; we don’t store ID numbers.</p>
          {(travellers.data?.results.length ?? 0) > 0 && (
            <div className="tv-chips" aria-label="Saved travellers">
              {travellers.data!.results.map((t) => (
                <button key={t.id} type="button" className="tv-chip" onClick={() => {
                  const i = pax.findIndex((p) => !p.name.trim() || p.name === user?.fullName);
                  set(i < 0 ? 0 : i, { name: t.name, age: t.age, gender: t.gender, berthPreference: t.berthPreference });
                }}><Icon name="user" size={14} /> {t.name}</button>
              ))}
            </div>
          )}
          {pax.map((p, i) => (
            <fieldset key={i} className="tv-pax">
              <legend>{i < s.adults ? `Adult ${i + 1}` : `Child ${i - s.adults + 1}`}{seats[i] ? ` · seat ${seats[i]}` : ''}</legend>
              <label className="tv-field"><span className="tv-field__label">Full name</span>
                <input className="tv-field__input" value={p.name} autoComplete="name" onChange={(e) => set(i, { name: e.target.value })} aria-invalid={!!errors[`n${i}`]} /></label>
              {errors[`n${i}`] && <p className="tv-error small">{errors[`n${i}`]}</p>}
              <div className="tv-row2">
                <label className="tv-field"><span className="tv-field__label">Age</span>
                  <input className="tv-field__input" inputMode="numeric" value={p.age || ''} onChange={(e) => set(i, { age: Number(e.target.value.replace(/\D/g, '')) || 0 })} aria-invalid={!!errors[`a${i}`]} /></label>
                <label className="tv-field"><span className="tv-field__label">Gender</span>
                  <select className="tv-field__input" value={p.gender} onChange={(e) => set(i, { gender: e.target.value as TravelPassengerInput['gender'] })}>
                    <option value="female">Female</option><option value="male">Male</option><option value="other">Other</option></select></label>
              </div>
              {errors[`a${i}`] && <p className="tv-error small">{errors[`a${i}`]}</p>}
              {s.mode === 'train' && (
                <label className="tv-field"><span className="tv-field__label">Berth preference</span>
                  <select className="tv-field__input" value={p.berthPreference ?? ''} onChange={(e) => set(i, { berthPreference: e.target.value })}>
                    {(['CC', 'EC'].includes(cls) ? CHAIR : BERTHS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
              )}
            </fieldset>
          ))}
          {s.infants > 0 && <p className="tv-note small"><Icon name="user" size={14} /> {s.infants} infant{s.infants > 1 ? 's' : ''} on a lap — the airline’s infant fare applies.</p>}
          <fieldset className="tv-pax"><legend>Contact for journey updates</legend>
            <label className="tv-field"><span className="tv-field__label">Phone</span><input className="tv-field__input" type="tel" autoComplete="tel" value={contact.phone} onChange={(e) => setContact({ ...contact, phone: e.target.value })} aria-invalid={!!errors.phone} /></label>
            {errors.phone && <p className="tv-error small">{errors.phone}</p>}
            <label className="tv-field"><span className="tv-field__label">Email (optional)</span><input className="tv-field__input" type="email" autoComplete="email" value={contact.email} onChange={(e) => setContact({ ...contact, email: e.target.value })} /></label>
            {errors.email && <p className="tv-error small">{errors.email}</p>}
          </fieldset>
          <label className="tv-check"><input type="checkbox" checked={save} onChange={(e) => setSave(e.target.checked)} /> Save these travellers for next time (name, age, gender, berth preference)</label>
          <label className="tv-field"><span className="tv-field__label">Offer code (optional)</span><input className="tv-field__input" value={coupon} onChange={(e) => setCoupon(e.target.value.toUpperCase())} /></label>
          <Button type="submit" block className="tv-go" loading={check.isPending}>Review journey</Button>
        </form>
      ) : (
        <ReviewPanel r={r} balance={balance} short={short} busy={book.isPending} onPay={() => book.mutate(r.total)} />
      )}

      <Sheet open={!!fareChange} onClose={() => setFareChange(null)} label="Fare updated">
        {fareChange && (
          <div className="tv-sheet">
            <h2>Fare updated</h2>
            <p className="small">The operator’s fare changed since you reviewed it. Nothing has been charged.</p>
            <dl className="tv-dl"><dt>Previous</dt><dd><s>{formatMoney(fareChange.previous)}</s></dd><dt>Current</dt><dd><strong>{formatMoney(fareChange.review.total)}</strong></dd></dl>
            <Button block loading={book.isPending} onClick={() => { setReview(fareChange.review); const t = fareChange.review.total; setFareChange(null); book.mutate(t); }}>Continue at {formatMoney(fareChange.review.total)}</Button>
            <Button block variant="secondary" onClick={() => { setFareChange(null); nav(`/travel/search?${searchQs(s)}`); }}>Back to results</Button>
          </div>
        )}
      </Sheet>
    </div>
  );
}

function ReviewPanel({ r, balance, short, busy, onPay }: { r: TravelReview; balance: number | null; short: boolean; busy: boolean; onPay: () => void }) {
  const j = r.journey;
  return (
    <div className="tv-review">
      <h1 className="tv-title">Review journey</h1>
      <section className="tv-sec tv-revj">
        <span className="tv-kicker"><Icon name={modeOf(j.mode).icon} size={14} /> {j.operator} · {j.number}{j.name && j.mode === 'train' ? ` ${j.name}` : ''}</span>
        <div className="tv-legbig">
          <div><strong className="tv-time">{fmtTime(j.departsAt)}</strong><span>{j.from}</span><span className="small tv-muted">{fmtDate(j.departsAt)}</span></div>
          <div className="tv-legbig__mid"><span>{fmtDur(j.durationMinutes)}</span><span className="tv-leg__line" aria-hidden="true"><i /></span><span className="small tv-muted">{j.className}{j.fareType ? ` · ${j.fareType}` : ''}</span></div>
          <div className="tv-legbig__end"><strong className="tv-time">{fmtTime(j.arrivesAt)}</strong><span>{j.to}</span><span className="small tv-muted">{fmtDate(j.arrivesAt)}</span></div>
        </div>
        {j.baggage && <p className="small tv-muted">Baggage: {j.baggage.cabin} cabin{j.baggage.checkIn ? ` · ${j.baggage.checkIn} check-in` : ''}</p>}
      </section>
      <section className="tv-sec"><h2 className="tv-h3">Passengers</h2>
        <ul className="tv-paxlist">{r.passengers.map((p, i) => (
          <li key={i}><span><strong>{p.name}</strong><span className="small tv-muted">{p.age} · {p.gender}</span></span>
            <span className={`tv-pstat tv-pstat--${p.status}`}>{STATUS_WORD[p.status]}{p.seat ? ` · ${p.seat}` : p.queue ? ` ${p.queue}` : ''}{p.berth && p.status === 'CNF' ? ` (${p.berth})` : ''}</span></li>
        ))}</ul>
        {r.statusNote && <p className="small tv-warn">{r.statusNote}</p>}
      </section>
      <section className="tv-sec"><h2 className="tv-h3">Fare</h2>
        <ul className="tv-lines">
          {r.lines.map((l) => <li key={l.label}><span>{l.label}</span><span>{formatMoney(l.amount)}</span></li>)}
          {Number(r.discount) > 0 && <li className="tv-ok"><span>{r.offer}</span><span>−{formatMoney(r.discount)}</span></li>}
          <li><span>Taxes (GST)</span><span>{formatMoney(r.tax)}</span></li>
          <li className="tv-lines__total"><span>Total</span><span>{formatMoney(r.total)}</span></li>
        </ul>
        {r.couponError && <p className="small tv-warn">{r.couponError}</p>}
        <p className="small tv-muted">{r.policy}</p>
        {r.points > 0 && <p className="small"><Icon name="star" size={12} /> You’ll earn {r.points} Click. Rewards points after you travel.</p>}
      </section>
      <section className="tv-sec"><h2 className="tv-h3">Payment</h2>
        <div className="tv-paywith"><Icon name="wallet" size={18} /><span><strong>Click. Wallet</strong><span className="small tv-muted">{balance != null ? `Balance ${formatMoney(String(balance))}` : 'Charged when you confirm'}</span></span></div>
        <p className="small tv-muted">Cards and UPI aren’t connected yet. Wallet contribution: {formatMoney(r.total)}.</p>
        {short && <p className="small tv-warn">Your wallet balance is lower than the total. If you continue, the seats are held for {r.holdMinutes} minutes so you can <Link to="/wallet" className="tv-link">add money</Link> and retry — no ticket is issued until it’s paid.</p>}
      </section>
      {!r.bookable && <p className="tv-alert tv-alert--bad" role="alert"><Icon name="alert" size={14} /> {r.problem}</p>}
      <div className="tv-cta">
        <div><strong>{formatMoney(r.total)}</strong><span className="small tv-muted"> total</span></div>
        <button type="button" className="tv-btn" disabled={!r.bookable || busy} onClick={onPay}>{busy ? 'Booking…' : 'Pay & book'}</button>
      </div>
    </div>
  );
}
