import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { StoreType } from '@click/api';
import { EmptyState, ErrorState, Skeleton } from '../components/ui';
import { OfferCard } from '../features/offers/OfferCard';
import { api } from '../lib/api';

const TABS: { id: '' | StoreType; label: string }[] = [
  { id: '', label: 'All' }, { id: 'restaurant', label: 'Food' }, { id: 'grocery', label: 'Groceries' }, { id: 'retail', label: 'Shopping' },
];

export function OffersPage() {
  const [params, setParams] = useSearchParams();
  const type = (TABS.find((t) => t.id === params.get('type'))?.id ?? '') as '' | StoreType;
  const offers = useQuery({ queryKey: ['offers', type], queryFn: () => api.catalog.offers(type || undefined) });

  return (
    <div className="stack">
      <div className="page-head"><div><h1>Offers</h1><p>Current deals from stores on Click.</p></div></div>
      <div className="tabs" role="tablist" aria-label="Offer category">
        {TABS.map((t) => <button key={t.id || 'all'} role="tab" aria-selected={type === t.id} onClick={() => setParams(t.id ? { type: t.id } : {}, { replace: true })}>{t.label}</button>)}
      </div>
      {offers.isError ? <ErrorState error={offers.error} onRetry={() => offers.refetch()} />
        : offers.isPending ? <Skeleton height={96} radius={16} />
        : offers.data.results.length === 0 ? <EmptyState icon="tag" title="No offers right now" message="Check back soon for new deals." />
        : <div className="offer-grid">{offers.data.results.map((o) => <OfferCard key={o.id} offer={o} />)}</div>}
      <p className="small muted">Offers are set by each store and applied by the store. Automatic discounts at checkout are coming soon.</p>
    </div>
  );
}
