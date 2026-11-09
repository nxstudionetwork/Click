import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type SavedRecipient } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, EmptyState, ErrorState, Icon, Sheet, Skeleton, useConfirm, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { MissionCard } from '../features/parcels/MissionCard';
import { Panel, ParcelRow, RouteGlyph, RouteLine, StatusChip, vehicleIcon, when } from '../features/parcels/parts';
import { PHONE, useParcelDraft } from '../features/parcels/useParcelDraft';
import { api } from '../lib/api';
import { LocationSelector } from '../location/LocationSelector';
import { useDeliveryLocation } from '../location/LocationProvider';

const recipientsKey = ['customer', 'parcels', 'recipients'] as const;

/**
 * Click. Parcel: a logistics command centre. Hero with the route idea, the Plan-a-delivery mission card (send,
 * receive, store pickup → route → package → service & vehicle → backend estimate → review & pay), then the
 * dashboard: active parcel, quick actions, tracking lookup, recent parcels, saved recipients and places, the delivery
 * services actually configured, and help for frequent senders.
 */
export function ParcelPage() {
  useThemeOverride('parcel');
  const { status } = useAuth();
  const authed = status === 'authenticated';
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const { point, addresses } = useDeliveryLocation();
  const d = useParcelDraft();
  const mission = useRef<HTMLDivElement>(null);
  const [trackRef, setTrackRef] = useState('');
  const [editing, setEditing] = useState<SavedRecipient | null>(null);

  const options = useQuery({ queryKey: ['parcels', 'options', point], queryFn: () => api.parcels.options(point), staleTime: 5 * 60_000 });
  const active = useQuery({ queryKey: ['customer', 'parcels', 'active'], queryFn: () => api.parcels.list('active'), enabled: authed, refetchInterval: 60_000 });
  const past = useQuery({ queryKey: ['customer', 'parcels', 'past'], queryFn: () => api.parcels.list('past'), enabled: authed });
  const recipients = useQuery({ queryKey: recipientsKey, queryFn: () => api.parcels.recipients.list(), enabled: authed });

  const goMission = () => mission.current?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });

  // Deep links: ?mode=receive, ?recipient=<id> (from Buddy), ?repeat=<parcel id>.
  useEffect(() => {
    const mode = params.get('mode');
    if (mode === 'send' || mode === 'receive' || mode === 'store_pickup') d.setMode(mode);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const rid = params.get('recipient');
    const r = rid && recipients.data?.find((x) => x.id === rid);
    if (r) { d.applyRecipient(r); params.delete('recipient'); setParams(params, { replace: true }); goMission(); }
  }, [recipients.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const startRepeat = (id: string) => api.parcels.repeat(id)
    .then((draft) => { d.loadDraft(draft); toast('Loaded your previous parcel. Check the details; the price is quoted again.'); goMission(); })
    .catch(() => toast('Couldn’t load that parcel.', 'error'));
  useEffect(() => {
    const id = params.get('repeat');
    if (!id || !authed) return;
    void startRepeat(id);
    params.delete('repeat'); setParams(params, { replace: true });
  }, [authed]); // eslint-disable-line react-hooks/exhaustive-deps

  const track = useMutation({
    mutationFn: () => api.parcels.track(trackRef),
    onSuccess: (r) => navigate(`/parcels/${r.id}`),
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t look that up.', 'error'),
  });
  const removeRecipient = useMutation({
    mutationFn: api.parcels.recipients.remove,
    onSuccess: () => qc.invalidateQueries({ queryKey: recipientsKey }),
  });
  const saveRecipient = useMutation({
    mutationFn: (r: SavedRecipient) => api.parcels.recipients.update(r.id, { name: r.name, phone: r.phone, altPhone: r.altPhone, label: r.label, instructions: r.instructions }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: recipientsKey }); setEditing(null); toast('Recipient saved'); },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t save.', 'error'),
  });

  const now = active.data?.results[0];
  const lastDone = past.data?.results.find((p) => p.status === 'delivered');
  const cov = options.data?.coverage;
  const quick = [
    { label: 'Send', icon: 'send' as const, run: () => { d.setMode('send'); goMission(); } },
    { label: 'Receive', icon: 'download' as const, run: () => { d.setMode('receive'); goMission(); } },
    { label: 'Store pickup', icon: 'store' as const, run: () => { d.setMode('store_pickup'); goMission(); } },
    { label: 'Schedule', icon: 'clock' as const, run: () => { d.setService('scheduled'); goMission(); } },
    { label: 'Track', icon: 'locate' as const, run: () => document.getElementById('pc-track-input')?.focus() },
    { label: 'Repeat', icon: 'history' as const, run: () => (lastDone ? void startRepeat(lastDone.id) : toast('Your delivered parcels will appear here to repeat.')) },
  ];

  return (
    <div className="pc-page" data-theme="parcel">
      <header className="pc-hero">
        <div className="pc-hero__text">
          <span className="pc-kicker">Click. Parcel</span>
          <h1>Parcel<span>.</span></h1>
          <p>Send it. Track it. Delivered.</p>
          <div className="pc-hero__cta">
            <Button onClick={() => { d.setMode('send'); goMission(); }}>Send a parcel</Button>
            {now && <Link to={`/parcels/${now.id}`} className="btn btn--outline">Track {now.number}</Link>}
          </div>
        </div>
        <div className="pc-hero__route">
          <RouteGlyph />
          <div className="pc-hero__labels"><span>Pickup</span><span>Transit</span><span>Drop</span></div>
          <p className="small muted">PIN-verified pickup and delivery · status from your partner’s confirmed steps</p>
        </div>
      </header>

      <div className="pc-where">
        <LocationSelector />
        {cov?.checked && !cov.available && <p className="pc-note pc-note--warn" role="status"><Icon name="alert" size={14} /> Click. Parcel doesn’t deliver around this location yet.</p>}
        {cov?.checked && cov.available && <p className="pc-note"><Icon name="check" size={14} /> Click. Parcel operates in {cov.area}.</p>}
        {authed && !point && addresses.length > 0 && <p className="pc-note"><Icon name="pin" size={14} /> Your selected address has no map pin; choose pickup and drop below.</p>}
      </div>

      {now && (
        <Link to={`/parcels/${now.id}`} className="pc-active" aria-label={`Active parcel ${now.number}: ${now.statusLabel}`}>
          <div className="pc-active__top"><span className="pc-kicker">Active parcel · {now.number}</span><StatusChip status={now.status} label={now.statusLabel} /></div>
          <RouteLine from={now.pickup.label} to={now.drop.label} />
          <div className="pc-active__foot small">
            <span><Icon name={vehicleIcon(now.vehicle.code)} size={14} /> {now.service.name} · {now.vehicle.name}</span>
            {now.deliverBy && <span>By {when(now.deliverBy)} (estimated)</span>}
            <span className="pc-active__go">Track <Icon name="right" size={14} /></span>
          </div>
        </Link>
      )}

      <div ref={mission} className="pc-mission-wrap">
        {options.isError ? <ErrorState error={options.error} onRetry={() => options.refetch()} /> : options.isPending ? <Skeleton height={420} radius={24} /> : (
          <MissionCard d={d} options={options.data} recipients={recipients.data ?? []} />
        )}
      </div>

      <nav className="pc-quick" aria-label="Quick actions">
        {quick.map((a) => <button key={a.label} type="button" className="pc-quick__btn" onClick={a.run}><span><Icon name={a.icon} size={20} /></span>{a.label}</button>)}
      </nav>

      <div className="pc-grid">
        <Panel title="Track a parcel" kicker="Tracking" id="pc-track">
          <form className="pc-trackform" onSubmit={(e) => { e.preventDefault(); if (trackRef.trim()) track.mutate(); }}>
            <label className="sr-only" htmlFor="pc-track-input">Parcel ID</label>
            <input id="pc-track-input" value={trackRef} onChange={(e) => setTrackRef(e.target.value.toUpperCase())} placeholder="PCL-XXXXXXXX" maxLength={16} autoCapitalize="characters" />
            <Button type="submit" size="sm" loading={track.isPending} disabled={!authed || !trackRef.trim()}>Track</Button>
          </form>
          <p className="small muted">{authed ? 'Parcels in your account. Someone shared a link with you? Open the link directly.' : 'Sign in to track your parcels.'}</p>
        </Panel>

        <Panel title="Recent parcels" kicker="History" id="pc-recent" aside={past.data?.results.length ? <Link to="/parcels/history" className="pc-more">All</Link> : undefined}>
          {!authed ? <p className="small muted">Sign in to see your parcels.</p> : past.isPending ? <Skeleton height={120} /> : past.isError ? <ErrorState error={past.error} onRetry={() => past.refetch()} />
            : past.data.results.length === 0 ? <p className="small muted">No recent deliveries.</p> : (
              <div className="pc-rows">
                {past.data.results.slice(0, 4).map((p) => (
                  <ParcelRow key={p.id} p={p} actions={<>
                    <Link to={`/parcels/${p.id}`} className="btn btn--ghost btn--sm">View</Link>
                    <button type="button" className="btn btn--outline btn--sm" onClick={() => void startRepeat(p.id)}>Repeat</button>
                  </>} />
                ))}
              </div>
            )}
        </Panel>

        <Panel title="Saved recipients" kicker="People" id="pc-recips">
          {!authed ? <p className="small muted">Sign in to use saved recipients.</p> : recipients.isPending ? <Skeleton height={80} />
            : (recipients.data ?? []).length === 0 ? <p className="small muted">No saved recipients. Tick “Save this recipient” when you book.</p> : (
              <ul className="pc-people">
                {recipients.data!.map((r) => (
                  <li key={r.id}>
                    <span className="pc-people__av" aria-hidden="true">{r.name.slice(0, 1)}</span>
                    <span className="pc-people__txt"><strong>{r.label || r.name}</strong><span className="small muted">{r.name} · ••••• {r.phone.replace(/\D/g, '').slice(-4)}</span></span>
                    <button type="button" className="btn btn--ghost btn--sm" onClick={() => { d.setMode('send'); d.applyRecipient(r); goMission(); }}>Use</button>
                    <button type="button" className="icon-btn" aria-label={`Edit ${r.name}`} onClick={() => setEditing(r)}><Icon name="edit" size={16} /></button>
                    <button type="button" className="icon-btn" aria-label={`Remove ${r.name}`}
                      onClick={async () => { if (await confirm({ title: `Remove ${r.name}?`, confirmLabel: 'Remove', danger: true })) removeRecipient.mutate(r.id); }}><Icon name="close" size={16} /></button>
                  </li>
                ))}
              </ul>
            )}
        </Panel>

        <Panel title="Saved places" kicker="Addresses" id="pc-places" aside={<Link to="/account/addresses" className="pc-more">Manage</Link>}>
          {!authed ? <p className="small muted">Sign in to use your saved addresses.</p> : addresses.length === 0 ? <p className="small muted">No saved addresses yet.</p> : (
            <ul className="pc-places">
              {addresses.map((a) => {
                const spot = a.latitude && a.longitude ? { label: a.label.charAt(0).toUpperCase() + a.label.slice(1), address: [a.line1, a.line2, a.city].filter(Boolean).join(', '), lat: Number(a.latitude), lng: Number(a.longitude) } : null;
                return (
                  <li key={a.id}>
                    <Icon name={a.label === 'work' ? 'briefcase' : a.label === 'home' ? 'home' : 'pin'} size={16} />
                    <span className="pc-people__txt"><strong style={{ textTransform: 'capitalize' }}>{a.label}</strong><span className="small muted">{a.line2 || a.city}</span></span>
                    {spot ? <>
                      <button type="button" className="btn btn--ghost btn--sm" onClick={() => { d.setPickup(spot); goMission(); }}>Pickup</button>
                      <button type="button" className="btn btn--ghost btn--sm" onClick={() => { d.setDrop(spot); goMission(); }}>Drop</button>
                    </> : <span className="small muted">No map pin</span>}
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>
      </div>

      {options.data && options.data.services.length > 0 && (
        <Panel title="Delivery options" kicker="Services" id="pc-svcs">
          <div className="pc-svcgrid">
            {options.data.services.map((s) => (
              <div key={s.code} className={`pc-svccard pc-svc--${s.code}`}>
                <strong>{s.name}</strong><span className="small">{s.description}</span>
                <span className="small muted">{s.hours} · up to {s.maxDistanceKm} km{s.allowStops ? ` · up to ${s.maxStops} stops` : ''}</span>
              </div>
            ))}
            {options.data.vehicles.some((v) => Number(v.capacity.maxKg) >= 100) && (
              <div className="pc-svccard pc-svc--large"><strong>Large goods</strong>
                <span className="small">{options.data.vehicles.filter((v) => Number(v.capacity.maxKg) >= 100).map((v) => `${v.name} up to ${v.capacity.maxKg} kg`).join(' · ')}</span></div>
            )}
          </div>
        </Panel>
      )}

      <Panel title="Sending often?" kicker="Frequent senders" id="pc-often">
        <div className="pc-often">
          <button type="button" className="pc-oftencard" onClick={() => (lastDone ? void startRepeat(lastDone.id) : toast('Repeat appears after your first delivered parcel.'))}>
            <Icon name="history" size={20} /><strong>Repeat a delivery</strong><span className="small muted">Same route and package, re-quoted</span></button>
          <button type="button" className="pc-oftencard" onClick={() => { d.setMode('send'); goMission(); }}>
            <Icon name="parcel" size={20} /><strong>Multiple drops</strong><span className="small muted">Add up to 3 stops on one trip (where the service allows)</span></button>
          <Link to="/help/new?category=delivery&subject=Business%20%2F%20bulk%20parcel%20deliveries" className="pc-oftencard">
            <Icon name="briefcase" size={20} /><strong>Business &amp; bulk</strong><span className="small muted">Business accounts aren’t available yet. Tell us your volumes and we’ll get in touch.</span></Link>
        </div>
      </Panel>

      <Panel title="Need help with a parcel?" kicker="Support" id="pc-help">
        <p className="small muted">Open the parcel and choose Get help: delayed parcel, pickup issue, recipient unavailable, wrong address, damaged or missing parcel, payment or cancellation.</p>
        <Link to="/help" className="btn btn--outline btn--sm">Help &amp; Support</Link>
      </Panel>

      <Sheet open={!!editing} onClose={() => setEditing(null)} label="Edit recipient">
        {editing && (
          <form className="pc-review" onSubmit={(e) => { e.preventDefault(); if (PHONE.test(editing.phone.trim())) saveRecipient.mutate(editing); }}>
            <h2>Edit recipient</h2>
            {(['label', 'name', 'phone', 'altPhone', 'instructions'] as const).map((k) => (
              <label key={k} className="pc-field pc-field--wide"><span>{{ label: 'Place name', name: 'Name', phone: 'Phone', altPhone: 'Alternate phone', instructions: 'Instructions' }[k]}</span>
                <input value={editing[k] ?? ''} onChange={(e) => setEditing({ ...editing, [k]: e.target.value })} aria-invalid={k === 'phone' && !PHONE.test(editing.phone.trim())} /></label>
            ))}
            <Button type="submit" block loading={saveRecipient.isPending}>Save</Button>
          </form>
        )}
      </Sheet>
      {!authed && status !== 'loading' && <EmptyState icon="parcel" title="Sign in to book" message="You can plan a delivery and see estimates after signing in." action={<Link to="/login?next=/parcels" className="btn btn--primary">Sign in</Link>} />}
    </div>
  );
}
