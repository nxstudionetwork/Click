import type { ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Icon, type IconName } from '../../components/ui';
import { formatMoney } from '../../lib/format';

const TZ = 'Asia/Kolkata';

/** Icons per service / category across Wallet, Payments, Activity, Offers and Notifications. */
export const SERVICE_ICON: Record<string, IconName> = {
  food: 'food', groceries: 'grocery', shop: 'shop', ride: 'ride', rides: 'ride', parcel: 'parcel', services: 'wrench', service: 'wrench', shows: 'film',
  events: 'gift', hotels: 'hotel', travel: 'plane', bookings: 'temple', wallet: 'wallet', payments: 'card', payment: 'card', rewards: 'star', offers: 'tag',
  pharma: 'plus', pharmacy: 'plus', wishlist: 'heart', buddy: 'sparkle', support: 'help', account: 'shield', orders: 'bag', order: 'bag', deliveries: 'parcel', system: 'shield', delivery: 'parcel',
};
export const iconFor = (s: string): IconName => SERVICE_ICON[s] ?? 'receipt';

/** Theme per service (data-theme), so rows pick up each service's colour. */
export const THEME: Record<string, string> = {
  food: 'food', groceries: 'groceries', shop: 'shop', ride: 'ride', rides: 'ride', parcel: 'parcel', services: 'services', shows: 'movies',
  events: 'events', hotels: 'hotels', travel: 'travel', bookings: 'bookings', pharma: 'pharma',
};

export const money = (v: string | number | null | undefined) => formatMoney(Number(v ?? 0));
export const signed = (v: string | number) => `${Number(v) > 0 ? '+' : '−'}${formatMoney(Math.abs(Number(v)))}`;

export function dayLabel(iso: string): string {
  const d = new Date(iso);
  const key = (x: Date) => x.toLocaleDateString('en-CA', { timeZone: TZ });
  const today = new Date();
  const yesterday = new Date(Date.now() - 86_400_000);
  if (key(d) === key(today)) return 'Today';
  if (key(d) === key(yesterday)) return 'Yesterday';
  const diff = (today.getTime() - d.getTime()) / 86_400_000;
  if (diff < 7) return 'This week';
  return d.toLocaleDateString('en-IN', { timeZone: TZ, month: 'long', year: 'numeric' });
}

export const timeOf = (iso: string) => new Date(iso).toLocaleTimeString('en-IN', { timeZone: TZ, hour: 'numeric', minute: '2-digit' });
export const dateOf = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { timeZone: TZ, day: 'numeric', month: 'short', year: 'numeric' });
export const dateTimeOf = (iso: string) => `${dateOf(iso)}, ${timeOf(iso)}`;

/** Splits newest-first rows into "Today / Yesterday / This week / Month" groups. */
export function groupByDay<T>(rows: T[], at: (r: T) => string): { label: string; rows: T[] }[] {
  const out: { label: string; rows: T[] }[] = [];
  for (const r of rows) {
    const label = dayLabel(at(r));
    const last = out[out.length - 1];
    if (last && last.label === label) last.rows.push(r);
    else out.push({ label, rows: [r] });
  }
  return out;
}

export function Pill({ tone, children }: { tone: 'ok' | 'bad' | 'pending' | 'info' | ''; children: ReactNode }) {
  return <span className={`mn-pill mn-pill--${tone || 'info'}`}>{children}</span>;
}

export const toneOfPayment = (s: string): 'ok' | 'bad' | 'pending' | 'info' =>
  s === 'successful' ? 'ok' : s === 'failed' ? 'bad' : s === 'pending' ? 'pending' : 'info';

/** A focused header for the money pages: back, title, an optional action. */
export function MoneyHead({ title, back = '/account', backLabel = 'Back', action, sub }: { title: string; back?: string; backLabel?: string; action?: ReactNode; sub?: ReactNode }) {
  const nav = useNavigate();
  return (
    <header className="mn-head">
      <button type="button" className="mn-head__back" onClick={() => (window.history.length > 1 ? nav(-1) : nav(back))} aria-label={backLabel}>
        <Icon name="back" size={20} />
      </button>
      <div className="mn-head__title"><h1>{title}</h1>{sub && <p className="small mn-muted">{sub}</p>}</div>
      {action ?? <Link to="/" className="mn-head__home" aria-label="Home"><Icon name="home" size={20} /></Link>}
    </header>
  );
}

export function Section({ title, action, children, id }: { title: string; action?: ReactNode; children: ReactNode; id?: string }) {
  return (
    <section className="mn-sec" aria-labelledby={id}>
      <div className="mn-sec__head"><h2 id={id}>{title}</h2>{action}</div>
      {children}
    </section>
  );
}

export const newKey = () => (typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`);
