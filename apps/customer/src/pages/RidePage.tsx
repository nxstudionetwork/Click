import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type RidePlace, type RideQuoteOption } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { useThemeOverride } from '../components/layout/AppShell';
import { Button, Icon, type IconName } from '../components/ui';
import { useAddresses } from '../features/addresses/useAddresses';
import { LocationPicker } from '../features/ride/LocationPicker';
import { RideMap } from '../features/ride/RideMap';
import { useWallet, walletKey } from '../features/wallet/useWallet';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';
import { useDeliveryLocation } from '../location/LocationProvider';

const MAX_STOPS = 2;
type Target = 'pickup' | 'drop' | number;
const RIDE_ICON: Record<string, IconName> = { bike: 'bike', auto: 'auto', car: 'car' };

/** Click. Ride: map-first booking console (location → route → options → confirm). Matching and status live on /rides/:id. */
export function RidePage() {
  useThemeOverride('ride');
  const { status } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const { selected, point } = useDeliveryLocation();
  const addresses = useAddresses(status === 'authenticated');
  const wallet = useWallet();

  const [pickup, setPickup] = useState<RidePlace | null>(null);
  const [drop, setDrop] = useState<RidePlace | null>(null);
  const [stops, setStops] = useState<RidePlace[]>([]);
  const [picker, setPicker] = useState<Target | null>(null);
  const [mapPick, setMapPick] = useState<{ target: Target; point: { lat: number; lng: number } | null } | null>(null);
  const [rideType, setRideType] = useState<string | null>(null);
  const [payment, setPayment] = useState<'cash' | 'wallet'>('cash');
  const [offerId, setOfferId] = useState<string | null>(null);
  const [schedule, setSchedule] = useState<string | null>(null);
  const [passenger, setPassenger] = useState<{ name: string; phone: string } | null>(null);
  const idempotencyKey = useRef(crypto.randomUUID());

  // Pickup starts at the active app location (chosen on Home) when it has coordinates; it can be changed here.
  useEffect(() => {
    if (!pickup && selected && point) setPickup({ label: selected.label[0]!.toUpperCase() + selected.label.slice(1), address: [selected.line1, selected.line2, selected.city].filter(Boolean).join(', '), lat: point.lat, lng: point.lng });
  }, [selected, point]); // eslint-disable-line react-hooks/exhaustive-deps

  // "Ride again" (from a completed ride) and Buddy hand-offs pre-fill, but never book on their own.
  const again = params.get('again');
  const againRide = useQuery({ queryKey: ['customer', 'rides', again], queryFn: () => api.customer.rides.get(again!), enabled: !!again && status === 'authenticated' });
  useEffect(() => {
    if (!againRide.data) return;
    setPickup(againRide.data.pickup); setDrop(againRide.data.drop); setStops(againRide.data.stops); setRideType(againRide.data.rideType.code);
    setParams({}, { replace: true });
  }, [againRide.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const toQuery = params.get('to');
  useEffect(() => { if (toQuery && status === 'authenticated') setPicker('drop'); }, [toQuery, status]);

  // Only stops with a chosen place count (a stop being added has no place yet).
  const validStops = useMemo(() => stops.filter((s) => s.label), [stops]);
  const trip = useMemo(() => (pickup && drop ? { pickup, drop, stops: validStops, offerId } : null), [pickup, drop, validStops, offerId]);
  const quote = useQuery({ queryKey: ['rides', 'quote', trip], queryFn: () => api.customer.rides.quote(trip!), enabled: !!trip && status === 'authenticated', staleTime: 60_000 });
  const options = quote.data?.options ?? [];
  const chosen: RideQuoteOption | undefined = options.find((o) => o.rideType.code === rideType && o.available) ?? options.find((o) => o.available);
  useEffect(() => { if (chosen && chosen.rideType.code !== rideType) setRideType(chosen.rideType.code); }, [chosen, rideType]);
  const offers = (quote.data?.offers ?? []).filter((o) => !chosen || o.rideTypes.length === 0 || o.rideTypes.includes(chosen.rideType.code));

  const book = useMutation({
    mutationFn: () => api.customer.rides.request({
      pickup: pickup!, drop: drop!, stops: validStops, rideType: chosen!.rideType.code, paymentMethod: payment, offerId,
      idempotencyKey: idempotencyKey.current, scheduledFor: schedule ? new Date(schedule).toISOString() : null,
      passengerName: passenger?.name ?? '', passengerPhone: passenger?.phone ?? '',
    }),
    onSuccess: (ride) => { qc.invalidateQueries({ queryKey: walletKey }); qc.invalidateQueries({ queryKey: ['customer', 'rides'] }); navigate(`/rides/${ride.id}`); },
    onError: (e) => { if (e instanceof ApiError && e.status !== 0) idempotencyKey.current = crypto.randomUUID(); },
  });
  const err = book.error instanceof ApiError ? book.error : book.error ? new Error('Couldn’t book. Check your connection and try again.') : null;

  const setTarget = (t: Target, p: RidePlace) => {
    if (t === 'pickup') setPickup(p); else if (t === 'drop') setDrop(p); else setStops((s) => s.map((x, i) => (i === t ? p : x)));
    setPicker(null); setMapPick(null); book.reset();
  };
  const quick = (label: string) => (addresses.data ?? []).find((a) => a.label === label && a.latitude && a.longitude);
  const home = quick('home'), work = quick('work');
  const toPlace = (a: NonNullable<typeof home>): RidePlace => ({ label: a.label[0]!.toUpperCase() + a.label.slice(1), address: [a.line1, a.line2, a.city].filter(Boolean).join(', '), lat: Number(a.latitude), lng: Number(a.longitude) });
  const walletShort = payment === 'wallet' && chosen && wallet.data && Number(wallet.data.balance) < Number(chosen.fare.total);

  if (status === 'anonymous') {
    return (
      <div className="ride">
        <RideIntro />
        <div className="ride-signin"><Icon name="ride" size={28} /><p>Sign in to book a ride with Click.</p><Link to="/login?next=/rides" className="btn btn--primary">Sign in</Link></div>
      </div>
    );
  }

  return (
    <div className="ride">
      <RideIntro />
      <div className="ride__grid">
        <div className="ride__map-wrap">
          <RideMap pickup={pickup} drop={drop} stops={validStops} center={point} className="ride__map"
            onPick={mapPick ? (p) => setMapPick({ ...mapPick, point: p }) : undefined} />
          {mapPick ? (
            <div className="ride__pickbar" role="status">
              <span>{mapPick.point ? 'Spot selected. Confirm it or tap again.' : `Tap the map to set the ${mapPick.target === 'pickup' ? 'pickup' : mapPick.target === 'drop' ? 'drop' : 'stop'}`}</span>
              <div className="row">
                <button className="btn btn--ghost btn--sm" onClick={() => setMapPick(null)}>Cancel</button>
                <button className="btn btn--primary btn--sm" disabled={!mapPick.point}
                  onClick={() => mapPick.point && setTarget(mapPick.target, { label: 'Pinned location', address: `${mapPick.point.lat.toFixed(5)}, ${mapPick.point.lng.toFixed(5)}`, ...mapPick.point })}>
                  Confirm spot
                </button>
              </div>
            </div>
          ) : quote.data && (
            <span className="ride__estimate">{quote.data.distanceKm} km · estimated from your points (no live traffic)</span>
          )}
        </div>

        <div className="ride__console">
          <section className="route-box" aria-label="Your trip">
            <h2>Where are you going?</h2>
            <RouteRow kind="pickup" title="Pick-up" place={pickup} placeholder="Choose pickup location" onClick={() => setPicker('pickup')} />
            {stops.map((s, i) => (
              <RouteRow key={i} kind="stop" index={i + 1} title={`Stop ${i + 1}`} place={s} placeholder="Choose stop" onClick={() => setPicker(i)}
                onRemove={() => setStops((x) => x.filter((_, j) => j !== i))} />
            ))}
            <RouteRow kind="drop" title="Drop" place={drop} placeholder="Enter destination" onClick={() => setPicker('drop')} />
            {stops.length < MAX_STOPS && drop && (
              <button type="button" className="route-box__add" onClick={() => { setStops((s) => [...s, { label: '', address: '', lat: 0, lng: 0 }]); setPicker(stops.length); }}>
                <Icon name="plus" size={16} /> Add stop
              </button>
            )}
          </section>

          <div className="ride-quick" role="group" aria-label="Quick actions">
            {home && <button className="ride-chip" onClick={() => setDrop(toPlace(home))}><Icon name="home" size={16} />Home</button>}
            {work && <button className="ride-chip" onClick={() => setDrop(toPlace(work))}><Icon name="briefcase" size={16} />Work</button>}
            <button className="ride-chip" onClick={() => setPicker('drop')}><Icon name="history" size={16} />Recent</button>
            <button className={`ride-chip ${schedule !== null ? 'is-on' : ''}`} aria-pressed={schedule !== null} onClick={() => setSchedule((s) => (s === null ? defaultSchedule() : null))}><Icon name="clock" size={16} />Schedule</button>
            <button className={`ride-chip ${passenger ? 'is-on' : ''}`} aria-pressed={!!passenger} onClick={() => setPassenger((p) => (p ? null : { name: '', phone: '' }))}><Icon name="user" size={16} />For someone</button>
          </div>

          {schedule !== null && (
            <label className="ride-field">
              <span>Pickup time</span>
              <input type="datetime-local" value={schedule} min={toLocalInput(new Date(Date.now() + 30 * 60_000))} max={toLocalInput(new Date(Date.now() + 7 * 86_400_000))} onChange={(e) => setSchedule(e.target.value)} />
              <small>Between 30 minutes and 7 days from now. We start finding a driver shortly before.</small>
            </label>
          )}
          {passenger && (
            <div className="ride-field ride-field--pair">
              <span>Passenger</span>
              <input placeholder="Name" value={passenger.name} onChange={(e) => setPassenger({ ...passenger, name: e.target.value })} maxLength={120} aria-label="Passenger name" />
              <input placeholder="Phone" type="tel" value={passenger.phone} onChange={(e) => setPassenger({ ...passenger, phone: e.target.value })} maxLength={20} aria-label="Passenger phone" />
            </div>
          )}

          {!trip ? (
            <p className="ride-hint"><Icon name="pin" size={16} /> Choose a pickup and a drop to see rides and fares.</p>
          ) : quote.isPending ? (
            <div className="ride-options" aria-busy="true">{Array.from({ length: 3 }, (_, i) => <span key={i} className="skeleton ride-option ride-option--skel" />)}</div>
          ) : quote.isError ? (
            <div className="hstate" role="alert">
              <span className="hstate__icon hstate__icon--error"><Icon name="alert" size={18} /></span>
              <div><strong>{quote.error instanceof ApiError && quote.error.status === 400 ? quote.error.message : 'We couldn’t get fares right now.'}</strong><span>Change a location or try again.</span></div>
              <button className="btn btn--outline btn--sm" onClick={() => quote.refetch()}>Retry</button>
            </div>
          ) : (
            <>
              <section aria-labelledby="ride-opts-h" className="ride-section">
                <h3 id="ride-opts-h">Choose a ride</h3>
                {options.every((o) => !o.available) && <p className="loc-warn" role="status">No rides available right now. Try another ride type or pickup point.</p>}
                <div className="ride-options" role="radiogroup" aria-label="Ride options">
                  {options.map((o) => (
                    <button key={o.rideType.code} type="button" role="radio" aria-checked={chosen?.rideType.code === o.rideType.code} disabled={!o.available}
                      className={`ride-option ${chosen?.rideType.code === o.rideType.code ? 'is-on' : ''}`} onClick={() => setRideType(o.rideType.code)}>
                      <span className="ride-option__icon"><Icon name={RIDE_ICON[o.rideType.icon] ?? 'car'} size={24} /></span>
                      <span className="ride-option__name">{o.rideType.name}<small><Icon name="user" size={11} />{o.rideType.seats}</small></span>
                      <span className="ride-option__eta">{o.available ? `${o.pickupEtaMinutes} min away` : 'No drivers nearby'}</span>
                      <span className="ride-option__fare">
                        {Number(o.fare.discount) > 0 && <s>{formatMoney(o.fare.subtotal, 'INR')}</s>}
                        {formatMoney(o.fare.total, 'INR')}
                      </span>
                      <span className="ride-option__desc">{o.rideType.description} · ~{o.durationMinutes} min trip</span>
                    </button>
                  ))}
                </div>
              </section>

              {chosen && (
                <section className="ride-section ride-details" aria-labelledby="ride-pay-h">
                  {offers.length > 0 && (
                    <div className="ride-offers">
                      {offers.map((o) => {
                        const on = offerId === o.id;
                        const problem = on ? chosen.offerProblem : null;
                        return (
                          <button key={o.id} type="button" className={`ride-offer ${on ? 'is-on' : ''}`} aria-pressed={on} onClick={() => setOfferId(on ? null : o.id)}>
                            <Icon name="tag" size={16} /><span><strong>{o.title}</strong><small>{problem ?? (on ? 'Applied · fare updated' : o.description)}</small></span>
                            <span className="ride-offer__cta">{on ? 'Remove' : 'Apply'}</span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                  <h3 id="ride-pay-h">Pay with</h3>
                  <div className="ride-pay" role="radiogroup" aria-label="Payment method">
                    <button type="button" role="radio" aria-checked={payment === 'cash'} className={`ride-pay__opt ${payment === 'cash' ? 'is-on' : ''}`} onClick={() => setPayment('cash')}>
                      <Icon name="wallet" size={18} /><span><strong>Cash</strong><small>Pay the driver at the end</small></span>
                    </button>
                    <button type="button" role="radio" aria-checked={payment === 'wallet'} className={`ride-pay__opt ${payment === 'wallet' ? 'is-on' : ''}`} onClick={() => setPayment('wallet')}>
                      <Icon name="card" size={18} /><span><strong>Click. Wallet</strong><small>{wallet.data ? `Balance ${formatMoney(wallet.data.balance, wallet.data.currency)}` : 'Charged when you book; refunded if cancelled'}</small></span>
                    </button>
                  </div>
                  {walletShort && <p className="loc-warn" role="status">Your wallet balance is lower than this fare. Choose cash or add money to your wallet.</p>}
                </section>
              )}
            </>
          )}

          {chosen && (
            <div className="ride-confirm">
              {err && (
                <p className="ride-confirm__err" role="alert">
                  {err.message}
                  {err instanceof ApiError && err.code === 'insufficient_wallet_balance' && <> <button className="btn btn--ghost btn--sm" onClick={() => { setPayment('cash'); book.reset(); }}>Pay with cash</button></>}
                </p>
              )}
              <div className="ride-confirm__sum">
                <span>{chosen.rideType.name} · {payment === 'cash' ? 'Cash' : 'Wallet'}{schedule ? ` · ${new Date(schedule).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })}` : ''}</span>
                <strong>{formatMoney(chosen.fare.total, 'INR')}</strong>
              </div>
              <Button block loading={book.isPending} disabled={!!walletShort || (passenger !== null && (!passenger.name.trim() || !passenger.phone.trim()))} onClick={() => book.mutate()}>
                {schedule ? 'Confirm schedule' : 'Confirm Ride'}
              </Button>
              <small className="ride-confirm__note">Upfront fare, calculated by Click. before you confirm.</small>
            </div>
          )}
        </div>
      </div>

      <LocationPicker
        open={picker !== null && !mapPick}
        title={picker === 'pickup' ? 'Choose pickup location' : picker === 'drop' ? 'Where are you going?' : 'Choose a stop'}
        allowCurrent={picker === 'pickup'}
        initialQuery={picker === 'drop' ? toQuery ?? '' : ''}
        onClose={() => { if (typeof picker === 'number' && !stops[picker]?.label) setStops((s) => s.filter((_, i) => i !== picker)); setPicker(null); }}
        onSelect={(p) => picker !== null && setTarget(picker, p)}
        onPickOnMap={() => { if (picker !== null) setMapPick({ target: picker, point: null }); setPicker(null); }}
      />
    </div>
  );
}

function RideIntro() {
  return (
    <header className="ride-intro">
      <h1>Ride</h1>
      <p>Wherever you’re going, get there with Click.</p>
    </header>
  );
}

function RouteRow({ kind, index, title, place, placeholder, onClick, onRemove }: {
  kind: 'pickup' | 'drop' | 'stop'; index?: number; title: string; place: RidePlace | null; placeholder: string; onClick: () => void; onRemove?: () => void;
}) {
  return (
    <div className={`route-row route-row--${kind}`}>
      <span className="route-row__marker" aria-hidden="true">{kind === 'stop' ? index : null}</span>
      <button type="button" className="route-row__btn" onClick={onClick} aria-label={`${title}: ${place?.label || placeholder}. Change`}>
        <span className="route-row__title">{title}</span>
        <span className={`route-row__value ${place?.label ? '' : 'is-empty'}`}>{place?.label || placeholder}</span>
        {place?.address && <span className="route-row__addr">{place.address}</span>}
      </button>
      {onRemove && <button type="button" className="icon-btn" aria-label={`Remove ${title}`} onClick={onRemove}><Icon name="close" size={16} /></button>}
    </div>
  );
}

const toLocalInput = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
const defaultSchedule = () => toLocalInput(new Date(Date.now() + 60 * 60_000));
