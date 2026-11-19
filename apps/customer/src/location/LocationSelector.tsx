import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError, type GeoPlace } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { Icon, Sheet } from '../components/ui';
import { addressesKey } from '../features/addresses/useAddresses';
import { api } from '../lib/api';
import { useDeliveryLocation } from './LocationProvider';

export const formatAddressLine = (a: { line1: string; line2?: string; city: string }) =>
  [a.line1, a.line2, a.city].filter(Boolean).join(', ');

/** Short "area, city" line for the header (the full address is in the selector). */
export const formatArea = (a: { line2?: string; city: string; state?: string }) =>
  [a.line2 || a.city, a.line2 ? a.city : a.state].filter(Boolean).join(', ');

type Locate = { state: 'idle' } | { state: 'locating' } | { state: 'found'; place: GeoPlace } | { state: 'error'; message: string };

/**
 * The app-wide location, chosen on Home. Every service (Food, Groceries, Shop, Pharma, Services…) uses it; checkout
 * only confirms it and lets the customer change it there. Choices: a saved address, the device's current location
 * (turned into a street address and saved in one tap), or a new address.
 */
export function LocationSelector({ compact = false }: { compact?: boolean }) {
  const { status, user } = useAuth();
  const { addresses, selected, select, isLoading } = useDeliveryLocation();
  const [open, setOpen] = useState(false);
  const [locate, setLocate] = useState<Locate>({ state: 'idle' });
  const navigate = useNavigate();
  const qc = useQueryClient();

  const label = status !== 'authenticated' ? 'Set location' : isLoading ? 'Locating…' : selected ? selected.label : 'Choose a location';
  const detail = selected ? formatArea(selected) : status === 'authenticated' ? 'Pick or add an address' : 'Sign in to use your addresses';

  function useCurrent() {
    if (!('geolocation' in navigator)) { setLocate({ state: 'error', message: 'This device can’t share its location. Add the address instead.' }); return; }
    setLocate({ state: 'locating' });
    navigator.geolocation.getCurrentPosition(async (p) => {
      const at = { lat: +p.coords.latitude.toFixed(6), lng: +p.coords.longitude.toFixed(6) };
      const r = await api.money.geo.reverse(at).catch(() => null);
      if (r?.place) setLocate({ state: 'found', place: r.place });
      else setLocate({ state: 'error', message: 'We found you but couldn’t read the street address. Add it instead; it takes a few seconds.' });
    }, (e) => setLocate({ state: 'error', message: e.code === e.PERMISSION_DENIED
      ? 'Location access is blocked for Click. Allow it in your browser settings, or add the address.' : 'We couldn’t get your location. Try again or add the address.' }),
    { enableHighAccuracy: true, timeout: 12_000, maximumAge: 60_000 });
  }

  // Saving the current location creates a real saved address (the server validates it), then makes it active.
  const save = useMutation({
    mutationFn: (p: GeoPlace) => api.customer.addresses.create({
      label: 'other', recipientName: user?.fullName ?? '', phone: user?.phone ?? '',
      line1: p.parts?.street || p.label, line2: [p.parts?.street ? p.label : '', p.parts?.locality].filter(Boolean).join(', '), landmark: '',
      city: p.parts?.city ?? '', state: p.parts?.state ?? '', postalCode: p.parts?.postalCode ?? '', country: 'IN', isDefault: false,
      latitude: String(p.lat), longitude: String(p.lng),
    }),
    onSuccess: (a) => { qc.invalidateQueries({ queryKey: addressesKey }); select(a.id); setLocate({ state: 'idle' }); setOpen(false); },
  });
  const incomplete = locate.state === 'found' && (!locate.place.parts?.city || !locate.place.parts?.postalCode);
  const full = addresses.length >= 5;

  const close = () => { setOpen(false); setLocate({ state: 'idle' }); save.reset(); };

  return (
    <>
      <button
        type="button" className={`location ${compact ? 'location--compact' : ''}`}
        onClick={() => (status === 'authenticated' ? setOpen(true) : navigate('/login'))}
        aria-label={`Delivering to ${selected ? `${selected.label}, ${formatAddressLine(selected)}` : label}. Change location`}
      >
        <span className="location__pin"><Icon name="pin" size={18} /></span>
        <span className="location__text">
          <span className="location__eyebrow">Delivering to</span>
          <span className="location__label"><span className="location__name">{label}</span><span className="location__detail"> · {detail}</span></span>
        </span>
        <Icon name="chevron" size={16} className="location__chev" />
      </button>

      <Sheet open={open} onClose={close} label="Choose your location">
        <div className="stack loc-sheet">
          <div className="spread">
            <div><h2>Your location</h2><p className="small muted">Used across Click. You can still change it at checkout.</p></div>
            <button className="icon-btn" aria-label="Close" onClick={close}><Icon name="close" /></button>
          </div>

          <div className="loc-actions">
            <button type="button" className="loc-action loc-action--live" onClick={useCurrent} disabled={locate.state === 'locating' || save.isPending}>
              <span className="loc-action__icon"><Icon name="locate" size={18} /></span>
              <span><strong>{locate.state === 'locating' ? 'Finding you…' : 'Use my current location'}</strong><small>Find the street you’re on</small></span>
            </button>
            <Link to="/account/addresses?new=1" className="loc-action" onClick={close}>
              <span className="loc-action__icon"><Icon name="plus" size={18} /></span>
              <span><strong>Add a new address</strong><small>Home, work or anywhere</small></span>
            </Link>
          </div>

          {locate.state === 'found' && (
            <div className="loc-found" role="status">
              <span className="loc-option__icon"><Icon name="locate" size={18} /></span>
              <span className="loc-option__text"><strong>{locate.place.label}</strong><span className="small muted">{locate.place.address}</span></span>
              {incomplete || full ? (
                <Link to="/account/addresses?new=1" className="btn btn--outline btn--sm" onClick={close}>{full ? 'Manage' : 'Complete'}</Link>
              ) : (
                <button type="button" className="btn btn--primary btn--sm" disabled={save.isPending} onClick={() => save.mutate(locate.place)}>{save.isPending ? 'Saving…' : 'Deliver here'}</button>
              )}
              {full && <p className="small muted loc-found__note">You have 5 saved addresses, the most allowed. Remove one in Addresses to add this place.</p>}
              {incomplete && !full && <p className="small muted loc-found__note">We need the PIN code and city to deliver here. Complete the address in a few seconds.</p>}
              {save.error && <p className="small loc-found__note" role="alert" style={{ color: 'var(--c-danger)' }}>{save.error instanceof ApiError ? save.error.message : 'Couldn’t save this place. Try again.'}</p>}
            </div>
          )}
          {locate.state === 'error' && <p className="loc-warn" role="alert">{locate.message}</p>}

          <h3 className="loc-sheet__h">Saved addresses</h3>
          {addresses.length === 0 ? (
            <p className="small muted">No saved addresses yet. Use your current location or add one.</p>
          ) : (
            <div className="stack" style={{ gap: 'var(--s-2)' }} role="radiogroup" aria-label="Saved addresses">
              {addresses.map((a) => (
                <label key={a.id} className={`loc-option ${selected?.id === a.id ? 'loc-option--on' : ''}`}>
                  <input type="radio" name="loc" className="visually-hidden" checked={selected?.id === a.id} onChange={() => { select(a.id); close(); }} />
                  <span className="loc-option__icon"><Icon name={a.label === 'work' ? 'briefcase' : a.label === 'home' ? 'home' : 'pin'} size={18} /></span>
                  <span className="loc-option__text">
                    <strong>{a.label}{a.isDefault && <span className="badge" style={{ marginLeft: 6 }}>Default</span>}</strong>
                    <span className="small muted">{formatAddressLine(a)}</span>
                  </span>
                  {selected?.id === a.id && <Icon name="check" size={18} className="loc-option__check" />}
                </label>
              ))}
            </div>
          )}
          <Link to="/account/addresses" className="small loc-sheet__manage" onClick={close}>Manage addresses</Link>
        </div>
      </Sheet>
    </>
  );
}
