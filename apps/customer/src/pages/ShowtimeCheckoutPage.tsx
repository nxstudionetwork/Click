import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@click/api';
import { Button, EmptyState, ErrorState, Icon, QuantityStepper, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { dayOf, timeOf, useNowTick } from '../features/showtime/time';
import { useWallet, walletKey } from '../features/wallet/useWallet';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

/**
 * Showtime checkout for held seats: food & drinks (this cinema's menu), offers, payment and the bill. Every figure
 * comes from the server's quote; the countdown is the server's hold expiry. Nothing is charged until "Pay".
 */
export function ShowtimeCheckoutPage() {
  useThemeOverride('movies');
  const { holdId = '' } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [items, setItems] = useState<Record<string, number>>({});
  const [offerId, setOfferId] = useState<string | null>(null);
  const [payment, setPayment] = useState<'wallet' | 'pay_at_venue'>('pay_at_venue');
  const key = useRef(crypto.randomUUID());
  const wallet = useWallet();
  const concessions = Object.entries(items).filter(([, n]) => n > 0).map(([id, quantity]) => ({ id, quantity }));
  const quote = useQuery({
    queryKey: ['showtime', 'quote', holdId, concessions, offerId, payment],
    queryFn: () => api.showtime.quote({ holdId, concessions, offerId, paymentMethod: payment }),
    placeholderData: keepPreviousData, retry: false,
  });
  const showId = quote.data?.hold.showId;
  const show = useQuery({ queryKey: ['showtime', 'seats', showId], queryFn: () => api.events.seatMap(showId!), enabled: !!showId, staleTime: 60_000 });
  const now = useNowTick(1000);
  const expiresAt = quote.data ? new Date(quote.data.hold.expiresAt).getTime() : null;
  const left = expiresAt ? Math.max(0, Math.floor((expiresAt - now) / 1000)) : null;
  const expired = left === 0;
  // An offer that stops applying (e.g. a wallet-only offer after switching to pay at venue) is dropped, with the reason shown.
  const offerProblem = quote.data?.offerProblem;

  const pay = useMutation({
    mutationFn: () => api.customer.bookings.create({ holdId, concessions, offerId: quote.data?.offer?.id ?? null, paymentMethod: payment, idempotencyKey: key.current }),
    onSuccess: (b) => {
      qc.invalidateQueries({ queryKey: walletKey });
      qc.invalidateQueries({ queryKey: ['customer', 'bookings'] });
      navigate(`/tickets/${b.id}`, { replace: true, state: { justBooked: true } });
    },
    onError: (e) => { if (e instanceof ApiError && e.status !== 0) key.current = crypto.randomUUID(); },
  });
  const release = useMutation({ mutationFn: () => api.showtime.releaseHold(holdId), onSettled: () => navigate(showId ? `/shows/${showId}` : '/showtime', { replace: true }) });
  useEffect(() => { if (offerProblem) setOfferId(null); }, [offerProblem]);

  if (quote.isError && !quote.data) {
    const gone = quote.error instanceof ApiError && ['hold_not_found', 'hold_expired'].includes(quote.error.code);
    return (
      <div className="st-page">
        {gone ? <EmptyState icon="clock" title="Your seat hold has ended" message="Seats are held for a few minutes. Choose them again to continue."
          action={<Link to="/showtime" className="btn btn--primary">Back to Showtime</Link>} />
          : <ErrorState error={quote.error} onRetry={() => quote.refetch()} />}
      </div>
    );
  }
  if (quote.isPending) return <div className="st-page"><Skeleton height={80} radius={18} /><Skeleton height={260} radius={18} /></div>;
  const q = quote.data!;
  const m = show.data;
  const balance = Number(wallet.data?.balance ?? 0);
  const walletShort = balance < Number(q.lines.total);
  const err = pay.error instanceof ApiError ? pay.error : null;
  const mm = left != null ? `${String(Math.floor(left / 60)).padStart(2, '0')}:${String(left % 60).padStart(2, '0')}` : '--:--';
  const groups = q.menu.reduce<Record<string, typeof q.menu>>((acc, i) => { (acc[i.categoryLabel] ||= []).push(i); return acc; }, {});

  return (
    <div className="st-page st-checkout" data-theme="movies">
      <div className="stack" style={{ gap: 'var(--s-4)' }}>
        <header className="spread" style={{ alignItems: 'flex-start' }}>
          <div className="stack" style={{ gap: 4 }}>
            <h1 style={{ fontSize: 'clamp(1.3rem, 4vw, 1.8rem)' }}>Checkout</h1>
            {m && <span className="small muted">{m.event.title} · {m.venue.name} · {dayOf(m.startsAt)}, {timeOf(m.startsAt)}</span>}
            {m && <span className="small" style={{ color: 'var(--c-ink-2)' }}>{[m.language, m.format, m.screen].filter(Boolean).join(' • ')}</span>}
          </div>
          <span className={`st-timer ${left !== null && left < 90 ? 'st-timer--low' : ''}`} role="timer" aria-live="off" aria-label={`Seats held for ${mm}`}>
            <Icon name="clock" size={16} /> {mm}
          </span>
        </header>
        {expired && (
          <div className="st-box" role="alert"><strong>Your seat hold has expired.</strong><span className="small muted">The seats have gone back on sale. Choose them again to continue.</span>
            <Link to={showId ? `/shows/${showId}` : '/showtime'} className="btn btn--primary btn--sm">Choose seats again</Link></div>
        )}

        <section className="st-box" aria-label="Seats">
          <div className="spread"><h3>Seats</h3><Button size="sm" variant="ghost" loading={release.isPending} onClick={() => release.mutate()}>Change seats</Button></div>
          <div className="chips">{q.hold.seats.map((s) => <span key={s.label} className="chip">{s.label} · {formatMoney(s.price, q.currency)}</span>)}</div>
        </section>

        {q.menu.length > 0 && (
          <section className="st-box" aria-label="Food and drinks">
            <h3>Add Food & Drinks</h3>
            <span className="small muted">From {m?.venue.name ?? 'this cinema'}, collected at the counter with your ticket.</span>
            {Object.entries(groups).map(([label, list]) => (
              <div key={label} className="st-menu">
                <span className="st-venue__label">{label}</span>
                {list.map((i) => (
                  <div key={i.id} className="st-menu__item">
                    <div><strong className="small">{i.name}</strong>{i.description && <div className="small muted">{i.description}</div>}
                      <div className="small">{formatMoney(i.price, q.currency)}{i.isVeg ? '' : ' · Non-veg'}</div></div>
                    {items[i.id] ? <QuantityStepper value={items[i.id]!} max={10} label={i.name} onChange={(n) => setItems((s) => ({ ...s, [i.id]: Math.max(0, n) }))} />
                      : <Button size="sm" variant="secondary" onClick={() => setItems((s) => ({ ...s, [i.id]: 1 }))}>Add</Button>}
                  </div>
                ))}
              </div>
            ))}
          </section>
        )}

        {q.offers.length > 0 && (
          <section className="st-box" aria-label="Offers">
            <h3>Offers</h3>
            {q.offers.map((o) => {
              const on = q.offer?.id === o.id;
              return (
                <div key={o.id} className="spread small" style={{ alignItems: 'center', gap: 10 }}>
                  <span><strong>{o.title}</strong><br /><span className="muted">{on ? `Applied · you save ${formatMoney(q.lines.discount, q.currency)}` : o.problem ?? (o.saving ? `Save ${formatMoney(o.saving, q.currency)}` : o.description)}</span></span>
                  {on ? <Button size="sm" variant="ghost" onClick={() => setOfferId(null)}>Remove</Button>
                    : <Button size="sm" variant="secondary" disabled={!!o.problem} onClick={() => setOfferId(o.id)}>Apply</Button>}
                </div>
              );
            })}
            {offerProblem && <p className="small" role="status" style={{ color: '#ffb4c0' }}>Offer removed: {offerProblem}</p>}
          </section>
        )}

        <section className="st-box st-pay" aria-label="Payment">
          <h3>Payment</h3>
          <label><input type="radio" name="pay" checked={payment === 'pay_at_venue'} onChange={() => setPayment('pay_at_venue')} />
            <span><strong>Pay at the cinema</strong><br /><span className="small muted">Pay at the box office before the show. Nothing is charged now.</span></span></label>
          <label style={walletShort ? { opacity: 0.6 } : undefined}><input type="radio" name="pay" checked={payment === 'wallet'} disabled={walletShort} onChange={() => setPayment('wallet')} />
            <span><strong>Click. Wallet</strong><br /><span className="small muted">{wallet.isPending ? 'Checking balance…' : `Balance ${formatMoney(balance, q.currency)}${walletShort ? ' · not enough for this booking' : ' · paid now, refunded if you cancel in time'}`}</span></span></label>
          <span className="small muted"><Icon name="shield" size={13} /> Card and UPI payments aren’t connected yet.</span>
        </section>
      </div>

      <aside className="st-checkout__aside st-box" aria-label="Bill">
        <h3>Bill</h3>
        <div className="st-bill">
          <div><span>Tickets ({q.hold.seats.length})</span><span>{formatMoney(q.lines.tickets, q.currency)}</span></div>
          {Number(q.lines.concessions) > 0 && <div><span>Food & drinks</span><span>{formatMoney(q.lines.concessions, q.currency)}</span></div>}
          <div><span>Convenience fee</span><span>{formatMoney(q.lines.convenienceFee, q.currency)}</span></div>
          <div><span>Taxes</span><span>{formatMoney(q.lines.tax, q.currency)}</span></div>
          {Number(q.lines.discount) > 0 && <div className="st-bill__save"><span>{q.offer?.title}</span><span>−{formatMoney(q.lines.discount, q.currency)}</span></div>}
          <div className="st-bill__total"><span>Total</span><span>{formatMoney(q.lines.total, q.currency)}</span></div>
        </div>
        {err && (
          <p className="small" role="alert" style={{ color: '#ffb4c0' }}>
            {err.message}{err.code === 'insufficient_wallet_balance' ? ' Choose “Pay at the cinema” or add money to your wallet.' : ''}
            {err.code === 'hold_expired' || err.code === 'hold_not_found' ? <> <Link to={showId ? `/shows/${showId}` : '/showtime'} style={{ textDecoration: 'underline' }}>Choose seats again</Link></> : null}
          </p>
        )}
        <button type="button" className="st-btn st-btn--book" style={{ justifyContent: 'center', width: '100%' }} disabled={expired || pay.isPending || quote.isFetching}
          onClick={() => pay.mutate()}>
          {pay.isPending ? 'Booking…' : payment === 'wallet' ? `Pay ${formatMoney(q.lines.total, q.currency)}` : `Confirm booking · ${formatMoney(q.lines.total, q.currency)}`}
        </button>
        <span className="small muted">Cancel up to {m?.cancellationHours ?? 2} hours before the show for a full refund of wallet payments.</span>
      </aside>
    </div>
  );
}
