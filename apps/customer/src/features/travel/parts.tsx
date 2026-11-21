import { useEffect, useId, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { SeatInfo, TravelMode, TravelOption, TravelOptionDetail, TravelPlace, TravelSearchQuery } from '@click/api';
import { Button, Icon, type IconName, Sheet } from '../../components/ui';
import { api } from '../../lib/api';
import { formatMoney } from '../../lib/format';

/* Times are the operator's local (India) times, shown the same wherever the customer is. */
const TZ = 'Asia/Kolkata';
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
export const todayIso = () => new Date().toLocaleDateString('en-CA', { timeZone: TZ });
export const addDays = (s: string, n: number) => { const d = new Date(`${s}T00:00:00`); d.setDate(d.getDate() + n); return iso(d); };
export const fmtTime = (at: string) => new Date(at).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', hour12: true, timeZone: TZ });
export const fmtDate = (at: string, opts: Intl.DateTimeFormatOptions = { weekday: 'short', day: 'numeric', month: 'short' }) =>
  new Date(at.length === 10 ? `${at}T12:00:00` : at).toLocaleDateString('en-IN', { ...opts, timeZone: TZ });
export const fmtDur = (m: number) => `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m`;

export const MODES: { id: TravelMode; label: string; icon: IconName; noun: string }[] = [
  { id: 'bus', label: 'Bus', icon: 'bus', noun: 'buses' }, { id: 'train', label: 'Train', icon: 'train', noun: 'trains' },
  { id: 'flight', label: 'Flight', icon: 'plane', noun: 'flights' },
];
export const modeOf = (m: TravelMode) => MODES.find((x) => x.id === m)!;
export const STATUS_TONE: Record<string, string> = { confirmed: 'ok', completed: 'ok', pending_payment: 'warn', cancelled: 'bad', failed: 'bad' };
export const HIGHLIGHT: Record<string, string> = { cheapest: 'Cheapest', fastest: 'Fastest', best_value: 'Best value' };

/** The search lives in the URL so results, details and booking share it, Back keeps it, and links can be shared. */
export function searchFrom(sp: URLSearchParams): TravelSearchQuery {
  const mode = (['bus', 'train', 'flight'].includes(sp.get('mode') ?? '') ? sp.get('mode') : 'bus') as TravelMode;
  const date = sp.get('date') && sp.get('date')! >= todayIso() ? sp.get('date')! : todayIso();
  const n = (k: string, d: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, Number(sp.get(k) ?? d) || d));
  return { mode, origin: sp.get('origin') ?? '', destination: sp.get('destination') ?? '', date, returnDate: sp.get('return_date') || null,
    adults: n('adults', 1, 1, 9), children: Math.min(8, Math.max(0, Number(sp.get('children')) || 0)), infants: Math.min(4, Math.max(0, Number(sp.get('infants')) || 0)),
    travelClass: sp.get('travel_class') ?? '' };
}
export function searchQs(s: TravelSearchQuery, extra: Record<string, string> = {}) {
  const p = new URLSearchParams({ mode: s.mode, origin: s.origin, destination: s.destination, date: s.date, adults: String(s.adults) });
  if (s.children) p.set('children', String(s.children));
  if (s.infants) p.set('infants', String(s.infants));
  if (s.returnDate) p.set('return_date', s.returnDate);
  if (s.travelClass) p.set('travel_class', s.travelClass);
  Object.entries(extra).forEach(([k, v]) => v && p.set(k, v));
  return p.toString();
}
export const paxLabel = (s: { adults: number; children: number; infants: number }) =>
  [`${s.adults} adult${s.adults > 1 ? 's' : ''}`, s.children ? `${s.children} child${s.children > 1 ? 'ren' : ''}` : '', s.infants ? `${s.infants} infant${s.infants > 1 ? 's' : ''}` : '']
    .filter(Boolean).join(' · ');

