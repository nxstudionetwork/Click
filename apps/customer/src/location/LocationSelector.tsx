import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import type { AddressInput } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, Icon, Sheet } from '../components/ui';
import { AddressForm } from '../features/addresses/AddressForm';
import { useDeliveryLocation } from './LocationProvider';

export const formatAddressLine = (a: { line1: string; line2?: string; city: string }) =>
  [a.line1, a.line2, a.city].filter(Boolean).join(', ');

/** Short "area, city" line for the header (the full address is in the selector). */
export const formatArea = (a: { line2?: string; city: string; state?: string }) =>
  [a.line2 || a.city, a.line2 ? a.city : a.state].filter(Boolean).join(', ');

type Mode = 'list' | 'add';
type Geo = { state: 'idle' | 'locating' | 'denied' | 'unavailable' } | { state: 'found'; lat: number; lng: number; accuracy: number };

export function LocationSelector({ compact = false }: { compact?: boolean }) {
  const { status, user } = useAuth();
  const { addresses, selected, select, isLoading } = useDeliveryLocation();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<Mode>('list');
  const [geo, setGeo] = useState<Geo>({ state: 'idle' });
  const navigate = useNavigate();
  const close = () => { setOpen(false); setMode('list'); setGeo({ state: 'idle' }); };

  const label = status !== 'authenticated' ? 'Set location' : isLoading ? 'Locating…' : selected ? selected.label : 'Add a location';
  const detail = selected ? formatArea(selected) : status === 'authenticated' ? 'Choose where you are' : 'Sign in to save places';

  function locateMe() {
    if (!('geolocation' in navigator)) { setGeo({ state: 'unavailable' }); return; }
    setGeo({ state: 'locating' });
    navigator.geolocation.getCurrentPosition(
      (p) => { setGeo({ state: 'found', lat: p.coords.latitude, lng: p.coords.longitude, accuracy: p.coords.accuracy }); setMode('add'); },
      (e) => setGeo({ state: e.code === e.PERMISSION_DENIED ? 'denied' : 'unavailable' }),
      { enableHighAccuracy: true, timeout: 12_000, maximumAge: 60_000 },
    );
  }

  const initial: Partial<AddressInput> | undefined = geo.state === 'found'
    ? { latitude: geo.lat.toFixed(6), longitude: geo.lng.toFixed(6), label: 'other' }
    : undefined;

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
          <span className="location__label">{label}<span className="location__detail"> · {detail}</span></span>
        </span>
        <Icon name="chevron" size={16} className="location__chev" />
      </button>

      <Sheet open={open} onClose={close} label="Choose your location">
        <div className="stack loc-sheet">
          <div className="spread">
            <h2>{mode === 'add' ? 'Add a location' : 'Choose location'}</h2>
            <button className="icon-btn" aria-label="Close" onClick={close}><Icon name="close" /></button>
          </div>

          {mode === 'add' ? (
            <AddressForm
              key={geo.state === 'found' ? `${geo.lat},${geo.lng}` : 'manual'}
              defaultName={user?.fullName} defaultPhone={user?.phone ?? ''} initial={initial}
              pinAccuracy={geo.state === 'found' ? geo.accuracy : null} submitLabel="Save and deliver here"
              onSaved={(a) => { select(a.id); close(); }} onCancel={() => { setMode('list'); setGeo({ state: 'idle' }); }}
            />
          ) : (
            <>
              <button type="button" className="loc-current" onClick={locateMe} disabled={geo.state === 'locating'}>
                <span className="loc-current__icon"><Icon name="locate" /></span>
                <span><strong>{geo.state === 'locating' ? 'Finding you…' : 'Use current location'}</strong>
                  <span className="small muted">Pin this spot, then add the address details</span></span>
              </button>
              {geo.state === 'denied' && <p className="loc-warn" role="alert">Location access is blocked. Allow it in your browser settings, or choose a saved place or add one below.</p>}
              {geo.state === 'unavailable' && <p className="loc-warn" role="alert">We couldn’t get your location right now. Choose a saved place or add the address manually.</p>}

              <div className="stack" style={{ gap: 'var(--s-2)' }} role="radiogroup" aria-label="Saved locations">
                <span className="loc-heading">Saved locations</span>
                {addresses.length === 0 && <p className="muted small">No saved locations yet.</p>}
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
              <div className="row" style={{ flexWrap: 'wrap' }}>
                <Button onClick={() => setMode('add')}><Icon name="plus" size={18} /> Add new location</Button>
                <Link to="/account/addresses" className="btn btn--ghost" onClick={close}>Manage</Link>
              </div>
            </>
          )}
        </div>
      </Sheet>
    </>
  );
}
