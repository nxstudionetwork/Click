import { useMemo, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { TravelMode, TravelPlace, TravelRoute, TravelSearchQuery } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, ErrorState, Icon, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { addDays, fmtDate, fmtDur, fmtTime, ModeTabs, modeOf, MODES, PaxPicker, PlaceField, searchQs, STATUS_TONE, todayIso } from '../features/travel/parts';
import { useDeliveryLocation } from '../location/LocationProvider';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

const RECENT_KEY = ['travel', 'recent'];

/** Click. Travel home: a journey search (its own origin, never the Home location), the next journey, recent searches,
 *  saved routes, routes Click. sells, data-rule collections, live offers and the journey planner. */
export function TravelPage() {
  useThemeOverride('travel');
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const { status } = useAuth();
  const authed = status === 'authenticated';
  const qc = useQueryClient();
  const { selected } = useDeliveryLocation();
  const [mode, setMode] = useState<TravelMode>((['bus', 'train', 'flight'].includes(sp.get('mode') ?? '') ? sp.get('mode') : 'bus') as TravelMode);
  const [from, setFrom] = useState<TravelPlace | null>(null);
  const [to, setTo] = useState<TravelPlace | null>(null);
  const [date, setDate] = useState(addDays(todayIso(), 1));
  const [roundTrip, setRoundTrip] = useState(false);
  const [ret, setRet] = useState(addDays(todayIso(), 3));
  const [cls, setCls] = useState('');
  const [pax, setPax] = useState({ adults: 1, children: 0, infants: 0 });
  const [error, setError] = useState('');

  const home = useQuery({ queryKey: ['travel', 'home', selected?.city ?? ''], queryFn: () => api.travel.home(selected?.city) });
  const recent = useQuery({ queryKey: RECENT_KEY, queryFn: () => api.travel.recent(), enabled: authed });
  const next = useQuery({ queryKey: ['travel', 'next'], queryFn: () => api.travel.next(), enabled: authed });
  const routes = useQuery({ queryKey: ['travel', 'routes'], queryFn: () => api.travel.routes(), enabled: authed });
  const clear = useMutation({ mutationFn: () => api.travel.clearRecent(), onSuccess: () => qc.setQueryData(RECENT_KEY, { results: [] }) });
  const toSlug = sp.get('to');
  useQuery({ queryKey: ['travel', 'prefill', toSlug], enabled: !!toSlug && !to, queryFn: async () => {
    const r = await api.travel.places(toSlug!.replace(/-/g, ' '));
    const p = r.results.find((x) => x.slug === toSlug) ?? null;
    if (p) setTo(p);
    return p;
  } });
  const max = home.data?.maxPassengers[mode] ?? 6;

  const useMyCity = async () => {
    if (!selected?.city) return;
    const r = await api.travel.places(selected.city);
    const city = r.results.find((p) => p.kind === 'city' && p.name.toLowerCase() === selected.city.toLowerCase());
    if (city) setFrom(city); else setError(`Click. Travel doesn’t serve ${selected.city} yet. Choose another city.`);
  };
  const fill = (r: TravelRoute) => { setMode(r.mode); setFrom(r.from); setTo(r.to); setError(''); window.scrollTo({ top: 0, behavior: 'smooth' }); };
  const go = (s: TravelSearchQuery) => nav(`/travel/search?${searchQs(s)}`);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!from || !to) return setError('Choose where you’re leaving from and going to, from the suggestions.');
    if (from.citySlug === to.citySlug) return setError('From and To can’t be the same city.');
    if (date < todayIso()) return setError('Choose today or a later date.');
    if (roundTrip && ret < date) return setError('The return date can’t be before departure.');
    setError('');
    go({ mode, origin: from.slug, destination: to.slug, date, returnDate: roundTrip && mode !== 'train' ? ret : null, ...pax,
      infants: mode === 'flight' ? pax.infants : 0, travelClass: cls });
  };

  const byMode = home.data?.routes[mode] ?? [];
  const collections = useMemo(() => home.data?.collections ?? [], [home.data]);

  return (
    <div className="tv-page" data-theme="travel">
      <section className="tv-hero">
        <div className="tv-hero__lines" aria-hidden="true" />
        <span className="tv-kicker">Click. Travel</span>
        <h1>Travel</h1>
        <p className="tv-hero__tag">Go farther. Book smarter.</p>
        <p className="tv-muted">Buses, trains and flights — all in one journey.</p>
      </section>

      <form className="tv-search" onSubmit={submit} noValidate aria-labelledby="tv-q">
        <h2 id="tv-q" className="tv-search__q">Where are you going?</h2>
        <ModeTabs value={mode} onChange={(m) => { setMode(m); setCls(''); if (m !== 'flight') setPax((p) => ({ ...p, infants: 0 })); }} />
        <div className="tv-search__ends">
          <PlaceField label="From" mode={mode} value={from} onPick={(p) => { setFrom(p); setError(''); }} />
          <button type="button" className="tv-swap" aria-label="Swap From and To" onClick={() => { setFrom(to); setTo(from); }}><Icon name="swap" size={18} /></button>
          <PlaceField label="To" mode={mode} value={to} onPick={(p) => { setTo(p); setError(''); }} />
        </div>
        {!from && selected?.city && <button type="button" className="tv-link small" onClick={useMyCity}><Icon name="locate" size={14} /> Leave from my city ({selected.city})</button>}
        <div className="tv-search__row">
          <label className="tv-field"><span className="tv-field__label">{mode === 'train' ? 'Journey date' : 'Departure'}</span>
            <input className="tv-field__input" type="date" min={todayIso()} value={date} onChange={(e) => { setDate(e.target.value); if (ret < e.target.value) setRet(e.target.value); }} required /></label>
          {mode !== 'train' && (roundTrip
            ? <label className="tv-field"><span className="tv-field__label">Return</span>
                <input className="tv-field__input" type="date" min={date} value={ret} onChange={(e) => setRet(e.target.value)} /></label>
            : <button type="button" className="tv-field tv-field--btn" onClick={() => setRoundTrip(true)}><span className="tv-field__label">Return</span><span className="tv-field__value tv-muted">+ Add return</span></button>)}
          <PaxPicker mode={mode} value={pax} max={max} onChange={setPax} />
          {mode === 'train' && (
            <label className="tv-field"><span className="tv-field__label">Class</span>
              <select className="tv-field__input" value={cls} onChange={(e) => setCls(e.target.value)}>
                <option value="">All classes</option>{(home.data?.trainClasses ?? []).map((c) => <option key={c.code} value={c.code}>{c.name} ({c.code})</option>)}
              </select></label>
          )}
          {mode === 'flight' && (
            <label className="tv-field"><span className="tv-field__label">Cabin</span>
              <select className="tv-field__input" value={cls} onChange={(e) => setCls(e.target.value)}>
                <option value="">Any cabin</option>{(home.data?.cabins ?? []).map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
              </select></label>
          )}
        </div>
        {mode !== 'train' && roundTrip && <p className="small tv-muted">Return trips are booked as two tickets: choose your outbound first, then we’ll take you to the return.
          <button type="button" className="tv-link small" onClick={() => setRoundTrip(false)}>One way instead</button></p>}
        {error && <p className="tv-error small" role="alert">{error}</p>}
        <Button type="submit" block className="tv-go">Search {modeOf(mode).noun}</Button>
      </form>

      {authed && next.data?.booking && (() => {
        const b = next.data.booking!;
        return (
          <section className="tv-next" aria-labelledby="tv-next">
            <span className="tv-kicker" id="tv-next">Your next journey</span>
            <div className="tv-next__row">
              <Icon name={modeOf(b.mode).icon} size={22} />
              <div><strong>{b.from.city} → {b.to.city}</strong>
                <span className="small tv-muted">{fmtDate(b.departsAt)} · {fmtTime(b.departsAt)} · {b.modeLabel} · {b.operator}</span></div>
              <span className={`tv-status tv-status--${STATUS_TONE[b.status] ?? 'warn'}`}>{b.statusLabel}</span>
            </div>
            {b.journeyStatus !== 'scheduled' && <p className="tv-alert small"><Icon name="alert" size={14} /> {b.journeyStatusLabel}{b.notice ? ` · ${b.notice}` : ''}</p>}
            <Link className="tv-btn tv-btn--sm" to={`/travel/bookings/${b.id}`}>View journey</Link>
          </section>
        );
      })()}

      {authed && (recent.data?.results.length ?? 0) > 0 && (
        <section className="tv-sec">
          <div className="tv-sec__head"><h2 className="tv-h2">Recent searches</h2><button type="button" className="tv-link small" onClick={() => clear.mutate()}>Clear search history</button></div>
          <div className="tv-chips">
            {recent.data!.results.map((r) => (
              <button key={r.id} type="button" className="tv-chip" onClick={() => go({ mode: r.mode, origin: r.origin.slug, destination: r.destination.slug, date: r.date,
                returnDate: r.returnDate, adults: r.adults, children: r.children, infants: r.infants, travelClass: r.travelClass })}>
                <Icon name={modeOf(r.mode).icon} size={14} /> {r.origin.name} → {r.destination.name}<span className="tv-muted"> · {fmtDate(r.date, { day: 'numeric', month: 'short' })}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      {authed && (routes.data?.results.length ?? 0) > 0 && (
        <section className="tv-sec">
          <h2 className="tv-h2">My routes</h2>
          <div className="tv-chips">{routes.data!.results.map((r) => (
            <button key={r.favoriteId} type="button" className="tv-chip" onClick={() => { setFrom(r.origin); setTo(r.destination); window.scrollTo({ top: 0, behavior: 'smooth' }); }}>
              <Icon name="heart" size={14} /> {r.origin.name} → {r.destination.name}</button>
          ))}</div>
        </section>
      )}

      {home.isError ? <ErrorState error={home.error} onRetry={() => home.refetch()} /> : !home.data ? <Skeleton height={180} radius={22} /> : (
        <>
          {home.data.fromCity.length > 0 && (
            <section className="tv-sec"><h2 className="tv-h2">From {selected?.city}</h2>
              <div className="tv-routes">{home.data.fromCity.map((r) => <RouteTile key={`${r.mode}${r.to.slug}`} r={r} onPick={fill} />)}</div></section>
          )}
          <section className="tv-sec">
            <div className="tv-sec__head"><h2 className="tv-h2">{modeOf(mode).label} routes on Click.</h2></div>
            {byMode.length ? <div className="tv-routes">{byMode.map((r) => <RouteTile key={`${r.from.slug}-${r.to.slug}`} r={r} onPick={fill} />)}</div>
              : <p className="tv-muted">No {modeOf(mode).noun} on Click. yet.</p>}
            <p className="small tv-muted">{home.data.priceNote}</p>
          </section>
          {home.data.offers.length > 0 && (
            <section className="tv-sec"><h2 className="tv-h2">Travel offers</h2>
              <div className="tv-offers">{home.data.offers.map((o) => (
                <article key={o.id} className="tv-offer"><Icon name="tag" size={18} /><div><strong>{o.title}</strong>
                  <span className="small tv-muted">{o.mode ? `${modeOf(o.mode).label} only` : 'All modes'}{o.minFare ? ` · fares from ₹${o.minFare}` : ''}{o.code ? ` · code ${o.code}` : ' · applied automatically'}
                    {' · until '}{fmtDate(o.endsAt, { day: 'numeric', month: 'short' })}</span></div></article>
              ))}</div></section>
          )}
          <section className="tv-sec" aria-labelledby="tv-disc">
            <h2 className="tv-h2" id="tv-disc">Travel discovery</h2>
            <div className="tv-collections">{collections.map((c) => (
              <article key={c.code} className={`tv-col tv-col--${c.code}`}>
                <h3>{c.title}</h3><p className="small tv-muted">{c.subtitle}</p>
                <ul>{c.routes.slice(0, 3).map((r) => (
                  <li key={`${r.mode}${r.from.slug}${r.to.slug}`}><button type="button" onClick={() => fill(r)}>
                    <Icon name={modeOf(r.mode).icon} size={14} /> {r.from.name} → {r.to.name}{r.fromPrice ? <span className="tv-muted"> · from {formatMoney(r.fromPrice)}</span> : null}
                  </button></li>
                ))}</ul>
              </article>
            ))}</div>
          </section>
        </>
      )}

      <section className="tv-plan">
        <div><span className="tv-kicker">Plan your journey</span><h2>Travel + Hotels + Shows + Events</h2>
          <p className="small tv-muted">Pick a destination and dates: we line up real journeys, stays, shows, events and places to visit there. Nothing is booked until you confirm each one.</p></div>
        <Link className="tv-btn" to="/travel/plan">Plan a trip</Link>
      </section>

      {authed && (
        <nav className="tv-mine" aria-label="My travel">
          <Link to="/travel/bookings"><Icon name="ticket" size={18} /> My journeys</Link>
          <Link to="/travel/me"><Icon name="user" size={18} /> Travellers, preferences &amp; fare alerts</Link>
          <Link to="/bookings/mine"><Icon name="history" size={18} /> All bookings</Link>
        </nav>
      )}
      <p className="small tv-muted tv-sep">{MODES.map((m) => m.label).join(', ')} only. Local rides are in <Link to="/rides">Ride</Link>; stays are in <Link to="/hotels">Hotels</Link>.</p>
    </div>
  );
}

function RouteTile({ r, onPick }: { r: TravelRoute; onPick: (r: TravelRoute) => void }) {
  return (
    <button type="button" className="tv-route-tile" onClick={() => onPick(r)} aria-label={`${r.from.name} to ${r.to.name} by ${r.mode}`}>
      <span className="tv-route-tile__ends"><strong>{r.from.name}</strong><Icon name="right" size={14} /><strong>{r.to.name}</strong></span>
      <span className="small tv-muted">{r.services} service{r.services === 1 ? '' : 's'} · {r.km.toLocaleString('en-IN')} km{r.minutes ? ` · from ${fmtDur(r.minutes)}` : ''}</span>
      {r.fromPrice && <span className="tv-route-tile__price">from {formatMoney(r.fromPrice)}</span>}
    </button>
  );
}
