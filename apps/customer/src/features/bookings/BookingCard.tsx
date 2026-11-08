import { Link } from 'react-router-dom';
import type { Booking } from '@click/api';
import { SmartImage } from '../../components/ui';
import { formatMoney } from '../../lib/format';

export const showTime = (iso: string) => new Date(iso).toLocaleString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' });

export function BookingCard({ booking }: { booking: Booking }) {
  return (
    <Link to={`/bookings/${booking.id}`} className="order-row">
      <SmartImage src={booking.event.posterUrl} alt={booking.event.title} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="spread"><strong className="truncate">{booking.event.title}</strong><strong>{formatMoney(booking.total, booking.currency)}</strong></div>
        <div className="small">{showTime(booking.show.startsAt)} · {booking.show.venue.name}</div>
        <div className="muted small">{booking.seats.map((s) => s.label).join(', ')} · {booking.reference}</div>
        <span className={`badge ${booking.status === 'cancelled' ? 'badge--danger' : 'badge--accent'}`} style={{ marginTop: 6 }}>{booking.status === 'cancelled' ? 'Cancelled' : 'Confirmed'}</span>
      </div>
    </Link>
  );
}
