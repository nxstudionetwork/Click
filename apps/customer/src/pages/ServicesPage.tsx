import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../auth/AuthProvider';
import { EmptyState, ErrorState, Icon, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { servicePhoto } from '../config/media';
import { catIcon, ProCardView, Section } from '../features/pros/parts';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';
import { LocationSelector } from '../location/LocationSelector';
import { useDeliveryLocation } from '../location/LocationProvider';

/**
 * Click. Services: local professionals. Hero, "Need help now?", search, category rail, then real professionals in
 * several formats (available now, popular near you, by group, trusted), offers, My Professionals, your bookings and
 * "Can't find your service?". Only categories with professionals serving the selected address are shown.
 */
export function ServicesPage() {
  useThemeOverride('services');
  const { status } = useAuth();
  const navigate = useNavigate();
  const { selected } = useDeliveryLocation();
  const address = selected?.id ?? null;
  const home = useQuery({ queryKey: ['services', 'home', address], queryFn: () => api.services.home({ address }), staleTime: 60_000 });
  const favorites = useQuery({ queryKey: ['services', 'favorites', address], queryFn: () => api.services.favorites(address), enabled: status === 'authenticated' });
  const active = useQuery({ queryKey: ['services', 'bookings', 'active'], queryFn: () => api.services.bookings('active'), enabled: status === 'authenticated' });
  const upcoming = useQuery({ queryKey: ['services', 'bookings', 'upcoming'], queryFn: () => api.services.bookings('upcoming'), enabled: status === 'authenticated' });
  const [q, setQ] = useState('');
  const [debounced, setDebounced] = useState('');
  useEffect(() => { const t = setTimeout(() => setDebounced(q.trim()), 250); return () => clearTimeout(t); }, [q]);
  const search = useQuery({ queryKey: ['services', 'search', debounced, address], queryFn: () => api.services.search(debounced, address), enabled: debounced.length > 1 });
  const photo = servicePhoto('services');
  const d = home.data;
  const mine = [...(active.data?.results ?? []), ...(upcoming.data?.results ?? [])];

  return (
    <div className="sv-page" data-theme="services">
      <header className="sv-hero">
        {photo && <img className="sv-hero__img" src={photo.src} srcSet={photo.srcSet} sizes="(min-width: 900px) 50vw, 100vw" alt="" />}
        <div className="sv-hero__text">
          <span className="sv-kicker">Click. Services</span>
          <h1>Services<span>.</span></h1>
          <p>Skilled people. Right when you need them.</p>
        </div>
      </header>

      <div className="sv-where"><LocationSelector /></div>

      <section className="sv-now" aria-labelledby="sv-now-h">
        <div>
          <h2 id="sv-now-h">Need help now?</h2>
          <p>Find an available professional near you — a leak, a power issue, a broken appliance, urgent cleaning or carpentry.</p>
          {d && <p className="small sv-now__live">{d.availableNow.length ? `${d.availableNow.length} professional${d.availableNow.length > 1 ? 's are' : ' is'} available near you right now.`
            : d.hasLocation ? 'Nobody is free right now. You can still schedule a time.' : 'Choose a saved address to check who is free near you.'}</p>}
        </div>
        <Link to="/services/book?mode=now" className="sv-btn sv-btn--big"><Icon name="sparkle" size={18} /> Get Help Now</Link>
      </section>

      <div className="sv-search" role="search">
        <Icon name="search" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="What do you need help with?" aria-label="What do you need help with?"
          onKeyDown={(e) => { if (e.key === 'Enter' && search.data?.categories[0]) navigate(`/services/${search.data.categories[0].slug}`); }} />
        {q && <button type="button" className="sv-search__clear" aria-label="Clear" onClick={() => setQ('')}><Icon name="close" size={16} /></button>}
      </div>
      {debounced.length > 1 && (
        <div className="sv-results" aria-live="polite">
          {search.isPending ? <Skeleton height={60} /> : search.data && (search.data.categories.length + search.data.jobs.length + search.data.professionals.length === 0 ? (
            <p className="small sv-muted">No service matches “{debounced}”. <Link to={`/services/request?text=${encodeURIComponent(debounced)}`}>Tell Click what you need</Link>.</p>
          ) : (
            <>
              {search.data.categories.map((c) => <Link key={c.slug} to={`/services/${c.slug}`} className="sv-result"><Icon name={catIcon(c.icon)} size={18} /><span><strong>{c.name}</strong><span className="small sv-muted">{c.summary}</span></span></Link>)}
              {search.data.jobs.slice(0, 4).map((j) => <Link key={j.id} to={`/services/${j.category!.slug}?job=${j.id}`} className="sv-result"><Icon name="wrench" size={18} /><span><strong>{j.name}</strong><span className="small sv-muted">{j.category!.name} · {j.priceLabel}</span></span></Link>)}
              {search.data.professionals.slice(0, 3).map((p) => <Link key={p.id} to={`/services/pro/${p.id}`} className="sv-result"><Icon name="user" size={18} /><span><strong>{p.name}</strong><span className="small sv-muted">{p.profession} · {p.availabilityLabel}</span></span></Link>)}
            </>
          ))}
        </div>
      )}

      {home.isError ? <ErrorState error={home.error} onRetry={() => home.refetch()} /> : home.isPending ? (
        <><div className="sv-rail">{Array.from({ length: 7 }, (_, i) => <Skeleton key={i} width={92} height={96} radius={20} />)}</div><Skeleton height={220} radius={22} /></>
      ) : d!.categories.length === 0 ? (
        <EmptyState icon="wrench" title="No professionals serve this address yet" message="Try another saved address, or tell Click what you need."
          action={<Link to="/services/request" className="btn btn--primary">Tell Click what you need</Link>} />
      ) : (
        <>
          <nav className="sv-rail" aria-label="Services">
            {d!.categories.map((c) => (
              <Link key={c.slug} to={`/services/${c.slug}`} className="sv-cat" style={{ ['--sv-accent' as string]: c.accent }}>
                <span className="sv-cat__icon"><Icon name={catIcon(c.icon)} size={22} /></span><span className="sv-cat__name">{c.name}</span>
              </Link>
            ))}
            <Link to="/services/request" className="sv-cat"><span className="sv-cat__icon"><Icon name="plus" size={22} /></span><span className="sv-cat__name">Other services</span></Link>
          </nav>

          {mine.length > 0 && (
            <Section title="Your bookings" kicker="In progress" action={<Link to="/services/bookings" className="sv-more">All</Link>}>
              <div className="sv-mine">{mine.slice(0, 3).map((b) => (
                <Link key={b.id} to={`/services/bookings/${b.id}`} className="sv-minecard" style={{ ['--sv-accent' as string]: b.category.accent }}>
                  <span className="sv-kicker">{b.number}</span><strong>{b.job.name}</strong>
                  <span className="small">{b.provider ? b.provider.name : b.requestedProvider ? `Asked ${b.requestedProvider.name}` : 'Finding a professional'} · {b.statusLabel}</span>
                </Link>
              ))}</div>
            </Section>
          )}

          {d!.availableNow.length > 0 && (
            <Section title="Need it now?" kicker="Available now" action={<Link to="/services/book?mode=now" className="sv-more">Get help now</Link>}>
              <div className="sv-prorail">{d!.availableNow.map((p) => <ProCardView key={p.id} p={p} />)}</div>
            </Section>
          )}
          {d!.popular.length > 0 && <Section title="Popular near you" kicker="Most booked"><div className="sv-prorail">{d!.popular.map((p) => <ProCardView key={p.id} p={p} />)}</div></Section>}

          <div className="sv-groups">
            {d!.groups.map((g) => (
              <section key={g.code} className="sv-group">
                <h3>{g.label}</h3>
                <div className="sv-group__list">
                  {g.categories.map((c) => (
                    <Link key={c.slug} to={`/services/${c.slug}`} className="sv-grouprow" style={{ ['--sv-accent' as string]: c.accent }}>
                      <span className="sv-cat__icon sv-cat__icon--sm"><Icon name={catIcon(c.icon)} size={18} /></span>
                      <span><strong>{c.name}</strong><span className="small sv-muted">{c.summary}</span></span>
                      <span className="small sv-muted">{c.professionals} pro{c.professionals === 1 ? '' : 's'}</span>
                    </Link>
                  ))}
                </div>
              </section>
            ))}
          </div>

          {d!.trusted.length > 0 && <Section title="Trusted professionals" kicker="Verified · rated 4.5+ by 3+ customers"><div className="sv-prorail">{d!.trusted.map((p) => <ProCardView key={p.id} p={p} />)}</div></Section>}

          {d!.offers.length > 0 && (
            <Section title="Offers" kicker="Applied automatically to the final bill">
              <div className="sv-offers">{d!.offers.map((o) => (
                <div key={o.id} className="sv-offer"><Icon name="tag" size={18} /><span><strong>{o.title}</strong>
                  <span className="small sv-muted">{o.description}{o.minAmount ? ` · min ${formatMoney(o.minAmount)}` : ''}{o.categoryName ? ` · ${o.categoryName}` : ''}</span></span></div>
              ))}</div>
            </Section>
          )}

          {(favorites.data?.results.length ?? 0) > 0 && (
            <Section title="My Professionals" kicker="Saved" action={<Link to="/wishlist" className="sv-more">Manage</Link>}>
              <div className="sv-prorail">{favorites.data!.results.map((p) => (
                <ProCardView key={p.id} p={p} extra={p.lastBooking ? <Link to={`/services/book?pro=${p.id}`} className="sv-link small">Book again</Link> : undefined} />
              ))}</div>
            </Section>
          )}
        </>
      )}

      <section className="sv-cant">
        <div><h2>Can’t find your service?</h2><p>Tell Click what you need. We review every request and look for a suitable professional.</p></div>
        <Link to="/services/request" className="sv-btn sv-btn--ghost">Tell Click what you need</Link>
      </section>
      {status === 'authenticated' && <Link to="/services/bookings" className="sv-link small" style={{ alignSelf: 'center' }}>Service history</Link>}
    </div>
  );
}
