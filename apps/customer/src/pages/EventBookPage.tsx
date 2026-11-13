import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type EventBookInput } from '@click/api';
import { Button, EmptyState, ErrorState, Icon, Skeleton, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { fmtDate } from '../features/events/parts';
import { useWallet, walletKey } from '../features/wallet/useWallet';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

const newKey = () => (globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`);

/**
 * Booking summary → Confirm Booking, from an accepted quote or a package, for one of the customer's event plans. The
 * server prices it (lines, tax, total) and checks the provider is free that day; the booking is sent with the total the
 * customer saw. Payment goes through the Click. Wallet now, or later (before the pay-by date) when the event is far enough.
 */
export function EventBookPage() {
  useThemeOverride('events');
  const [sp] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const quoteId = sp.get('quote');
  const packageId = sp.get('package');
  const plans = useQuery({ queryKey: ['eventhub', 'plans'], queryFn: () => api.eventHub.plans() });
  const usable = (plans.data?.results ?? []).filter((p) => (p.status === 'planning' || p.status === 'booked'));
  const [planId, setPlanId] = useState<string>(sp.get('plan') ?? '');
  useEffect(() => { if (!planId && usable.length === 1) setPlanId(usable[0]!.id); }, [usable, planId]);
  const plan = usable.find((p) => p.id === planId);
  const [guests, setGuests] = useState<number | null>(null);
  const [addons, setAddons] = useState<string[]>([]);
  const [optional, setOptional] = useState<string[]>([]);
  const [method, setMethod] = useState<'wallet' | 'pay_later'>('wallet');
  const idem = useRef(newKey());
  const wallet = useWallet();

  const planDetail = useQuery({ queryKey: ['eventhub', 'plan', planId], queryFn: () => api.eventHub.plan(planId), enabled: !!planId && !!quoteId });
  const quote = planDetail.data?.enquiries.flatMap((e) => e.quotes.map((q) => ({ ...q, provider: e.provider }))).find((q) => q.id === quoteId);
  const pkgOwner = useQuery({ queryKey: ['eventhub', 'home', null], queryFn: () => api.eventHub.home(null), enabled: !!packageId, staleTime: 60_000 });
  const pkg = pkgOwner.data?.packages.find((x) => x.id === packageId);

  const input: EventBookInput = useMemo(() => ({
    planId, quoteId: quoteId || null, packageId: packageId || null, guests: packageId ? guests ?? plan?.guests ?? null : null,
    addonIds: addons, optionalItems: optional, paymentMethod: method,
  }), [planId, quoteId, packageId, guests, plan?.guests, addons, optional, method]);
  const est = useQuery({ queryKey: ['eventhub', 'estimate', input], queryFn: () => api.eventHub.estimate(input), enabled: !!planId && !!plan, placeholderData: (p) => p, retry: false });
  const e = est.data;
  const book = useMutation({
    mutationFn: () => api.eventHub.book({ ...input, expectedTotal: e?.total ?? null, idempotencyKey: idem.current }),
    onSuccess: (b) => { qc.invalidateQueries({ queryKey: ['eventhub'] }); qc.invalidateQueries({ queryKey: walletKey }); navigate(`/events/bookings/${b.id}`, { replace: true, state: { justBooked: true } }); },
    onError: (err) => {
      if (err instanceof ApiError && ['price_changed', 'not_bookable'].includes(err.code)) { qc.invalidateQueries({ queryKey: ['eventhub', 'estimate'] }); idem.current = newKey(); }
      toast(err instanceof ApiError ? err.message : 'Couldn’t book.', 'error');
    },
  });
  const balance = wallet.data ? Number(wallet.data.balance) : null;
  const short = method === 'wallet' && balance != null && e != null && balance < Number(e.total);

  if (!quoteId && !packageId) return <div className="ev-page"><EmptyState icon="gift" title="Choose a package or a quote to book" action={<Link to="/events" className="btn btn--primary">Back to Events</Link>} /></div>;
  if (plans.isError) return <div className="ev-page"><ErrorState error={plans.error} onRetry={() => plans.refetch()} /></div>;
  if (plans.isPending) return <div className="ev-page"><Skeleton height={360} radius={24} /></div>;

  return (
    <div className="ev-page" data-theme="events">
      <button type="button" className="ev-back" onClick={() => navigate(-1)}><Icon name="back" size={18} /> Back</button>
      <h1 className="ev-title">Booking summary</h1>

      {pkg && (
        <div className="ev-booksrc"><span className="ev-kicker">Package</span><strong>{pkg.name}</strong><span className="small ev-muted">{pkg.provider?.name} · {pkg.priceLabel}{pkg.basis === 'per_guest' ? ' per guest' : ''} · {pkg.minGuests}–{pkg.maxGuests} guests</span></div>
      )}
      {quote && (
        <div className="ev-booksrc"><span className="ev-kicker">Quote v{quote.version}</span><strong>{quote.provider.name}</strong><span className="small ev-muted">{formatMoney(quote.amount)} + tax for the required items</span></div>
      )}

      <section className="ev-step">
        <h2 className="ev-h2">Which event?</h2>
        {usable.length === 0 ? (
          <div className="ev-note"><Icon name="gift" size={14} /> Bookings belong to an event plan (date, place and guests).{' '}
            <Link className="ev-link" to={`/events/plan?package=${packageId ?? ''}${pkg?.provider ? `&provider=${pkg.provider.id}` : ''}${pkg?.eventTypes[0] ? `&type=${pkg.eventTypes[0]}` : ''}`}>Plan this event</Link></div>
        ) : (
          <div className="ev-addrs" role="radiogroup" aria-label="Event plan">
            {usable.map((p) => (
              <button key={p.id} type="button" role="radio" aria-checked={p.id === planId} className={`ev-addr${p.id === planId ? ' is-on' : ''}`} disabled={!!quoteId && p.id !== planId}
                onClick={() => { setPlanId(p.id); setGuests(null); }}>
                <Icon name="gift" size={16} /><span><strong>{p.title}</strong><span className="small ev-muted">{p.dateFlexible ? 'Flexible date' : fmtDate(p.date)} · {p.guests} guests · {p.address.line2 || p.address.line1}</span></span>
              </button>
            ))}
            {packageId && <Link to={`/events/plan?package=${packageId}${pkg?.provider ? `&provider=${pkg.provider.id}` : ''}`} className="ev-link small">+ Plan a new event for this package</Link>}
          </div>
        )}
      </section>

      {plan && pkg && (
        <section className="ev-step">
          <h2 className="ev-h2">Guests & add-ons</h2>
          <label className="ev-field">Guests ({pkg.minGuests}–{pkg.maxGuests})
            <input inputMode="numeric" value={guests ?? plan.guests} onChange={(ev) => setGuests(Number(ev.target.value.replace(/\D/g, '')) || 0)} />
          </label>
          {pkg.addons.map((a) => (
            <label key={a.id} className="ev-check"><input type="checkbox" checked={addons.includes(a.id)} onChange={(ev) => setAddons(ev.target.checked ? [...addons, a.id] : addons.filter((x) => x !== a.id))} />
              {a.name} <span className="ev-muted">+{formatMoney(a.price)}{a.perGuest ? ' per guest' : ''}</span></label>
          ))}
        </section>
      )}
      {plan && quote && quote.items.some((i) => i.optional) && (
        <section className="ev-step">
          <h2 className="ev-h2">Optional items</h2>
          {quote.items.map((i, n) => i.optional && (
            <label key={n} className="ev-check"><input type="checkbox" checked={optional.includes(String(n))} onChange={(ev) => setOptional(ev.target.checked ? [...optional, String(n)] : optional.filter((x) => x !== String(n)))} />
              {i.label} <span className="ev-muted">+{formatMoney(i.amount)}</span></label>
          ))}
        </section>
      )}

      {plan && (est.isError ? <ErrorState error={est.error} onRetry={() => est.refetch()} /> : !e ? <Skeleton height={260} radius={22} /> : (
        <>
          <section className="ev-step">
            <dl className="ev-dl">
              <dt>Event</dt><dd>{e.plan.eventType} · {e.plan.number}</dd>
              <dt>Provider</dt><dd>{e.provider.name}</dd>
              <dt>Date</dt><dd>{fmtDate(e.plan.date)}</dd>
              <dt>Time</dt><dd>{e.plan.startTime ?? 'To agree with the team'}</dd>
              <dt>Location</dt><dd>{[e.plan.address.line1, e.plan.address.city].filter(Boolean).join(', ')}</dd>
              <dt>Guests</dt><dd>{e.guests}</dd>
              <dt>Services</dt><dd>{e.services.join(', ') || '—'}</dd>
            </dl>
            <ul className="ev-lines">{e.lines.map((l, i) => <li key={i}><span>{l.label}</span><span>{formatMoney(l.amount)}</span></li>)}
              {Number(e.discount) > 0 && <li><span>Discount</span><span>−{formatMoney(e.discount)}</span></li>}
              <li><span>Tax (18%)</span><span>{formatMoney(e.tax)}</span></li>
              <li className="ev-lines__total"><span>Total</span><span>{formatMoney(e.total)}</span></li>
            </ul>
            {e.terms && <p className="small ev-muted">Terms: {e.terms}</p>}
            <p className="small"><Icon name="clock" size={13} /> {e.cancellation}</p>
          </section>
          <section className="ev-step">
            <h2 className="ev-h2">Payment</h2>
            <div className="ev-addrs" role="radiogroup" aria-label="Payment method">
              <button type="button" role="radio" aria-checked={method === 'wallet'} className={`ev-addr${method === 'wallet' ? ' is-on' : ''}`} onClick={() => setMethod('wallet')}>
                <Icon name="wallet" size={16} /><span><strong>Click. Wallet</strong><span className="small ev-muted">Pay now and confirm{balance != null ? ` · balance ${formatMoney(String(balance))}` : ''}</span></span>
              </button>
              <button type="button" role="radio" aria-checked={method === 'pay_later'} disabled={!e.payLaterAllowed} className={`ev-addr${method === 'pay_later' ? ' is-on' : ''}`} onClick={() => setMethod('pay_later')}>
                <Icon name="clock" size={16} /><span><strong>Hold now, pay later</strong><span className="small ev-muted">{e.payLaterAllowed ? 'Pay from your wallet up to 2 days before the event, or the date is released' : 'Not available this close to the event'}</span></span>
              </button>
            </div>
            {short && <p className="small">Not enough wallet balance. <Link to="/wallet" className="ev-link">Add money</Link>{e.payLaterAllowed ? ' or hold now and pay later.' : '.'}</p>}
            <p className="small ev-muted">Card and UPI aren’t available yet.</p>
          </section>
          {!e.bookable && <p className="ev-note" role="status"><Icon name="alert" size={14} /> {e.problem}</p>}
          <Button block loading={book.isPending} disabled={!e.bookable || short || est.isFetching} onClick={() => book.mutate()}>
            Confirm Booking · {formatMoney(e.total)}
          </Button>
        </>
      ))}
    </div>
  );
}
