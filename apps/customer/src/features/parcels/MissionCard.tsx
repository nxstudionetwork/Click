import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type ParcelMode, type ParcelOptions, type RidePlace, type SavedRecipient } from '@click/api';
import { useAuth } from '../../auth/AuthProvider';
import { Button, Icon, Sheet, useToast } from '../../components/ui';
import { api } from '../../lib/api';
import { formatMoney } from '../../lib/format';
import { LocationPicker } from '../ride/LocationPicker';
import { WalletOption } from '../wallet/WalletOption';
import { walletKey } from '../wallet/useWallet';
import { vehicleIcon } from './parts';
import { PHONE, type ParcelDraftState, type Spot } from './useParcelDraft';

const RideMap = lazy(() => import('../ride/RideMap').then((m) => ({ default: m.RideMap })));

const MODES: { id: ParcelMode; label: string; hint: string; icon: 'send' | 'download' | 'store' }[] = [
  { id: 'send', label: 'Send', hint: 'From you to someone', icon: 'send' },
  { id: 'receive', label: 'Receive', hint: 'From someone to you', icon: 'download' },
  { id: 'store_pickup', label: 'Store pickup', hint: 'From a store to you', icon: 'store' },
];
const WEIGHTS = ['0.5', '1', '3', '5', '10', '20'];
type Target = 'pickup' | 'drop' | number;

function ContactFields({ who, value, onChange, alt = false, prefix }: {
  who: string; value: { name: string; phone: string; altPhone: string; instructions: string }; prefix: string;
  onChange: (v: { name: string; phone: string; altPhone: string; instructions: string }) => void; alt?: boolean;
}) {
  const bad = value.phone !== '' && !PHONE.test(value.phone.trim());
  return (
    <div className="pc-contact">
      <label className="pc-field"><span>{who} name</span>
        <input id={`${prefix}-name`} value={value.name} maxLength={120} autoComplete="name" onChange={(e) => onChange({ ...value, name: e.target.value })} /></label>
      <label className="pc-field"><span>{who} phone</span>
        <input id={`${prefix}-phone`} value={value.phone} inputMode="tel" autoComplete="tel" maxLength={20} aria-invalid={bad}
          onChange={(e) => onChange({ ...value, phone: e.target.value })} placeholder="+91 98765 43210" />
        {bad && <em className="pc-err">Enter a valid phone number</em>}</label>
      {alt && <label className="pc-field"><span>Alternate contact (optional)</span>
        <input value={value.altPhone} inputMode="tel" maxLength={20} onChange={(e) => onChange({ ...value, altPhone: e.target.value })} /></label>}
      <label className="pc-field pc-field--wide"><span>Instructions (optional)</span>
        <input value={value.instructions} maxLength={200} placeholder="Gate, floor, when they're available…" onChange={(e) => onChange({ ...value, instructions: e.target.value })} /></label>
    </div>
  );
}

