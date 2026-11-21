import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { StoreQuery, StoreType } from '@click/api';
import { useAuth } from '../../auth/AuthProvider';
import { momentsFor, type HomeMoment } from '../../config/home';
import { useDeliveryLocation } from '../../location/LocationProvider';
import { useStores } from '../stores/hooks';
import { StoreCard } from '../stores/StoreCard';
import { HomeSection, Rail, RailItem, RailSkeleton, SectionEmpty, SectionError } from './HomeSection';

const NEAR_RADIUS_KM = 5;

function StoreRail({ query, label, empty }: { query: StoreQuery; label: string; empty: React.ReactNode }) {
  const stores = useStores(query);
  if (stores.isPending) return <RailSkeleton />;
  if (stores.isError) return <SectionError onRetry={() => stores.refetch()} />;
  if (stores.data.results.length === 0) return <>{empty}</>;
  return (
    <Rail label={label}>
      {stores.data.results.slice(0, 12).map((s) => <RailItem key={s.id}><StoreCard store={s} /></RailItem>)}
    </Rail>
  );
}

const NEAR_FILTERS: { id: StoreType | 'all'; label: string }[] = [
  { id: 'all', label: 'All' }, { id: 'restaurant', label: 'Food' }, { id: 'grocery', label: 'Groceries' }, { id: 'retail', label: 'Shops' },
];

/** Places around the selected location. Distance is shown only when the location has real coordinates. */
export function NearbySection() {
  const { status } = useAuth();
  const { selected, point, isLoading } = useDeliveryLocation();
  const [type, setType] = useState<StoreType | 'all'>('all');
  const typeQ = type === 'all' ? {} : { type };

  if (status === 'anonymous') {
    return (
      <HomeSection id="near" title="Near you" subtitle="Places and services around your location" icon="pin">
        <SectionEmpty icon="pin" title="Set your location" text="Sign in and choose a location to see places near you." action={<Link to="/login" className="btn btn--primary btn--sm">Sign in</Link>} />
      </HomeSection>
    );
  }
  if (isLoading || status === 'loading') {
    return <HomeSection id="near" title="Near you" icon="pin"><RailSkeleton /></HomeSection>;
  }
  if (!selected) {
    return (
      <HomeSection id="near" title="Near you" subtitle="Places and services around your location" icon="pin">
        <SectionEmpty icon="pin" title="Where are you?" text="Choose a location from the top of the page to see what’s near you." action={<Link to="/account/addresses" className="btn btn--outline btn--sm">Add a location</Link>} />
      </HomeSection>
    );
  }

  const located = !!point;
  const query: StoreQuery = located ? { ...typeQ, lat: point!.lat, lng: point!.lng, radius: NEAR_RADIUS_KM } : { ...typeQ, city: selected.city };
  return (
    <HomeSection
      id="near" icon="pin"
      title={located ? 'Near you' : `Around ${selected.city}`}
      subtitle={located ? `Within ${NEAR_RADIUS_KM} km of ${selected.label}` : `Pin ${selected.label} on the map to sort by distance`}
      to={type === 'grocery' ? '/groceries' : type === 'retail' ? '/shopping' : '/food'}
    >
      <div className="chips" role="group" aria-label="Filter nearby places">
        {NEAR_FILTERS.map((f) => <button key={f.id} className="chip" aria-pressed={type === f.id} onClick={() => setType(f.id)}>{f.label}</button>)}
      </div>
      <StoreRail
        query={query} label="Places near you"
        empty={<SectionEmpty icon="pin" title={located ? 'Nothing nearby yet' : `No places in ${selected.city} yet`} text="Try another category or change your location." />}
      />
    </HomeSection>
  );
}

export function PopularSection() {
  return (
    <HomeSection id="popular" title="Popular on Click." subtitle="Most rated by Click. customers" to="/food" icon="star" theme="food">
      <StoreRail query={{ type: 'restaurant', sort: 'popular' }} label="Popular restaurants" empty={<SectionEmpty title="Nothing popular yet" text="Ratings from customers will shape this list." />} />
    </HomeSection>
  );
}

/** Time-of-day sections from config (src/config/home.ts); each hides itself when the catalogue has nothing for it. */
export function MomentSections() {
  return <>{momentsFor().map((m) => <Moment key={m.id} moment={m} />)}</>;
}

function Moment({ moment: m }: { moment: HomeMoment }) {
  const stores = useStores(m.query);
  if (stores.isSuccess && stores.data.results.length === 0) return null;
  return (
    <HomeSection id={`m-${m.id}`} title={m.title} subtitle={m.subtitle} to={m.to} icon={m.icon} theme={m.theme}>
      <StoreRail query={m.query} label={m.title} empty={null} />
    </HomeSection>
  );
}
