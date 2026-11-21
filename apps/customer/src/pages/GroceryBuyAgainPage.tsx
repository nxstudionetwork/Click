import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { EmptyState, ErrorState, Icon, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { BasketBar, ProductCard } from '../features/groceries/parts';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';
import { useDeliveryLocation } from '../location/LocationProvider';

/** Everything from delivered grocery orders, at today's price and stock (never cloned from the old order). */
export function GroceryBuyAgainPage() {
  useThemeOverride('grocery');
  const { selected } = useDeliveryLocation();
  const q = useQuery({ queryKey: ['customer', 'groceries', 'buy-again', selected?.id], queryFn: () => api.groceries.buyAgain(selected?.id) });
  return (
    <div className="gr-page" data-theme="grocery">
      <Link to="/groceries" className="gr-back"><Icon name="back" size={18} /> Groceries</Link>
      <header className="gr-intro"><h1>Buy again<span>.</span></h1><p>Your repeat essentials, checked against today’s prices and stock.</p></header>
      {q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isPending ? <Skeleton height={260} /> : q.data.results.length === 0 ? (
        <EmptyState icon="history" title="Nothing yet" message="Your repeat essentials will appear here after your first orders." action={<Link to="/groceries" className="btn btn--primary">Shop groceries</Link>} />
      ) : (
        <>
          {q.data.runningLow.length > 0 && (
            <div className="gr-lowlist">
              {q.data.runningLow.map((r) => <div key={r.listing.id} className="gr-low"><Icon name="history" size={16} /><span><strong>{r.listing.name}</strong> — last bought {r.daysSince} days ago; you usually reorder about every {r.usualDays} days. You may be ready to reorder.</span></div>)}
            </div>
          )}
          <div className="gr-grid">
            {q.data.results.map((b) => (
              <div key={b.listing.id} className="gr-again">
                <ProductCard l={b.listing} />
                <span className="small muted">Bought {b.times}× · last paid {formatMoney(b.lastPrice)}{!b.sameStore ? ' · now from a nearby store' : ''}</span>
              </div>
            ))}
          </div>
        </>
      )}
      <BasketBar />
    </div>
  );
}