export function MissionCard({ d, options, recipients }: { d: ParcelDraftState; options?: ParcelOptions; recipients: SavedRecipient[] }) {
  const { status } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const [picker, setPicker] = useState<Target | null>(null);
  const [mapPick, setMapPick] = useState<{ target: Target; point: { lat: number; lng: number } | null } | null>(null);
  const [storeQ, setStoreQ] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [saveRecipient, setSaveRecipient] = useState(false);
  const [review, setReview] = useState(false);
  const [payment, setPayment] = useState<'wallet' | 'cash'>('wallet');
  const key = useRef(crypto.randomUUID());
  const stores = useQuery({ queryKey: ['parcels', 'stores', storeQ], queryFn: () => api.stores.list({ search: storeQ || undefined } as never),
    enabled: d.mode === 'store_pickup' && !d.store, staleTime: 60_000 });
  const q = d.quote.data;
  const veh = q?.vehicles.find((v) => v.code === d.vehicle && v.fare);
  const svc = q?.services.find((s) => s.code === (d.service || q.service));
  useEffect(() => { if (q && !q.paymentMethods.includes(payment)) setPayment(q.paymentMethods[0] ?? 'wallet'); }, [q, payment]);

  const setTarget = (t: Target, p: RidePlace) => {
    const spot: Spot = { label: p.label, address: p.address, lat: p.lat, lng: p.lng };
    if (t === 'pickup') d.setPickup(spot);
    else if (t === 'drop') d.setDrop(spot);
    else d.setStops(d.stops.map((s, i) => (i === t ? { ...s, ...spot } : s)));
    setPicker(null); setMapPick(null);
  };
  const svcInfo = options?.services.find((s) => s.code === (d.service || q?.service));
  const canStop = d.mode === 'send' && (svcInfo?.allowStops ?? true) && d.stops.length < (svcInfo?.maxStops || 3);
  const contactsOk = (d.mode === 'store_pickup' || (d.sender.name.trim() && PHONE.test(d.sender.phone.trim())))
    && d.recipient.name.trim() && PHONE.test(d.recipient.phone.trim()) && (!d.recipient.altPhone || PHONE.test(d.recipient.altPhone.trim()));
  const needsTime = svc?.code === 'scheduled' && !d.scheduledFor;
  const ready = !!q && !q.packageProblem && !!veh && contactsOk && confirmed && !needsTime && d.stops.every((s) => s.lat);

  const book = useMutation({
    mutationFn: () => api.parcels.book({
      ...d.input!, pickup: d.input!.pickup!, drop: d.input!.drop!, service: d.service || q!.service!, vehicle: d.vehicle, paymentMethod: payment, expectedTotal: veh!.fare!.total,
      idempotencyKey: key.current, contentsConfirmed: confirmed, saveRecipient, storeReference: d.storeReference, repeatOf: d.repeatOf,
    }),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ['customer', 'parcels'] });
      qc.invalidateQueries({ queryKey: walletKey });
      navigate(`/parcels/${p.id}`, { state: { justBooked: true } });
    },
    onError: (e) => {
      key.current = crypto.randomUUID();
      if (e instanceof ApiError && e.code === 'price_changed') { d.quote.refetch(); toast('The price changed. Review the new estimate.', 'error'); setReview(false); return; }
      toast(e instanceof ApiError ? e.message : 'Couldn’t book. Check your connection and try again.', 'error');
    },
  });

  const placeRow = (t: Target, spot: Spot | null, label: string, sub?: string) => (
    <button type="button" className={`pc-stop pc-stop--${typeof t === 'number' ? 'mid' : t}`} onClick={() => setPicker(t)}
      aria-label={`${label}: ${spot ? spot.label : 'not set'}. Change`}>
      <span className="pc-stop__dot" aria-hidden="true" />
      <span className="pc-stop__text">
        <span className="pc-kicker">{label}</span>
        <strong>{spot ? spot.label : 'Choose location'}</strong>
        <span className="small muted">{spot ? spot.address || `${spot.lat.toFixed(4)}, ${spot.lng.toFixed(4)}` : sub}</span>
      </span>
      <Icon name="edit" size={16} />
    </button>
  );

  return (
    <section className="pc-mission" aria-labelledby="pc-mission-h">
      <header className="pc-mission__head">
        <h2 id="pc-mission-h">Plan a delivery</h2>
        <div className="pc-modes" role="tablist" aria-label="Delivery type">
          {MODES.map((m) => (
            <button key={m.id} role="tab" type="button" aria-selected={d.mode === m.id} className="pc-mode" onClick={() => d.setMode(m.id)}>
              <Icon name={m.icon} size={18} /><strong>{m.label}</strong><span>{m.hint}</span>
            </button>
          ))}
        </div>
      </header>

      {/* 1. Route */}
      <div className="pc-step">
        <span className="pc-step__n" aria-hidden="true">1</span>
        <div className="pc-step__body">
          <h3>Pickup &amp; drop</h3>
          <div className="pc-route">
            {d.mode === 'store_pickup' ? (
              d.store ? (
                <button type="button" className="pc-stop pc-stop--pickup" onClick={() => d.setStore(null)} aria-label={`Store: ${d.store.name}. Change`}>
                  <span className="pc-stop__dot" aria-hidden="true" />
                  <span className="pc-stop__text"><span className="pc-kicker">Pickup · store</span><strong>{d.store.name}</strong><span className="small muted">Location from the store’s Click. listing</span></span>
                  <Icon name="edit" size={16} />
                </button>
              ) : (
                <div className="pc-storepick">
                  <span className="pc-kicker">Pickup · choose the store</span>
                  <input value={storeQ} onChange={(e) => setStoreQ(e.target.value)} placeholder="Search stores on Click." aria-label="Search stores" />
                  <div className="pc-storepick__list">
                    {(stores.data?.results ?? []).slice(0, 6).map((s) => (
                      <button key={s.id} type="button" className="chip" onClick={() => d.setStore({ id: s.id, name: s.name })}>{s.name}</button>
                    ))}
                    {stores.data && stores.data.results.length === 0 && <span className="small muted">No store matches.</span>}
                  </div>
                </div>
              )
            ) : placeRow('pickup', d.pickup, d.mode === 'send' ? 'Pickup · you' : 'Pickup · sender', 'Where should we collect it?')}
            <span className="pc-route__line" aria-hidden="true"><span /></span>
            {d.stops.map((s, i) => (
              <div key={i} className="pc-route__mid">
                {placeRow(i, s.lat ? s : null, `Stop ${i + 1}`, 'Choose the stop')}
                <div className="pc-route__tools">
                  <button type="button" className="icon-btn" aria-label={`Move stop ${i + 1} up`} disabled={i === 0}
                    onClick={() => d.setStops(d.stops.map((x, j) => (j === i - 1 ? d.stops[i]! : j === i ? d.stops[i - 1]! : x)))}><Icon name="chevron" size={16} className="pc-up" /></button>
                  <button type="button" className="icon-btn" aria-label={`Move stop ${i + 1} down`} disabled={i === d.stops.length - 1}
                    onClick={() => d.setStops(d.stops.map((x, j) => (j === i + 1 ? d.stops[i]! : j === i ? d.stops[i + 1]! : x)))}><Icon name="chevron" size={16} /></button>
                  <button type="button" className="icon-btn" aria-label={`Remove stop ${i + 1}`} onClick={() => d.setStops(d.stops.filter((_, j) => j !== i))}><Icon name="close" size={16} /></button>
                </div>
              </div>
            ))}
            {d.stops.length > 0 && <span className="pc-route__line" aria-hidden="true"><span /></span>}
            {placeRow('drop', d.drop, d.mode === 'send' ? 'Drop · recipient' : 'Drop · you', 'Where should it go?')}
          </div>
          {canStop && (
            <button type="button" className="link-btn small" onClick={() => { d.setStops([...d.stops, { label: '', address: '', lat: 0, lng: 0, name: '', phone: '' }]); setPicker(d.stops.length); }}>
              + Add another stop
            </button>
          )}
          {q && <p className="small muted">About {q.distanceKm} km{q.stops ? ` with ${q.stops} stop${q.stops > 1 ? 's' : ''}` : ''} · estimated from straight-line distance (no road routing yet)</p>}

          {d.mode === 'send' && recipients.length > 0 && (
            <div className="pc-recips" aria-label="Saved recipients">
              {recipients.slice(0, 6).map((r) => <button key={r.id} type="button" className="chip" onClick={() => d.applyRecipient(r)}><Icon name="user" size={14} /> {r.label || r.name}</button>)}
            </div>
          )}
          {d.mode === 'receive' && <ContactFields who="Sender" prefix="pc-sender" value={d.sender} onChange={d.setSender} />}
          {d.mode === 'send' && (
            <details className="pc-me">
              <summary>Sender: {d.sender.name || 'you'}{d.sender.phone ? ` · ${d.sender.phone}` : ''}</summary>
              <ContactFields who="Sender" prefix="pc-sender" value={d.sender} onChange={d.setSender} />
            </details>
          )}
          {d.mode === 'store_pickup' && (
            <label className="pc-field pc-field--wide"><span>Order / bill reference at the store</span>
              <input value={d.storeReference} maxLength={80} onChange={(e) => d.setStoreReference(e.target.value)} placeholder="e.g. Bill #4521 · paid at the counter" />
              <em className="small muted">Click. collects an item you’ve already arranged with the store. Paying the store for the item isn’t part of this booking.</em>
            </label>
          )}
          {d.mode === 'send' ? (
            <>
              <ContactFields who="Recipient" prefix="pc-recipient" value={d.recipient} onChange={d.setRecipient} alt />
              <label className="pc-check"><input type="checkbox" checked={saveRecipient} onChange={(e) => setSaveRecipient(e.target.checked)} /> Save this recipient</label>
            </>
          ) : (
            <details className="pc-me"><summary>Delivered to: {d.recipient.name || 'you'}{d.recipient.phone ? ` · ${d.recipient.phone}` : ''}</summary>
              <ContactFields who="Receiver" prefix="pc-recipient" value={d.recipient} onChange={d.setRecipient} alt /></details>
          )}
        </div>
      </div>

      {/* 2. Package */}
      <div className="pc-step">
        <span className="pc-step__n" aria-hidden="true">2</span>
        <div className="pc-step__body">
          <h3>What’s inside?</h3>
          <div className="pc-cats" role="radiogroup" aria-label="Contents">
            {options?.categories.map((c) => (
              <button key={c.code} type="button" role="radio" aria-checked={d.pkg.category === c.code} disabled={!c.allowed}
                className={`pc-cat${c.allowed ? '' : ' is-off'}`} onClick={() => d.setPkg((p) => ({ ...p, category: c.code }))} title={c.note || undefined}>
                <Icon name={(c.icon as never) || 'parcel'} size={18} /><span>{c.label}</span>{!c.allowed && <em>Not accepted</em>}
              </button>
            ))}
          </div>
          <div className="pc-sizes" role="radiogroup" aria-label="Package size">
            {options?.sizes.map((s) => (
              <button key={s.code} type="button" role="radio" aria-checked={d.pkg.size === s.code} className="pc-size" onClick={() => d.setPkg((p) => ({ ...p, size: s.code }))}>
                <span className={`pc-size__box pc-size__box--${s.code}`} aria-hidden="true" />
                <strong>{s.label}</strong><span className="small muted">{s.maxKg ? `Up to ${s.maxKg} kg` : s.hint}</span>
              </button>
            ))}
          </div>
          <div className="pc-weight">
            <span className="small">Approximate weight</span>
            <div className="pc-chips">
              {WEIGHTS.map((w) => <button key={w} type="button" className="chip" aria-pressed={d.pkg.weightKg === w} onClick={() => d.setPkg((p) => ({ ...p, weightKg: w }))}>{Number(w) < 1 ? '< 1' : `≤ ${w}`} kg</button>)}
              <label className="pc-inline"><span className="sr-only">Weight in kg</span>
                <input type="number" min={0.1} step={0.1} max={5000} inputMode="decimal" value={d.pkg.weightKg ?? ''} placeholder="kg"
                  onChange={(e) => d.setPkg((p) => ({ ...p, weightKg: e.target.value }))} /> kg</label>
            </div>
          </div>
          <details className="pc-dims" open={d.pkg.size === 'custom'}>
            <summary className="small">{d.pkg.size === 'custom' ? 'Dimensions (needed for custom size)' : 'Dimensions (optional)'}</summary>
            <div className="pc-dims__row">
              {(['lengthCm', 'widthCm', 'heightCm'] as const).map((k) => (
                <label key={k} className="pc-field"><span>{k === 'lengthCm' ? 'Length' : k === 'widthCm' ? 'Width' : 'Height'} (cm)</span>
                  <input type="number" min={1} max={600} inputMode="numeric" value={d.pkg[k] ?? ''}
                    onChange={(e) => d.setPkg((p) => ({ ...p, [k]: e.target.value ? Number(e.target.value) : null }))} /></label>
              ))}
            </div>
          </details>
          {options?.categories.find((c) => c.code === d.pkg.category)?.requiresValue && (
            <label className="pc-field"><span>Item value (₹), needed for this kind of item</span>
              <input type="number" min={1} inputMode="decimal" value={d.pkg.declaredValue ?? ''} onChange={(e) => d.setPkg((p) => ({ ...p, declaredValue: e.target.value || null }))} /></label>
          )}
          <label className="pc-field pc-field--wide"><span>Notes for the partner (optional)</span>
            <input value={d.pkg.notes ?? ''} maxLength={300} onChange={(e) => d.setPkg((p) => ({ ...p, notes: e.target.value }))} placeholder="Fragile, keep upright…" /></label>
          {q?.packageProblem && d.pkgReady && <p className="pc-err" role="alert">{q.packageProblem}</p>}
          {options && options.rules.length > 0 && (
            <div className="pc-rules">
              <strong className="small">Package rules</strong>
              <ul>{options.rules.filter((r) => r.kind === 'rule').map((r) => <li key={r.text} className="small">{r.text}</li>)}</ul>
              <strong className="small">Not accepted</strong>
              <ul className="pc-rules__no">{options.rules.filter((r) => r.kind === 'prohibited').map((r) => <li key={r.text} className="small">{r.text}</li>)}</ul>
              <label className="pc-check"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
                I’ve declared the contents correctly and the package follows these rules.</label>
            </div>
          )}
        </div>
      </div>

      {/* 3. Service & vehicle */}
      <div className="pc-step">
        <span className="pc-step__n" aria-hidden="true">3</span>
        <div className="pc-step__body">
          <h3>Delivery type &amp; vehicle</h3>
          {!d.placeReady ? <p className="small muted">Choose the pickup and drop to see what’s available.</p>
            : d.quote.isError ? <p className="pc-err" role="alert">{d.quote.error instanceof ApiError ? d.quote.error.message : 'Couldn’t get prices. Check your connection.'}</p>
            : !q ? <p className="small muted">Checking what’s available…</p> : (
              <>
                <div className="pc-services" role="radiogroup" aria-label="Delivery type">
                  {q.services.map((s) => (
                    <button key={s.code} type="button" role="radio" aria-checked={(d.service || q.service) === s.code} disabled={!s.available}
                      className={`pc-svc pc-svc--${s.code}${s.available ? '' : ' is-off'}`} onClick={() => { d.setService(s.code); if (s.code !== 'scheduled') d.setScheduledFor(null); }}>
                      <strong>{s.name}</strong>
                      <span className="small">{s.available ? (s.label || s.description) : s.reason}</span>
                    </button>
                  ))}
                </div>
                {svc?.code === 'scheduled' && (svc.slots?.length ?? 0) > 0 && (
                  <label className="pc-field"><span>Pickup time</span>
                    <select value={d.scheduledFor ?? ''} onChange={(e) => d.setScheduledFor(e.target.value || null)}>
                      <option value="">Choose a time</option>
                      {svc.slots!.map((s) => <option key={s.start} value={s.start}>{s.label}</option>)}
                    </select></label>
                )}
                <div className="pc-vehicles" role="radiogroup" aria-label="Vehicle">
                  {q.vehicles.map((v) => (
                    <button key={v.code} type="button" role="radio" aria-checked={d.vehicle === v.code} disabled={!v.available || !v.fare}
                      className={`pc-veh${v.available && v.fare ? '' : ' is-off'}`} onClick={() => d.setVehicle(v.code)}>
                      <span className="pc-veh__icon"><Icon name={vehicleIcon(v.code, v.icon)} size={22} /></span>
                      <strong>{v.name}</strong>
                      <span className="small muted">Up to {v.capacity.maxKg} kg · {v.capacity.maxCm.join('×')} cm</span>
                      {v.fare ? <span className="pc-veh__price">{formatMoney(v.fare.total)}<em>est.</em></span> : <span className="small pc-veh__why">{v.reason}</span>}
                      {v.fare && v.pickupEtaMinutes != null && <span className="small">Pickup in ~{v.pickupEtaMinutes} min</span>}
                    </button>
                  ))}
                </div>
              </>
            )}
        </div>
      </div>

      {/* 4. Estimate */}
      {veh?.fare && (
        <div className="pc-estimate" aria-live="polite">
          <div className="pc-estimate__head"><span className="pc-kicker">Estimated · confirmed when you book</span><strong>{formatMoney(veh.fare.total)}</strong></div>
          <dl className="pc-bill">
            <div><dt>Base fare</dt><dd>{formatMoney(veh.fare.base)}</dd></div>
            <div><dt>Distance ({q?.distanceKm} km)</dt><dd>{formatMoney(veh.fare.distance)}</dd></div>
            {Number(veh.fare.service) !== 0 && <div><dt>{svc?.name} service</dt><dd>{Number(veh.fare.service) < 0 ? '−' : ''}{formatMoney(Math.abs(Number(veh.fare.service)))}</dd></div>}
            {Number(veh.fare.stops) > 0 && <div><dt>Extra stops</dt><dd>{formatMoney(veh.fare.stops)}</dd></div>}
            <div><dt>Taxes</dt><dd>{formatMoney(veh.fare.tax)}</dd></div>
            {Number(veh.fare.discount) > 0 && <div><dt>Offer</dt><dd>−{formatMoney(veh.fare.discount)}</dd></div>}
          </dl>
          {veh.window && <p className="small">{veh.window}</p>}
          <Button block disabled={!ready} onClick={() => (status === 'authenticated' ? setReview(true) : navigate('/login?next=/parcels'))}>Review &amp; continue to payment</Button>
          {!ready && <p className="small muted">{q?.packageProblem ? q.packageProblem : !contactsOk ? 'Add names and valid phone numbers.' : !confirmed ? 'Confirm the package rules.' : needsTime ? 'Choose a pickup time.' : ''}</p>}
        </div>
      )}

      <LocationPicker open={picker !== null && !mapPick} title={picker === 'pickup' ? 'Pickup location' : picker === 'drop' ? 'Drop location' : 'Stop location'}
        allowCurrent onClose={() => { if (typeof picker === 'number' && !d.stops[picker]?.lat) d.setStops(d.stops.filter((s) => s.lat)); setPicker(null); }}
        onSelect={(p) => picker !== null && setTarget(picker, p)}
        onPickOnMap={() => { if (picker !== null) setMapPick({ target: picker, point: null }); }} />

      <Sheet open={!!mapPick} onClose={() => { setMapPick(null); setPicker(null); }} label="Pick on map">
        {mapPick && (
          <div className="pc-mapsheet">
            <h2>Tap the map to set the {mapPick.target === 'pickup' ? 'pickup' : mapPick.target === 'drop' ? 'drop' : 'stop'}</h2>
            <Suspense fallback={<div className="pc-map pc-map--loading">Loading map…</div>}>
              <RideMap className="pc-map" pickup={mapPick.target === 'pickup' && mapPick.point ? { label: 'Pin', address: '', ...mapPick.point } : d.pickup}
                drop={mapPick.target === 'drop' && mapPick.point ? { label: 'Pin', address: '', ...mapPick.point } : d.drop}
                center={d.mine} onPick={(p) => setMapPick({ ...mapPick, point: p })} />
            </Suspense>
            <Button block disabled={!mapPick.point} onClick={() => mapPick.point && setTarget(mapPick.target, {
              label: 'Pinned location', address: `${mapPick.point.lat.toFixed(5)}, ${mapPick.point.lng.toFixed(5)}`, ...mapPick.point })}>Use this spot</Button>
          </div>
        )}
      </Sheet>

      <Sheet open={review && !!veh} onClose={() => setReview(false)} label="Parcel summary">
        {veh?.fare && q && (
          <div className="pc-review">
            <h2>Parcel summary</h2>
            <dl className="pc-sum">
              <div><dt>From</dt><dd>{d.mode === 'store_pickup' ? d.store?.name : d.pickup?.label}<span className="small muted">{d.mode === 'store_pickup' ? d.storeReference : d.sender.name}</span></dd></div>
              {d.stops.map((s, i) => <div key={i}><dt>Stop {i + 1}</dt><dd>{s.label}</dd></div>)}
              <div><dt>To</dt><dd>{d.drop?.label}<span className="small muted">{d.recipient.name} · ••••• {d.recipient.phone.replace(/\D/g, '').slice(-4)}</span></dd></div>
              <div><dt>Package</dt><dd>{options?.categories.find((c) => c.code === d.pkg.category)?.label} · {d.pkg.size} · {d.pkg.weightKg} kg</dd></div>
              <div><dt>Service</dt><dd>{svc?.name}<span className="small muted">{veh.window}</span></dd></div>
              <div><dt>Vehicle</dt><dd>{veh.name}</dd></div>
              <div><dt>Price</dt><dd><strong>{formatMoney(veh.fare.total)}</strong><span className="small muted">Estimated; the server confirms it when you book</span></dd></div>
            </dl>
            <fieldset className="pc-pay"><legend className="small">Payment</legend>
              {q.paymentMethods.includes('wallet') && <WalletOption total={veh.fare.total} currency="INR" checked={payment === 'wallet'} onSelect={() => setPayment('wallet')} />}
              {q.paymentMethods.includes('cash') && (
                <label className="option"><input type="radio" name="pc-pay" checked={payment === 'cash'} onChange={() => setPayment('cash')} />
                  <div><strong>Cash to the partner at pickup</strong><div className="small muted">Hand {formatMoney(veh.fare.total)} to the partner when they collect the parcel.</div></div></label>
              )}
              <p className="small muted"><Icon name="shield" size={14} /> Card and UPI payments aren’t connected yet.{q.cancellationFee && Number(q.cancellationFee) > 0 ? ` Free cancellation until a partner is assigned; ₹${Number(q.cancellationFee).toFixed(0)} after that (wallet payments).` : ''}</p>
            </fieldset>
            <Button block loading={book.isPending} onClick={() => book.mutate()}>Confirm and book · {formatMoney(veh.fare.total)}</Button>
          </div>
        )}
      </Sheet>
    </section>
  );
}
