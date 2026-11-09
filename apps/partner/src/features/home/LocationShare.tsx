import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Button, Icon } from '@click/ui';
import type { PartnerHome } from '@click/api';
import { api } from '../../lib/api';
import { timeAgo } from '../../lib/money';
import { HOME_KEY } from './queries';

const REPORT_EVERY_MS = 20_000;
type Perm = 'unknown' | 'prompt' | 'granted' | 'denied' | 'unsupported';

/**
 * Live location for workspaces that need it (drivers). It runs only while the partner is online, only after they
 * choose to share, only while the app is open and visible, and stops the moment they go offline. Business partners
 * never see this: their saved address is used instead.
 */
export function LocationShare({ home }: { home: PartnerHome }) {
  const needed = home.workspace.location === 'live' && home.workspace.state === 'live' && home.availability.isOn;
  const qc = useQueryClient();
  const [perm, setPerm] = useState<Perm>(() => (typeof navigator !== 'undefined' && 'geolocation' in navigator ? 'unknown' : 'unsupported'));
  const [sharing, setSharing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const last = useRef(0);

  useEffect(() => {
    if (perm !== 'unknown') return;
    navigator.permissions?.query({ name: 'geolocation' as PermissionName })
      .then((s) => { setPerm(s.state as Perm); s.onchange = () => setPerm(s.state as Perm); })
      .catch(() => setPerm('prompt'));
  }, [perm]);

  // Resume automatically only when the partner already granted permission earlier.
  useEffect(() => { if (needed && perm === 'granted') setSharing(true); }, [needed, perm]);
  useEffect(() => { if (!needed) setSharing(false); }, [needed]);

  useEffect(() => {
    if (!sharing || !needed) return;
    const id = navigator.geolocation.watchPosition(
      (pos) => {
        setPerm('granted');
        setError(null);
        if (document.hidden || Date.now() - last.current < REPORT_EVERY_MS) return;
        last.current = Date.now();
        api.partner.reportDriverLocation(pos.coords.latitude, pos.coords.longitude)
          .then(() => qc.invalidateQueries({ queryKey: HOME_KEY }))
          .catch(() => setError('Couldn’t send your location to Click. We’ll keep trying.'));
      },
      (err) => {
        if (err.code === err.PERMISSION_DENIED) { setPerm('denied'); setSharing(false); }
        else setError('Your location isn’t available right now.');
      },
      { enableHighAccuracy: true, maximumAge: 10_000, timeout: 30_000 },
    );
    return () => navigator.geolocation.clearWatch(id);
  }, [sharing, needed, qc]);

  if (!needed) return null;
  const live = home.workspace.liveLocation;
  if (sharing && live?.fresh) {
    return (
      <p className="loc loc--ok small" role="status">
        <Icon name="locate" size={16} /> Sharing your location with Click while you’re online · updated {timeAgo(live.reportedAt)}
      </p>
    );
  }
  return (
    <div className="loc" role="region" aria-label="Location for ride requests">
      <Icon name="pin" size={20} />
      <div className="loc__text">
        <p className="loc__title">{perm === 'denied' ? 'Location is blocked' : 'Share your location to get ride requests'}</p>
        <p className="small">
          {perm === 'denied'
            ? 'Click matches riders to the nearest online drivers, so it needs your location while you’re online. Allow location for this site in your browser settings.'
            : perm === 'unsupported'
              ? 'This browser can’t share location, so Click can’t match you to nearby riders here.'
              : 'Click uses it only while you’re online, to send you requests nearby and to show riders where you are during a trip. It stops when you go offline.'}
        </p>
        {error && <p className="small loc__error" role="alert">{error}</p>}
      </div>
      {perm !== 'denied' && perm !== 'unsupported' && !sharing && (
        <Button size="sm" onClick={() => setSharing(true)}>Share location</Button>
      )}
    </div>
  );
}
