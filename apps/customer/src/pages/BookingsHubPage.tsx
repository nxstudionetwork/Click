import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../auth/AuthProvider';
import { Button, ErrorState, Icon, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { fmtDay, GROUP_ICON, KIND_ICON, PlaceCard, todayIso } from '../features/bookings/parts';
import { useDeliveryLocation } from '../location/LocationProvider';
import { api } from '../lib/api';

/** Click. Bookings: discover places and experiences to book (temples, tourist spots, parks, tours, activities) with their
 *  own destination search — never forced to the Home location — and every reservation the customer holds across Click. */
export function BookingsHubPage() {
  useThemeOverride('bookings');
  const nav = useNavigate();
  const { status } = useAuth();
  const authed = status === 'authenticated';
  const { selected, point } = useDeliveryLocation();
  const [q, setQ] = useState('');
  const [date, setDate] = useState('');
  const home = useQuery({ queryKey: ['bookings', 'home', selected?.city ?? '', point?.lat ?? null],
    queryFn: () => api.bookings.home({ city: selected?.city, lat: point?.lat, lng: point?.lng }) });
  const mine = useQuery({ queryKey: ['bookings', 'reservations', 'upcoming', ''], queryFn: () => api.bookings.reservations('upcoming'), enabled: authed });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const p = new URLSearchParams();
    if (q.trim()) p.set('q', q.trim());
    if (date) p.set('date', date);
    nav(`/bookings/search?${p}`);
  };

  return (
    <div className="bk-page" data-theme="bookings">
      <section className="bk-hero">
        <span className="bk-kicker">Click. Bookings</span>
        <h1>Bookings</h1>
        <p className="bk-hero__tag">Discover places. Book experiences. Make memories.</p>
        <form className="bk-search" onSubmit={submit} role="search">
          <label className="bk-search__q"><span className="sr-only">Search places and experiences</span><Icon name="search" size={18} />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Where do you want to go or what do you want to book?" /></label>
          <label className="bk-search__date"><span className="small">Visit date</span><input type="date" min={todayIso()} value={date} onChange={(e) => setDate(e.target.value)} /></label>
          <Button type="submit">Search</Button>
        </form>
        <div className="bk-quick">{['Tirupati', 'Hyderabad', 'temple darshan', 'water park', 'museum', 'boat ride'].map((x) => (
          <Link key={x} to={`/bookings/search?q=${encodeURIComponent(x)}`}>{x}</Link>))}</div>
      </section>

      {authed && (mine.data?.results.length ?? 0) > 0 && (
        <section className="bk-sec" aria-labelledby="bk-mine">
          <div className="bk-sec__head"><h2 className="bk-h2" id="bk-mine">Coming up</h2><Link to="/bookings/mine" className="bk-more">My bookings ({mine.data!.counts.upcoming})</Link></div>
          <ul className="bk-resv">{mine.data!.results.slice(0, 3).map((r) => (
            <li key={r.id}><Link to={r.link} className="bk-resv__row" data-theme={r.theme}>
              <span className="bk-resv__icon"><Icon name={KIND_ICON[r.kind]} size={18} /></span>
              <span><strong>{r.title}</strong><span className="small bk-muted">{r.kindLabel} · {r.subtitle}{r.when ? ` · ${fmtDay(r.when)}` : ''}</span></span>
              <span className="small">{r.statusLabel}</span></Link></li>
          ))}</ul>
        </section>
      )}

      {home.isError ? <ErrorState error={home.error} onRetry={() => home.refetch()} /> : !home.data ? <><Skeleton height={90} radius={18} /><Skeleton height={260} radius={22} /></> : (
        <>
          <nav className="bk-rail" aria-label="Categories">
            {home.data.groups.map((g) => (
              <Link key={g.code} to={`/bookings/search?group=${g.code}`} className={`bk-cat bk-cat--${g.code}`}>
                <Icon name={GROUP_ICON[g.code] ?? 'ticket'} size={22} /><strong>{g.label}</strong>
                <span className="small">{g.kinds.filter((k) => k.count).slice(0, 4).map((k) => k.label).join(' · ') || `${g.count} places`}</span>
              </Link>
            ))}
            {home.data.services.map((s) => (
              <Link key={s.code} to={s.link} className="bk-cat bk-cat--svc" data-theme={s.theme}><Icon name={s.code === 'shows' ? 'film' : s.code === 'events' ? 'gift' : s.code === 'hotels' ? 'hotel' : 'bus'} size={22} />
                <strong>{s.title}</strong><span className="small">{s.subtitle}</span></Link>
            ))}
          </nav>

          {home.data.sections.map((s) => (
            <section key={s.code} className="bk-sec" aria-labelledby={`bk-${s.code}`}>
              <div className="bk-sec__head"><div><h2 className="bk-h2" id={`bk-${s.code}`}>{s.title}</h2><p className="small bk-muted">{s.subtitle}</p></div>
                <Link className="bk-more" to={`/bookings/search?${s.code === 'temples' ? 'group=spiritual' : s.code === 'tourist' ? 'group=tourist' : s.code === 'parks' ? 'group=parks'
                  : s.code === 'experiences' ? 'group=experiences' : s.code === 'family' ? 'kids=1&bookable=1' : s.code === 'popular' ? 'sort=popular' : s.code === 'top_rated' ? 'sort=rating'
                    : s.code === 'near' && selected?.city ? `city=${encodeURIComponent(selected.city)}` : ''}`}>See all</Link></div>
              <div className="bk-row">{s.items.map((a) => <PlaceCard key={a.id} a={a} />)}</div>
            </section>
          ))}

          <section className="bk-sec" aria-labelledby="bk-cities">
            <h2 className="bk-h2" id="bk-cities">Explore by city</h2>
            <div className="bk-cities">{home.data.cities.map((c) => (
              <Link key={c.name} to={`/bookings/search?city=${encodeURIComponent(c.name)}`} className="bk-city">
                <strong>{c.name}</strong><span className="small bk-muted">{c.region} · {c.count} place{c.count === 1 ? '' : 's'}{c.bookable ? ` · ${c.bookable} bookable` : ''}</span></Link>
            ))}</div>
          </section>
          <p className="small bk-muted">“Bookable through Click.” means an onboarded provider sells it here with live availability. “Information available” places are booked
            through their official channels — Click. never pretends to sell them.</p>
        </>
      )}
      {authed && <Link to="/bookings/mine" className="bk-btn bk-btn--ghost"><Icon name="history" size={16} /> All my bookings across Click.</Link>}
    </div>
  );
}
