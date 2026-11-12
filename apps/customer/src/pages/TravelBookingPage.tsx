import { useEffect, useState } from 'react';
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type TravelBookingDetail } from '@click/api';
import { Button, ErrorState, Icon, Sheet, Skeleton, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { fmtDate, fmtDur, fmtTime, modeOf, STATUS_TONE } from '../features/travel/parts';
import { walletKey } from '../features/wallet/useWallet';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

const REASONS = ['Plans changed', 'Booked the wrong date', 'Found another option', 'Travelling another way', 'Other'];

function Countdown({ until, onDone }: { until: string; onDone: () => void }) {
  const [left, setLeft] = useState(() => Math.max(0, new Date(until).getTime() - Date.now()));
  useEffect(() => {
    const t = setInterval(() => { const l = Math.max(0, new Date(until).getTime() - Date.now()); setLeft(l); if (!l) { clearInterval(t); onDone(); } }, 1000);
    return () => clearInterval(t);
  }, [until, onDone]);
  return <strong>{Math.floor(left / 60000)}:{String(Math.floor((left % 60000) / 1000)).padStart(2, '0')}</strong>;
}

const ics = (b: TravelBookingDetail) => {
  const stamp = (at: string) => new Date(at).toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
  const body = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Click.//Travel//EN', 'BEGIN:VEVENT', `UID:${b.number}@click`, `DTSTAMP:${stamp(new Date().toISOString())}`,
    `DTSTART:${stamp(b.departsAt)}`, `DTEND:${stamp(b.arrivesAt)}`, `SUMMARY:${b.modeLabel} ${b.from.city} → ${b.to.city} (${b.service})`,
    `LOCATION:${b.fromFull.label}${b.fromFull.address ? `, ${b.fromFull.address}` : ''}`, `DESCRIPTION:PNR ${b.pnr} · ${b.operator}`, 'END:VEVENT', 'END:VCALENDAR'].join('\r\n');
  const url = URL.createObjectURL(new Blob([body], { type: 'text/calendar' }));
  const a = Object.assign(document.createElement('a'), { href: url, download: `${b.number}.ics` });
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};

/** Booking details and confirmation: status from the server, payment retry while seats are held, the digital ticket
 *  (only once paid and issued), calendar, share, policy-based cancellation with the exact refund, refund status,
 *  support with the booking attached, a verified trip rating, and the return leg of a round trip. */
