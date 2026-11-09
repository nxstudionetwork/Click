import type { ReactNode } from 'react';
import type { ParcelDetail, ParcelStatus, ParcelSummary } from '@click/api';
import { Icon, type IconName } from '../../components/ui';

export const VEHICLE_ICON: Record<string, IconName> = { bike: 'bike', scooter: 'bike', auto: 'auto', mini_truck: 'warehouse' };
export const vehicleIcon = (code: string, icon?: string): IconName => VEHICLE_ICON[code] ?? ((icon as IconName) || 'parcel');

export const when = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' }) : '';
export const clock = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' }) : '');

const TONE: Record<ParcelStatus, string> = {
  scheduled: 'info', searching: 'info', assigned: 'active', at_pickup: 'active', picked_up: 'active', in_transit: 'active', arriving: 'active',
  delivered: 'done', cancelled: 'off', failed: 'warn', no_partner: 'off',
};
export function StatusChip({ status, label }: { status: ParcelStatus; label: string }) {
  return <span className={`pc-status pc-status--${TONE[status]}`}>{label}</span>;
}

/** Pickup → Transit → Drop. A visual explanation of the service (not tracking). Motion stops with reduced motion. */
export function RouteGlyph({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`pc-glyph${compact ? ' pc-glyph--compact' : ''}`} aria-hidden="true">
      <span className="pc-glyph__node pc-glyph__node--a"><Icon name="parcel" size={compact ? 14 : 18} /></span>
      <span className="pc-glyph__line"><span className="pc-glyph__dot" /></span>
      <span className="pc-glyph__node pc-glyph__node--mid"><Icon name="bike" size={compact ? 14 : 18} /></span>
      <span className="pc-glyph__line"><span className="pc-glyph__dot pc-glyph__dot--late" /></span>
      <span className="pc-glyph__node pc-glyph__node--b"><Icon name="pin" size={compact ? 14 : 18} /></span>
    </div>
  );
}

export function RouteLine({ from, to, stops = 0 }: { from: string; to: string; stops?: number }) {
  return (
    <div className="pc-routeline">
      <span className="pc-routeline__pt pc-routeline__pt--a" aria-hidden="true" />
      <span className="pc-routeline__txt"><span className="small muted">From</span><strong>{from}</strong></span>
      {stops > 0 && <span className="pc-routeline__stops small">+{stops} stop{stops > 1 ? 's' : ''}</span>}
      <span className="pc-routeline__pt pc-routeline__pt--b" aria-hidden="true" />
      <span className="pc-routeline__txt"><span className="small muted">To</span><strong>{to}</strong></span>
    </div>
  );
}

export function Timeline({ steps }: { steps: ParcelDetail['timeline'] }) {
  const last = steps.reduce((i, s, idx) => (s.at ? idx : i), -1);
  return (
    <ol className="pc-timeline">
      {steps.map((s, i) => (
        <li key={s.status} className={`${s.at ? 'is-done' : ''} ${i === last ? 'is-now' : ''} pc-timeline--${s.status}`}>
          <span className="pc-timeline__dot" aria-hidden="true" />
          <span className="pc-timeline__label">{s.label}</span>
          {s.at && <span className="pc-timeline__at small muted">{clock(s.at)}</span>}
        </li>
      ))}
    </ol>
  );
}

export function ParcelRow({ p, actions }: { p: ParcelSummary; actions?: ReactNode }) {
  return (
    <div className="pc-row">
      <span className="pc-row__icon"><Icon name={vehicleIcon(p.vehicle.code, p.vehicle.icon)} size={20} /></span>
      <div className="pc-row__main">
        <div className="pc-row__top"><strong>{p.number}</strong><StatusChip status={p.status} label={p.statusLabel} /></div>
        <span className="small pc-row__route">{p.pickup.label} → {p.drop.label}</span>
        <span className="small muted">{when(p.createdAt)} · {p.service.name} · ₹{Number(p.total).toFixed(0)}</span>
      </div>
      {actions && <div className="pc-row__actions">{actions}</div>}
    </div>
  );
}

export function Panel({ title, kicker, children, id, aside }: { title: string; kicker?: string; children: ReactNode; id?: string; aside?: ReactNode }) {
  return (
    <section className="pc-panel" aria-labelledby={id} id={id ? `${id}-sec` : undefined}>
      <header className="pc-panel__head">
        <div>{kicker && <span className="pc-kicker">{kicker}</span>}<h2 id={id}>{title}</h2></div>
        {aside}
      </header>
      {children}
    </section>
  );
}
