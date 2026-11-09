import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { EmptyState, ErrorState, Icon, Skeleton } from '../components/ui';
import { OrderCard } from '../features/orders/OrderCard';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

/** Confirmation of a Shopping or Groceries checkout that became several orders (one per seller / store). */
export function CheckoutDonePage() {
  const { id = '' } = useParams();
  const r = useQuery({ queryKey: ['customer', 'checkouts', id], queryFn: () => api.customer.orders.getCheckout(id) });
  if (r.isError) return <ErrorState error={r.error} onRetry={() => r.refetch()} />;
  if (r.isPending) return <Skeleton height={260} radius={20} />;
  if (!r.data.checkout) return <EmptyState icon="receipt" title="Checkout not found" action={<Link to="/orders" className="btn btn--outline">Your orders</Link>} />;
  const { checkout, orders } = r.data;
  const grocery = orders.some((o) => o.store.storeType === 'grocery');
  return (
    <div className="stack" data-theme={grocery ? 'grocery' : 'shopping'}>
      <section className="placed" role="status" aria-labelledby="done-h">
        <span className="placed__check" aria-hidden="true"><Icon name="check" size={30} /></span>
        <h2 id="done-h">{orders.length} orders placed</h2>
        <p>{grocery ? 'Each store packs and delivers its part separately. We’ll update you as each store progresses.' : 'Each seller packs and ships their part separately. We’ll update you on every order.'}</p>
        <dl className="placed__facts">
          <div><dt>Checkout</dt><dd>{checkout.number}</dd></div>
          <div><dt>Total</dt><dd>{formatMoney(checkout.total, checkout.currency)}</dd></div>
        </dl>
        <div className="row" style={{ flexWrap: 'wrap', justifyContent: 'center' }}>
          <Link to={grocery ? '/groceries' : '/shopping'} className="btn btn--glass btn--sm">{grocery ? 'Continue Groceries' : 'Continue Shopping'}</Link>
          <Link to="/activity" className="btn btn--glass btn--sm">Activity</Link>
        </div>
      </section>
      <div className="card">{orders.map((o, i) => <div key={o.id} style={i ? { borderTop: '1px solid var(--c-line)' } : undefined}><OrderCard order={o} /></div>)}</div>
    </div>
  );
}
