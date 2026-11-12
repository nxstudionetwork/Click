import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type SavedTraveller, type TravelPreferences } from '@click/api';
import { Button, EmptyState, Icon, Skeleton, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { fmtDate, modeOf, searchQs } from '../features/travel/parts';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

const BERTH = [['', 'No preference'], ['LB', 'Lower'], ['MB', 'Middle'], ['UB', 'Upper'], ['SL', 'Side lower'], ['SU', 'Side upper']];
const blank = { name: '', age: 30, gender: 'female' as SavedTraveller['gender'], berthPreference: '' };

/** Saved travellers (name, age, gender, berth preference only), travel preferences used as search defaults, saved
 *  routes and fare alerts. All stored on the customer's Click. account. */
export function TravelMePage() {
  useThemeOverride('travel');
  const qc = useQueryClient();
  const toast = useToast();
  const tq = useQuery({ queryKey: ['travel', 'travellers'], queryFn: () => api.travel.travellers() });
  const pq = useQuery({ queryKey: ['travel', 'prefs'], queryFn: () => api.travel.preferences() });
  const aq = useQuery({ queryKey: ['travel', 'alerts'], queryFn: () => api.travel.alerts() });
  const rq = useQuery({ queryKey: ['travel', 'routes'], queryFn: () => api.travel.routes() });
  const [form, setForm] = useState<typeof blank & { id?: string }>(blank);
  const [err, setErr] = useState('');
  const fail = (e: unknown) => toast(e instanceof ApiError ? e.message : 'Couldn’t save.', 'error');
  const saveT = useMutation({
    mutationFn: () => (form.id ? api.travel.updateTraveller(form.id, form) : api.travel.addTraveller(form)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['travel', 'travellers'] }); setForm(blank); toast('Traveller saved'); }, onError: fail,
  });
  const delT = useMutation({ mutationFn: (id: string) => api.travel.removeTraveller(id), onSuccess: () => qc.invalidateQueries({ queryKey: ['travel', 'travellers'] }), onError: fail });
  const savePrefs = useMutation({ mutationFn: (p: Partial<TravelPreferences>) => api.travel.savePreferences(p), onSuccess: (p) => { qc.setQueryData(['travel', 'prefs'], p); toast('Preferences saved'); }, onError: fail });
  const delA = useMutation({ mutationFn: (id: string) => api.travel.removeAlert(id), onSuccess: () => qc.invalidateQueries({ queryKey: ['travel', 'alerts'] }), onError: fail });
  const delR = useMutation({ mutationFn: (id: string) => api.customer.wishlist.remove(id), onSuccess: () => qc.invalidateQueries({ queryKey: ['travel'] }), onError: fail });
  const p = pq.data;
  const toggleBus = (v: string) => p && savePrefs.mutate({ busTypes: p.busTypes.includes(v) ? p.busTypes.filter((x) => x !== v) : [...p.busTypes, v] });

  return (
    <div className="tv-page" data-theme="travel">
      <Link to="/travel" className="tv-backlink"><Icon name="back" size={18} /> Travel</Link>
      <h1 className="tv-title">My travel</h1>

      <section className="tv-sec" aria-labelledby="tv-trav">
        <h2 className="tv-h2" id="tv-trav">Saved travellers</h2>
        <p className="small tv-muted">Only what bookings need — no ID numbers are stored.</p>
        {!tq.data ? <Skeleton height={60} /> : tq.data.results.length === 0 ? <p className="tv-muted small">No saved travellers yet.</p> : (
          <ul className="tv-mylist">{tq.data.results.map((t) => (
            <li key={t.id} className="tv-myrow"><Icon name="user" size={18} /><span><strong>{t.name}</strong><span className="small tv-muted">{t.age} · {t.gender}{t.berthPreference ? ` · prefers ${BERTH.find(([v]) => v === t.berthPreference)?.[1]}` : ''}</span></span>
              <span className="tv-myrow__end"><button type="button" className="tv-link small" onClick={() => setForm({ ...t })}>Edit</button>
                <button type="button" className="tv-link small" onClick={() => delT.mutate(t.id)}>Remove</button></span></li>
          ))}</ul>
        )}
        <form className="tv-form tv-form--inline" onSubmit={(e) => { e.preventDefault(); if (!/^[A-Za-z][A-Za-z .'-]{1,79}$/.test(form.name.trim())) return setErr('Enter a name (letters only).'); setErr(''); saveT.mutate(); }}>
          <h3 className="tv-h3">{form.id ? 'Edit traveller' : 'Add passenger'}</h3>
          <label className="tv-field"><span className="tv-field__label">Name</span><input className="tv-field__input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <div className="tv-row3">
            <label className="tv-field"><span className="tv-field__label">Age</span><input className="tv-field__input" inputMode="numeric" value={form.age || ''} onChange={(e) => setForm({ ...form, age: Number(e.target.value.replace(/\D/g, '')) || 0 })} /></label>
            <label className="tv-field"><span className="tv-field__label">Gender</span><select className="tv-field__input" value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value as SavedTraveller['gender'] })}><option value="female">Female</option><option value="male">Male</option><option value="other">Other</option></select></label>
            <label className="tv-field"><span className="tv-field__label">Berth</span><select className="tv-field__input" value={form.berthPreference} onChange={(e) => setForm({ ...form, berthPreference: e.target.value })}>{BERTH.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
          </div>
          {err && <p className="tv-error small">{err}</p>}
          <div className="tv-row2"><Button type="submit" loading={saveT.isPending}>{form.id ? 'Save changes' : 'Add passenger'}</Button>{form.id && <Button variant="secondary" onClick={() => setForm(blank)}>Cancel</Button>}</div>
        </form>
      </section>

      <section className="tv-sec" aria-labelledby="tv-prefs">
        <h2 className="tv-h2" id="tv-prefs">Travel preferences</h2>
        <p className="small tv-muted">Used to pre-select filters. They never guarantee a seat, class or airline.</p>
        {!p ? <Skeleton height={120} /> : (
          <div className="tv-prefs">
            <fieldset className="tv-fgroup"><legend>Bus</legend>{[['sleeper', 'Sleeper'], ['seater', 'Seater'], ['ac', 'AC']].map(([v, l]) => (
              <label key={v} className="tv-check"><input type="checkbox" checked={p.busTypes.includes(v!)} onChange={() => toggleBus(v!)} /> {l}</label>))}
              <label className="tv-mini"><span className="small">Preferred departure</span><select value={p.busDeparture} onChange={(e) => savePrefs.mutate({ busDeparture: e.target.value })}>
                {[['', 'Any time'], ['morning', 'Morning'], ['afternoon', 'Afternoon'], ['evening', 'Evening'], ['night', 'Night']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label></fieldset>
            <fieldset className="tv-fgroup"><legend>Train</legend>
              <label className="tv-mini"><span className="small">Class</span><select value={p.trainClass} onChange={(e) => savePrefs.mutate({ trainClass: e.target.value })}>
                {[['', 'Any'], ['SL', 'Sleeper'], ['3A', 'AC 3 Tier'], ['2A', 'AC 2 Tier'], ['1A', 'First AC'], ['CC', 'Chair Car'], ['EC', 'Executive']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
              <label className="tv-mini"><span className="small">Berth</span><select value={p.berth} onChange={(e) => savePrefs.mutate({ berth: e.target.value })}>{BERTH.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label></fieldset>
            <fieldset className="tv-fgroup"><legend>Flight</legend>
              <label className="tv-mini"><span className="small">Cabin</span><select value={p.flightCabin} onChange={(e) => savePrefs.mutate({ flightCabin: e.target.value })}>
                {[['', 'Any'], ['economy', 'Economy'], ['premium_economy', 'Premium Economy'], ['business', 'Business']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
              <label className="tv-check"><input type="checkbox" checked={p.nonstop} onChange={(e) => savePrefs.mutate({ nonstop: e.target.checked })} /> Prefer non-stop</label>
              {p.airlineOptions.map((a) => <label key={a.id} className="tv-check"><input type="checkbox" checked={p.airlines.includes(a.id)}
                onChange={() => savePrefs.mutate({ airlines: p.airlines.includes(a.id) ? p.airlines.filter((x) => x !== a.id) : [...p.airlines, a.id] })} /> {a.name}</label>)}</fieldset>
          </div>
        )}
      </section>

      <section className="tv-sec" aria-labelledby="tv-alerts">
        <h2 className="tv-h2" id="tv-alerts">Fare alerts</h2>
        <p className="small tv-muted">We re-check the lowest fare with the same search the app uses and notify you when it changes. Follow a journey from its results page.</p>
        {!aq.data ? <Skeleton height={60} /> : aq.data.results.length === 0 ? <EmptyState icon="bell" title="No fare alerts" message="Open a search and tap “Fare alert”." /> : (
          <ul className="tv-mylist">{aq.data.results.map((a) => (
            <li key={a.id} className="tv-myrow"><Icon name={modeOf(a.mode).icon} size={18} />
              <Link to={`/travel/search?${searchQs({ mode: a.mode, origin: a.origin.slug, destination: a.destination.slug, date: a.date, adults: 1, children: 0, infants: 0 })}`}>
                <strong>{a.origin.name} → {a.destination.name}</strong><span className="small tv-muted">{fmtDate(a.date)} · {a.isActive ? (a.lastFare ? `lowest ${formatMoney(a.lastFare)}` : 'no fares yet') : 'date passed'}</span></Link>
              <span className="tv-myrow__end"><button type="button" className="tv-link small" onClick={() => delA.mutate(a.id)}>Stop</button></span></li>
          ))}</ul>
        )}
      </section>

      <section className="tv-sec" aria-labelledby="tv-routes">
        <h2 className="tv-h2" id="tv-routes">My routes</h2>
        {!rq.data ? <Skeleton height={40} /> : rq.data.results.length === 0 ? <p className="small tv-muted">Save a route from its results page.</p> : (
          <div className="tv-chips">{rq.data.results.map((r) => (
            <span key={r.favoriteId} className="tv-chip"><Link to={`/travel?to=${r.destination.slug}`}>{r.origin.name} → {r.destination.name}</Link>
              <button type="button" aria-label={`Remove ${r.origin.name} to ${r.destination.name}`} onClick={() => delR.mutate(r.favoriteId)}><Icon name="close" size={12} /></button></span>
          ))}</div>
        )}
      </section>
    </div>
  );
}
