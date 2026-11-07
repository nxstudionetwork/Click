import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { ErrorState, Icon, type IconName } from '../components/ui';
import { useStores } from '../features/stores/hooks';
import { StoreCard, StoreCardSkeleton } from '../features/stores/StoreCard';

/** Service catalogue. Only live services are navigable; others are clearly marked. */
const SERVICES: { name: string; icon: IconName; to?: string }[] = [
  { name: 'Food', icon: 'food', to: '/food' },
  { name: 'Groceries', icon: 'grocery' },
  { name: 'Shopping', icon: 'shop' },
  { name: 'Rides', icon: 'ride' },
  { name: 'Parcels', icon: 'parcel' },
  { name: 'Tickets', icon: 'ticket' },
];

export function HomePage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const stores = useStores({ type: 'restaurant' });
  const all = stores.data?.results ?? [];
  const withOffers = all.filter((s) => s.isOpen && s.offers.length > 0);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    navigate(`/food${q.trim() ? `?search=${encodeURIComponent(q.trim())}` : ''}`);
  };

  return (
    <>
      <section className="hero">
        <div className="stack" style={{ gap: 6 }}>
          <h1>{user?.fullName ? `Hi ${user.fullName.split(' ')[0]}, what do you need?` : 'Everything you need, one click away.'}</h1>
          <p>Order from the best places around you.</p>
        </div>
        <form className="search" onSubmit={submit} role="search">
          <Icon name="search" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search restaurants or dishes" aria-label="Search restaurants or dishes" />
        </form>
      </section>

      <section className="section" aria-labelledby="services-h">
        <h2 id="services-h">Services</h2>
        <div className="services">
          {SERVICES.map((s) =>
            s.to ? (
              <Link key={s.name} to={s.to} className="service service--live">
                <span className="service__icon"><Icon name={s.icon} /></span>
                <span className="service__name">{s.name}</span>
              </Link>
            ) : (
              <div key={s.name} className="service service--soon" aria-disabled="true">
                <span className="badge">Soon</span>
                <span className="service__icon"><Icon name={s.icon} /></span>
                <span className="service__name">{s.name}</span>
              </div>
            ),
          )}
        </div>
      </section>

      {stores.isError ? (
        <ErrorState error={stores.error} onRetry={() => stores.refetch()} />
      ) : (
        <>
          {(stores.isPending || withOffers.length > 0) && (
            <section className="section" aria-labelledby="offers-h">
              <div className="section__head"><h2 id="offers-h">Offers for you</h2></div>
              <div className="store-rail">
                {stores.isPending
                  ? Array.from({ length: 3 }, (_, i) => <StoreCardSkeleton key={i} />)
                  : withOffers.map((s) => <StoreCard key={s.id} store={s} />)}
              </div>
            </section>
          )}
          <section className="section" aria-labelledby="top-h">
            <div className="section__head"><h2 id="top-h">Top restaurants</h2><Link to="/food">See all</Link></div>
            <div className="store-grid">
              {stores.isPending
                ? Array.from({ length: 6 }, (_, i) => <StoreCardSkeleton key={i} />)
                : all.slice(0, 6).map((s) => <StoreCard key={s.id} store={s} />)}
            </div>
          </section>
        </>
      )}
    </>
  );
}
