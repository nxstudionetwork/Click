import { Link, useLocation, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@click/api';
import { Button, EmptyState, ErrorState, Icon, Skeleton, useToast } from '../components/ui';
import { showTime } from '../features/bookings/BookingCard';
import { PAYMENT_LABEL } from '../features/orders/status';
import { walletKey } from '../features/wallet/useWallet';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

const METHOD: Record<string, string> = { pay_at_venue: 'Pay at venue', wallet: 'Click Wallet', cash_on_delivery: 'Cash' };

export function BookingPage() {
  const { id = '' } = useParams();
  const location = useLocation();
  const qc = useQueryClient();
  const toast = useToast();
  const key = ['customer', 'bookings', 'detail', id];
  const booking = useQuery({ queryKey: key, queryFn: () => api.customer.bookings.get(id) });
  const cancel = useMutation({
    mutationFn: () => api.customer.bookings.cancel(id),
    onSuccess: (b) => { qc.setQueryData(key, b); qc.invalidateQueries({ queryKey: ['customer', 'bookings'] }); qc.invalidateQueries({ queryKey: walletKey }); toast('Booking cancelled'); },
    onError: (e) => toast(e instanceof Error ? e.message : 'Could not cancel.', 'error'),
  });

  if (booking.isError) {
    return booking.error instanceof ApiError && booking.error.status === 404
      ? <EmptyState icon="ticket" title="Booking not found" action={<Link className="btn btn--outline" to="/bookings">All bookings</Link>} />
      : <ErrorState error={booking.error} onRetry={() => booking.refetch()} />;
  }
  if (booking.isPending) return <Skeleton height={320} radius={22} />;
  const b = booking.data;
  const payment = b.payments[0];

  return (
    <div className="stack" style={{ maxWidth: 640 }}>
      <Link to="/bookings" className="phead__back"><Icon name="back" size={18} /> Bookings</Link>
      {(location.state as { justBooked?: boolean } | null)?.justBooked && (
        <div className="card card--pad row success-pop" style={{ background: 'var(--c-accent-soft)', borderColor: 'transparent' }} role="status">
          <Icon name="check" /> <strong>You’re booked! Show this ticket at the venue.</strong>
        </div>
      )}
      <article className={`ticket ${b.status === 'cancelled' ? 'ticket--cancelled' : ''}`} aria-label="Ticket">
        <div className="ticket__top">
          <span className="small" style={{ opacity: 0.8 }}>{b.event.kind === 'movie' ? 'Movie ticket' : 'Event ticket'}</span>
          <h1 style={{ color: '#fff' }}>{b.event.title}</h1>
          <span>{showTime(b.show.startsAt)}</span>
          <span className="small" style={{ opacity: 0.85 }}>{b.show.venue.name}{b.show.screen && ` · ${b.show.screen}`} · {b.show.format}</span>
        </div>
        <div className="ticket__body">
          <div><span className="small muted">Seats</span><strong style={{ display: 'block', fontSize: 'var(--fs-xl)' }}>{b.seats.map((s) => s.label).join(', ')}</strong></div>
          <div><span className="small muted">Booking ID</span><strong className="ticket__ref">{b.reference}</strong></div>
          <span className={`badge ${b.status === 'cancelled' ? 'badge--danger' : 'badge--accent'}`}>{b.status === 'cancelled' ? 'Cancelled' : 'Confirmed'}</span>
        </div>
      </article>
      <section className="card card--pad stack" style={{ gap: 'var(--s-2)' }}>
        <h3>Payment</h3>
        <div className="totals">
          <div><span>Tickets</span><span>{formatMoney(b.subtotal, b.currency)}</span></div>
          <div><span>Convenience fee</span><span>{formatMoney(b.convenienceFee, b.currency)}</span></div>
          <div><span>GST on fee</span><span>{formatMoney(b.tax, b.currency)}</span></div>
          <div className="totals__grand"><span>Total</span><span>{formatMoney(b.total, b.currency)}</span></div>
        </div>
        {payment && <p className="small muted">{METHOD[payment.method] ?? payment.method} · {PAYMENT_LABEL[payment.status]}</p>}
      </section>
      <div className="row" style={{ flexWrap: 'wrap' }}>
        {b.canCancel && <Button variant="danger" size="sm" loading={cancel.isPending} onClick={() => window.confirm('Cancel this booking? Seats will be released.') && cancel.mutate()}>Cancel booking</Button>}
        <Link to={`/movies/${b.event.slug}`} className="btn btn--outline btn--sm">View show</Link>
        <Link to={`/help/new?category=other&subject=${encodeURIComponent(`Booking ${b.reference}`)}`} className="btn btn--ghost btn--sm">Get help</Link>
      </div>
      {b.status === 'confirmed' && !b.canCancel && <p className="small muted">This booking can no longer be cancelled (within 2 hours of the show).</p>}
    </div>
  );
}
