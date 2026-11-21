import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { RidePlace, RidePlaceResult } from '@click/api';
import { Icon, Sheet, type IconName } from '../../components/ui';
import { api } from '../../lib/api';

const KIND: Record<RidePlaceResult['kind'], { icon: IconName; label: string }> = {
  saved: { icon: 'pin', label: 'Saved' }, recent: { icon: 'history', label: 'Recent' }, place: { icon: 'store', label: 'On Click.' },
  search: { icon: 'compass', label: '' },
};

type Geo = 'idle' | 'locating' | 'denied' | 'unavailable';

/**
 * Pickup / drop / stop chooser: current location (real device position, turned into a street address), search over
 * saved addresses, recent ride places, Click places and every address in India (maps search, nearest first), or a pin
 * placed on the map.
 */
export function LocationPicker({ open, title, allowCurrent, initialQuery = '', near, onClose, onSelect, onPickOnMap }: {
  open: boolean; title: string; allowCurrent: boolean; initialQuery?: string; near?: { lat: number; lng: number } | null;
  onClose: () => void; onSelect: (p: RidePlace) => void; onPickOnMap: () => void;
}) {
  const [q, setQ] = useState('');
  useEffect(() => { if (open && initialQuery) setQ(initialQuery); }, [open, initialQuery]);
  const [debounced, setDebounced] = useState('');
  const [geo, setGeo] = useState<Geo>('idle');
  useEffect(() => { const t = setTimeout(() => setDebounced(q.trim()), 250); return () => clearTimeout(t); }, [q]);
  useEffect(() => { if (!open) { setQ(''); setGeo('idle'); } }, [open]);
  const nearKey = near ? `${near.lat.toFixed(2)},${near.lng.toFixed(2)}` : '';
  const places = useQuery({ queryKey: ['rides', 'places', debounced, nearKey], queryFn: () => api.customer.rides.places(debounced, near), enabled: open, staleTime: 30_000,
    placeholderData: (prev) => prev });

  function current() {
    if (!('geolocation' in navigator)) { setGeo('unavailable'); return; }
    setGeo('locating');
    navigator.geolocation.getCurrentPosition(
      async (p) => {
        const at = { lat: +p.coords.latitude.toFixed(6), lng: +p.coords.longitude.toFixed(6) };
        // Turn the position into a street address the driver can read; the exact coordinates are kept either way.
        const found = await api.money.geo.reverse(at).then((r) => r.place).catch(() => null);
        setGeo('idle');
        onSelect({ label: found?.label ?? 'Current location', address: found?.address ?? `Your location (within about ${Math.round(p.coords.accuracy)} m)`, ...at });
      },
      (e) => setGeo(e.code === e.PERMISSION_DENIED ? 'denied' : 'unavailable'),
      { enableHighAccuracy: true, timeout: 12_000, maximumAge: 30_000 },
    );
  }

  const results = places.data?.results ?? [];
  return (
    <Sheet open={open} onClose={onClose} label={title}>
      <div className="lpick">
        <div className="spread"><h2>{title}</h2><button className="icon-btn" aria-label="Close" onClick={onClose}><Icon name="close" /></button></div>
        <div className="lpick__search">
          <Icon name="search" size={18} />
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search an area, landmark or saved place" aria-label="Search location" />
          {q && <button className="gsearch__tool" aria-label="Clear text" onClick={() => setQ('')}><Icon name="close" size={16} /></button>}
        </div>
        <div className="lpick__actions">
          {allowCurrent && (
            <button type="button" className="lpick__action" onClick={current} disabled={geo === 'locating'}>
              <span className="lpick__icon lpick__icon--live"><Icon name="locate" size={18} /></span>
              <span><strong>{geo === 'locating' ? 'Finding you…' : 'Use my current location'}</strong><span>Uses your device’s location</span></span>
            </button>
          )}
          <button type="button" className="lpick__action" onClick={onPickOnMap}>
            <span className="lpick__icon"><Icon name="pin" size={18} /></span>
            <span><strong>Pin on map</strong><span>Move the map to the exact spot</span></span>
          </button>
        </div>
        {geo === 'denied' && <p className="loc-warn" role="alert">Location access is blocked. Search for the place or choose it on the map instead.</p>}
        {geo === 'unavailable' && <p className="loc-warn" role="alert">We couldn’t get your location. Search for the place or choose it on the map.</p>}
        <ul className="lpick__results" aria-live="polite">
          {places.isPending && Array.from({ length: 3 }, (_, i) => <li key={i}><span className="skeleton" style={{ display: 'block', height: 52, borderRadius: 12 }} /></li>)}
          {places.isError && <li className="muted small">Couldn’t load places. <button className="btn btn--ghost btn--sm" onClick={() => places.refetch()}>Retry</button></li>}
          {places.isSuccess && results.length === 0 && (
            <li className="muted small">{debounced ? (debounced.length < 3 ? 'Keep typing to search every address in India.' : 'No matching places. Try another spelling, a nearby landmark, or place a pin on the map.') : 'Your saved addresses and recent ride places appear here. Type to search any address, landmark or area.'}</li>
          )}
          {results.map((r) => (
            <li key={`${r.kind}-${r.lat}-${r.lng}`}>
              <button type="button" className="lpick__result" onClick={() => onSelect({ label: r.label, address: r.address, lat: r.lat, lng: r.lng })}>
                <span className="lpick__icon"><Icon name={KIND[r.kind].icon} size={16} /></span>
                <span className="lpick__text"><strong>{r.label}</strong><span>{r.address}</span></span>
                {KIND[r.kind].label && <span className="lpick__kind">{KIND[r.kind].label}</span>}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </Sheet>
  );
}
