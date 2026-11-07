import { useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, EmptyState, ErrorState, Icon, Skeleton } from '../components/ui';
import { showTime } from '../features/bookings/BookingCard';
import { WalletOption } from '../features/wallet/WalletOption';
import { walletKey } from '../features/wallet/useWallet';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

const FEE_PER_SEAT = 20;   // mirrors backend CONVENIENCE_FEE_PER_SEAT (estimate only; server computes the total)
const FEE_TAX = 0.18;

export function ShowPage() {
  const { id = '' } = useParams();
  const { status } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const qc = useQueryClient();
  const show = useQuery({ queryKey: ['shows', id], queryFn: () => api.events.seatMap(id) });
  const [seats, setSeats] = useState<string[]>([]);
  const [method, setMethod] = useState<'pay_at_venue' | 'wallet'>('pay_at_venue');
  const key = useRef(crypto.randomUUID());

  const book = useMutation({
    mutationFn: api.customer.bookings.create,
    onSuccess: (b) => {
      qc.invalidateQueries({ queryKey: ['customer', 'bookings'] });
      qc.invalidateQueries({ queryKey: walletKey });
      qc.invalidateQueries({ queryKey: ['customer', 'notifications'] });
      navigate(`/bookings/${b.id}`, { replace: true, state: { justBooked: true } });
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status !== 0) key.current = crypto.randomUUID();
      if (e instanceof ApiError && e.code === 'seats_unavailable') {
        const taken = (e.details?.seats as string[] | undefined) ?? [];
        setSeats((s) => s.filter((x) => !taken.includes(x)));
        show.refetch();
      }
    },
  });

  if (show.isError) {
    return show.error instanceof ApiError && show.error.status === 404
      ? <EmptyState icon="ticket" title="This show isn’t available" message="It may have started or been cancelled." action={<Link className="btn btn--outline" to="/movies">Browse shows</Link>} />
      : <ErrorState error={show.error} onRetry={() => show.refetch()} />;
  }
  if (show.isPending) return <div className="stack"><Skeleton height={60} /><Skeleton height={360} radius={16} /></div>;
  const s = show.data;
  const max = s.layout.maxPerBooking;
  const premiumRows = new Set(s.layout.rows.filter((r) => r.tier === 'premium').map((r) => r.row));
  const subtotal = seats.reduce((sum, l) => sum + Number(premiumRows.has(l[0]!) ? s.premiumPrice : s.price), 0);
  const fees = seats.length * FEE_PER_SEAT;
  const total = (subtotal + fees + fees * FEE_TAX).toFixed(2);

  const toggle = (label: string) => setSeats((cur) => cur.includes(label) ? cur.filter((x) => x !== label) : cur.length >= max ? cur : [...cur, label]);
  const err = book.error instanceof ApiError ? book.error : null;
  const confirm = () => book.mutate({ showId: s.id, seats, paymentMethod: method, idempotencyKey: key.current });
  const cta = (block: boolean) => status === 'authenticated' ? (
    <Button block={block} loading={book.isPending} disabled={seats.length === 0} onClick={confirm}>
      {seats.length ? `Confirm booking · ${formatMoney(total, s.currency)}` : 'Select seats'}
    </Button>
  ) : (
    <Link className={`btn btn--primary ${block ? 'btn--block' : ''}`} to={`/login?next=${encodeURIComponent(location.pathname)}`}>Sign in to book</Link>
  );

  return (
    <div className="stack has-book-bar">
      <Link to={`/movies/${s.event.slug}`} className="phead__back"><Icon name="back" size={18} /> {s.event.title}</Link>
      <div className="spread" style={{ flexWrap: 'wrap' }}>
        <div><h1>{s.event.title}</h1><span className="muted small">{showTime(s.startsAt)} · {s.venue.name}{s.screen && ` · ${s.screen}`} · {s.format}</span></div>
      </div>

      <div className="checkout">
        <section className="card card--pad stack" aria-label="Seat map">
          <div className="seat-legend small">
            <span><i className="seat seat--free" /> Available</span><span><i className="seat seat--sel" /> Selected</span><span><i className="seat seat--taken" /> Booked</span>
          </div>
          <div className="seatmap" role="grid" aria-label="Choose seats">
            {s.layout.rows.map((r) => (
              <div key={r.row} className="seatmap__row" role="row">
                <span className="seatmap__label" aria-hidden="true">{r.row}</span>
                {r.seats.map((seat, i) => (
                  <button key={seat.label} type="button" role="gridcell"
                    className={`seat ${!seat.available ? 'seat--taken' : seats.includes(seat.label) ? 'seat--sel' : 'seat--free'} ${r.tier === 'premium' ? 'seat--premium' : ''} ${i === Math.floor(r.seats.length / 2) - 1 ? 'seat--aisle' : ''}`}
                    disabled={!seat.available} aria-pressed={seats.includes(seat.label)}
                    aria-label={`Seat ${seat.label}, ${r.tier}, ${seat.available ? 'available' : 'booked'}`}
                    onClick={() => toggle(seat.label)}>{seat.label.slice(1)}</button>
                ))}
              </div>
            ))}
            <div className="seatmap__screen">Screen this way</div>
          </div>
          <div className="row small muted" style={{ flexWrap: 'wrap', justifyContent: 'center' }}>
            <span>Standard {formatMoney(s.price, s.currency)}</span><span className="dot-sep">Premium (back rows) {formatMoney(s.premiumPrice, s.currency)}</span>
          </div>
        </section>

        <aside className="checkout__aside card card--pad stack">
          <h3>Your booking</h3>
          {seats.length === 0 ? <p className="small muted">Select up to {max} seats.</p> : (
            <>
              <div className="spread small"><span>Seats</span><strong>{[...seats].sort().join(', ')}</strong></div>
              <div className="totals">
                <div><span>Tickets ({seats.length})</span><span>{formatMoney(subtotal, s.currency)}</span></div>
                <div><span>Convenience fee + GST</span><span>{formatMoney(fees * (1 + FEE_TAX), s.currency)}</span></div>
                <div className="totals__grand"><span>Total</span><span>{formatMoney(total, s.currency)}</span></div>
              </div>
              <div className="stack" style={{ gap: 'var(--s-2)' }} role="radiogroup" aria-label="Payment">
                <label className="option">
                  <input type="radio" name="payment" checked={method === 'pay_at_venue'} onChange={() => setMethod('pay_at_venue')} />
                  <div><strong>Pay at venue</strong><div className="muted small">Seats are held for you. Pay at the box office before the show.</div></div>
                </label>
                {status === 'authenticated' && <WalletOption total={total} currency={s.currency} checked={method === 'wallet'} onSelect={() => setMethod('wallet')} />}
              </div>
            </>
          )}
          {err && <div className="badge badge--danger" role="alert" style={{ whiteSpace: 'normal', padding: '8px 12px' }}>{err.message}{err.code === 'seats_unavailable' && ' Pick other seats.'}</div>}
          <div className="book-cta">{cta(true)}</div>
          <p className="small muted">Free cancellation up to 2 hours before the show.</p>
        </aside>
      </div>
      <div className="book-bar" aria-hidden={false}>
        <div className="small">{seats.length ? <><strong>{[...seats].sort().join(', ')}</strong><span className="muted" style={{ display: 'block' }}>{seats.length} seat{seats.length > 1 ? 's' : ''} · review payment below</span></> : <span className="muted">Tap seats to select</span>}</div>
        {cta(false)}
      </div>
    </div>
  );
}
