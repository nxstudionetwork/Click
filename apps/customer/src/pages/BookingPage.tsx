import { useEffect, useState } from 'react';
import QRCode from 'qrcode';
import { Link, useLocation, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type Booking } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { EmptyState, ErrorState, Icon, Skeleton, SmartImage, useConfirm, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { PAYMENT_LABEL } from '../features/orders/status';
import { Poster, dayOf, runtime, timeOf } from '../features/showtime/parts';
import { walletKey } from '../features/wallet/useWallet';
import { api } from '../lib/api';
import { formatDateTime, formatMoney } from '../lib/format';

/** A Showtime ticket: details, a QR the venue verifies, actions, cancellation (with its real terms) and the evening plan. */
export function BookingPage() {
  useThemeOverride('movies');
  const { id = '' } = useParams();
  const location = useLocation();
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const { user } = useAuth();
  const key = ['customer', 'bookings', 'detail', id];
  const booking = useQuery({ queryKey: key, queryFn: () => api.customer.bookings.get(id) });
  const cancel = useMutation({
    mutationFn: () => api.customer.bookings.cancel(id),
    onSuccess: (b) => { qc.setQueryData(key, b); qc.invalidateQueries({ queryKey: walletKey }); qc.invalidateQueries({ queryKey: ['customer', 'bookings'] }); toast('Booking cancelled'); },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t cancel.', 'error'),
  });

  if (booking.isError) {
    return booking.error instanceof ApiError && booking.error.status === 404
      ? <div className="st-page"><EmptyState icon="ticket" title="Ticket not found" action={<Link className="btn btn--primary" to="/tickets">My Tickets</Link>} /></div>
      : <div className="st-page"><ErrorState error={booking.error} onRetry={() => booking.refetch()} /></div>;
  }
  if (booking.isPending) return <div className="st-page"><Skeleton height={420} radius={24} /></div>;
  const b = booking.data;
  const s = b.show;
  const just = (location.state as { justBooked?: boolean } | null)?.justBooked;
  const pay = b.payments[0];
  const venue = s.venue;

  return (
    <div className="st-page" data-theme="movies" style={{ maxWidth: 720, margin: '0 auto', width: '100%' }}>
      <Link to="/tickets" className="btn btn--ghost btn--sm" style={{ alignSelf: 'flex-start', paddingLeft: 4, color: 'var(--c-ink-2)' }}><Icon name="back" size={18} /> My Tickets</Link>
      {just && <h1 style={{ fontSize: 'clamp(1.5rem, 5vw, 2rem)' }}><Icon name="check" size={26} /> Booking confirmed</h1>}
      {b.state === 'cancelled' && <div className="st-box" role="status"><strong>This booking was cancelled{b.cancelledAt ? ` on ${formatDateTime(b.cancelledAt)}` : ''}.</strong>
        {pay && <span className="small muted">Payment: {PAYMENT_LABEL[pay.status]}</span>}</div>}

      <article className="ticket" aria-label="Ticket">
        <div className="ticket__top">
          <div className="ticket__poster"><Poster t={{ title: b.event.title, posterUrl: b.event.posterUrl, genres: b.event.genres, kind: b.event.kind }} /></div>
          <div className="stack" style={{ gap: 4 }}>
            <strong style={{ fontSize: 'var(--fs-lg)' }}>{b.event.title}</strong>
            <span className="small" style={{ color: 'var(--c-ink-2)' }}>{[b.event.certification, runtime(b.event.durationMinutes), s.language, s.format].filter(Boolean).join(' • ')}</span>
            <span className="small muted">{venue.name}, {venue.locality}</span>
          </div>
        </div>
        <div className="ticket__perf" aria-hidden="true" />
        <dl className="ticket__facts">
          <div><dt>Date</dt><dd>{dayOf(s.startsAt)}</dd></div>
          <div><dt>Time</dt><dd>{timeOf(s.startsAt)}</dd></div>
          <div><dt>Screen</dt><dd>{s.screen || '—'}</dd></div>
          <div><dt>Seats</dt><dd>{b.seats.map((x) => x.label).join(', ')}</dd></div>
          <div><dt>Booking ID</dt><dd>{b.reference}</dd></div>
          <div><dt>Name</dt><dd>{user?.fullName || '—'}</dd></div>
          <div><dt>Payment</dt><dd>{pay ? `${pay.method === 'wallet' ? 'Click. Wallet' : 'At the cinema'} · ${PAYMENT_LABEL[pay.status]}` : '—'}</dd></div>
          <div><dt>Total</dt><dd>{formatMoney(b.total, b.currency)}</dd></div>
        </dl>
        {b.concessions.length > 0 && (
          <div style={{ padding: '0 var(--s-4) var(--s-3)' }}><span className="st-venue__label">Food & drinks (collect at the counter)</span>
            <div className="small">{b.concessions.map((c) => `${c.quantity} × ${c.name}`).join(' · ')}</div></div>
        )}
        {b.ticketCode && <TicketQr code={b.ticketCode} checkedIn={b.checkedInAt} />}
      </article>

      {b.state !== 'cancelled' && <TicketActions b={b} />}

      {b.state === 'upcoming' && <EveningPlan b={b} />}

      {b.state === 'completed' && (
        <div className="st-box"><strong>How was {b.event.title}?</strong><Link to={`/showtime/${b.event.slug}#reviews`} className="btn btn--primary btn--sm">Rate and review</Link></div>
      )}

      <section className="st-box" aria-label="Bill">
        <h3>Bill</h3>
        <div className="st-bill">
          <div><span>Tickets</span><span>{formatMoney(b.subtotal, b.currency)}</span></div>
          {Number(b.concessionsTotal) > 0 && <div><span>Food & drinks</span><span>{formatMoney(b.concessionsTotal, b.currency)}</span></div>}
          <div><span>Convenience fee</span><span>{formatMoney(b.convenienceFee, b.currency)}</span></div>
          <div><span>Taxes</span><span>{formatMoney(b.tax, b.currency)}</span></div>
          {Number(b.discount) > 0 && <div className="st-bill__save"><span>{b.offerTitle}</span><span>−{formatMoney(b.discount, b.currency)}</span></div>}
          <div className="st-bill__total"><span>Total</span><span>{formatMoney(b.total, b.currency)}</span></div>
        </div>
      </section>

      {b.cancellation && b.state === 'upcoming' && (
        <section className="st-box" aria-label="Cancellation">
          <h3>Cancellation</h3>
          <span className="small muted">You can cancel up to {b.cancellation.cutoffHours} hours before the show (until {formatDateTime(b.cancellation.deadline)}). No cancellation charges.
            Refund: {Number(b.cancellation.refundAmount) > 0 ? `${formatMoney(b.cancellation.refundAmount, b.currency)} to your ${b.cancellation.refundMethod}` : b.cancellation.refundMethod}.</span>
          {b.cancellation.allowed ? (
            <button type="button" className="st-btn st-btn--ghost" disabled={cancel.isPending} style={{ justifySelf: 'start' }}
              onClick={async () => { if (await confirm({ title: 'Cancel this booking?', danger: true, confirmLabel: 'Cancel booking', cancelLabel: 'Keep it',
                message: Number(b.cancellation!.refundAmount) > 0 ? `${formatMoney(b.cancellation!.refundAmount, b.currency)} goes back to your Click. Wallet. Seats are released.` : 'Your seats are released. Nothing was charged.' })) cancel.mutate(); }}>
              Cancel booking</button>
          ) : <span className="small">Cancellation has closed for this show.</span>}
        </section>
      )}
      <Link to={`/help/new?category=booking&bookingId=${b.id}`} className="small" style={{ color: 'var(--c-ink-3)' }}>Need help with this booking?</Link>
    </div>
  );
}

function TicketQr({ code, checkedIn }: { code: string; checkedIn: string | null }) {
  const [src, setSrc] = useState('');
  useEffect(() => { QRCode.toDataURL(code, { margin: 1, width: 360, errorCorrectionLevel: 'M' }).then(setSrc).catch(() => setSrc('')); }, [code]);
  return (
    <div className="ticket__qr">
      {src ? <img src={src} alt="Ticket QR code. Show it at the entrance." /> : <Skeleton width={180} height={180} />}
      <small>{checkedIn ? `Checked in at ${timeOf(checkedIn)}` : 'Show this at the entrance. The cinema scans it to check you in.'}</small>
    </div>
  );
}

function ics(b: Booking) {
  const start = new Date(b.show.startsAt);
  const end = new Date(start.getTime() + (b.event.durationMinutes ?? 150) * 60000);
  const f = (d: Date) => d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
  return ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Click//Showtime//EN', 'BEGIN:VEVENT', `UID:${b.reference}@click`, `DTSTAMP:${f(new Date())}`,
    `DTSTART:${f(start)}`, `DTEND:${f(end)}`, `SUMMARY:${b.event.title} (${b.show.format || 'Show'})`,
    `LOCATION:${b.show.venue.name}, ${b.show.venue.address || ''} ${b.show.venue.locality}`.trim(),
    `DESCRIPTION:Booking ${b.reference} · Seats ${b.seats.map((s) => s.label).join(', ')}`, 'END:VEVENT', 'END:VCALENDAR'].join('\r\n');
}

