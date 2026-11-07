import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../auth/AuthProvider';
import { ErrorState, Icon, Skeleton } from '../components/ui';
import { SERVICES } from '../config/services';
import { EventCard } from '../features/bookings/EventCard';
import { useWallet } from '../features/wallet/useWallet';
import { formatMoney } from '../lib/format';
import { OfferCard } from '../features/offers/OfferCard';
import { OrderCard } from '../features/orders/OrderCard';
import { ServiceCard } from '../features/services/ServiceCard';
import { useStores } from '../features/stores/hooks';
import { StoreCard, StoreCardSkeleton } from '../features/stores/StoreCard';
import { api } from '../lib/api';

function greeting(name?: string) {
  const h = new Date().getHours();
  const part = h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
  return name ? `${part}, ${name.split(' ')[0]}` : part;
}

export function HomePage() {
  const { user, status } = useAuth();
  const authed = status === 'authenticated';
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const restaurants = useStores({ type: 'restaurant' });
  const grocery = useStores({ type: 'grocery' });
  const shops = useStores({ type: 'retail' });
  const offers = useQuery({ queryKey: ['offers', 'all'], queryFn: () => api.catalog.offers() });
  const recent = useQuery({ queryKey: ['customer', 'orders', 'list', 'recent'], queryFn: () => api.customer.orders.list(), enabled: authed });
  const rewards = useQuery({ queryKey: ['customer', 'rewards'], queryFn: api.customer.rewards, enabled: authed });
  const wallet = useWallet();
  const movies = useQuery({ queryKey: ['events', 'home'], queryFn: () => api.events.list({ status: 'now_showing' }) });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    navigate(`/search${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ''}`);
  };

  return (
    <>
      <section className="hero">
        <div className="stack" style={{ gap: 6 }}>
          <h1>{greeting(user?.fullName)}</h1>
          <p>What can Click do for you today?</p>
        </div>
        <form className="search" onSubmit={submit} role="search">
          <Icon name="search" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Try “biryani”, “earbuds” or “movies tonight”" aria-label="Search Click from home" />
          <button type="button" className="gsearch__tool gsearch__tool--ai" aria-label="Ask Buddy" onClick={() => navigate(q.trim() ? `/buddy?q=${encodeURIComponent(q.trim())}` : '/buddy')}><Icon name="sparkle" size={18} /></button>
        </form>
      </section>

      <section className="section" aria-labelledby="services-h">
        <div className="section__head"><h2 id="services-h">Services</h2><Link to="/explore">Explore all</Link></div>
        <div className="services">{SERVICES.map((s) => <ServiceCard key={s.id} service={s} />)}</div>
      </section>

      <section className="section dash-grid" aria-label="Your Click">
        {authed ? (
          <Link to="/rewards" className="dash-tile">
            <span className="dash-tile__icon"><Icon name="gift" /></span>
            <span className="stack" style={{ gap: 0 }}>
              <strong>{rewards.isPending ? '…' : rewards.isError ? 'Rewards' : `${rewards.data.balance.toLocaleString('en-IN')} Click points`}</strong>
              <span className="small muted">Earn points on every delivered order</span>
            </span>
          </Link>
        ) : (
          <Link to="/login" className="dash-tile">
            <span className="dash-tile__icon"><Icon name="user" /></span>
            <span className="stack" style={{ gap: 0 }}><strong>Sign in to Click</strong><span className="small muted">Track orders, save favourites, earn rewards</span></span>
          </Link>
        )}
        <Link to="/buddy" className="dash-tile dash-tile--ai">
          <span className="dash-tile__icon"><Icon name="sparkle" /></span>
          <span className="stack" style={{ gap: 0 }}><strong>Ask Buddy</strong><span className="small muted">Find, compare and plan across Click</span></span>
        </Link>
        {authed && (
          <Link to="/wallet" className="dash-tile">
            <span className="dash-tile__icon"><Icon name="wallet" /></span>
            <span className="stack" style={{ gap: 0 }}>
              <strong>{wallet.isPending ? '…' : wallet.isError ? 'Click Wallet' : `${formatMoney(wallet.data.balance, wallet.data.currency)} in wallet`}</strong>
              <span className="small muted">Refunds and credits, ready at checkout</span>
            </span>
          </Link>
        )}
      </section>

      {authed && (recent.isPending || (recent.data?.results.length ?? 0) > 0) && (
        <section className="section" aria-labelledby="recent-h">
          <div className="section__head"><h2 id="recent-h">Recent activity</h2><Link to="/orders">All orders</Link></div>
          {recent.isPending ? <Skeleton height={96} radius={16} /> : (
            <div className="card">{recent.data!.results.slice(0, 2).map((o) => <OrderCard key={o.id} order={o} />)}</div>
          )}
        </section>
      )}

      {(offers.isPending || (offers.data?.results.length ?? 0) > 0) && (
        <section className="section" aria-labelledby="offers-h">
          <div className="section__head"><h2 id="offers-h">Offers</h2><Link to="/offers">See all</Link></div>
          {offers.isPending ? <Skeleton height={96} radius={16} /> : (
            <div className="offer-grid">{offers.data!.results.slice(0, 3).map((o) => <OfferCard key={o.id} offer={o} />)}</div>
          )}
        </section>
      )}

      <StoreRail title="Top restaurants" to="/food" query={restaurants} />
      {(movies.isPending || (movies.data?.results.length ?? 0) > 0) && (
        <section className="section" aria-label="Movies and events" data-theme="movies">
          <div className="section__head"><h2>Movies & events near you</h2><Link to="/movies">See all</Link></div>
          {movies.isPending ? <Skeleton height={240} radius={16} /> : (
            <div className="store-rail store-rail--posters">{movies.data!.results.slice(0, 8).map((e) => <EventCard key={e.id} event={e} />)}</div>
          )}
        </section>
      )}
      <StoreRail title="Groceries" to="/groceries" query={grocery} />
      <StoreRail title="Shops" to="/shopping" query={shops} />

    </>
  );
}

function StoreRail({ title, to, query }: { title: string; to: string; query: ReturnType<typeof useStores> }) {
  if (query.isSuccess && query.data.results.length === 0) return null;
  return (
    <section className="section" aria-label={title}>
      <div className="section__head"><h2>{title}</h2><Link to={to}>See all</Link></div>
      {query.isError ? <ErrorState error={query.error} onRetry={() => query.refetch()} /> : (
        <div className="store-rail">
          {query.isPending
            ? Array.from({ length: 3 }, (_, i) => <StoreCardSkeleton key={i} />)
            : query.data.results.slice(0, 8).map((s) => <StoreCard key={s.id} store={s} />)}
        </div>
      )}
    </section>
  );
}
