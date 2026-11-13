import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { StoreCategory, StoreQuery } from '@click/api';
import { useAuth } from '../../auth/AuthProvider';
import { Icon } from '../../components/ui';
import type { ServicePageConfig } from '../../config/servicePages';
import { serviceForStoreType } from '../../config/services';
import { api } from '../../lib/api';
import { useDeliveryLocation } from '../../location/LocationProvider';
import { HomeSection, Rail, RailItem, RailSkeleton, SectionEmpty, SectionError } from '../home/HomeSection';
import { OfferCarouselFor } from '../home/OfferCarousel';
import { useStores } from '../stores/hooks';
import { StoreCard } from '../stores/StoreCard';

const NEAR_KM = 5;

function StoreRail({ query, label, emptyText }: { query: StoreQuery; label: string; emptyText: string }) {
  const stores = useStores(query);
  if (stores.isPending) return <RailSkeleton />;
  if (stores.isError) return <SectionError onRetry={() => stores.refetch()} />;
  if (stores.data.results.length === 0) return <SectionEmpty icon="pin" title={emptyText} text="Try changing your location or filters." />;
  return <Rail label={label}>{stores.data.results.slice(0, 12).map((s) => <RailItem key={s.id}><StoreCard store={s} /></RailItem>)}</Rail>;
}

/** Offers for this service (from the API; nothing hard-coded). Hidden when there are none. */
export function ServiceOffers({ config }: { config: ServicePageConfig }) {
  return <OfferCarouselFor type={config.storeType} title="Offers for you" subtitle={`Live deals on Click. ${config.title}`} hideWhenEmpty />;
}

/** Stores near the selected address. Distance is used only when the address has coordinates. */
export function ServiceNearby({ config }: { config: ServicePageConfig }) {
  const { status } = useAuth();
  const { selected, point } = useDeliveryLocation();
  const theme = serviceForStoreType(config.storeType).theme;
  if (status !== 'authenticated' || !selected) {
    return (
      <HomeSection id="svc-near" title={`${config.title} near you`} icon="pin" theme={theme}>
        <SectionEmpty icon="pin" title={`Add a delivery location to discover ${config.title.toLowerCase()} near you.`}
          action={<Link to={status === 'authenticated' ? '/account/addresses' : '/login'} className="btn btn--primary btn--sm">{status === 'authenticated' ? 'Add location' : 'Sign in'}</Link>} />
      </HomeSection>
    );
  }
  const query: StoreQuery = point ? { type: config.storeType, lat: point.lat, lng: point.lng, radius: NEAR_KM } : { type: config.storeType, city: selected.city };
  return (
    <HomeSection id="svc-near" title={point ? `Nearby ${config.plural}` : `${config.title} in ${selected.city}`} icon="pin" theme={theme}
      subtitle={point ? `Within ${NEAR_KM} km of ${selected.label}` : `Pin ${selected.label} to sort by distance`}>
      <StoreRail query={query} label={`Nearby ${config.plural}`} emptyText={`No ${config.plural} nearby yet`} />
    </HomeSection>
  );
}

/** Most-rated near the customer (rating counts are real customer ratings). */
export function ServicePopular({ config }: { config: ServicePageConfig }) {
  const { point } = useDeliveryLocation();
  const theme = serviceForStoreType(config.storeType).theme;
  const query: StoreQuery = point ? { type: config.storeType, sort: 'popular', lat: point.lat, lng: point.lng, radius: 10 } : { type: config.storeType, sort: 'popular' };
  return (
    <HomeSection id="svc-popular" title={point ? 'Popular near you' : `Popular on Click. ${config.title}`} subtitle="Most rated by Click. customers" icon="star" theme={theme}>
      <StoreRail query={query} label="Popular" emptyText="Nothing popular yet" />
    </HomeSection>
  );
}

/** Rule-based picks from the customer's own order history; each card says why it was picked. */
export function ServiceRecommended({ config }: { config: ServicePageConfig }) {
  const { status } = useAuth();
  const { point } = useDeliveryLocation();
  const theme = serviceForStoreType(config.storeType).theme;
  const recs = useQuery({
    queryKey: ['customer', 'recommendations', config.storeType, point?.lat, point?.lng],
    queryFn: () => api.customer.recommendedStores({ type: config.storeType, ...(point ? { lat: point.lat, lng: point.lng, radius: 10 } : {}) }),
    enabled: status === 'authenticated',
  });
  if (status !== 'authenticated') return null;
  return (
    <HomeSection id="svc-recs" title="Recommended for you" subtitle="Based on what you’ve ordered before" icon="sparkle" theme={theme}>
      {recs.isPending ? <RailSkeleton /> : recs.isError ? <SectionError onRetry={() => recs.refetch()} /> : recs.data.results.length === 0 ? (
        <SectionEmpty icon="sparkle" title="Order once and we’ll learn what you like." />
      ) : (
        <Rail label="Recommended">
          {recs.data.results.map((r) => (
            <RailItem key={r.store.id}>
              <div className="rec">
                <span className="rec__why"><Icon name="sparkle" size={12} />{r.reason}</span>
                <StoreCard store={r.store} />
              </div>
            </RailItem>
          ))}
        </Rail>
      )}
    </HomeSection>
  );
}

/** Category tiles to keep exploring (same categories as the top row). */
export function ServiceExploreCategories({ config, categories, onSelect }: { config: ServicePageConfig; categories: StoreCategory[]; onSelect: (slug: string) => void }) {
  if (categories.length === 0) return null;
  return (
    <HomeSection id="svc-explore" title={`Explore ${config.categoriesLabel.toLowerCase()}`} icon="compass" theme={serviceForStoreType(config.storeType).theme}>
      <div className="svc-tiles">
        {categories.map((c) => (
          <button key={c.id} type="button" className="svc-tile" onClick={() => { onSelect(c.slug); window.scrollTo?.({ top: 0, behavior: 'smooth' }); }}>
            <Icon name={config.categoryIcons[c.slug] ?? config.fallbackIcon} size={20} /><span>{c.name}</span>
          </button>
        ))}
      </div>
    </HomeSection>
  );
}
