import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../auth/AuthProvider';
import { EmptyState, ErrorState, Icon, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { GrocerySearchField } from '../features/groceries/GrocerySearch';
import { BasketBar, CategoryRail, ProductCard, Rail, Section, StoreCard } from '../features/groceries/parts';
import { useGroceryAt } from '../features/groceries/useGroceries';
import { api } from '../lib/api';
import { LocationSelector } from '../location/LocationSelector';
import { formatMoney } from '../lib/format';

/**
 * Click. Groceries: local stores near the selected address. Order: title + line, delivery location, search,
 * categories, stores near you, then only sections with real data (fresh, deals, essentials, dairy, buy again,
 * fast delivery, support local, snacks, home, personal care, more), with the shopping list and Food cross-links.
 */
export function GroceriesPage() {
  useThemeOverride('grocery');
  const { status } = useAuth();
  const { at, key } = useGroceryAt();
  const home = useQuery({ queryKey: ['groceries', 'home', key, status], queryFn: () => api.groceries.home(at), staleTime: 60_000 });
  const d = home.data;
  const section = (code: string) => d?.sections.find((s) => s.code === code);
  const sec = (code: string, subtitle: string) => {
    const s = section(code);
    if (!s) return null;
    return (
      <Section title={s.title} subtitle={subtitle} action={<Link className="gr-more" to={`/groceries/search?section=${code}&q=`}>See all</Link>}>
        <Rail items={s.items} />
      </Section>
    );
  };

  return (
    <div className="gr-page" data-theme="grocery">
      <header className="gr-intro">
        <h1>Groceries<span>.</span></h1>
        <p>Fresh essentials. From stores near you.</p>
      </header>

      <div className="gr-where">
        <LocationSelector />
        {status === 'authenticated' && !home.isPending && d && !d.hasLocation && (
          <p className="small gr-note"><Icon name="pin" size={14} /> Add a map pin to this address (Profile → Addresses) so we can check which stores deliver to you and how fast.</p>
        )}
      </div>

      <GrocerySearchField />

      {home.isError ? <ErrorState error={home.error} onRetry={() => home.refetch()} /> : home.isPending ? (
        <>
          <div className="gr-cats">{Array.from({ length: 7 }, (_, i) => <Skeleton key={i} width={84} height={92} radius={18} />)}</div>
          <div className="gr-stores">{Array.from({ length: 3 }, (_, i) => <Skeleton key={i} height={150} radius={20} />)}</div>
          <div className="gr-rail">{Array.from({ length: 5 }, (_, i) => <Skeleton key={i} height={260} radius={18} />)}</div>
        </>
      ) : d!.stores.length === 0 ? (
        <EmptyState icon="store" title="No grocery stores deliver here yet"
          message={d!.hasLocation ? 'No grocery stores are available for this location yet. Try another saved address.' : 'Choose a delivery location to see stores near you.'}
          action={<Link to="/account/addresses" className="btn btn--outline">Manage addresses</Link>} />
      ) : (
        <>
          <CategoryRail cats={d!.categories} to={(slug) => `/groceries/search?category=${slug}`} />

          <Section title="Stores Near You" subtitle={d!.hasLocation ? 'Local stores that deliver to your address, nearest first.' : 'Set a delivery location to see delivery times and fees.'}>
            <div className="gr-stores">{d!.stores.slice(0, 6).map((s) => <StoreCard key={s.id} s={s} />)}</div>
          </Section>

          {(d!.runningLow.length > 0 || d!.buyAgain.length > 0) && (
            <Section title="Buy Again" subtitle="From your delivered grocery orders, at today’s price and stock."
              action={<Link className="gr-more" to="/groceries/buy-again">See all</Link>}>
              {d!.runningLow.length > 0 && (
                <div className="gr-lowlist" aria-label="Running low">
                  {d!.runningLow.map((r) => (
                    <div key={r.listing.id} className="gr-low">
                      <Icon name="history" size={16} />
                      <span><strong>{r.listing.name}</strong> — you usually reorder about every {r.usualDays} days. You may be ready to reorder.</span>
                    </div>
                  ))}
                </div>
              )}
              <div className="gr-rail">{d!.buyAgain.map((b) => <ProductCard key={b.listing.id} l={b.listing} />)}</div>
            </Section>
          )}

          {sec('fresh', d!.freshToday ? `${d!.freshToday} store${d!.freshToday > 1 ? 's' : ''} restocked produce today.` : 'Vegetables, fruit and greens from stores nearby.')}

          {(d!.offers.length > 0 || d!.deals.length > 0) && (
            <Section title="Deals From Local Stores" subtitle="Offers set by each store. Applied at checkout by the server.">
              {d!.offers.length > 0 && (
                <div className="gr-offers">
                  {d!.offers.map((o) => (
                    <Link key={o.id} to={`/groceries/store/${o.store.slug}`} className="gr-offer">
                      <Icon name="tag" size={18} />
                      <span><strong>{o.title}</strong><span className="small muted">{o.store.name}{o.minOrder && Number(o.minOrder) > 0 ? ` · min ${formatMoney(o.minOrder)}` : ''}{!o.redeemable ? ' · in-store promotion' : ''}</span></span>
                    </Link>
                  ))}
                </div>
              )}
              {d!.deals.length > 0 && <Rail items={d!.deals} />}
            </Section>
          )}

          {sec('essentials', 'Rice, atta, dal, oil and spices.')}
          {sec('dairy', 'Milk, curd, eggs, bread and breakfast.')}

          {d!.fast.length > 0 && (
            <Section title="Need It Fast?" subtitle="Estimated from each store’s packing time, distance and current orders.">
              <div className="gr-fast">
                {d!.fast.map((s) => (
                  <Link key={s.id} to={`/groceries/store/${s.slug}`} className="gr-fastcard">
                    <span className="gr-fastcard__eta">{s.etaMin}–{s.etaMax}<small> min</small></span>
                    <strong>{s.name}</strong>
                    <span className="small muted">{s.distanceKm?.toFixed(1)} km · estimated</span>
                  </Link>
                ))}
              </div>
            </Section>
          )}

          {d!.local.length > 0 && (
            <Section title="Support Local" subtitle="Independent neighbourhood businesses on Click.">
              <div className="gr-stores">{d!.local.map((s) => <StoreCard key={s.id} s={s} />)}</div>
            </Section>
          )}

          {sec('snacks', 'Biscuits, chips, chocolate, juices and more.')}
          {sec('home', 'Cleaning, laundry and household supplies.')}
          {sec('personal', 'Soap, shampoo, toothpaste and hygiene.')}
          {sec('more', 'Baby care, pet care and specialty.')}

          <div className="gr-tools">
            <Link to="/groceries/lists" className="gr-tool">
              <Icon name="receipt" size={22} />
              <span><strong>Shopping list</strong><span className="small muted">Write what you need. Click. finds which nearby stores have it.</span></span>
            </Link>
            <Link to="/food" className="gr-tool">
              <Icon name="food" size={22} />
              <span><strong>Need dinner instead?</strong><span className="small muted">Prepared meals are in Food.</span></span>
            </Link>
          </div>
        </>
      )}
      <BasketBar />
    </div>
  );
}