export function TravelBookingPage() {
  useThemeOverride('travel');
  const { id = '' } = useParams();
  const [sp] = useSearchParams();
  const location = useLocation();
  const toast = useToast();
  const qc = useQueryClient();
  const key = ['travel', 'booking', id];
  const q = useQuery({ queryKey: key, queryFn: () => api.travel.booking(id) });
  const [ticketOpen, setTicketOpen] = useState(false);
  const ticket = useQuery({ queryKey: ['travel', 'ticket', id], queryFn: () => api.travel.ticket(id), enabled: ticketOpen });
  const [cancelOpen, setCancelOpen] = useState(sp.get('cancel') === '1');
  const [reason, setReason] = useState(REASONS[0]!);
  const [stars, setStars] = useState(0);
  const [comment, setComment] = useState('');
  const act = useMutation({
    mutationFn: ({ action, body }: { action: 'pay' | 'cancel' | 'rate'; body: object; done: string }) => api.travel.act(id, action, body),
    onSuccess: (b, v) => { qc.setQueryData(key, b); qc.invalidateQueries({ queryKey: ['travel'] }); qc.invalidateQueries({ queryKey: walletKey }); setCancelOpen(false); toast(v.done); },
    onError: (e) => { toast(e instanceof ApiError ? e.message : 'Something went wrong.', 'error'); q.refetch(); },
  });

  if (q.isError) return <div className="tv-page"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  if (!q.data) return <div className="tv-page"><Skeleton height={240} radius={22} /><Skeleton height={300} radius={22} /></div>;
  const b = q.data;
  const st = location.state as { justBooked?: boolean; paymentError?: string; returnSearch?: string } | null;
  const m = modeOf(b.mode);

  return (
    <div className="tv-page" data-theme="travel">
      <Link to="/travel/bookings" className="tv-backlink"><Icon name="back" size={18} /> My journeys</Link>
      {st?.justBooked && b.status === 'confirmed' && (
        <section className="tv-confirm" role="status">
          <span className="tv-confirm__mark" aria-hidden="true"><Icon name="check" size={26} /></span>
          <h1>You’re booked</h1>
          <p className="tv-muted">PNR <strong>{b.pnr}</strong> · Booking ID {b.number}. Your ticket is ready and a confirmation is in your notifications.</p>
        </section>
      )}
      {st?.returnSearch && b.status === 'confirmed' && (
        <section className="tv-note"><Icon name="swap" size={16} /><span>Now choose your return journey.</span>
          <Link className="tv-btn tv-btn--sm" to={`/travel/search?${st.returnSearch}`}>Find return</Link></section>
      )}
      {b.canPay && b.holdExpiresAt && (
        <section className="tv-hold" role="alert">
          <h2>Payment wasn’t completed</h2>
          <p className="small">{st?.paymentError || 'Your payment didn’t go through.'} Your seats are held for <Countdown until={b.holdExpiresAt} onDone={() => q.refetch()} />. No ticket is issued until it’s paid.</p>
          <div className="tv-row3">
            <Button loading={act.isPending} onClick={() => act.mutate({ action: 'pay', body: {}, done: 'Paid — your ticket is ready' })}>Try again · {formatMoney(b.total)}</Button>
            <Link to="/wallet" className="btn btn--secondary">Add money</Link>
            <Link to="/account/payments" className="btn btn--ghost">Other payment methods</Link>
          </div>
        </section>
      )}
      {b.status === 'failed' && <p className="tv-alert tv-alert--bad"><Icon name="alert" size={14} /> Payment wasn’t completed in time, so the seats were released. Nothing was charged.</p>}

      <header className="tv-dhead">
        <span className="tv-kicker"><Icon name={m.icon} size={14} /> {b.modeLabel} · {b.number}</span>
        <h1 className="tv-title">{b.from.city} → {b.to.city}</h1>
        <span className={`tv-status tv-status--${STATUS_TONE[b.status] ?? 'warn'}`}>{b.statusLabel}</span>
        {b.journeyStatus !== 'scheduled' && <p className={`tv-alert${b.journeyStatus === 'cancelled' ? ' tv-alert--bad' : ''}`}><Icon name="alert" size={14} /> {b.journeyStatusLabel}{b.delayMinutes ? ` · about ${b.delayMinutes} min late` : ''}{b.notice ? ` · ${b.notice}` : ''}</p>}
      </header>

      <section className="tv-legbig">
        <div><strong className="tv-time">{fmtTime(b.departsAt)}</strong><span>{b.from.name}{b.from.code ? ` (${b.from.code})` : ''}</span><span className="small tv-muted">{fmtDate(b.departsAt)}</span></div>
        <div className="tv-legbig__mid"><span>{fmtDur(b.durationMinutes)}</span><span className="tv-leg__line" aria-hidden="true"><i /></span><span className="small tv-muted">{b.className}</span></div>
        <div className="tv-legbig__end"><strong className="tv-time">{fmtTime(b.arrivesAt)}</strong><span>{b.to.name}{b.to.code ? ` (${b.to.code})` : ''}</span><span className="small tv-muted">{fmtDate(b.arrivesAt)}</span></div>
      </section>

      <section className="tv-sec">
        <h2 className="tv-h2">Booking details</h2>
        <dl className="tv-dl">
          <dt>Operator</dt><dd>{b.operator} · {b.service}{b.vehicle ? ` · ${b.vehicle}` : ''}</dd>
          {b.pnr && <><dt>PNR / reference</dt><dd><strong>{b.pnr}</strong></dd></>}
          <dt>{b.mode === 'bus' ? 'Boarding' : 'From'}</dt><dd>{b.fromFull.label}{b.fromFull.address ? ` · ${b.fromFull.address}` : ''}{b.fromFull.note ? ` · ${b.fromFull.note}` : ''}</dd>
          <dt>{b.mode === 'bus' ? 'Dropping' : 'To'}</dt><dd>{b.toFull.label}{b.toFull.address ? ` · ${b.toFull.address}` : ''}</dd>
          {b.baggage && <><dt>Baggage</dt><dd>{b.baggage.cabin} cabin{b.baggage.checkIn ? ` · ${b.baggage.checkIn} check-in` : ''}</dd></>}
          <dt>Contact</dt><dd>{b.contact.phone}{b.contact.email ? ` · ${b.contact.email}` : ''}</dd>
          <dt>Cancellation</dt><dd>{b.policy}</dd>
          <dt>Payment</dt><dd>{b.paymentStatusLabel}{b.payment ? ` · ${b.payment.method === 'wallet' ? 'Click. Wallet' : b.payment.method} · ref ${b.payment.reference}` : ''}</dd>
          {b.refund && <><dt>Refund</dt><dd className="tv-ok">{formatMoney(b.refund.amount)} · {b.refund.label}</dd></>}
        </dl>
        <ul className="tv-paxlist">{b.passengers.map((p) => (
          <li key={p.position}><span><strong>{p.name}</strong><span className="small tv-muted">{p.age} · {p.genderLabel}</span></span>
            <span className={`tv-pstat tv-pstat--${p.status}`}>{p.statusLabel}{p.seat ? ` · ${p.seat}` : p.queue && p.status !== 'CNF' && p.status !== 'CAN' ? ` ${p.queue}` : ''}{b.mode === 'flight' && p.status === 'CNF' ? ' · seat at check-in' : ''}</span></li>
        ))}{b.infants > 0 && <li><span>{b.infants} infant{b.infants > 1 ? 's' : ''} on a lap</span></li>}</ul>
        <ul className="tv-lines">
          <li><span>Fare</span><span>{formatMoney(b.baseFare)}</span></li>
          {Number(b.fees) > 0 && <li><span>Reservation &amp; superfast charges</span><span>{formatMoney(b.fees)}</span></li>}
          {Number(b.discount) > 0 && <li className="tv-ok"><span>{b.offerTitle}</span><span>−{formatMoney(b.discount)}</span></li>}
          <li><span>Taxes (GST)</span><span>{formatMoney(b.tax)}</span></li>
          <li className="tv-lines__total"><span>{b.paymentStatus === 'paid' ? 'Total paid' : 'Total'}</span><span>{formatMoney(b.total)}</span></li>
          {Number(b.refunded) > 0 && <li className="tv-ok"><span>Refunded to Click. Wallet</span><span>{formatMoney(b.refunded)}</span></li>}
        </ul>
        {b.points > 0 && <p className="small"><Icon name="star" size={12} /> {b.points} Click. Rewards points after you travel.</p>}
      </section>

      <div className="tv-actions">
        <Button variant="secondary" disabled={!b.hasTicket} onClick={() => setTicketOpen(true)}><Icon name="ticket" size={16} /> View ticket</Button>
        <Button variant="secondary" disabled={!b.hasTicket} onClick={() => { setTicketOpen(true); setTimeout(() => window.print(), 400); }}><Icon name="download" size={16} /> Download ticket</Button>
        <Button variant="secondary" disabled={!b.hasTicket} onClick={async () => {
          const text = `${b.modeLabel} ${b.from.city} → ${b.to.city}, ${fmtDate(b.departsAt)} ${fmtTime(b.departsAt)} · ${b.operator} · PNR ${b.pnr}`;
          try { if (navigator.share) await navigator.share({ title: 'My journey', text }); else { await navigator.clipboard.writeText(text); toast('Copied'); } } catch { /* dismissed */ }
        }}><Icon name="share" size={16} /> Share</Button>
        <Button variant="secondary" disabled={!b.isActive} onClick={() => ics(b)}><Icon name="clock" size={16} /> Add to calendar</Button>
        <Link className="btn btn--ghost" to={`/help/new?travelBookingId=${b.id}&category=other&subject=${encodeURIComponent(`${b.modeLabel} ${b.from.city} → ${b.to.city} · ${b.pnr || b.number}`)}`}>
          <Icon name="help" size={16} /> Need help with this journey?</Link>
      </div>
      {b.cancellation.allowed && <Button variant="danger" onClick={() => setCancelOpen(true)}>Cancel journey</Button>}
      {b.isActive && <p className="small tv-muted">{b.modification}</p>}
      {b.cancelReason && <p className="small tv-muted">Cancelled: {b.cancelReason}</p>}

      {b.canRate && (
        <section className="tv-sec" aria-labelledby="tv-rate">
          <h2 className="tv-h2" id="tv-rate">How was the journey with {b.operator}?</h2>
          <div className="tv-stars" role="radiogroup" aria-label="Rating">{[1, 2, 3, 4, 5].map((n) => (
            <button key={n} type="button" role="radio" aria-checked={stars === n} aria-label={`${n} star${n > 1 ? 's' : ''}`} className={n <= stars ? 'is-on' : ''} onClick={() => setStars(n)}><Icon name="star" size={22} /></button>
          ))}</div>
          {stars > 0 && <>
            <textarea className="tv-textarea" rows={3} maxLength={1000} placeholder="Punctuality, comfort, staff (optional)" value={comment} onChange={(e) => setComment(e.target.value)} aria-label="Comment" />
            <Button block loading={act.isPending} onClick={() => act.mutate({ action: 'rate', body: { rating: stars, comment }, done: 'Thanks — your rating helps other travellers' })}>Submit rating</Button>
          </>}
        </section>
      )}
      {b.rating && <p className="tv-note small"><Icon name="star" size={14} /> You rated this journey {b.rating.rating}/5.</p>}

      <section className="tv-sec"><h2 className="tv-h2">Timeline</h2>
        <ol className="tv-timeline">{b.timeline.map((t, i) => <li key={i}><strong>{t.note || t.label}</strong><span className="small tv-muted">{new Date(t.at).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })}</span></li>)}</ol>
      </section>

      <Sheet open={ticketOpen} onClose={() => setTicketOpen(false)} label="Ticket">
        <div className="tv-sheet tv-ticket" id="tv-ticket">
          {ticket.isError ? <ErrorState error={ticket.error} /> : !ticket.data ? <Skeleton height={300} /> : (() => {
            const t = ticket.data;
            return (
              <>
                <header><span className="tv-kicker">{t.modeLabel} ticket</span><h2>{t.from.city} → {t.to.city}</h2><p className="small">{t.issuer}</p></header>
                <dl className="tv-dl">
                  <dt>PNR</dt><dd><strong className="tv-pnr">{t.pnr}</strong></dd><dt>Booking</dt><dd>{t.number}</dd>
                  <dt>{t.mode === 'flight' ? 'Flight' : t.mode === 'train' ? 'Train' : 'Bus'}</dt><dd>{t.operator} · {t.service} · {t.className}</dd>
                  <dt>Departs</dt><dd>{fmtDate(t.departsAt, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })}, {fmtTime(t.departsAt)} · {t.fromFull.label}</dd>
                  <dt>Arrives</dt><dd>{fmtDate(t.arrivesAt)}, {fmtTime(t.arrivesAt)} · {t.toFull.label}</dd>
                  {t.baggage && <><dt>Baggage</dt><dd>{t.baggage.cabin} cabin{t.baggage.checkIn ? ` · ${t.baggage.checkIn} check-in` : ''}</dd></>}
                </dl>
                <table className="tv-table small"><thead><tr><th scope="col">Passenger</th><th scope="col">Age</th><th scope="col">{t.mode === 'train' ? 'Coach-berth / status' : 'Seat'}</th></tr></thead>
                  <tbody>{t.passengers.map((p) => <tr key={p.position}><td>{p.name}</td><td>{p.age}</td><td>{p.seat || (t.mode === 'flight' ? 'At check-in' : '')} {p.status !== 'CNF' ? p.statusLabel + (p.queue ? ` ${p.queue}` : '') : ''}</td></tr>)}</tbody></table>
                <ul className="small">{t.instructions.map((x) => <li key={x}>{x}</li>)}</ul>
                <p className="small tv-muted">{t.codeNote}</p>
                <Button block variant="secondary" onClick={() => window.print()}><Icon name="download" size={16} /> Print / save as PDF</Button>
              </>
            );
          })()}
        </div>
      </Sheet>

      <Sheet open={cancelOpen} onClose={() => setCancelOpen(false)} label="Cancel journey">
        <div className="tv-sheet">
          <h2>Cancel journey</h2>
          <p className="small">{b.policy}</p>
          <dl className="tv-dl">
            <dt>Cancellation fee</dt><dd>{b.cancellation.fee != null ? `${formatMoney(b.cancellation.fee)}${b.cancellation.feePercent != null ? ` (${b.cancellation.feePercent}%)` : ''}` : '—'}</dd>
            <dt>Refund</dt><dd>{b.cancellation.refund != null && Number(b.cancellation.refund) > 0 ? `${formatMoney(b.cancellation.refund)} to your ${b.cancellation.refundTo ?? 'Click. Wallet'}, immediately` : 'No refund'}</dd>
          </dl>
          <p className="small tv-muted">{b.cancellation.note}</p>
          <div role="radiogroup" aria-label="Reason">{REASONS.map((r) => <label key={r} className="tv-check"><input type="radio" name="reason" checked={reason === r} onChange={() => setReason(r)} /> {r}</label>)}</div>
          <Button block variant="danger" loading={act.isPending} disabled={!b.cancellation.allowed} onClick={() => act.mutate({ action: 'cancel', body: { reason }, done: 'Journey cancelled' })}>Confirm cancellation</Button>
        </div>
      </Sheet>
    </div>
  );
}