/** City / station / airport autocomplete. Each suggestion says what it is ("Hyderabad — Airport (HYD)"). */
export function PlaceField({ label, mode, value, onPick, autoFocus }: {
  label: string; mode: TravelMode; value: TravelPlace | null; onPick: (p: TravelPlace) => void; autoFocus?: boolean;
}) {
  const id = useId();
  const [text, setText] = useState(value?.name ?? '');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [debounced, setDebounced] = useState('');
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => { setText(value?.name ?? ''); }, [value?.slug, value?.name]);
  useEffect(() => { const t = setTimeout(() => setDebounced(text.trim()), 180); return () => clearTimeout(t); }, [text]);
  const q = useQuery({ queryKey: ['travel', 'places', mode, debounced], queryFn: () => api.travel.places(debounced, mode), enabled: open && debounced.length >= 2 });
  const rows = q.data?.results ?? [];
  const pick = (p: TravelPlace) => { onPick(p); setText(p.name); setOpen(false); };
  return (
    <div className="tv-field tv-place" ref={box} onBlur={(e) => { if (!box.current?.contains(e.relatedTarget as Node)) setOpen(false); }}>
      <label htmlFor={id} className="tv-field__label">{label}</label>
      <input id={id} className="tv-field__input" value={text} autoComplete="off" autoFocus={autoFocus} placeholder="City, station or airport"
        role="combobox" aria-expanded={open && rows.length > 0} aria-controls={`${id}-list`} aria-autocomplete="list"
        aria-activedescendant={open && rows[active] ? `${id}-${active}` : undefined}
        onChange={(e) => { setText(e.target.value); setOpen(true); setActive(0); }} onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(rows.length - 1, a + 1)); }
          else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
          else if (e.key === 'Enter' && open && rows[active]) { e.preventDefault(); pick(rows[active]!); }
          else if (e.key === 'Escape') setOpen(false);
        }} />
      {value && value.kind !== 'city' && <span className="tv-field__sub">{value.kindLabel}{value.code ? ` · ${value.code}` : ''} · {value.city}</span>}
      {open && debounced.length >= 2 && (
        <ul id={`${id}-list`} role="listbox" className="tv-suggest" aria-label={`${label} suggestions`}>
          {q.isFetching && rows.length === 0 && <li className="tv-suggest__note">Searching…</li>}
          {!q.isFetching && rows.length === 0 && <li className="tv-suggest__note">No matching city, station or airport on Click. Travel.</li>}
          {rows.map((p, i) => (
            <li key={p.id} id={`${id}-${i}`} role="option" aria-selected={i === active} className={i === active ? 'is-active' : ''}
              onMouseDown={(e) => e.preventDefault()} onClick={() => pick(p)}>
              <Icon name={p.kind === 'airport' ? 'plane' : p.kind === 'station' ? 'train' : p.kind === 'bus_stop' ? 'bus' : 'pin'} size={16} />
              <span><strong>{p.name}</strong> <span className="tv-muted">— {p.kind === 'city' ? 'City' : `${p.kindLabel}${p.code ? ` (${p.code})` : ''}`}</span>
                <span className="tv-suggest__sub">{p.kind === 'city' ? p.state : p.city}</span></span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ModeTabs({ value, onChange, compact }: { value: TravelMode; onChange: (m: TravelMode) => void; compact?: boolean }) {
  return (
    <div className={`tv-modes${compact ? ' tv-modes--compact' : ''}`} role="tablist" aria-label="Transport">
      {MODES.map((m) => (
        <button key={m.id} type="button" role="tab" aria-selected={value === m.id} className={value === m.id ? 'is-on' : ''} onClick={() => onChange(m.id)}>
          <Icon name={m.icon} size={18} /> {m.label}
        </button>
      ))}
    </div>
  );
}

export function PaxPicker({ mode, value, max, onChange }: {
  mode: TravelMode; value: { adults: number; children: number; infants: number }; max: number; onChange: (v: { adults: number; children: number; infants: number }) => void;
}) {
  const [open, setOpen] = useState(false);
  const [d, setD] = useState(value);
  const seats = d.adults + d.children;
  const row = (k: 'adults' | 'children' | 'infants', label: string, hint: string, lo: number, hi: number) => (
    <div className="tv-step" key={k}>
      <span><strong>{label}</strong><span className="small tv-muted">{hint}</span></span>
      <span className="tv-step__ctl">
        <button type="button" aria-label={`Fewer ${label.toLowerCase()}`} disabled={d[k] <= lo} onClick={() => setD({ ...d, [k]: d[k] - 1 })}>−</button>
        <output aria-live="polite">{d[k]}</output>
        <button type="button" aria-label={`More ${label.toLowerCase()}`} disabled={d[k] >= hi} onClick={() => setD({ ...d, [k]: d[k] + 1 })}>+</button>
      </span>
    </div>
  );
  return (
    <>
      <button type="button" className="tv-field tv-field--btn" onClick={() => { setD(value); setOpen(true); }}>
        <span className="tv-field__label">Passengers</span><span className="tv-field__value">{paxLabel(value)}</span>
      </button>
      <Sheet open={open} onClose={() => setOpen(false)} label="Passengers">
        <div className="tv-sheet">
          <h2>Passengers</h2>
          {row('adults', 'Adults', '12 and over', 1, max - d.children)}
          {row('children', 'Children', mode === 'flight' ? '2–11, own seat' : mode === 'train' ? '5–11, own berth' : '3–11, own seat', 0, max - d.adults)}
          {mode === 'flight' && row('infants', 'Infants', 'Under 2, on a lap', 0, d.adults)}
          <p className="small tv-muted">Up to {max} passengers per booking{mode !== 'flight' ? '; younger children travel on an adult’s seat' : ''}.</p>
          <Button block disabled={seats < 1} onClick={() => { onChange(mode === 'flight' ? d : { ...d, infants: 0 }); setOpen(false); }}>Done</Button>
        </div>
      </Sheet>
    </>
  );
}

function OperatorMark({ name, accent, mode }: { name: string; accent: string; mode: TravelMode }) {
  const initials = name.split(' ').filter((w) => /^[A-Z]/.test(w)).map((w) => w[0]).slice(0, 2).join('');
  return <span className="tv-op" style={{ ['--tv-accent' as string]: accent }} aria-hidden="true">{initials || <Icon name={modeOf(mode).icon} size={16} />}</span>;
}

export function JourneyCard({ o, to, compare, onCompare }: { o: TravelOption; to: string; compare?: boolean; onCompare?: () => void }) {
  const avail = o.classes.filter((c) => c.bookable);
  return (
    <article className={`tv-card${o.available ? '' : ' is-off'}`} style={{ ['--tv-accent' as string]: o.operator.accent }}>
      <header className="tv-card__head">
        <OperatorMark name={o.operator.name} accent={o.operator.accent} mode={o.mode} />
        <div className="tv-card__op">
          <strong>{o.operator.name}</strong>
          <span className="small tv-muted">
            {o.mode === 'train' ? `${o.service.number} · ${o.service.name}` : o.mode === 'flight' ? `${o.service.number} · ${o.service.vehicle}` : o.service.vehicle}
          </span>
        </div>
        {o.operator.rating && <span className="tv-rate" title={`${o.operator.rating.count} verified trips`}><Icon name="star" size={12} /> {o.operator.rating.average}</span>}
      </header>
      {(o.highlights?.length ?? 0) > 0 && <div className="tv-flags">{o.highlights!.map((h) => <span key={h} className={`tv-flag tv-flag--${h}`}>{HIGHLIGHT[h]}</span>)}</div>}
      <div className="tv-leg">
        <div><strong className="tv-time">{fmtTime(o.departsAt)}</strong><span className="small">{o.mode === 'bus' ? o.from.name : `${o.from.code || o.from.name}`}</span></div>
        <div className="tv-leg__mid" aria-label={`${fmtDur(o.durationMinutes)}${o.mode === 'flight' ? `, ${o.stops ? `${o.stops} stop` : 'non-stop'}` : ''}`}>
          <span className="small">{fmtDur(o.durationMinutes)}</span>
          <span className="tv-leg__line" aria-hidden="true"><i /></span>
          <span className="small tv-muted">{o.mode === 'flight' ? (o.stops ? `${o.stops} stop · ${o.via.join(', ')}` : 'Non-stop') : o.mode === 'train' ? `${o.distanceKm} km` : `${o.distanceKm} km`}</span>
        </div>
        <div className="tv-leg__end"><strong className="tv-time">{fmtTime(o.arrivesAt)}{o.daysLater > 0 && <sup>+{o.daysLater}</sup>}</strong><span className="small">{o.mode === 'bus' ? o.to.name : o.to.code || o.to.name}</span></div>
      </div>
      {o.status !== 'scheduled' && <p className={`tv-alert${o.status === 'cancelled' ? ' tv-alert--bad' : ''}`}><Icon name="alert" size={14} /> {o.statusLabel}{o.delayMinutes ? ` · about ${o.delayMinutes} min late` : ''}{o.notice ? ` · ${o.notice}` : ''}</p>}
      {o.mode === 'train' && (
        <div className="tv-classes" role="list" aria-label="Classes">
          {o.classes.map((c) => (
            <span key={c.code} role="listitem" className={`tv-cls tv-cls--${c.availability.status}`}>
              <strong>{c.code}</strong><span>{c.availability.label}</span><span>{formatMoney(c.perPerson)}</span>
            </span>
          ))}
        </div>
      )}
      <div className="tv-tags">
        {o.mode === 'bus' && <span>{o.service.ac ? 'AC' : 'Non-AC'} · {o.service.busTypeLabel}</span>}
        {o.mode === 'flight' && o.service.baggage?.checkIn && <span><Icon name="bag" size={12} /> {o.service.baggage.checkIn} check-in</span>}
        {o.service.amenities.slice(0, 3).map((a) => <span key={a}>{a}</span>)}
        <span className={o.cancellation === 'non_refundable' ? 'tv-bad' : 'tv-ok'}>{o.cancellation === 'free' ? 'Free cancellation window' : o.cancellation === 'partial' ? 'Partly refundable' : 'Non-refundable'}</span>
      </div>
      <footer className="tv-card__foot">
        <div className="tv-price">
          {o.lowest ? <><span className="small tv-muted">{avail.length ? 'from' : 'Sold out'}</span><strong>{formatMoney(o.lowest)}</strong><span className="small tv-muted">per person incl. GST</span></>
            : <strong>—</strong>}
          {o.mode === 'bus' && o.seatsLeft != null && <span className={`small ${o.seatsLeft <= 5 ? 'tv-warn' : 'tv-muted'}`}>{o.seatsLeft ? `${o.seatsLeft} seats left` : 'No seats left'}</span>}
          {o.mode === 'flight' && avail[0]?.availability.label.includes('left') && <span className="small tv-warn">{avail[0].availability.label}</span>}
        </div>
        <div className="tv-card__cta">
          {onCompare && <label className="tv-cmp small"><input type="checkbox" checked={!!compare} onChange={onCompare} /> Compare</label>}
          <Link to={to} className={`tv-btn${o.available ? '' : ' tv-btn--ghost'}`}>{o.mode === 'bus' ? 'View seats' : o.mode === 'train' ? 'Choose class' : 'Select'}</Link>
        </div>
      </footer>
    </article>
  );
}

export function RouteTimeline({ route }: { route: TravelOptionDetail['route'] }) {
  const visible = route.filter((s) => s.inSegment);
  return (
    <ol className="tv-route" aria-label="Route">
      {visible.map((s, i) => (
        <li key={`${s.name}-${i}`} className={i === 0 || i === visible.length - 1 ? 'is-end' : ''}>
          <span className="tv-route__dot" aria-hidden="true" />
          <div><strong>{s.name}{s.code ? ` (${s.code})` : ''}</strong>
            <span className="small tv-muted">{s.arrive && i > 0 ? `arr ${fmtTime(s.arrive)}` : ''}{s.arrive && s.depart && i > 0 && i < visible.length - 1 ? ' · ' : ''}{s.depart && i < visible.length - 1 ? `dep ${fmtTime(s.depart)}` : ''}
              {' · '}day {s.day}{s.note ? ` · ${s.note}` : ''}</span></div>
          <span className="small tv-muted">{s.km} km</span>
        </li>
      ))}
    </ol>
  );
}

/** The seat layout from the operator. Every seat says its state in words (not colour alone) and its fare. */
export function SeatMap({ map, picked, max, onToggle }: {
  map: NonNullable<TravelOptionDetail['seatMap']>; picked: string[]; max: number; onToggle: (seat: string) => void;
}) {
  const label = (k: string, s: SeatInfo) =>
    `${s.kind === 'sleeper' ? 'Berth' : 'Seat'} ${k}, ${formatMoney(s.fare)}, ${s.status === 'sold' ? 'booked' : s.status === 'blocked' ? 'not for sale' : picked.includes(k) ? 'selected' : 'available'}${s.ladies ? ', reserved for women' : ''}${s.gents ? ', reserved for men' : ''}`;
  return (
    <div className="tv-seatmap">
      <ul className="tv-legend small" aria-label="Legend">
        <li><i className="tv-seat tv-seat--free" /> Available</li><li><i className="tv-seat tv-seat--on" /> Selected</li>
        <li><i className="tv-seat tv-seat--sold" /> Booked</li><li><i className="tv-seat tv-seat--ladies" /> Women only (♀)</li>
      </ul>
      <div className="tv-decks">
        {map.decks.map((deck) => (
          <section key={deck.name} className="tv-deck" aria-label={deck.name}>
            <h3 className="small">{deck.name}</h3>
            <div className="tv-deck__rows">
              {deck.rows.map((row, ri) => (
                <div key={ri} className="tv-deck__row">
                  {row.map((k, ci) => {
                    if (!k) return <span key={ci} className="tv-aisle" aria-hidden="true" />;
                    const s = map.seats[k]!;
                    const on = picked.includes(k);
                    const off = s.status !== 'available' || (!on && picked.length >= max);
                    return (
                      <button key={k} type="button" className={`tv-seat tv-seat--${s.kind}${on ? ' tv-seat--on' : ''}${s.status !== 'available' ? ' tv-seat--sold' : ''}${s.ladies ? ' tv-seat--ladies' : ''}`}
                        aria-pressed={on} aria-label={label(k, s)} disabled={off} onClick={() => onToggle(k)}>
                        <span>{k}</span>{s.ladies && <em aria-hidden="true">♀</em>}
                      </button>
                    );
                  })}
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
