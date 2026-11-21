import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQueries, useQuery } from '@tanstack/react-query';
import type { TravelPlace } from '@click/api';
import { Button, Icon } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { addDays, fmtDate, modeOf, MODES, PlaceField, searchQs, todayIso } from '../features/travel/parts';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

const KEY = 'click.tripPlan';
interface Plan { from: TravelPlace | null; to: TravelPlace | null; start: string; end: string; picks: string[] }

function load(): Plan | null {
  try { const p = JSON.parse(localStorage.getItem(KEY) ?? 'null') as Plan | null; return p && p.start >= todayIso() ? p : null; } catch { return null; }
}

/** Plan your journey: one destination and dates, and what Click. really has for it — journeys (bus / train / flight),
 *  stays, places and experiences to book, shows and events — each linking into its own booking flow. Nothing is booked
 *  here; the checklist is kept on this device. */
export function TravelPlanPage() {
  useThemeOverride('travel');
  const saved = load();
  const [from, setFrom] = useState<TravelPlace | null>(saved?.from ?? null);
  const [to, setTo] = useState<TravelPlace | null>(saved?.to ?? null);
  const [start, setStart] = useState(saved?.start ?? addDays(todayIso(), 7));
  const [end, setEnd] = useState(saved?.end ?? addDays(todayIso(), 10));
  const [picks, setPicks] = useState<string[]>(saved?.picks ?? []);
  const ready = !!from && !!to && from.citySlug !== to.citySlug && end > start;
  useEffect(() => { try { localStorage.setItem(KEY, JSON.stringify({ from, to, start, end, picks })); } catch { /* storage off */ } }, [from, to, start, end, picks]);

  const base = { origin: from?.citySlug ?? '', destination: to?.citySlug ?? '', date: start, adults: 1, children: 0, infants: 0 };
  const travel = useQueries({ queries: MODES.map((m) => ({ queryKey: ['travel', 'plan', m.id, base], enabled: ready, retry: false,
    queryFn: () => api.travel.search({ ...base, mode: m.id }, { available_only: '1', sort: 'price' }) })) });
  const back = useQueries({ queries: MODES.map((m) => ({ queryKey: ['travel', 'plan-back', m.id, base, end], enabled: ready, retry: false,
    queryFn: () => api.travel.search({ ...base, origin: base.destination, destination: base.origin, date: end, mode: m.id }, { available_only: '1', sort: 'price' }) })) });
  const hotels = useQuery({ queryKey: ['hotels', 'dest', to?.city], enabled: ready, queryFn: () => api.hotels.destinations(to!.city) });
  const places = useQuery({ queryKey: ['bookings', 'plan', to?.city], enabled: ready, queryFn: () => api.bookings.search({ city: to!.city, bookable: '1' }) });
  const dest = hotels.data?.results.find((r) => r.kind === 'destination' && r.label.toLowerCase() === to?.city.toLowerCase());
  const toggle = (k: string) => setPicks((p) => (p.includes(k) ? p.filter((x) => x !== k) : [...p, k]));
  const nights = Math.round((new Date(`${end}T00:00:00`).getTime() - new Date(`${start}T00:00:00`).getTime()) / 86400000);

  return (
    <div className="tv-page" data-theme="travel">
      <Link to="/travel" className="tv-backlink"><Icon name="back" size={18} /> Travel</Link>
      <span className="tv-kicker">Plan your journey</span>
      <h1 className="tv-title">{to ? `Plan your ${to.city} trip` : 'Plan a trip'}</h1>
      <p className="small tv-muted">Travel + Hotels + Shows + Events, from what’s really on Click. Each item opens its own booking — nothing is booked until you confirm it there.</p>
      <section className="tv-search tv-search--flat">
        <div className="tv-search__ends">
          <PlaceField label="From" mode="bus" value={from} onPick={setFrom} />
          <PlaceField label="Going to" mode="bus" value={to} onPick={setTo} />
        </div>
        <div className="tv-search__row">
          <label className="tv-field"><span className="tv-field__label">Leave</span><input className="tv-field__input" type="date" min={todayIso()} value={start} onChange={(e) => { setStart(e.target.value); if (end <= e.target.value) setEnd(addDays(e.target.value, 1)); }} /></label>
          <label className="tv-field"><span className="tv-field__label">Return</span><input className="tv-field__input" type="date" min={addDays(start, 1)} value={end} onChange={(e) => setEnd(e.target.value)} /></label>
        </div>
        {from && to && from.citySlug === to.citySlug && <p className="tv-error small">Choose a destination different from where you start.</p>}
      </section>

      {ready && (
        <ol className="tv-itin" aria-label="Trip plan">
          <li className="tv-itin__step">
            <h2 className="tv-h3"><Icon name="bus" size={16} /> Travel there · {fmtDate(start)}</h2>
            <PlanTravel results={travel.map((t) => t.data)} picks={picks} toggle={toggle} prefix="out" qs={(m) => searchQs({ ...base, mode: m })} />
          </li>
          <li className="tv-itin__step">
            <h2 className="tv-h3"><Icon name="hotel" size={16} /> Stay · {nights} night{nights === 1 ? '' : 's'}</h2>
            {dest ? <label className="tv-plan-item"><input type="checkbox" checked={picks.includes('stay')} onChange={() => toggle('stay')} />
              <Link to={`/hotels/search?destination=${dest.value}&check_in=${start}&check_out=${end}&adults=1&rooms=1`}>Hotels in {to!.city} · {fmtDate(start, { day: 'numeric', month: 'short' })} – {fmtDate(end, { day: 'numeric', month: 'short' })}</Link></label>
              : <p className="small tv-muted">{hotels.isFetching ? 'Checking stays…' : `No Click. Hotels in ${to!.city} yet.`}</p>}
          </li>
          <li className="tv-itin__step">
            <h2 className="tv-h3"><Icon name="temple" size={16} /> Places &amp; experiences</h2>
            {places.data?.results.length ? places.data.results.slice(0, 5).map((a) => (
              <label key={a.id} className="tv-plan-item"><input type="checkbox" checked={picks.includes(`place:${a.slug}`)} onChange={() => toggle(`place:${a.slug}`)} />
                <Link to={`/bookings/places/${a.slug}`}>{a.name}<span className="small tv-muted"> · {a.kindLabel}{a.fromPrice ? ` · from ${formatMoney(a.fromPrice)}` : ''}</span></Link></label>
            )) : <p className="small tv-muted">{places.isFetching ? 'Looking…' : `Nothing bookable in ${to!.city} on Click. yet.`} <Link to={`/bookings/search?city=${encodeURIComponent(to!.city)}`}>See places to visit</Link></p>}
          </li>
          <li className="tv-itin__step">
            <h2 className="tv-h3"><Icon name="film" size={16} /> Shows &amp; events</h2>
            <label className="tv-plan-item"><input type="checkbox" checked={picks.includes('shows')} onChange={() => toggle('shows')} /> <Link to="/showtime">See what’s on in Showtime</Link></label>
            <label className="tv-plan-item"><input type="checkbox" checked={picks.includes('events')} onChange={() => toggle('events')} /> <Link to="/events">Plan an event with a Click. team</Link></label>
          </li>
          <li className="tv-itin__step">
            <h2 className="tv-h3"><Icon name="swap" size={16} /> Travel back · {fmtDate(end)}</h2>
            <PlanTravel results={back.map((t) => t.data)} picks={picks} toggle={toggle} prefix="back"
              qs={(m) => searchQs({ ...base, origin: base.destination, destination: base.origin, date: end, mode: m })} />
          </li>
        </ol>
      )}
      {ready && <p className="small tv-muted">{picks.length} item{picks.length === 1 ? '' : 's'} on your checklist · saved on this device. <Button variant="ghost" size="sm" onClick={() => setPicks([])}>Clear</Button></p>}
    </div>
  );
}

function PlanTravel({ results, picks, toggle, prefix, qs }: {
  results: (Awaited<ReturnType<typeof api.travel.search>> | undefined)[]; picks: string[]; toggle: (k: string) => void; prefix: string; qs: (m: 'bus' | 'train' | 'flight') => string;
}) {
  return (
    <>{MODES.map((m, i) => {
      const r = results[i];
      const k = `${prefix}:${m.id}`;
      return (
        <label key={m.id} className="tv-plan-item"><input type="checkbox" checked={picks.includes(k)} onChange={() => toggle(k)} disabled={!r?.count} />
          {r?.count ? <Link to={`/travel/search?${qs(m.id)}`}>{modeOf(m.id).label}: {r.count} with seats{r.results[0]?.lowest ? ` · from ${formatMoney(r.results[0].lowest)}` : ''}</Link>
            : <span className="tv-muted">{modeOf(m.id).label}: {r ? 'none on this route / date' : 'checking…'}</span>}
        </label>
      );
    })}</>
  );
}