function TicketActions({ b }: { b: Booking }) {
  const v = b.show.venue;
  const share = async () => {
    const text = `${b.event.title} · ${dayOf(b.show.startsAt)} ${timeOf(b.show.startsAt)} · ${v.name} · Seats ${b.seats.map((s) => s.label).join(', ')}`;
    try { if (navigator.share) await navigator.share({ title: b.event.title, text }); else await navigator.clipboard.writeText(text); } catch { /* cancelled */ }
  };
  const calendar = () => {
    const url = URL.createObjectURL(new Blob([ics(b)], { type: 'text/calendar' }));
    const a = document.createElement('a');
    a.href = url; a.download = `${b.reference}.ics`; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  };
  const directions = v.latitude != null && v.longitude != null ? `https://www.openstreetmap.org/directions?to=${v.latitude}%2C${v.longitude}` : null;
  return (
    <div className="st-actions">
      <button type="button" className="st-action" onClick={share}><Icon name="share" size={18} /> Share</button>
      {b.state === 'upcoming' && <button type="button" className="st-action" onClick={calendar}><Icon name="clock" size={18} /> Add to calendar</button>}
      {directions && <a className="st-action" href={directions} target="_blank" rel="noreferrer"><Icon name="pin" size={18} /> Directions</a>}
      <Link to={`/showtime/${b.event.slug}`} className="st-action"><Icon name="film" size={18} /> View show</Link>
    </div>
  );
}

