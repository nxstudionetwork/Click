import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { StayQuery } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { ErrorState, Icon, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { addDays, fmtDay, GuestsPicker, HotelImage, stayQs, todayIso } from '../features/hotels/parts';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

const COLLECTION_FILTER: Record<string, string> = { family: 'room_class=family', business: 'amenities=wifi', luxury: 'stars=5', budget: 'max_price=2500' };
const DEST_ICON: Record<string, string> = { beach: 'drop', nature: 'leaf', city: 'store', business: 'briefcase', weekend: 'sparkle' };

/**
 * Click. Hotels: "Stay somewhere you'll love." The search panel is the centrepiece. The destination is what the
 * customer types — never forced from their current Click. location. Destinations, collections and offers are real data.
 */
export function HotelsPage() {
  useThemeOverride('hotels');
  const navigate = useNavigate();
  const { status } = useAuth();
  const home = useQuery({ queryKey: ['hotels', 'home'], queryFn: () => api.hotels.home(), staleTime: 300_000 });
  const upcoming = useQuery({ queryKey: ['hotels', 'bookings', 'upcoming'], queryFn: () => api.hotels.bookings('upcoming'), enabled: status === 'authenticated' });
  const [dest, setDest] = useState('');
  const [picked, setPicked] = useState<{ kind: string; value: string; label: string } | null>(null);
  const [stay, setStay] = useState<StayQuery>({ checkIn: addDays(todayIso(), 1), checkOut: addDays(todayIso(), 2), adults: 2, children: 0, rooms: 1 });
  const [debounced, setDebounced] = useState('');
  const [focus, setFocus] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { const t = setTimeout(() => setDebounced(dest.trim()), 200); return () => clearTimeout(t); }, [dest]);
  const suggest = useQuery({ queryKey: ['hotels', 'suggest', debounced], queryFn: () => api.hotels.destinations(debounced), enabled: debounced.length > 1 && !picked });

  const go = (destination: string, extra = '') => navigate(`/hotels/search?destination=${encodeURIComponent(destination)}&${stayQs(stay)}${extra ? `&${extra}` : ''}`);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!dest.trim()) return setError('Where do you want to stay?');
    if (stay.checkOut <= stay.checkIn) return setError('Check-out must be after check-in.');
    setError('');
    if (picked?.kind === 'property') return navigate(`/hotels/${picked.value}?${stayQs(stay)}`);
    go(picked?.value ?? dest.trim());
  };
  const d = home.data;

  return (
    <div className="ht-page" data-theme="hotels">
      <header className="ht-hero">
        <div className="ht-hero__glow" aria-hidden="true" />
        <span className="ht-kicker">Click. Hotels</span>
        <h1>Hotels</h1>
        <p className="ht-hero__tag">Stay somewhere you’ll love.</p>
      </header>

      <form className="ht-search" onSubmit={submit} role="search" aria-label="Search hotels">
        <div className="ht-field ht-field--dest">
          <label className="ht-field__label" htmlFor="ht-dest">Destination</label>
          <div className="ht-field__input"><Icon name="pin" size={16} />
            <input id="ht-dest" value={dest} autoComplete="off" placeholder="Where do you want to stay?" onFocus={() => setFocus(true)} onBlur={() => setTimeout(() => setFocus(false), 150)}
              onChange={(e) => { setDest(e.target.value); setPicked(null); }} aria-autocomplete="list" aria-controls="ht-suggest" />
          </div>
          {focus && !picked && debounced.length > 1 && (suggest.data?.results.length ?? 0) > 0 && (
            <ul className="ht-suggest" id="ht-suggest" role="listbox">
              {suggest.data!.results.map((r) => (
                <li key={`${r.kind}-${r.value}`} role="option" aria-selected={false}>
                  <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => { setPicked(r); setDest(r.label); setFocus(false); }}>
                    <Icon name={r.kind === 'property' ? 'hotel' : r.kind === 'landmark' ? 'compass' : 'pin'} size={16} />
                    <span><strong>{r.label}</strong><span className="small ht-muted">{r.detail}</span></span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <label className="ht-field"><span className="ht-field__label">Check-in</span>
          <input type="date" min={todayIso()} value={stay.checkIn} onChange={(e) => { const ci = e.target.value; setStay((s) => ({ ...s, checkIn: ci, checkOut: s.checkOut <= ci ? addDays(ci, 1) : s.checkOut })); }} />
        </label>
        <label className="ht-field"><span className="ht-field__label">Check-out</span>
          <input type="date" min={addDays(stay.checkIn, 1)} value={stay.checkOut} onChange={(e) => setStay((s) => ({ ...s, checkOut: e.target.value }))} />
        </label>
        <GuestsPicker value={stay} onChange={setStay} />
        <button type="submit" className="ht-btn ht-btn--big ht-search__go"><Icon name="search" size={18} /> Search hotels</button>
        {error && <p className="ht-error small" role="alert">{error}</p>}
      </form>

      {status === 'authenticated' && (upcoming.data?.results.length ?? 0) > 0 && (
        <section className="ht-sec">
          <header className="ht-sec__head"><div><span className="ht-kicker">Your next stay</span><h2>Upcoming</h2></div><Link to="/hotels/bookings" className="ht-more">All stays</Link></header>
          <div className="ht-upcoming">{upcoming.data!.results.slice(0, 2).map((b) => (
            <Link key={b.id} to={`/hotels/bookings/${b.id}`} className="ht-upc" style={{ ['--ht-accent' as string]: b.property.accent }}>
              <HotelImage src={b.property.imageUrl} name={b.property.name} accent={b.property.accent} />
              <span><span className="ht-kicker">{fmtDay(b.checkIn)} – {fmtDay(b.checkOut)}</span><strong>{b.property.name}</strong>
                <span className="small ht-muted">{b.roomName} · {b.statusLabel}</span></span>
            </Link>
          ))}</div>
        </section>
      )}

      {home.isError ? <ErrorState error={home.error} onRetry={() => home.refetch()} /> : home.isPending ? (
        <div className="ht-dests">{Array.from({ length: 6 }, (_, i) => <Skeleton key={i} height={150} radius={22} />)}</div>
      ) : d && (
        <>
          <section className="ht-sec">
            <header className="ht-sec__head"><div><span className="ht-kicker">Where Click. has stays</span><h2>Popular destinations</h2></div></header>
            <div className="ht-dests">{d.destinations.map((x, i) => (
              <button key={x.slug} type="button" className={`ht-dest${i === 0 ? ' ht-dest--wide' : ''}`} onClick={() => go(x.name)}>
                <span className="ht-dest__icon" aria-hidden="true"><Icon name={(DEST_ICON[x.tags[0] ?? ''] ?? 'pin') as never} size={18} /></span>
                <span className="ht-dest__name">{x.name}</span>
                <span className="small ht-muted">{x.tagline}</span>
                <span className="ht-dest__foot small"><span>{x.properties} stay{x.properties > 1 ? 's' : ''}</span>{x.fromPrice && <span>from {formatMoney(x.fromPrice)}</span>}</span>
              </button>
            ))}</div>
          </section>

          <section className="ht-sec">
            <header className="ht-sec__head"><div><span className="ht-kicker">Find your kind of stay</span><h2>Collections</h2></div></header>
            <div className="ht-rail">{d.collections.map((c) => (
              <div key={c.code} className="ht-col">
                <span className="ht-kicker">{c.properties} stay{c.properties > 1 ? 's' : ''}{c.fromPrice ? ` · from ${formatMoney(c.fromPrice)}` : ''}</span>
                <strong>{c.title}</strong><span className="small ht-muted">{c.subtitle}</span>
                <div className="ht-col__places">{c.destinations.map((p) => <button key={p} type="button" className="ht-chip" onClick={() => go(p, COLLECTION_FILTER[c.code] ?? '')}>{p}</button>)}</div>
              </div>
            ))}</div>
            <p className="small ht-muted">{d.priceNote}</p>
          </section>

          {d.offers.length > 0 && (
            <section className="ht-sec">
              <header className="ht-sec__head"><div><span className="ht-kicker">Applied automatically when your stay qualifies</span><h2>Offers</h2></div></header>
              <div className="ht-offers">{d.offers.map((o) => (
                <div key={o.id} className="ht-offer"><span className="ht-offer__pct">{o.percent}%</span>
                  <span><strong>{o.title}</strong><span className="small ht-muted">{o.property ?? 'All stays'}{o.conditions ? ` · ${o.conditions}` : ''}</span></span></div>
              ))}</div>
            </section>
          )}

          <section className="ht-sec ht-trust">
            <div><Icon name="shield" size={18} /><span><strong>Prices you can trust</strong><span className="small ht-muted">Room price, taxes and any offer are shown before you pay.</span></span></div>
            <div><Icon name="check" size={18} /><span><strong>Policies up front</strong><span className="small ht-muted">The cancellation deadline and refund are on every room.</span></span></div>
            <div><Icon name="star" size={18} /><span><strong>Verified reviews</strong><span className="small ht-muted">Only guests who stayed through Click. can review.</span></span></div>
          </section>
          {status === 'authenticated' && <Link to="/hotels/bookings" className="ht-more" style={{ alignSelf: 'center' }}>My stays &amp; saved hotels</Link>}
        </>
      )}
    </div>
  );
}