/** Continue your evening: links into Ride and Food. Nothing is booked or paid without the customer. */
function EveningPlan({ b }: { b: Booking }) {
  const v = b.show.venue;
  const near = useQuery({
    queryKey: ['stores', 'near-venue', v.id],
    queryFn: () => api.stores.list({ type: 'restaurant', lat: v.latitude!, lng: v.longitude!, radius: 3, open: true }),
    enabled: v.latitude != null && v.longitude != null, staleTime: 5 * 60_000,
  });
  const restaurants = (near.data?.results ?? []).slice(0, 3);
  return (
    <section className="st-plan" aria-label="Continue your evening">
      <h2 style={{ color: '#fff', fontSize: 'var(--fs-lg)' }}>Continue your evening</h2>
      <p>Get there and grab a bite. You confirm and pay for each yourself.</p>
      <div className="st-plan__steps" style={{ gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' }}>
        <Link to={`/rides?to=${encodeURIComponent(v.name)}`} className="st-plan__step"><span><Icon name="ride" size={18} /></span>Get a ride to {v.name}</Link>
        <Link to="/food" className="st-plan__step"><span><Icon name="food" size={18} /></span>Grab something to eat</Link>
      </div>
      {restaurants.length > 0 && (
        <div className="stack" style={{ gap: 8 }}>
          <span className="st-venue__label" style={{ color: '#fff' }}>Open near the cinema</span>
          {restaurants.map((r) => (
            <Link key={r.id} to={`/stores/${r.slug}`} className="row" style={{ color: '#fff' }}>
              <SmartImage src={r.imageUrl} alt={r.name} className="thumb" />
              <span><strong className="small">{r.name}</strong><br /><span className="small" style={{ opacity: .75 }}>{r.distanceKm != null ? `${r.distanceKm.toFixed(1)} km from the cinema` : r.locality}</span></span>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
